"""
Scraper schemas for admin API.
"""

from typing import Optional, List, Dict, Any
from datetime import datetime

from pydantic import BaseModel


class ScraperRunRequest(BaseModel):
    """Request to run a scraper."""
    scraper: str  # "clerk_office", "thunderstone", "rss_hearings"
    state_code: str = "FL"

    # Scraper-specific parameters
    year: Optional[int] = None  # For clerk_office
    docket_number: Optional[str] = None  # For thunderstone
    profile: Optional[str] = None  # For thunderstone: library, filingsCurrent, orders, tariffs
    query: Optional[str] = None  # For thunderstone
    limit: int = 100


class ScraperResultResponse(BaseModel):
    """Scraper execution result."""
    success: bool
    scraper: str
    state_code: str
    items_found: int = 0
    items_created: int = 0
    items_updated: int = 0
    errors: List[str] = []
    duration_seconds: Optional[float] = None


class ScraperListResponse(BaseModel):
    """List of available scrapers."""
    scrapers: Dict[str, List[str]]  # {state_code: [scraper_names]}


class ScraperStatusResponse(BaseModel):
    """Scraper status information."""
    scraper: str
    state_code: str
    last_run: Optional[datetime] = None
    last_result: Optional[ScraperResultResponse] = None
    is_configured: bool = True
    config_error: Optional[str] = None
