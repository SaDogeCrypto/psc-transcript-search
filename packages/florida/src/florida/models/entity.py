"""
Florida Entity model.

Represents entities extracted from transcripts (utilities, dockets, statutes, etc.)
"""
from datetime import datetime
from typing import Optional, TYPE_CHECKING

from sqlalchemy import (
    Column, Integer, String, Text, DateTime, Float, ForeignKey
)
from sqlalchemy.orm import relationship, Mapped, mapped_column

from florida.models.base import Base, JSONB

if TYPE_CHECKING:
    from florida.models.hearing import FLHearing, FLTranscriptSegment


class FLEntity(Base):
    """
    Entity extracted from transcript.

    Entity types:
    - utility: Utility company name (FPL, Duke, etc.)
    - person: Person name (witness, attorney, commissioner)
    - docket: Docket number reference
    - statute: Florida statute citation (F.S. 366.XX)
    - rate: Rate or dollar amount
    - date: Date reference
    - tariff: Tariff number or schedule
    - territory: Service territory reference
    """
    __tablename__ = 'fl_entities'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    hearing_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey('fl_hearings.id', ondelete='CASCADE'))
    segment_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey('fl_transcript_segments.id', ondelete='SET NULL'))

    # Entity data
    entity_type: Mapped[Optional[str]] = mapped_column(String(50))
    entity_value: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_value: Mapped[Optional[str]] = mapped_column(Text)
    confidence: Mapped[Optional[float]] = mapped_column(Float)

    # Florida-specific entity metadata
    entity_metadata = Column(JSONB)

    # Review status
    status: Mapped[Optional[str]] = mapped_column(String(20), default='pending')
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    reviewed_by: Mapped[Optional[str]] = mapped_column(String(100))

    # Timestamps
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    hearing: Mapped[Optional["FLHearing"]] = relationship("FLHearing", back_populates="entities")
    segment: Mapped[Optional["FLTranscriptSegment"]] = relationship("FLTranscriptSegment", back_populates="entities")

    def __repr__(self):
        return f"<FLEntity {self.entity_type}: {self.entity_value[:30]}>"

    @property
    def is_verified(self) -> bool:
        """Check if entity has been verified."""
        return self.status == 'verified'

    @property
    def needs_review(self) -> bool:
        """Check if entity needs review."""
        return self.status == 'pending'

    def verify(self, reviewer: str):
        """Mark entity as verified."""
        self.status = 'verified'
        self.reviewed_at = datetime.utcnow()
        self.reviewed_by = reviewer

    def reject(self, reviewer: str):
        """Mark entity as rejected."""
        self.status = 'rejected'
        self.reviewed_at = datetime.utcnow()
        self.reviewed_by = reviewer
