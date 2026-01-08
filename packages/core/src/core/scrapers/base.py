"""
Base class for PSC docket scrapers.

Provides a common interface for scraping docket information from
various state Public Service Commission websites.
"""

from abc import ABC, abstractmethod
from typing import Iterator, Optional, List
from dataclasses import dataclass
import os
import logging

import requests
import urllib3

# Suppress SSL warnings when verification is disabled
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger(__name__)

# Allow disabling SSL verification for development/testing
VERIFY_SSL = os.getenv('VERIFY_SSL', 'false').lower() == 'true'


@dataclass
class DocketRecord:
    """Standardized docket record from any source."""
    docket_number: str
    title: Optional[str] = None
    utility_name: Optional[str] = None
    filing_date: Optional[str] = None
    status: Optional[str] = None
    case_type: Optional[str] = None
    source_url: Optional[str] = None
    description: Optional[str] = None


class BaseDocketScraper(ABC):
    """Base class for PSC docket scrapers."""

    state_code: str
    state_name: str
    base_url: str
    search_url: str

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'CanaryScope Research Bot (contact: admin@canaryscope.com)'
        })
        # Disable SSL verification if configured (for dev/testing environments)
        self.session.verify = VERIFY_SSL

    @abstractmethod
    def scrape_docket_list(
        self,
        year: Optional[int] = None,
        status: Optional[str] = None,
        limit: int = 1000
    ) -> Iterator[DocketRecord]:
        """
        Scrape list of dockets from PSC website.

        Args:
            year: Filter by year (default: current year)
            status: Filter by status (open, closed, etc.)
            limit: Maximum number of dockets to return

        Yields:
            DocketRecord objects
        """
        pass

    def test_connection(self) -> bool:
        """Test if scraper can connect to the PSC website."""
        try:
            response = self.session.get(self.search_url, timeout=10)
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Connection test failed for {self.state_code}: {e}")
            return False

    def get_docket_detail(self, docket_number: str) -> Optional[DocketRecord]:
        """
        Get detailed information for a specific docket.
        Override in subclasses if PSC provides detail pages.
        """
        return None


class MockDocketScraper(BaseDocketScraper):
    """Mock scraper for testing and states without real scrapers."""

    def __init__(self, state_code: str, state_name: str):
        super().__init__()
        self.state_code = state_code
        self.state_name = state_name
        self.base_url = ""
        self.search_url = ""

    def scrape_docket_list(
        self,
        year: Optional[int] = None,
        status: Optional[str] = None,
        limit: int = 1000
    ) -> Iterator[DocketRecord]:
        """Return empty results for mock scraper."""
        return iter([])


__all__ = ['DocketRecord', 'BaseDocketScraper', 'MockDocketScraper', 'VERIFY_SSL']
