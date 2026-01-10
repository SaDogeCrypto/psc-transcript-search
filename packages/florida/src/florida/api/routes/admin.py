"""
Admin API routes for Florida PSC pipeline monitoring and management.

Adapted from the multi-state backend to work with Florida-specific models.
"""
from datetime import datetime, timedelta, timezone
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import func, text

from florida.models import get_db
from florida.models.hearing import FLHearing, FLTranscriptSegment
from florida.models.analysis import FLAnalysis
from florida.models.docket import FLDocket
from florida.models.linking import FLHearingDocket
from florida.scraper import (
    get_scraper_status as _get_scraper_status,
    start_scraper_async,
    stop_scraper as _stop_scraper,
)
from florida.pipeline.stages import FLTranscribeStage, FLAnalyzeStage

router = APIRouter(prefix="/admin", tags=["admin"])


# ============================================================================
# PYDANTIC MODELS
# ============================================================================

class StateResponse(BaseModel):
    id: int
    code: str
    name: str
    commission_name: Optional[str] = None
    hearing_count: int


class AdminStatsResponse(BaseModel):
    total_states: int
    total_sources: int
    total_hearings: int
    total_segments: int
    total_hours: float
    hearings_by_status: dict
    hearings_by_state: dict
    total_transcription_cost: float
    total_analysis_cost: float
    total_cost: float
    cost_by_model: dict  # Breakdown of costs by LLM model
    hearings_last_24h: int
    hearings_last_7d: int


class RunStageRequest(BaseModel):
    stage: str
    hearing_ids: List[int]


class SourceResponse(BaseModel):
    id: int
    state_id: int
    state_code: str
    state_name: str
    name: str
    source_type: str
    url: str
    enabled: bool
    check_frequency_hours: int
    last_checked_at: Optional[str] = None
    last_hearing_at: Optional[str] = None
    status: str
    error_message: Optional[str] = None
    created_at: str


class HearingAdminResponse(BaseModel):
    id: int
    state_code: str
    state_name: str
    title: str
    hearing_date: Optional[str] = None
    hearing_type: Optional[str] = None
    utility_name: Optional[str] = None
    duration_seconds: Optional[int] = None
    status: str
    source_url: Optional[str] = None
    created_at: str
    pipeline_status: str
    segment_count: int = 0
    has_analysis: bool = False


class PipelineStatusResponse(BaseModel):
    status: str
    started_at: Optional[str] = None
    current_hearing_id: Optional[int] = None
    current_hearing_title: Optional[str] = None
    current_stage: Optional[str] = None
    hearings_processed: int
    errors_count: int
    total_cost_usd: float
    stage_counts: dict
    processed_today: int
    cost_today: float
    errors_today: int


class PipelineActivityItem(BaseModel):
    id: int
    hearing_id: int
    hearing_title: str
    state_code: str
    stage: str
    status: str
    started_at: str
    completed_at: Optional[str] = None
    cost_usd: Optional[float] = None


class PipelineError(BaseModel):
    hearing_id: int
    hearing_title: str
    state_code: str
    status: str
    last_stage: Optional[str] = None
    error_message: Optional[str] = None
    retry_count: int
    updated_at: str


# ============================================================================
# STATES
# ============================================================================

@router.get("/states", response_model=List[StateResponse])
def list_states(db: Session = Depends(get_db)):
    """List available states (Florida only for this API)."""
    hearing_count = db.query(func.count(FLHearing.id)).scalar() or 0

    return [
        StateResponse(
            id=1,
            code="FL",
            name="Florida",
            commission_name="Florida Public Service Commission",
            hearing_count=hearing_count
        )
    ]


# ============================================================================
# SOURCES (Florida uses The Florida Channel as primary source)
# ============================================================================

@router.get("/sources", response_model=List[SourceResponse])
def list_sources(
    state: Optional[str] = None,
    status: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """List sources. Florida primarily uses The Florida Channel."""
    # Get most recent hearing date
    last_hearing = db.query(func.max(FLHearing.hearing_date)).scalar()

    return [
        SourceResponse(
            id=1,
            state_id=1,
            state_code="FL",
            state_name="Florida",
            name="The Florida Channel",
            source_type="video_archive",
            url="https://thefloridachannel.org",
            enabled=True,
            check_frequency_hours=24,
            last_checked_at=datetime.now(timezone.utc).isoformat(),
            last_hearing_at=last_hearing.isoformat() if last_hearing else None,
            status="active",
            error_message=None,
            created_at="2025-01-01T00:00:00Z"
        )
    ]


@router.post("/sources/{source_id}/check")
def trigger_source_check(source_id: int, db: Session = Depends(get_db)):
    """Trigger a check for new hearings."""
    return {
        "message": "Check triggered for The Florida Channel",
        "source_id": source_id,
        "status": "checking"
    }


@router.patch("/sources/{source_id}/toggle")
def toggle_source(source_id: int, db: Session = Depends(get_db)):
    """Toggle source enabled state."""
    return {"message": "Source toggled", "enabled": True}


# ============================================================================
# STATS
# ============================================================================

@router.get("/stats", response_model=AdminStatsResponse)
def get_admin_stats(db: Session = Depends(get_db)):
    """Get comprehensive admin statistics."""
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = today_start - timedelta(days=7)
    month_start = today_start - timedelta(days=30)

    # Basic counts
    total_hearings = db.query(func.count(FLHearing.id)).scalar() or 0
    total_segments = db.query(func.count(FLTranscriptSegment.id)).scalar() or 0
    total_analyses = db.query(func.count(FLAnalysis.id)).scalar() or 0

    # Duration in hours
    total_seconds = db.query(func.sum(FLHearing.duration_seconds)).scalar() or 0
    total_hours = round(total_seconds / 3600, 1)

    # Hearings by transcript_status
    status_counts = db.query(
        FLHearing.transcript_status,
        func.count(FLHearing.id)
    ).group_by(FLHearing.transcript_status).all()
    hearings_by_status = {s or 'pending': c for s, c in status_counts}

    # Hearings by state (Florida only)
    hearings_by_state = {"FL": total_hearings}

    # Costs from analyses
    total_analysis_cost = db.query(func.sum(FLAnalysis.cost_usd)).scalar() or 0
    total_transcription_cost = db.query(func.sum(FLHearing.processing_cost_usd)).scalar() or 0

    # Cost breakdown by model
    cost_by_model = {}

    # Analysis costs - first try FLAnalysis table which has model info
    analysis_by_model = db.query(
        func.coalesce(FLAnalysis.model, 'gpt-4o-mini'),
        func.sum(FLAnalysis.cost_usd)
    ).filter(FLAnalysis.cost_usd.isnot(None)).group_by(func.coalesce(FLAnalysis.model, 'gpt-4o-mini')).all()

    for model_name, cost in analysis_by_model:
        if model_name and cost:
            cost_by_model[model_name] = float(cost or 0)

    # Transcription costs by whisper model
    transcription_by_model = db.query(
        func.coalesce(FLHearing.whisper_model, 'whisper-large-v3-turbo'),
        func.sum(FLHearing.processing_cost_usd)
    ).filter(FLHearing.processing_cost_usd.isnot(None)).group_by(func.coalesce(FLHearing.whisper_model, 'whisper-large-v3-turbo')).all()

    for model_name, cost in transcription_by_model:
        if model_name and cost:
            cost_by_model[model_name] = cost_by_model.get(model_name, 0) + float(cost or 0)

    # Recent activity
    hearings_24h = db.query(func.count(FLHearing.id)).filter(
        FLHearing.created_at >= now - timedelta(hours=24)
    ).scalar() or 0
    hearings_7d = db.query(func.count(FLHearing.id)).filter(
        FLHearing.created_at >= now - timedelta(days=7)
    ).scalar() or 0

    # Pipeline status counts based on transcript_status
    pending_count = db.query(func.count(FLHearing.id)).filter(
        FLHearing.transcript_status.is_(None)
    ).scalar() or 0

    # Count hearings with transcripts but no analysis
    transcribed_no_analysis = db.execute(text("""
        SELECT COUNT(*) FROM fl_hearings h
        LEFT JOIN fl_analyses a ON a.hearing_id = h.id
        WHERE h.transcript_status = 'transcribed' AND a.id IS NULL
    """)).scalar() or 0

    # Error count (hearings with 'error' in transcript_status)
    error_count = db.query(func.count(FLHearing.id)).filter(
        FLHearing.transcript_status == 'error'
    ).scalar() or 0

    # Cost calculations
    cost_today = db.query(func.sum(FLAnalysis.cost_usd)).filter(
        FLAnalysis.created_at >= today_start
    ).scalar() or 0
    cost_week = db.query(func.sum(FLAnalysis.cost_usd)).filter(
        FLAnalysis.created_at >= week_start
    ).scalar() or 0
    cost_month = db.query(func.sum(FLAnalysis.cost_usd)).filter(
        FLAnalysis.created_at >= month_start
    ).scalar() or 0

    return AdminStatsResponse(
        total_states=1,
        total_sources=1,
        total_hearings=total_hearings,
        total_segments=total_segments,
        total_hours=total_hours,
        hearings_by_status=hearings_by_status,
        hearings_by_state=hearings_by_state,
        total_transcription_cost=float(total_transcription_cost),
        total_analysis_cost=float(total_analysis_cost),
        total_cost=float(total_transcription_cost) + float(total_analysis_cost),
        cost_by_model=cost_by_model,
        hearings_last_24h=hearings_24h,
        hearings_last_7d=hearings_7d,
        sources_healthy=1,
        sources_error=0,
        pipeline_jobs_pending=pending_count + transcribed_no_analysis,
        pipeline_jobs_running=0,
        pipeline_jobs_error=error_count,
        cost_today=float(cost_today),
        cost_this_week=float(cost_week),
        cost_this_month=float(cost_month)
    )


# ============================================================================
# HEARINGS (ADMIN VIEW)
# ============================================================================

@router.get("/hearings")
def list_hearings_admin(
    states: Optional[str] = Query(None, description="Comma-separated state codes"),
    status: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    page: int = 1,
    page_size: int = 50,
    db: Session = Depends(get_db)
):
    """List hearings with pipeline status for admin dashboard."""
    query = db.query(FLHearing)

    # Filter by transcript_status (mapped from the dashboard's expected statuses)
    if status:
        if status == 'pending':
            query = query.filter(FLHearing.transcript_status.is_(None))
        elif status == 'transcribed':
            # Transcribed but not analyzed
            query = query.outerjoin(FLAnalysis).filter(
                FLHearing.transcript_status == 'transcribed',
                FLAnalysis.id.is_(None)
            )
        elif status == 'analyzed':
            query = query.join(FLAnalysis)
        elif status == 'error':
            query = query.filter(FLHearing.transcript_status == 'error')
        else:
            query = query.filter(FLHearing.transcript_status == status)

    if date_from:
        query = query.filter(FLHearing.hearing_date >= date_from)
    if date_to:
        query = query.filter(FLHearing.hearing_date <= date_to)

    # Get total count
    total = query.count()

    # Order by most recent first
    query = query.order_by(FLHearing.created_at.desc())

    # Pagination
    offset = (page - 1) * page_size
    hearings = query.offset(offset).limit(page_size).all()

    # Build response
    items = []
    for h in hearings:
        # Get segment count
        segment_count = db.query(func.count(FLTranscriptSegment.id)).filter(
            FLTranscriptSegment.hearing_id == h.id
        ).scalar() or 0

        # Check if analyzed
        has_analysis = db.query(FLAnalysis.id).filter(
            FLAnalysis.hearing_id == h.id
        ).first() is not None

        # Determine pipeline status
        if has_analysis:
            pipeline_status = "analyzed"
        elif segment_count > 0:
            pipeline_status = "transcribed"
        elif h.transcript_status == 'error':
            pipeline_status = "error"
        else:
            pipeline_status = "pending"

        items.append({
            "id": h.id,
            "state_code": "FL",
            "state_name": "Florida",
            "title": h.title or f"Hearing {h.id}",
            "hearing_date": h.hearing_date.isoformat() if h.hearing_date else None,
            "hearing_type": h.hearing_type,
            "utility_name": None,  # Could be extracted from analysis
            "duration_seconds": h.duration_seconds,
            "status": h.transcript_status or "pending",
            "source_url": h.source_url,
            "created_at": h.created_at.isoformat() if h.created_at else None,
            "pipeline_status": pipeline_status,
            "pipeline_jobs": [],  # Not using job system
            "segment_count": segment_count,
            "has_analysis": has_analysis
        })

    total_pages = (total + page_size - 1) // page_size

    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages
    }


@router.post("/hearings/{hearing_id}/retry")
def retry_hearing(
    hearing_id: int,
    stage: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Retry processing for a hearing (reset status)."""
    hearing = db.query(FLHearing).filter(FLHearing.id == hearing_id).first()
    if not hearing:
        raise HTTPException(status_code=404, detail="Hearing not found")

    # Reset the transcript status to allow reprocessing
    if stage == 'analyze' or stage is None:
        # Delete existing analysis to allow re-analysis
        db.query(FLAnalysis).filter(FLAnalysis.hearing_id == hearing_id).delete()

    if stage == 'transcribe' or (stage is None and hearing.transcript_status == 'error'):
        hearing.transcript_status = None
        # Optionally delete segments to re-transcribe
        db.query(FLTranscriptSegment).filter(FLTranscriptSegment.hearing_id == hearing_id).delete()

    db.commit()

    return {
        "message": f"Hearing {hearing_id} reset for reprocessing",
        "stage": stage or "all",
        "hearing_id": hearing_id
    }


@router.post("/hearings/{hearing_id}/cancel")
def cancel_hearing(hearing_id: int, db: Session = Depends(get_db)):
    """Cancel/skip processing for a hearing."""
    hearing = db.query(FLHearing).filter(FLHearing.id == hearing_id).first()
    if not hearing:
        raise HTTPException(status_code=404, detail="Hearing not found")

    hearing.transcript_status = 'skipped'
    db.commit()

    return {
        "message": f"Hearing {hearing_id} marked as skipped",
        "hearing_id": hearing_id
    }


# ============================================================================
# PIPELINE STATUS & CONTROL
# ============================================================================

# Simple in-memory pipeline state (would use Redis in production)
_pipeline_state = {
    "status": "idle",
    "started_at": None,
    "current_hearing_id": None,
    "current_stage": None,
    "hearings_processed": 0,
    "errors_count": 0
}


@router.get("/pipeline/status", response_model=PipelineStatusResponse)
def get_pipeline_status(db: Session = Depends(get_db)):
    """Get current pipeline status."""
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    # Count hearings at each stage
    # Pending = hearings without transcript segments (need transcription)
    pending = db.execute(text("""
        SELECT COUNT(*) FROM fl_hearings h
        WHERE NOT EXISTS (SELECT 1 FROM fl_transcript_segments s WHERE s.hearing_id = h.id)
    """)).scalar() or 0

    # Count hearings that have transcript segments but no analysis
    transcribed = db.execute(text("""
        SELECT COUNT(DISTINCT h.id) FROM fl_hearings h
        JOIN fl_transcript_segments s ON s.hearing_id = h.id
        LEFT JOIN fl_analyses a ON a.hearing_id = h.id
        WHERE a.id IS NULL
    """)).scalar() or 0

    analyzed = db.query(func.count(FLAnalysis.id)).scalar() or 0

    errors = db.query(func.count(FLHearing.id)).filter(
        FLHearing.transcript_status == 'error'
    ).scalar() or 0

    # Today's stats
    processed_today = db.query(func.count(FLAnalysis.id)).filter(
        FLAnalysis.created_at >= today_start
    ).scalar() or 0

    cost_today = db.query(func.sum(FLAnalysis.cost_usd)).filter(
        FLAnalysis.created_at >= today_start
    ).scalar() or 0

    total_cost = db.query(func.sum(FLAnalysis.cost_usd)).scalar() or 0

    # Get current hearing if processing
    current_title = None
    if _pipeline_state.get("current_hearing_id"):
        h = db.query(FLHearing).filter(FLHearing.id == _pipeline_state["current_hearing_id"]).first()
        if h:
            current_title = h.title

    return PipelineStatusResponse(
        status=_pipeline_state.get("status", "idle"),
        started_at=_pipeline_state.get("started_at"),
        current_hearing_id=_pipeline_state.get("current_hearing_id"),
        current_hearing_title=current_title,
        current_stage=_pipeline_state.get("current_stage"),
        hearings_processed=analyzed,
        errors_count=errors,
        total_cost_usd=float(total_cost or 0),
        stage_counts={
            # Dashboard expects these keys for stage mapping:
            "discovered": 0,  # All FL hearings are already discovered
            "downloaded": pending,  # Downloaded but need transcription
            "transcribed": transcribed,  # Transcribed but need analysis
            "review": 0,  # No review step in Florida
            "ready_for_extract": 0,  # No extract step
            "complete": analyzed,  # Fully processed
            "error": errors,
            # Also include original keys for backwards compat
            "pending": pending,
            "analyzed": analyzed
        },
        processed_today=processed_today,
        cost_today=float(cost_today or 0),
        errors_today=0  # Would track separately
    )


class PipelineStartRequest(BaseModel):
    only_stage: Optional[str] = None  # transcribe, analyze, or None for full pipeline
    states: Optional[List[str]] = None  # State codes to filter (ignored for FL-only API)
    max_cost: Optional[float] = None  # Maximum cost limit
    limit: int = 10  # Max hearings to process


def _run_pipeline_stages(
    stage: Optional[str],
    limit: int,
    max_cost: Optional[float],
    db_session_factory
):
    """Background task to run pipeline stages."""
    from florida.models import SessionLocal
    db = db_session_factory()

    try:
        _pipeline_state["status"] = "running"
        _pipeline_state["hearings_processed"] = 0
        _pipeline_state["errors_count"] = 0

        stages_to_run = [stage] if stage else ["transcribe", "analyze"]
        total_cost = 0.0

        for current_stage in stages_to_run:
            if _pipeline_state["status"] == "stopping":
                break

            _pipeline_state["current_stage"] = current_stage

            # Initialize stage
            if current_stage == "transcribe":
                pipeline_stage = FLTranscribeStage()
                # Find hearings needing transcription (no segments yet)
                hearings = db.execute(text("""
                    SELECT h.id FROM fl_hearings h
                    WHERE NOT EXISTS (
                        SELECT 1 FROM fl_transcript_segments s WHERE s.hearing_id = h.id
                    )
                    AND (h.transcript_status IS NULL OR h.transcript_status NOT IN ('transcribed', 'analyzed', 'error', 'skipped'))
                    LIMIT :limit
                """), {"limit": limit}).fetchall()
                hearing_ids = [r[0] for r in hearings]

            elif current_stage == "analyze":
                pipeline_stage = FLAnalyzeStage()
                # Find hearings needing analysis (have segments but no analysis)
                hearings = db.execute(text("""
                    SELECT DISTINCT h.id FROM fl_hearings h
                    JOIN fl_transcript_segments s ON s.hearing_id = h.id
                    LEFT JOIN fl_analyses a ON a.hearing_id = h.id
                    WHERE a.id IS NULL
                    LIMIT :limit
                """), {"limit": limit}).fetchall()
                hearing_ids = [r[0] for r in hearings]
            else:
                continue

            # Process each hearing
            for hearing_id in hearing_ids:
                if _pipeline_state["status"] == "stopping":
                    break

                if max_cost and total_cost >= max_cost:
                    break

                hearing = db.query(FLHearing).filter(FLHearing.id == hearing_id).first()
                if not hearing:
                    continue

                _pipeline_state["current_hearing_id"] = hearing.id

                try:
                    is_valid, validation_error = pipeline_stage.validate(hearing, db)
                    if not is_valid:
                        continue

                    result = pipeline_stage.execute(hearing, db)

                    if result.success:
                        _pipeline_state["hearings_processed"] += 1
                        total_cost += result.cost_usd
                    else:
                        _pipeline_state["errors_count"] += 1

                except Exception as e:
                    _pipeline_state["errors_count"] += 1

        _pipeline_state["status"] = "idle"
        _pipeline_state["current_stage"] = None
        _pipeline_state["current_hearing_id"] = None

    except Exception as e:
        _pipeline_state["status"] = "error"
        _pipeline_state["errors_count"] += 1
    finally:
        db.close()


@router.post("/pipeline/start")
def start_pipeline(
    request: PipelineStartRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    Start the pipeline to process hearings.

    Accepts JSON body:
    - only_stage: "transcribe" or "analyze" (optional, runs both if not specified)
    - limit: Max hearings to process (default 10)
    - max_cost: Maximum USD to spend (optional)
    """
    if _pipeline_state["status"] == "running":
        raise HTTPException(status_code=409, detail="Pipeline is already running")

    _pipeline_state["status"] = "starting"
    _pipeline_state["started_at"] = datetime.now(timezone.utc).isoformat()
    _pipeline_state["current_stage"] = request.only_stage

    # Get the session factory for background task
    from florida.models import SessionLocal

    # Run in background
    background_tasks.add_task(
        _run_pipeline_stages,
        request.only_stage,
        request.limit,
        request.max_cost,
        SessionLocal
    )

    return {
        "message": "Pipeline started",
        "stages": [request.only_stage] if request.only_stage else ["transcribe", "analyze"],
        "limit": request.limit,
        "max_cost": request.max_cost,
        "status": "starting"
    }


# Dashboard compatibility endpoint
class PipelineRunRequest(BaseModel):
    stage: str
    state_code: Optional[str] = None
    hearing_ids: Optional[List[int]] = None
    limit: int = 5


@router.post("/pipeline/run")
def run_pipeline_compat(
    request: PipelineRunRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    Run pipeline (dashboard compatibility endpoint).

    Maps to the start endpoint with appropriate parameters.
    """
    from florida.models import SessionLocal

    # Find hearings needing this stage
    if request.stage == "transcribe":
        hearings = db.execute(text("""
            SELECT h.id FROM fl_hearings h
            WHERE NOT EXISTS (
                SELECT 1 FROM fl_transcript_segments s WHERE s.hearing_id = h.id
            )
            AND (h.transcript_status IS NULL OR h.transcript_status NOT IN ('transcribed', 'analyzed', 'error', 'skipped'))
            LIMIT :limit
        """), {"limit": request.limit}).fetchall()
    elif request.stage == "analyze":
        hearings = db.execute(text("""
            SELECT DISTINCT h.id FROM fl_hearings h
            JOIN fl_transcript_segments s ON s.hearing_id = h.id
            LEFT JOIN fl_analyses a ON a.hearing_id = h.id
            WHERE a.id IS NULL
            LIMIT :limit
        """), {"limit": request.limit}).fetchall()
    else:
        raise HTTPException(status_code=400, detail=f"Unknown stage: {request.stage}")

    hearing_ids = [r[0] for r in hearings]

    if not hearing_ids:
        return {
            "status": "completed",
            "stage": request.stage,
            "total": 0,
            "successful": 0,
            "failed": 0,
            "total_cost_usd": 0,
            "errors": []
        }

    # Run in background
    _pipeline_state["status"] = "running"
    _pipeline_state["started_at"] = datetime.now(timezone.utc).isoformat()
    _pipeline_state["current_stage"] = request.stage

    background_tasks.add_task(
        _run_pipeline_stages,
        request.stage,
        request.limit,
        None,
        SessionLocal
    )

    return {
        "status": "running",
        "stage": request.stage,
        "total": len(hearing_ids),
        "successful": 0,
        "failed": 0,
        "total_cost_usd": 0,
        "started_at": _pipeline_state["started_at"]
    }


@router.get("/pipeline/stats")
def get_pipeline_stats(
    state_code: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Get pipeline statistics (dashboard compatibility)."""
    # Count hearings by transcript_status
    status_counts = {}

    # Pending = no transcript segments
    pending = db.execute(text("""
        SELECT COUNT(*) FROM fl_hearings h
        WHERE NOT EXISTS (SELECT 1 FROM fl_transcript_segments s WHERE s.hearing_id = h.id)
    """)).scalar() or 0
    status_counts["pending"] = pending

    # Transcribed = has segments but no analysis
    transcribed = db.execute(text("""
        SELECT COUNT(DISTINCT h.id) FROM fl_hearings h
        JOIN fl_transcript_segments s ON s.hearing_id = h.id
        LEFT JOIN fl_analyses a ON a.hearing_id = h.id
        WHERE a.id IS NULL
    """)).scalar() or 0
    status_counts["transcribed"] = transcribed

    # Analyzed = has analysis
    analyzed = db.query(func.count(FLAnalysis.id)).scalar() or 0
    status_counts["analyzed"] = analyzed

    # Errors
    errors = db.query(func.count(FLHearing.id)).filter(
        FLHearing.transcript_status == 'error'
    ).scalar() or 0
    status_counts["error"] = errors

    total_hearings = db.query(func.count(FLHearing.id)).scalar() or 0
    total_cost = db.query(func.sum(FLAnalysis.cost_usd)).scalar() or 0

    return {
        "status_counts": status_counts,
        "total_hearings": total_hearings,
        "total_processing_cost_usd": float(total_cost or 0)
    }


@router.get("/pipeline/pending")
def get_pending_hearings(
    stage: str = Query(...),
    state_code: Optional[str] = None,
    limit: int = 20,
    db: Session = Depends(get_db)
):
    """Get hearings pending for a specific stage."""
    if stage == "transcribe":
        hearings = db.execute(text("""
            SELECT h.id, h.title, NULL as docket_number, h.hearing_date, h.transcript_status
            FROM fl_hearings h
            WHERE NOT EXISTS (
                SELECT 1 FROM fl_transcript_segments s WHERE s.hearing_id = h.id
            )
            AND (h.transcript_status IS NULL OR h.transcript_status NOT IN ('transcribed', 'analyzed', 'error', 'skipped'))
            ORDER BY h.hearing_date DESC
            LIMIT :limit
        """), {"limit": limit}).fetchall()
    elif stage == "analyze":
        hearings = db.execute(text("""
            SELECT DISTINCT h.id, h.title, NULL as docket_number, h.hearing_date, h.transcript_status
            FROM fl_hearings h
            JOIN fl_transcript_segments s ON s.hearing_id = h.id
            LEFT JOIN fl_analyses a ON a.hearing_id = h.id
            WHERE a.id IS NULL
            ORDER BY h.hearing_date DESC
            LIMIT :limit
        """), {"limit": limit}).fetchall()
    else:
        hearings = []

    items = []
    for h in hearings:
        # Handle both datetime objects and strings (SQLite returns strings)
        hearing_date = h[3]
        if hearing_date and hasattr(hearing_date, 'isoformat'):
            hearing_date = hearing_date.isoformat()
        items.append({
            "id": str(h[0]),
            "title": h[1],
            "docket_number": h[2],
            "hearing_date": hearing_date,
            "transcript_status": h[4]
        })

    return {
        "stage": stage,
        "state_code": state_code,
        "count": len(items),
        "hearings": items
    }


@router.post("/pipeline/stop")
def stop_pipeline():
    """Stop the pipeline."""
    _pipeline_state["status"] = "stopping"
    return {"message": "Pipeline stop requested", "status": "stopping"}


@router.post("/pipeline/pause")
def pause_pipeline():
    """Pause the pipeline."""
    _pipeline_state["status"] = "paused"
    return {"message": "Pipeline paused", "status": "paused"}


@router.post("/pipeline/resume")
def resume_pipeline():
    """Resume the pipeline."""
    _pipeline_state["status"] = "running"
    return {"message": "Pipeline resumed", "status": "running"}


@router.get("/pipeline/activity")
def get_pipeline_activity(
    limit: int = Query(50, description="Max items to return"),
    db: Session = Depends(get_db)
):
    """Get recent pipeline activity."""
    # Get recent analyses as activity
    analyses = db.query(FLAnalysis, FLHearing).join(
        FLHearing, FLAnalysis.hearing_id == FLHearing.id
    ).order_by(FLAnalysis.created_at.desc()).limit(limit).all()

    items = []
    for idx, (analysis, hearing) in enumerate(analyses):
        items.append({
            "id": idx + 1,
            "hearing_id": hearing.id,
            "hearing_title": hearing.title or f"Hearing {hearing.id}",
            "state_code": "FL",
            "stage": "analyze",
            "status": "completed",
            "started_at": analysis.created_at.isoformat() if analysis.created_at else None,
            "completed_at": analysis.created_at.isoformat() if analysis.created_at else None,
            "cost_usd": float(analysis.cost_usd) if analysis.cost_usd else None
        })

    return {"items": items, "total": len(items)}


@router.get("/pipeline/errors")
def get_pipeline_errors(
    limit: int = Query(50, description="Max items to return"),
    db: Session = Depends(get_db)
):
    """Get hearings with errors."""
    error_hearings = db.query(FLHearing).filter(
        FLHearing.transcript_status == 'error'
    ).order_by(FLHearing.created_at.desc()).limit(limit).all()

    items = []
    for h in error_hearings:
        items.append({
            "hearing_id": h.id,
            "hearing_title": h.title or f"Hearing {h.id}",
            "state_code": "FL",
            "status": "error",
            "last_stage": "transcribe",
            "error_message": None,  # Would store error details
            "retry_count": 0,
            "updated_at": h.created_at.isoformat() if h.created_at else None
        })

    return {"items": items, "total": len(items)}


@router.post("/pipeline/hearings/{hearing_id}/retry")
def retry_pipeline_hearing(
    hearing_id: int,
    stage: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Retry a specific hearing in the pipeline."""
    return retry_hearing(hearing_id, stage, db)


@router.post("/pipeline/hearings/{hearing_id}/skip")
def skip_pipeline_hearing(hearing_id: int, db: Session = Depends(get_db)):
    """Skip a hearing in the pipeline."""
    return cancel_hearing(hearing_id, db)


@router.post("/pipeline/retry-all")
def retry_all_errors(db: Session = Depends(get_db)):
    """Retry all hearings with errors."""
    error_count = db.query(FLHearing).filter(
        FLHearing.transcript_status == 'error'
    ).update({FLHearing.transcript_status: None})
    db.commit()

    return {"message": f"Reset {error_count} hearings for retry", "count": error_count}


# ============================================================================
# PIPELINE RUNS (Simplified for Florida)
# ============================================================================

@router.get("/runs")
def list_pipeline_runs(
    limit: int = 30,
    db: Session = Depends(get_db)
):
    """Get history of pipeline activity (grouped by day)."""
    # Group analyses by day
    result = db.execute(text("""
        SELECT
            DATE(created_at) as run_date,
            COUNT(*) as hearings_processed,
            COALESCE(SUM(cost_usd), 0) as total_cost
        FROM fl_analyses
        WHERE created_at IS NOT NULL
        GROUP BY DATE(created_at)
        ORDER BY run_date DESC
        LIMIT :limit
    """), {"limit": limit})

    runs = []
    for idx, row in enumerate(result):
        runs.append({
            "id": idx + 1,
            "started_at": f"{row[0]}T00:00:00Z",
            "completed_at": f"{row[0]}T23:59:59Z",
            "status": "completed",
            "sources_checked": 1,
            "new_hearings": 0,
            "hearings_processed": row[1],
            "errors": 0,
            "transcription_cost_usd": 0,
            "analysis_cost_usd": float(row[2]),
            "total_cost_usd": float(row[2])
        })

    return runs


# ============================================================================
# RUN ANALYSIS (Florida-specific)
# ============================================================================

@router.post("/pipeline/run-stage")
def run_pipeline_stage(
    request: RunStageRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    Execute a specific pipeline stage on selected hearings.

    Supported stages:
    - transcribe: Transcribe audio using Whisper (Groq/OpenAI/Azure)
    - analyze: Analyze transcript using GPT-4o-mini

    This endpoint executes the stages directly, not via batch scripts.
    """
    stage = request.stage
    hearing_ids = request.hearing_ids

    if stage not in ["transcribe", "analyze"]:
        raise HTTPException(
            status_code=400,
            detail=f"Stage '{stage}' not supported. Supported stages: transcribe, analyze"
        )

    if not hearing_ids:
        raise HTTPException(status_code=400, detail="No hearing IDs provided")

    # Get the hearings
    hearings = db.query(FLHearing).filter(FLHearing.id.in_(hearing_ids)).all()

    if not hearings:
        raise HTTPException(status_code=404, detail="No hearings found with provided IDs")

    # Initialize the appropriate stage
    if stage == "transcribe":
        pipeline_stage = FLTranscribeStage()
    else:
        pipeline_stage = FLAnalyzeStage()

    processed = []
    errors = []
    total_cost = 0.0

    for hearing in hearings:
        try:
            # Validate the hearing for this stage
            is_valid, validation_error = pipeline_stage.validate(hearing, db)

            if not is_valid:
                errors.append({
                    "id": hearing.id,
                    "title": hearing.title[:50] if hearing.title else f"Hearing {hearing.id}",
                    "error": validation_error
                })
                continue

            # Execute the stage
            result = pipeline_stage.execute(hearing, db)

            if result.success:
                processed.append({
                    "id": hearing.id,
                    "title": hearing.title[:50] if hearing.title else f"Hearing {hearing.id}",
                    "cost_usd": result.cost_usd,
                    "skipped": getattr(result, 'error', '') == 'Already transcribed (skipped)' or
                               getattr(result, 'error', '') == 'Already analyzed (skipped)'
                })
                total_cost += result.cost_usd
            else:
                errors.append({
                    "id": hearing.id,
                    "title": hearing.title[:50] if hearing.title else f"Hearing {hearing.id}",
                    "error": result.error
                })

        except Exception as e:
            errors.append({
                "id": hearing.id,
                "title": hearing.title[:50] if hearing.title else f"Hearing {hearing.id}",
                "error": str(e)
            })

    return {
        "message": f"Processed {len(processed)} hearings for {stage}",
        "stage": stage,
        "processed": processed,
        "errors": errors,
        "total_cost_usd": round(total_cost, 4),
        "summary": {
            "total_requested": len(hearing_ids),
            "successful": len(processed),
            "failed": len(errors),
            "skipped": sum(1 for p in processed if p.get("skipped", False))
        }
    }


# ============================================================================
# SCHEDULES (Stub for dashboard compatibility)
# ============================================================================

@router.get("/pipeline/schedules")
def get_schedules():
    """Get pipeline schedules (stub for compatibility)."""
    return []


@router.post("/pipeline/schedules")
def create_schedule():
    """Create a schedule (stub)."""
    raise HTTPException(status_code=501, detail="Schedules not implemented for Florida API")


# ============================================================================
# SCRAPER (Florida Channel RSS Scraper)
# ============================================================================

# Compatibility endpoint for admin dashboard
@router.get("/scrapers")
def list_scrapers():
    """List available scrapers by state (dashboard compatibility)."""
    return {"FL": ["rss"]}


@router.post("/scrapers/run")
def run_scraper_compat(
    state_code: str = Query(...),
    scraper: str = Query(...),
    days_back: int = Query(None),
    db: Session = Depends(get_db)
):
    """Run a scraper (dashboard compatibility endpoint)."""
    if state_code != "FL" or scraper != "rss":
        raise HTTPException(status_code=404, detail=f"Scraper {state_code}/{scraper} not found")

    # Run the scraper
    result = start_scraper_async(dry_run=False)

    # Wait a moment for it to complete since it's fast
    import time
    time.sleep(2)

    # Get final status
    status = _get_scraper_status()

    return {
        "state_code": "FL",
        "scraper": "rss",
        "status": status.get("status", "completed"),
        "items_found": status.get("items_found", 0),
        "hearings_created": status.get("new_hearings", 0),
        "errors": status.get("errors", [])
    }


@router.get("/scraper/status")
def get_scraper_status():
    """Get current scraper status."""
    return _get_scraper_status()


@router.post("/scraper/start")
def start_scraper(
    dry_run: bool = Query(False, description="Preview mode - don't save to database"),
):
    """Start the Florida Channel RSS scraper."""
    return start_scraper_async(dry_run=dry_run)


@router.post("/scraper/stop")
def stop_scraper():
    """Request the scraper to stop."""
    return _stop_scraper()


# ============================================================================
# DOCKET DISCOVERY
# ============================================================================

# Track docket discovery status
_docket_discovery_status = {
    "status": "idle",
    "last_run": None,
    "last_count": 0,
    "errors": []
}

@router.get("/pipeline/docket-sources")
def get_docket_sources(db: Session = Depends(get_db)):
    """Get docket sources for Florida PSC."""
    from florida.scrapers.clerkoffice import FloridaClerkOfficeScraper

    # Check if scraper is available
    scraper = FloridaClerkOfficeScraper()
    is_connected = False
    try:
        is_connected = scraper.test_connection()
    except:
        pass

    # Count existing dockets
    docket_count = db.query(func.count(FLDocket.id)).scalar() or 0

    return [{
        "id": 1,
        "state_code": "FL",
        "state_name": "Florida",
        "commission_name": "Florida Public Service Commission",
        "search_url": "https://www.psc.state.fl.us/ClerkOffice/DocketSearch",
        "scraper_type": "api_json",
        "api_url": "https://pscweb.floridapsc.com/api/ClerkOffice",
        "enabled": True,
        "connected": is_connected,
        "last_scraped_at": _docket_discovery_status.get("last_run"),
        "last_scrape_count": _docket_discovery_status.get("last_count"),
        "docket_count": docket_count,
        "status": "active" if is_connected else "disconnected"
    }]


@router.post("/pipeline/docket-sources/{source_id}/toggle")
def toggle_docket_source(source_id: int):
    """Toggle docket source (Florida only has one source)."""
    return {"message": "Florida source is always enabled", "source_id": source_id, "enabled": True}


@router.get("/pipeline/data-quality")
def get_data_quality(db: Session = Depends(get_db)):
    """Get data quality stats."""
    total_hearings = db.query(func.count(FLHearing.id)).scalar() or 0
    with_transcripts = db.execute(text("""
        SELECT COUNT(DISTINCT hearing_id) FROM fl_transcript_segments
    """)).scalar() or 0
    with_analysis = db.query(func.count(FLAnalysis.id)).scalar() or 0
    total_dockets = db.query(func.count(FLDocket.id)).scalar() or 0

    return {
        "total_hearings": total_hearings,
        "hearings_with_transcripts": with_transcripts,
        "hearings_with_analysis": with_analysis,
        "transcript_coverage": round(with_transcripts / total_hearings * 100, 1) if total_hearings > 0 else 0,
        "analysis_coverage": round(with_analysis / total_hearings * 100, 1) if total_hearings > 0 else 0,
        "dockets_total": total_dockets,
        "dockets_matched": 0,
        "utilities_total": 0,
        "utilities_matched": 0,
        # Required by dashboard DataQuality interface
        "docket_confidence": {
            "verified": with_analysis,  # Analyzed hearings are "verified"
            "likely": 0,
            "possible": with_transcripts - with_analysis,  # Transcribed but not analyzed
            "unverified": total_hearings - with_transcripts  # No transcript yet
        },
        "known_dockets": total_dockets,
        "docket_sources": {
            "total": 1,
            "enabled": 1
        }
    }


@router.get("/pipeline/docket-discovery/stats")
def get_docket_discovery_stats(db: Session = Depends(get_db)):
    """Get docket discovery statistics."""
    total_dockets = db.query(func.count(FLDocket.id)).scalar() or 0
    open_dockets = db.query(func.count(FLDocket.id)).filter(FLDocket.status == 'open').scalar() or 0

    # Get dockets by sector (sector_code might be null, so also try industry_type)
    sector_counts = db.execute(text("""
        SELECT COALESCE(sector_code, UPPER(LEFT(industry_type, 1)), 'X') as sector, COUNT(*) as count
        FROM fl_dockets
        GROUP BY sector
        HAVING COUNT(*) > 0
    """)).fetchall()

    by_sector = {row[0]: row[1] for row in sector_counts if row[0]}

    # Get dockets by year
    year_counts = db.execute(text("""
        SELECT year, COUNT(*) as count
        FROM fl_dockets
        WHERE year IS NOT NULL
        GROUP BY year
        ORDER BY year DESC
    """)).fetchall()

    by_year = {str(row[0]): row[1] for row in year_counts}

    return {
        "total_dockets": total_dockets,
        "open_dockets": open_dockets,
        "closed_dockets": total_dockets - open_dockets,
        "by_sector": by_sector,
        "by_year": by_year,
        "last_run": _docket_discovery_status.get("last_run"),
        "last_count": _docket_discovery_status.get("last_count"),
        "status": _docket_discovery_status.get("status")
    }


@router.get("/pipeline/docket-discovery/scrapers")
def get_docket_scrapers():
    """Get available docket scrapers."""
    return [{
        "state_code": "FL",
        "state_name": "Florida",
        "scraper_type": "api_json",
        "batch_available": True,
        "individual_available": True,
        "api_url": "https://pscweb.floridapsc.com/api/ClerkOffice"
    }]


@router.post("/pipeline/docket-discovery/start")
def start_docket_discovery(
    year: Optional[int] = None,
    status: Optional[str] = None,
    limit: int = 500,
    db: Session = Depends(get_db)
):
    """
    Start docket discovery for Florida PSC.

    Args:
        year: Optional year filter (e.g., 2024)
        status: Optional status filter ('open', 'closed')
        limit: Maximum dockets to fetch (default 500)
    """
    from datetime import datetime
    from florida.scrapers.clerkoffice import FloridaClerkOfficeScraper

    global _docket_discovery_status
    _docket_discovery_status["status"] = "running"
    _docket_discovery_status["errors"] = []

    try:
        scraper = FloridaClerkOfficeScraper()

        # Test connection first
        if not scraper.test_connection():
            _docket_discovery_status["status"] = "error"
            _docket_discovery_status["errors"].append("Failed to connect to Florida PSC API")
            return {"status": "error", "message": "Failed to connect to Florida PSC API"}

        # Scrape dockets
        new_count = 0
        updated_count = 0
        total_count = 0

        for docket_data in scraper.scrape_florida_dockets(year=year, status=status, limit=limit):
            total_count += 1

            # Check if docket exists
            existing = db.query(FLDocket).filter(
                FLDocket.docket_number == docket_data.docket_number
            ).first()

            if existing:
                # Update existing docket
                existing.title = docket_data.title or existing.title
                existing.utility_name = docket_data.utility_name or existing.utility_name
                existing.status = docket_data.status or existing.status
                existing.case_type = docket_data.case_type or existing.case_type
                existing.industry_type = docket_data.industry_type or existing.industry_type
                existing.filed_date = docket_data.filed_date or existing.filed_date
                existing.closed_date = docket_data.closed_date or existing.closed_date
                existing.psc_docket_url = docket_data.psc_docket_url or existing.psc_docket_url
                existing.updated_at = datetime.utcnow()
                updated_count += 1
            else:
                # Create new docket
                new_docket = FLDocket(
                    docket_number=docket_data.docket_number,
                    year=docket_data.year,
                    sequence=docket_data.sequence,
                    sector_code=docket_data.sector_code,
                    title=docket_data.title,
                    utility_name=docket_data.utility_name,
                    status=docket_data.status,
                    case_type=docket_data.case_type,
                    industry_type=docket_data.industry_type,
                    filed_date=docket_data.filed_date,
                    closed_date=docket_data.closed_date,
                    psc_docket_url=docket_data.psc_docket_url,
                )
                db.add(new_docket)
                new_count += 1

            # Commit in batches
            if total_count % 50 == 0:
                db.commit()

        db.commit()

        _docket_discovery_status["status"] = "idle"
        _docket_discovery_status["last_run"] = datetime.utcnow().isoformat()
        _docket_discovery_status["last_count"] = total_count

        return {
            "status": "success",
            "total_scraped": total_count,
            "new_dockets": new_count,
            "updated_dockets": updated_count,
            "year_filter": year,
            "status_filter": status
        }

    except Exception as e:
        _docket_discovery_status["status"] = "error"
        _docket_discovery_status["errors"].append(str(e))
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Docket discovery failed: {str(e)}")


@router.get("/pipeline/docket-discovery/verify")
def verify_docket(
    docket_number: str,
    save: bool = False,
    db: Session = Depends(get_db)
):
    """
    Verify a single docket number against Florida PSC.

    Args:
        docket_number: Docket number to verify (e.g., "20250001-EI" or "20250001")
        save: Whether to save the docket to the database
    """
    from florida.scrapers.clerkoffice import FloridaClerkOfficeClient
    import re

    # Normalize docket number - strip any sector suffix for the API call
    clean_number = re.sub(r'-[A-Z]{2}$', '', docket_number.strip())

    client = FloridaClerkOfficeClient()
    try:
        details = client.get_docket_details(clean_number)

        if not details:
            return {
                "valid": False,
                "docket_number": docket_number,
                "error": "Docket not found in Florida PSC system"
            }

        # Navigate the nested response structure
        inner_result = details.get('result', {})
        docket_events = inner_result.get('docketEventDetails', [])

        if not docket_events:
            return {
                "valid": False,
                "docket_number": docket_number,
                "error": "No docket details returned from PSC"
            }

        # Get first event (primary docket info)
        event = docket_events[0]
        docket_num = event.get('docketnum', clean_number)
        title = event.get('docketTitle', '')
        case_status = event.get('casestatus', 0)
        status = 'open' if case_status == 1 else 'closed'
        filed_date = event.get('dueDate', event.get('completionDate'))

        # Parse filed date
        if filed_date and filed_date != '0001-01-01T00:00:00':
            try:
                from datetime import datetime
                if 'T' in str(filed_date):
                    filed_date = datetime.fromisoformat(filed_date.replace('Z', '')).strftime('%Y-%m-%d')
            except:
                pass

    except Exception as e:
        return {
            "valid": False,
            "docket_number": docket_number,
            "error": f"API error: {str(e)}"
        }

    # Build the response
    result = {
        "valid": True,
        "docket_number": docket_num,
        "title": title,
        "status": status,
        "filed_date": filed_date if filed_date != '0001-01-01T00:00:00' else None,
    }

    if save:
        from datetime import datetime

        existing = db.query(FLDocket).filter(
            FLDocket.docket_number == docket_num
        ).first()

        if existing:
            result["saved"] = False
            result["message"] = "Docket already exists in database"
        else:
            # Parse year from docket number
            try:
                year = int(docket_num[:4])
            except:
                year = datetime.now().year

            new_docket = FLDocket(
                docket_number=docket_num,
                year=year,
                title=title,
                status=status,
                psc_docket_url=f"https://www.psc.state.fl.us/ClerkOffice/DocketFiling?docket={docket_num}",
            )
            db.add(new_docket)
            db.commit()
            result["saved"] = True
            result["message"] = "Docket saved to database"

    return result


@router.get("/dockets")
def list_dockets(
    status: Optional[str] = None,
    sector: Optional[str] = None,
    year: Optional[int] = None,
    search: Optional[str] = None,
    page: int = 1,
    page_size: int = 50,
    db: Session = Depends(get_db)
):
    """List dockets with filtering and pagination."""
    query = db.query(FLDocket)

    if status:
        query = query.filter(FLDocket.status == status)
    if sector:
        query = query.filter(FLDocket.sector_code == sector)
    if year:
        query = query.filter(FLDocket.year == year)
    if search:
        query = query.filter(
            (FLDocket.docket_number.ilike(f"%{search}%")) |
            (FLDocket.title.ilike(f"%{search}%")) |
            (FLDocket.utility_name.ilike(f"%{search}%"))
        )

    total = query.count()
    dockets = query.order_by(FLDocket.filed_date.desc().nullslast()).offset(
        (page - 1) * page_size
    ).limit(page_size).all()

    return {
        "items": [
            {
                "id": d.id,
                "docket_number": d.docket_number,
                "title": d.title,
                "utility_name": d.utility_name,
                "status": d.status,
                "case_type": d.case_type,
                "sector_code": d.sector_code,
                "industry_type": d.industry_type,
                "filed_date": d.filed_date.isoformat() if d.filed_date else None,
                "psc_url": d.psc_url
            }
            for d in dockets
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size
    }


# ============================================================================
# THUNDERSTONE DOCUMENT SEARCH
# ============================================================================

@router.get("/thunderstone/profiles")
def get_thunderstone_profiles():
    """Get available Thunderstone search profiles."""
    from florida.scrapers.thunderstone import FloridaThunderstoneScraper

    try:
        scraper = FloridaThunderstoneScraper()
        profiles = scraper.get_profiles()
        return {
            "profiles": [
                {
                    "id": p.id,
                    "name": p.name,
                    "description": p.description,
                    "document_count": p.document_count
                }
                for p in profiles
            ]
        }
    except Exception as e:
        return {"profiles": [], "error": str(e)}


@router.get("/thunderstone/search")
def thunderstone_search(
    query: str,
    profile: str = "library",
    docket_number: Optional[str] = None,
    limit: int = 50
):
    """
    Search Florida PSC documents via Thunderstone.

    Args:
        query: Search query text
        profile: Search profile (library, orders, filingsCurrent, etc.)
        docket_number: Optional docket number filter
        limit: Maximum results
    """
    from florida.scrapers.thunderstone import FloridaThunderstoneScraper

    try:
        scraper = FloridaThunderstoneScraper()
        documents = list(scraper.search(
            query=query,
            profile=profile,
            docket_number=docket_number,
            limit=limit
        ))

        return {
            "query": query,
            "profile": profile,
            "total": len(documents),
            "documents": [
                {
                    "id": doc.thunderstone_id,
                    "title": doc.title,
                    "document_type": doc.document_type,
                    "docket_number": doc.docket_number,
                    "file_url": doc.file_url,
                    "file_type": doc.file_type,
                    "filed_date": doc.filed_date.isoformat() if doc.filed_date else None,
                    "filer_name": doc.filer_name,
                    "excerpt": doc.content_excerpt[:300] if doc.content_excerpt else None
                }
                for doc in documents
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Thunderstone search failed: {str(e)}")


@router.get("/pipeline/hearings/{hearing_id}/details")
def get_hearing_details(hearing_id: int, db: Session = Depends(get_db)):
    """Get detailed hearing info for pipeline view."""
    hearing = db.query(FLHearing).filter(FLHearing.id == hearing_id).first()
    if not hearing:
        raise HTTPException(status_code=404, detail="Hearing not found")

    segment_count = db.query(func.count(FLTranscriptSegment.id)).filter(
        FLTranscriptSegment.hearing_id == hearing_id
    ).scalar() or 0

    analysis = db.query(FLAnalysis).filter(FLAnalysis.hearing_id == hearing_id).first()

    # Build synthetic jobs list based on processing state
    jobs = []
    job_id = 1

    # Transcription job
    if segment_count > 0:
        jobs.append({
            "id": job_id,
            "stage": "transcribe",
            "status": "completed",
            "started_at": hearing.processed_at.isoformat() if hearing.processed_at else hearing.created_at.isoformat() if hearing.created_at else None,
            "completed_at": hearing.processed_at.isoformat() if hearing.processed_at else None,
            "cost_usd": float(hearing.processing_cost_usd) if hearing.processing_cost_usd else None,
            "details": f"{segment_count} segments transcribed"
        })
        job_id += 1

    # Analysis job
    if analysis:
        jobs.append({
            "id": job_id,
            "stage": "analyze",
            "status": "completed",
            "started_at": analysis.created_at.isoformat() if analysis.created_at else None,
            "completed_at": analysis.created_at.isoformat() if analysis.created_at else None,
            "cost_usd": float(analysis.cost_usd) if analysis.cost_usd else None,
            "details": analysis.one_sentence_summary[:100] if analysis.one_sentence_summary else "Analysis complete"
        })

    # Get transcript preview (first 10 segments)
    segments = db.query(FLTranscriptSegment).filter(
        FLTranscriptSegment.hearing_id == hearing_id
    ).order_by(FLTranscriptSegment.start_time).limit(20).all()

    transcript_preview = []
    for seg in segments:
        transcript_preview.append({
            "speaker": seg.speaker_name or seg.speaker_label or "Unknown",
            "text": seg.text,
            "start_time": seg.start_time,
            "end_time": seg.end_time
        })

    # Build analysis data
    analysis_data = None
    if analysis:
        analysis_data = {
            "summary": analysis.summary,
            "one_sentence_summary": analysis.one_sentence_summary,
            "hearing_type": analysis.hearing_type,
            "utility_name": analysis.utility_name,
            "sector": analysis.sector,
            "participants": analysis.participants_json or [],
            "issues": analysis.issues_json or [],
            "commitments": analysis.commitments_json or [],
            "quotes": analysis.quotes_json or [],
            "topics": analysis.topics_extracted or [],
            "utilities": analysis.utilities_extracted or [],
            "commissioner_concerns": analysis.commissioner_concerns_json or [],
            "commissioner_mood": analysis.commissioner_mood,
            "public_comments": analysis.public_comments,
            "public_sentiment": analysis.public_sentiment,
            "likely_outcome": analysis.likely_outcome,
            "outcome_confidence": analysis.outcome_confidence,
            "risk_factors": analysis.risk_factors_json or [],
            "action_items": analysis.action_items_json or [],
        }

    return {
        "id": hearing.id,
        "title": hearing.title,
        "hearing_date": hearing.hearing_date.isoformat() if hearing.hearing_date else None,
        "hearing_type": hearing.hearing_type,
        "source_url": hearing.source_url,
        "video_url": hearing.source_url,  # For Florida, source_url is the video
        "transcript_status": hearing.transcript_status,
        "segment_count": segment_count,
        "has_analysis": analysis is not None,
        "analysis_summary": analysis.one_sentence_summary if analysis else None,
        "processing_cost_usd": float(hearing.processing_cost_usd) if hearing.processing_cost_usd else None,
        "analysis_cost": float(analysis.cost_usd) if analysis and analysis.cost_usd else None,
        "jobs": jobs,
        "transcript_preview": transcript_preview,
        "analysis": analysis_data
    }


# ============================================================================
# ENTITY LINKING
# ============================================================================

class EntityLinkingRequest(BaseModel):
    hearing_ids: Optional[List[int]] = None
    limit: int = 50


@router.post("/pipeline/entity-linking/run")
def run_entity_linking(
    request: EntityLinkingRequest,
    db: Session = Depends(get_db)
):
    """
    Run entity linking on analyzed hearings.

    This extracts docket numbers, utilities, and topics from transcripts
    and links them to canonical records using fuzzy matching.
    """
    from florida.services.entity_linking import FloridaEntityLinker

    linker = FloridaEntityLinker(db)

    if request.hearing_ids:
        # Process specific hearings
        results = []
        for hearing_id in request.hearing_ids:
            try:
                result = linker.link_hearing(hearing_id, skip_existing=False)
                results.append({
                    "hearing_id": hearing_id,
                    "dockets": len(result.dockets),
                    "utilities": len(result.utilities),
                    "topics": len(result.topics),
                    "needs_review": result.needs_review_count,
                    "errors": result.errors
                })
            except Exception as e:
                results.append({
                    "hearing_id": hearing_id,
                    "error": str(e)
                })

        return {
            "status": "completed",
            "hearings": results,
            "total_processed": len(results)
        }
    else:
        # Process all analyzed hearings
        stats = linker.link_all_hearings(
            status="analyzed",
            limit=request.limit
        )

        return {
            "status": "completed",
            "hearings_processed": stats['total_processed'],
            "total_dockets": stats['total_dockets'],
            "total_utilities": stats['total_utilities'],
            "total_topics": stats['total_topics'],
            "needs_review": stats['needs_review'],
            "errors": stats['errors'][:10]  # Limit error list
        }


@router.get("/pipeline/entity-linking/stats")
def get_entity_linking_stats(db: Session = Depends(get_db)):
    """Get entity linking statistics."""
    from florida.models.linking import (
        FLHearingDocket, FLHearingUtility, FLHearingTopic,
        FLUtility, FLTopic
    )

    # Count linked hearings
    hearings_with_dockets = db.query(func.count(func.distinct(FLHearingDocket.hearing_id))).scalar() or 0
    hearings_with_utilities = db.query(func.count(func.distinct(FLHearingUtility.hearing_id))).scalar() or 0
    hearings_with_topics = db.query(func.count(func.distinct(FLHearingTopic.hearing_id))).scalar() or 0

    # Count total links
    total_docket_links = db.query(func.count(FLHearingDocket.id)).scalar() or 0
    total_utility_links = db.query(func.count(FLHearingUtility.id)).scalar() or 0
    total_topic_links = db.query(func.count(FLHearingTopic.id)).scalar() or 0

    # Count items needing review
    dockets_review = db.query(func.count(FLHearingDocket.id)).filter(
        FLHearingDocket.needs_review == True
    ).scalar() or 0
    utilities_review = db.query(func.count(FLHearingUtility.id)).filter(
        FLHearingUtility.needs_review == True
    ).scalar() or 0
    topics_review = db.query(func.count(FLHearingTopic.id)).filter(
        FLHearingTopic.needs_review == True
    ).scalar() or 0

    # Count canonical entities
    total_utilities = db.query(func.count(FLUtility.id)).scalar() or 0
    total_topics = db.query(func.count(FLTopic.id)).scalar() or 0
    total_dockets = db.query(func.count(FLDocket.id)).scalar() or 0

    # Count analyzed hearings (those with analysis records)
    from florida.models.analysis import FLAnalysis
    analyzed_count = db.query(func.count(func.distinct(FLAnalysis.hearing_id))).scalar() or 0

    unlinked_count = db.execute(text("""
        SELECT COUNT(DISTINCT h.id)
        FROM fl_hearings h
        JOIN fl_analyses a ON a.hearing_id = h.id
        WHERE NOT EXISTS (SELECT 1 FROM fl_hearing_dockets hd WHERE hd.hearing_id = h.id)
          AND NOT EXISTS (SELECT 1 FROM fl_hearing_utilities hu WHERE hu.hearing_id = h.id)
          AND NOT EXISTS (SELECT 1 FROM fl_hearing_topics ht WHERE ht.hearing_id = h.id)
    """)).scalar() or 0

    return {
        "hearings": {
            "analyzed": analyzed_count,
            "with_dockets": hearings_with_dockets,
            "with_utilities": hearings_with_utilities,
            "with_topics": hearings_with_topics,
            "unlinked": unlinked_count
        },
        "links": {
            "dockets": total_docket_links,
            "utilities": total_utility_links,
            "topics": total_topic_links
        },
        "needs_review": {
            "dockets": dockets_review,
            "utilities": utilities_review,
            "topics": topics_review,
            "total": dockets_review + utilities_review + topics_review
        },
        "canonical_entities": {
            "dockets": total_dockets,
            "utilities": total_utilities,
            "topics": total_topics
        }
    }


# ============================================================================
# CASES (Sales Dashboard)
# ============================================================================

class CaseListItem(BaseModel):
    docket_number: str
    title: Optional[str] = None
    utility: Optional[str] = None
    filed_date: Optional[str] = None
    status: Optional[str] = None
    case_type: Optional[str] = None
    sector: Optional[str] = None
    document_count: int = 0
    hearing_count: int = 0
    event_count: int = 0
    has_selling_windows: bool = False


class CaseListResponse(BaseModel):
    total: int
    items: list
    limit: int
    offset: int


@router.get("/cases", response_model=CaseListResponse)
def list_cases(
    state: str = "FL",
    status: Optional[str] = Query(None, description="Filter by status: 'open' or 'closed'"),
    utility: Optional[str] = Query(None, description="Filter by utility name (partial match)"),
    case_type: Optional[str] = Query(None, description="Filter by docket suffix: EI, GU, etc."),
    year: Optional[int] = Query(None, description="Filter by filing year"),
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db)
):
    """
    List cases with basic info.

    Pulls from fl_dockets, enriches with counts from fl_documents, fl_hearings, fl_case_events.
    This is the main endpoint for the Cases page in the sales dashboard.
    """
    from florida.models.document import FLDocument
    from florida.models.sales import FLCaseEvent, FLSellingWindow

    query = db.query(FLDocket)

    # Exclude junk records created from order numbers
    # - Records with title that looks like an order (PSC-YYYY-NNNN-* or ORDER*)
    # - Records with docket_number that doesn't match proper format (YYYYNNNN-XX)
    from sqlalchemy import or_, and_
    query = query.filter(
        or_(
            FLDocket.title.is_(None),
            and_(
                ~FLDocket.title.like('PSC-%'),
                ~FLDocket.title.like('ORDER%')
            )
        ),
        # Proper docket format: 8 digits, hyphen, 2 letter sector code (PostgreSQL regex)
        FLDocket.docket_number.op('~')(r'^[0-9]{8}-[A-Z]{2}$')
    )

    # Status filter
    if status == 'open':
        query = query.filter(
            (FLDocket.status == 'open') |
            (FLDocket.status == 'Open') |
            (FLDocket.closed_date.is_(None))
        )
    elif status == 'closed':
        query = query.filter(
            (FLDocket.status == 'closed') |
            (FLDocket.status == 'Closed') |
            (FLDocket.closed_date.isnot(None))
        )

    # Utility filter (partial match)
    if utility:
        query = query.filter(FLDocket.utility_name.ilike(f'%{utility}%'))

    # Case type filter (sector code suffix like EI, GU)
    if case_type:
        query = query.filter(FLDocket.docket_number.like(f'%-{case_type}'))

    # Year filter
    if year:
        query = query.filter(FLDocket.year == year)

    # Get total count before pagination
    total = query.count()

    # Order by filed_date descending (most recent first)
    dockets = query.order_by(
        FLDocket.filed_date.desc().nullslast()
    ).offset(offset).limit(limit).all()

    # Enrich with counts
    results = []
    for d in dockets:
        # Document count
        doc_count = db.query(func.count(FLDocument.id)).filter(
            FLDocument.docket_number == d.docket_number
        ).scalar() or 0

        # Hearing count (via hearing_docket junction table)
        hearing_count = db.query(func.count(FLHearingDocket.id)).filter(
            FLHearingDocket.docket_id == d.id
        ).scalar() or 0

        # Event count
        event_count = db.query(func.count(FLCaseEvent.id)).filter(
            FLCaseEvent.docket_number == d.docket_number
        ).scalar() or 0

        # Check for active selling windows
        has_windows = db.query(FLSellingWindow.id).filter(
            FLSellingWindow.docket_number == d.docket_number,
            FLSellingWindow.is_active == True
        ).first() is not None

        results.append({
            "docket_number": d.docket_number,
            "title": d.title,
            "utility": d.utility_name,
            "filed_date": d.filed_date.isoformat() if d.filed_date else None,
            "status": d.status,
            "case_type": d.case_type,
            "sector": d.sector_code,
            "document_count": doc_count,
            "hearing_count": hearing_count,
            "event_count": event_count,
            "has_selling_windows": has_windows,
        })

    return CaseListResponse(
        total=total,
        items=results,
        limit=limit,
        offset=offset
    )


@router.get("/cases/{docket_number}")
def get_case_detail(
    docket_number: str,
    db: Session = Depends(get_db)
):
    """
    Get detailed case information including timeline, documents, hearings.
    """
    from florida.models.document import FLDocument
    from florida.models.sales import FLCaseEvent, FLSellingWindow
    from florida.models.regulatory_decision import FLRegulatoryDecision

    # Get docket
    docket = db.query(FLDocket).filter(
        FLDocket.docket_number == docket_number
    ).first()

    if not docket:
        raise HTTPException(status_code=404, detail=f"Docket {docket_number} not found")

    # Get documents
    documents = db.query(FLDocument).filter(
        FLDocument.docket_number == docket_number
    ).order_by(FLDocument.filed_date.desc().nullslast()).limit(50).all()

    # Get events
    events = db.query(FLCaseEvent).filter(
        FLCaseEvent.docket_number == docket_number
    ).order_by(FLCaseEvent.event_date.desc()).limit(100).all()

    # Get selling windows
    windows = db.query(FLSellingWindow).filter(
        FLSellingWindow.docket_number == docket_number
    ).order_by(FLSellingWindow.window_date).all()

    # Get regulatory decision if exists
    decision = db.query(FLRegulatoryDecision).filter(
        FLRegulatoryDecision.docket_number == docket_number
    ).first()

    # Get linked hearings
    hearing_links = db.query(FLHearingDocket).filter(
        FLHearingDocket.docket_id == docket.id
    ).all()

    hearings = []
    for link in hearing_links:
        h = link.hearing
        if h:
            hearings.append({
                "id": h.id,
                "title": h.title,
                "hearing_date": h.hearing_date.isoformat() if h.hearing_date else None,
                "hearing_type": h.hearing_type,
                "source_url": h.source_url,
            })

    return {
        "docket": {
            "docket_number": docket.docket_number,
            "title": docket.title,
            "utility": docket.utility_name,
            "status": docket.status,
            "case_type": docket.case_type,
            "industry_type": docket.industry_type,
            "sector": docket.sector_code,
            "filed_date": docket.filed_date.isoformat() if docket.filed_date else None,
            "closed_date": docket.closed_date.isoformat() if docket.closed_date else None,
            "psc_url": docket.psc_url,
            # Rate case outcome fields
            "requested_revenue_increase": float(docket.requested_revenue_increase) if docket.requested_revenue_increase else None,
            "approved_revenue_increase": float(docket.approved_revenue_increase) if docket.approved_revenue_increase else None,
            "requested_roe": float(docket.requested_roe) if docket.requested_roe else None,
            "approved_roe": float(docket.approved_roe) if docket.approved_roe else None,
            "vote_result": docket.vote_result,
            "final_order_number": docket.final_order_number,
        },
        "documents": [
            {
                "id": d.id,
                "title": d.title,
                "document_type": d.document_type,
                "filed_date": d.filed_date.isoformat() if d.filed_date else None,
                "filer_name": d.filer_name,
                "file_url": d.file_url,
            }
            for d in documents
        ],
        "events": [
            {
                "id": e.id,
                "event_date": e.event_date.isoformat() if e.event_date else None,
                "event_type": e.event_type,
                "who": e.who,
                "what": e.what,
                "why_it_matters": e.why_it_matters,
                "source_type": e.source_type,
                "source_id": e.source_id,
            }
            for e in events
        ],
        "hearings": hearings,
        "selling_windows": [
            {
                "id": w.id,
                "window_type": w.window_type,
                "window_date": w.window_date.isoformat() if w.window_date else None,
                "description": w.description,
                "target_personas": w.target_personas,
                "outreach_start_date": w.outreach_start_date.isoformat() if w.outreach_start_date else None,
                "is_active": w.is_active,
            }
            for w in windows
        ],
        "decision": {
            "id": decision.id,
            "document_type": decision.document_type,
            "order_number": decision.order_number,
            "utility_name": decision.utility_name,
            "case_type": decision.case_type,
            "revenue_requested": float(decision.revenue_requested) if decision.revenue_requested else None,
            "revenue_approved": float(decision.revenue_approved) if decision.revenue_approved else None,
            "roe_requested": float(decision.roe_requested) if decision.roe_requested else None,
            "roe_approved": float(decision.roe_approved) if decision.roe_approved else None,
        } if decision else None,
        "counts": {
            "documents": len(documents),
            "events": len(events),
            "hearings": len(hearings),
            "selling_windows": len(windows),
        }
    }


@router.get("/cases/{docket_number}/events")
def get_case_events(
    docket_number: str,
    event_type: Optional[str] = Query(None, description="Filter by event type"),
    limit: int = Query(100, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db)
):
    """
    Get timeline events for a case.

    Returns events in chronological order for the CaseTimeline component.
    """
    from florida.models.sales import FLCaseEvent

    query = db.query(FLCaseEvent).filter(FLCaseEvent.docket_number == docket_number)

    if event_type:
        query = query.filter(FLCaseEvent.event_type == event_type)

    total = query.count()
    events = query.order_by(FLCaseEvent.event_date.desc()).offset(offset).limit(limit).all()

    return {
        "docket_number": docket_number,
        "total": total,
        "events": [
            {
                "id": e.id,
                "event_date": e.event_date.isoformat() if e.event_date else None,
                "event_type": e.event_type,
                "who": e.who,
                "what": e.what,
                "why_it_matters": e.why_it_matters,
                "case_summary_after": e.case_summary_after,
                "source_type": e.source_type,
                "source_id": e.source_id,
            }
            for e in events
        ]
    }


@router.get("/cases/{docket_number}/participants")
def get_case_participants(
    docket_number: str,
    role: Optional[str] = Query(None, description="Filter by role: commissioner, counsel, witness"),
    db: Session = Depends(get_db)
):
    """
    Get participants from all hearings linked to this case.

    Aggregates participants from FLHearingParticipant across all linked hearings.
    """
    from florida.models.transcript import FLHearingParticipant

    # Get docket
    docket = db.query(FLDocket).filter(FLDocket.docket_number == docket_number).first()
    if not docket:
        raise HTTPException(status_code=404, detail=f"Docket {docket_number} not found")

    # Get hearing IDs linked to this docket
    hearing_links = db.query(FLHearingDocket).filter(FLHearingDocket.docket_id == docket.id).all()
    hearing_ids = [link.hearing_id for link in hearing_links]

    if not hearing_ids:
        return {
            "docket_number": docket_number,
            "total": 0,
            "participants": [],
            "by_role": {}
        }

    # Get participants
    query = db.query(FLHearingParticipant).filter(FLHearingParticipant.hearing_id.in_(hearing_ids))

    if role:
        query = query.filter(FLHearingParticipant.participant_role == role)

    participants = query.all()

    # Group by role
    by_role = {}
    seen_names = set()  # De-duplicate across hearings
    unique_participants = []

    for p in participants:
        key = (p.participant_name, p.participant_role, p.representing_party)
        if key not in seen_names:
            seen_names.add(key)
            unique_participants.append(p)
            role_name = p.participant_role
            if role_name not in by_role:
                by_role[role_name] = []
            by_role[role_name].append({
                "name": p.participant_name,
                "role": p.participant_role,
                "representing_party": p.representing_party,
                "organization": p.organization,
                "turn_count": p.turn_count,
                "word_count": p.word_count,
            })

    return {
        "docket_number": docket_number,
        "total": len(unique_participants),
        "participants": [
            {
                "id": p.id,
                "name": p.participant_name,
                "role": p.participant_role,
                "representing_party": p.representing_party,
                "organization": p.organization,
                "turn_count": p.turn_count,
                "word_count": p.word_count,
            }
            for p in unique_participants
        ],
        "by_role": by_role
    }


@router.get("/cases/{docket_number}/financials")
def get_case_financials(
    docket_number: str,
    db: Session = Depends(get_db)
):
    """
    Get financial data for a rate case.

    Includes requested vs approved amounts, ROE, and voting info.
    """
    from florida.models.regulatory_decision import FLRegulatoryDecision

    # Get docket
    docket = db.query(FLDocket).filter(FLDocket.docket_number == docket_number).first()
    if not docket:
        raise HTTPException(status_code=404, detail=f"Docket {docket_number} not found")

    # Get decision if exists
    decision = db.query(FLRegulatoryDecision).filter(
        FLRegulatoryDecision.docket_number == docket_number
    ).first()

    # Check if this is a rate case (has financial data)
    is_rate_case = any([
        docket.requested_revenue_increase,
        docket.approved_revenue_increase,
        docket.requested_roe,
        docket.approved_roe,
        decision
    ])

    return {
        "docket_number": docket_number,
        "is_rate_case": is_rate_case,
        "requested": {
            "revenue_increase": float(docket.requested_revenue_increase) if docket.requested_revenue_increase else None,
            "roe": float(docket.requested_roe) if docket.requested_roe else None,
        },
        "approved": {
            "revenue_increase": float(docket.approved_revenue_increase) if docket.approved_revenue_increase else None,
            "roe": float(docket.approved_roe) if docket.approved_roe else None,
        },
        "vote_result": docket.vote_result,
        "final_order_number": docket.final_order_number,
        "decision": {
            "id": decision.id,
            "decision_date": decision.decision_date.isoformat() if decision.decision_date else None,
            "outcome": decision.outcome,
            "revenue_approved": float(decision.revenue_approved) if decision.revenue_approved else None,
            "roe_approved": float(decision.roe_approved) if decision.roe_approved else None,
            "vote_result": decision.vote_result,
            "order_number": decision.order_number,
            "summary": decision.summary,
        } if decision else None
    }


@router.get("/cases/{docket_number}/documents")
def get_case_documents(
    docket_number: str,
    document_type: Optional[str] = Query(None, description="Filter by document type"),
    filer: Optional[str] = Query(None, description="Filter by filer name"),
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db)
):
    """
    Get documents for a case with filtering.

    Supports filtering by document type and filer.
    """
    from florida.models.document import FLDocument

    query = db.query(FLDocument).filter(FLDocument.docket_number == docket_number)

    if document_type:
        query = query.filter(FLDocument.document_type.ilike(f'%{document_type}%'))

    if filer:
        query = query.filter(FLDocument.filer_name.ilike(f'%{filer}%'))

    total = query.count()
    documents = query.order_by(FLDocument.filed_date.desc().nullslast()).offset(offset).limit(limit).all()

    # Get distinct document types for filter options
    doc_types = db.query(FLDocument.document_type).filter(
        FLDocument.docket_number == docket_number,
        FLDocument.document_type.isnot(None)
    ).distinct().all()

    # Get distinct filers for filter options
    filers = db.query(FLDocument.filer_name).filter(
        FLDocument.docket_number == docket_number,
        FLDocument.filer_name.isnot(None)
    ).distinct().all()

    return {
        "docket_number": docket_number,
        "total": total,
        "documents": [
            {
                "id": d.id,
                "title": d.title,
                "document_type": d.document_type,
                "filed_date": d.filed_date.isoformat() if d.filed_date else None,
                "filer_name": d.filer_name,
                "file_url": d.file_url,
                "file_type": d.file_type,
                "page_count": d.page_count,
            }
            for d in documents
        ],
        "filter_options": {
            "document_types": [t[0] for t in doc_types if t[0]],
            "filers": [f[0] for f in filers if f[0]],
        }
    }
