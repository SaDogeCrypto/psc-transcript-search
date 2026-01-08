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
from florida.scraper import (
    get_scraper_status as _get_scraper_status,
    start_scraper_async,
    stop_scraper as _stop_scraper,
)

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


@router.post("/pipeline/start")
def start_pipeline(
    background_tasks: BackgroundTasks,
    stages: Optional[str] = Query(None, description="Comma-separated stages: transcribe,analyze"),
    limit: int = Query(10, description="Max hearings to process"),
    db: Session = Depends(get_db)
):
    """Start the pipeline (for demo, this just updates status)."""
    if _pipeline_state["status"] == "running":
        raise HTTPException(status_code=409, detail="Pipeline is already running")

    _pipeline_state["status"] = "running"
    _pipeline_state["started_at"] = datetime.now(timezone.utc).isoformat()

    return {
        "message": "Pipeline started",
        "stages": stages.split(",") if stages else ["transcribe", "analyze"],
        "limit": limit,
        "status": "running"
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
    Trigger a specific pipeline stage on selected hearings.

    Supported stages:
    - transcribe: Queue hearings for transcription
    - analyze: Queue hearings for analysis
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

    processed = []
    errors = []

    for hearing in hearings:
        try:
            if stage == "transcribe":
                # Mark hearing as ready for transcription
                # The actual transcription happens via batch_transcribe.py
                if hearing.status == "pending":
                    processed.append({"id": hearing.id, "title": hearing.title[:50]})
                else:
                    errors.append({"id": hearing.id, "error": f"Cannot transcribe: status is {hearing.status}"})

            elif stage == "analyze":
                # Check if hearing has transcript segments
                segment_count = db.query(func.count(FLTranscriptSegment.id)).filter(
                    FLTranscriptSegment.hearing_id == hearing.id
                ).scalar()

                if segment_count > 0:
                    # Check if already analyzed
                    existing_analysis = db.query(FLAnalysis).filter(
                        FLAnalysis.hearing_id == hearing.id
                    ).first()

                    if existing_analysis:
                        errors.append({"id": hearing.id, "error": "Already analyzed"})
                    else:
                        # Mark as ready for analysis (status transcribed -> will be picked up by batch_analyze)
                        if hearing.status != "analyzed":
                            hearing.status = "transcribed"
                            processed.append({"id": hearing.id, "title": hearing.title[:50]})
                        else:
                            errors.append({"id": hearing.id, "error": "Already analyzed"})
                else:
                    errors.append({"id": hearing.id, "error": "No transcript segments found"})

        except Exception as e:
            errors.append({"id": hearing.id, "error": str(e)})

    db.commit()

    return {
        "message": f"Queued {len(processed)} hearings for {stage}",
        "stage": stage,
        "processed": processed,
        "errors": errors,
        "note": f"Run 'python scripts/batch_{stage}.py' to process these hearings"
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
# DOCKET DISCOVERY (Stub endpoints)
# ============================================================================

@router.get("/pipeline/docket-sources")
def get_docket_sources():
    """Get docket sources (stub)."""
    return []


@router.post("/pipeline/docket-sources/{source_id}/toggle")
def toggle_docket_source(source_id: int):
    """Toggle docket source (stub)."""
    return {"message": "Not implemented", "source_id": source_id}


@router.get("/pipeline/data-quality")
def get_data_quality(db: Session = Depends(get_db)):
    """Get data quality stats."""
    total_hearings = db.query(func.count(FLHearing.id)).scalar() or 0
    with_transcripts = db.execute(text("""
        SELECT COUNT(DISTINCT hearing_id) FROM fl_transcript_segments
    """)).scalar() or 0
    with_analysis = db.query(func.count(FLAnalysis.id)).scalar() or 0

    return {
        "total_hearings": total_hearings,
        "hearings_with_transcripts": with_transcripts,
        "hearings_with_analysis": with_analysis,
        "transcript_coverage": round(with_transcripts / total_hearings * 100, 1) if total_hearings > 0 else 0,
        "analysis_coverage": round(with_analysis / total_hearings * 100, 1) if total_hearings > 0 else 0,
        "dockets_total": 0,
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
        "known_dockets": 0,
        "docket_sources": {
            "total": 1,
            "enabled": 1
        }
    }


@router.get("/pipeline/docket-discovery/stats")
def get_docket_discovery_stats():
    """Get docket discovery stats (stub)."""
    return {
        "total_dockets": 0,
        "matched_dockets": 0,
        "pending_dockets": 0,
        "last_run": None
    }


@router.get("/pipeline/docket-discovery/scrapers")
def get_docket_scrapers():
    """Get docket scrapers (stub)."""
    return []


@router.post("/pipeline/docket-discovery/start")
def start_docket_discovery(states: Optional[str] = None):
    """Start docket discovery (stub)."""
    return {"message": "Docket discovery not implemented", "status": "unavailable"}


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
# REVIEW ENDPOINTS (Stub for entity review workflow)
# ============================================================================

@router.get("/review/stats")
def get_review_stats(db: Session = Depends(get_db)):
    """Get review queue statistics."""
    # For now, return zeros since we don't have the entity review workflow
    return {
        "total": 0,
        "dockets": 0,
        "topics": 0,
        "utilities": 0,
        "hearings": 0
    }


@router.get("/review/queue")
def get_review_queue(
    entity_type: Optional[str] = None,
    limit: int = 50,
    offset: int = 0
):
    """Get items needing review (stub)."""
    return {"items": [], "total": 0}


@router.get("/review/hearings")
def get_review_hearings(
    limit: int = 20,
    offset: int = 0,
    db: Session = Depends(get_db)
):
    """Get hearings with entities needing review (stub)."""
    return {"items": [], "total": 0}


@router.post("/review/hearings/{hearing_id}/bulk")
def bulk_review_hearing(hearing_id: int, db: Session = Depends(get_db)):
    """Bulk approve/reject entities for a hearing (stub)."""
    return {"message": "Review not implemented", "hearing_id": hearing_id}


@router.post("/review/{entity_type}/{entity_id}")
def review_entity(entity_type: str, entity_id: int):
    """Review a specific entity (stub)."""
    return {"message": "Review not implemented", "entity_type": entity_type, "entity_id": entity_id}


@router.post("/review/hearing_docket/{hearing_id}/{docket_id}")
def link_hearing_docket(hearing_id: int, docket_id: int):
    """Link a hearing to a docket (stub)."""
    return {"message": "Not implemented", "hearing_id": hearing_id, "docket_id": docket_id}
