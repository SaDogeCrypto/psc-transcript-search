"""
Florida Hearing and Transcript Segment models.

Represents hearing transcripts and their speaker-attributed segments.
"""
from datetime import datetime, date
from typing import Optional, List, TYPE_CHECKING
from decimal import Decimal

from sqlalchemy import (
    Column, Integer, String, Text, Date, DateTime, Float,
    Numeric, ForeignKey
)
from sqlalchemy.orm import relationship, Mapped, mapped_column

from florida.models.base import Base

if TYPE_CHECKING:
    from florida.models.docket import FLDocket
    from florida.models.entity import FLEntity
    from florida.models.analysis import FLAnalysis


class FLHearing(Base):
    """
    Florida hearing with transcript.

    Hearing types:
    - Evidentiary: Formal hearing with sworn testimony
    - Prehearing: Procedural hearing before evidentiary
    - Workshop: Informal stakeholder meeting
    - Agenda: Regular commission meeting
    - Special Agenda: Special commission meeting
    """
    __tablename__ = 'fl_hearings'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    docket_number: Mapped[Optional[str]] = mapped_column(String(20), ForeignKey('fl_dockets.docket_number'))

    # Hearing details
    hearing_date: Mapped[date] = mapped_column(Date, nullable=False)
    hearing_type: Mapped[Optional[str]] = mapped_column(String(100))
    location: Mapped[Optional[str]] = mapped_column(String(255))
    title: Mapped[Optional[str]] = mapped_column(Text)

    # Transcript
    transcript_url: Mapped[Optional[str]] = mapped_column(String(500))
    transcript_status: Mapped[Optional[str]] = mapped_column(String(50))

    # Audio/Video source
    source_type: Mapped[Optional[str]] = mapped_column(String(50))
    source_url: Mapped[Optional[str]] = mapped_column(String(500))
    external_id: Mapped[Optional[str]] = mapped_column(String(100))
    duration_seconds: Mapped[Optional[int]] = mapped_column(Integer)

    # Full transcript text
    full_text: Mapped[Optional[str]] = mapped_column(Text)
    word_count: Mapped[Optional[int]] = mapped_column(Integer)

    # Processing metadata
    whisper_model: Mapped[Optional[str]] = mapped_column(String(50))
    transcription_confidence: Mapped[Optional[float]] = mapped_column(Float)
    processing_cost_usd: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 4))

    # Timestamps
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime, default=datetime.utcnow)
    processed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    # Relationships
    docket: Mapped[Optional["FLDocket"]] = relationship("FLDocket", back_populates="hearings")
    segments: Mapped[List["FLTranscriptSegment"]] = relationship(
        "FLTranscriptSegment",
        back_populates="hearing",
        cascade="all, delete-orphan"
    )
    entities: Mapped[List["FLEntity"]] = relationship(
        "FLEntity",
        back_populates="hearing",
        cascade="all, delete-orphan"
    )
    analysis: Mapped[Optional["FLAnalysis"]] = relationship(
        "FLAnalysis",
        back_populates="hearing",
        uselist=False,
        cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<FLHearing {self.id}: {self.hearing_date} - {self.title[:50] if self.title else 'No title'}>"

    @property
    def duration_minutes(self) -> Optional[int]:
        """Get duration in minutes."""
        if self.duration_seconds:
            return self.duration_seconds // 60
        return None

    @property
    def is_transcribed(self) -> bool:
        """Check if hearing has been transcribed."""
        return self.transcript_status in ('transcribed', 'analyzed')

    @property
    def youtube_url(self) -> Optional[str]:
        """Get YouTube URL if source is YouTube."""
        if self.source_type == 'youtube' and self.external_id:
            return f"https://www.youtube.com/watch?v={self.external_id}"
        return self.source_url


class FLTranscriptSegment(Base):
    """
    Speaker-attributed transcript segment.

    Segments are typically 30-60 seconds of audio, with optional
    speaker attribution and role identification.
    """
    __tablename__ = 'fl_transcript_segments'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    hearing_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey('fl_hearings.id', ondelete='CASCADE'))

    # Segment data
    segment_index: Mapped[Optional[int]] = mapped_column(Integer)
    start_time: Mapped[Optional[float]] = mapped_column(Float)
    end_time: Mapped[Optional[float]] = mapped_column(Float)

    # Speaker attribution
    speaker_label: Mapped[Optional[str]] = mapped_column(String(100))
    speaker_name: Mapped[Optional[str]] = mapped_column(String(255))
    speaker_role: Mapped[Optional[str]] = mapped_column(String(100))

    # Content
    text: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[Optional[float]] = mapped_column(Float)

    # text_tsvector is a generated column in PostgreSQL

    # Relationships
    hearing: Mapped[Optional["FLHearing"]] = relationship("FLHearing", back_populates="segments")
    entities: Mapped[List["FLEntity"]] = relationship(
        "FLEntity",
        back_populates="segment",
        cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<FLTranscriptSegment {self.id}: {self.start_time:.1f if self.start_time else 0}s - {self.text[:50]}>"

    @property
    def duration(self) -> float:
        """Get segment duration in seconds."""
        if self.start_time is not None and self.end_time is not None:
            return self.end_time - self.start_time
        return 0.0

    @property
    def timestamp_display(self) -> str:
        """Get human-readable timestamp."""
        if self.start_time is None:
            return "00:00"
        minutes = int(self.start_time // 60)
        seconds = int(self.start_time % 60)
        return f"{minutes:02d}:{seconds:02d}"
