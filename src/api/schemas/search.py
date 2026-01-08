"""
Search schemas for API requests/responses.
"""

from datetime import date
from typing import Optional, List, Dict, Any

from pydantic import BaseModel


class SearchRequest(BaseModel):
    """Search request parameters."""
    query: str
    state_code: Optional[str] = None
    docket_number: Optional[str] = None
    date_from: Optional[date] = None
    date_to: Optional[date] = None
    hearing_type: Optional[str] = None
    utility: Optional[str] = None
    sector: Optional[str] = None
    limit: int = 20
    offset: int = 0


class SearchResult(BaseModel):
    """Individual search result."""
    hearing_id: str
    title: str
    hearing_date: str
    state_code: str
    docket_number: Optional[str] = None
    snippet: str
    score: float


class SearchFacets(BaseModel):
    """Search facet counts."""
    states: List[Dict[str, Any]] = []
    hearing_types: List[Dict[str, Any]] = []
    sectors: List[Dict[str, Any]] = []
    utilities: List[Dict[str, Any]] = []


class SearchResponse(BaseModel):
    """Search response with results and metadata."""
    results: List[SearchResult]
    total: int
    query: str
    filters: Dict[str, Any]
    facets: Optional[SearchFacets] = None
