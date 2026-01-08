"""
Hearing model - represents a commission hearing/meeting.

Hearings include:
- Evidentiary hearings
- Public comment sessions
- Commission agenda meetings
- Workshops

Transcription and analysis results are stored here and in related tables.
"""

import uuid
from datetime import date, time, datetime
from typing import Optional, TYPE_CHECKING

from sqlalchemy import Column, String, Text, Date, Time, Integer, Numeric, ForeignKey, Index, DateTime
from sqlalchemy.orm import relationship, Mapped

from src.core.models.base import Base, TimestampMixin, StateModelMixin, GUID

if TYPE_CHECKING:
    from src.core.models.docket import Docket
    from src.core.models.transcript import TranscriptSegment
    from src.core.models.analysis import Analysis


class Hearing(Base, StateModelMixin, TimestampMixin):
    """
    Core hearing model - commission hearings and meetings.

    Contains both metadata and transcript content.
    State-specific fields stored in extension tables.
    """

    __tablename__ = "hearings"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)

    # Link to docket (optional)
    docket_id = Column(
        GUID(),
        ForeignKey("dockets.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Denormalized docket number for convenience
    docket_number = Column(
        String(50),
        index=True,
        comment="Docket number (denormalized for queries)",
    )

    # Hearing identification
    title = Column(Text, comment="Hearing title/description")
    hearing_type = Column(
        String(100),
        index=True,
        comment="Type (evidentiary, public comment, agenda, workshop)",
    )

    # Scheduling
    hearing_date = Column(Date, index=True, comment="Date of hearing")
    scheduled_time = Column(Time, comment="Scheduled start time")
    location = Column(Text, comment="Physical or virtual location")

    # Media
    video_url = Column(Text, comment="URL to video recording")
    audio_url = Column(Text, comment="URL to audio recording")
    duration_seconds = Column(Integer, comment="Duration in seconds")

    # Transcript content
    full_text = Column(Text, comment="Full transcript text")
    word_count = Column(Integer, comment="Word count of transcript")

    # Processing status
    transcript_status = Column(
        String(50),
        index=True,
        default="pending",
        comment="Status: pending, downloaded, transcribed, analyzed, error",
    )

    # Processing metadata
    whisper_model = Column(String(50), comment="Whisper model used for transcription")
    processing_cost_usd = Column(
        Numeric(10, 4),
        comment="Total processing cost in USD",
    )
    processed_at = Column(
        DateTime(timezone=True),
        comment="When transcript was processed",
    )

    # Source tracking
    source_system = Column(
        String(50),
        comment="Source of hearing data (rss, youtube, calendar)",
    )
    external_id = Column(
        String(255),
        index=True,
        comment="ID in source system (e.g., YouTube video ID)",
    )

    # Relationships
    docket: Mapped[Optional["Docket"]] = relationship(
        "Docket",
        back_populates="hearings",
    )
    segments: Mapped[list["TranscriptSegment"]] = relationship(
        "TranscriptSegment",
        back_populates="hearing",
        cascade="all, delete-orphan",
        order_by="TranscriptSegment.segment_index",
    )
    analysis: Mapped[Optional["Analysis"]] = relationship(
        "Analysis",
        back_populates="hearing",
        uselist=False,
        cascade="all, delete-orphan",
    )

    # Indexes
    __table_args__ = (
        Index("ix_hearings_state_date", "state_code", "hearing_date"),
        Index("ix_hearings_state_status", "state_code", "transcript_status"),
        Index("ix_hearings_external", "source_system", "external_id"),
    )

    def __repr__(self) -> str:
        return f"<Hearing({self.state_code}:{self.id}, {self.hearing_date})>"

    @property
    def duration_minutes(self) -> Optional[int]:
        """Duration in minutes (for display)."""
        if self.duration_seconds:
            return self.duration_seconds // 60
        return None
