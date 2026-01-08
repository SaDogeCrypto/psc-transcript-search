"""
Document model - represents a filed document in a docket.

Documents include:
- Filings (applications, motions, testimony)
- Orders (commission decisions)
- Tariffs
- Correspondence
- Exhibits

State-specific metadata stored in extension tables.
"""

import uuid
from datetime import date
from typing import Optional, TYPE_CHECKING

from sqlalchemy import Column, String, Text, Date, Integer, ForeignKey, Index
from sqlalchemy.orm import relationship, Mapped

from src.core.models.base import Base, TimestampMixin, StateModelMixin, GUID

if TYPE_CHECKING:
    from src.core.models.docket import Docket


class Document(Base, StateModelMixin, TimestampMixin):
    """
    Core document model - filed documents in regulatory proceedings.

    State-specific fields (e.g., Thunderstone metadata for FL)
    are stored in extension tables.
    """

    __tablename__ = "documents"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)

    # Link to docket (optional - some documents may be standalone)
    docket_id = Column(
        GUID(),
        ForeignKey("dockets.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Document identification
    title = Column(Text, nullable=False, comment="Document title")
    document_type = Column(
        String(100),
        index=True,
        comment="Type (filing, order, tariff, testimony, etc.)",
    )

    # Filing information
    filed_date = Column(Date, comment="Date document was filed")
    filing_party = Column(String(500), comment="Party that filed the document")

    # File information
    file_url = Column(Text, comment="URL to download the document")
    file_size_bytes = Column(Integer, comment="File size in bytes")
    file_type = Column(String(50), comment="File extension/MIME type")

    # Content extraction
    content_text = Column(Text, comment="Extracted text content for search")
    page_count = Column(Integer, comment="Number of pages")

    # Source tracking
    source_system = Column(
        String(50),
        comment="System document was imported from (thunderstone, cms, etc.)",
    )
    external_id = Column(
        String(255),
        index=True,
        comment="ID in the source system",
    )

    # Relationships
    docket: Mapped[Optional["Docket"]] = relationship(
        "Docket",
        back_populates="documents",
    )

    # Indexes
    __table_args__ = (
        Index("ix_documents_state_type", "state_code", "document_type"),
        Index("ix_documents_filed_date", "filed_date"),
        Index("ix_documents_external", "source_system", "external_id"),
    )

    def __repr__(self) -> str:
        return f"<Document({self.state_code}:{self.id}, {self.document_type})>"
