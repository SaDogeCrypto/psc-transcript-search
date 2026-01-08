"""
Docket model - represents a regulatory docket/case.

Each state has its own docket numbering format:
- Florida: YYYYNNNN-XX (e.g., 20240001-EI)
- Texas: 5-digit control number
- California: varies by proceeding type

State-specific fields are stored in extension tables (e.g., fl_docket_details).
"""

import uuid
from datetime import date
from typing import Optional, TYPE_CHECKING

from sqlalchemy import Column, String, Text, Date, Index
from sqlalchemy.orm import relationship, Mapped

from src.core.models.base import Base, TimestampMixin, StateModelMixin, GUID

if TYPE_CHECKING:
    from src.core.models.document import Document
    from src.core.models.hearing import Hearing


class Docket(Base, StateModelMixin, TimestampMixin):
    """
    Core docket model - regulatory case/proceeding.

    This contains fields common across all states. State-specific
    fields are stored in extension tables linked via foreign key.
    """

    __tablename__ = "dockets"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)

    # Docket identification (format varies by state)
    docket_number = Column(
        String(50),
        nullable=False,
        index=True,
        comment="State-specific docket number format",
    )

    # Basic information
    title = Column(Text, comment="Docket title/description")
    description = Column(Text, comment="Extended description")

    # Status tracking
    status = Column(
        String(50),
        index=True,
        comment="Current status (open, closed, pending, etc.)",
    )

    # Dates
    filed_date = Column(Date, comment="Date docket was filed/opened")
    closed_date = Column(Date, comment="Date docket was closed (if applicable)")

    # Classification
    docket_type = Column(
        String(100),
        index=True,
        comment="Type of proceeding (rate case, certificate, etc.)",
    )

    # Source tracking
    source_system = Column(
        String(50),
        comment="System this docket was imported from",
    )
    external_id = Column(
        String(255),
        comment="ID in the source system",
    )

    # Relationships
    documents: Mapped[list["Document"]] = relationship(
        "Document",
        back_populates="docket",
        cascade="all, delete-orphan",
    )
    hearings: Mapped[list["Hearing"]] = relationship(
        "Hearing",
        back_populates="docket",
        cascade="all, delete-orphan",
    )

    # Indexes
    __table_args__ = (
        Index("ix_dockets_state_number", "state_code", "docket_number", unique=True),
        Index("ix_dockets_state_status", "state_code", "status"),
        Index("ix_dockets_filed_date", "filed_date"),
    )

    def __repr__(self) -> str:
        return f"<Docket({self.state_code}:{self.docket_number})>"
