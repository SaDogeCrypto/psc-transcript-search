"""
Florida document extension model.

Extends the core Document model with Florida-specific fields:
- Thunderstone search metadata
- Document profile (library, filings, orders, tariffs)
"""

from sqlalchemy import Column, String, Float, ForeignKey, Index
from sqlalchemy.orm import relationship

from src.core.models.base import Base, GUID


# Thunderstone search profiles
THUNDERSTONE_PROFILES = {
    "library": "Library documents",
    "filingsCurrent": "Current filings",
    "orders": "Commission orders",
    "tariffs": "Utility tariffs",
}


class FLDocumentDetails(Base):
    """
    Florida-specific document fields.

    Linked 1:1 with core Document model via document_id.
    Stores Thunderstone search metadata.
    """

    __tablename__ = "fl_document_details"

    document_id = Column(
        GUID(),
        ForeignKey("documents.id", ondelete="CASCADE"),
        primary_key=True,
    )

    # Thunderstone-specific fields
    thunderstone_id = Column(
        String(100),
        index=True,
        comment="Thunderstone document ID",
    )
    profile = Column(
        String(50),
        index=True,
        comment="Thunderstone profile (library, filingsCurrent, orders, tariffs)",
    )
    thunderstone_score = Column(
        Float,
        comment="Thunderstone search relevance score",
    )

    # Additional FL metadata
    filing_party = Column(
        String(500),
        comment="Party that filed the document",
    )
    document_category = Column(
        String(100),
        comment="Document category/classification",
    )

    # Relationship to core document
    document = relationship("Document", backref="fl_details", uselist=False)

    # Indexes
    __table_args__ = (
        Index("ix_fl_doc_profile_id", "profile", "thunderstone_id"),
    )

    def __repr__(self) -> str:
        return f"<FLDocumentDetails({self.document_id}, profile={self.profile})>"
