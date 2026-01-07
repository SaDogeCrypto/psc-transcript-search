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
    confidence_score: Optional[int] = None  # 0-100 smart validation score
    match_type: Optional[str] = None  # exact, fuzzy, none
    review_reason: Optional[str] = None
    transcript_context: Optional[str] = None
    suggestions: List[ReviewSuggestion]


class ReviewAction(BaseModel):
    action: str  # "approve", "link", "correct", "invalid", "skip", "reject"
    correct_entity_id: Optional[int] = None
    corrected_text: Optional[str] = None
    notes: Optional[str] = None


class ReviewQueueStats(BaseModel):
    total: int
    dockets: int
    topics: int
    utilities: int
    hearings: int = 0  # Number of unique hearings with items needing review


# =============================================================================
# HEARING-GROUPED REVIEW SCHEMAS
# =============================================================================

class EntityReviewItem(BaseModel):
    """Single entity within a hearing review."""
    id: int
    entity_type: str  # topic, utility, docket
    entity_id: int
    name: str
    role: Optional[str] = None  # For utilities: applicant, intervenor, subject
    category: Optional[str] = None  # For topics
    context: Optional[str] = None
    confidence: str
    confidence_score: Optional[int] = None
    match_type: Optional[str] = None
    review_reason: Optional[str] = None
    # For dockets
    known_docket_id: Optional[int] = None
    known_utility: Optional[str] = None
    known_title: Optional[str] = None
    utility_match: bool = False  # True if docket utility matches extracted utilities
    suggestions: List[ReviewSuggestion] = []


class HearingReviewItem(BaseModel):
    """All entities for a single hearing grouped together."""
    hearing_id: int
    hearing_title: str
    hearing_date: Optional[str] = None
    state_code: Optional[str] = None
    # Grouped entities
    topics: List[EntityReviewItem] = []
    utilities: List[EntityReviewItem] = []
    dockets: List[EntityReviewItem] = []
    # Summary stats
    total_entities: int = 0
    needs_review_count: int = 0
    lowest_confidence: Optional[int] = None
    # Cross-entity validation
    utility_docket_matches: int = 0  # How many dockets have matching utilities


class BulkReviewAction(BaseModel):
    """Bulk action on multiple entities."""
    action: str  # "approve_all", "approve_high_confidence", "reject_low_confidence"
    confidence_threshold: int = 80  # For threshold-based actions
    entity_ids: Optional[List[dict]] = None  # For selective: [{"type": "topic", "id": 123}, ...]
    notes: Optional[str] = None


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
    from app.models.database import Docket, HearingTopic, HearingUtility, HearingDocket, Topic

    # Count dockets needing review (via HearingDocket)
    docket_count = db.query(HearingDocket).filter(
        HearingDocket.needs_review == True
    ).count()

    # Count topics needing review
    topic_count = db.query(HearingTopic).filter(
        HearingTopic.needs_review == True
    ).count()

    # Count utilities needing review
    utility_count = db.query(HearingUtility).filter(
        HearingUtility.needs_review == True
    ).count()

    # Count unique hearings with items needing review
    hearing_ids = set()
    for (hid,) in db.query(HearingDocket.hearing_id).filter(HearingDocket.needs_review == True).all():
        hearing_ids.add(hid)
    for (hid,) in db.query(HearingTopic.hearing_id).filter(HearingTopic.needs_review == True).all():
        hearing_ids.add(hid)
    for (hid,) in db.query(HearingUtility.hearing_id).filter(HearingUtility.needs_review == True).all():
        hearing_ids.add(hid)

    return ReviewQueueStats(
        total=docket_count + topic_count + utility_count,
        dockets=docket_count,
        topics=topic_count,
        utilities=utility_count,
        hearings=len(hearing_ids)
    )


@router.get("/hearings")
def get_hearing_review_queue(
    state: Optional[str] = Query(None, description="Filter by state code"),
    limit: int = Query(20, le=50, description="Max hearings to return"),
    db: Session = Depends(get_db)
) -> List[HearingReviewItem]:
    """
    Get review items grouped by hearing.
    Returns all entities for each hearing together for contextual review.
    """
    from app.models.database import (
        Hearing, State,
        HearingTopic, Topic,
        HearingUtility, Utility,
        HearingDocket, Docket, KnownDocket
    )

    # Find hearings with items needing review
    # Get hearing IDs from all entity types
    hearing_ids_with_review = set()

    # From dockets
    docket_query = db.query(HearingDocket.hearing_id).filter(
        HearingDocket.needs_review == True
    )
    if state:
        docket_query = docket_query.join(Hearing).join(State).filter(State.code == state.upper())
    for (hid,) in docket_query.all():
        hearing_ids_with_review.add(hid)

    # From topics
    topic_query = db.query(HearingTopic.hearing_id).filter(
        HearingTopic.needs_review == True
    )
    if state:
        topic_query = topic_query.join(Hearing).join(State).filter(State.code == state.upper())
    for (hid,) in topic_query.all():
        hearing_ids_with_review.add(hid)

    # From utilities
    utility_query = db.query(HearingUtility.hearing_id).filter(
        HearingUtility.needs_review == True
    )
    if state:
        utility_query = utility_query.join(Hearing).join(State).filter(State.code == state.upper())
    for (hid,) in utility_query.all():
        hearing_ids_with_review.add(hid)

    if not hearing_ids_with_review:
        return []

    # Get hearing details
    hearings = db.query(Hearing, State).join(
        State, Hearing.state_id == State.id
    ).filter(
        Hearing.id.in_(hearing_ids_with_review)
    ).order_by(Hearing.hearing_date.desc()).limit(limit).all()

    results = []

    for hearing, hearing_state in hearings:
        item = HearingReviewItem(
            hearing_id=hearing.id,
            hearing_title=hearing.title[:150] if hearing.title else "",
            hearing_date=str(hearing.hearing_date) if hearing.hearing_date else None,
            state_code=hearing_state.code,
        )

        # Collect utility names for cross-validation
        utility_names = set()

        # Get topics for this hearing
        topics = db.query(HearingTopic, Topic).join(
            Topic, HearingTopic.topic_id == Topic.id
        ).filter(
            HearingTopic.hearing_id == hearing.id,
            HearingTopic.needs_review == True
        ).all()

        for ht, topic in topics:
            suggestions = get_topic_suggestions(db, topic.name)
            item.topics.append(EntityReviewItem(
                id=ht.id,
                entity_type="topic",
                entity_id=topic.id,
                name=topic.name,
                category=topic.category,
                context=ht.context_summary,
                confidence=ht.confidence or "auto",
                confidence_score=ht.confidence_score,
                match_type=ht.match_type,
                review_reason=ht.review_reason,
                suggestions=[ReviewSuggestion(**s) for s in suggestions]
            ))

        # Get utilities for this hearing
        utilities = db.query(HearingUtility, Utility).join(
            Utility, HearingUtility.utility_id == Utility.id
        ).filter(
            HearingUtility.hearing_id == hearing.id,
            HearingUtility.needs_review == True
        ).all()

        for hu, utility in utilities:
            utility_names.add(utility.name.lower())
            if utility.normalized_name:
                utility_names.add(utility.normalized_name.lower())
            for alias in (utility.aliases or []):
                utility_names.add(alias.lower())

            suggestions = get_utility_suggestions(db, utility.name)
            item.utilities.append(EntityReviewItem(
                id=hu.id,
                entity_type="utility",
                entity_id=utility.id,
                name=utility.name,
                role=hu.role,
                context=hu.context_summary,
                confidence=hu.confidence or "auto",
                confidence_score=hu.confidence_score,
                match_type=hu.match_type,
                review_reason=hu.review_reason,
                suggestions=[ReviewSuggestion(**s) for s in suggestions]
            ))

        # Get dockets for this hearing
        dockets = db.query(HearingDocket, Docket).join(
            Docket, HearingDocket.docket_id == Docket.id
        ).filter(
            HearingDocket.hearing_id == hearing.id,
            HearingDocket.needs_review == True
        ).all()

        for hd, docket in dockets:
            # Get known docket info
            known_utility = None
            known_title = None
            if docket.known_docket_id:
                known = db.query(KnownDocket).filter(KnownDocket.id == docket.known_docket_id).first()
                if known:
                    known_utility = known.utility_name
                    known_title = known.title

            # Check if docket utility matches extracted utilities
            utility_match = False
            if known_utility:
                if known_utility.lower() in utility_names:
                    utility_match = True
                else:
                    # Fuzzy check
                    for uname in utility_names:
                        if known_utility.lower() in uname or uname in known_utility.lower():
                            utility_match = True
                            break

            if utility_match:
                item.utility_docket_matches += 1

            suggestions = get_docket_suggestions(db, docket.docket_number, hearing_state.code)
            item.dockets.append(EntityReviewItem(
                id=hd.docket_id,  # Use docket_id since HearingDocket has composite key
                entity_type="docket",
                entity_id=docket.id,
                name=docket.docket_number,
                context=hd.context_summary,
                confidence=docket.confidence or "unverified",
                confidence_score=hd.confidence_score,
                match_type=hd.match_type,
                review_reason=hd.review_reason,
                known_docket_id=docket.known_docket_id,
                known_utility=known_utility,
                known_title=known_title,
                utility_match=utility_match,
                suggestions=[ReviewSuggestion(**s) for s in suggestions]
            ))

        # Calculate summary stats
        item.total_entities = len(item.topics) + len(item.utilities) + len(item.dockets)
        item.needs_review_count = item.total_entities  # All are needs_review since we filtered

        # Find lowest confidence
        all_scores = []
        for t in item.topics:
            if t.confidence_score is not None:
                all_scores.append(t.confidence_score)
        for u in item.utilities:
            if u.confidence_score is not None:
                all_scores.append(u.confidence_score)
        for d in item.dockets:
            if d.confidence_score is not None:
                all_scores.append(d.confidence_score)

        if all_scores:
            item.lowest_confidence = min(all_scores)

        results.append(item)

    return results


@router.post("/hearings/{hearing_id}/bulk")
def bulk_review_hearing(
    hearing_id: int,
    action: BulkReviewAction,
    db: Session = Depends(get_db)
):
    """
    Bulk approve/reject entities for a hearing.
    Actions:
    - approve_all: Approve all entities
    - approve_high_confidence: Approve entities above threshold
    - reject_all: Reject all entities
    """
    from app.models.database import HearingTopic, HearingUtility, HearingDocket, Docket

    approved = 0
    rejected = 0

    if action.action == "approve_all":
        # Approve all topics
        topics = db.query(HearingTopic).filter(
            HearingTopic.hearing_id == hearing_id,
            HearingTopic.needs_review == True
        ).all()
        for ht in topics:
            ht.needs_review = False
            ht.confidence = "verified"
            ht.review_notes = action.notes or "Bulk approved"
            approved += 1

        # Approve all utilities
        utilities = db.query(HearingUtility).filter(
            HearingUtility.hearing_id == hearing_id,
            HearingUtility.needs_review == True
        ).all()
        for hu in utilities:
            hu.needs_review = False
            hu.confidence = "verified"
            hu.review_notes = action.notes or "Bulk approved"
            approved += 1

        # Approve all dockets
        dockets = db.query(HearingDocket).filter(
            HearingDocket.hearing_id == hearing_id,
            HearingDocket.needs_review == True
        ).all()
        for hd in dockets:
            hd.needs_review = False
            hd.review_notes = action.notes or "Bulk approved"
            # Also update docket confidence
            docket = db.query(Docket).filter(Docket.id == hd.docket_id).first()
            if docket:
                docket.confidence = "verified"
                docket.review_status = "reviewed"
            approved += 1

    elif action.action == "approve_high_confidence":
        threshold = action.confidence_threshold

        # Topics
        topics = db.query(HearingTopic).filter(
            HearingTopic.hearing_id == hearing_id,
            HearingTopic.needs_review == True,
            HearingTopic.confidence_score >= threshold
        ).all()
        for ht in topics:
            ht.needs_review = False
            ht.confidence = "verified"
            ht.review_notes = f"Auto-approved (score >= {threshold})"
            approved += 1

        # Utilities
        utilities = db.query(HearingUtility).filter(
            HearingUtility.hearing_id == hearing_id,
            HearingUtility.needs_review == True,
            HearingUtility.confidence_score >= threshold
        ).all()
        for hu in utilities:
            hu.needs_review = False
            hu.confidence = "verified"
            hu.review_notes = f"Auto-approved (score >= {threshold})"
            approved += 1

        # Dockets
        dockets = db.query(HearingDocket).filter(
            HearingDocket.hearing_id == hearing_id,
            HearingDocket.needs_review == True,
            HearingDocket.confidence_score >= threshold
        ).all()
        for hd in dockets:
            hd.needs_review = False
            hd.review_notes = f"Auto-approved (score >= {threshold})"
            docket = db.query(Docket).filter(Docket.id == hd.docket_id).first()
            if docket:
                docket.confidence = "verified"
                docket.review_status = "reviewed"
            approved += 1

    elif action.action == "reject_all":
        # Delete all entity links
        db.query(HearingTopic).filter(
            HearingTopic.hearing_id == hearing_id,
            HearingTopic.needs_review == True
        ).delete()

        db.query(HearingUtility).filter(
            HearingUtility.hearing_id == hearing_id,
            HearingUtility.needs_review == True
        ).delete()

        dockets = db.query(HearingDocket).filter(
            HearingDocket.hearing_id == hearing_id,
            HearingDocket.needs_review == True
        ).all()
        for hd in dockets:
            docket = db.query(Docket).filter(Docket.id == hd.docket_id).first()
            if docket:
                docket.review_status = "rejected"
            rejected += 1
        db.query(HearingDocket).filter(
            HearingDocket.hearing_id == hearing_id,
            HearingDocket.needs_review == True
        ).delete()

    else:
        raise HTTPException(status_code=400, detail=f"Unknown action: {action.action}")

    # Check if all entities for this hearing have been reviewed
    # If so, advance the hearing to the next pipeline stage
    from app.models.database import Hearing

    # Flush to ensure our changes are visible in subsequent queries
    db.flush()

    remaining_topics = db.query(HearingTopic).filter(
        HearingTopic.hearing_id == hearing_id,
        HearingTopic.needs_review == True
    ).count()

    remaining_utilities = db.query(HearingUtility).filter(
        HearingUtility.hearing_id == hearing_id,
        HearingUtility.needs_review == True
    ).count()

    remaining_dockets = db.query(HearingDocket).filter(
        HearingDocket.hearing_id == hearing_id,
        HearingDocket.needs_review == True
    ).count()

    hearing_advanced = False
    if remaining_topics == 0 and remaining_utilities == 0 and remaining_dockets == 0:
        # All entities reviewed - advance hearing to smart_extracted for Extract stage
        hearing = db.query(Hearing).filter(Hearing.id == hearing_id).first()
        if hearing and hearing.status in ('analyzed', 'smart_extracting', 'smart_extracted'):
            hearing.status = 'smart_extracted'
            hearing_advanced = True

    db.commit()

    return {
        "message": f"Bulk review complete",
        "approved": approved,
        "rejected": rejected,
        "hearing_advanced": hearing_advanced
    }


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

    # Get dockets needing review
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
            HearingDocket.needs_review == True
        )

        if state:
            docket_query = docket_query.join(
                State, Hearing.state_id == State.id
            ).filter(State.code == state.upper())

        docket_query = docket_query.order_by(
            HearingDocket.confidence_score.asc().nullsfirst(),
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
                confidence_score=hd.confidence_score,
                match_type=hd.match_type,
                review_reason=hd.review_reason,
                transcript_context=hd.context_summary,
                suggestions=[ReviewSuggestion(**s) for s in suggestions]
            ))

    # Get topics needing review
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
            HearingTopic.needs_review == True
        )

        if state:
            topic_query = topic_query.join(
                State, Hearing.state_id == State.id
            ).filter(State.code == state.upper())

        topic_query = topic_query.order_by(
            HearingTopic.confidence_score.asc().nullsfirst(),
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
                confidence_score=ht.confidence_score,
                match_type=ht.match_type,
                review_reason=ht.review_reason,
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
            HearingUtility.confidence_score.asc().nullsfirst(),
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
                confidence_score=hu.confidence_score,
                match_type=hu.match_type,
                review_reason=hu.review_reason,
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

    if action.action == "approve":
        # Approve the docket as-is
        docket.confidence = "verified"
        docket.review_status = "reviewed"
        # Also update any HearingDocket records
        for hd in docket.hearing_dockets:
            hd.needs_review = False

    elif action.action == "reject" or action.action == "invalid":
        # Mark as not a real docket
        docket.review_status = "invalid"
        docket.confidence = "invalid"
        # Also update any HearingDocket records
        for hd in docket.hearing_dockets:
            hd.needs_review = False

    elif action.action == "link":
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

        # Also update any HearingDocket records
        for hd in docket.hearing_dockets:
            hd.needs_review = False

    elif action.action == "correct":
        # Fix the docket number
        if not action.corrected_text:
            raise HTTPException(status_code=400, detail="corrected_text required for correct action")

        docket.original_extracted = original_text
        docket.docket_number = action.corrected_text
        docket.review_status = "reviewed"
        # Also update any HearingDocket records
        for hd in docket.hearing_dockets:
            hd.needs_review = False

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


@router.post("/hearing_docket/{hearing_id}/{docket_id}")
def review_hearing_docket(
    hearing_id: int,
    docket_id: int,
    action: ReviewAction,
    db: Session = Depends(get_db)
):
    """Process review action for a hearing_docket link (approve/reject/link individual entity)."""
    from app.models.database import HearingDocket, Docket, KnownDocket, EntityCorrection

    # HearingDocket uses composite key (hearing_id, docket_id)
    hd = db.query(HearingDocket).filter(
        HearingDocket.hearing_id == hearing_id,
        HearingDocket.docket_id == docket_id
    ).first()
    if not hd:
        raise HTTPException(status_code=404, detail="HearingDocket not found")

    docket = db.query(Docket).filter(Docket.id == hd.docket_id).first()
    original_text = docket.docket_number if docket else ""

    if action.action == "approve":
        # Approve this hearing-docket link
        hd.needs_review = False
        if docket:
            docket.confidence = "verified"
            docket.review_status = "reviewed"

    elif action.action == "link":
        # Link to a known docket
        if not action.correct_entity_id:
            raise HTTPException(status_code=400, detail="correct_entity_id required for link action")

        known = db.query(KnownDocket).filter(KnownDocket.id == action.correct_entity_id).first()
        if not known:
            raise HTTPException(status_code=404, detail="Known docket not found")

        # Update the docket with the known docket info
        if docket:
            docket.known_docket_id = known.id
            docket.confidence = "verified"
            docket.review_status = "reviewed"
            # Copy metadata from known docket
            if known.utility_name:
                docket.company = known.utility_name
            if known.sector:
                docket.sector = known.sector
            if known.title:
                docket.title = known.title

        hd.needs_review = False

    elif action.action == "reject" or action.action == "invalid":
        # Remove this hearing-docket link
        db.delete(hd)

    elif action.action == "skip":
        pass

    else:
        raise HTTPException(status_code=400, detail=f"Unknown action: {action.action}")

    # Record correction
    if action.action in ("reject", "invalid", "link"):
        correction = EntityCorrection(
            entity_type="docket",
            hearing_id=hd.hearing_id,
            original_text=original_text,
            corrected_text=action.corrected_text,
            correct_entity_id=action.correct_entity_id,
            correction_type=action.action,
            created_by="admin",
        )
        db.add(correction)

    hd.review_notes = action.notes
    db.commit()

    return {"message": "Review processed"}


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

    if action.action == "approve":
        # Approve the topic as-is
        ht.confidence = "verified"
        ht.needs_review = False

    elif action.action == "reject" or action.action == "invalid":
        # Remove the topic link
        db.delete(ht)

    elif action.action == "link":
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

    if action.action == "approve":
        # Approve the utility as-is
        hu.confidence = "verified"
        hu.needs_review = False

    elif action.action == "reject" or action.action == "invalid":
        # Remove the utility link
        db.delete(hu)

    elif action.action == "link":
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


# =============================================================================
# EXTRACTION MATCH FROM SOURCE
# =============================================================================

class MatchFromSourceRequest(BaseModel):
    """Request to match an extraction to a verified source docket."""
    notes: Optional[str] = None


class MatchFromSourceResponse(BaseModel):
    """Response after matching extraction to source docket."""
    success: bool
    message: str
    known_docket_id: Optional[int] = None
    docket_id: Optional[int] = None
    extraction_status: Optional[str] = None
    scraped_data: Optional[dict] = None


@router.post("/extraction/{extraction_id}/match-from-source")
async def match_extraction_from_source(
    extraction_id: int,
    request: MatchFromSourceRequest = MatchFromSourceRequest(),
    db: Session = Depends(get_db)
) -> MatchFromSourceResponse:
    """
    Match an extraction to a docket by verifying and scraping from the source PSC website.

    This will:
    1. Verify the docket exists on the state PSC website
    2. Create or update the known_docket record with scraped metadata
    3. Create or update the docket entry
    4. Link the extraction to the docket
    5. Mark the extraction as accepted
    """
    from app.services.docket_scraper import DocketScraper
    from app.models.database import KnownDocket, Docket, Hearing, HearingDocket
    from app.services.docket_parser import parse_docket

    # Get the extraction with hearing info
    result = db.execute(text("""
        SELECT ed.id, ed.raw_text, ed.normalized_id, ed.hearing_id,
               s.code as state_code, h.state_id
        FROM extracted_dockets ed
        JOIN hearings h ON ed.hearing_id = h.id
        JOIN states s ON h.state_id = s.id
        WHERE ed.id = :id
    """), {"id": extraction_id})
    row = result.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Extraction not found")

    extraction_id = row[0]
    docket_number = row[1]
    normalized_id = row[2]
    hearing_id = row[3]
    state_code = row[4]
    state_id = row[5]

    # Parse the docket ID to extract structured fields
    parsed = parse_docket(docket_number, state_code)

    # Verify and save using unified scraper
    scraper = DocketScraper(db)
    scraped = await scraper.verify_and_save(state_code, docket_number, extraction_id)

    if not scraped.found:
        return MatchFromSourceResponse(
            success=False,
            message=f"Docket not found on source: {scraped.error or 'Not found'}",
            scraped_data=scraped.to_dict()
        )

    # Get the known_docket that was created/updated
    known = db.execute(text(
        "SELECT id, title, utility_name, utility_type FROM known_dockets WHERE normalized_id = :nid"
    ), {"nid": normalized_id}).fetchone()

    if not known:
        return MatchFromSourceResponse(
            success=False,
            message="Failed to create known_docket record"
        )

    known_docket_id = known[0]

    # Update known_docket with parsed fields (parser supplements scraper)
    # Only update fields that the scraper didn't provide
    db.execute(text("""
        UPDATE known_dockets SET
            year = COALESCE(year, :parsed_year),
            case_number = COALESCE(case_number, :case_number),
            raw_prefix = COALESCE(raw_prefix, :prefix),
            raw_suffix = COALESCE(raw_suffix, :suffix),
            docket_type = COALESCE(docket_type, :docket_type),
            company_code = COALESCE(company_code, :company_code),
            sector = COALESCE(sector, :utility_sector)
        WHERE id = :id
    """), {
        "id": known_docket_id,
        "parsed_year": parsed.year,
        "case_number": parsed.case_number,
        "prefix": parsed.prefix,
        "suffix": parsed.suffix,
        "docket_type": parsed.docket_type,
        "company_code": parsed.company_code,
        "utility_sector": parsed.utility_sector
    })

    # Create or update docket entry
    existing_docket = db.execute(text(
        "SELECT id FROM dockets WHERE normalized_id = :nid"
    ), {"nid": normalized_id}).fetchone()

    if existing_docket:
        docket_id = existing_docket[0]
        # Update with new info
        db.execute(text("""
            UPDATE dockets SET
                known_docket_id = :known_id,
                title = COALESCE(:title, title),
                company = COALESCE(:company, company),
                confidence = 'verified',
                review_status = 'reviewed'
            WHERE id = :id
        """), {
            "id": docket_id,
            "known_id": known_docket_id,
            "title": scraped.title,
            "company": scraped.utility_name or scraped.filing_party
        })
    else:
        # Create new docket
        db.execute(text("""
            INSERT INTO dockets
            (state_id, docket_number, normalized_id, known_docket_id, title, company,
             confidence, review_status, first_seen_at, last_mentioned_at, mention_count)
            VALUES
            (:state_id, :docket_number, :normalized_id, :known_id, :title, :company,
             'verified', 'reviewed', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 1)
        """), {
            "state_id": state_id,
            "docket_number": docket_number,
            "normalized_id": normalized_id,
            "known_id": known_docket_id,
            "title": scraped.title,
            "company": scraped.utility_name or scraped.filing_party
        })
        db.flush()
        docket_id = db.execute(text(
            "SELECT id FROM dockets WHERE normalized_id = :nid"
        ), {"nid": normalized_id}).fetchone()[0]

    # Create hearing-docket link if not exists
    existing_link = db.execute(text(
        "SELECT hearing_id FROM hearing_dockets WHERE hearing_id = :hid AND docket_id = :did"
    ), {"hid": hearing_id, "did": docket_id}).fetchone()

    if not existing_link:
        db.execute(text("""
            INSERT INTO hearing_dockets (hearing_id, docket_id)
            VALUES (:hid, :did)
        """), {"hid": hearing_id, "did": docket_id})

    # Update the extraction to accepted, including parsed fields
    db.execute(text("""
        UPDATE extracted_dockets SET
            status = 'accepted',
            matched_known_docket_id = :known_id,
            final_docket_id = :docket_id,
            review_decision = 'matched_from_source',
            reviewed_by = 'admin',
            reviewed_at = CURRENT_TIMESTAMP,
            review_notes = :notes,
            parsed_year = :parsed_year,
            parsed_utility_sector = :parsed_sector,
            parsed_docket_type = :parsed_type,
            parsed_company_code = :parsed_company
        WHERE id = :id
    """), {
        "id": extraction_id,
        "known_id": known_docket_id,
        "docket_id": docket_id,
        "notes": request.notes or f"Matched from source: {scraped.title}",
        "parsed_year": parsed.year,
        "parsed_sector": parsed.utility_sector,
        "parsed_type": parsed.docket_type,
        "parsed_company": parsed.company_code
    })

    db.commit()

    return MatchFromSourceResponse(
        success=True,
        message=f"Successfully matched to {normalized_id}",
        known_docket_id=known_docket_id,
        docket_id=docket_id,
        extraction_status="accepted",
        scraped_data={
            "title": scraped.title,
            "utility_type": scraped.utility_type,
            "company": scraped.utility_name or scraped.filing_party,
            "filing_date": scraped.filing_date.isoformat() if scraped.filing_date else None,
            "status": scraped.status,
            "url": scraped.source_url,
            "parsed": {
                "year": parsed.year,
                "utility_sector": parsed.utility_sector,
                "docket_type": parsed.docket_type,
                "company_code": parsed.company_code,
                "case_number": parsed.case_number
            }
        }
    )


# =============================================================================
# DOCKET VERIFICATION FROM SOURCE
# =============================================================================

# State PSC lookup URLs
STATE_LOOKUP_URLS = {
    "GA": "https://psc.ga.gov/facts-advanced-search/docket/?docketId={docket}",
    "TX": "https://interchange.puc.texas.gov/search/documents/?controlNumber={docket}&itemNumber=1",
    "FL": "https://www.floridapsc.com/ClerkOffice/DocketFiling?docket={docket}",
    "OH": "https://dis.puc.state.oh.us/CaseRecord.aspx?CaseNo={docket}",
}


class DocketVerificationResult(BaseModel):
    """Result of verifying a docket on the source website."""
    found: bool
    docket_number: str
    state_code: str
    title: Optional[str] = None
    company: Optional[str] = None
    filing_date: Optional[str] = None
    status: Optional[str] = None
    utility_type: Optional[str] = None
    url: Optional[str] = None
    error: Optional[str] = None


@router.get("/extraction/{extraction_id}/verify")
async def verify_extraction_on_source(
    extraction_id: int,
    save: bool = Query(False, description="Save verified docket to known_dockets"),
    db: Session = Depends(get_db)
) -> DocketVerificationResult:
    """
    Verify an extraction candidate by looking it up on the state's PSC website.

    This helps confirm that new docket candidates actually exist.
    If save=True, creates or updates the known_dockets record.
    """
    from app.services.docket_scraper import DocketScraper

    # Get the extraction
    result = db.execute(text(
        "SELECT ed.raw_text, s.code as state_code FROM extracted_dockets ed "
        "JOIN hearings h ON ed.hearing_id = h.id "
        "JOIN states s ON h.state_id = s.id "
        "WHERE ed.id = :id"
    ), {"id": extraction_id})
    row = result.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Extraction not found")

    docket_number = row[0]
    state_code = row[1]

    # Use unified scraper
    scraper = DocketScraper(db)

    if save:
        scraped = await scraper.verify_and_save(state_code, docket_number, extraction_id)
    else:
        scraped = await scraper.scrape_docket(state_code, docket_number)

    return DocketVerificationResult(
        found=scraped.found,
        docket_number=scraped.docket_number,
        state_code=scraped.state_code,
        title=scraped.title,
        company=scraped.utility_name or scraped.filing_party,
        filing_date=scraped.filing_date.isoformat() if scraped.filing_date else None,
        status=scraped.status,
        utility_type=scraped.utility_type,
        url=scraped.source_url,
        error=scraped.error
    )


@router.get("/docket/{state_code}/{docket_number}/verify")
async def verify_docket_direct(
    state_code: str,
    docket_number: str,
    save: bool = Query(False, description="Save verified docket to known_dockets"),
    db: Session = Depends(get_db)
) -> DocketVerificationResult:
    """
    Directly verify a docket by state code and docket number.

    Useful for ad-hoc lookups without an extraction record.
    """
    from app.services.docket_scraper import DocketScraper

    scraper = DocketScraper(db)

    if save:
        scraped = await scraper.verify_and_save(state_code.upper(), docket_number)
    else:
        scraped = await scraper.scrape_docket(state_code.upper(), docket_number)

    return DocketVerificationResult(
        found=scraped.found,
        docket_number=scraped.docket_number,
        state_code=scraped.state_code,
        title=scraped.title,
        company=scraped.utility_name or scraped.filing_party,
        filing_date=scraped.filing_date.isoformat() if scraped.filing_date else None,
        status=scraped.status,
        utility_type=scraped.utility_type,
        url=scraped.source_url,
        error=scraped.error
    )


@router.get("/states/configs")
async def get_state_configs(
    db: Session = Depends(get_db)
) -> List[dict]:
    """Get all state PSC configurations."""
    result = db.execute(text(
        "SELECT state_code, state_name, commission_name, commission_abbreviation, "
        "website_url, docket_detail_url_template, scraper_type, enabled, "
        "last_scrape_at, dockets_count "
        "FROM state_psc_configs ORDER BY state_name"
    ))

    configs = []
    for row in result.mappings():
        configs.append(dict(row))

    return configs


def _parse_ga_verification(html: str, docket_number: str, state_code: str, url: str) -> DocketVerificationResult:
    """Parse Georgia PSC page for docket info."""
    import re

    # Check if docket exists
    if f"#{docket_number}" not in html and docket_number not in html:
        return DocketVerificationResult(
            found=False,
            docket_number=docket_number,
            state_code=state_code,
            url=url
        )

    # Extract info from page - Georgia uses <h6> labels followed by values
    title = None
    company = None
    filing_date = None
    status = None
    industry = None

    # Title: appears after <h6>Title:</h6> or similar
    title_match = re.search(r'<h6[^>]*>\s*Title[:\s]*</h6>\s*([^<]+)', html, re.IGNORECASE)
    if title_match:
        title = title_match.group(1).strip()

    # Industry (used as company/sector indicator)
    industry_match = re.search(r'<h6[^>]*>\s*Industry[:\s]*</h6>\s*([^<]+)', html, re.IGNORECASE)
    if industry_match:
        industry = industry_match.group(1).strip()

    # Date
    date_match = re.search(r'<h6[^>]*>\s*Date[:\s]*</h6>\s*([^<]+)', html, re.IGNORECASE)
    if date_match:
        filing_date = date_match.group(1).strip()

    # Status
    status_match = re.search(r'<h6[^>]*>\s*Status[:\s]*</h6>\s*([^<]+)', html, re.IGNORECASE)
    if status_match:
        status = status_match.group(1).strip()

    # Look for company name in the content
    company_patterns = [
        r'Georgia\s+Power\s+Company',
        r'Atlanta\s+Gas\s+Light',
        r'Southern\s+Company\s+Gas',
        r'Liberty\s+Utilities',
    ]
    for pattern in company_patterns:
        match = re.search(pattern, html, re.IGNORECASE)
        if match:
            company = match.group(0)
            break

    # If no specific company found but we have industry, use that
    if not company and industry:
        company = f"{industry} utility"

    return DocketVerificationResult(
        found=True,
        docket_number=docket_number,
        state_code=state_code,
        title=title,
        company=company,
        filing_date=filing_date,
        status=status,
        url=url
    )


async def _parse_tx_verification(html: str, docket_number: str, state_code: str, url: str) -> DocketVerificationResult:
    """Parse Texas PUC documents page for docket info.

    Uses the /search/documents/ endpoint which has server-rendered HTML with
    Case Style, File Stamp, and Filing Party fields. Also fetches the PDF
    to extract utility type.
    """
    import re
    import httpx

    # Check if we got results - look for indicators of no results
    if "No filings found" in html or "0 results" in html.lower() or "no records" in html.lower():
        return DocketVerificationResult(
            found=False,
            docket_number=docket_number,
            state_code=state_code,
            url=url
        )

    # Check if docket number appears in page
    if docket_number not in html and f"controlNumber={docket_number}" not in url.lower():
        return DocketVerificationResult(
            found=False,
            docket_number=docket_number,
            state_code=state_code,
            url=url
        )

    # Parse the server-rendered fields
    # Format: <p><strong>Case Style</strong> &nbsp; Title here</p>
    title = None
    company = None
    filing_date = None
    utility_type = None

    # Case Style (title)
    case_style_match = re.search(r'<strong>Case Style</strong>\s*(?:&nbsp;|\s)*([^<]+)', html, re.IGNORECASE)
    if case_style_match:
        title = case_style_match.group(1).strip()

    # File Stamp (filing date)
    file_stamp_match = re.search(r'<strong>File Stamp</strong>\s*(?:&nbsp;|\s)*([^<]+)', html, re.IGNORECASE)
    if file_stamp_match:
        filing_date = file_stamp_match.group(1).strip()

    # Filing Party (company)
    filing_party_match = re.search(r'<strong>Filing Party</strong>\s*(?:&nbsp;|\s)*([^<]+)', html, re.IGNORECASE)
    if filing_party_match:
        company = filing_party_match.group(1).strip()

    # Try to extract PDF URL and parse for utility type
    pdf_match = re.search(r'href="(https://interchange\.puc\.texas\.gov/Documents/[^"]+\.PDF)"', html, re.IGNORECASE)
    if pdf_match:
        pdf_url = pdf_match.group(1)
        try:
            async with httpx.AsyncClient(timeout=10.0, verify=False) as client:
                pdf_response = await client.get(pdf_url)
                if pdf_response.status_code == 200:
                    utility_type = _extract_utility_type_from_pdf(pdf_response.content)
        except Exception:
            pass  # PDF parsing is best-effort

    return DocketVerificationResult(
        found=True,
        docket_number=docket_number,
        state_code=state_code,
        title=title,
        company=company,
        filing_date=filing_date,
        status=None,
        utility_type=utility_type,
        url=url
    )


def _extract_utility_type_from_pdf(pdf_bytes: bytes) -> Optional[str]:
    """Extract utility type from Texas PUC Control Number Request Form PDF.

    Uses PyMuPDF to extract text which properly captures checkbox markers.
    The checked checkbox appears as '~' before the utility type name.
    Pattern: '~ ELECTRIC ~' means Electric is checked.
    """
    try:
        import fitz  # PyMuPDF
        from io import BytesIO

        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        text = ""
        for page in doc:
            text += page.get_text() + "\n"
        doc.close()

        # Look for checkbox markers - '~' before the type name indicates checked
        # Pattern in PDF: "~ ELECTRIC ~" means Electric checkbox is marked
        lines = text.split('\n')
        checked_types = []

        for line in lines:
            line_stripped = line.strip()
            # Check for pattern: ~ TYPE or ~ TYPE ~
            if line_stripped.startswith('~'):
                # Extract the type name after the ~
                parts = line_stripped.split()
                if len(parts) >= 2:
                    type_name = parts[1].upper()
                    if type_name in ['ELECTRIC', 'TELEPHONE', 'WATER', 'OTHER']:
                        checked_types.append(type_name.capitalize())

        if checked_types:
            return ", ".join(checked_types)

        # Fallback to keyword-based detection for older PDFs without checkbox format
        text_upper = text.upper()
        electric_indicators = ["ERCOT", "POWER", "ENERGY FUND", "RELIABILITY", "GRID",
                               "GENERATION", "FUEL", "ANCILLARY", "INTERCONNECTION"]
        telephone_indicators = ["TELECOM", "COMMUNICATIONS", "CARRIER",
                                "LONG DISTANCE", "LOCAL EXCHANGE"]

        electric_score = sum(1 for ind in electric_indicators if ind in text_upper)
        telephone_score = sum(1 for ind in telephone_indicators if ind in text_upper)

        if electric_score > telephone_score:
            return "Electric"
        if telephone_score > electric_score:
            return "Telephone"

        return None
    except Exception:
        return None
