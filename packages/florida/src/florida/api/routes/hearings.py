"""
Florida Hearing API routes.

Provides endpoints for hearing transcripts and segments.
"""

from datetime import date
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from pydantic import BaseModel

from florida.models import get_db, FLHearing, FLTranscriptSegment

router = APIRouter(prefix="/hearings", tags=["hearings"])


class SegmentResponse(BaseModel):
    """Transcript segment response model."""
    id: int
    segment_index: Optional[int] = None
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    speaker_label: Optional[str] = None
    speaker_name: Optional[str] = None
    speaker_role: Optional[str] = None
    text: str
    confidence: Optional[float] = None
    timestamp_display: str

    class Config:
        from_attributes = True


class HearingResponse(BaseModel):
    """Hearing response model."""
    id: int
    docket_number: Optional[str] = None
    hearing_date: date
    hearing_type: Optional[str] = None
    location: Optional[str] = None
    title: Optional[str] = None
    transcript_url: Optional[str] = None
    transcript_status: Optional[str] = None
    source_type: Optional[str] = None
    source_url: Optional[str] = None
    external_id: Optional[str] = None
    duration_seconds: Optional[int] = None
    duration_minutes: Optional[int] = None
    word_count: Optional[int] = None
    youtube_url: Optional[str] = None

    class Config:
        from_attributes = True


class HearingDetailResponse(HearingResponse):
    """Hearing with segments."""
    segments: List[SegmentResponse] = []


class HearingListResponse(BaseModel):
    """Paginated hearing list response."""
    items: List[HearingResponse]
    total: int
    page: int
    per_page: int
    pages: int


class HearingStats(BaseModel):
    """Hearing statistics."""
    total: int
    transcribed: int
    pending: int
    by_type: dict
    by_source: dict


@router.get("", response_model=HearingListResponse)
def list_hearings(
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    docket: Optional[str] = None,
    hearing_type: Optional[str] = None,
    status: Optional[str] = None,
    year: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """
    List hearings with pagination and filtering.

    Query parameters:
    - page: Page number (1-indexed)
    - per_page: Results per page (max 200)
    - docket: Filter by docket number
    - hearing_type: Filter by hearing type
    - status: Filter by transcript status
    - year: Filter by year
    """
    query = db.query(FLHearing)

    if docket:
        query = query.filter(FLHearing.docket_number == docket)
    if hearing_type:
        query = query.filter(FLHearing.hearing_type.ilike(f"%{hearing_type}%"))
    if status:
        query = query.filter(FLHearing.transcript_status == status)
    if year:
        query = query.filter(func.extract('year', FLHearing.hearing_date) == year)

    total = query.count()
    pages = (total + per_page - 1) // per_page

    hearings = query.order_by(FLHearing.hearing_date.desc()).offset(
        (page - 1) * per_page
    ).limit(per_page).all()

    return HearingListResponse(
        items=[HearingResponse.model_validate(h) for h in hearings],
        total=total,
        page=page,
        per_page=per_page,
        pages=pages,
    )


@router.get("/stats", response_model=HearingStats)
def get_hearing_stats(db: Session = Depends(get_db)):
    """Get hearing statistics."""
    total = db.query(func.count(FLHearing.id)).scalar() or 0
    transcribed = db.query(func.count(FLHearing.id)).filter(
        FLHearing.transcript_status.in_(['transcribed', 'analyzed'])
    ).scalar() or 0
    pending = db.query(func.count(FLHearing.id)).filter(
        FLHearing.transcript_status == 'pending'
    ).scalar() or 0

    # By type
    by_type = {}
    type_counts = db.query(
        FLHearing.hearing_type,
        func.count(FLHearing.id)
    ).group_by(FLHearing.hearing_type).all()
    for htype, count in type_counts:
        if htype:
            by_type[htype] = count

    # By source
    by_source = {}
    source_counts = db.query(
        FLHearing.source_type,
        func.count(FLHearing.id)
    ).group_by(FLHearing.source_type).all()
    for source, count in source_counts:
        if source:
            by_source[source] = count

    return HearingStats(
        total=total,
        transcribed=transcribed,
        pending=pending,
        by_type=by_type,
        by_source=by_source,
    )


@router.get("/by-docket/{docket_number}", response_model=List[HearingResponse])
def get_hearings_by_docket(
    docket_number: str,
    db: Session = Depends(get_db)
):
    """Get all hearings for a specific docket."""
    hearings = db.query(FLHearing).filter(
        FLHearing.docket_number == docket_number
    ).order_by(FLHearing.hearing_date.desc()).all()

    return [HearingResponse.model_validate(h) for h in hearings]


@router.get("/{hearing_id}", response_model=HearingDetailResponse)
def get_hearing(hearing_id: int, db: Session = Depends(get_db)):
    """Get a specific hearing with transcript segments."""
    hearing = db.query(FLHearing).filter(
        FLHearing.id == hearing_id
    ).first()

    if not hearing:
        raise HTTPException(status_code=404, detail="Hearing not found")

    # Get segments
    segments = db.query(FLTranscriptSegment).filter(
        FLTranscriptSegment.hearing_id == hearing_id
    ).order_by(FLTranscriptSegment.segment_index).all()

    response = HearingDetailResponse.model_validate(hearing)
    response.segments = [SegmentResponse.model_validate(s) for s in segments]

    return response


@router.get("/{hearing_id}/segments", response_model=List[SegmentResponse])
def get_hearing_segments(
    hearing_id: int,
    speaker: Optional[str] = None,
    role: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    Get transcript segments for a hearing.

    Optionally filter by speaker name or role.
    """
    query = db.query(FLTranscriptSegment).filter(
        FLTranscriptSegment.hearing_id == hearing_id
    )

    if speaker:
        query = query.filter(FLTranscriptSegment.speaker_name.ilike(f"%{speaker}%"))
    if role:
        query = query.filter(FLTranscriptSegment.speaker_role.ilike(f"%{role}%"))

    segments = query.order_by(FLTranscriptSegment.segment_index).all()

    return [SegmentResponse.model_validate(s) for s in segments]
