"""
Docket schemas for API requests/responses.
"""

from datetime import date
from typing import Optional, List, Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class DocketResponse(BaseModel):
    """Docket summary for list views."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    state_code: str
    docket_number: str
    title: Optional[str] = None
    status: Optional[str] = None
    docket_type: Optional[str] = None
    filed_date: Optional[date] = None


class DocketDetail(BaseModel):
    """Full docket details."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    state_code: str
    docket_number: str
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    docket_type: Optional[str] = None
    filed_date: Optional[date] = None
    closed_date: Optional[date] = None

    # Counts
    document_count: int = 0
    hearing_count: int = 0

    # Florida-specific fields (optional, only present for FL dockets)
    year: Optional[int] = None
    sector_code: Optional[str] = None
    applicant_name: Optional[str] = None
    is_rate_case: Optional[bool] = None
    requested_revenue_increase: Optional[float] = None
    approved_revenue_increase: Optional[float] = None
    commissioner_assignments: Optional[List[Any]] = None
    related_dockets: Optional[List[str]] = None


class DocketListResponse(BaseModel):
    """Paginated docket list response."""
    items: List[DocketResponse]
    total: int
    limit: int
    offset: int
