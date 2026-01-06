"""
Review Queue API Routes

Manual review queue for unverified entity matches.
Allows admins to verify, correct, or reject entity links.
"""

from datetime import datetime, timezone
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.database import SessionLocal

router = APIRouter(prefix="/admin/review", tags=["review"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# =============================================================================
# SCHEMAS
# =============================================================================

class ReviewSuggestion(BaseModel):
    id: int
    normalized_id: Optional[str] = None
    name: Optional[str] = None
    title: Optional[str] = None
    utility_name: Optional[str] = None
    score: float


class ReviewItem(BaseModel):
    id: int
    entity_type: str
    hearing_id: int
    hearing_title: str
    hearing_date: Optional[str] = None
    original_text: str
    current_entity_id: Optional[int] = None
    current_entity_name: Optional[str] = None
    confidence: str
    transcript_context: Optional[str] = None
    suggestions: List[ReviewSuggestion]


class ReviewAction(BaseModel):
    action: str  # "link", "correct", "invalid", "skip"
    correct_entity_id: Optional[int] = None
    corrected_text: Optional[str] = None
    notes: Optional[str] = None


class ReviewQueueStats(BaseModel):
    total: int
    dockets: int
    topics: int
    utilities: int


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def get_docket_suggestions(db: Session, text: str, state_code: Optional[str]) -> List[dict]:
    """Get suggested known dockets for matching."""
    try:
        from rapidfuzz import process, fuzz
    except ImportError:
        return []

    from app.models.database import KnownDocket
    from app.services.docket_parser import normalize_for_matching

    # Get known dockets for this state
    query = db.query(KnownDocket)
    if state_code:
        query = query.filter(KnownDocket.state_code == state_code)
    known = query.limit(500).all()

    if not known:
        return []

    # Fuzzy match
    normalized = normalize_for_matching(text)
    choices = {normalize_for_matching(k.normalized_id): k for k in known}

    matches = process.extract(normalized, choices.keys(), scorer=fuzz.ratio, limit=5)

    suggestions = []
    for match_text, score, _ in matches:
        k = choices[match_text]
        suggestions.append({
            "id": k.id,
            "normalized_id": k.normalized_id,
            "title": k.title,
            "utility_name": k.utility_name,
            "score": score,
        })

    return suggestions


def get_topic_suggestions(db: Session, text: str) -> List[dict]:
    """Get suggested topics for matching."""
    try:
        from rapidfuzz import process, fuzz
    except ImportError:
        return []

    from app.models.database import Topic

    topics = db.query(Topic).filter(Topic.category != 'uncategorized').all()
    if not topics:
        return []

    choices = {t.name.lower(): t for t in topics}
    matches = process.extract(text.lower(), choices.keys(), scorer=fuzz.ratio, limit=5)

    suggestions = []
    for match_text, score, _ in matches:
        t = choices[match_text]
        suggestions.append({
            "id": t.id,
            "name": t.name,
            "title": t.category,
            "score": score,
        })

    return suggestions


def get_utility_suggestions(db: Session, text: str) -> List[dict]:
    """Get suggested utilities for matching."""
    try:
        from rapidfuzz import process, fuzz
    except ImportError:
        return []

    from app.models.database import Utility

    utilities = db.query(Utility).all()
    if not utilities:
        return []

    choices = {u.name.lower(): u for u in utilities}
    matches = process.extract(text.lower(), choices.keys(), scorer=fuzz.ratio, limit=5)

    suggestions = []
    for match_text, score, _ in matches:
        u = choices[match_text]
        suggestions.append({
            "id": u.id,
            "name": u.name,
            "title": u.utility_type,
            "score": score,
        })

    return suggestions


# =============================================================================
# ROUTES
# =============================================================================

@router.get("/stats")
def get_review_stats(db: Session = Depends(get_db)) -> ReviewQueueStats:
    """Get count of items needing review."""
    from app.models.database import Docket, HearingTopic, HearingUtility, Topic

    # Count unverified dockets
    docket_count = db.query(Docket).filter(
        Docket.confidence.in_(["unverified", "possible"]),
        Docket.review_status == "pending"
    ).count()

    # Count uncategorized topics
    topic_count = db.query(HearingTopic).join(Topic).filter(
        Topic.category == "uncategorized"
    ).count()

    # Count utilities needing review
    utility_count = db.query(HearingUtility).filter(
        HearingUtility.needs_review == True
    ).count()

    return ReviewQueueStats(
        total=docket_count + topic_count + utility_count,
        dockets=docket_count,
        topics=topic_count,
        utilities=utility_count
    )


@router.get("/queue")
def get_review_queue(
    entity_type: Optional[str] = Query(None, description="Filter by entity type: docket, topic, utility"),
    state: Optional[str] = Query(None, description="Filter by state code"),
    limit: int = Query(50, le=100),
    db: Session = Depends(get_db)
) -> List[ReviewItem]:
    """Get items that need manual review."""
    from app.models.database import (
        Docket, HearingDocket, Hearing, KnownDocket, State,
        HearingTopic, Topic,
        HearingUtility, Utility
    )

    items = []

    # Get unverified dockets
    if entity_type in (None, "docket"):
        docket_query = db.query(
            Docket,
            HearingDocket,
            Hearing
        ).join(
            HearingDocket, Docket.id == HearingDocket.docket_id
        ).join(
            Hearing, HearingDocket.hearing_id == Hearing.id
        ).filter(
            Docket.confidence.in_(["unverified", "possible"]),
            Docket.review_status == "pending"
        )

        if state:
            docket_query = docket_query.join(
                State, Hearing.state_id == State.id
            ).filter(State.code == state.upper())

        docket_query = docket_query.order_by(
            Hearing.hearing_date.desc()
        ).limit(limit)

        for docket, hd, hearing in docket_query.all():
            # Get state code for suggestions
            hearing_state = db.query(State).filter(State.id == hearing.state_id).first()
            state_code = hearing_state.code if hearing_state else None

            # Get known docket name if linked
            known_name = None
            if docket.known_docket_id:
                known = db.query(KnownDocket).filter(KnownDocket.id == docket.known_docket_id).first()
                known_name = known.normalized_id if known else None

            suggestions = get_docket_suggestions(db, docket.docket_number, state_code)

            items.append(ReviewItem(
                id=docket.id,
                entity_type="docket",
                hearing_id=hearing.id,
                hearing_title=hearing.title[:100] if hearing.title else "",
                hearing_date=str(hearing.hearing_date) if hearing.hearing_date else None,
                original_text=docket.docket_number,
                current_entity_id=docket.known_docket_id,
                current_entity_name=known_name,
                confidence=docket.confidence or "unverified",
                transcript_context=hd.context_summary,
                suggestions=[ReviewSuggestion(**s) for s in suggestions]
            ))

    # Get uncategorized topics
    if entity_type in (None, "topic"):
        topic_query = db.query(
            HearingTopic,
            Topic,
            Hearing
        ).join(
            Topic, HearingTopic.topic_id == Topic.id
        ).join(
            Hearing, HearingTopic.hearing_id == Hearing.id
        ).filter(
            Topic.category == "uncategorized"
        )

        if state:
            topic_query = topic_query.join(
                State, Hearing.state_id == State.id
            ).filter(State.code == state.upper())

        topic_query = topic_query.order_by(
            Hearing.hearing_date.desc()
        ).limit(limit)

        for ht, topic, hearing in topic_query.all():
            suggestions = get_topic_suggestions(db, topic.name)

            items.append(ReviewItem(
                id=ht.id,
                entity_type="topic",
                hearing_id=hearing.id,
                hearing_title=hearing.title[:100] if hearing.title else "",
                hearing_date=str(hearing.hearing_date) if hearing.hearing_date else None,
                original_text=topic.name,
                current_entity_id=topic.id,
                current_entity_name=topic.category,
                confidence=ht.confidence or "auto",
                transcript_context=ht.context_summary,
                suggestions=[ReviewSuggestion(**s) for s in suggestions]
            ))

    # Get utilities needing review
    if entity_type in (None, "utility"):
        utility_query = db.query(
            HearingUtility,
            Utility,
            Hearing
        ).join(
            Utility, HearingUtility.utility_id == Utility.id
        ).join(
            Hearing, HearingUtility.hearing_id == Hearing.id
        ).filter(
            HearingUtility.needs_review == True
        )

        if state:
            utility_query = utility_query.join(
                State, Hearing.state_id == State.id
            ).filter(State.code == state.upper())

        utility_query = utility_query.order_by(
            Hearing.hearing_date.desc()
        ).limit(limit)

        for hu, utility, hearing in utility_query.all():
            suggestions = get_utility_suggestions(db, utility.name)

            items.append(ReviewItem(
                id=hu.id,
                entity_type="utility",
                hearing_id=hearing.id,
                hearing_title=hearing.title[:100] if hearing.title else "",
                hearing_date=str(hearing.hearing_date) if hearing.hearing_date else None,
                original_text=utility.name,
                current_entity_id=utility.id,
                current_entity_name=utility.normalized_name,
                confidence=hu.confidence or "auto",
                transcript_context=hu.context_summary,
                suggestions=[ReviewSuggestion(**s) for s in suggestions]
            ))

    return items


@router.post("/docket/{docket_id}")
def review_docket(
    docket_id: int,
    action: ReviewAction,
    db: Session = Depends(get_db)
):
    """Process review action for a docket."""
    from app.models.database import Docket, KnownDocket, EntityCorrection

    docket = db.query(Docket).filter(Docket.id == docket_id).first()
    if not docket:
        raise HTTPException(status_code=404, detail="Docket not found")

    # Store original for correction tracking
    original_text = docket.docket_number

    if action.action == "link":
        # Link to a known docket
        if not action.correct_entity_id:
            raise HTTPException(status_code=400, detail="correct_entity_id required for link action")

        known = db.query(KnownDocket).filter(KnownDocket.id == action.correct_entity_id).first()
        if not known:
            raise HTTPException(status_code=404, detail="Known docket not found")

        docket.known_docket_id = known.id
        docket.confidence = "verified"
        docket.review_status = "reviewed"

        # Copy metadata from known docket
        if known.utility_name and not docket.company:
            docket.company = known.utility_name
        if known.sector:
            docket.sector = known.sector
        if known.year:
            docket.year = known.year
        if known.title and not docket.title:
            docket.title = known.title

    elif action.action == "correct":
        # Fix the docket number
        if not action.corrected_text:
            raise HTTPException(status_code=400, detail="corrected_text required for correct action")

        docket.original_extracted = original_text
        docket.docket_number = action.corrected_text
        docket.review_status = "reviewed"

    elif action.action == "invalid":
        # Mark as not a real docket
        docket.review_status = "invalid"
        docket.confidence = "invalid"

    elif action.action == "skip":
        # Skip for now
        pass

    else:
        raise HTTPException(status_code=400, detail=f"Unknown action: {action.action}")

    # Record correction for training
    if action.action in ("link", "correct", "invalid"):
        # Get first associated hearing
        hearing_id = None
        if docket.hearing_dockets:
            hearing_id = docket.hearing_dockets[0].hearing_id

        correction = EntityCorrection(
            entity_type="docket",
            hearing_id=hearing_id,
            original_text=original_text,
            corrected_text=action.corrected_text,
            correct_entity_id=action.correct_entity_id,
            correction_type=action.action,
            created_by="admin",  # TODO: get from auth
        )
        db.add(correction)

    docket.reviewed_by = "admin"  # TODO: get from auth
    docket.reviewed_at = datetime.now(timezone.utc)
    docket.review_notes = action.notes

    db.commit()

    return {"message": "Review processed", "new_confidence": docket.confidence}


@router.post("/topic/{hearing_topic_id}")
def review_topic(
    hearing_topic_id: int,
    action: ReviewAction,
    db: Session = Depends(get_db)
):
    """Process review action for a topic."""
    from app.models.database import HearingTopic, Topic, EntityCorrection

    ht = db.query(HearingTopic).filter(HearingTopic.id == hearing_topic_id).first()
    if not ht:
        raise HTTPException(status_code=404, detail="HearingTopic not found")

    topic = db.query(Topic).filter(Topic.id == ht.topic_id).first()
    original_text = topic.name if topic else ""

    if action.action == "link":
        # Link to a different topic
        if not action.correct_entity_id:
            raise HTTPException(status_code=400, detail="correct_entity_id required for link action")

        correct_topic = db.query(Topic).filter(Topic.id == action.correct_entity_id).first()
        if not correct_topic:
            raise HTTPException(status_code=404, detail="Topic not found")

        # Update the hearing_topic to point to correct topic
        ht.topic_id = correct_topic.id
        ht.confidence = "verified"
        ht.needs_review = False

        # Decrement old topic mention count
        if topic:
            topic.mention_count = max(0, (topic.mention_count or 1) - 1)
        # Increment new topic mention count
        correct_topic.mention_count = (correct_topic.mention_count or 0) + 1

    elif action.action == "correct":
        # Update the topic category
        if topic and action.corrected_text:
            topic.category = action.corrected_text
        ht.confidence = "verified"
        ht.needs_review = False

    elif action.action == "invalid":
        # Remove the topic link
        db.delete(ht)

    elif action.action == "skip":
        pass

    else:
        raise HTTPException(status_code=400, detail=f"Unknown action: {action.action}")

    # Record correction
    if action.action in ("link", "correct", "invalid"):
        correction = EntityCorrection(
            entity_type="topic",
            hearing_id=ht.hearing_id,
            original_text=original_text,
            corrected_text=action.corrected_text,
            correct_entity_id=action.correct_entity_id,
            correction_type=action.action,
            created_by="admin",
        )
        db.add(correction)

    ht.review_notes = action.notes
    db.commit()

    return {"message": "Review processed"}


@router.post("/utility/{hearing_utility_id}")
def review_utility(
    hearing_utility_id: int,
    action: ReviewAction,
    db: Session = Depends(get_db)
):
    """Process review action for a utility."""
    from app.models.database import HearingUtility, Utility, EntityCorrection

    hu = db.query(HearingUtility).filter(HearingUtility.id == hearing_utility_id).first()
    if not hu:
        raise HTTPException(status_code=404, detail="HearingUtility not found")

    utility = db.query(Utility).filter(Utility.id == hu.utility_id).first()
    original_text = utility.name if utility else ""

    if action.action == "link":
        # Link to a different utility
        if not action.correct_entity_id:
            raise HTTPException(status_code=400, detail="correct_entity_id required for link action")

        correct_utility = db.query(Utility).filter(Utility.id == action.correct_entity_id).first()
        if not correct_utility:
            raise HTTPException(status_code=404, detail="Utility not found")

        # Update the hearing_utility to point to correct utility
        hu.utility_id = correct_utility.id
        hu.confidence = "verified"
        hu.needs_review = False

        # Update mention counts
        if utility:
            utility.mention_count = max(0, (utility.mention_count or 1) - 1)
        correct_utility.mention_count = (correct_utility.mention_count or 0) + 1

    elif action.action == "correct":
        # Update the utility name (create new if needed)
        if action.corrected_text and utility:
            # Add as alias
            aliases = utility.aliases or []
            if original_text not in aliases:
                aliases.append(original_text)
            utility.aliases = aliases
            utility.name = action.corrected_text
        hu.confidence = "verified"
        hu.needs_review = False

    elif action.action == "invalid":
        # Remove the utility link
        db.delete(hu)

    elif action.action == "skip":
        pass

    else:
        raise HTTPException(status_code=400, detail=f"Unknown action: {action.action}")

    # Record correction
    if action.action in ("link", "correct", "invalid"):
        correction = EntityCorrection(
            entity_type="utility",
            hearing_id=hu.hearing_id,
            original_text=original_text,
            corrected_text=action.corrected_text,
            correct_entity_id=action.correct_entity_id,
            correction_type=action.action,
            created_by="admin",
        )
        db.add(correction)

    hu.review_notes = action.notes
    db.commit()

    return {"message": "Review processed"}


@router.get("/corrections")
def get_corrections(
    entity_type: Optional[str] = None,
    limit: int = Query(50, le=100),
    db: Session = Depends(get_db)
) -> List[dict]:
    """Get recent entity corrections for training/analysis."""
    from app.models.database import EntityCorrection

    query = db.query(EntityCorrection)

    if entity_type:
        query = query.filter(EntityCorrection.entity_type == entity_type)

    corrections = query.order_by(EntityCorrection.created_at.desc()).limit(limit).all()

    return [
        {
            "id": c.id,
            "entity_type": c.entity_type,
            "hearing_id": c.hearing_id,
            "original_text": c.original_text,
            "corrected_text": c.corrected_text,
            "correct_entity_id": c.correct_entity_id,
            "correction_type": c.correction_type,
            "created_by": c.created_by,
            "created_at": c.created_at.isoformat() if c.created_at else None,
        }
        for c in corrections
    ]


# =============================================================================
# SMART EXTRACTION REVIEW QUEUE
# =============================================================================

class ExtractionReviewItem(BaseModel):
    """An extracted docket candidate needing review."""
    id: int
    hearing_id: int
    hearing_title: Optional[str] = None
    hearing_date: Optional[str] = None
    state_code: Optional[str] = None

    # Extraction details
    raw_text: str
    normalized_id: str
    context_before: Optional[str] = None
    context_after: Optional[str] = None
    trigger_phrase: Optional[str] = None

    # Validation results
    format_valid: bool
    format_score: int
    format_issues: Optional[List[str]] = None

    # Matching results
    match_type: str
    matched_docket_id: Optional[int] = None
    matched_docket_number: Optional[str] = None
    matched_docket_title: Optional[str] = None
    fuzzy_score: int

    # Scoring
    context_score: int
    confidence_score: int
    status: str
    review_reason: Optional[str] = None

    # Suggestion
    suggested_docket_id: Optional[int] = None
    suggested_correction: Optional[str] = None
    correction_confidence: int
    correction_evidence: Optional[List[str]] = None


class ExtractionReviewAction(BaseModel):
    """Action to take on an extraction review item."""
    action: str  # "accept", "accept_suggestion", "correct", "reject"
    corrected_docket_id: Optional[int] = None  # For linking to known docket
    corrected_text: Optional[str] = None  # For manual correction
    notes: Optional[str] = None


class ExtractionReviewStats(BaseModel):
    """Stats for extraction review queue."""
    total_pending: int
    needs_review: int
    by_state: dict


@router.get("/extraction/stats")
def get_extraction_review_stats(db: Session = Depends(get_db)) -> ExtractionReviewStats:
    """Get stats for extraction review queue."""
    result = db.execute(text("""
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN status = 'needs_review' THEN 1 ELSE 0 END) as needs_review
        FROM extracted_dockets
        WHERE status IN ('needs_review', 'pending')
    """))
    row = result.fetchone()

    # Get by state
    state_result = db.execute(text("""
        SELECT
            h.state_id,
            s.code,
            COUNT(*) as count
        FROM extracted_dockets ed
        JOIN hearings h ON ed.hearing_id = h.id
        JOIN states s ON h.state_id = s.id
        WHERE ed.status = 'needs_review'
        GROUP BY h.state_id, s.code
    """))
    by_state = {r[1]: r[2] for r in state_result.fetchall()}

    return ExtractionReviewStats(
        total_pending=row[0] if row else 0,
        needs_review=row[1] if row else 0,
        by_state=by_state
    )


@router.get("/extraction/queue")
def get_extraction_review_queue(
    state: Optional[str] = Query(None, description="Filter by state code"),
    status: str = Query("needs_review", description="Filter by status"),
    limit: int = Query(50, le=100),
    db: Session = Depends(get_db)
) -> List[ExtractionReviewItem]:
    """Get extraction candidates needing review."""
    import json

    # Build query
    sql = """
        SELECT
            ed.*,
            h.title as hearing_title,
            h.hearing_date,
            s.code as state_code,
            kd.docket_number as matched_docket_number,
            kd.title as matched_docket_title,
            skd.docket_number as suggested_docket_number
        FROM extracted_dockets ed
        JOIN hearings h ON ed.hearing_id = h.id
        JOIN states s ON h.state_id = s.id
        LEFT JOIN known_dockets kd ON ed.matched_known_docket_id = kd.id
        LEFT JOIN known_dockets skd ON ed.suggested_docket_id = skd.id
        WHERE ed.status = :status
    """
    params = {"status": status, "limit": limit}

    if state:
        sql += " AND s.code = :state"
        params["state"] = state.upper()

    sql += " ORDER BY ed.confidence_score DESC, ed.created_at DESC LIMIT :limit"

    result = db.execute(text(sql), params)
    rows = result.fetchall()
    columns = result.keys()

    items = []
    for row in rows:
        data = dict(zip(columns, row))

        # Parse JSON fields
        format_issues = json.loads(data.get('format_issues') or '[]') if data.get('format_issues') else []
        correction_evidence = json.loads(data.get('correction_evidence') or '[]') if data.get('correction_evidence') else []

        items.append(ExtractionReviewItem(
            id=data['id'],
            hearing_id=data['hearing_id'],
            hearing_title=data.get('hearing_title'),
            hearing_date=str(data['hearing_date']) if data.get('hearing_date') else None,
            state_code=data.get('state_code'),
            raw_text=data['raw_text'],
            normalized_id=data['normalized_id'],
            context_before=data.get('context_before'),
            context_after=data.get('context_after'),
            trigger_phrase=data.get('trigger_phrase'),
            format_valid=bool(data.get('format_valid')),
            format_score=data.get('format_score', 0),
            format_issues=format_issues,
            match_type=data.get('match_type', 'none'),
            matched_docket_id=data.get('matched_known_docket_id'),
            matched_docket_number=data.get('matched_docket_number'),
            matched_docket_title=data.get('matched_docket_title'),
            fuzzy_score=data.get('fuzzy_score', 0),
            context_score=data.get('context_score', 0),
            confidence_score=data.get('confidence_score', 0),
            status=data.get('status', 'pending'),
            review_reason=data.get('review_reason'),
            suggested_docket_id=data.get('suggested_docket_id'),
            suggested_correction=data.get('suggested_correction') or data.get('suggested_docket_number'),
            correction_confidence=data.get('correction_confidence', 0),
            correction_evidence=correction_evidence,
        ))

    return items


@router.post("/extraction/{extraction_id}")
def review_extraction(
    extraction_id: int,
    action: ExtractionReviewAction,
    db: Session = Depends(get_db)
):
    """Process review action for an extraction candidate."""
    from app.models.database import Docket, KnownDocket, HearingDocket, Hearing

    # Get the extraction
    result = db.execute(text(
        "SELECT * FROM extracted_dockets WHERE id = :id"
    ), {"id": extraction_id})
    row = result.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Extraction not found")

    columns = result.keys()
    extraction = dict(zip(columns, row))

    hearing_id = extraction['hearing_id']
    raw_text = extraction['raw_text']
    normalized_id = extraction['normalized_id']

    # Get hearing for state info
    hearing = db.query(Hearing).filter(Hearing.id == hearing_id).first()

    final_docket_id = None
    review_decision = action.action

    if action.action == "accept":
        # Accept the extraction as-is
        # Create/update docket if it matches a known docket
        if extraction['matched_known_docket_id']:
            known = db.query(KnownDocket).filter(
                KnownDocket.id == extraction['matched_known_docket_id']
            ).first()
            if known:
                final_docket_id = known.id
                # Create docket entry linked to known docket
                docket = _get_or_create_docket_from_known(known, hearing, db)
                _link_hearing_to_docket(hearing_id, docket.id, db)
        else:
            # Create new docket from extraction
            docket = _create_docket_from_extraction(extraction, hearing, db)
            _link_hearing_to_docket(hearing_id, docket.id, db)

        review_decision = "confirmed"

    elif action.action == "accept_suggestion":
        # Accept the suggested correction
        if not extraction['suggested_docket_id']:
            raise HTTPException(status_code=400, detail="No suggestion available")

        known = db.query(KnownDocket).filter(
            KnownDocket.id == extraction['suggested_docket_id']
        ).first()
        if known:
            final_docket_id = known.id
            docket = _get_or_create_docket_from_known(known, hearing, db)
            _link_hearing_to_docket(hearing_id, docket.id, db)

        review_decision = "corrected"

    elif action.action == "correct":
        # Manual correction to a specific known docket
        if not action.corrected_docket_id:
            raise HTTPException(status_code=400, detail="corrected_docket_id required")

        known = db.query(KnownDocket).filter(
            KnownDocket.id == action.corrected_docket_id
        ).first()
        if not known:
            raise HTTPException(status_code=404, detail="Known docket not found")

        final_docket_id = known.id
        docket = _get_or_create_docket_from_known(known, hearing, db)
        _link_hearing_to_docket(hearing_id, docket.id, db)

        review_decision = "corrected"

    elif action.action == "reject":
        # Mark as rejected (not a valid docket)
        review_decision = "rejected"

    else:
        raise HTTPException(status_code=400, detail=f"Unknown action: {action.action}")

    # Update the extraction record
    db.execute(text("""
        UPDATE extracted_dockets
        SET status = 'reviewed',
            review_decision = :decision,
            final_docket_id = :final_id,
            reviewed_by = 'admin',
            reviewed_at = CURRENT_TIMESTAMP,
            review_notes = :notes
        WHERE id = :id
    """), {
        "id": extraction_id,
        "decision": review_decision,
        "final_id": final_docket_id,
        "notes": action.notes,
    })

    db.commit()

    return {
        "message": "Review processed",
        "decision": review_decision,
        "final_docket_id": final_docket_id
    }


def _get_or_create_docket_from_known(known: "KnownDocket", hearing: "Hearing", db: Session) -> "Docket":
    """Get or create a Docket entry linked to a KnownDocket."""
    from app.models.database import Docket

    # Check if docket already exists
    existing = db.query(Docket).filter(
        Docket.normalized_id == known.normalized_id
    ).first()

    if existing:
        return existing

    # Create new docket
    docket = Docket(
        state_id=hearing.state_id,
        docket_number=known.docket_number,
        normalized_id=known.normalized_id,
        known_docket_id=known.id,
        title=known.title,
        company=known.utility_name,
        sector=known.sector,
        year=known.year,
        confidence="verified",
        review_status="reviewed",
    )
    db.add(docket)
    db.flush()
    return docket


def _create_docket_from_extraction(extraction: dict, hearing: "Hearing", db: Session) -> "Docket":
    """Create a Docket entry from an extraction."""
    from app.models.database import Docket
    from datetime import datetime, timezone

    docket = Docket(
        state_id=hearing.state_id,
        docket_number=extraction['raw_text'],
        normalized_id=extraction['normalized_id'],
        confidence="verified",
        review_status="reviewed",
        first_seen_at=datetime.now(timezone.utc),
        last_mentioned_at=datetime.now(timezone.utc),
        mention_count=1,
    )
    db.add(docket)
    db.flush()
    return docket


def _link_hearing_to_docket(hearing_id: int, docket_id: int, db: Session):
    """Create HearingDocket link if not exists."""
    from app.models.database import HearingDocket

    existing = db.query(HearingDocket).filter(
        HearingDocket.hearing_id == hearing_id,
        HearingDocket.docket_id == docket_id
    ).first()

    if not existing:
        link = HearingDocket(
            hearing_id=hearing_id,
            docket_id=docket_id,
        )
        db.add(link)
