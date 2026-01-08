"""
TranscriptSegment model - individual segments of a hearing transcript.

Each segment represents a portion of the transcript with:
- Timestamps (start/end)
- Text content
- Optional speaker attribution

Used for:
- Time-synced transcript display
- Speaker-attributed search
- Semantic search with embeddings
"""

import uuid
from typing import Optional, TYPE_CHECKING

from sqlalchemy import Column, String, Text, Float, Integer, ForeignKey, Index
from sqlalchemy.orm import relationship, Mapped

from src.core.models.base import Base, TimestampMixin, GUID

try:
    from pgvector.sqlalchemy import Vector
    HAS_PGVECTOR = True
except ImportError:
    HAS_PGVECTOR = False

if TYPE_CHECKING:
    from src.core.models.hearing import Hearing


class TranscriptSegment(Base, TimestampMixin):
    """
    Transcript segment with optional speaker attribution.

    Segments are created by Whisper transcription and optionally
    enhanced with speaker diarization.
    """

    __tablename__ = "transcript_segments"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)

    # Parent hearing
    hearing_id = Column(
        GUID(),
        ForeignKey("hearings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Ordering
    segment_index = Column(
        Integer,
        nullable=False,
        comment="Order of segment within hearing",
    )

    # Timestamps (in seconds from start)
    start_time = Column(Float, comment="Start time in seconds")
    end_time = Column(Float, comment="End time in seconds")

    # Content
    text = Column(Text, nullable=False, comment="Segment text")

    # Speaker attribution
    speaker_label = Column(
        String(50),
        comment="Speaker label from diarization (SPEAKER_01, etc.)",
    )
    speaker_name = Column(
        String(255),
        index=True,
        comment="Resolved speaker name",
    )
    speaker_role = Column(
        String(100),
        comment="Speaker role (commissioner, counsel, witness, etc.)",
    )

    # Confidence
    confidence = Column(
        Float,
        comment="Transcription confidence score (0-1)",
    )

    # Relationships
    hearing: Mapped["Hearing"] = relationship(
        "Hearing",
        back_populates="segments",
    )

    # Indexes
    __table_args__ = (
        Index("ix_segments_hearing_index", "hearing_id", "segment_index"),
        Index("ix_segments_speaker", "speaker_name"),
    )

    def __repr__(self) -> str:
        return f"<TranscriptSegment({self.hearing_id}:{self.segment_index})>"

    @property
    def duration(self) -> Optional[float]:
        """Duration of segment in seconds."""
        if self.start_time is not None and self.end_time is not None:
            return self.end_time - self.start_time
        return None

    @property
    def timestamp_display(self) -> str:
        """Human-readable timestamp (HH:MM:SS)."""
        if self.start_time is None:
            return ""
        minutes, seconds = divmod(int(self.start_time), 60)
        hours, minutes = divmod(minutes, 60)
        if hours > 0:
            return f"{hours}:{minutes:02d}:{seconds:02d}"
        return f"{minutes}:{seconds:02d}"


# Add embedding column if pgvector is available
if HAS_PGVECTOR:
    TranscriptSegment.embedding = Column(
        Vector(1536),
        comment="OpenAI text-embedding-3-small vector",
    )
