"""
Florida Entity Review API routes.

Endpoints for reviewing and linking extracted entities to canonical records.
"""
from datetime import datetime
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, text
from sqlalchemy.orm import Session

from florida.models import (
    get_db,
    FLHearing,
    FLDocket,
    FLUtility,
    FLTopic,
    FLHearingDocket,
    FLHearingUtility,
    FLHearingTopic,
    FLEntity,
    FLEntityCorrection,
    FLAnalysis,
)

router = APIRouter(prefix="/admin/review", tags=["review"])


# =============================================================================
# Pydantic Models
# =============================================================================

class ReviewQueueStats(BaseModel):
    total: int
    dockets: int
    utilities: int
    topics: int
    hearings_with_pending: int


class DocketLinkRequest(BaseModel):
    docket_id: int
    is_primary: bool = False
    context_summary: Optional[str] = None


class UtilityLinkRequest(BaseModel):
    utility_id: int
    role: Optional[str] = None  # applicant, intervenor, subject
    context_summary: Optional[str] = None


class TopicLinkRequest(BaseModel):
    topic_id: int
    relevance_score: Optional[float] = None
    context_summary: Optional[str] = None


class ReviewActionRequest(BaseModel):
    action: str  # approve, reject, link, correct, skip
    correct_entity_id: Optional[int] = None
    corrected_text: Optional[str] = None
    notes: Optional[str] = None


class BulkReviewRequest(BaseModel):
    action: str  # approve_all, approve_high_confidence, reject_all
    confidence_threshold: int = 80
    notes: Optional[str] = None


class UtilityCreate(BaseModel):
    name: str
    normalized_name: Optional[str] = None
    utility_type: Optional[str] = None
    sectors: Optional[List[str]] = None
    aliases: Optional[List[str]] = None


class TopicCreate(BaseModel):
    name: str
    slug: Optional[str] = None
    category: Optional[str] = None
    description: Optional[str] = None


# =============================================================================
# Review Queue Stats
# =============================================================================

@router.get("/stats")
def get_review_stats(db: Session = Depends(get_db)) -> ReviewQueueStats:
    """Get review queue statistics."""
    # Count entities needing review by type
    docket_count = db.query(func.count(FLHearingDocket.id)).filter(
        FLHearingDocket.needs_review == True
    ).scalar() or 0

    utility_count = db.query(func.count(FLHearingUtility.id)).filter(
        FLHearingUtility.needs_review == True
    ).scalar() or 0

    topic_count = db.query(func.count(FLHearingTopic.id)).filter(
        FLHearingTopic.needs_review == True
    ).scalar() or 0

    # Count hearings with pending reviews
    hearings_with_pending = db.execute(text("""
        SELECT COUNT(DISTINCT hearing_id) FROM (
            SELECT hearing_id FROM fl_hearing_dockets WHERE needs_review = true
            UNION
            SELECT hearing_id FROM fl_hearing_utilities WHERE needs_review = true
            UNION
            SELECT hearing_id FROM fl_hearing_topics WHERE needs_review = true
        ) sub
    """)).scalar() or 0

    return ReviewQueueStats(
        total=docket_count + utility_count + topic_count,
        dockets=docket_count,
        utilities=utility_count,
        topics=topic_count,
        hearings_with_pending=hearings_with_pending,
    )


# =============================================================================
# Review Queue Listings
# =============================================================================

@router.get("/queue")
def get_review_queue(
    entity_type: Optional[str] = None,  # docket, utility, topic
    limit: int = Query(default=50, le=100),
    db: Session = Depends(get_db)
):
    """Get entities needing review, optionally filtered by type."""
    results = []

    if entity_type is None or entity_type == 'docket':
        docket_links = db.query(FLHearingDocket).filter(
            FLHearingDocket.needs_review == True
        ).order_by(
            FLHearingDocket.confidence_score.asc().nullsfirst()
        ).limit(limit).all()

        for link in docket_links:
            hearing = db.query(FLHearing).filter(FLHearing.id == link.hearing_id).first()
            docket = db.query(FLDocket).filter(FLDocket.id == link.docket_id).first()
            results.append({
                "type": "docket",
                "link_id": link.id,
                "hearing_id": link.hearing_id,
                "hearing_title": hearing.title if hearing else None,
                "hearing_date": hearing.hearing_date.isoformat() if hearing and hearing.hearing_date else None,
                "entity_id": link.docket_id,
                "entity_name": docket.docket_number if docket else None,
                "entity_title": docket.title if docket else None,
                "confidence_score": link.confidence_score,
                "match_type": link.match_type,
                "review_reason": link.review_reason,
                "context_summary": link.context_summary,
            })

    if entity_type is None or entity_type == 'utility':
        utility_links = db.query(FLHearingUtility).filter(
            FLHearingUtility.needs_review == True
        ).order_by(
            FLHearingUtility.confidence_score.asc().nullsfirst()
        ).limit(limit).all()

        for link in utility_links:
            hearing = db.query(FLHearing).filter(FLHearing.id == link.hearing_id).first()
            utility = db.query(FLUtility).filter(FLUtility.id == link.utility_id).first()
            results.append({
                "type": "utility",
                "link_id": link.id,
                "hearing_id": link.hearing_id,
                "hearing_title": hearing.title if hearing else None,
                "hearing_date": hearing.hearing_date.isoformat() if hearing and hearing.hearing_date else None,
                "entity_id": link.utility_id,
                "entity_name": utility.name if utility else None,
                "role": link.role,
                "confidence_score": link.confidence_score,
                "match_type": link.match_type,
                "review_reason": link.review_reason,
                "context_summary": link.context_summary,
            })

    if entity_type is None or entity_type == 'topic':
        topic_links = db.query(FLHearingTopic).filter(
            FLHearingTopic.needs_review == True
        ).order_by(
            FLHearingTopic.confidence_score.asc().nullsfirst()
        ).limit(limit).all()

        for link in topic_links:
            hearing = db.query(FLHearing).filter(FLHearing.id == link.hearing_id).first()
            topic = db.query(FLTopic).filter(FLTopic.id == link.topic_id).first()
            results.append({
                "type": "topic",
                "link_id": link.id,
                "hearing_id": link.hearing_id,
                "hearing_title": hearing.title if hearing else None,
                "hearing_date": hearing.hearing_date.isoformat() if hearing and hearing.hearing_date else None,
                "entity_id": link.topic_id,
                "entity_name": topic.name if topic else None,
                "category": topic.category if topic else None,
                "relevance_score": link.relevance_score,
                "confidence_score": link.confidence_score,
                "match_type": link.match_type,
                "review_reason": link.review_reason,
                "context_summary": link.context_summary,
            })

    return {"items": results, "total": len(results)}


@router.get("/hearings")
def get_hearings_for_review(
    limit: int = Query(default=20, le=50),
    db: Session = Depends(get_db)
):
    """Get hearings with entities needing review, grouped by hearing."""
    # Find hearings with pending reviews
    hearing_ids = db.execute(text("""
        SELECT DISTINCT hearing_id FROM (
            SELECT hearing_id FROM fl_hearing_dockets WHERE needs_review = true
            UNION
            SELECT hearing_id FROM fl_hearing_utilities WHERE needs_review = true
            UNION
            SELECT hearing_id FROM fl_hearing_topics WHERE needs_review = true
        ) sub
        LIMIT :limit
    """), {"limit": limit}).fetchall()

    results = []
    for (hearing_id,) in hearing_ids:
        hearing = db.query(FLHearing).filter(FLHearing.id == hearing_id).first()
        if not hearing:
            continue

        # Get pending links for this hearing
        docket_links = db.query(FLHearingDocket).filter(
            FLHearingDocket.hearing_id == hearing_id,
            FLHearingDocket.needs_review == True
        ).all()

        utility_links = db.query(FLHearingUtility).filter(
            FLHearingUtility.hearing_id == hearing_id,
            FLHearingUtility.needs_review == True
        ).all()

        topic_links = db.query(FLHearingTopic).filter(
            FLHearingTopic.hearing_id == hearing_id,
            FLHearingTopic.needs_review == True
        ).all()

        results.append({
            "hearing_id": hearing.id,
            "hearing_title": hearing.title,
            "hearing_date": hearing.hearing_date.isoformat() if hearing.hearing_date else None,
            "docket_number": hearing.docket_number,
            "pending_dockets": len(docket_links),
            "pending_utilities": len(utility_links),
            "pending_topics": len(topic_links),
            "total_pending": len(docket_links) + len(utility_links) + len(topic_links),
        })

    return {"items": results, "total": len(results)}


# =============================================================================
# Hearing Entity Links
# =============================================================================

@router.get("/hearings/{hearing_id}/links")
def get_hearing_links(hearing_id: int, db: Session = Depends(get_db)):
    """Get all entity links for a hearing."""
    hearing = db.query(FLHearing).filter(FLHearing.id == hearing_id).first()
    if not hearing:
        raise HTTPException(status_code=404, detail="Hearing not found")

    # Get docket links
    docket_links = []
    for link in db.query(FLHearingDocket).filter(FLHearingDocket.hearing_id == hearing_id).all():
        docket = db.query(FLDocket).filter(FLDocket.id == link.docket_id).first()
        docket_links.append({
            "link_id": link.id,
            "docket_id": link.docket_id,
            "docket_number": docket.docket_number if docket else None,
            "docket_title": docket.title if docket else None,
            "is_primary": link.is_primary,
            "confidence_score": link.confidence_score,
            "match_type": link.match_type,
            "needs_review": link.needs_review,
            "context_summary": link.context_summary,
        })

    # Get utility links
    utility_links = []
    for link in db.query(FLHearingUtility).filter(FLHearingUtility.hearing_id == hearing_id).all():
        utility = db.query(FLUtility).filter(FLUtility.id == link.utility_id).first()
        utility_links.append({
            "link_id": link.id,
            "utility_id": link.utility_id,
            "utility_name": utility.name if utility else None,
            "role": link.role,
            "confidence_score": link.confidence_score,
            "match_type": link.match_type,
            "needs_review": link.needs_review,
            "context_summary": link.context_summary,
        })

    # Get topic links
    topic_links = []
    for link in db.query(FLHearingTopic).filter(FLHearingTopic.hearing_id == hearing_id).all():
        topic = db.query(FLTopic).filter(FLTopic.id == link.topic_id).first()
        topic_links.append({
            "link_id": link.id,
            "topic_id": link.topic_id,
            "topic_name": topic.name if topic else None,
            "category": topic.category if topic else None,
            "relevance_score": link.relevance_score,
            "confidence_score": link.confidence_score,
            "match_type": link.match_type,
            "needs_review": link.needs_review,
            "context_summary": link.context_summary,
        })

    return {
        "hearing_id": hearing_id,
        "hearing_title": hearing.title,
        "dockets": docket_links,
        "utilities": utility_links,
        "topics": topic_links,
    }


# =============================================================================
# Link Management
# =============================================================================

@router.post("/hearings/{hearing_id}/dockets")
def link_hearing_to_docket(
    hearing_id: int,
    request: DocketLinkRequest,
    db: Session = Depends(get_db)
):
    """Link a hearing to a docket."""
    hearing = db.query(FLHearing).filter(FLHearing.id == hearing_id).first()
    if not hearing:
        raise HTTPException(status_code=404, detail="Hearing not found")

    docket = db.query(FLDocket).filter(FLDocket.id == request.docket_id).first()
    if not docket:
        raise HTTPException(status_code=404, detail="Docket not found")

    # Check if link already exists
    existing = db.query(FLHearingDocket).filter(
        FLHearingDocket.hearing_id == hearing_id,
        FLHearingDocket.docket_id == request.docket_id
    ).first()

    if existing:
        raise HTTPException(status_code=400, detail="Link already exists")

    # If this is primary, unset other primary links
    if request.is_primary:
        db.query(FLHearingDocket).filter(
            FLHearingDocket.hearing_id == hearing_id,
            FLHearingDocket.is_primary == True
        ).update({"is_primary": False})

    link = FLHearingDocket(
        hearing_id=hearing_id,
        docket_id=request.docket_id,
        is_primary=request.is_primary,
        context_summary=request.context_summary,
        confidence_score=100,
        match_type="manual",
        needs_review=False,
    )
    db.add(link)
    db.commit()

    return {"success": True, "link_id": link.id}


@router.delete("/hearings/{hearing_id}/dockets/{docket_id}")
def unlink_hearing_from_docket(
    hearing_id: int,
    docket_id: int,
    db: Session = Depends(get_db)
):
    """Remove a hearing-docket link."""
    link = db.query(FLHearingDocket).filter(
        FLHearingDocket.hearing_id == hearing_id,
        FLHearingDocket.docket_id == docket_id
    ).first()

    if not link:
        raise HTTPException(status_code=404, detail="Link not found")

    db.delete(link)
    db.commit()

    return {"success": True}


@router.post("/hearings/{hearing_id}/utilities")
def link_hearing_to_utility(
    hearing_id: int,
    request: UtilityLinkRequest,
    db: Session = Depends(get_db)
):
    """Link a hearing to a utility."""
    hearing = db.query(FLHearing).filter(FLHearing.id == hearing_id).first()
    if not hearing:
        raise HTTPException(status_code=404, detail="Hearing not found")

    utility = db.query(FLUtility).filter(FLUtility.id == request.utility_id).first()
    if not utility:
        raise HTTPException(status_code=404, detail="Utility not found")

    # Check if link already exists
    existing = db.query(FLHearingUtility).filter(
        FLHearingUtility.hearing_id == hearing_id,
        FLHearingUtility.utility_id == request.utility_id
    ).first()

    if existing:
        raise HTTPException(status_code=400, detail="Link already exists")

    link = FLHearingUtility(
        hearing_id=hearing_id,
        utility_id=request.utility_id,
        role=request.role,
        context_summary=request.context_summary,
        confidence_score=100,
        match_type="manual",
        confidence="manual",
        needs_review=False,
    )
    db.add(link)

    # Update mention count
    utility.mention_count = (utility.mention_count or 0) + 1

    db.commit()

    return {"success": True, "link_id": link.id}


@router.delete("/hearings/{hearing_id}/utilities/{utility_id}")
def unlink_hearing_from_utility(
    hearing_id: int,
    utility_id: int,
    db: Session = Depends(get_db)
):
    """Remove a hearing-utility link."""
    link = db.query(FLHearingUtility).filter(
        FLHearingUtility.hearing_id == hearing_id,
        FLHearingUtility.utility_id == utility_id
    ).first()

    if not link:
        raise HTTPException(status_code=404, detail="Link not found")

    # Update mention count
    utility = db.query(FLUtility).filter(FLUtility.id == utility_id).first()
    if utility:
        utility.mention_count = max(0, (utility.mention_count or 0) - 1)

    db.delete(link)
    db.commit()

    return {"success": True}


@router.post("/hearings/{hearing_id}/topics")
def link_hearing_to_topic(
    hearing_id: int,
    request: TopicLinkRequest,
    db: Session = Depends(get_db)
):
    """Link a hearing to a topic."""
    hearing = db.query(FLHearing).filter(FLHearing.id == hearing_id).first()
    if not hearing:
        raise HTTPException(status_code=404, detail="Hearing not found")

    topic = db.query(FLTopic).filter(FLTopic.id == request.topic_id).first()
    if not topic:
        raise HTTPException(status_code=404, detail="Topic not found")

    # Check if link already exists
    existing = db.query(FLHearingTopic).filter(
        FLHearingTopic.hearing_id == hearing_id,
        FLHearingTopic.topic_id == request.topic_id
    ).first()

    if existing:
        raise HTTPException(status_code=400, detail="Link already exists")

    link = FLHearingTopic(
        hearing_id=hearing_id,
        topic_id=request.topic_id,
        relevance_score=request.relevance_score,
        context_summary=request.context_summary,
        confidence_score=100,
        match_type="manual",
        confidence="manual",
        needs_review=False,
    )
    db.add(link)

    # Update mention count
    topic.mention_count = (topic.mention_count or 0) + 1

    db.commit()

    return {"success": True, "link_id": link.id}


@router.delete("/hearings/{hearing_id}/topics/{topic_id}")
def unlink_hearing_from_topic(
    hearing_id: int,
    topic_id: int,
    db: Session = Depends(get_db)
):
    """Remove a hearing-topic link."""
    link = db.query(FLHearingTopic).filter(
        FLHearingTopic.hearing_id == hearing_id,
        FLHearingTopic.topic_id == topic_id
    ).first()

    if not link:
        raise HTTPException(status_code=404, detail="Link not found")

    # Update mention count
    topic = db.query(FLTopic).filter(FLTopic.id == topic_id).first()
    if topic:
        topic.mention_count = max(0, (topic.mention_count or 0) - 1)

    db.delete(link)
    db.commit()

    return {"success": True}


# =============================================================================
# Review Actions
# =============================================================================

@router.post("/docket-link/{link_id}")
def review_docket_link(
    link_id: int,
    request: ReviewActionRequest,
    db: Session = Depends(get_db)
):
    """Review a docket link."""
    link = db.query(FLHearingDocket).filter(FLHearingDocket.id == link_id).first()
    if not link:
        raise HTTPException(status_code=404, detail="Link not found")

    if request.action == "approve":
        link.needs_review = False
        link.confidence = "verified"
        link.review_notes = request.notes
        link.reviewed_at = datetime.utcnow()

    elif request.action == "reject":
        # Record correction before deleting
        if request.notes:
            correction = FLEntityCorrection(
                entity_type="docket",
                hearing_id=link.hearing_id,
                original_entity_id=link.docket_id,
                correction_type="invalid",
                created_by="admin",
            )
            db.add(correction)
        db.delete(link)

    elif request.action == "link":
        if not request.correct_entity_id:
            raise HTTPException(status_code=400, detail="correct_entity_id required for link action")

        # Change to different docket
        old_docket_id = link.docket_id
        link.docket_id = request.correct_entity_id
        link.needs_review = False
        link.confidence = "verified"
        link.match_type = "manual"
        link.review_notes = request.notes
        link.reviewed_at = datetime.utcnow()

        # Record correction
        correction = FLEntityCorrection(
            entity_type="docket",
            hearing_id=link.hearing_id,
            original_entity_id=old_docket_id,
            correct_entity_id=request.correct_entity_id,
            correction_type="wrong_entity",
            created_by="admin",
        )
        db.add(correction)

    elif request.action == "skip":
        link.review_notes = request.notes
        # Keep needs_review = True

    else:
        raise HTTPException(status_code=400, detail=f"Unknown action: {request.action}")

    db.commit()
    return {"success": True}


@router.post("/utility-link/{link_id}")
def review_utility_link(
    link_id: int,
    request: ReviewActionRequest,
    db: Session = Depends(get_db)
):
    """Review a utility link."""
    link = db.query(FLHearingUtility).filter(FLHearingUtility.id == link_id).first()
    if not link:
        raise HTTPException(status_code=404, detail="Link not found")

    if request.action == "approve":
        link.needs_review = False
        link.confidence = "verified"
        link.review_notes = request.notes
        link.reviewed_at = datetime.utcnow()

    elif request.action == "reject":
        utility = db.query(FLUtility).filter(FLUtility.id == link.utility_id).first()
        if utility:
            utility.mention_count = max(0, (utility.mention_count or 0) - 1)
        db.delete(link)

    elif request.action == "link":
        if not request.correct_entity_id:
            raise HTTPException(status_code=400, detail="correct_entity_id required for link action")

        old_utility = db.query(FLUtility).filter(FLUtility.id == link.utility_id).first()
        new_utility = db.query(FLUtility).filter(FLUtility.id == request.correct_entity_id).first()

        if old_utility:
            old_utility.mention_count = max(0, (old_utility.mention_count or 0) - 1)
        if new_utility:
            new_utility.mention_count = (new_utility.mention_count or 0) + 1

        old_utility_id = link.utility_id
        link.utility_id = request.correct_entity_id
        link.needs_review = False
        link.confidence = "verified"
        link.match_type = "manual"
        link.review_notes = request.notes
        link.reviewed_at = datetime.utcnow()

        correction = FLEntityCorrection(
            entity_type="utility",
            hearing_id=link.hearing_id,
            original_entity_id=old_utility_id,
            correct_entity_id=request.correct_entity_id,
            correction_type="wrong_entity",
            created_by="admin",
        )
        db.add(correction)

    db.commit()
    return {"success": True}


@router.post("/topic-link/{link_id}")
def review_topic_link(
    link_id: int,
    request: ReviewActionRequest,
    db: Session = Depends(get_db)
):
    """Review a topic link."""
    link = db.query(FLHearingTopic).filter(FLHearingTopic.id == link_id).first()
    if not link:
        raise HTTPException(status_code=404, detail="Link not found")

    if request.action == "approve":
        link.needs_review = False
        link.confidence = "verified"
        link.review_notes = request.notes
        link.reviewed_at = datetime.utcnow()

    elif request.action == "reject":
        topic = db.query(FLTopic).filter(FLTopic.id == link.topic_id).first()
        if topic:
            topic.mention_count = max(0, (topic.mention_count or 0) - 1)
        db.delete(link)

    elif request.action == "link":
        if not request.correct_entity_id:
            raise HTTPException(status_code=400, detail="correct_entity_id required for link action")

        old_topic = db.query(FLTopic).filter(FLTopic.id == link.topic_id).first()
        new_topic = db.query(FLTopic).filter(FLTopic.id == request.correct_entity_id).first()

        if old_topic:
            old_topic.mention_count = max(0, (old_topic.mention_count or 0) - 1)
        if new_topic:
            new_topic.mention_count = (new_topic.mention_count or 0) + 1

        old_topic_id = link.topic_id
        link.topic_id = request.correct_entity_id
        link.needs_review = False
        link.confidence = "verified"
        link.match_type = "manual"
        link.review_notes = request.notes
        link.reviewed_at = datetime.utcnow()

        correction = FLEntityCorrection(
            entity_type="topic",
            hearing_id=link.hearing_id,
            original_entity_id=old_topic_id,
            correct_entity_id=request.correct_entity_id,
            correction_type="wrong_entity",
            created_by="admin",
        )
        db.add(correction)

    db.commit()
    return {"success": True}


@router.post("/hearings/{hearing_id}/bulk")
def bulk_review_hearing(
    hearing_id: int,
    request: BulkReviewRequest,
    db: Session = Depends(get_db)
):
    """Bulk review all entities for a hearing."""
    hearing = db.query(FLHearing).filter(FLHearing.id == hearing_id).first()
    if not hearing:
        raise HTTPException(status_code=404, detail="Hearing not found")

    approved = 0
    rejected = 0

    if request.action == "approve_all":
        # Approve all pending links
        approved += db.query(FLHearingDocket).filter(
            FLHearingDocket.hearing_id == hearing_id,
            FLHearingDocket.needs_review == True
        ).update({"needs_review": False, "confidence": "verified", "reviewed_at": datetime.utcnow()})

        approved += db.query(FLHearingUtility).filter(
            FLHearingUtility.hearing_id == hearing_id,
            FLHearingUtility.needs_review == True
        ).update({"needs_review": False, "confidence": "verified", "reviewed_at": datetime.utcnow()})

        approved += db.query(FLHearingTopic).filter(
            FLHearingTopic.hearing_id == hearing_id,
            FLHearingTopic.needs_review == True
        ).update({"needs_review": False, "confidence": "verified", "reviewed_at": datetime.utcnow()})

    elif request.action == "approve_high_confidence":
        threshold = request.confidence_threshold

        approved += db.query(FLHearingDocket).filter(
            FLHearingDocket.hearing_id == hearing_id,
            FLHearingDocket.needs_review == True,
            FLHearingDocket.confidence_score >= threshold
        ).update({"needs_review": False, "confidence": "verified", "reviewed_at": datetime.utcnow()})

        approved += db.query(FLHearingUtility).filter(
            FLHearingUtility.hearing_id == hearing_id,
            FLHearingUtility.needs_review == True,
            FLHearingUtility.confidence_score >= threshold
        ).update({"needs_review": False, "confidence": "verified", "reviewed_at": datetime.utcnow()})

        approved += db.query(FLHearingTopic).filter(
            FLHearingTopic.hearing_id == hearing_id,
            FLHearingTopic.needs_review == True,
            FLHearingTopic.confidence_score >= threshold
        ).update({"needs_review": False, "confidence": "verified", "reviewed_at": datetime.utcnow()})

    elif request.action == "reject_all":
        rejected += db.query(FLHearingDocket).filter(
            FLHearingDocket.hearing_id == hearing_id,
            FLHearingDocket.needs_review == True
        ).delete()

        rejected += db.query(FLHearingUtility).filter(
            FLHearingUtility.hearing_id == hearing_id,
            FLHearingUtility.needs_review == True
        ).delete()

        rejected += db.query(FLHearingTopic).filter(
            FLHearingTopic.hearing_id == hearing_id,
            FLHearingTopic.needs_review == True
        ).delete()

    db.commit()

    return {"success": True, "approved": approved, "rejected": rejected}


# =============================================================================
# Canonical Entity Management
# =============================================================================

@router.get("/utilities")
def list_utilities(
    search: Optional[str] = None,
    limit: int = Query(default=50, le=200),
    db: Session = Depends(get_db)
):
    """List canonical utilities."""
    query = db.query(FLUtility)

    if search:
        query = query.filter(FLUtility.name.ilike(f"%{search}%"))

    utilities = query.order_by(FLUtility.mention_count.desc()).limit(limit).all()

    return {
        "items": [
            {
                "id": u.id,
                "name": u.name,
                "normalized_name": u.normalized_name,
                "utility_type": u.utility_type,
                "sectors": u.sectors or [],
                "aliases": u.aliases or [],
                "mention_count": u.mention_count,
            }
            for u in utilities
        ]
    }


@router.post("/utilities")
def create_utility(request: UtilityCreate, db: Session = Depends(get_db)):
    """Create a new canonical utility."""
    normalized = request.normalized_name or request.name.lower().strip()

    # Check for duplicate
    existing = db.query(FLUtility).filter(FLUtility.normalized_name == normalized).first()
    if existing:
        raise HTTPException(status_code=400, detail="Utility with this name already exists")

    utility = FLUtility(
        name=request.name,
        normalized_name=normalized,
        utility_type=request.utility_type,
        sectors=request.sectors or [],
        aliases=request.aliases or [],
    )
    db.add(utility)
    db.commit()

    return {"success": True, "id": utility.id}


@router.get("/topics")
def list_topics(
    category: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = Query(default=50, le=200),
    db: Session = Depends(get_db)
):
    """List canonical topics."""
    query = db.query(FLTopic)

    if category:
        query = query.filter(FLTopic.category == category)

    if search:
        query = query.filter(FLTopic.name.ilike(f"%{search}%"))

    topics = query.order_by(FLTopic.mention_count.desc()).limit(limit).all()

    return {
        "items": [
            {
                "id": t.id,
                "name": t.name,
                "slug": t.slug,
                "category": t.category,
                "description": t.description,
                "mention_count": t.mention_count,
            }
            for t in topics
        ]
    }


@router.post("/topics")
def create_topic(request: TopicCreate, db: Session = Depends(get_db)):
    """Create a new topic."""
    slug = request.slug or request.name.lower().replace(" ", "-")

    # Check for duplicate
    existing = db.query(FLTopic).filter(FLTopic.slug == slug).first()
    if existing:
        raise HTTPException(status_code=400, detail="Topic with this name already exists")

    topic = FLTopic(
        name=request.name,
        slug=slug,
        category=request.category,
        description=request.description,
    )
    db.add(topic)
    db.commit()

    return {"success": True, "id": topic.id}


# =============================================================================
# Corrections / Training Data
# =============================================================================

@router.get("/corrections")
def list_corrections(
    entity_type: Optional[str] = None,
    limit: int = Query(default=50, le=200),
    db: Session = Depends(get_db)
):
    """Get recent entity corrections for analysis."""
    query = db.query(FLEntityCorrection)

    if entity_type:
        query = query.filter(FLEntityCorrection.entity_type == entity_type)

    corrections = query.order_by(FLEntityCorrection.created_at.desc()).limit(limit).all()

    return {
        "items": [
            {
                "id": c.id,
                "entity_type": c.entity_type,
                "hearing_id": c.hearing_id,
                "original_text": c.original_text,
                "corrected_text": c.corrected_text,
                "correction_type": c.correction_type,
                "created_by": c.created_by,
                "created_at": c.created_at.isoformat() if c.created_at else None,
            }
            for c in corrections
        ]
    }
