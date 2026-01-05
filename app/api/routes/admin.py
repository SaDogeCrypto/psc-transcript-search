"""
Admin API routes for pipeline monitoring and management.
"""
from datetime import datetime, timedelta
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_

from app.database import get_db
from app.models.database import (
    State, Source, Hearing, PipelineJob, PipelineRun,
    Transcript, Analysis, Segment
)
from app.models.schemas import (
    SourceWithStatus, HearingWithPipeline, PipelineJobResponse,
    PipelineRunResponse, PipelineRunDetail, AdminStatsResponse,
    HearingFilters, SourceCreateRequest, StateResponse
)

router = APIRouter(prefix="/admin", tags=["admin"])


# ============================================================================
# STATES
# ============================================================================

@router.get("/states", response_model=List[StateResponse])
def list_states(db: Session = Depends(get_db)):
    """List all available states."""
    states = db.query(State).order_by(State.name).all()

    # Get hearing counts per state
    hearing_counts = dict(
        db.query(Hearing.state_id, func.count(Hearing.id))
        .group_by(Hearing.state_id)
        .all()
    )

    return [
        StateResponse(
            id=s.id,
            code=s.code,
            name=s.name,
            commission_name=s.commission_name,
            hearing_count=hearing_counts.get(s.id, 0)
        )
        for s in states
    ]


# ============================================================================
# SOURCES
# ============================================================================

@router.post("/sources", response_model=SourceWithStatus)
def create_source(
    source_data: SourceCreateRequest,
    db: Session = Depends(get_db)
):
    """Create a new source."""
    # Verify state exists
    state = db.query(State).filter(State.id == source_data.state_id).first()
    if not state:
        raise HTTPException(status_code=404, detail="State not found")

    # Check for duplicate URL
    existing = db.query(Source).filter(Source.url == source_data.url).first()
    if existing:
        raise HTTPException(status_code=400, detail="A source with this URL already exists")

    # Create the source
    source = Source(
        state_id=source_data.state_id,
        name=source_data.name,
        source_type=source_data.source_type,
        url=source_data.url,
        check_frequency_hours=source_data.check_frequency_hours,
        enabled=source_data.enabled,
        status="pending"
    )
    db.add(source)
    db.commit()
    db.refresh(source)

    return SourceWithStatus(
        id=source.id,
        state_id=source.state_id,
        state_code=state.code,
        state_name=state.name,
        name=source.name,
        source_type=source.source_type,
        url=source.url,
        enabled=source.enabled,
        check_frequency_hours=source.check_frequency_hours,
        last_checked_at=source.last_checked_at,
        last_hearing_at=source.last_hearing_at,
        status=source.status,
        error_message=source.error_message,
        created_at=source.created_at
    )


@router.delete("/sources/{source_id}")
def delete_source(source_id: int, db: Session = Depends(get_db)):
    """Delete a source. This will NOT delete associated hearings."""
    source = db.query(Source).filter(Source.id == source_id).first()
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")

    source_name = source.name
    db.delete(source)
    db.commit()

    return {"message": f"Source '{source_name}' deleted successfully", "source_id": source_id}


@router.get("/sources", response_model=List[SourceWithStatus])
def list_sources(
    state: Optional[str] = None,
    status: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """List all sources with their current status."""
    query = db.query(
        Source,
        State.code.label("state_code"),
        State.name.label("state_name")
    ).join(State, Source.state_id == State.id)

    if state:
        query = query.filter(State.code == state.upper())
    if status:
        query = query.filter(Source.status == status)

    query = query.order_by(State.code, Source.name)
    results = query.all()

    return [
        SourceWithStatus(
            id=s.Source.id,
            state_id=s.Source.state_id,
            state_code=s.state_code,
            state_name=s.state_name,
            name=s.Source.name,
            source_type=s.Source.source_type,
            url=s.Source.url,
            enabled=s.Source.enabled,
            check_frequency_hours=s.Source.check_frequency_hours,
            last_checked_at=s.Source.last_checked_at,
            last_hearing_at=s.Source.last_hearing_at,
            status=s.Source.status,
            error_message=s.Source.error_message,
            created_at=s.Source.created_at
        )
        for s in results
    ]


@router.post("/sources/{source_id}/check")
def trigger_source_check(
    source_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """Manually trigger a check for new hearings from a source."""
    source = db.query(Source).filter(Source.id == source_id).first()
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")

    # Queue the check (would integrate with worker in production)
    # For now, just update status
    source.status = "checking"
    source.last_checked_at = datetime.utcnow()
    db.commit()

    # TODO: Add to background task queue
    # background_tasks.add_task(check_source_for_hearings, source_id)

    return {"message": f"Check triggered for source {source.name}", "source_id": source_id}


@router.patch("/sources/{source_id}/toggle")
def toggle_source(source_id: int, db: Session = Depends(get_db)):
    """Enable or disable a source."""
    source = db.query(Source).filter(Source.id == source_id).first()
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")

    source.enabled = not source.enabled
    db.commit()

    return {"message": f"Source {'enabled' if source.enabled else 'disabled'}", "enabled": source.enabled}


# ============================================================================
# HEARINGS (ADMIN VIEW)
# ============================================================================

@router.get("/hearings", response_model=List[HearingWithPipeline])
def list_hearings_admin(
    states: Optional[str] = Query(None, description="Comma-separated state codes"),
    status: Optional[str] = None,
    pipeline_status: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    page: int = 1,
    page_size: int = 50,
    db: Session = Depends(get_db)
):
    """List hearings with full pipeline status for admin dashboard."""
    query = db.query(
        Hearing,
        State.code.label("state_code"),
        State.name.label("state_name")
    ).join(State, Hearing.state_id == State.id)

    # Filters
    if states:
        state_list = [s.strip().upper() for s in states.split(",")]
        query = query.filter(State.code.in_(state_list))
    if status:
        query = query.filter(Hearing.status == status)
    if date_from:
        query = query.filter(Hearing.hearing_date >= date_from)
    if date_to:
        query = query.filter(Hearing.hearing_date <= date_to)

    # Order by most recent first
    query = query.order_by(Hearing.created_at.desc())

    # Pagination
    offset = (page - 1) * page_size
    results = query.offset(offset).limit(page_size).all()

    # Fetch pipeline jobs for each hearing
    hearing_ids = [r.Hearing.id for r in results]
    pipeline_jobs = db.query(PipelineJob).filter(
        PipelineJob.hearing_id.in_(hearing_ids)
    ).all()

    # Group jobs by hearing
    jobs_by_hearing = {}
    for job in pipeline_jobs:
        if job.hearing_id not in jobs_by_hearing:
            jobs_by_hearing[job.hearing_id] = []
        jobs_by_hearing[job.hearing_id].append(job)

    # Calculate pipeline status for each hearing
    def get_pipeline_status(jobs):
        if not jobs:
            return "discovered"
        stages = {j.stage: j.status for j in jobs}
        if any(s == "error" for s in stages.values()):
            return "error"
        if any(s == "running" for s in stages.values()):
            if stages.get("download") == "running":
                return "downloading"
            if stages.get("transcribe") == "running":
                return "transcribing"
            if stages.get("analyze") == "running":
                return "analyzing"
        if all(s == "complete" for s in stages.values()) and len(stages) == 3:
            return "complete"
        if stages.get("analyze") == "complete":
            return "complete"
        if stages.get("transcribe") == "complete":
            return "analyzing"
        if stages.get("download") == "complete":
            return "transcribing"
        return "discovered"

    # Filter by pipeline status if requested
    response = []
    for r in results:
        jobs = jobs_by_hearing.get(r.Hearing.id, [])
        p_status = get_pipeline_status(jobs)

        if pipeline_status and p_status != pipeline_status:
            continue

        response.append(HearingWithPipeline(
            id=r.Hearing.id,
            state_code=r.state_code,
            state_name=r.state_name,
            title=r.Hearing.title,
            hearing_date=r.Hearing.hearing_date,
            hearing_type=r.Hearing.hearing_type,
            utility_name=r.Hearing.utility_name,
            duration_seconds=r.Hearing.duration_seconds,
            status=r.Hearing.status,
            source_url=r.Hearing.source_url,
            created_at=r.Hearing.created_at,
            pipeline_status=p_status,
            pipeline_jobs=[
                PipelineJobResponse(
                    id=j.id,
                    hearing_id=j.hearing_id,
                    stage=j.stage,
                    status=j.status,
                    started_at=j.started_at,
                    completed_at=j.completed_at,
                    error_message=j.error_message,
                    retry_count=j.retry_count,
                    cost_usd=float(j.cost_usd) if j.cost_usd else None
                )
                for j in jobs
            ]
        ))

    return response


@router.post("/hearings/{hearing_id}/retry")
def retry_hearing(
    hearing_id: int,
    stage: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Retry failed pipeline stages for a hearing."""
    hearing = db.query(Hearing).filter(Hearing.id == hearing_id).first()
    if not hearing:
        raise HTTPException(status_code=404, detail="Hearing not found")

    # Find failed jobs
    query = db.query(PipelineJob).filter(
        PipelineJob.hearing_id == hearing_id,
        PipelineJob.status == "error"
    )
    if stage:
        query = query.filter(PipelineJob.stage == stage)

    failed_jobs = query.all()
    if not failed_jobs:
        raise HTTPException(status_code=400, detail="No failed jobs to retry")

    # Reset jobs to pending
    for job in failed_jobs:
        job.status = "pending"
        job.error_message = None
        job.retry_count += 1

    db.commit()

    return {
        "message": f"Retrying {len(failed_jobs)} job(s) for hearing {hearing_id}",
        "jobs_retried": [j.stage for j in failed_jobs]
    }


@router.post("/hearings/{hearing_id}/cancel")
def cancel_hearing(hearing_id: int, db: Session = Depends(get_db)):
    """Cancel stuck/running pipeline jobs for a hearing."""
    hearing = db.query(Hearing).filter(Hearing.id == hearing_id).first()
    if not hearing:
        raise HTTPException(status_code=404, detail="Hearing not found")

    # Find running jobs
    running_jobs = db.query(PipelineJob).filter(
        PipelineJob.hearing_id == hearing_id,
        PipelineJob.status == "running"
    ).all()

    for job in running_jobs:
        job.status = "cancelled"
        job.error_message = "Cancelled by admin"
        job.completed_at = datetime.utcnow()

    db.commit()

    return {
        "message": f"Cancelled {len(running_jobs)} job(s) for hearing {hearing_id}",
        "jobs_cancelled": [j.stage for j in running_jobs]
    }


# ============================================================================
# PIPELINE RUNS
# ============================================================================

@router.get("/runs", response_model=List[PipelineRunResponse])
def list_pipeline_runs(
    limit: int = 30,
    db: Session = Depends(get_db)
):
    """Get history of daily pipeline runs."""
    runs = db.query(PipelineRun).order_by(
        PipelineRun.started_at.desc()
    ).limit(limit).all()

    return [
        PipelineRunResponse(
            id=r.id,
            started_at=r.started_at,
            completed_at=r.completed_at,
            status=r.status,
            sources_checked=r.sources_checked,
            new_hearings=r.new_hearings,
            hearings_processed=r.hearings_processed,
            errors=r.errors,
            transcription_cost_usd=float(r.transcription_cost_usd or 0),
            analysis_cost_usd=float(r.analysis_cost_usd or 0),
            total_cost_usd=float(r.total_cost_usd or 0)
        )
        for r in runs
    ]


@router.get("/runs/{run_id}", response_model=PipelineRunDetail)
def get_pipeline_run(run_id: int, db: Session = Depends(get_db)):
    """Get details of a specific pipeline run."""
    run = db.query(PipelineRun).filter(PipelineRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Pipeline run not found")

    return PipelineRunDetail(
        id=run.id,
        started_at=run.started_at,
        completed_at=run.completed_at,
        status=run.status,
        sources_checked=run.sources_checked,
        new_hearings=run.new_hearings,
        hearings_processed=run.hearings_processed,
        errors=run.errors,
        transcription_cost_usd=float(run.transcription_cost_usd or 0),
        analysis_cost_usd=float(run.analysis_cost_usd or 0),
        total_cost_usd=float(run.total_cost_usd or 0),
        details_json=run.details_json
    )


# ============================================================================
# STATS
# ============================================================================

@router.get("/stats", response_model=AdminStatsResponse)
def get_admin_stats(db: Session = Depends(get_db)):
    """Get comprehensive admin statistics."""
    now = datetime.utcnow()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = today_start - timedelta(days=7)
    month_start = today_start - timedelta(days=30)

    # Basic counts
    total_states = db.query(func.count(State.id)).scalar()
    total_sources = db.query(func.count(Source.id)).scalar()
    total_hearings = db.query(func.count(Hearing.id)).scalar()
    total_segments = db.query(func.count(Segment.id)).scalar()

    # Duration
    total_seconds = db.query(func.sum(Hearing.duration_seconds)).scalar() or 0
    total_hours = round(total_seconds / 3600, 1)

    # Hearings by status
    status_counts = db.query(
        Hearing.status,
        func.count(Hearing.id)
    ).group_by(Hearing.status).all()
    hearings_by_status = {s: c for s, c in status_counts}

    # Hearings by state
    state_counts = db.query(
        State.code,
        func.count(Hearing.id)
    ).join(Hearing).group_by(State.code).all()
    hearings_by_state = {s: c for s, c in state_counts}

    # Source health
    sources_healthy = db.query(func.count(Source.id)).filter(Source.status == "healthy").scalar()
    sources_error = db.query(func.count(Source.id)).filter(Source.status == "error").scalar()

    # Pipeline jobs
    jobs_pending = db.query(func.count(PipelineJob.id)).filter(PipelineJob.status == "pending").scalar()
    jobs_running = db.query(func.count(PipelineJob.id)).filter(PipelineJob.status == "running").scalar()
    jobs_error = db.query(func.count(PipelineJob.id)).filter(PipelineJob.status == "error").scalar()

    # Costs
    total_transcription = db.query(func.sum(PipelineJob.cost_usd)).filter(
        PipelineJob.stage == "transcribe"
    ).scalar() or 0
    total_analysis = db.query(func.sum(PipelineJob.cost_usd)).filter(
        PipelineJob.stage == "analyze"
    ).scalar() or 0

    # Costs by period
    cost_today = db.query(func.sum(PipelineJob.cost_usd)).filter(
        PipelineJob.completed_at >= today_start
    ).scalar() or 0
    cost_week = db.query(func.sum(PipelineJob.cost_usd)).filter(
        PipelineJob.completed_at >= week_start
    ).scalar() or 0
    cost_month = db.query(func.sum(PipelineJob.cost_usd)).filter(
        PipelineJob.completed_at >= month_start
    ).scalar() or 0

    # Recent activity
    hearings_24h = db.query(func.count(Hearing.id)).filter(
        Hearing.created_at >= now - timedelta(hours=24)
    ).scalar()
    hearings_7d = db.query(func.count(Hearing.id)).filter(
        Hearing.created_at >= now - timedelta(days=7)
    ).scalar()

    return AdminStatsResponse(
        total_states=total_states,
        total_sources=total_sources,
        total_hearings=total_hearings,
        total_segments=total_segments,
        total_hours=total_hours,
        hearings_by_status=hearings_by_status,
        hearings_by_state=hearings_by_state,
        total_transcription_cost=float(total_transcription),
        total_analysis_cost=float(total_analysis),
        total_cost=float(total_transcription) + float(total_analysis),
        hearings_last_24h=hearings_24h,
        hearings_last_7d=hearings_7d,
        sources_healthy=sources_healthy,
        sources_error=sources_error,
        pipeline_jobs_pending=jobs_pending,
        pipeline_jobs_running=jobs_running,
        pipeline_jobs_error=jobs_error,
        cost_today=float(cost_today),
        cost_this_week=float(cost_week),
        cost_this_month=float(cost_month)
    )


# ============================================================================
# SCRAPER CONTROL
# ============================================================================

# Scraper endpoints are only available when the scraper module is installed
# (not in the lightweight API-only deployment)
try:
    from scripts.scraper_orchestrator import get_orchestrator, ScraperStatus
    SCRAPER_AVAILABLE = True
except ImportError:
    SCRAPER_AVAILABLE = False


@router.get("/scraper/status")
def get_scraper_status():
    """Get current scraper status and progress."""
    if not SCRAPER_AVAILABLE:
        raise HTTPException(status_code=501, detail="Scraper module not available in this deployment")
    orchestrator = get_orchestrator()
    return orchestrator.get_progress()


@router.post("/scraper/start")
def start_scraper(
    background_tasks: BackgroundTasks,
    scraper_types: Optional[str] = Query(
        None,
        description="Comma-separated scraper types (admin_monitor, youtube_channel, rss_feed)"
    ),
    state: Optional[str] = Query(None, description="State code to filter (e.g., CA, TX)"),
    dry_run: bool = Query(False, description="Preview mode - don't save to database")
):
    """
    Start the scraper in the background.

    Returns immediately with status. Poll /admin/scraper/status for progress.
    """
    if not SCRAPER_AVAILABLE:
        raise HTTPException(status_code=501, detail="Scraper module not available in this deployment")
    orchestrator = get_orchestrator()

    if orchestrator.is_running:
        raise HTTPException(
            status_code=409,
            detail="Scraper is already running. Stop it first or wait for completion."
        )

    # Parse scraper types
    types_list = None
    if scraper_types:
        types_list = [t.strip() for t in scraper_types.split(",")]
        valid_types = {"admin_monitor", "youtube_channel", "rss_feed"}
        invalid = set(types_list) - valid_types
        if invalid:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid scraper types: {invalid}. Valid types: {valid_types}"
            )

    # Start in background
    orchestrator.run_async(
        scraper_types=types_list,
        state_code=state,
        dry_run=dry_run
    )

    return {
        "message": "Scraper started",
        "scraper_types": types_list or ["admin_monitor", "youtube_channel", "rss_feed"],
        "state_filter": state,
        "dry_run": dry_run,
        "status": "running"
    }


@router.post("/scraper/stop")
def stop_scraper():
    """
    Request the scraper to stop after completing the current source.

    The scraper will finish processing the current source before stopping.
    """
    if not SCRAPER_AVAILABLE:
        raise HTTPException(status_code=501, detail="Scraper module not available in this deployment")
    orchestrator = get_orchestrator()

    if not orchestrator.is_running:
        return {
            "message": "Scraper is not running",
            "status": orchestrator.progress.status.value
        }

    orchestrator.request_stop()

    return {
        "message": "Stop requested - scraper will stop after current source",
        "status": "stopping"
    }


@router.post("/scraper/run-now")
def run_scraper_sync(
    scraper_types: Optional[str] = Query(
        None,
        description="Comma-separated scraper types (admin_monitor, youtube_channel, rss_feed)"
    ),
    state: Optional[str] = Query(None, description="State code to filter (e.g., CA, TX)"),
    dry_run: bool = Query(False, description="Preview mode - don't save to database"),
    db: Session = Depends(get_db)
):
    """
    Run the scraper synchronously and wait for completion.

    Warning: This can take several minutes depending on the number of sources.
    For long-running scrapes, use /admin/scraper/start instead.
    """
    if not SCRAPER_AVAILABLE:
        raise HTTPException(status_code=501, detail="Scraper module not available in this deployment")
    orchestrator = get_orchestrator()

    if orchestrator.is_running:
        raise HTTPException(
            status_code=409,
            detail="Scraper is already running"
        )

    # Parse scraper types
    types_list = None
    if scraper_types:
        types_list = [t.strip() for t in scraper_types.split(",")]

    # Run synchronously
    results = orchestrator.run(
        scraper_types=types_list,
        state_code=state,
        dry_run=dry_run
    )

    return results
