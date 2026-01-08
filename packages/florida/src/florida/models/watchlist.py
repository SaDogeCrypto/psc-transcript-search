"""
Florida Watchlist model.

Stores user watchlist entries for dockets.
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime

from florida.models.base import Base


class FLWatchlist(Base):
    """User watchlist entry for a docket."""

    __tablename__ = "fl_watchlist"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=False, default=1)
    docket_number = Column(String(20), nullable=False)
    notify_on_mention = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<FLWatchlist user={self.user_id} docket={self.docket_number}>"
