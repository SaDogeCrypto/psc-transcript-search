"""
Entity model - extracted named entities with review workflow.

Entities are extracted from transcripts and analysis:
- Utilities (companies)
- People (commissioners, attorneys, witnesses)
- Docket references
- Statutes and rules
- Tariffs
- Geographic territories
- Monetary amounts
- Dates

Includes a review workflow for human verification.
"""

import uuid
from datetime import datetime
from typing import Optional, TYPE_CHECKING

from sqlalchemy import Column, String, Text, Float, ForeignKey, Index, DateTime
from sqlalchemy.orm import relationship

from src.core.models.base import Base, TimestampMixin, StateModelMixin, GUID

if TYPE_CHECKING:
    from src.core.models.hearing import Hearing
    from src.core.models.analysis import Analysis


# Standard entity types
ENTITY_TYPES = [
    "utility",      # Company/utility name
    "person",       # Individual name
    "docket",       # Docket number reference
    "statute",      # Statute or rule citation
    "tariff",       # Tariff reference
    "territory",    # Geographic service territory
    "rate",         # Monetary rate/amount
    "date",         # Date reference
    "organization", # Other organization
]

# Review status values
REVIEW_STATUS = [
    "pending",      # Awaiting review
    "verified",     # Human verified as correct
    "rejected",     # Human marked as incorrect
    "merged",       # Merged with another entity
]


class Entity(Base, StateModelMixin, TimestampMixin):
    """
    Extracted named entity with review workflow.

    Entities are extracted during analysis and can be
    reviewed/verified by humans for accuracy.
    """

    __tablename__ = "entities"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)

    # Source references (optional - entity may come from multiple sources)
    hearing_id = Column(
        GUID(),
        ForeignKey("hearings.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    analysis_id = Column(
        GUID(),
        ForeignKey("analyses.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Entity classification
    entity_type = Column(
        String(50),
        nullable=False,
        index=True,
        comment="Type: utility, person, docket, statute, etc.",
    )

    # Entity values
    value = Column(
        Text,
        nullable=False,
        comment="Raw extracted value",
    )
    normalized_value = Column(
        Text,
        index=True,
        comment="Normalized/canonical form",
    )

    # Context
    context = Column(
        Text,
        comment="Surrounding text context",
    )

    # Extraction confidence
    confidence = Column(
        Float,
        comment="Extraction confidence score (0-1)",
    )

    # Review workflow
    status = Column(
        String(20),
        default="pending",
        comment="Review status: pending, verified, rejected, merged",
    )
    reviewed_at = Column(
        DateTime(timezone=True),
        comment="When entity was reviewed",
    )
    reviewed_by = Column(
        String(255),
        comment="User who reviewed the entity",
    )
    review_notes = Column(
        Text,
        comment="Notes from reviewer",
    )

    # For merged entities
    merged_into_id = Column(
        GUID(),
        ForeignKey("entities.id", ondelete="SET NULL"),
        nullable=True,
        comment="If merged, points to canonical entity",
    )

    # Indexes
    __table_args__ = (
        Index("ix_entities_type_value", "entity_type", "normalized_value"),
        Index("ix_entities_state_type", "state_code", "entity_type"),
        Index("ix_entities_status", "status"),
    )

    def __repr__(self) -> str:
        return f"<Entity({self.entity_type}:{self.value[:30]})>"

    def verify(self, user: str, normalized: Optional[str] = None, notes: Optional[str] = None):
        """Mark entity as verified."""
        self.status = "verified"
        self.reviewed_at = datetime.utcnow()
        self.reviewed_by = user
        if normalized:
            self.normalized_value = normalized
        if notes:
            self.review_notes = notes

    def reject(self, user: str, notes: Optional[str] = None):
        """Mark entity as rejected/incorrect."""
        self.status = "rejected"
        self.reviewed_at = datetime.utcnow()
        self.reviewed_by = user
        if notes:
            self.review_notes = notes

    def merge_into(self, canonical_entity: "Entity", user: str):
        """Merge this entity into another canonical entity."""
        self.status = "merged"
        self.merged_into_id = canonical_entity.id
        self.reviewed_at = datetime.utcnow()
        self.reviewed_by = user
