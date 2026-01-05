"""
Pipeline Control API Endpoints

Provides endpoints for:
- Pipeline status and control (start/stop/pause/resume)
- Activity and error monitoring
- Hearing retry/skip operations
- Schedule CRUD operations
"""

from datetime import datetime, timezone
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

    # Get hearing counts by status
    status_counts = dict(
        db.query(Hearing.status, func.count(Hearing.id))
        .group_by(Hearing.status)
        .all()
    )

    # Get today's stats
    today = datetime.now(timezone.utc).date()
    today_jobs = db.query(PipelineJob).filter(
        func.date(PipelineJob.completed_at) == today
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

    # Reset hearing status
    hearing.status = "discovered"

    # Reset retry counts on failed jobs
    for job in hearing.pipeline_jobs:
        if job.status == "error":
            job.retry_count = 0

    db.commit()

    return {"message": f"Hearing {hearing_id} queued for retry"}


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
