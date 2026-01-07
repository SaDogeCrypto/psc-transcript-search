"""
Pipeline Control API Endpoints

Provides endpoints for:
- Pipeline status and control (start/stop/pause/resume)
- Activity and error monitoring
- Hearing retry/skip operations
- Schedule CRUD operations
"""

from datetime import datetime, timezone, timedelta
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Query
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.database import get_db
from app.models.database import (
    Hearing, PipelineJob, PipelineState, PipelineSchedule, State
)
from app.models.schemas import (
    PipelineStatusResponse,
    PipelineStartRequest,
    PipelineActivityItem,
    PipelineActivityResponse,
    PipelineErrorItem,
    PipelineErrorsResponse,
    ScheduleResponse,
    ScheduleCreateRequest,
    ScheduleUpdateRequest,
    RunStageRequest,
    RunStageResponse,
)
from app.pipeline.orchestrator import (
    PipelineOrchestrator,
    OrchestratorConfig,
    get_orchestrator,
    HEARING_STATUSES,
)
from app.pipeline.scheduler import (
    calculate_next_run,
    format_schedule_display,
)

router = APIRouter(prefix="/admin/pipeline", tags=["pipeline"])


# =============================================================================
# PIPELINE STATUS & CONTROL
# =============================================================================

@router.get("/status", response_model=PipelineStatusResponse)
def get_pipeline_status(db: Session = Depends(get_db)):
    """Get current pipeline orchestrator status and statistics."""
    # Get pipeline state
    state = db.query(PipelineState).filter(PipelineState.id == 1).first()
    if not state:
        state = PipelineState(id=1, status="idle")
        db.add(state)
        db.commit()

    # Clean up stale state if status is idle but has current hearing
    if state.status == "idle" and state.current_hearing_id is not None:
        state.current_hearing_id = None
        state.current_stage = None
        db.commit()

    # Get hearing counts by status
    status_counts = dict(
        db.query(Hearing.status, func.count(Hearing.id))
        .group_by(Hearing.status)
        .all()
    )

    # Count hearings with pending review entities (for Review stage)
    from app.models.database import HearingTopic, HearingUtility, HearingDocket
    from sqlalchemy import or_

    hearings_needing_review = db.query(Hearing.id).filter(
        Hearing.status == 'smart_extracted',
        or_(
            Hearing.id.in_(
                db.query(HearingTopic.hearing_id).filter(HearingTopic.needs_review == True)
            ),
            Hearing.id.in_(
                db.query(HearingUtility.hearing_id).filter(HearingUtility.needs_review == True)
            ),
            Hearing.id.in_(
                db.query(HearingDocket.hearing_id).filter(HearingDocket.needs_review == True)
            ),
        )
    ).distinct().count()

    status_counts['review'] = hearings_needing_review
    # Adjust smart_extracted to only count those ready for extract (no pending reviews)
    if 'smart_extracted' in status_counts:
        status_counts['ready_for_extract'] = status_counts['smart_extracted'] - hearings_needing_review

    # Get recent stats (last 24 hours to avoid timezone issues)
    since = datetime.now() - timedelta(hours=24)
    today_jobs = db.query(PipelineJob).filter(
        PipelineJob.completed_at >= since
    ).all()

    completed_jobs = [j for j in today_jobs if j.status == "complete"]
    error_jobs = [j for j in today_jobs if j.status == "error"]

    processed_today = len(set(j.hearing_id for j in completed_jobs))
    cost_today = sum(float(j.cost_usd or 0) for j in completed_jobs)
    errors_today = len(error_jobs)

    # Current hearing info
    current_hearing_title = None
    if state.current_hearing_id:
        hearing = db.query(Hearing).filter(Hearing.id == state.current_hearing_id).first()
        current_hearing_title = hearing.title[:100] if hearing else None

    return PipelineStatusResponse(
        status=state.status or "idle",
        started_at=state.started_at,
        current_hearing_id=state.current_hearing_id,
        current_hearing_title=current_hearing_title,
        current_stage=state.current_stage,
        hearings_processed=state.hearings_processed or 0,
        errors_count=state.errors_count or 0,
        total_cost_usd=float(state.total_cost_usd or 0),
        stage_counts=status_counts,
        processed_today=processed_today,
        cost_today=cost_today,
        errors_today=errors_today,
    )


@router.post("/start")
def start_pipeline(
    request: PipelineStartRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """Start the pipeline orchestrator in background."""
    # Check if already running
    state = db.query(PipelineState).filter(PipelineState.id == 1).first()
    if state and state.status == "running":
        raise HTTPException(400, "Pipeline is already running")

    # Create config from request
    config = OrchestratorConfig(
        states=request.states,
        only_stage=request.only_stage,
        max_cost_per_run=request.max_cost,
        max_hearings=request.max_hearings,
    )

    # Start in background
    orchestrator = get_orchestrator(config)
    background_tasks.add_task(orchestrator.run, once=True)

    return {"message": "Pipeline started", "config": {
        "states": request.states,
        "only_stage": request.only_stage,
        "max_cost": request.max_cost,
        "max_hearings": request.max_hearings,
    }}


@router.post("/stop")
def stop_pipeline(db: Session = Depends(get_db)):
    """Stop the pipeline after current hearing completes."""
    state = db.query(PipelineState).filter(PipelineState.id == 1).first()
    if not state or state.status != "running":
        raise HTTPException(400, "Pipeline is not running")

    orchestrator = get_orchestrator()
    orchestrator.request_stop()

    return {"message": "Stop requested - pipeline will stop after current hearing"}


@router.post("/pause")
def pause_pipeline(db: Session = Depends(get_db)):
    """Pause the pipeline (can be resumed)."""
    state = db.query(PipelineState).filter(PipelineState.id == 1).first()
    if not state or state.status != "running":
        raise HTTPException(400, "Pipeline is not running")

    orchestrator = get_orchestrator()
    orchestrator.pause()

    return {"message": "Pipeline paused"}


@router.post("/resume")
def resume_pipeline(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """Resume a paused pipeline."""
    state = db.query(PipelineState).filter(PipelineState.id == 1).first()
    if not state or state.status != "paused":
        raise HTTPException(400, "Pipeline is not paused")

    orchestrator = get_orchestrator()
    orchestrator.resume()
    background_tasks.add_task(orchestrator.run, once=True)

    return {"message": "Pipeline resumed"}


# =============================================================================
# ACTIVITY & ERRORS
# =============================================================================

@router.get("/activity", response_model=PipelineActivityResponse)
def get_pipeline_activity(
    limit: int = Query(50, le=200),
    stage: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Get recent pipeline activity (completed jobs)."""
    query = db.query(
        PipelineJob,
        Hearing.title.label("hearing_title"),
        State.code.label("state_code")
    ).join(
        Hearing, PipelineJob.hearing_id == Hearing.id
    ).outerjoin(
        State, Hearing.state_id == State.id
    ).filter(
        PipelineJob.status.in_(["complete", "error"])
    )

    if stage:
        query = query.filter(PipelineJob.stage == stage)

    jobs = query.order_by(PipelineJob.completed_at.desc()).limit(limit).all()

    items = [
        PipelineActivityItem(
            id=job.PipelineJob.id,
            hearing_id=job.PipelineJob.hearing_id,
            hearing_title=job.hearing_title[:100] if job.hearing_title else "",
            state_code=job.state_code,
            stage=job.PipelineJob.stage,
            status=job.PipelineJob.status,
            started_at=job.PipelineJob.started_at,
            completed_at=job.PipelineJob.completed_at,
            cost_usd=float(job.PipelineJob.cost_usd) if job.PipelineJob.cost_usd else None,
            error_message=job.PipelineJob.error_message,
        )
        for job in jobs
    ]

    return PipelineActivityResponse(items=items, total_count=len(items))


@router.get("/errors", response_model=PipelineErrorsResponse)
def get_pipeline_errors(
    limit: int = Query(50, le=200),
    db: Session = Depends(get_db)
):
    """Get hearings in error/failed state."""
    hearings = db.query(
        Hearing,
        State.code.label("state_code")
    ).outerjoin(
        State, Hearing.state_id == State.id
    ).filter(
        Hearing.status.in_(["error", "failed"])
    ).order_by(
        Hearing.updated_at.desc()
    ).limit(limit).all()

    items = []
    for h, state_code in hearings:
        # Get last failed job for this hearing
        last_job = db.query(PipelineJob).filter(
            PipelineJob.hearing_id == h.id,
            PipelineJob.status == "error"
        ).order_by(PipelineJob.created_at.desc()).first()

        items.append(PipelineErrorItem(
            hearing_id=h.id,
            hearing_title=h.title[:100] if h.title else "",
            state_code=state_code,
            status=h.status,
            last_stage=last_job.stage if last_job else None,
            error_message=last_job.error_message if last_job else None,
            retry_count=last_job.retry_count if last_job else 0,
            updated_at=h.updated_at,
        ))

    return PipelineErrorsResponse(items=items, total_count=len(items))


# =============================================================================
# HEARING OPERATIONS
# =============================================================================

@router.get("/hearings/{hearing_id}/details")
def get_hearing_details(hearing_id: int, db: Session = Depends(get_db)):
    """Get detailed hearing info with processing history."""
    hearing = db.query(Hearing).filter(Hearing.id == hearing_id).first()
    if not hearing:
        raise HTTPException(404, "Hearing not found")

    # Get state
    state = db.query(State).filter(State.id == hearing.state_id).first()

    # Get pipeline jobs
    jobs = db.query(PipelineJob).filter(
        PipelineJob.hearing_id == hearing_id
    ).order_by(PipelineJob.created_at.desc()).all()

    # Get transcript if exists
    from app.models.database import Transcript, Analysis, Docket, HearingDocket
    transcript = db.query(Transcript).filter(Transcript.hearing_id == hearing_id).first()

    # Get analysis if exists
    analysis = db.query(Analysis).filter(Analysis.hearing_id == hearing_id).first()

    # Get extracted dockets
    docket_links = db.query(HearingDocket, Docket).join(
        Docket, HearingDocket.docket_id == Docket.id
    ).filter(HearingDocket.hearing_id == hearing_id).all()

    return {
        "id": hearing.id,
        "title": hearing.title,
        "state_code": state.code if state else None,
        "state_name": state.name if state else None,
        "hearing_date": hearing.hearing_date,
        "status": hearing.status,
        "video_url": hearing.video_url,
        "created_at": hearing.created_at,
        "updated_at": hearing.updated_at,
        "processing_cost_usd": float(hearing.processing_cost_usd or 0),
        "jobs": [
            {
                "id": j.id,
                "stage": j.stage,
                "status": j.status,
                "started_at": j.started_at,
                "completed_at": j.completed_at,
                "cost_usd": float(j.cost_usd) if j.cost_usd else None,
                "error_message": j.error_message,
                "retry_count": j.retry_count,
            }
            for j in jobs
        ],
        "transcript": {
            "id": transcript.id,
            "word_count": transcript.word_count,
            "cost_usd": float(transcript.cost_usd) if transcript.cost_usd else None,
            "preview": transcript.full_text[:500] + "..." if transcript.full_text and len(transcript.full_text) > 500 else transcript.full_text,
        } if transcript else None,
        "analysis": {
            "id": analysis.id,
            "summary": analysis.summary,
            "one_sentence_summary": analysis.one_sentence_summary,
            "hearing_type": analysis.hearing_type,
            "utility_name": analysis.utility_name,
            "issues": analysis.issues_json,
            "commissioner_mood": analysis.commissioner_mood,
            "likely_outcome": analysis.likely_outcome,
            "cost_usd": float(analysis.cost_usd) if analysis.cost_usd else None,
        } if analysis else None,
        "dockets": [
            {
                "id": docket.id,
                "docket_number": docket.docket_number,
                "normalized_id": docket.normalized_id,
                "company": docket.company,
                "title": docket.title,
                "status": docket.status,
            }
            for link, docket in docket_links
        ],
    }


@router.post("/hearings/{hearing_id}/retry")
def retry_hearing(
    hearing_id: int,
    from_stage: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Retry a failed hearing from a specific stage."""
    hearing = db.query(Hearing).filter(Hearing.id == hearing_id).first()
    if not hearing:
        raise HTTPException(404, "Hearing not found")

    if hearing.status not in ["error", "failed"]:
        raise HTTPException(400, "Hearing is not in error state")

    # Find the last failed stage to determine where to retry from
    last_failed_job = db.query(PipelineJob).filter(
        PipelineJob.hearing_id == hearing_id,
        PipelineJob.status == "error"
    ).order_by(PipelineJob.created_at.desc()).first()

    # Map stage to the input status for that stage
    stage_input_status = {
        "download": "discovered",
        "transcribe": "downloaded",
        "analyze": "transcribed",
        "extract": "analyzed",
    }

    if from_stage:
        # User specified a stage to retry from
        hearing.status = stage_input_status.get(from_stage, "discovered")
    elif last_failed_job:
        # Retry from the failed stage
        hearing.status = stage_input_status.get(last_failed_job.stage, "discovered")
    else:
        # No info, start from beginning
        hearing.status = "discovered"

    # Reset retry counts on failed jobs
    for job in hearing.pipeline_jobs:
        if job.status == "error":
            job.retry_count = 0

    db.commit()

    return {"message": f"Hearing {hearing_id} queued for retry from {hearing.status}"}


@router.post("/hearings/{hearing_id}/skip")
def skip_hearing(
    hearing_id: int,
    reason: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Skip a hearing from pipeline processing."""
    hearing = db.query(Hearing).filter(Hearing.id == hearing_id).first()
    if not hearing:
        raise HTTPException(404, "Hearing not found")

    hearing.status = "skipped"
    db.commit()

    return {"message": f"Hearing {hearing_id} marked as skipped"}


@router.post("/retry-all")
def retry_all_errors(db: Session = Depends(get_db)):
    """Retry all failed hearings."""
    count = db.query(Hearing).filter(
        Hearing.status.in_(["error", "failed"])
    ).update({"status": "discovered"}, synchronize_session=False)

    # Reset retry counts
    db.query(PipelineJob).filter(
        PipelineJob.status == "error"
    ).update({"retry_count": 0}, synchronize_session=False)

    db.commit()

    return {"message": f"Reset {count} hearings for retry"}


@router.post("/run-stage", response_model=RunStageResponse)
def run_stage_on_hearings(
    request: RunStageRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    Queue specific hearings for a pipeline stage.

    Sets hearing status to be picked up by the specified stage,
    then starts the pipeline to process them.
    """
    valid_stages = ["download", "transcribe", "analyze", "extract"]
    if request.stage not in valid_stages:
        raise HTTPException(400, f"Invalid stage. Must be one of: {valid_stages}")

    # Check if pipeline is already running - stop it first if so
    state = db.query(PipelineState).filter(PipelineState.id == 1).first()
    if state and state.status == "running":
        # Request stop on existing orchestrator
        try:
            existing_orchestrator = get_orchestrator()
            existing_orchestrator.request_stop()
        except Exception:
            pass
        raise HTTPException(400, "Pipeline is currently running. Please wait for it to stop or stop it manually first.")

    # Map stage to the status that makes it ready for that stage
    stage_ready_status = {
        "download": "discovered",
        "transcribe": "downloaded",
        "analyze": "transcribed",
        "extract": "analyzed",  # Analyze now includes entity linking + docket matching
    }
    ready_status = stage_ready_status[request.stage]

    # Get the hearings
    hearings = db.query(Hearing).filter(Hearing.id.in_(request.hearing_ids)).all()
    found_ids = {h.id for h in hearings}
    missing_ids = set(request.hearing_ids) - found_ids

    if missing_ids:
        raise HTTPException(404, f"Hearings not found: {list(missing_ids)}")

    queued_ids = []
    skipped_ids = []

    for hearing in hearings:
        # Check if hearing can be set to this status
        # Allow setting back if already past this stage (for re-processing)
        # Skip if already in-progress for this stage
        in_progress_statuses = ["downloading", "transcribing", "analyzing", "extracting"]

        if hearing.status in in_progress_statuses:
            skipped_ids.append(hearing.id)
            continue

        # Set to ready status for the stage
        hearing.status = ready_status
        queued_ids.append(hearing.id)

    db.commit()

    # Start the pipeline if we queued any hearings
    if queued_ids:
        config = OrchestratorConfig(
            only_stage=request.stage,
            max_hearings=len(queued_ids),
            hearing_ids=queued_ids,  # Only process these specific hearings
        )
        orchestrator = get_orchestrator(config)
        background_tasks.add_task(orchestrator.run, once=True)

    return RunStageResponse(
        message=f"Queued {len(queued_ids)} hearings for {request.stage}",
        stage=request.stage,
        queued_count=len(queued_ids),
        skipped_count=len(skipped_ids),
        queued_ids=queued_ids,
        skipped_ids=skipped_ids,
    )


@router.post("/hearings/{hearing_id}/run-stage")
def run_stage_on_single_hearing(
    hearing_id: int,
    stage: str = Query(..., description="Stage to run: download, transcribe, analyze, extract"),
    background_tasks: BackgroundTasks = None,
    db: Session = Depends(get_db)
):
    """Run a specific stage on a single hearing."""
    valid_stages = ["download", "transcribe", "analyze", "extract"]
    if stage not in valid_stages:
        raise HTTPException(400, f"Invalid stage. Must be one of: {valid_stages}")

    # Check if pipeline is already running
    state = db.query(PipelineState).filter(PipelineState.id == 1).first()
    if state and state.status == "running":
        raise HTTPException(400, "Pipeline is currently running. Please wait for it to stop first.")

    hearing = db.query(Hearing).filter(Hearing.id == hearing_id).first()
    if not hearing:
        raise HTTPException(404, "Hearing not found")

    # Map stage to the status that makes it ready for that stage
    stage_ready_status = {
        "download": "discovered",
        "transcribe": "downloaded",
        "analyze": "transcribed",
        "extract": "analyzed",  # Analyze now includes entity linking + docket matching
    }
    ready_status = stage_ready_status[stage]

    # Check if hearing is in-progress
    in_progress_statuses = ["downloading", "transcribing", "analyzing", "linking", "matching", "extracting"]
    if hearing.status in in_progress_statuses:
        raise HTTPException(400, f"Hearing is currently being processed ({hearing.status})")

    # Set to ready status
    hearing.status = ready_status
    db.commit()

    # Start the pipeline
    config = OrchestratorConfig(
        only_stage=stage,
        max_hearings=1,
        hearing_ids=[hearing_id],  # Only process this specific hearing
    )
    orchestrator = get_orchestrator(config)
    background_tasks.add_task(orchestrator.run, once=True)

    return {
        "message": f"Hearing {hearing_id} queued for {stage}",
        "hearing_id": hearing_id,
        "stage": stage,
        "previous_status": hearing.status,
    }


# =============================================================================
# SCHEDULES
# =============================================================================

@router.get("/schedules", response_model=List[ScheduleResponse])
def list_schedules(db: Session = Depends(get_db)):
    """List all pipeline schedules."""
    schedules = db.query(PipelineSchedule).order_by(PipelineSchedule.name).all()

    return [
        ScheduleResponse(
            id=s.id,
            name=s.name,
            schedule_type=s.schedule_type,
            schedule_value=s.schedule_value,
            schedule_display=format_schedule_display(s),
            target=s.target,
            enabled=s.enabled,
            config_json=s.config_json,
            last_run_at=s.last_run_at,
            next_run_at=s.next_run_at,
            last_run_status=s.last_run_status,
            last_run_error=s.last_run_error,
            created_at=s.created_at,
            updated_at=s.updated_at,
        )
        for s in schedules
    ]


@router.post("/schedules", response_model=ScheduleResponse)
def create_schedule(
    request: ScheduleCreateRequest,
    db: Session = Depends(get_db)
):
    """Create a new schedule."""
    # Check for duplicate name
    existing = db.query(PipelineSchedule).filter(
        PipelineSchedule.name == request.name
    ).first()
    if existing:
        raise HTTPException(400, f"Schedule with name '{request.name}' already exists")

    schedule = PipelineSchedule(
        name=request.name,
        schedule_type=request.schedule_type,
        schedule_value=request.schedule_value,
        target=request.target,
        enabled=request.enabled,
        config_json=request.config or {},
    )

    # Calculate initial next run
    schedule.next_run_at = calculate_next_run(schedule)

    db.add(schedule)
    db.commit()
    db.refresh(schedule)

    return ScheduleResponse(
        id=schedule.id,
        name=schedule.name,
        schedule_type=schedule.schedule_type,
        schedule_value=schedule.schedule_value,
        schedule_display=format_schedule_display(schedule),
        target=schedule.target,
        enabled=schedule.enabled,
        config_json=schedule.config_json,
        last_run_at=schedule.last_run_at,
        next_run_at=schedule.next_run_at,
        last_run_status=schedule.last_run_status,
        last_run_error=schedule.last_run_error,
        created_at=schedule.created_at,
        updated_at=schedule.updated_at,
    )


@router.patch("/schedules/{schedule_id}", response_model=ScheduleResponse)
def update_schedule(
    schedule_id: int,
    request: ScheduleUpdateRequest,
    db: Session = Depends(get_db)
):
    """Update an existing schedule."""
    schedule = db.query(PipelineSchedule).filter(
        PipelineSchedule.id == schedule_id
    ).first()

    if not schedule:
        raise HTTPException(404, "Schedule not found")

    # Update fields
    if request.name is not None:
        schedule.name = request.name
    if request.schedule_type is not None:
        schedule.schedule_type = request.schedule_type
    if request.schedule_value is not None:
        schedule.schedule_value = request.schedule_value
    if request.target is not None:
        schedule.target = request.target
    if request.enabled is not None:
        schedule.enabled = request.enabled
    if request.config is not None:
        schedule.config_json = request.config

    # Recalculate next run
    if schedule.enabled:
        schedule.next_run_at = calculate_next_run(schedule)
    else:
        schedule.next_run_at = None

    schedule.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(schedule)

    return ScheduleResponse(
        id=schedule.id,
        name=schedule.name,
        schedule_type=schedule.schedule_type,
        schedule_value=schedule.schedule_value,
        schedule_display=format_schedule_display(schedule),
        target=schedule.target,
        enabled=schedule.enabled,
        config_json=schedule.config_json,
        last_run_at=schedule.last_run_at,
        next_run_at=schedule.next_run_at,
        last_run_status=schedule.last_run_status,
        last_run_error=schedule.last_run_error,
        created_at=schedule.created_at,
        updated_at=schedule.updated_at,
    )


@router.delete("/schedules/{schedule_id}")
def delete_schedule(schedule_id: int, db: Session = Depends(get_db)):
    """Delete a schedule."""
    schedule = db.query(PipelineSchedule).filter(
        PipelineSchedule.id == schedule_id
    ).first()

    if not schedule:
        raise HTTPException(404, "Schedule not found")

    db.delete(schedule)
    db.commit()

    return {"message": f"Schedule '{schedule.name}' deleted"}


@router.post("/schedules/{schedule_id}/toggle")
def toggle_schedule(schedule_id: int, db: Session = Depends(get_db)):
    """Enable/disable a schedule."""
    schedule = db.query(PipelineSchedule).filter(
        PipelineSchedule.id == schedule_id
    ).first()

    if not schedule:
        raise HTTPException(404, "Schedule not found")

    schedule.enabled = not schedule.enabled

    if schedule.enabled:
        schedule.next_run_at = calculate_next_run(schedule)
    else:
        schedule.next_run_at = None

    schedule.updated_at = datetime.now(timezone.utc)
    db.commit()

    return {
        "enabled": schedule.enabled,
        "next_run_at": schedule.next_run_at.isoformat() if schedule.next_run_at else None
    }


@router.post("/schedules/{schedule_id}/run-now")
def run_schedule_now(
    schedule_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """Trigger a schedule to run immediately."""
    schedule = db.query(PipelineSchedule).filter(
        PipelineSchedule.id == schedule_id
    ).first()

    if not schedule:
        raise HTTPException(404, "Schedule not found")

    # Queue the run
    config = schedule.config_json or {}

    if schedule.target in ("pipeline", "all"):
        orchestrator_config = OrchestratorConfig(
            states=config.get("states"),
            only_stage=config.get("only_stage"),
            max_cost_per_run=config.get("max_cost"),
            max_hearings=config.get("max_hearings"),
        )
        orchestrator = get_orchestrator(orchestrator_config)
        background_tasks.add_task(orchestrator.run, once=True)

    return {"message": f"Schedule '{schedule.name}' triggered"}


# =============================================================================
# DOCKET DISCOVERY & MATCHING
# =============================================================================

@router.get("/docket-sources")
def get_docket_sources(
    enabled_only: bool = False,
    db: Session = Depends(get_db)
):
    """Get all docket sources (PSC websites for scraping)."""
    from app.models.database import DocketSource

    query = db.query(DocketSource).order_by(DocketSource.state_code)

    if enabled_only:
        query = query.filter(DocketSource.enabled == True)

    sources = query.all()

    return [
        {
            "id": s.id,
            "state_code": s.state_code,
            "state_name": s.state_name,
            "commission_name": s.commission_name,
            "search_url": s.search_url,
            "scraper_type": s.scraper_type,
            "enabled": s.enabled,
            "last_scraped_at": s.last_scraped_at,
            "last_scrape_count": s.last_scrape_count,
            "last_error": s.last_error,
        }
        for s in sources
    ]


@router.post("/docket-sources/{source_id}/toggle")
def toggle_docket_source(
    source_id: int,
    db: Session = Depends(get_db)
):
    """Toggle a docket source enabled/disabled."""
    from app.models.database import DocketSource

    source = db.query(DocketSource).filter(DocketSource.id == source_id).first()
    if not source:
        raise HTTPException(status_code=404, detail="Docket source not found")

    source.enabled = not source.enabled
    db.commit()

    return {"enabled": source.enabled}


@router.patch("/docket-sources/{source_id}")
def update_docket_source(
    source_id: int,
    enabled: Optional[bool] = Query(None),
    scraper_type: Optional[str] = Query(None),
    search_url: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """Update a docket source configuration."""
    from app.models.database import DocketSource

    source = db.query(DocketSource).filter(DocketSource.id == source_id).first()
    if not source:
        raise HTTPException(status_code=404, detail="Docket source not found")

    if enabled is not None:
        source.enabled = enabled
    if scraper_type is not None:
        source.scraper_type = scraper_type
    if search_url is not None:
        source.search_url = search_url

    db.commit()

    return {
        "id": source.id,
        "state_code": source.state_code,
        "enabled": source.enabled,
        "scraper_type": source.scraper_type,
        "search_url": source.search_url,
    }


@router.get("/known-dockets")
def get_known_dockets(
    state: Optional[str] = None,
    sector: Optional[str] = None,
    limit: int = Query(100, le=1000),
    offset: int = 0,
    db: Session = Depends(get_db)
):
    """Get known authoritative dockets."""
    from app.models.database import KnownDocket

    query = db.query(KnownDocket)

    if state:
        query = query.filter(KnownDocket.state_code == state.upper())
    if sector:
        query = query.filter(KnownDocket.sector == sector)

    total = query.count()
    dockets = query.order_by(
        KnownDocket.updated_at.desc()
    ).offset(offset).limit(limit).all()

    return {
        "total": total,
        "dockets": [
            {
                "id": d.id,
                "state_code": d.state_code,
                "docket_number": d.docket_number,
                "normalized_id": d.normalized_id,
                "year": d.year,
                "sector": d.sector,
                "title": d.title,
                "utility_name": d.utility_name,
                "status": d.status,
                "case_type": d.case_type,
                "source_url": d.source_url,
                "scraped_at": d.scraped_at,
            }
            for d in dockets
        ]
    }


@router.get("/data-quality")
def get_data_quality(db: Session = Depends(get_db)):
    """Get docket data quality statistics."""
    from app.models.database import Docket, KnownDocket, DocketSource

    # Docket confidence breakdown
    confidence_counts = dict(
        db.query(Docket.confidence, func.count(Docket.id))
        .group_by(Docket.confidence)
        .all()
    )

    # Known dockets count
    known_count = db.query(KnownDocket).count()

    # Docket sources summary
    total_sources = db.query(DocketSource).count()
    enabled_sources = db.query(DocketSource).filter(
        DocketSource.enabled == True,
        DocketSource.scraper_type.isnot(None)
    ).count()

    return {
        "docket_confidence": {
            "verified": confidence_counts.get("verified", 0),
            "likely": confidence_counts.get("likely", 0),
            "possible": confidence_counts.get("possible", 0),
            "unverified": confidence_counts.get("unverified", 0) + confidence_counts.get(None, 0),
        },
        "known_dockets": known_count,
        "docket_sources": {
            "total": total_sources,
            "enabled": enabled_sources,
        }
    }


@router.post("/docket-discovery/start")
def start_docket_discovery(
    states: Optional[List[str]] = Query(None),
    year: Optional[int] = None,
    limit_per_state: int = Query(1000, le=5000),
    background_tasks: BackgroundTasks = None,
    db: Session = Depends(get_db)
):
    """Start docket discovery for specified states."""
    from app.pipeline.stages.docket_discovery import DocketDiscoveryStage

    stage = DocketDiscoveryStage(db)
    pending = stage.get_pending_count()

    if pending == 0 and not states:
        return {"message": "No docket sources need scraping"}

    # Run in background
    def run_discovery():
        from app.database import SessionLocal
        with SessionLocal() as session:
            discovery = DocketDiscoveryStage(session)
            return discovery.run(
                states=states,
                year=year,
                limit_per_state=limit_per_state
            )

    background_tasks.add_task(run_discovery)

    return {
        "message": "Docket discovery started",
        "states": states or "all enabled",
        "year": year or "current",
    }


# States with individual scraper support (can verify single dockets)
INDIVIDUAL_SCRAPER_STATES = {
    'AZ': 'Arizona',
    'CA': 'California',
    'CO': 'Colorado',
    'CT': 'Connecticut',
    'DE': 'Delaware',
    'FL': 'Florida',
    'GA': 'Georgia',
    'KS': 'Kansas',
    'KY': 'Kentucky',
    'MD': 'Maryland',
    'MI': 'Michigan',
    'MN': 'Minnesota',
    'MO': 'Missouri',
    'NC': 'North Carolina',
    'NJ': 'New Jersey',
    'NY': 'New York',
    'OH': 'Ohio',
    'PA': 'Pennsylvania',
    'SC': 'South Carolina',
    'TX': 'Texas',
    'UT': 'Utah',
    'VA': 'Virginia',
    'WA': 'Washington',
    'WI': 'Wisconsin',
}

# States with batch scraper support (can scrape docket lists)
BATCH_SCRAPER_STATES = {'AZ', 'CA', 'FL', 'GA', 'OH', 'TX'}


@router.get("/docket-discovery/scrapers")
def get_docket_scrapers(db: Session = Depends(get_db)):
    """Get all states with scraper support (batch or individual)."""
    from app.models.database import KnownDocket, DocketSource

    # Get docket counts per state
    docket_counts = dict(
        db.query(KnownDocket.state_code, func.count(KnownDocket.id))
        .group_by(KnownDocket.state_code)
        .all()
    )

    # Get last scraped times from DocketSource
    sources = {
        s.state_code: s
        for s in db.query(DocketSource).all()
    }

    # Build unified list of all states with scraper support
    all_states = set(INDIVIDUAL_SCRAPER_STATES.keys()) | BATCH_SCRAPER_STATES

    result = []
    for state_code in sorted(all_states):
        source = sources.get(state_code)
        result.append({
            "state_code": state_code,
            "state_name": INDIVIDUAL_SCRAPER_STATES.get(state_code, source.state_name if source else state_code),
            "has_batch": state_code in BATCH_SCRAPER_STATES,
            "has_individual": state_code in INDIVIDUAL_SCRAPER_STATES,
            "last_scraped": source.last_scraped_at.isoformat() if source and source.last_scraped_at else None,
            "docket_count": docket_counts.get(state_code, 0),
            "enabled": source.enabled if source else False,
        })

    return result


@router.get("/docket-discovery/stats")
def get_docket_discovery_stats(db: Session = Depends(get_db)):
    """Get stats for the Docket Discovery stage."""
    from app.models.database import KnownDocket, DocketSource
    from datetime import timedelta

    # Count known dockets
    known_count = db.query(KnownDocket).count()

    # Count enabled sources
    sources_enabled = db.query(DocketSource).filter(
        DocketSource.enabled == True,
        DocketSource.scraper_type.isnot(None)
    ).count()

    # Count sources due for scraping (not scraped in 7 days)
    cutoff = datetime.utcnow() - timedelta(days=7)
    sources_due = db.query(DocketSource).filter(
        DocketSource.enabled == True,
        DocketSource.scraper_type.isnot(None),
        (DocketSource.last_scraped_at == None) | (DocketSource.last_scraped_at < cutoff)
    ).count()

    # Get most recent scrape time
    latest_source = db.query(DocketSource).filter(
        DocketSource.last_scraped_at.isnot(None)
    ).order_by(DocketSource.last_scraped_at.desc()).first()

    return {
        "known_dockets_count": known_count,
        "sources_enabled": sources_enabled,
        "sources_due": sources_due,
        "last_discovery_run": latest_source.last_scraped_at.isoformat() if latest_source else None,
        "batch_states": len(BATCH_SCRAPER_STATES),
        "individual_states": len(INDIVIDUAL_SCRAPER_STATES),
    }


@router.post("/docket-discovery/verify-single")
async def verify_single_docket(
    state_code: str = Query(..., description="Two-letter state code"),
    docket_number: str = Query(..., description="Docket number to verify"),
    save: bool = Query(True, description="Save verified docket to known_dockets"),
    db: Session = Depends(get_db)
):
    """Verify and optionally save a single docket from a PSC website."""
    state_code = state_code.upper()

    if state_code not in INDIVIDUAL_SCRAPER_STATES:
        raise HTTPException(
            status_code=400,
            detail=f"No individual scraper available for {state_code}. Available: {', '.join(sorted(INDIVIDUAL_SCRAPER_STATES.keys()))}"
        )

    from app.services.docket_scraper import DocketScraper

    scraper = DocketScraper(db)

    if save:
        result = await scraper.verify_and_save(state_code, docket_number)
    else:
        result = await scraper.scrape_docket(state_code, docket_number)

    return {
        "found": result.found,
        "docket_number": result.docket_number,
        "state_code": state_code,
        "title": result.title,
        "company": result.company,
        "filing_date": result.filing_date,
        "status": result.status,
        "utility_type": result.utility_type,
        "docket_type": result.docket_type,
        "source_url": result.source_url,
        "error": result.error,
        "saved": save and result.found,
    }


@router.get("/extended-status")
def get_extended_pipeline_status(db: Session = Depends(get_db)):
    """Get extended pipeline status including docket discovery."""
    from app.models.database import DocketSource, KnownDocket, Docket, Source
    from datetime import timedelta

    # Get pipeline state
    state = db.query(PipelineState).filter(PipelineState.id == 1).first()
    pipeline_status = state.status if state else "idle"

    # Discovery stats
    docket_sources = db.query(DocketSource).filter(
        DocketSource.enabled == True,
        DocketSource.scraper_type.isnot(None)
    ).count()

    cutoff = datetime.utcnow() - timedelta(days=7)
    docket_sources_pending = db.query(DocketSource).filter(
        DocketSource.enabled == True,
        DocketSource.scraper_type.isnot(None),
        (DocketSource.last_scraped_at == None) | (DocketSource.last_scraped_at < cutoff)
    ).count()

    hearing_sources = db.query(Source).filter(Source.enabled == True).count()
    known_dockets = db.query(KnownDocket).count()

    # Processing stats
    status_counts = dict(
        db.query(Hearing.status, func.count(Hearing.id))
        .group_by(Hearing.status)
        .all()
    )

    # Data quality
    confidence_counts = dict(
        db.query(Docket.confidence, func.count(Docket.id))
        .group_by(Docket.confidence)
        .all()
    )

    # Today's stats
    since = datetime.utcnow() - timedelta(hours=24)
    today_jobs = db.query(PipelineJob).filter(
        PipelineJob.completed_at >= since
    ).all()

    completed_jobs = [j for j in today_jobs if j.status == "complete"]
    error_jobs = [j for j in today_jobs if j.status == "error"]

    return {
        "pipeline_status": pipeline_status,
        "discovery": {
            "docket_sources": docket_sources,
            "docket_sources_pending": docket_sources_pending,
            "hearing_sources": hearing_sources,
            "known_dockets": known_dockets,
        },
        "processing": {
            "download_pending": status_counts.get("discovered", 0),
            "transcribe_pending": status_counts.get("downloaded", 0),
            "analyze_pending": status_counts.get("transcribed", 0),
            "extract_pending": status_counts.get("analyzed", 0),
            "complete": status_counts.get("complete", 0) + status_counts.get("extracted", 0) + status_counts.get("matched", 0),
        },
        "data_quality": {
            "verified": confidence_counts.get("verified", 0),
            "likely": confidence_counts.get("likely", 0),
            "possible": confidence_counts.get("possible", 0),
            "unverified": confidence_counts.get("unverified", 0) + confidence_counts.get(None, 0),
        },
        "today": {
            "processed": len(set(j.hearing_id for j in completed_jobs)),
            "cost": sum(float(j.cost_usd or 0) for j in completed_jobs),
            "errors": len(error_jobs),
        }
    }
