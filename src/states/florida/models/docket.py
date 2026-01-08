"""
Florida docket extension model.

Extends the core Docket model with Florida-specific fields:
- Docket number parsing (YYYYNNNN-XX format)
- Rate case fields (requested/approved amounts)
- Commissioner assignments
- ClerkOffice API sync metadata
"""

import re
from datetime import datetime
from typing import Optional, Dict, Any

from sqlalchemy import Column, String, Integer, Boolean, Numeric, ForeignKey, DateTime, Index, JSON
from sqlalchemy.orm import relationship

from src.core.models.base import Base, GUID


class FLDocketDetails(Base):
    """
    Florida-specific docket fields.

    Linked 1:1 with core Docket model via docket_id.
    """

    __tablename__ = "fl_docket_details"

    docket_id = Column(
        GUID(),
        ForeignKey("dockets.id", ondelete="CASCADE"),
        primary_key=True,
    )

    # Parsed docket number components (YYYYNNNN-XX)
    year = Column(Integer, index=True, comment="Year from docket number")
    sequence_number = Column(Integer, comment="Sequence number within year")
    sector_code = Column(
        String(10),
        index=True,
        comment="Sector code (EI, GU, WU, etc.)",
    )

    # Applicant/utility
    applicant_name = Column(String(500), comment="Primary applicant/utility name")

    # Rate case fields
    is_rate_case = Column(Boolean, default=False, comment="Whether this is a rate case")
    requested_revenue_increase = Column(
        Numeric(15, 2),
        comment="Requested revenue increase in USD",
    )
    approved_revenue_increase = Column(
        Numeric(15, 2),
        comment="Approved revenue increase in USD",
    )
    requested_roe = Column(
        Numeric(5, 3),
        comment="Requested return on equity (e.g., 0.105 for 10.5%)",
    )
    approved_roe = Column(
        Numeric(5, 3),
        comment="Approved return on equity",
    )

    # Commissioner assignments
    commissioner_assignments = Column(
        JSON,
        comment='[{name, role, assigned_date}]',
    )

    # Related dockets (stored as JSON array)
    related_dockets = Column(
        JSON,
        comment="Related docket numbers as JSON array",
    )

    # ClerkOffice API sync metadata
    clerk_office_id = Column(
        String(100),
        index=True,
        comment="ID in ClerkOffice API",
    )
    clerk_office_data = Column(
        JSON,
        comment="Full response from ClerkOffice API",
    )
    last_synced_at = Column(
        DateTime(timezone=True),
        comment="Last sync with ClerkOffice API",
    )

    # Relationship to core docket
    docket = relationship("Docket", backref="fl_details", uselist=False)

    # Indexes
    __table_args__ = (
        Index("ix_fl_docket_year_sector", "year", "sector_code"),
    )

    def __repr__(self) -> str:
        return f"<FLDocketDetails({self.docket_id})>"

    @staticmethod
    def parse_docket_number(docket_number: str) -> Dict[str, Any]:
        """
        Parse Florida docket number format: YYYYNNNN-XX

        Args:
            docket_number: Docket number string (e.g., "20240001-EI")

        Returns:
            Dict with year, sequence_number, sector_code
            Empty dict if format doesn't match
        """
        pattern = r'^(\d{4})(\d{4})-([A-Z]{2})$'
        match = re.match(pattern, docket_number)

        if match:
            return {
                "year": int(match.group(1)),
                "sequence_number": int(match.group(2)),
                "sector_code": match.group(3),
            }

        return {}

    @staticmethod
    def format_docket_number(year: int, sequence: int, sector_code: str) -> str:
        """
        Format components into Florida docket number.

        Args:
            year: 4-digit year
            sequence: Sequence number (will be zero-padded to 4 digits)
            sector_code: 2-letter sector code

        Returns:
            Formatted docket number (e.g., "20240001-EI")
        """
        return f"{year}{sequence:04d}-{sector_code}"
