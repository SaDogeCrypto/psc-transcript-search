"""
Pipeline Orchestrator

Single-process, database-driven pipeline execution for PSC hearing processing.

Architecture:
- Polls database for hearings in actionable states
- Processes one hearing at a time (single-threaded for simplicity)
- Uses database as source of truth for state
- Supports pause/resume/stop via database state

Usage:
    python -m app.pipeline.orchestrator run
    python -m app.pipeline.orchestrator run --once --states FL,GA
    python -m app.pipeline.orchestrator run --only transcribe --max-cost 50
    python -m app.pipeline.orchestrator status
"""

import os
import sys
import signal
import logging
import threading
import argparse
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
from enum import Enum

from sqlalchemy.orm import Session
from sqlalchemy import func

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.database import SessionLocal
from app.models.database import Hearing, PipelineJob, PipelineState, State

logger = logging.getLogger(__name__)


# =============================================================================
# STATUS DEFINITIONS
# =============================================================================

class PipelineStatus(str, Enum):
    """Orchestrator status."""
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPING = "stopping"


# Hearing status progression through the pipeline
# Flow: discovered -> downloaded -> transcribed -> analyzed -> extracted -> complete
HEARING_STATUSES = {
    "discovered": {"next": "downloading", "stage": "download"},
    "downloading": {"next": "downloaded", "stage": "download", "in_progress": True},
    "downloaded": {"next": "transcribing", "stage": "transcribe"},
    "transcribing": {"next": "transcribed", "stage": "transcribe", "in_progress": True},
    "transcribed": {"next": "analyzing", "stage": "analyze"},
    "analyzing": {"next": "analyzed", "stage": "analyze", "in_progress": True},
    "analyzed": {"next": "extracting", "stage": "extract"},
    "extracting": {"next": "extracted", "stage": "extract", "in_progress": True},
    "extracted": {"next": "complete", "stage": None},
    "complete": {"next": None, "stage": None, "terminal": True},
    "error": {"next": None, "stage": None, "retryable": True},
    "failed": {"next": None, "stage": None, "terminal": True},
    "skipped": {"next": None, "stage": None, "terminal": True},
}

# Statuses that can be picked up for processing (non-in-progress, non-terminal)
PROCESSABLE_STATUSES = ["discovered", "downloaded", "transcribed", "analyzed", "extracted", "error"]

# Map from stage name to (in_progress_status, complete_status)
STAGE_TO_STATUS = {
    "download": ("downloading", "downloaded"),
    "transcribe": ("transcribing", "transcribed"),
    "analyze": ("analyzing", "analyzed"),
    "extract": ("extracting", "extracted"),
}


# =============================================================================
# CONFIGURATION
# =============================================================================

@dataclass
class OrchestratorConfig:
    """Configuration for the orchestrator."""
    # Polling
    poll_interval: int = 60  # seconds between polls when idle
    batch_size: int = 1  # hearings per batch (1 = sequential)

    # Retries
    max_retries: int = 3
    retry_backoff_base: int = 300  # 5 min, doubles each retry

    # Cost controls
    max_cost_per_run: Optional[float] = None
    max_cost_per_day: float = 100.0

    # Filters
    states: Optional[List[str]] = None  # State codes to process
    only_stage: Optional[str] = None  # download, transcribe, analyze, extract
    max_hearings: Optional[int] = None  # Max hearings per run

    @classmethod
    def from_env(cls):
        """Load config from environment variables."""
        return cls(
            poll_interval=int(os.getenv("PIPELINE_POLL_INTERVAL", 60)),
            max_cost_per_run=float(os.getenv("PIPELINE_MAX_COST")) if os.getenv("PIPELINE_MAX_COST") else None,
            max_cost_per_day=float(os.getenv("PIPELINE_MAX_DAILY_COST", 100)),
            max_retries=int(os.getenv("PIPELINE_MAX_RETRIES", 3)),
        )


# =============================================================================
# ORCHESTRATOR
# =============================================================================

class PipelineOrchestrator:
    """
    Main orchestrator class.

    State machine:
    discovered -> downloading -> transcribing -> transcribed
    -> analyzing -> analyzed -> extracting -> extracted -> complete

    Any state can transition to: error (retryable), failed (permanent), skipped
    """

    def __init__(self, config: Optional[OrchestratorConfig] = None):
        self.config = config or OrchestratorConfig.from_env()
        self._stop_requested = threading.Event()
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._stages = None  # Lazy loaded
        self._daily_cost = 0.0
        self._run_cost = 0.0
        self._hearings_processed = 0  # Fully completed hearings
        self._hearings_attempted: set = set()  # Unique hearing IDs worked on this run

    @property
    def stages(self):
        """Lazy load stages to avoid import issues."""
        if self._stages is None:
            from app.pipeline.stages.download import DownloadStage
            from app.pipeline.stages.transcribe import TranscribeStage
            from app.pipeline.stages.analyze import AnalyzeStage
            from app.pipeline.stages.extract import ExtractStage

            self._stages = {
                "download": DownloadStage(),
                "transcribe": TranscribeStage(),
                "analyze": AnalyzeStage(),
                "extract": ExtractStage(),
            }
        return self._stages

    def _get_db(self) -> Session:
        """Get database session."""
        return SessionLocal()

    def _get_state(self, db: Session) -> PipelineState:
        """Get or create pipeline state singleton."""
        state = db.query(PipelineState).filter(PipelineState.id == 1).first()
        if not state:
            state = PipelineState(id=1, status="idle")
            db.add(state)
            db.commit()
        return state

    def _update_state(self, db: Session, **kwargs):
        """Update pipeline state."""
        state = self._get_state(db)
        for key, value in kwargs.items():
            setattr(state, key, value)
        state.updated_at = datetime.now(timezone.utc)
        db.commit()

    # -------------------------------------------------------------------------
    # Control methods
    # -------------------------------------------------------------------------

    def request_stop(self):
        """Request the orchestrator to stop after current hearing."""
        self._stop_requested.set()
        db = self._get_db()
        try:
            self._update_state(db, status=PipelineStatus.STOPPING.value)
        finally:
            db.close()
        logger.info("Stop requested - will stop after current hearing")

    def pause(self):
        """Pause the orchestrator."""
        db = self._get_db()
        try:
            self._update_state(db, status=PipelineStatus.PAUSED.value)
        finally:
            db.close()
        logger.info("Pipeline paused")

    def resume(self):
        """Resume a paused orchestrator."""
        db = self._get_db()
        try:
            state = self._get_state(db)
            if state.status == PipelineStatus.PAUSED.value:
                self._update_state(db, status=PipelineStatus.RUNNING.value)
                logger.info("Pipeline resumed")
            else:
                logger.warning(f"Cannot resume - status is {state.status}")
        finally:
            db.close()

    def get_status(self) -> Dict[str, Any]:
        """Get current orchestrator status and stats."""
        db = self._get_db()
        try:
            state = self._get_state(db)

            # Get counts by status
            status_counts = dict(
                db.query(Hearing.status, func.count(Hearing.id))
                .group_by(Hearing.status)
                .all()
            )

            # Get today's stats
            today = datetime.now(timezone.utc).date()
            today_jobs = db.query(PipelineJob).filter(
                func.date(PipelineJob.completed_at) == today,
                PipelineJob.status == "complete"
            ).all()
            processed_today = len(set(j.hearing_id for j in today_jobs))
            cost_today = sum(float(j.cost_usd or 0) for j in today_jobs)
            errors_today = db.query(PipelineJob).filter(
                func.date(PipelineJob.completed_at) == today,
                PipelineJob.status == "error"
            ).count()

            # Current hearing info
            current_hearing_title = None
            if state.current_hearing_id:
                hearing = db.query(Hearing).filter(Hearing.id == state.current_hearing_id).first()
                current_hearing_title = hearing.title[:100] if hearing else None

            return {
                "status": state.status,
                "started_at": state.started_at.isoformat() if state.started_at else None,
                "current_hearing_id": state.current_hearing_id,
                "current_hearing_title": current_hearing_title,
                "current_stage": state.current_stage,
                "hearings_processed": state.hearings_processed,
                "errors_count": state.errors_count,
                "total_cost_usd": float(state.total_cost_usd or 0),
                "stage_counts": status_counts,
                "processed_today": processed_today,
                "cost_today": cost_today,
                "errors_today": errors_today,
            }
        finally:
            db.close()

    # -------------------------------------------------------------------------
    # Run methods
    # -------------------------------------------------------------------------

    def run_async(self):
        """Run orchestrator in background thread."""
        if self._thread and self._thread.is_alive():
            raise RuntimeError("Orchestrator already running")

        self._thread = threading.Thread(target=self.run, daemon=True)
        self._thread.start()

    def run(self, once: bool = False, dry_run: bool = False) -> Dict[str, Any]:
        """
        Main run loop.

        Args:
            once: Exit after processing all available work (for cron)
            dry_run: Show what would be processed without doing it

        Returns:
            Dict with run statistics
        """
        self._stop_requested.clear()
        self._run_cost = 0.0
        self._hearings_processed = 0
        self._hearings_attempted = set()

        db = self._get_db()

        try:
            # Update state to running
            self._update_state(
                db,
                status=PipelineStatus.RUNNING.value,
                started_at=datetime.now(timezone.utc),
                hearings_processed=0,
                errors_count=0,
                total_cost_usd=0,
                config_json={
                    "states": self.config.states,
                    "only_stage": self.config.only_stage,
                    "max_cost": self.config.max_cost_per_run,
                }
            )

            logger.info(f"Pipeline started (states={self.config.states}, only_stage={self.config.only_stage})")

            while not self._stop_requested.is_set():
                # Check limits
                if self._should_stop():
                    break

                # Check if paused
                state = self._get_state(db)
                if state.status == PipelineStatus.PAUSED.value:
                    logger.debug("Pipeline paused, sleeping...")
                    self._stop_requested.wait(self.config.poll_interval)
                    continue

                # Find and process next hearing
                hearing = self._get_next_hearing(db)

                if hearing:
                    if dry_run:
                        logger.info(f"[DRY RUN] Would process: {hearing.id} - {hearing.title[:50]}... (status={hearing.status})")
                        # Mark as processed to avoid infinite loop in dry run
                        continue
                    else:
                        self._process_hearing(hearing, db)
                else:
                    if once:
                        logger.info("No more work found, exiting (--once mode)")
                        break
                    logger.debug(f"No work found, sleeping {self.config.poll_interval}s")
                    self._stop_requested.wait(self.config.poll_interval)

        except Exception as e:
            logger.exception(f"Orchestrator error: {e}")
            self._update_state(db, last_error=str(e)[:1000])

        finally:
            # Update final state
            self._update_state(
                db,
                status=PipelineStatus.IDLE.value,
                current_hearing_id=None,
                current_stage=None,
            )
            db.close()

        return {
            "hearings_processed": self._hearings_processed,
            "total_cost": self._run_cost,
        }

    def _should_stop(self) -> bool:
        """Check if we should stop due to limits."""
        if self.config.max_cost_per_run and self._run_cost >= self.config.max_cost_per_run:
            logger.info(f"Run cost limit reached (${self._run_cost:.2f})")
            return True

        # max_hearings limits unique hearings attempted, not just completed
        if self.config.max_hearings and len(self._hearings_attempted) >= self.config.max_hearings:
            logger.info(f"Max hearings limit reached ({len(self._hearings_attempted)} attempted)")
            return True

        return False

    def _get_next_hearing(self, db: Session) -> Optional[Hearing]:
        """Find the next hearing that needs processing."""
        # Determine which statuses to look for based on only_stage filter
        if self.config.only_stage:
            # Map stage to the input status it processes FROM
            stage_input_statuses = {
                "download": ["discovered"],
                "transcribe": ["downloaded"],
                "analyze": ["transcribed"],
                "extract": ["analyzed"],
            }
            statuses = stage_input_statuses.get(self.config.only_stage, PROCESSABLE_STATUSES)
        else:
            statuses = PROCESSABLE_STATUSES

        query = db.query(Hearing).filter(Hearing.status.in_(statuses))

        # Exclude hearings already attempted in this run (to avoid re-trying failed ones in same run)
        if self._hearings_attempted:
            query = query.filter(~Hearing.id.in_(self._hearings_attempted))

        # Filter by states
        if self.config.states:
            state_ids = db.query(State.id).filter(
                State.code.in_([s.upper() for s in self.config.states])
            ).all()
            state_ids = [s[0] for s in state_ids]
            query = query.filter(Hearing.state_id.in_(state_ids))

        # For error status, check retry eligibility
        # (skip if max retries exceeded or in backoff period)

        # Priority: oldest first (FIFO by hearing_date, then created_at)
        query = query.order_by(Hearing.hearing_date.asc(), Hearing.created_at.asc())

        return query.first()

    def _process_hearing(self, hearing: Hearing, db: Session):
        """Process a single hearing through its next stage."""
        # Track this hearing as attempted for max_hearings limit
        self._hearings_attempted.add(hearing.id)

        logger.info(f"Processing hearing {hearing.id}: {hearing.title[:50]}... (status={hearing.status})")

        # Determine which stage to run
        status_info = HEARING_STATUSES.get(hearing.status, {})
        stage_name = status_info.get("stage")

        if hearing.status == "error":
            # Retry: determine last failed stage
            last_job = db.query(PipelineJob).filter(
                PipelineJob.hearing_id == hearing.id,
                PipelineJob.status == "error"
            ).order_by(PipelineJob.created_at.desc()).first()

            if last_job:
                # Check retry count
                if last_job.retry_count >= self.config.max_retries:
                    logger.warning(f"Hearing {hearing.id} exceeded max retries, marking failed")
                    hearing.status = "failed"
                    db.commit()
                    return

                stage_name = last_job.stage
            else:
                # No failed job found, reset to discovered
                hearing.status = "discovered"
                db.commit()
                return

        if hearing.status == "extracted":
            # Just mark complete
            hearing.status = "complete"
            self._hearings_processed += 1
            self._update_state(
                db,
                hearings_processed=self._hearings_processed,
                current_hearing_id=None,
                current_stage=None,
            )
            db.commit()
            logger.info(f"Hearing {hearing.id} marked complete")
            return

        if not stage_name or stage_name not in self.stages:
            logger.warning(f"No stage found for hearing {hearing.id} (status={hearing.status})")
            return

        stage = self.stages[stage_name]
        in_progress_status, complete_status = STAGE_TO_STATUS[stage_name]

        # Update orchestrator state
        self._update_state(
            db,
            current_hearing_id=hearing.id,
            current_stage=stage_name,
        )

        # Create or update pipeline job
        job = db.query(PipelineJob).filter(
            PipelineJob.hearing_id == hearing.id,
            PipelineJob.stage == stage_name
        ).first()

        if not job:
            job = PipelineJob(
                hearing_id=hearing.id,
                stage=stage_name,
                status="pending",
                retry_count=0,
            )
            db.add(job)

        job.status = "running"
        job.started_at = datetime.now(timezone.utc)

        # Update hearing status to in-progress
        hearing.status = in_progress_status
        hearing.processing_started_at = datetime.now(timezone.utc)
        db.commit()

        # Run the stage
        try:
            # Validate
            if not stage.validate(hearing, db):
                logger.warning(f"Stage {stage_name} validation failed for hearing {hearing.id}")
                job.status = "error"
                job.error_message = "Validation failed"
                hearing.status = "error"
                db.commit()
                return

            # Execute
            stage.on_start(hearing, job, db)
            result = stage.execute(hearing, db)

            if result.success:
                job.status = "complete"
                job.completed_at = datetime.now(timezone.utc)
                job.cost_usd = result.cost_usd
                hearing.status = complete_status
                hearing.processing_cost_usd = float(hearing.processing_cost_usd or 0) + result.cost_usd
                self._run_cost += result.cost_usd
                stage.on_success(hearing, job, result, db)
                logger.info(f"Stage {stage_name} complete for hearing {hearing.id} (cost=${result.cost_usd:.4f})")
            else:
                job.status = "error"
                job.error_message = result.error[:1000] if result.error else "Unknown error"
                job.retry_count += 1
                hearing.status = "error" if result.should_retry else "failed"
                stage.on_error(hearing, job, result, db)
                self._update_state(db, errors_count=self._get_state(db).errors_count + 1)
                logger.error(f"Stage {stage_name} failed for hearing {hearing.id}: {result.error}")

            db.commit()

            # If stage marked skip_remaining, mark hearing as skipped
            if result.skip_remaining:
                hearing.status = "skipped"
                db.commit()

            # Count as processed if completed a full cycle
            if hearing.status == "complete":
                self._hearings_processed += 1
                self._update_state(db, hearings_processed=self._hearings_processed)

        except Exception as e:
            logger.exception(f"Exception in stage {stage_name} for hearing {hearing.id}")
            job.status = "error"
            job.error_message = str(e)[:1000]
            job.retry_count += 1
            hearing.status = "error"
            self._update_state(
                db,
                errors_count=self._get_state(db).errors_count + 1,
                last_error=str(e)[:1000]
            )
            db.commit()


# =============================================================================
# SINGLETON
# =============================================================================

_orchestrator: Optional[PipelineOrchestrator] = None


def get_orchestrator(config: Optional[OrchestratorConfig] = None) -> PipelineOrchestrator:
    """Get or create the global orchestrator instance."""
    global _orchestrator
    if _orchestrator is None or config is not None:
        _orchestrator = PipelineOrchestrator(config)
    return _orchestrator


# =============================================================================
# CLI
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="Pipeline Orchestrator")
    parser.add_argument("command", choices=["run", "status", "retry-failed"], nargs="?", default="run")
    parser.add_argument("--once", action="store_true", help="Exit after processing available work")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be processed")
    parser.add_argument("--states", help="Comma-separated state codes (e.g., FL,GA,TX)")
    parser.add_argument("--only", choices=["download", "transcribe", "analyze", "extract"],
                       help="Only run specific stage")
    parser.add_argument("--max-cost", type=float, help="Max cost for this run")
    parser.add_argument("--max-hearings", type=int, help="Max hearings to process")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )

    if args.command == "run":
        config = OrchestratorConfig.from_env()

        if args.states:
            config.states = [s.strip() for s in args.states.split(",")]
        if args.only:
            config.only_stage = args.only
        if args.max_cost:
            config.max_cost_per_run = args.max_cost
        if args.max_hearings:
            config.max_hearings = args.max_hearings

        orchestrator = get_orchestrator(config)

        # Handle Ctrl+C gracefully
        def signal_handler(sig, frame):
            print("\nStopping orchestrator (will finish current hearing)...")
            orchestrator.request_stop()

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

        result = orchestrator.run(once=args.once, dry_run=args.dry_run)

        print(f"\nPipeline finished:")
        print(f"  Hearings processed: {result['hearings_processed']}")
        print(f"  Total cost: ${result['total_cost']:.4f}")

    elif args.command == "status":
        orchestrator = get_orchestrator()
        status = orchestrator.get_status()

        print("\nPipeline Status")
        print("=" * 50)
        print(f"  Status:            {status['status']}")
        print(f"  Started at:        {status['started_at'] or 'N/A'}")
        print(f"  Current hearing:   {status['current_hearing_id'] or 'None'}")
        print(f"  Current stage:     {status['current_stage'] or 'None'}")
        print(f"  Hearings processed:{status['hearings_processed']}")
        print(f"  Errors:            {status['errors_count']}")
        print(f"  Total cost:        ${status['total_cost_usd']:.4f}")

        print("\nToday's Stats:")
        print(f"  Processed: {status['processed_today']}")
        print(f"  Cost:      ${status['cost_today']:.4f}")
        print(f"  Errors:    {status['errors_today']}")

        print("\nHearing Status Counts:")
        for status_name, count in sorted(status.get('stage_counts', {}).items()):
            print(f"  {status_name:15} {count:6}")

    elif args.command == "retry-failed":
        db = SessionLocal()
        try:
            failed = db.query(Hearing).filter(
                Hearing.status.in_(["error", "failed"])
            ).all()

            for h in failed:
                h.status = "discovered"
                # Reset retry counts on jobs
                for job in h.pipeline_jobs:
                    if job.status == "error":
                        job.retry_count = 0

            db.commit()
            print(f"Reset {len(failed)} failed hearings to retry")
        finally:
            db.close()


if __name__ == "__main__":
    main()
