"""
Dashboard-compatible API routes.

These endpoints match the format expected by the customer dashboard,
providing a compatibility layer for the Florida-specific data.
"""

from typing import Optional, List
from datetime import datetime
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text, func
from pydantic import BaseModel

from florida.models import get_db
from florida.models.hearing import FLHearing, FLTranscriptSegment
from florida.models.analysis import FLAnalysis
from florida.models.docket import FLDocket
from florida.models.watchlist import FLWatchlist

router = APIRouter(tags=["dashboard"])


# Response Models (matching dashboard expectations)
class HearingListItem(BaseModel):
    id: int
    state_code: str = "FL"
    state_name: str = "Florida"
    title: str
    hearing_date: Optional[str] = None
    hearing_type: Optional[str] = None
    utility_name: Optional[str] = None
    duration_seconds: Optional[int] = None
    status: str = "complete"
    source_url: Optional[str] = None
    created_at: str
    pipeline_status: str = "analyzed"
    # Analysis indicators for list view
    commissioner_mood: Optional[str] = None
    one_sentence_summary: Optional[str] = None


class Participant(BaseModel):
    name: str
    role: str
    affiliation: Optional[str] = None


class Issue(BaseModel):
    issue: str
    description: str
    stance_by_party: Optional[dict] = None


class Commitment(BaseModel):
    commitment: str
    by_whom: Optional[str] = None
    context: str
    binding: Optional[bool] = None


class CommissionerConcern(BaseModel):
    commissioner: str
    concern: str
    severity: Optional[str] = None


class RiskFactor(BaseModel):
    factor: str
    likelihood: str
    impact: str


class Quote(BaseModel):
    quote: str
    speaker: str
    timestamp: Optional[str] = None
    significance: str


class HearingDetail(HearingListItem):
    description: Optional[str] = None
    docket_numbers: Optional[List[str]] = None
    video_url: Optional[str] = None
    source_name: Optional[str] = "Florida Channel"
    summary: Optional[str] = None
    one_sentence_summary: Optional[str] = None
    participants: Optional[List[Participant]] = None
    issues: Optional[List[Issue]] = None
    commitments: Optional[List[Commitment]] = None
    commissioner_concerns: Optional[List[CommissionerConcern]] = None
    commissioner_mood: Optional[str] = None
    likely_outcome: Optional[str] = None
    outcome_confidence: Optional[float] = None
    risk_factors: Optional[List[RiskFactor]] = None
    quotes: Optional[List[Quote]] = None
    segment_count: Optional[int] = None
    word_count: Optional[int] = None


# Helper functions to safely parse analysis JSON fields that may have format variations
def safe_parse_risk_factors(data) -> Optional[List[dict]]:
    """Parse risk_factors handling both object and string formats."""
    if not data:
        return None
    result = []
    for item in data:
        if isinstance(item, dict) and 'factor' in item:
            result.append(item)
        elif isinstance(item, str):
            # Convert string to risk factor object
            result.append({"factor": item, "likelihood": "unknown", "impact": "unknown"})
    return result if result else None


def safe_parse_quotes(data) -> Optional[List[dict]]:
    """Parse quotes handling format variations."""
    if not data:
        return None
    result = []
    for item in data:
        if isinstance(item, dict):
            # Ensure required fields exist
            if 'quote' in item and 'speaker' in item:
                item.setdefault('significance', 'Notable statement')
                result.append(item)
        elif isinstance(item, str):
            result.append({"quote": item, "speaker": "Unknown", "significance": "Notable statement"})
    return result if result else None


def safe_parse_commitments(data) -> Optional[List[dict]]:
    """Parse commitments handling format variations."""
    if not data:
        return None
    result = []
    for item in data:
        if isinstance(item, dict):
            # Ensure required fields exist
            if 'commitment' in item:
                item.setdefault('context', '')
                result.append(item)
    return result if result else None


class Segment(BaseModel):
    id: int
    segment_index: int
    start_time: float
    end_time: float
    text: str
    speaker: Optional[str] = None
    speaker_role: Optional[str] = None


class TranscriptResponse(BaseModel):
    hearing_id: int
    total_segments: int
    segments: List[Segment]
    page: int
    page_size: int


class SearchResult(BaseModel):
    segment_id: int
    hearing_id: int
    hearing_title: str
    state_code: str = "FL"
    state_name: str = "Florida"
    hearing_date: Optional[str] = None
    text: str
    start_time: float
    end_time: float
    speaker: Optional[str] = None
    speaker_role: Optional[str] = None
    source_url: Optional[str] = None
    video_url: Optional[str] = None
    timestamp_url: Optional[str] = None
    snippet: Optional[str] = None


class SearchResponse(BaseModel):
    query: str
    results: List[SearchResult]
    total_count: int
    page: int
    page_size: int


class Stats(BaseModel):
    total_states: int = 1
    total_sources: int = 1
    total_hearings: int
    total_segments: int
    total_hours: float
    hearings_by_status: dict
    hearings_by_state: dict
    total_transcription_cost: float = 0.0
    total_analysis_cost: float = 0.0
    total_cost: float = 0.0
    hearings_last_24h: int = 0
    hearings_last_7d: int = 0


class State(BaseModel):
    id: int = 9
    code: str = "FL"
    name: str = "Florida"
    commission_name: str = "Florida Public Service Commission"
    hearing_count: int


# Helper functions
def hearing_to_list_item(h: FLHearing, segment_count: int = 0, analysis: Optional[FLAnalysis] = None) -> HearingListItem:
    """Convert FLHearing to dashboard format."""
    status = "complete" if h.transcript_status == "transcribed" else h.transcript_status or "pending"
    pipeline_status = "analyzed" if analysis else "transcribed" if segment_count > 0 else "pending"

    return HearingListItem(
        id=h.id,
        title=h.title or f"Hearing {h.id}",
        hearing_date=h.hearing_date.isoformat() if h.hearing_date else None,
        hearing_type=h.hearing_type,
        utility_name=analysis.utility_name if analysis else None,
        duration_seconds=h.duration_seconds,
        status=status,
        source_url=h.source_url,
        created_at=h.created_at.isoformat() if h.created_at else datetime.utcnow().isoformat(),
        pipeline_status=pipeline_status,
        commissioner_mood=analysis.commissioner_mood if analysis else None,
        one_sentence_summary=analysis.one_sentence_summary if analysis else None,
    )


# Routes
@router.get("/api/states", response_model=List[State])
def get_states(db: Session = Depends(get_db)):
    """Get list of states (Florida only for now)."""
    hearing_count = db.query(func.count(FLHearing.id)).scalar() or 0
    return [State(hearing_count=hearing_count)]


@router.get("/api/states/{state_code}", response_model=State)
def get_state(state_code: str, db: Session = Depends(get_db)):
    """Get state details."""
    if state_code.upper() != "FL":
        raise HTTPException(status_code=404, detail="State not found")
    hearing_count = db.query(func.count(FLHearing.id)).scalar() or 0
    return State(hearing_count=hearing_count)


@router.get("/api/hearings", response_model=List[HearingListItem])
def get_hearings(
    states: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    search_query: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    sort_by: str = "hearing_date",
    sort_order: str = "desc",
    db: Session = Depends(get_db)
):
    """Get list of hearings with analysis indicators."""
    # Query hearings with their analysis
    query = db.query(FLHearing, FLAnalysis).outerjoin(
        FLAnalysis, FLAnalysis.hearing_id == FLHearing.id
    )

    # Apply filters
    if date_from:
        query = query.filter(FLHearing.hearing_date >= date_from)
    if date_to:
        query = query.filter(FLHearing.hearing_date <= date_to)
    if search_query:
        query = query.filter(FLHearing.title.ilike(f"%{search_query}%"))

    # Sorting
    if sort_by == "hearing_date":
        order_col = FLHearing.hearing_date
    elif sort_by == "created_at":
        order_col = FLHearing.created_at
    else:
        order_col = FLHearing.hearing_date

    if sort_order == "asc":
        query = query.order_by(order_col.asc())
    else:
        query = query.order_by(order_col.desc())

    # Pagination
    offset = (page - 1) * page_size
    results = query.offset(offset).limit(page_size).all()

    # Get segment counts and build response
    response = []
    for h, analysis in results:
        segment_count = db.query(func.count(FLTranscriptSegment.id)).filter(
            FLTranscriptSegment.hearing_id == h.id
        ).scalar() or 0
        response.append(hearing_to_list_item(h, segment_count, analysis))

    return response


@router.get("/api/hearings/{hearing_id}", response_model=HearingDetail)
def get_hearing(hearing_id: int, db: Session = Depends(get_db)):
    """Get hearing details with analysis."""
    hearing = db.query(FLHearing).filter(FLHearing.id == hearing_id).first()
    if not hearing:
        raise HTTPException(status_code=404, detail="Hearing not found")

    # Get segment count and word count
    segment_count = db.query(func.count(FLTranscriptSegment.id)).filter(
        FLTranscriptSegment.hearing_id == hearing_id
    ).scalar() or 0

    # Get word count from segments
    word_count_result = db.execute(text("""
        SELECT COALESCE(SUM(array_length(regexp_split_to_array(text, '\s+'), 1)), 0)
        FROM fl_transcript_segments WHERE hearing_id = :hid
    """), {"hid": hearing_id}).scalar() or 0

    # Get analysis if exists
    analysis = db.query(FLAnalysis).filter(FLAnalysis.hearing_id == hearing_id).first()

    # Build response - exclude fields we'll override from analysis
    base = hearing_to_list_item(hearing, segment_count, analysis)

    return HearingDetail(
        **base.model_dump(exclude={'one_sentence_summary', 'commissioner_mood'}),
        description=None,
        docket_numbers=[hearing.docket_number] if hearing.docket_number else None,
        video_url=hearing.source_url,
        summary=analysis.summary if analysis else None,
        one_sentence_summary=analysis.one_sentence_summary if analysis else None,
        participants=analysis.participants_json if analysis else None,
        issues=analysis.issues_json if analysis else None,
        commitments=safe_parse_commitments(analysis.commitments_json) if analysis else None,
        commissioner_concerns=analysis.commissioner_concerns_json if analysis else None,
        commissioner_mood=analysis.commissioner_mood if analysis else None,
        likely_outcome=analysis.likely_outcome if analysis else None,
        outcome_confidence=analysis.outcome_confidence if analysis else None,
        risk_factors=safe_parse_risk_factors(analysis.risk_factors_json) if analysis else None,
        quotes=safe_parse_quotes(analysis.quotes_json) if analysis else None,
        segment_count=segment_count,
        word_count=int(word_count_result),
    )


@router.get("/api/hearings/{hearing_id}/transcript", response_model=TranscriptResponse)
def get_transcript(
    hearing_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db)
):
    """Get transcript segments for a hearing."""
    # Verify hearing exists
    hearing = db.query(FLHearing).filter(FLHearing.id == hearing_id).first()
    if not hearing:
        raise HTTPException(status_code=404, detail="Hearing not found")

    # Get total count
    total = db.query(func.count(FLTranscriptSegment.id)).filter(
        FLTranscriptSegment.hearing_id == hearing_id
    ).scalar() or 0

    # Get segments with pagination
    offset = (page - 1) * page_size
    segments = db.query(FLTranscriptSegment).filter(
        FLTranscriptSegment.hearing_id == hearing_id
    ).order_by(FLTranscriptSegment.segment_index).offset(offset).limit(page_size).all()

    return TranscriptResponse(
        hearing_id=hearing_id,
        total_segments=total,
        segments=[
            Segment(
                id=s.id,
                segment_index=s.segment_index,
                start_time=s.start_time or 0,
                end_time=s.end_time or 0,
                text=s.text or "",
                speaker=s.speaker_name or s.speaker_label,
                speaker_role=s.speaker_role,
            )
            for s in segments
        ],
        page=page,
        page_size=page_size,
    )


@router.get("/api/search", response_model=SearchResponse)
def search_transcripts(
    q: str = Query(..., min_length=2),
    states: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """Full-text search across transcripts."""
    offset = (page - 1) * page_size

    # Build search query
    results = db.execute(text("""
        SELECT
            s.id as segment_id,
            s.hearing_id,
            h.title as hearing_title,
            h.hearing_date,
            s.text,
            s.start_time,
            s.end_time,
            s.speaker_name as speaker,
            s.speaker_role,
            h.source_url,
            ts_rank(s.text_tsvector, plainto_tsquery('english', :q)) as rank
        FROM fl_transcript_segments s
        JOIN fl_hearings h ON s.hearing_id = h.id
        WHERE s.text_tsvector @@ plainto_tsquery('english', :q)
        ORDER BY rank DESC
        LIMIT :limit OFFSET :offset
    """), {"q": q, "limit": page_size, "offset": offset}).fetchall()

    # Get total count
    total = db.execute(text("""
        SELECT COUNT(*)
        FROM fl_transcript_segments s
        WHERE s.text_tsvector @@ plainto_tsquery('english', :q)
    """), {"q": q}).scalar() or 0

    return SearchResponse(
        query=q,
        results=[
            SearchResult(
                segment_id=r.segment_id,
                hearing_id=r.hearing_id,
                hearing_title=r.hearing_title or "",
                hearing_date=r.hearing_date.isoformat() if r.hearing_date else None,
                text=r.text or "",
                start_time=r.start_time or 0,
                end_time=r.end_time or 0,
                speaker=r.speaker,
                speaker_role=r.speaker_role,
                source_url=r.source_url,
                video_url=r.source_url,
                timestamp_url=f"{r.source_url}#t={int(r.start_time or 0)}" if r.source_url else None,
                snippet=r.text[:200] + "..." if r.text and len(r.text) > 200 else r.text,
            )
            for r in results
        ],
        total_count=total,
        page=page,
        page_size=page_size,
    )


@router.get("/api/stats", response_model=Stats)
def get_stats(db: Session = Depends(get_db)):
    """Get dashboard statistics."""
    total_hearings = db.query(func.count(FLHearing.id)).scalar() or 0
    total_segments = db.query(func.count(FLTranscriptSegment.id)).scalar() or 0

    # Calculate total hours from duration
    total_seconds = db.query(func.sum(FLHearing.duration_seconds)).scalar() or 0
    total_hours = total_seconds / 3600 if total_seconds else 0

    # Get processing costs
    total_cost = db.query(func.sum(FLHearing.processing_cost_usd)).scalar() or 0

    return Stats(
        total_hearings=total_hearings,
        total_segments=total_segments,
        total_hours=round(total_hours, 1),
        hearings_by_status={"complete": total_hearings},
        hearings_by_state={"FL": total_hearings},
        total_cost=float(total_cost),
    )


@router.get("/api/utilities")
def get_utilities(db: Session = Depends(get_db)):
    """Get list of utilities."""
    # For now, return empty - could be populated from docket data
    return []


@router.get("/api/hearing-types")
def get_hearing_types(db: Session = Depends(get_db)):
    """Get list of hearing types."""
    results = db.query(
        FLHearing.hearing_type,
        func.count(FLHearing.id).label("count")
    ).filter(
        FLHearing.hearing_type.isnot(None)
    ).group_by(FLHearing.hearing_type).all()

    return [{"hearing_type": r[0], "count": r[1]} for r in results]


class WatchlistAddRequest(BaseModel):
    docket_id: int = None
    docket_number: str = None
    notify_on_mention: bool = True


@router.get("/api/watchlist")
def get_watchlist(user_id: int = 1, db: Session = Depends(get_db)):
    """Get user's watchlist with docket details."""
    # Get watchlist entries
    watchlist_entries = db.query(FLWatchlist).filter(
        FLWatchlist.user_id == user_id
    ).all()

    dockets = []
    for entry in watchlist_entries:
        # Get docket details
        docket = db.query(FLDocket).filter(
            FLDocket.docket_number == entry.docket_number
        ).first()

        if docket:
            dockets.append({
                "id": entry.id,  # Use watchlist entry id for delete operations
                "normalized_id": f"FL-{docket.docket_number}",
                "docket_number": docket.docket_number,
                "state_code": "FL",
                "state_name": "Florida",
                "docket_type": docket.sector_code,
                "company": docket.utility_name,
                "status": docket.status,
                "mention_count": 1,
                "first_seen_at": docket.filed_date.isoformat() if docket.filed_date else None,
                "last_mentioned_at": entry.created_at.isoformat() if entry.created_at else None,
                "hearing_count": 0,
                "latest_mention": {
                    "summary": docket.title,
                },
            })

    return {"dockets": dockets, "total_count": len(dockets)}


@router.post("/api/watchlist")
def add_to_watchlist(
    request: WatchlistAddRequest,
    user_id: int = 1,
    db: Session = Depends(get_db)
):
    """Add docket to watchlist."""
    # Handle docket_id format like "FL-20260010"
    docket_number = request.docket_number
    if not docket_number and request.docket_id:
        # Try to find by id
        docket_number = str(request.docket_id)

    if not docket_number:
        raise HTTPException(status_code=400, detail="docket_number or docket_id required")

    # Strip FL- prefix if present
    if docket_number.startswith("FL-"):
        docket_number = docket_number[3:]

    # Check if already in watchlist
    existing = db.query(FLWatchlist).filter(
        FLWatchlist.user_id == user_id,
        FLWatchlist.docket_number == docket_number
    ).first()

    if existing:
        return {"message": "Already in watchlist", "docket_id": docket_number}

    # Add to watchlist
    entry = FLWatchlist(
        user_id=user_id,
        docket_number=docket_number,
        notify_on_mention=request.notify_on_mention,
    )
    db.add(entry)
    db.commit()

    return {"message": "Added to watchlist", "docket_id": docket_number}


@router.delete("/api/watchlist/{docket_id}")
def remove_from_watchlist(docket_id: str, user_id: int = 1, db: Session = Depends(get_db)):
    """Remove docket from watchlist."""
    entry = None

    # First try as watchlist entry id (numeric)
    if docket_id.isdigit():
        entry = db.query(FLWatchlist).filter(
            FLWatchlist.id == int(docket_id),
            FLWatchlist.user_id == user_id
        ).first()

    # If not found, try as docket_number
    if not entry:
        docket_number = docket_id
        if docket_number.startswith("FL-"):
            docket_number = docket_number[3:]

        entry = db.query(FLWatchlist).filter(
            FLWatchlist.user_id == user_id,
            FLWatchlist.docket_number == docket_number
        ).first()

    if entry:
        db.delete(entry)
        db.commit()
        return {"message": "Removed from watchlist", "docket_id": docket_id}
    else:
        raise HTTPException(status_code=404, detail="Not in watchlist")


@router.get("/api/activity")
def get_activity_feed(
    states: Optional[str] = None,
    limit: int = 10,
    offset: int = 0,
    db: Session = Depends(get_db)
):
    """Get recent activity feed with analysis data."""
    # Get recent hearings with their analysis
    query = db.query(FLHearing, FLAnalysis).outerjoin(
        FLAnalysis, FLAnalysis.hearing_id == FLHearing.id
    ).order_by(FLHearing.created_at.desc())

    if limit:
        query = query.limit(limit)
    if offset:
        query = query.offset(offset)

    results = query.all()

    items = []
    for h, analysis in results:
        # Determine activity type based on what's available
        if analysis:
            activity_type = "analysis_complete"
        elif h.transcript_status == 'transcribed':
            activity_type = "transcript_ready"
        else:
            activity_type = "new_hearing"

        item = {
            "date": h.created_at.isoformat() if h.created_at else None,
            "state_code": "FL",
            "state_name": "Florida",
            "activity_type": activity_type,
            "hearing_title": h.title or f"Hearing {h.id}",
            "hearing_id": h.id,
            "dockets_mentioned": [],
        }

        # Add analysis data if available
        if analysis:
            item["one_sentence_summary"] = analysis.one_sentence_summary
            item["commissioner_mood"] = analysis.commissioner_mood
            item["likely_outcome"] = analysis.likely_outcome[:100] + "..." if analysis.likely_outcome and len(analysis.likely_outcome) > 100 else analysis.likely_outcome

        items.append(item)

    return {
        "items": items,
        "total_count": len(items),
        "limit": limit,
        "offset": offset,
    }


@router.get("/api/suggestions")
def get_suggestions(user_id: int = 1, db: Session = Depends(get_db)):
    """Get suggestions for watchlist (trending dockets, utilities)."""
    # Get user's current watchlist
    watched_dockets = set(
        w.docket_number for w in db.query(FLWatchlist).filter(
            FLWatchlist.user_id == user_id
        ).all()
    )

    # Get recent/active dockets as trending
    trending_dockets = db.query(FLDocket).filter(
        FLDocket.status == 'open'
    ).order_by(FLDocket.year.desc(), FLDocket.docket_number.desc()).limit(10).all()

    trending = []
    for d in trending_dockets:
        trending.append({
            "id": hash(d.docket_number) % 100000,  # Generate pseudo-id
            "docket_id": f"FL-{d.docket_number}",
            "utility_name": d.utility_name or d.title[:50] if d.title else "Florida PSC",
            "mention_count": 1,
            "state": "FL",
            "already_watching": d.docket_number in watched_dockets,
        })

    # Get unique utilities from dockets
    utility_results = db.query(
        FLDocket.utility_name,
        func.count(FLDocket.docket_number).label('count')
    ).filter(
        FLDocket.utility_name.isnot(None),
        FLDocket.status == 'open'
    ).group_by(FLDocket.utility_name).order_by(func.count(FLDocket.docket_number).desc()).limit(5).all()

    utilities = []
    for name, count in utility_results:
        # Check if all dockets for this utility are being watched
        utility_dockets = db.query(FLDocket.docket_number).filter(
            FLDocket.utility_name == name,
            FLDocket.status == 'open'
        ).all()
        utility_docket_numbers = {d[0] for d in utility_dockets}
        already_following = len(utility_docket_numbers) > 0 and utility_docket_numbers.issubset(watched_dockets)

        utilities.append({
            "utility_name": name,
            "states": ["FL"],
            "active_docket_count": count,
            "already_following": already_following,
        })

    return {
        "trending": trending,
        "utilities": utilities,
    }


class FollowUtilityRequest(BaseModel):
    utility_name: str


@router.post("/api/watchlist/follow-utility")
def follow_utility(
    request: FollowUtilityRequest,
    user_id: int = 1,
    db: Session = Depends(get_db)
):
    """Follow all dockets for a utility."""
    # Get all open dockets for this utility
    dockets = db.query(FLDocket).filter(
        FLDocket.utility_name == request.utility_name,
        FLDocket.status == 'open'
    ).all()

    added_ids = []
    for docket in dockets:
        # Check if already watching
        existing = db.query(FLWatchlist).filter(
            FLWatchlist.user_id == user_id,
            FLWatchlist.docket_number == docket.docket_number
        ).first()

        if not existing:
            entry = FLWatchlist(
                user_id=user_id,
                docket_number=docket.docket_number,
                notify_on_mention=True,
            )
            db.add(entry)
            added_ids.append(f"FL-{docket.docket_number}")

    db.commit()

    return {"added_count": len(added_ids), "docket_ids": added_ids}


@router.get("/api/dockets")
def get_dockets(
    states: Optional[str] = None,
    docket_type: Optional[str] = None,
    company: Optional[str] = None,
    status: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    sort_by: str = "docket_number",
    sort_order: str = "desc",
    db: Session = Depends(get_db)
):
    """Get list of dockets."""
    query = db.query(FLDocket)

    if status:
        query = query.filter(FLDocket.status == status)
    if company:
        query = query.filter(FLDocket.utility_name.ilike(f"%{company}%"))

    # Sorting
    if sort_order == "desc":
        query = query.order_by(FLDocket.docket_number.desc())
    else:
        query = query.order_by(FLDocket.docket_number.asc())

    # Pagination
    offset = (page - 1) * page_size
    dockets = query.offset(offset).limit(page_size).all()

    return [
        {
            "id": hash(d.docket_number) % 100000,
            "normalized_id": f"FL-{d.docket_number}",
            "docket_number": d.docket_number,
            "state_code": "FL",
            "state_name": "Florida",
            "docket_type": d.sector_code,
            "company": d.utility_name,
            "status": d.status,
            "mention_count": 1,
            "first_seen_at": d.filed_date.isoformat() if d.filed_date else None,
            "last_mentioned_at": None,
        }
        for d in dockets
    ]


@router.get("/api/dockets/search")
def search_dockets(
    q: str = Query(..., min_length=2),
    states: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Search dockets by title or utility name."""
    dockets = db.query(FLDocket).filter(
        (FLDocket.title.ilike(f"%{q}%")) |
        (FLDocket.utility_name.ilike(f"%{q}%")) |
        (FLDocket.docket_number.ilike(f"%{q}%"))
    ).limit(20).all()

    return {
        "results": [
            {
                "id": hash(d.docket_number) % 100000,
                "normalized_id": f"FL-{d.docket_number}",
                "docket_number": d.docket_number,
                "state_code": "FL",
                "state_name": "Florida",
                "docket_type": d.sector_code,
                "company": d.utility_name,
                "status": d.status,
                "mention_count": 1,
            }
            for d in dockets
        ],
        "total_count": len(dockets),
    }


@router.get("/api/dockets/by-normalized-id/{normalized_id}")
def get_docket_by_normalized_id(normalized_id: str, db: Session = Depends(get_db)):
    """Get docket details by normalized ID (e.g., FL-20250149)."""
    # Strip state prefix
    docket_number = normalized_id
    if normalized_id.startswith("FL-"):
        docket_number = normalized_id[3:]

    docket = db.query(FLDocket).filter(
        FLDocket.docket_number == docket_number
    ).first()

    if not docket:
        raise HTTPException(status_code=404, detail="Docket not found")

    # Get related hearings for timeline
    hearings = db.query(FLHearing).filter(
        FLHearing.docket_number == docket_number
    ).order_by(FLHearing.hearing_date.desc()).limit(10).all()

    timeline = [
        {
            "hearing_id": h.id,
            "hearing_title": h.title,
            "hearing_date": h.hearing_date.isoformat() if h.hearing_date else None,
            "video_url": h.source_url,
            "mention_summary": None,
        }
        for h in hearings
    ]

    return {
        "id": hash(docket.docket_number) % 100000,
        "normalized_id": f"FL-{docket.docket_number}",
        "docket_number": docket.docket_number,
        "state_code": "FL",
        "state_name": "Florida",
        "docket_type": docket.sector_code,
        "company": docket.utility_name,
        "status": docket.status,
        "mention_count": len(hearings),
        "first_seen_at": docket.filed_date.isoformat() if docket.filed_date else None,
        "last_mentioned_at": hearings[0].hearing_date.isoformat() if hearings and hearings[0].hearing_date else None,
        "title": docket.title,
        "description": docket.title,
        "current_summary": docket.title,
        "decision_expected": None,
        "timeline": timeline,
    }
