"""
Pipeline admin routes.

Provides endpoints to run transcription and analysis stages.
"""

import logging
from datetime import datetime
from typing import Optional, List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session

from src.api.dependencies import get_db, require_admin
from src.api.schemas.pipeline import (
    PipelineRunRequest,
    PipelineStatusResponse,
    StageResultResponse,
    PipelinePendingResponse,
)
from src.core.models.hearing import Hearing
from src.core.pipeline.orchestrator import PipelineOrchestrator
from src.core.pipeline.transcribe import TranscribeStage
from src.core.pipeline.analyze import AnalyzeStage

logger = logging.getLogger(__name__)
router = APIRouter()

# Store for tracking pipeline runs (in production, use Redis or database)
_pipeline_runs = {}


def _get_stage(stage_name: str):
    """Get stage instance by name."""
    stages = {
        "transcribe": TranscribeStage,
        "analyze": AnalyzeStage,
    }

    stage_class = stages.get(stage_name)
    if not stage_class:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown stage: {stage_name}. Valid stages: {list(stages.keys())}"
        )

    return stage_class()


async def _run_pipeline_async(
    run_id: str,
    stage_name: str,
    hearing_ids: List[UUID],
    state_code: str,
    db_session_factory,
):
    """Background task to run pipeline."""
    from src.core.database import SessionLocal

    _pipeline_runs[run_id]["status"] = "running"
    _pipeline_runs[run_id]["started_at"] = datetime.utcnow()

    db = SessionLocal()
    try:
        stage = _get_stage(stage_name)
        orchestrator = PipelineOrchestrator(db)

        batch_result = orchestrator.run_stage_batch(
            stage=stage,
            hearing_ids=hearing_ids,
            state_code=state_code,
        )

        # Update run status
        _pipeline_runs[run_id].update({
            "status": "completed",
            "total": batch_result.total,
            "successful": batch_result.successful,
            "failed": batch_result.failed,
            "skipped": batch_result.skipped,
            "total_cost_usd": batch_result.total_cost_usd,
            "errors": batch_result.errors,
            "completed_at": datetime.utcnow(),
        })

    except Exception as e:
        logger.exception(f"Pipeline run {run_id} failed")
        _pipeline_runs[run_id].update({
            "status": "failed",
            "errors": [{"error": str(e)}],
            "completed_at": datetime.utcnow(),
        })
    finally:
        db.close()


@router.post("/run", response_model=PipelineStatusResponse)
async def run_pipeline(
    request: PipelineRunRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    _admin: bool = Depends(require_admin),
):
    """
    Run a pipeline stage on hearings.

    Stages:
    - transcribe: Whisper transcription
    - analyze: GPT-4o-mini analysis

    If hearing_ids is not provided, automatically selects hearings
    based on status_filter and limit.
    """
    stage = _get_stage(request.stage)

    # Get hearing IDs to process
    if request.hearing_ids:
        hearing_ids = request.hearing_ids
    else:
        # Auto-select hearings based on stage and filters
        orchestrator = PipelineOrchestrator(db)
        hearings = orchestrator.get_pending_hearings(
            stage_name=request.stage,
            state_code=request.state_code,
            limit=request.limit,
        )
        hearing_ids = [h.id for h in hearings]

    if not hearing_ids:
        return PipelineStatusResponse(
            status="completed",
            stage=request.stage,
            total=0,
            successful=0,
            failed=0,
            skipped=0,
        )

    # Create run tracking entry
    run_id = f"{request.stage}_{datetime.utcnow().timestamp()}"
    _pipeline_runs[run_id] = {
        "status": "queued",
        "stage": request.stage,
        "total": len(hearing_ids),
    }

    # Queue background task
    background_tasks.add_task(
        _run_pipeline_async,
        run_id=run_id,
        stage_name=request.stage,
        hearing_ids=hearing_ids,
        state_code=request.state_code,
        db_session_factory=None,
    )

    return PipelineStatusResponse(
        status="queued",
        stage=request.stage,
        total=len(hearing_ids),
    )


@router.post("/run-sync", response_model=PipelineStatusResponse)
def run_pipeline_sync(
    request: PipelineRunRequest,
    db: Session = Depends(get_db),
    _admin: bool = Depends(require_admin),
):
    """
    Run pipeline stage synchronously (blocking).

    Use for small batches or testing. For larger batches, use /run.
    """
    stage = _get_stage(request.stage)
    orchestrator = PipelineOrchestrator(db)

    # Get hearing IDs
    if request.hearing_ids:
        hearing_ids = request.hearing_ids
    else:
        hearings = orchestrator.get_pending_hearings(
            stage_name=request.stage,
            state_code=request.state_code,
            limit=request.limit,
        )
        hearing_ids = [h.id for h in hearings]

    if not hearing_ids:
        return PipelineStatusResponse(
            status="completed",
            stage=request.stage,
            total=0,
        )

    # Run synchronously
    started_at = datetime.utcnow()
    batch_result = orchestrator.run_stage_batch(
        stage=stage,
        hearing_ids=hearing_ids,
        state_code=request.state_code,
    )

    return PipelineStatusResponse(
        status="completed",
        stage=request.stage,
        total=batch_result.total,
        successful=batch_result.successful,
        failed=batch_result.failed,
        skipped=batch_result.skipped,
        total_cost_usd=batch_result.total_cost_usd,
        errors=batch_result.errors,
        started_at=started_at,
        completed_at=datetime.utcnow(),
    )


@router.post("/run-single/{hearing_id}", response_model=StageResultResponse)
def run_single_hearing(
    hearing_id: UUID,
    stage: str,
    db: Session = Depends(get_db),
    _admin: bool = Depends(require_admin),
):
    """
    Run a pipeline stage on a single hearing.

    Synchronous operation, returns immediately.
    """
    stage_instance = _get_stage(stage)
    orchestrator = PipelineOrchestrator(db)

    result = orchestrator.run_stage(
        stage=stage_instance,
        hearing_id=hearing_id,
    )

    return StageResultResponse(
        hearing_id=str(hearing_id),
        success=result.success,
        skipped=result.skipped,
        error=result.error,
        cost_usd=result.cost_usd,
        model=result.model,
        data=result.data,
    )


@router.get("/pending", response_model=PipelinePendingResponse)
def get_pending_hearings(
    stage: str,
    state_code: Optional[str] = "FL",
    limit: int = 50,
    db: Session = Depends(get_db),
    _admin: bool = Depends(require_admin),
):
    """
    Get hearings pending for a specific stage.

    - transcribe: Returns hearings with status pending/downloaded
    - analyze: Returns hearings with status transcribed
    """
    orchestrator = PipelineOrchestrator(db)

    hearings = orchestrator.get_pending_hearings(
        stage_name=stage,
        state_code=state_code,
        limit=limit,
    )

    return PipelinePendingResponse(
        stage=stage,
        state_code=state_code,
        count=len(hearings),
        hearings=[
            {
                "id": str(h.id),
                "title": h.title,
                "docket_number": h.docket_number,
                "hearing_date": h.hearing_date.isoformat() if h.hearing_date else None,
                "transcript_status": h.transcript_status,
            }
            for h in hearings
        ],
    )


@router.get("/status/{run_id}", response_model=PipelineStatusResponse)
def get_pipeline_status(
    run_id: str,
    _admin: bool = Depends(require_admin),
):
    """
    Get status of a pipeline run.
    """
    if run_id not in _pipeline_runs:
        raise HTTPException(status_code=404, detail="Pipeline run not found")

    run_data = _pipeline_runs[run_id]

    return PipelineStatusResponse(
        status=run_data.get("status", "unknown"),
        stage=run_data.get("stage", ""),
        total=run_data.get("total", 0),
        successful=run_data.get("successful", 0),
        failed=run_data.get("failed", 0),
        skipped=run_data.get("skipped", 0),
        total_cost_usd=run_data.get("total_cost_usd", 0.0),
        errors=run_data.get("errors"),
        started_at=run_data.get("started_at"),
        completed_at=run_data.get("completed_at"),
    )


@router.get("/stats")
def get_pipeline_stats(
    state_code: Optional[str] = None,
    db: Session = Depends(get_db),
    _admin: bool = Depends(require_admin),
):
    """
    Get pipeline statistics.

    Returns counts by transcript_status and processing costs.
    """
    from sqlalchemy import func

    query = db.query(
        Hearing.transcript_status,
        func.count(Hearing.id).label('count'),
        func.sum(Hearing.processing_cost_usd).label('total_cost'),
    )

    if state_code:
        query = query.filter(Hearing.state_code == state_code.upper())

    results = query.group_by(Hearing.transcript_status).all()

    status_counts = {}
    total_cost = 0.0

    for r in results:
        status = r.transcript_status or "unknown"
        status_counts[status] = r.count
        if r.total_cost:
            total_cost += float(r.total_cost)

    return {
        "status_counts": status_counts,
        "total_hearings": sum(status_counts.values()),
        "total_processing_cost_usd": total_cost,
    }
