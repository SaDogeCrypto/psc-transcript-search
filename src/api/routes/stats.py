"""
Stats API routes.
"""

from datetime import datetime, timedelta
from typing import Dict, List, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, and_
from sqlalchemy.orm import Session

from src.api.dependencies import get_db
from src.core.models.hearing import Hearing
from src.core.models.docket import Docket
from src.core.models.transcript import TranscriptSegment
from src.core.models.analysis import Analysis
from src.states.registry import StateRegistry

router = APIRouter()


class StatsResponse(BaseModel):
    """Dashboard statistics."""
    total_states: int
    total_hearings: int
    total_segments: int
    total_hours: float
    hearings_by_status: Dict[str, int]
    hearings_by_state: Dict[str, int]
    total_transcription_cost: float
    total_analysis_cost: float
    total_cost: float
    hearings_last_24h: int
    hearings_last_7d: int


class UtilityCount(BaseModel):
    """Utility with hearing count."""
    utility_name: str
    count: int


class HearingTypeCount(BaseModel):
    """Hearing type with count."""
    hearing_type: str
    count: int


@router.get("", response_model=StatsResponse)
def get_stats(db: Session = Depends(get_db)):
    """
    Get dashboard statistics.
    """
    now = datetime.utcnow()
    last_24h = now - timedelta(hours=24)
    last_7d = now - timedelta(days=7)

    # Total counts
    total_hearings = db.query(func.count(Hearing.id)).scalar() or 0
    total_segments = db.query(func.count(TranscriptSegment.id)).scalar() or 0

    # Total hours from duration
    total_seconds = db.query(func.sum(Hearing.duration_seconds)).scalar() or 0
    total_hours = total_seconds / 3600

    # Hearings by status
    status_counts = dict(
        db.query(
            Hearing.transcript_status,
            func.count(Hearing.id)
        ).group_by(Hearing.transcript_status).all()
    )
    hearings_by_status = {k or "unknown": v for k, v in status_counts.items()}

    # Hearings by state
    state_counts = dict(
        db.query(
            Hearing.state_code,
            func.count(Hearing.id)
        ).group_by(Hearing.state_code).all()
    )
    hearings_by_state = {k or "unknown": v for k, v in state_counts.items()}

    # Costs from hearings
    transcription_cost = db.query(
        func.sum(Hearing.processing_cost_usd)
    ).scalar() or 0.0

    # Costs from analyses
    analysis_cost = db.query(
        func.sum(Analysis.cost_usd)
    ).scalar() or 0.0

    # Recent hearings
    hearings_last_24h = db.query(func.count(Hearing.id)).filter(
        Hearing.created_at >= last_24h
    ).scalar() or 0

    hearings_last_7d = db.query(func.count(Hearing.id)).filter(
        Hearing.created_at >= last_7d
    ).scalar() or 0

    return StatsResponse(
        total_states=len(StateRegistry.get_available_states()),
        total_hearings=total_hearings,
        total_segments=total_segments,
        total_hours=round(total_hours, 1),
        hearings_by_status=hearings_by_status,
        hearings_by_state=hearings_by_state,
        total_transcription_cost=float(transcription_cost),
        total_analysis_cost=float(analysis_cost),
        total_cost=float(transcription_cost) + float(analysis_cost),
        hearings_last_24h=hearings_last_24h,
        hearings_last_7d=hearings_last_7d,
    )


@router.get("/utilities", response_model=List[UtilityCount])
def get_utilities(db: Session = Depends(get_db)):
    """
    Get list of utilities with hearing counts.
    """
    results = db.query(
        Analysis.utility_name,
        func.count(Analysis.id).label('count')
    ).filter(
        Analysis.utility_name.isnot(None),
        Analysis.utility_name != ''
    ).group_by(
        Analysis.utility_name
    ).order_by(
        func.count(Analysis.id).desc()
    ).limit(100).all()

    return [
        UtilityCount(utility_name=r.utility_name, count=r.count)
        for r in results
    ]


@router.get("/hearing-types", response_model=List[HearingTypeCount])
def get_hearing_types(db: Session = Depends(get_db)):
    """
    Get list of hearing types with counts.
    """
    results = db.query(
        Hearing.hearing_type,
        func.count(Hearing.id).label('count')
    ).filter(
        Hearing.hearing_type.isnot(None),
        Hearing.hearing_type != ''
    ).group_by(
        Hearing.hearing_type
    ).order_by(
        func.count(Hearing.id).desc()
    ).all()

    return [
        HearingTypeCount(hearing_type=r.hearing_type, count=r.count)
        for r in results
    ]
