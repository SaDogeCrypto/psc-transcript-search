"""
Pipeline orchestrator - coordinates running stages on hearings.

Provides:
- Run single stage on single hearing
- Run single stage on batch of hearings
- Run full pipeline (multiple stages) on hearing
"""

import logging
from typing import List, Optional, Type
from uuid import UUID

from sqlalchemy.orm import Session

from src.core.models.hearing import Hearing
from src.core.pipeline.base import PipelineStage, StageResult, BatchResult

logger = logging.getLogger(__name__)


class PipelineOrchestrator:
    """
    Orchestrates pipeline stage execution.

    Usage:
        orchestrator = PipelineOrchestrator(db)

        # Run single stage on single hearing
        result = orchestrator.run_stage(TranscribeStage(), hearing_id)

        # Run stage on batch
        batch_result = orchestrator.run_stage_batch(
            TranscribeStage(),
            hearing_ids=[id1, id2, id3]
        )

        # Run full pipeline
        results = orchestrator.run_pipeline(
            hearing_id,
            stages=[TranscribeStage(), AnalyzeStage()]
        )
    """

    def __init__(self, db: Session):
        self.db = db

    def run_stage(
        self,
        stage: PipelineStage,
        hearing_id: UUID,
        state_code: Optional[str] = None,
    ) -> StageResult:
        """
        Run a single stage on a single hearing.

        Args:
            stage: The pipeline stage to run
            hearing_id: UUID of the hearing to process
            state_code: Optional state filter (for validation)

        Returns:
            StageResult from stage execution
        """
        # Load hearing
        hearing = self.db.query(Hearing).filter(Hearing.id == hearing_id).first()

        if not hearing:
            return StageResult(success=False, error=f"Hearing {hearing_id} not found")

        if state_code and hearing.state_code != state_code:
            return StageResult(
                success=False,
                error=f"Hearing state {hearing.state_code} does not match {state_code}"
            )

        logger.info(f"Running {stage.name} on hearing {hearing_id}")

        try:
            result = stage.process(hearing, self.db)

            if result.success and not result.skipped:
                logger.info(f"{stage.name} completed for hearing {hearing_id}")
            elif result.skipped:
                logger.info(f"{stage.name} skipped for hearing {hearing_id}: {result.error}")
            else:
                logger.error(f"{stage.name} failed for hearing {hearing_id}: {result.error}")

            return result

        except Exception as e:
            logger.exception(f"{stage.name} error for hearing {hearing_id}")
            return StageResult(success=False, error=str(e))

    def run_stage_batch(
        self,
        stage: PipelineStage,
        hearing_ids: Optional[List[UUID]] = None,
        state_code: Optional[str] = None,
        status_filter: Optional[str] = None,
        limit: int = 100,
    ) -> BatchResult:
        """
        Run a stage on a batch of hearings.

        Args:
            stage: The pipeline stage to run
            hearing_ids: Specific hearing IDs to process (optional)
            state_code: Filter by state code
            status_filter: Filter by transcript_status
            limit: Maximum hearings to process

        Returns:
            BatchResult with aggregated results
        """
        batch_result = BatchResult()

        if hearing_ids:
            # Process specific hearings
            hearings = self.db.query(Hearing).filter(
                Hearing.id.in_(hearing_ids)
            ).all()
        else:
            # Query hearings based on filters
            query = self.db.query(Hearing)

            if state_code:
                query = query.filter(Hearing.state_code == state_code)
            if status_filter:
                query = query.filter(Hearing.transcript_status == status_filter)

            hearings = query.limit(limit).all()

        logger.info(f"Running {stage.name} on {len(hearings)} hearings")

        for hearing in hearings:
            try:
                result = stage.process(hearing, self.db)
                batch_result.add_result(hearing.id, result)
            except Exception as e:
                logger.exception(f"{stage.name} error for hearing {hearing.id}")
                batch_result.add_result(
                    hearing.id,
                    StageResult(success=False, error=str(e))
                )

        logger.info(
            f"{stage.name} batch complete: "
            f"{batch_result.successful} successful, "
            f"{batch_result.failed} failed, "
            f"{batch_result.skipped} skipped, "
            f"${batch_result.total_cost_usd:.4f} total cost"
        )

        return batch_result

    def run_pipeline(
        self,
        hearing_id: UUID,
        stages: List[PipelineStage],
        stop_on_error: bool = True,
    ) -> List[StageResult]:
        """
        Run multiple stages in sequence on a hearing.

        Args:
            hearing_id: UUID of the hearing to process
            stages: List of stages to run in order
            stop_on_error: Whether to stop pipeline on first error

        Returns:
            List of StageResults, one per stage
        """
        results = []

        for stage in stages:
            result = self.run_stage(stage, hearing_id)
            results.append(result)

            if not result.success and stop_on_error:
                logger.warning(
                    f"Pipeline stopped at {stage.name} due to error: {result.error}"
                )
                break

        return results

    def get_pending_hearings(
        self,
        stage_name: str,
        state_code: Optional[str] = None,
        limit: int = 100,
    ) -> List[Hearing]:
        """
        Get hearings ready for a specific stage.

        Maps stage names to required status:
        - transcribe: status = "pending" or "downloaded"
        - analyze: status = "transcribed"
        """
        status_map = {
            "transcribe": ["pending", "downloaded"],
            "analyze": ["transcribed"],
        }

        required_status = status_map.get(stage_name, ["pending"])

        query = self.db.query(Hearing).filter(
            Hearing.transcript_status.in_(required_status)
        )

        if state_code:
            query = query.filter(Hearing.state_code == state_code)

        return query.order_by(Hearing.hearing_date.desc()).limit(limit).all()
