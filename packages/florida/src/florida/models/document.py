"""
Florida Document model.

Represents documents from the Florida PSC Thunderstone search API.
"""
from datetime import datetime, date
from typing import Optional, TYPE_CHECKING

from sqlalchemy import (
    Column, Integer, String, Text, Date, DateTime, ForeignKey
)
from sqlalchemy.orm import relationship, Mapped, mapped_column

from florida.models.base import Base

if TYPE_CHECKING:
    from florida.models.docket import FLDocket


class FLDocument(Base):
    """
    Florida document from Thunderstone search.

    Thunderstone profiles:
    - library: All PSC documents
    - filingsCurrent: Current year filings
    - filings: Older filings (pre-2014)
    - orders: Commission orders
    - financials: Financial reports
    - tariffs: Tariff filings
    """
    __tablename__ = 'fl_documents'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    thunderstone_id: Mapped[Optional[str]] = mapped_column(String(100))

    # Document metadata
    title: Mapped[str] = mapped_column(Text, nullable=False)
    document_type: Mapped[Optional[str]] = mapped_column(String(100))
    profile: Mapped[Optional[str]] = mapped_column(String(50))

    # Associations
    docket_number: Mapped[Optional[str]] = mapped_column(String(20), ForeignKey('fl_dockets.docket_number'))

    # Content
    file_url: Mapped[Optional[str]] = mapped_column(String(500))
    file_type: Mapped[Optional[str]] = mapped_column(String(20))
    file_size_bytes: Mapped[Optional[int]] = mapped_column(Integer)

    # Dates
    filed_date: Mapped[Optional[date]] = mapped_column(Date)
    effective_date: Mapped[Optional[date]] = mapped_column(Date)

    # Full-text search (content_text populated by document extraction)
    content_text: Mapped[Optional[str]] = mapped_column(Text)
    # content_tsvector is a generated column in PostgreSQL

    # Florida-specific
    filer_name: Mapped[Optional[str]] = mapped_column(String(255))
    document_number: Mapped[Optional[str]] = mapped_column(String(50))

    # Timestamps
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime, default=datetime.utcnow)
    scraped_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    # Relationships
    docket: Mapped[Optional["FLDocket"]] = relationship("FLDocket", back_populates="documents")

    def __repr__(self):
        return f"<FLDocument {self.id}: {self.title[:50] if self.title else 'No title'}>"

    @property
    def download_url(self) -> Optional[str]:
        """Get the document download URL."""
        return self.file_url

    @property
    def is_order(self) -> bool:
        """Check if this is a commission order."""
        if self.document_type:
            return 'order' in self.document_type.lower()
        return False

    @property
    def is_testimony(self) -> bool:
        """Check if this is testimony."""
        if self.document_type:
            return 'testimony' in self.document_type.lower()
        return False
