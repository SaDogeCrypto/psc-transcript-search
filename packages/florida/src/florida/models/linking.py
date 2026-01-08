"""
Florida Entity Linking models.

Junction tables for linking hearings to dockets, utilities, and topics.
These provide many-to-many relationships with metadata about the links.
"""
from datetime import datetime
from typing import Optional, List, TYPE_CHECKING

from sqlalchemy import (
    Column, Integer, String, Text, DateTime, Float, ForeignKey, Boolean
)
from sqlalchemy.orm import relationship, Mapped, mapped_column

from florida.models.base import Base, JSONB

if TYPE_CHECKING:
    from florida.models.hearing import FLHearing
    from florida.models.docket import FLDocket


class FLUtility(Base):
    """
    Canonical utility company record.

    Normalized utility names with aliases for fuzzy matching.
    """
    __tablename__ = 'fl_utilities'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)

    # Alternative names/abbreviations
    aliases = Column(JSONB, default=list)  # ["FPL", "Florida Power & Light", etc.]

    # Classification
    utility_type: Mapped[Optional[str]] = mapped_column(String(50))  # IOU, Municipal, Coop
    sectors = Column(JSONB, default=list)  # ["electric", "gas"]

    # Statistics
    mention_count: Mapped[int] = mapped_column(Integer, default=0)

    # Timestamps
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    hearing_links: Mapped[List["FLHearingUtility"]] = relationship(
        "FLHearingUtility",
        back_populates="utility",
        cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<FLUtility {self.name}>"


class FLTopic(Base):
    """
    Regulatory topic for categorization.

    Standard topics like "rate case", "fuel clause", "depreciation", etc.
    """
    __tablename__ = 'fl_topics'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)

    # Category for grouping
    category: Mapped[Optional[str]] = mapped_column(String(50))  # rates, operations, policy, etc.
    description: Mapped[Optional[str]] = mapped_column(Text)

    # Statistics
    mention_count: Mapped[int] = mapped_column(Integer, default=0)

    # Timestamps
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    hearing_links: Mapped[List["FLHearingTopic"]] = relationship(
        "FLHearingTopic",
        back_populates="topic",
        cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<FLTopic {self.name}>"


class FLHearingDocket(Base):
    """
    Junction table linking hearings to dockets.

    A hearing can reference multiple dockets (consolidated proceedings),
    and a docket can have multiple hearings.
    """
    __tablename__ = 'fl_hearing_dockets'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    hearing_id: Mapped[int] = mapped_column(Integer, ForeignKey('fl_hearings.id', ondelete='CASCADE'), nullable=False)
    docket_id: Mapped[int] = mapped_column(Integer, ForeignKey('fl_dockets.id', ondelete='CASCADE'), nullable=False)

    # How the docket was mentioned
    mention_summary: Mapped[Optional[str]] = mapped_column(Text)
    timestamps_json = Column(JSONB)  # Array of timestamps where mentioned
    context_summary: Mapped[Optional[str]] = mapped_column(Text)

    # Validation scores
    confidence_score: Mapped[Optional[float]] = mapped_column(Float)  # 0-100
    match_type: Mapped[Optional[str]] = mapped_column(String(20))  # exact, fuzzy, manual

    # Review status
    needs_review: Mapped[bool] = mapped_column(Boolean, default=False)
    review_reason: Mapped[Optional[str]] = mapped_column(String(255))
    review_notes: Mapped[Optional[str]] = mapped_column(Text)
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    reviewed_by: Mapped[Optional[str]] = mapped_column(String(100))

    # Link type
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)  # Primary docket for hearing

    # Timestamps
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    hearing: Mapped["FLHearing"] = relationship("FLHearing", back_populates="docket_links")
    docket: Mapped["FLDocket"] = relationship("FLDocket", back_populates="hearing_links")

    def __repr__(self):
        return f"<FLHearingDocket hearing={self.hearing_id} docket={self.docket_id}>"


class FLHearingUtility(Base):
    """
    Junction table linking hearings to utilities.

    Tracks which utilities are discussed in a hearing and their role.
    """
    __tablename__ = 'fl_hearing_utilities'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    hearing_id: Mapped[int] = mapped_column(Integer, ForeignKey('fl_hearings.id', ondelete='CASCADE'), nullable=False)
    utility_id: Mapped[int] = mapped_column(Integer, ForeignKey('fl_utilities.id', ondelete='CASCADE'), nullable=False)

    # Role in the hearing
    role: Mapped[Optional[str]] = mapped_column(String(50))  # applicant, intervenor, subject
    context_summary: Mapped[Optional[str]] = mapped_column(Text)

    # Validation scores
    confidence_score: Mapped[Optional[float]] = mapped_column(Float)  # 0-100
    match_type: Mapped[Optional[str]] = mapped_column(String(20))  # exact, fuzzy, manual
    confidence: Mapped[Optional[str]] = mapped_column(String(20))  # auto, verified, manual

    # Review status
    needs_review: Mapped[bool] = mapped_column(Boolean, default=False)
    review_reason: Mapped[Optional[str]] = mapped_column(String(255))
    review_notes: Mapped[Optional[str]] = mapped_column(Text)
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    reviewed_by: Mapped[Optional[str]] = mapped_column(String(100))

    # Timestamps
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    hearing: Mapped["FLHearing"] = relationship("FLHearing", back_populates="utility_links")
    utility: Mapped["FLUtility"] = relationship("FLUtility", back_populates="hearing_links")

    def __repr__(self):
        return f"<FLHearingUtility hearing={self.hearing_id} utility={self.utility_id}>"


class FLHearingTopic(Base):
    """
    Junction table linking hearings to topics.

    Tracks which regulatory topics are discussed in a hearing.
    """
    __tablename__ = 'fl_hearing_topics'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    hearing_id: Mapped[int] = mapped_column(Integer, ForeignKey('fl_hearings.id', ondelete='CASCADE'), nullable=False)
    topic_id: Mapped[int] = mapped_column(Integer, ForeignKey('fl_topics.id', ondelete='CASCADE'), nullable=False)

    # Relevance and context
    relevance_score: Mapped[Optional[float]] = mapped_column(Float)  # 0-1 how central to hearing
    mention_count: Mapped[int] = mapped_column(Integer, default=1)
    context_summary: Mapped[Optional[str]] = mapped_column(Text)
    sentiment: Mapped[Optional[str]] = mapped_column(String(20))  # positive, negative, neutral, mixed

    # Validation scores
    confidence_score: Mapped[Optional[float]] = mapped_column(Float)  # 0-100
    match_type: Mapped[Optional[str]] = mapped_column(String(20))  # exact, fuzzy, manual
    confidence: Mapped[Optional[str]] = mapped_column(String(20))  # auto, verified, manual

    # Review status
    needs_review: Mapped[bool] = mapped_column(Boolean, default=False)
    review_reason: Mapped[Optional[str]] = mapped_column(String(255))
    review_notes: Mapped[Optional[str]] = mapped_column(Text)
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    reviewed_by: Mapped[Optional[str]] = mapped_column(String(100))

    # Timestamps
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    hearing: Mapped["FLHearing"] = relationship("FLHearing", back_populates="topic_links")
    topic: Mapped["FLTopic"] = relationship("FLTopic", back_populates="hearing_links")

    def __repr__(self):
        return f"<FLHearingTopic hearing={self.hearing_id} topic={self.topic_id}>"


class FLEntityCorrection(Base):
    """
    Track entity corrections for model improvement.

    Records when users correct extracted entities, providing
    training data for improving extraction accuracy.
    """
    __tablename__ = 'fl_entity_corrections'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # What was corrected
    entity_type: Mapped[str] = mapped_column(String(20), nullable=False)  # docket, topic, utility
    hearing_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey('fl_hearings.id', ondelete='SET NULL'))

    # Original extraction
    original_text: Mapped[str] = mapped_column(Text, nullable=False)
    original_entity_id: Mapped[Optional[int]] = mapped_column(Integer)  # FK depends on type

    # Correction
    corrected_text: Mapped[Optional[str]] = mapped_column(Text)
    correct_entity_id: Mapped[Optional[int]] = mapped_column(Integer)

    # Correction type
    correction_type: Mapped[str] = mapped_column(String(20), nullable=False)  # typo, wrong_entity, merge, split, invalid, new

    # Context
    transcript_context: Mapped[Optional[str]] = mapped_column(Text)  # Surrounding text

    # Metadata
    created_by: Mapped[Optional[str]] = mapped_column(String(100))
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<FLEntityCorrection {self.entity_type}: {self.original_text[:30]}>"
