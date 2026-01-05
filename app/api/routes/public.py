"""
Public API routes for customer-facing dashboard.
"""
from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, or_, desc, asc

from app.database import get_db
from app.models.database import (
    State, Source, Hearing, PipelineJob,
    Transcript, Analysis, Segment, Docket, HearingDocket, UserWatchlist
)
from app.models.schemas import (
    StateResponse, HearingListItem, HearingDetail,
    SearchResult, SearchResponse, StatsResponse,
    SegmentResponse, TranscriptResponse,
    DocketListItem, DocketDetail, DocketHearingItem, DocketSearchResponse,
    WatchlistDocket, WatchlistAddRequest, WatchlistResponse, LatestMention,
    ActivityItem, ActivityFeedResponse, DocketMention,
    TimelineItem, DocketWithTimeline
)

router = APIRouter(prefix="/api", tags=["public"])


# ============================================================================
# STATES
# ============================================================================

@router.get("/states", response_model=List[StateResponse])
def list_states(db: Session = Depends(get_db)):
    """Get all states with hearing counts."""
    try:
        results = db.query(
            State,
            func.count(Hearing.id).label("hearing_count")
        ).outerjoin(Hearing).group_by(State.id).order_by(State.name).all()

        return [
            StateResponse(
                id=r.State.id,
                code=r.State.code,
                name=r.State.name,
                commission_name=r.State.commission_name,
                hearing_count=r.hearing_count
            )
            for r in results
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")


@router.get("/states/{state_code}", response_model=StateResponse)
def get_state(state_code: str, db: Session = Depends(get_db)):
    """Get a single state by code."""
    result = db.query(
        State,
        func.count(Hearing.id).label("hearing_count")
    ).outerjoin(Hearing).filter(
        State.code == state_code.upper()
    ).group_by(State.id).first()

    if not result:
        raise HTTPException(status_code=404, detail="State not found")

    return StateResponse(
        id=result.State.id,
        code=result.State.code,
        name=result.State.name,
        commission_name=result.State.commission_name,
        hearing_count=result.hearing_count
    )


# ============================================================================
# HEARINGS
# ============================================================================

@router.get("/hearings", response_model=List[HearingListItem])
def list_hearings(
    states: Optional[str] = Query(None, description="Comma-separated state codes"),
    utilities: Optional[str] = Query(None, description="Comma-separated utility names"),
    hearing_types: Optional[str] = Query(None, description="Comma-separated hearing types"),
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    status: Optional[str] = Query(None, description="Filter by status (complete recommended for public)"),
    search_query: Optional[str] = Query(None, description="Search in title"),
    page: int = 1,
    page_size: int = 20,
    sort_by: str = Query("hearing_date", description="Sort field"),
    sort_order: str = Query("desc", description="Sort order (asc/desc)"),
    db: Session = Depends(get_db)
):
    """List hearings with filters and pagination."""
    query = db.query(
        Hearing,
        State.code.label("state_code"),
        State.name.label("state_name")
    ).join(State, Hearing.state_id == State.id)

    # By default, only show completed hearings to public
    if status:
        query = query.filter(Hearing.status == status)
    else:
        query = query.filter(Hearing.status == "complete")

    # Apply filters
    if states:
        state_list = [s.strip().upper() for s in states.split(",")]
        query = query.filter(State.code.in_(state_list))

    if utilities:
        utility_list = [u.strip() for u in utilities.split(",")]
        query = query.filter(Hearing.utility_name.in_(utility_list))

    if hearing_types:
        type_list = [t.strip() for t in hearing_types.split(",")]
        query = query.filter(Hearing.hearing_type.in_(type_list))

    if date_from:
        query = query.filter(Hearing.hearing_date >= date_from)

    if date_to:
        query = query.filter(Hearing.hearing_date <= date_to)

    if search_query:
        query = query.filter(Hearing.title.ilike(f"%{search_query}%"))

    # Sorting
    sort_column = getattr(Hearing, sort_by, Hearing.hearing_date)
    if sort_order.lower() == "desc":
        query = query.order_by(desc(sort_column))
    else:
        query = query.order_by(asc(sort_column))

    # Pagination
    offset = (page - 1) * page_size
    results = query.offset(offset).limit(page_size).all()

    return [
        HearingListItem(
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
            pipeline_status="complete"
        )
        for r in results
    ]


@router.get("/hearings/{hearing_id}", response_model=HearingDetail)
def get_hearing(hearing_id: int, db: Session = Depends(get_db)):
    """Get detailed hearing information including analysis."""
    result = db.query(
        Hearing,
        State.code.label("state_code"),
        State.name.label("state_name"),
        Source.name.label("source_name")
    ).join(
        State, Hearing.state_id == State.id
    ).outerjoin(
        Source, Hearing.source_id == Source.id
    ).filter(Hearing.id == hearing_id).first()

    if not result:
        raise HTTPException(status_code=404, detail="Hearing not found")

    hearing = result.Hearing

    # Get analysis if exists
    analysis = db.query(Analysis).filter(Analysis.hearing_id == hearing_id).first()

    # Get segment stats
    segment_stats = db.query(
        func.count(Segment.id).label("segment_count"),
        func.sum(func.length(Segment.text)).label("total_chars")
    ).join(Transcript).filter(Transcript.hearing_id == hearing_id).first()

    segment_count = segment_stats.segment_count if segment_stats else 0
    # Rough word count estimate
    word_count = int((segment_stats.total_chars or 0) / 5) if segment_stats else 0

    return HearingDetail(
        id=hearing.id,
        state_code=result.state_code,
        state_name=result.state_name,
        title=hearing.title,
        hearing_date=hearing.hearing_date,
        hearing_type=hearing.hearing_type,
        utility_name=hearing.utility_name,
        duration_seconds=hearing.duration_seconds,
        status=hearing.status,
        source_url=hearing.source_url,
        created_at=hearing.created_at,
        pipeline_status="complete" if hearing.status == "complete" else hearing.status,
        description=hearing.description,
        docket_numbers=hearing.docket_numbers,
        video_url=hearing.video_url,
        source_name=result.source_name,
        # Analysis fields
        summary=analysis.summary if analysis else None,
        one_sentence_summary=analysis.one_sentence_summary if analysis else None,
        participants=analysis.participants if analysis else None,
        issues=analysis.issues if analysis else None,
        commitments=analysis.commitments if analysis else None,
        commissioner_concerns=analysis.commissioner_concerns if analysis else None,
        commissioner_mood=analysis.commissioner_mood if analysis else None,
        likely_outcome=analysis.likely_outcome if analysis else None,
        outcome_confidence=float(analysis.outcome_confidence) if analysis and analysis.outcome_confidence else None,
        risk_factors=analysis.risk_factors if analysis else None,
        quotes=analysis.quotes if analysis else None,
        segment_count=segment_count,
        word_count=word_count
    )


@router.get("/hearings/{hearing_id}/transcript", response_model=TranscriptResponse)
def get_transcript(
    hearing_id: int,
    page: int = 1,
    page_size: int = 100,
    db: Session = Depends(get_db)
):
    """Get transcript segments for a hearing."""
    hearing = db.query(Hearing).filter(Hearing.id == hearing_id).first()
    if not hearing:
        raise HTTPException(status_code=404, detail="Hearing not found")

    transcript = db.query(Transcript).filter(Transcript.hearing_id == hearing_id).first()
    if not transcript:
        raise HTTPException(status_code=404, detail="Transcript not found")

    # Get segments with pagination
    offset = (page - 1) * page_size
    segments = db.query(Segment).filter(
        Segment.transcript_id == transcript.id
    ).order_by(Segment.segment_index).offset(offset).limit(page_size).all()

    return TranscriptResponse(
        hearing_id=hearing_id,
        hearing_title=hearing.title,
        word_count=transcript.word_count,
        segments=[
            SegmentResponse(
                id=s.id,
                segment_index=s.segment_index,
                start_time=float(s.start_time),
                end_time=float(s.end_time),
                text=s.text,
                speaker=s.speaker,
                speaker_role=s.speaker_role
            )
            for s in segments
        ]
    )


# ============================================================================
# SEARCH
# ============================================================================

@router.get("/search", response_model=SearchResponse)
def search_transcripts(
    q: str = Query(..., min_length=2, description="Search query"),
    states: Optional[str] = Query(None, description="Comma-separated state codes"),
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
    db: Session = Depends(get_db)
):
    """Full-text search across all transcripts."""
    # Build base query
    query = db.query(
        Segment,
        Transcript.hearing_id,
        Hearing.title.label("hearing_title"),
        Hearing.source_url,
        Hearing.video_url,
        State.code.label("state_code"),
        State.name.label("state_name")
    ).join(
        Transcript, Segment.transcript_id == Transcript.id
    ).join(
        Hearing, Transcript.hearing_id == Hearing.id
    ).join(
        State, Hearing.state_id == State.id
    )

    # Only search completed hearings
    query = query.filter(Hearing.status == "complete")

    # Text search - using ILIKE for basic search
    # In production, use PostgreSQL full-text search with ts_vector
    search_pattern = f"%{q}%"
    query = query.filter(Segment.text.ilike(search_pattern))

    # Apply filters
    if states:
        state_list = [s.strip().upper() for s in states.split(",")]
        query = query.filter(State.code.in_(state_list))

    if date_from:
        query = query.filter(Hearing.hearing_date >= date_from)

    if date_to:
        query = query.filter(Hearing.hearing_date <= date_to)

    # Get total count
    total_count = query.count()

    # Pagination
    offset = (page - 1) * page_size
    results = query.order_by(Hearing.hearing_date.desc()).offset(offset).limit(page_size).all()

    def create_snippet(text: str, query: str, context_chars: int = 100) -> str:
        """Create a highlighted snippet around the match."""
        query_lower = query.lower()
        text_lower = text.lower()
        pos = text_lower.find(query_lower)
        if pos == -1:
            return text[:200] + "..." if len(text) > 200 else text

        start = max(0, pos - context_chars)
        end = min(len(text), pos + len(query) + context_chars)

        snippet = ""
        if start > 0:
            snippet = "..."
        snippet += text[start:pos]
        snippet += f"**{text[pos:pos + len(query)]}**"  # Highlight match
        snippet += text[pos + len(query):end]
        if end < len(text):
            snippet += "..."

        return snippet

    def create_timestamp_url(video_url: Optional[str], start_time: float) -> Optional[str]:
        """Create URL with timestamp for video."""
        if not video_url:
            return None
        if "youtube.com" in video_url or "youtu.be" in video_url:
            separator = "&" if "?" in video_url else "?"
            return f"{video_url}{separator}t={int(start_time)}"
        return video_url

    search_results = [
        SearchResult(
            segment_id=r.Segment.id,
            hearing_id=r.hearing_id,
            hearing_title=r.hearing_title,
            state_code=r.state_code,
            state_name=r.state_name,
            text=r.Segment.text,
            start_time=float(r.Segment.start_time),
            end_time=float(r.Segment.end_time),
            speaker=r.Segment.speaker,
            speaker_role=r.Segment.speaker_role,
            source_url=r.source_url,
            video_url=r.video_url,
            timestamp_url=create_timestamp_url(r.video_url, float(r.Segment.start_time)),
            snippet=create_snippet(r.Segment.text, q)
        )
        for r in results
    ]

    return SearchResponse(
        query=q,
        results=search_results,
        total_count=total_count,
        page=page,
        page_size=page_size
    )


# ============================================================================
# STATS
# ============================================================================

@router.get("/stats", response_model=StatsResponse)
def get_public_stats(db: Session = Depends(get_db)):
    """Get public statistics."""
    from datetime import timedelta

    now = datetime.utcnow()

    # Basic counts
    total_states = db.query(func.count(State.id)).scalar()
    total_sources = db.query(func.count(Source.id)).filter(Source.enabled == True).scalar()
    total_hearings = db.query(func.count(Hearing.id)).filter(Hearing.status == "complete").scalar()
    total_segments = db.query(func.count(Segment.id)).scalar()

    # Duration
    total_seconds = db.query(func.sum(Hearing.duration_seconds)).filter(
        Hearing.status == "complete"
    ).scalar() or 0
    total_hours = round(total_seconds / 3600, 1)

    # Hearings by status
    status_counts = db.query(
        Hearing.status,
        func.count(Hearing.id)
    ).group_by(Hearing.status).all()
    hearings_by_status = {s: c for s, c in status_counts}

    # Hearings by state (only completed)
    state_counts = db.query(
        State.code,
        func.count(Hearing.id)
    ).join(Hearing).filter(
        Hearing.status == "complete"
    ).group_by(State.code).all()
    hearings_by_state = {s: c for s, c in state_counts}

    # Costs (public view - totals only)
    total_transcription = db.query(func.sum(PipelineJob.cost_usd)).filter(
        PipelineJob.stage == "transcribe"
    ).scalar() or 0
    total_analysis = db.query(func.sum(PipelineJob.cost_usd)).filter(
        PipelineJob.stage == "analyze"
    ).scalar() or 0

    # Recent activity
    hearings_24h = db.query(func.count(Hearing.id)).filter(
        Hearing.created_at >= now - timedelta(hours=24),
        Hearing.status == "complete"
    ).scalar()
    hearings_7d = db.query(func.count(Hearing.id)).filter(
        Hearing.created_at >= now - timedelta(days=7),
        Hearing.status == "complete"
    ).scalar()

    return StatsResponse(
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
        hearings_last_7d=hearings_7d
    )


# ============================================================================
# UTILITIES
# ============================================================================

@router.get("/utilities")
def list_utilities(db: Session = Depends(get_db)):
    """Get list of all utilities with hearing counts."""
    results = db.query(
        Hearing.utility_name,
        func.count(Hearing.id).label("count")
    ).filter(
        Hearing.utility_name.isnot(None),
        Hearing.status == "complete"
    ).group_by(Hearing.utility_name).order_by(desc("count")).all()

    return [{"name": r.utility_name, "hearing_count": r.count} for r in results]


@router.get("/hearing-types")
def list_hearing_types(db: Session = Depends(get_db)):
    """Get list of all hearing types with counts."""
    results = db.query(
        Hearing.hearing_type,
        func.count(Hearing.id).label("count")
    ).filter(
        Hearing.hearing_type.isnot(None),
        Hearing.status == "complete"
    ).group_by(Hearing.hearing_type).order_by(desc("count")).all()

    return [{"type": r.hearing_type, "hearing_count": r.count} for r in results]


# ============================================================================
# DOCKETS
# ============================================================================

@router.get("/dockets", response_model=List[DocketListItem])
def list_dockets(
    states: Optional[str] = Query(None, description="Comma-separated state codes"),
    docket_type: Optional[str] = Query(None, description="Filter by docket type"),
    company: Optional[str] = Query(None, description="Filter by company name (partial match)"),
    status: Optional[str] = Query(None, description="Filter by status (open, closed, pending_decision)"),
    page: int = 1,
    page_size: int = 20,
    sort_by: str = Query("last_mentioned_at", description="Sort field"),
    sort_order: str = Query("desc", description="Sort order (asc/desc)"),
    db: Session = Depends(get_db)
):
    """List all dockets with filters and pagination."""
    query = db.query(
        Docket,
        State.code.label("state_code"),
        State.name.label("state_name")
    ).join(State, Docket.state_id == State.id)

    # Apply filters
    if states:
        state_list = [s.strip().upper() for s in states.split(",")]
        query = query.filter(State.code.in_(state_list))

    if docket_type:
        query = query.filter(Docket.docket_type == docket_type)

    if company:
        query = query.filter(Docket.company.ilike(f"%{company}%"))

    if status:
        query = query.filter(Docket.status == status)

    # Sorting
    sort_column = getattr(Docket, sort_by, Docket.last_mentioned_at)
    if sort_order.lower() == "desc":
        query = query.order_by(desc(sort_column))
    else:
        query = query.order_by(asc(sort_column))

    # Pagination
    offset = (page - 1) * page_size
    results = query.offset(offset).limit(page_size).all()

    return [
        DocketListItem(
            id=r.Docket.id,
            normalized_id=r.Docket.normalized_id,
            docket_number=r.Docket.docket_number,
            state_code=r.state_code,
            state_name=r.state_name,
            docket_type=r.Docket.docket_type,
            company=r.Docket.company,
            status=r.Docket.status,
            mention_count=r.Docket.mention_count or 1,
            first_seen_at=r.Docket.first_seen_at,
            last_mentioned_at=r.Docket.last_mentioned_at
        )
        for r in results
    ]


@router.get("/dockets/search", response_model=DocketSearchResponse)
def search_dockets(
    q: str = Query(..., min_length=1, description="Search query"),
    states: Optional[str] = Query(None, description="Comma-separated state codes"),
    page: int = 1,
    page_size: int = 20,
    db: Session = Depends(get_db)
):
    """Search dockets by number, company, or description."""
    query = db.query(
        Docket,
        State.code.label("state_code"),
        State.name.label("state_name")
    ).join(State, Docket.state_id == State.id)

    # Search across multiple fields
    search_pattern = f"%{q}%"
    query = query.filter(
        or_(
            Docket.normalized_id.ilike(search_pattern),
            Docket.docket_number.ilike(search_pattern),
            Docket.company.ilike(search_pattern),
            Docket.description.ilike(search_pattern),
            Docket.title.ilike(search_pattern)
        )
    )

    # Apply state filter
    if states:
        state_list = [s.strip().upper() for s in states.split(",")]
        query = query.filter(State.code.in_(state_list))

    # Get total count
    total_count = query.count()

    # Pagination and ordering
    offset = (page - 1) * page_size
    results = query.order_by(desc(Docket.mention_count)).offset(offset).limit(page_size).all()

    return DocketSearchResponse(
        query=q,
        results=[
            DocketListItem(
                id=r.Docket.id,
                normalized_id=r.Docket.normalized_id,
                docket_number=r.Docket.docket_number,
                state_code=r.state_code,
                state_name=r.state_name,
                docket_type=r.Docket.docket_type,
                company=r.Docket.company,
                status=r.Docket.status,
                mention_count=r.Docket.mention_count or 1,
                first_seen_at=r.Docket.first_seen_at,
                last_mentioned_at=r.Docket.last_mentioned_at
            )
            for r in results
        ],
        total_count=total_count,
        page=page,
        page_size=page_size
    )


@router.get("/dockets/{docket_id}", response_model=DocketDetail)
def get_docket(docket_id: int, db: Session = Depends(get_db)):
    """Get detailed docket information including related hearings."""
    result = db.query(
        Docket,
        State.code.label("state_code"),
        State.name.label("state_name")
    ).join(State, Docket.state_id == State.id).filter(Docket.id == docket_id).first()

    if not result:
        raise HTTPException(status_code=404, detail="Docket not found")

    docket = result.Docket

    # Get related hearings via junction table
    hearing_results = db.query(
        HearingDocket,
        Hearing.id.label("hearing_id"),
        Hearing.title.label("hearing_title"),
        Hearing.hearing_date
    ).join(
        Hearing, HearingDocket.hearing_id == Hearing.id
    ).filter(
        HearingDocket.docket_id == docket_id
    ).order_by(desc(Hearing.hearing_date)).all()

    hearings = [
        DocketHearingItem(
            hearing_id=hr.hearing_id,
            hearing_title=hr.hearing_title,
            hearing_date=hr.hearing_date,
            mention_summary=hr.HearingDocket.mention_summary
        )
        for hr in hearing_results
    ]

    return DocketDetail(
        id=docket.id,
        normalized_id=docket.normalized_id,
        docket_number=docket.docket_number,
        state_code=result.state_code,
        state_name=result.state_name,
        docket_type=docket.docket_type,
        company=docket.company,
        title=docket.title,
        description=docket.description,
        current_summary=docket.current_summary,
        status=docket.status,
        decision_expected=docket.decision_expected,
        mention_count=docket.mention_count or 1,
        first_seen_at=docket.first_seen_at,
        last_mentioned_at=docket.last_mentioned_at,
        created_at=docket.created_at,
        updated_at=docket.updated_at,
        hearings=hearings
    )


@router.get("/dockets/by-normalized-id/{normalized_id}", response_model=DocketWithTimeline)
def get_docket_by_normalized_id(normalized_id: str, db: Session = Depends(get_db)):
    """Get docket by normalized ID with full timeline (e.g., GA-44160, CA-A.24-07-003)."""
    result = db.query(
        Docket,
        State.code.label("state_code"),
        State.name.label("state_name")
    ).join(State, Docket.state_id == State.id).filter(
        Docket.normalized_id == normalized_id.upper()
    ).first()

    if not result:
        raise HTTPException(status_code=404, detail="Docket not found")

    docket = result.Docket

    # Get timeline (all hearing mentions)
    timeline_results = db.query(
        HearingDocket,
        Hearing.id.label("hearing_id"),
        Hearing.title.label("hearing_title"),
        Hearing.hearing_date,
        Hearing.video_url
    ).join(
        Hearing, HearingDocket.hearing_id == Hearing.id
    ).filter(
        HearingDocket.docket_id == docket.id
    ).order_by(desc(Hearing.hearing_date)).all()

    timeline = [
        TimelineItem(
            hearing_id=tr.hearing_id,
            hearing_title=tr.hearing_title,
            hearing_date=tr.hearing_date,
            video_url=tr.video_url,
            mention_summary=tr.HearingDocket.mention_summary,
            timestamps=None  # Could parse timestamps_json if needed
        )
        for tr in timeline_results
    ]

    # Get hearing count
    hearing_count = len(timeline)

    return DocketWithTimeline(
        id=docket.id,
        normalized_id=docket.normalized_id,
        docket_number=docket.docket_number,
        state_code=result.state_code,
        state_name=result.state_name,
        docket_type=docket.docket_type,
        company=docket.company,
        title=docket.title,
        description=docket.description,
        current_summary=docket.current_summary,
        status=docket.status,
        decision_expected=docket.decision_expected,
        mention_count=docket.mention_count or 1,
        first_seen_at=docket.first_seen_at,
        last_mentioned_at=docket.last_mentioned_at,
        created_at=docket.created_at,
        updated_at=docket.updated_at,
        hearings=[],  # Not needed, we have timeline
        timeline=timeline
    )


# ============================================================================
# WATCHLIST
# ============================================================================

@router.get("/watchlist", response_model=WatchlistResponse)
def get_watchlist(
    user_id: int = Query(1, description="User ID (demo mode uses 1)"),
    db: Session = Depends(get_db)
):
    """Get user's watched dockets with latest activity."""
    # Get watched dockets with hearing counts
    from sqlalchemy import literal_column

    results = db.query(
        Docket,
        State.code.label("state_code"),
        State.name.label("state_name"),
        func.count(func.distinct(HearingDocket.hearing_id)).label("hearing_count")
    ).join(
        UserWatchlist, UserWatchlist.docket_id == Docket.id
    ).join(
        State, Docket.state_id == State.id
    ).outerjoin(
        HearingDocket, HearingDocket.docket_id == Docket.id
    ).filter(
        UserWatchlist.user_id == user_id
    ).group_by(
        Docket.id, State.code, State.name
    ).order_by(desc(Docket.last_mentioned_at)).all()

    watchlist = []
    for r in results:
        # Get latest mention for this docket
        latest = db.query(
            HearingDocket.mention_summary,
            Hearing.id.label("hearing_id"),
            Hearing.title.label("hearing_title"),
            Hearing.hearing_date
        ).join(
            Hearing, HearingDocket.hearing_id == Hearing.id
        ).filter(
            HearingDocket.docket_id == r.Docket.id
        ).order_by(desc(Hearing.hearing_date)).first()

        latest_mention = None
        if latest:
            latest_mention = LatestMention(
                summary=latest.mention_summary,
                hearing_date=latest.hearing_date,
                hearing_title=latest.hearing_title,
                hearing_id=latest.hearing_id
            )

        watchlist.append(WatchlistDocket(
            id=r.Docket.id,
            normalized_id=r.Docket.normalized_id,
            docket_number=r.Docket.docket_number,
            state_code=r.state_code,
            state_name=r.state_name,
            docket_type=r.Docket.docket_type,
            company=r.Docket.company,
            status=r.Docket.status,
            mention_count=r.Docket.mention_count or 1,
            first_seen_at=r.Docket.first_seen_at,
            last_mentioned_at=r.Docket.last_mentioned_at,
            hearing_count=r.hearing_count,
            latest_mention=latest_mention
        ))

    return WatchlistResponse(
        dockets=watchlist,
        total_count=len(watchlist)
    )


@router.post("/watchlist")
def add_to_watchlist(
    request: WatchlistAddRequest,
    user_id: int = Query(1, description="User ID (demo mode uses 1)"),
    db: Session = Depends(get_db)
):
    """Add a docket to user's watchlist."""
    # Check docket exists
    docket = db.query(Docket).filter(Docket.id == request.docket_id).first()
    if not docket:
        raise HTTPException(status_code=404, detail="Docket not found")

    # Check if already watching
    existing = db.query(UserWatchlist).filter(
        UserWatchlist.user_id == user_id,
        UserWatchlist.docket_id == request.docket_id
    ).first()

    if existing:
        return {"message": "Already watching this docket", "docket_id": request.docket_id}

    # Add to watchlist
    watchlist_item = UserWatchlist(
        user_id=user_id,
        docket_id=request.docket_id,
        notify_on_mention=request.notify_on_mention
    )
    db.add(watchlist_item)
    db.commit()

    return {"message": "Added to watchlist", "docket_id": request.docket_id}


@router.delete("/watchlist/{docket_id}")
def remove_from_watchlist(
    docket_id: int,
    user_id: int = Query(1, description="User ID (demo mode uses 1)"),
    db: Session = Depends(get_db)
):
    """Remove a docket from user's watchlist."""
    result = db.query(UserWatchlist).filter(
        UserWatchlist.user_id == user_id,
        UserWatchlist.docket_id == docket_id
    ).delete()

    db.commit()

    if result == 0:
        raise HTTPException(status_code=404, detail="Docket not in watchlist")

    return {"message": "Removed from watchlist", "docket_id": docket_id}


# ============================================================================
# ACTIVITY FEED
# ============================================================================

@router.get("/activity", response_model=ActivityFeedResponse)
def get_activity_feed(
    states: Optional[str] = Query(None, description="Comma-separated state codes to filter"),
    limit: int = Query(20, le=100),
    offset: int = 0,
    db: Session = Depends(get_db)
):
    """Get recent activity feed (new hearings, transcripts ready, etc.)."""
    # Query recent hearings with their docket mentions
    query = db.query(
        Hearing,
        State.code.label("state_code"),
        State.name.label("state_name")
    ).join(
        State, Hearing.state_id == State.id
    ).filter(
        Hearing.status == "complete"
    )

    if states:
        state_list = [s.strip().upper() for s in states.split(",")]
        query = query.filter(State.code.in_(state_list))

    total_count = query.count()

    results = query.order_by(
        desc(Hearing.created_at)
    ).offset(offset).limit(limit).all()

    items = []
    for r in results:
        # Get dockets mentioned in this hearing
        docket_mentions = db.query(
            Docket.normalized_id,
            Docket.title,
            Docket.docket_type
        ).join(
            HearingDocket, HearingDocket.docket_id == Docket.id
        ).filter(
            HearingDocket.hearing_id == r.Hearing.id
        ).all()

        # Determine activity type based on hearing status
        activity_type = "new_hearing"
        if r.Hearing.status == "complete":
            activity_type = "transcript_ready"

        items.append(ActivityItem(
            date=r.Hearing.hearing_date or r.Hearing.created_at.date(),
            state_code=r.state_code,
            state_name=r.state_name,
            activity_type=activity_type,
            hearing_title=r.Hearing.title,
            hearing_id=r.Hearing.id,
            dockets_mentioned=[
                DocketMention(
                    normalized_id=dm.normalized_id,
                    title=dm.title,
                    docket_type=dm.docket_type
                )
                for dm in docket_mentions
            ]
        ))

    return ActivityFeedResponse(
        items=items,
        total_count=total_count,
        limit=limit,
        offset=offset
    )
