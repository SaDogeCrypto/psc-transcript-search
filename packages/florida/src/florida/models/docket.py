"""
Florida Docket model.

Represents dockets from the Florida PSC ClerkOffice API.
"""
from datetime import datetime, date
from typing import Optional, List, TYPE_CHECKING
from decimal import Decimal

from sqlalchemy import (
    Column, Integer, String, Text, Date, DateTime,
    Numeric, ForeignKey
)
from sqlalchemy.dialects.postgresql import JSONB, ARRAY
from sqlalchemy.orm import relationship, Mapped, mapped_column

from florida.models.base import Base

if TYPE_CHECKING:
    from florida.models.document import FLDocument
    from florida.models.hearing import FLHearing


class FLDocket(Base):
    """
    Florida docket with full PSC metadata.

    Docket number format: YYYYNNNN-XX
    - YYYY: 4-digit year
    - NNNN: Sequence number (1-4 digits, zero-padded)
    - XX: Sector code (EI, GU, WU, etc.)

    Example: 20250001-EI (First electric docket of 2025)
    """
    __tablename__ = 'fl_dockets'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    docket_number: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)

    # Parsed components
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    sector_code: Mapped[Optional[str]] = mapped_column(String(2))

    # ClerkOffice API fields
    title: Mapped[Optional[str]] = mapped_column(Text)
    utility_name: Mapped[Optional[str]] = mapped_column(String(255))
    status: Mapped[Optional[str]] = mapped_column(String(50))  # Open, Closed, etc.
    case_type: Mapped[Optional[str]] = mapped_column(String(100))  # Rate Case, Fuel Clause, etc.
    industry_type: Mapped[Optional[str]] = mapped_column(String(50))  # Electric, Gas, Water, Telecom

    # Filing metadata
    filed_date: Mapped[Optional[date]] = mapped_column(Date)
    closed_date: Mapped[Optional[date]] = mapped_column(Date)

    # Florida-specific fields
    psc_docket_url: Mapped[Optional[str]] = mapped_column(String(500))
    commissioner_assignments = Column(JSONB)  # Assigned commissioners
    related_dockets = Column(ARRAY(Text))  # Cross-referenced dockets

    # Rate case outcome fields (Pass 2)
    requested_revenue_increase: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 2))
    approved_revenue_increase: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 2))
    requested_roe: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2))
    approved_roe: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2))
    final_order_number: Mapped[Optional[str]] = mapped_column(String(50))
    vote_result: Mapped[Optional[str]] = mapped_column(String(20))

    # Timestamps
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    documents: Mapped[List["FLDocument"]] = relationship("FLDocument", back_populates="docket")
    hearings: Mapped[List["FLHearing"]] = relationship("FLHearing", back_populates="docket")

    def __repr__(self):
        return f"<FLDocket {self.docket_number}: {self.title[:50] if self.title else 'No title'}>"

    @classmethod
    def parse_docket_number(cls, docket_number: str) -> dict:
        """
        Parse a Florida docket number into components.

        Args:
            docket_number: e.g., "20250001-EI"

        Returns:
            dict with year, sequence, sector_code
        """
        import re
        match = re.match(r'^(\d{4})(\d{4})-([A-Z]{2})$', docket_number)
        if match:
            return {
                'year': int(match.group(1)),
                'sequence': int(match.group(2)),
                'sector_code': match.group(3),
            }
        # Try alternate format without sector
        match = re.match(r'^(\d{4})(\d+)$', docket_number)
        if match:
            return {
                'year': int(match.group(1)),
                'sequence': int(match.group(2)),
                'sector_code': None,
            }
        return {'year': 0, 'sequence': 0, 'sector_code': None}

    @property
    def psc_url(self) -> str:
        """Get the Florida PSC docket page URL."""
        if self.psc_docket_url:
            return self.psc_docket_url
        return f"https://www.floridapsc.com/ClerkOffice/Dockets/Index/{self.docket_number}"

    @property
    def is_rate_case(self) -> bool:
        """Check if this is a rate case."""
        if self.case_type:
            return 'rate' in self.case_type.lower()
        return False

    @property
    def is_open(self) -> bool:
        """Check if docket is still open."""
        return self.status and self.status.lower() == 'open'
