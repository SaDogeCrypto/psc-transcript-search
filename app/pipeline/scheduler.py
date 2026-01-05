"""
Pipeline Scheduler

Database-backed scheduler for automated pipeline and scraper runs.

Schedule types:
- interval: "30m", "1h", "4h", "1d"
- daily: "08:00", "14:30" (UTC)
- cron: "0 */4 * * *"

Usage:
    python -m app.pipeline.scheduler run    # Run scheduler daemon
    python -m app.pipeline.scheduler list   # List schedules
    python -m app.pipeline.scheduler create # Create new schedule
"""

import os
import re
import time
import signal
import logging
import argparse
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.database import PipelineSchedule

logger = logging.getLogger(__name__)


def parse_interval(value: str) -> timedelta:
    """
    Parse interval string to timedelta.

    Supports: 30m, 1h, 2h, 4h, 12h, 1d, 7d
    """
    match = re.match(r'^(\d+)(m|h|d)$', value.lower())
    if not match:
        raise ValueError(f"Invalid interval format: {value}. Use format like '30m', '1h', '1d'")

    amount = int(match.group(1))
    unit = match.group(2)

    if unit == 'm':
        return timedelta(minutes=amount)
    elif unit == 'h':
        return timedelta(hours=amount)
    elif unit == 'd':
        return timedelta(days=amount)


def parse_daily_time(value: str) -> tuple:
    """
    Parse daily time string to (hour, minute).

    Supports: "08:00", "14:30", "23:45"
    """
    match = re.match(r'^(\d{1,2}):(\d{2})$', value)
    if not match:
        raise ValueError(f"Invalid time format: {value}. Use format like '08:00', '14:30'")

    hour = int(match.group(1))
    minute = int(match.group(2))

    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError(f"Invalid time: {value}. Hours must be 0-23, minutes 0-59")

    return (hour, minute)


def calculate_next_run(schedule: PipelineSchedule) -> Optional[datetime]:
    """Calculate next run time based on schedule type and value."""
    now = datetime.now(timezone.utc)

    if schedule.schedule_type == "interval":
        interval = parse_interval(schedule.schedule_value)
        if schedule.last_run_at:
            return schedule.last_run_at + interval
        return now

    elif schedule.schedule_type == "daily":
        hour, minute = parse_daily_time(schedule.schedule_value)
        next_run = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if next_run <= now:
            next_run += timedelta(days=1)
        return next_run

    elif schedule.schedule_type == "cron":
        try:
            from croniter import croniter
            cron = croniter(schedule.schedule_value, now)
            return cron.get_next(datetime)
        except ImportError:
            logger.warning("croniter not installed, cron schedules not supported")
            return None
        except Exception as e:
            logger.error(f"Invalid cron expression '{schedule.schedule_value}': {e}")
            return None

    return None


def format_schedule_display(schedule: PipelineSchedule) -> str:
    """Format schedule for human-readable display."""
    if schedule.schedule_type == "interval":
        return f"Every {schedule.schedule_value}"

    elif schedule.schedule_type == "daily":
        hour, minute = parse_daily_time(schedule.schedule_value)
        period = "AM" if hour < 12 else "PM"
        display_hour = hour % 12 or 12
        return f"Daily at {display_hour}:{minute:02d} {period} UTC"

    elif schedule.schedule_type == "cron":
        return f"Cron: {schedule.schedule_value}"

    return "Unknown"


class PipelineScheduler:
    """
    Database-backed scheduler daemon.

    Checks for due schedules and triggers pipeline/scraper runs.
    """

    def __init__(self, check_interval: int = 60):
        self.check_interval = check_interval
        self.running = False
        self._stop_requested = False

    def run(self):
        """Main scheduler loop."""
        self.running = True
        self._stop_requested = False
        logger.info("Scheduler started")

        while not self._stop_requested:
            try:
                self._check_schedules()
            except Exception as e:
                logger.exception(f"Scheduler error: {e}")

            # Sleep in small increments to allow responsive shutdown
            for _ in range(self.check_interval):
                if self._stop_requested:
                    break
                time.sleep(1)

        self.running = False
        logger.info("Scheduler stopped")

    def stop(self):
        """Request scheduler to stop."""
        self._stop_requested = True

    def _check_schedules(self):
        """Check for due schedules and execute them."""
        db = SessionLocal()
        try:
            now = datetime.now(timezone.utc)

            # Find due schedules
            due_schedules = db.query(PipelineSchedule).filter(
                PipelineSchedule.enabled == True,
                PipelineSchedule.next_run_at <= now
            ).all()

            for schedule in due_schedules:
                logger.info(f"Running schedule: {schedule.name} (target={schedule.target})")
                self._run_schedule(schedule, db)

        finally:
            db.close()

    def _run_schedule(self, schedule: PipelineSchedule, db: Session):
        """Execute a scheduled pipeline/scraper run."""
        config = schedule.config_json or {}

        try:
            if schedule.target in ("pipeline", "all"):
                self._run_pipeline(config)

            if schedule.target in ("scraper", "all"):
                self._run_scraper(config)

            schedule.last_run_at = datetime.now(timezone.utc)
            schedule.last_run_status = "success"
            schedule.last_run_error = None

        except Exception as e:
            logger.exception(f"Schedule {schedule.name} failed: {e}")
            schedule.last_run_status = "error"
            schedule.last_run_error = str(e)[:500]

        finally:
            # Calculate next run
            schedule.next_run_at = calculate_next_run(schedule)
            schedule.updated_at = datetime.now(timezone.utc)
            db.commit()

    def _run_pipeline(self, config: dict):
        """Run pipeline orchestrator with config."""
        from app.pipeline.orchestrator import PipelineOrchestrator, OrchestratorConfig

        orchestrator_config = OrchestratorConfig(
            states=config.get("states"),
            only_stage=config.get("only_stage"),
            max_cost_per_run=config.get("max_cost"),
            max_hearings=config.get("max_hearings"),
        )

        orchestrator = PipelineOrchestrator(orchestrator_config)
        result = orchestrator.run(once=True)
        logger.info(f"Pipeline run complete: {result}")

    def _run_scraper(self, config: dict):
        """Run scraper orchestrator with config."""
        from scripts.scraper_orchestrator import get_orchestrator

        orchestrator = get_orchestrator()
        result = orchestrator.run(
            scraper_types=config.get("scraper_types"),
            state_code=config.get("state"),
            dry_run=config.get("dry_run", False)
        )
        logger.info(f"Scraper run complete: {result.get('status')}")


# =============================================================================
# SCHEDULE MANAGEMENT
# =============================================================================

def create_schedule(
    name: str,
    schedule_type: str,
    schedule_value: str,
    target: str = "pipeline",
    enabled: bool = True,
    config: Optional[dict] = None
) -> PipelineSchedule:
    """Create a new schedule."""
    db = SessionLocal()
    try:
        # Validate schedule value
        if schedule_type == "interval":
            parse_interval(schedule_value)
        elif schedule_type == "daily":
            parse_daily_time(schedule_value)
        elif schedule_type == "cron":
            try:
                from croniter import croniter
                croniter(schedule_value)
            except ImportError:
                raise ValueError("croniter package required for cron schedules")

        schedule = PipelineSchedule(
            name=name,
            schedule_type=schedule_type,
            schedule_value=schedule_value,
            target=target,
            enabled=enabled,
            config_json=config or {},
        )
        schedule.next_run_at = calculate_next_run(schedule)

        db.add(schedule)
        db.commit()
        db.refresh(schedule)

        logger.info(f"Created schedule: {name}")
        return schedule

    finally:
        db.close()


def list_schedules() -> List[Dict[str, Any]]:
    """List all schedules."""
    db = SessionLocal()
    try:
        schedules = db.query(PipelineSchedule).order_by(PipelineSchedule.name).all()

        return [{
            "id": s.id,
            "name": s.name,
            "schedule_type": s.schedule_type,
            "schedule_value": s.schedule_value,
            "schedule_display": format_schedule_display(s),
            "target": s.target,
            "enabled": s.enabled,
            "config": s.config_json,
            "last_run_at": s.last_run_at.isoformat() if s.last_run_at else None,
            "next_run_at": s.next_run_at.isoformat() if s.next_run_at else None,
            "last_run_status": s.last_run_status,
        } for s in schedules]

    finally:
        db.close()


def toggle_schedule(schedule_id: int) -> bool:
    """Toggle schedule enabled/disabled. Returns new enabled state."""
    db = SessionLocal()
    try:
        schedule = db.query(PipelineSchedule).filter(PipelineSchedule.id == schedule_id).first()
        if not schedule:
            raise ValueError(f"Schedule {schedule_id} not found")

        schedule.enabled = not schedule.enabled
        if schedule.enabled:
            schedule.next_run_at = calculate_next_run(schedule)
        else:
            schedule.next_run_at = None

        db.commit()
        return schedule.enabled

    finally:
        db.close()


def delete_schedule(schedule_id: int):
    """Delete a schedule."""
    db = SessionLocal()
    try:
        schedule = db.query(PipelineSchedule).filter(PipelineSchedule.id == schedule_id).first()
        if not schedule:
            raise ValueError(f"Schedule {schedule_id} not found")

        db.delete(schedule)
        db.commit()
        logger.info(f"Deleted schedule: {schedule.name}")

    finally:
        db.close()


# =============================================================================
# CLI
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="Pipeline Scheduler")
    subparsers = parser.add_subparsers(dest="command", help="Command")

    # Run command
    run_parser = subparsers.add_parser("run", help="Run scheduler daemon")
    run_parser.add_argument("--interval", type=int, default=60, help="Check interval in seconds")

    # List command
    list_parser = subparsers.add_parser("list", help="List all schedules")

    # Create command
    create_parser = subparsers.add_parser("create", help="Create new schedule")
    create_parser.add_argument("name", help="Schedule name")
    create_parser.add_argument("--type", required=True, choices=["interval", "daily", "cron"],
                              help="Schedule type")
    create_parser.add_argument("--value", required=True, help="Schedule value (e.g., '1h', '08:00', '0 */4 * * *')")
    create_parser.add_argument("--target", default="pipeline", choices=["pipeline", "scraper", "all"],
                              help="What to run")
    create_parser.add_argument("--states", help="Comma-separated state codes")
    create_parser.add_argument("--max-cost", type=float, help="Max cost per run")

    # Delete command
    delete_parser = subparsers.add_parser("delete", help="Delete schedule")
    delete_parser.add_argument("schedule_id", type=int, help="Schedule ID")

    # Toggle command
    toggle_parser = subparsers.add_parser("toggle", help="Enable/disable schedule")
    toggle_parser.add_argument("schedule_id", type=int, help="Schedule ID")

    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )

    if args.command == "run":
        scheduler = PipelineScheduler(check_interval=args.interval)

        def signal_handler(sig, frame):
            print("\nStopping scheduler...")
            scheduler.stop()

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

        scheduler.run()

    elif args.command == "list":
        schedules = list_schedules()
        if not schedules:
            print("No schedules configured.")
            return

        print("\nPipeline Schedules")
        print("=" * 80)
        for s in schedules:
            status_icon = "●" if s["enabled"] else "○"
            print(f"\n{status_icon} [{s['id']}] {s['name']}")
            print(f"    {s['schedule_display']} | Target: {s['target']}")
            if s["last_run_at"]:
                print(f"    Last run: {s['last_run_at'][:19]} ({s['last_run_status']})")
            if s["next_run_at"]:
                print(f"    Next run: {s['next_run_at'][:19]}")

    elif args.command == "create":
        config = {}
        if args.states:
            config["states"] = [s.strip() for s in args.states.split(",")]
        if args.max_cost:
            config["max_cost"] = args.max_cost

        schedule = create_schedule(
            name=args.name,
            schedule_type=args.type,
            schedule_value=args.value,
            target=args.target,
            config=config or None
        )
        print(f"Created schedule: {schedule.name} (ID: {schedule.id})")
        print(f"  {format_schedule_display(schedule)}")
        print(f"  Next run: {schedule.next_run_at}")

    elif args.command == "delete":
        delete_schedule(args.schedule_id)
        print(f"Deleted schedule {args.schedule_id}")

    elif args.command == "toggle":
        enabled = toggle_schedule(args.schedule_id)
        print(f"Schedule {args.schedule_id} is now {'enabled' if enabled else 'disabled'}")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
