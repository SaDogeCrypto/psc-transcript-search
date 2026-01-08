"""
Document schemas for API requests/responses.
"""

from datetime import date
from typing import Optional, List
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class DocumentResponse(BaseModel):
    """Document summary for list views."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    state_code: str
    docket_id: Optional[UUID] = None
    docket_number: Optional[str] = None  # Denormalized for convenience
    title: str
    document_type: Optional[str] = None
    filed_date: Optional[date] = None
    file_url: Optional[str] = None


class DocumentDetail(BaseModel):
    """Full document details."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    state_code: str
    docket_id: Optional[UUID] = None
    docket_number: Optional[str] = None
    title: str
    document_type: Optional[str] = None
    filed_date: Optional[date] = None
    filing_party: Optional[str] = None
    file_url: Optional[str] = None
    file_size_bytes: Optional[int] = None
    file_type: Optional[str] = None
    page_count: Optional[int] = None

    # Content (may be large)
    content_text: Optional[str] = None

    # Florida-specific (optional)
    thunderstone_id: Optional[str] = None
    profile: Optional[str] = None


class DocumentListResponse(BaseModel):
    """Paginated document list response."""
    items: List[DocumentResponse]
    total: int
    limit: int
    offset: int
