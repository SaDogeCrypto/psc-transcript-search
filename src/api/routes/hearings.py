"""
Hearing API routes.
"""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload

from src.api.dependencies import get_db
from src.api.schemas.hearing import (
    HearingResponse,
    HearingListResponse,
    HearingDetail,
    TranscriptSegmentResponse,
    AnalysisResponse,
)
from src.core.models.hearing import Hearing
from src.core.models.transcript import TranscriptSegment
from src.core.models.analysis import Analysis

router = APIRouter()


@router.get("", response_model=HearingListResponse)
def list_hearings(
    state_code: Optional[str] = Query(None, description="Filter by state"),
    status: Optional[str] = Query(None, description="Filter by transcript_status"),
    docket_number: Optional[str] = Query(None, description="Filter by docket number"),
    hearing_type: Optional[str] = Query(None, description="Filter by hearing type"),
    utility: Optional[str] = Query(None, description="Filter by utility name (from analysis)"),
    sector: Optional[str] = Query(None, description="Filter by sector (from analysis)"),
    has_transcript: Optional[bool] = Query(None, description="Filter by whether transcript exists"),
    has_analysis: Optional[bool] = Query(None, description="Filter by whether analysis exists"),
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """
    List hearings with optional filters.

    Supports filtering by state, status, docket, type, and analysis fields.
    """
    query = db.query(Hearing).options(
        joinedload(Hearing.analysis)
    )

    # Apply filters
    if state_code:
        query = query.filter(Hearing.state_code == state_code.upper())
    if status:
        query = query.filter(Hearing.transcript_status == status)
    if docket_number:
        query = query.filter(Hearing.docket_number.ilike(f"%{docket_number}%"))
    if hearing_type:
        query = query.filter(Hearing.hearing_type.ilike(f"%{hearing_type}%"))
    if has_transcript is True:
        query = query.filter(Hearing.full_text.isnot(None))
    if has_transcript is False:
        query = query.filter(Hearing.full_text.is_(None))

    # Analysis-based filters require join
    if utility or sector or has_analysis is not None:
        if has_analysis is True:
            query = query.join(Analysis)
        elif has_analysis is False:
            query = query.outerjoin(Analysis).filter(Analysis.id.is_(None))
        else:
            query = query.outerjoin(Analysis)

        if utility:
            query = query.filter(Analysis.utility_name.ilike(f"%{utility}%"))
        if sector:
            query = query.filter(Analysis.sector == sector)

    # Get total count
    total = query.count()

    # Get paginated results
    hearings = query.order_by(
        Hearing.hearing_date.desc().nullslast()
    ).offset(offset).limit(limit).all()

    # Build response
    items = []
    for h in hearings:
        item_data = {
            "id": h.id,
            "state_code": h.state_code,
            "docket_id": h.docket_id,
            "docket_number": h.docket_number,
            "title": h.title,
            "hearing_type": h.hearing_type,
            "hearing_date": h.hearing_date,
            "duration_seconds": h.duration_seconds,
            "transcript_status": h.transcript_status,
            "video_url": h.video_url,
        }

        if h.analysis:
            item_data["one_sentence_summary"] = h.analysis.one_sentence_summary
            item_data["utility_name"] = h.analysis.utility_name
            item_data["sector"] = h.analysis.sector

        items.append(HearingResponse(**item_data))

    return HearingListResponse(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{hearing_id}", response_model=HearingDetail)
def get_hearing(
    hearing_id: UUID,
    include_transcript: bool = Query(True, description="Include full transcript text"),
    include_segments: bool = Query(False, description="Include transcript segments"),
    include_analysis: bool = Query(True, description="Include analysis"),
    db: Session = Depends(get_db),
):
    """
    Get hearing by ID with full details.

    Optionally includes transcript text, segments, and analysis.
    """
    hearing = db.query(Hearing).filter(Hearing.id == hearing_id).first()

    if not hearing:
        raise HTTPException(status_code=404, detail="Hearing not found")

    response_data = {
        "id": hearing.id,
        "state_code": hearing.state_code,
        "docket_id": hearing.docket_id,
        "docket_number": hearing.docket_number,
        "title": hearing.title,
        "hearing_type": hearing.hearing_type,
        "hearing_date": hearing.hearing_date,
        "scheduled_time": hearing.scheduled_time,
        "location": hearing.location,
        "video_url": hearing.video_url,
        "audio_url": hearing.audio_url,
        "duration_seconds": hearing.duration_seconds,
        "duration_minutes": hearing.duration_minutes,
        "word_count": hearing.word_count,
        "transcript_status": hearing.transcript_status,
        "whisper_model": hearing.whisper_model,
        "processing_cost_usd": float(hearing.processing_cost_usd) if hearing.processing_cost_usd else None,
        "processed_at": hearing.processed_at,
    }

    # Include transcript text
    if include_transcript:
        response_data["full_text"] = hearing.full_text

    # Include segments
    if include_segments:
        segments = db.query(TranscriptSegment).filter(
            TranscriptSegment.hearing_id == hearing_id
        ).order_by(TranscriptSegment.segment_index).all()

        response_data["segments"] = [
            TranscriptSegmentResponse(
                id=s.id,
                segment_index=s.segment_index,
                start_time=s.start_time,
                end_time=s.end_time,
                text=s.text,
                speaker_label=s.speaker_label,
                speaker_name=s.speaker_name,
                speaker_role=s.speaker_role,
                timestamp_display=s.timestamp_display,
            )
            for s in segments
        ]

    # Include analysis
    if include_analysis and hearing.analysis:
        a = hearing.analysis
        response_data["analysis"] = AnalysisResponse(
            id=a.id,
            summary=a.summary,
            one_sentence_summary=a.one_sentence_summary,
            hearing_type=a.hearing_type,
            utility_name=a.utility_name,
            sector=a.sector,
            participants=a.participants_json,
            issues=a.issues_json,
            topics=a.topics_extracted,
            commitments=a.commitments_json,
            vulnerabilities=a.vulnerabilities_json,
            commissioner_concerns=a.commissioner_concerns_json,
            risk_factors=a.risk_factors_json,
            action_items=a.action_items_json,
            quotes=a.quotes_json,
            commissioner_mood=a.commissioner_mood,
            public_comments=a.public_comments,
            public_sentiment=a.public_sentiment,
            likely_outcome=a.likely_outcome,
            outcome_confidence=a.outcome_confidence,
            model=a.model,
            cost_usd=float(a.cost_usd) if a.cost_usd else None,
        )

    # Add Florida-specific fields
    if hasattr(hearing, 'fl_details') and hearing.fl_details:
        fl = hearing.fl_details
        response_data["youtube_video_id"] = fl.youtube_video_id
        response_data["youtube_url"] = fl.youtube_url

    return HearingDetail(**response_data)


@router.get("/{hearing_id}/segments")
def get_hearing_segments(
    hearing_id: UUID,
    speaker: Optional[str] = Query(None, description="Filter by speaker name"),
    search: Optional[str] = Query(None, description="Search in segment text"),
    limit: int = Query(100, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """
    Get transcript segments for a hearing.

    Supports filtering by speaker and text search.
    """
    # Verify hearing exists
    hearing = db.query(Hearing).filter(Hearing.id == hearing_id).first()
    if not hearing:
        raise HTTPException(status_code=404, detail="Hearing not found")

    query = db.query(TranscriptSegment).filter(
        TranscriptSegment.hearing_id == hearing_id
    )

    if speaker:
        query = query.filter(
            (TranscriptSegment.speaker_name.ilike(f"%{speaker}%")) |
            (TranscriptSegment.speaker_label.ilike(f"%{speaker}%"))
        )
    if search:
        query = query.filter(TranscriptSegment.text.ilike(f"%{search}%"))

    total = query.count()

    segments = query.order_by(
        TranscriptSegment.segment_index
    ).offset(offset).limit(limit).all()

    return {
        "items": [
            TranscriptSegmentResponse(
                id=s.id,
                segment_index=s.segment_index,
                start_time=s.start_time,
                end_time=s.end_time,
                text=s.text,
                speaker_label=s.speaker_label,
                speaker_name=s.speaker_name,
                speaker_role=s.speaker_role,
                timestamp_display=s.timestamp_display,
            )
            for s in segments
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/{hearing_id}/analysis", response_model=AnalysisResponse)
def get_hearing_analysis(
    hearing_id: UUID,
    db: Session = Depends(get_db),
):
    """
    Get analysis for a hearing.
    """
    analysis = db.query(Analysis).filter(Analysis.hearing_id == hearing_id).first()

    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found for this hearing")

    return AnalysisResponse(
        id=analysis.id,
        summary=analysis.summary,
        one_sentence_summary=analysis.one_sentence_summary,
        hearing_type=analysis.hearing_type,
        utility_name=analysis.utility_name,
        sector=analysis.sector,
        participants=analysis.participants_json,
        issues=analysis.issues_json,
        topics=analysis.topics_extracted,
        commitments=analysis.commitments_json,
        vulnerabilities=analysis.vulnerabilities_json,
        commissioner_concerns=analysis.commissioner_concerns_json,
        risk_factors=analysis.risk_factors_json,
        action_items=analysis.action_items_json,
        quotes=analysis.quotes_json,
        commissioner_mood=analysis.commissioner_mood,
        public_comments=analysis.public_comments,
        public_sentiment=analysis.public_sentiment,
        likely_outcome=analysis.likely_outcome,
        outcome_confidence=analysis.outcome_confidence,
        model=analysis.model,
        cost_usd=float(analysis.cost_usd) if analysis.cost_usd else None,
    )


@router.get("/statuses")
def get_hearing_statuses(
    state_code: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """
    Get hearing counts by transcript_status.
    """
    from sqlalchemy import func

    query = db.query(
        Hearing.transcript_status,
        func.count(Hearing.id).label('count')
    )

    if state_code:
        query = query.filter(Hearing.state_code == state_code.upper())

    results = query.group_by(Hearing.transcript_status).all()

    return [
        {"status": r.transcript_status or "unknown", "count": r.count}
        for r in results
    ]
