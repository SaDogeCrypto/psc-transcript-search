"""
Florida hearing extension model.

Extends the core Hearing model with Florida-specific fields:
- YouTube video metadata
- RSS feed source info
"""

from datetime import datetime

from sqlalchemy import Column, String, ForeignKey, DateTime, Index
from sqlalchemy.orm import relationship

from src.core.models.base import Base, GUID


class FLHearingDetails(Base):
    """
    Florida-specific hearing fields.

    Linked 1:1 with core Hearing model via hearing_id.
    Stores YouTube/RSS source metadata.
    """

    __tablename__ = "fl_hearing_details"

    hearing_id = Column(
        GUID(),
        ForeignKey("hearings.id", ondelete="CASCADE"),
        primary_key=True,
    )

    # YouTube source
    youtube_video_id = Column(
        String(50),
        index=True,
        comment="YouTube video ID",
    )
    youtube_channel_id = Column(
        String(50),
        comment="YouTube channel ID",
    )
    youtube_thumbnail_url = Column(
        String(500),
        comment="YouTube thumbnail URL",
    )

    # RSS feed metadata
    rss_guid = Column(
        String(255),
        index=True,
        comment="RSS feed GUID",
    )
    rss_published_at = Column(
        DateTime(timezone=True),
        comment="RSS published timestamp",
    )

    # Relationship to core hearing
    hearing = relationship("Hearing", backref="fl_details", uselist=False)

    # Indexes
    __table_args__ = (
        Index("ix_fl_hearing_youtube", "youtube_video_id"),
    )

    def __repr__(self) -> str:
        return f"<FLHearingDetails({self.hearing_id})>"

    @property
    def youtube_url(self) -> str:
        """Get full YouTube video URL."""
        if self.youtube_video_id:
            return f"https://www.youtube.com/watch?v={self.youtube_video_id}"
        return ""

    @property
    def youtube_embed_url(self) -> str:
        """Get YouTube embed URL."""
        if self.youtube_video_id:
            return f"https://www.youtube.com/embed/{self.youtube_video_id}"
        return ""
