"""
Florida PSC ClerkOffice API Scraper.

Scrapes docket metadata from the Florida PSC ClerkOffice REST API.

API Base: https://pscweb.floridapsc.com/api/ClerkOffice/

Key endpoints:
- /OpenDockets - List all open dockets
- /PscDocketsByType - List dockets by type/industry
- /DocketDetailsByDocketsNo - Full docket details
- /SearchDocketsByDocketNumber - Autocomplete search
"""

import logging
import re
import time
from datetime import datetime, date
from typing import Iterator, Optional, List, Dict, Any
from dataclasses import dataclass, field

import requests

from core.scrapers.base import BaseDocketScraper, DocketRecord
from florida.config import get_config, FloridaConfig
from florida import FL_SECTOR_CODES

logger = logging.getLogger(__name__)


# Industry type mappings from API codes to sector descriptions
INDUSTRY_CODES = {
    'E': 'electric',
    'G': 'gas',
    'T': 'telecom',
    'W': 'water',
    'X': 'other',
    'A': 'all',
}

# Docket type codes
DOCKET_TYPES = {
    'D': 'open',       # Open Dockets
    'O': 'recent',     # Opened Last 30 Days
    'C': 'closed',     # Closed Last 30 Days
}


@dataclass
class FloridaDocketData:
    """
    Florida-specific docket data from ClerkOffice API.

    Extends the basic DocketRecord with Florida-specific fields.
    """
    # Core identifiers
    docket_number: str
    year: int
    sequence: int
    sector_code: Optional[str] = None

    # Metadata from API
    title: Optional[str] = None
    utility_name: Optional[str] = None
    status: Optional[str] = None
    case_type: Optional[str] = None
    industry_type: Optional[str] = None

    # Dates
    filed_date: Optional[date] = None
    closed_date: Optional[date] = None

    # URLs
    psc_docket_url: Optional[str] = None

    # Rate case outcome fields (from details API)
    requested_revenue_increase: Optional[float] = None
    approved_revenue_increase: Optional[float] = None
    requested_roe: Optional[float] = None
    approved_roe: Optional[float] = None
    final_order_number: Optional[str] = None
    vote_result: Optional[str] = None

    # Commissioner assignments
    commissioner_assignments: List[str] = field(default_factory=list)

    # Related dockets
    related_dockets: List[str] = field(default_factory=list)

    # Raw API response for reference
    raw_data: Optional[Dict[str, Any]] = None

    def to_docket_record(self) -> DocketRecord:
        """Convert to standard DocketRecord for compatibility."""
        return DocketRecord(
            docket_number=self.docket_number,
            title=self.title,
            utility_name=self.utility_name,
            filing_date=self.filed_date.isoformat() if self.filed_date else None,
            status=self.status,
            case_type=self.case_type,
            source_url=self.psc_docket_url,
            description=self.title,
        )


class FloridaClerkOfficeClient:
    """Low-level client for Florida PSC ClerkOffice REST API."""

    def __init__(self, config: Optional[FloridaConfig] = None):
        self.config = config or get_config()
        self.base_url = self.config.clerk_office_base_url
        self.session = requests.Session()
        self.session.headers.update({
            'Accept': 'application/json',
            'User-Agent': 'CanaryScope Research Bot (contact: admin@canaryscope.com)',
        })
        self._last_request_time = 0.0

    def _rate_limit(self):
        """Enforce rate limiting between requests."""
        elapsed = time.time() - self._last_request_time
        wait_time = (1.0 / self.config.api_rate_limit) - elapsed
        if wait_time > 0:
            time.sleep(wait_time)
        self._last_request_time = time.time()

    def get_open_dockets(self) -> List[Dict[str, Any]]:
        """Get all open dockets."""
        self._rate_limit()
        response = self.session.get(
            f"{self.base_url}/OpenDockets",
            timeout=60
        )
        response.raise_for_status()
        data = response.json()
        return data.get('result', []) if isinstance(data, dict) else data

    def get_dockets_by_type(
        self,
        docket_type: str = 'D',   # D=Open, O=Recent, C=Closed
        industry_type: str = 'E',  # E=Electric, G=Gas, T=Telecom, W=Water, X=Other
    ) -> List[Dict[str, Any]]:
        """Get dockets filtered by type and industry."""
        self._rate_limit()
        params = {
            'docketType': docket_type,
            'industryType': industry_type,
        }
        response = self.session.get(
            f"{self.base_url}/PscDocketsByType",
            params=params,
            timeout=60
        )
        response.raise_for_status()
        data = response.json()

        # Handle nested response structure: {result: {result: [...]}}
        if isinstance(data, dict):
            outer_result = data.get('result', {})
            if isinstance(outer_result, dict):
                return outer_result.get('result', [])
            return outer_result if isinstance(outer_result, list) else []
        return data

    def get_docket_details(self, docket_no: str) -> Optional[Dict[str, Any]]:
        """Get detailed information for a specific docket."""
        self._rate_limit()
        params = {'docketNo': docket_no}
        response = self.session.get(
            f"{self.base_url}/DocketDetailsByDocketsNo",
            params=params,
            timeout=30
        )
        response.raise_for_status()
        data = response.json()
        return data.get('result') if isinstance(data, dict) else data

    def search_dockets(self, query: str) -> List[Dict[str, Any]]:
        """Search dockets by docket number (autocomplete)."""
        self._rate_limit()
        params = {'docketNumber': query}
        response = self.session.get(
            f"{self.base_url}/SearchDocketsByDocketNumber",
            params=params,
            timeout=30
        )
        response.raise_for_status()
        data = response.json()
        return data.get('result', []) if isinstance(data, dict) else data


class FloridaClerkOfficeScraper(BaseDocketScraper):
    """
    Florida PSC docket scraper using the ClerkOffice REST API.

    This scraper provides comprehensive docket metadata including:
    - Docket title and description
    - Utility name and industry type
    - Filing and closing dates
    - Case type classification
    - Status (open/closed)

    Florida docket number format: YYYYNNNN-XX
    - YYYY = year (e.g., 2025)
    - NNNN = 4-digit sequence (e.g., 0001)
    - XX = sector code (EI, EU, GU, WU, etc.)
    """

    state_code = 'FL'
    state_name = 'Florida'
    base_url = 'https://www.psc.state.fl.us'
    search_url = 'https://www.psc.state.fl.us/ClerkOffice/DocketSearch'

    # Pattern to extract docket components
    DOCKET_PATTERN = re.compile(r'^(\d{4})(\d{4})-([A-Z]{2})$')

    def __init__(self, config: Optional[FloridaConfig] = None):
        super().__init__()
        self.config = config or get_config()
        self.client = FloridaClerkOfficeClient(self.config)

    @staticmethod
    def parse_docket_number(docket_number: str) -> Optional[Dict[str, Any]]:
        """
        Parse a Florida docket number into its components.

        Args:
            docket_number: e.g., "20250001-EI"

        Returns:
            Dict with year, sequence, sector_code or None if invalid
        """
        match = FloridaClerkOfficeScraper.DOCKET_PATTERN.match(docket_number)
        if not match:
            return None
        return {
            'year': int(match.group(1)),
            'sequence': int(match.group(2)),
            'sector_code': match.group(3),
        }

    def _parse_date(self, date_str: Optional[str]) -> Optional[date]:
        """Parse an API date string to a date object."""
        if not date_str:
            return None
        try:
            # Handle ISO format: "2024-01-15T00:00:00" or "2024-01-15T00:00:00Z"
            dt = datetime.fromisoformat(date_str.replace('Z', '+00:00').split('+')[0])
            return dt.date()
        except (ValueError, AttributeError):
            return None

    def _parse_api_result(self, item: Dict[str, Any]) -> Optional[FloridaDocketData]:
        """Parse an API result into a FloridaDocketData object."""
        try:
            base_docket = item.get('docketnum') or str(item.get('docketId', ''))
            if not base_docket:
                return None

            # Get sector code from documentType field (e.g., "EU", "EI", "GU")
            sector_code = item.get('documentType')

            # Construct full docket number: YYYYNNNN-XX
            # API returns docketnum without suffix, documentType has the sector code
            if sector_code and '-' not in base_docket:
                docket_number = f"{base_docket}-{sector_code}"
            else:
                docket_number = base_docket

            # Parse docket number components
            components = self.parse_docket_number(docket_number)
            if not components:
                # Try to extract year and sequence from base docket
                if len(base_docket) >= 8 and base_docket[:8].isdigit():
                    year = int(base_docket[:4])
                    sequence = int(base_docket[4:8])
                else:
                    filed_date = self._parse_date(item.get('docketedDate'))
                    year = filed_date.year if filed_date else datetime.now().year
                    sequence = 0
            else:
                year = components['year']
                sequence = components['sequence']
                sector_code = components['sector_code']

            # Parse dates
            filed_date = self._parse_date(item.get('docketedDate'))
            closed_date = self._parse_date(item.get('docketCloseDate'))

            # Determine status
            status = 'closed' if closed_date else 'open'

            # Map industry code to type
            industry_code = item.get('industryCode', '')
            industry_type = INDUSTRY_CODES.get(industry_code)

            # Build source URL
            psc_docket_url = f"https://www.psc.state.fl.us/ClerkOffice/DocketFiling?docket={docket_number}"

            return FloridaDocketData(
                docket_number=docket_number,
                year=year,
                sequence=sequence,
                sector_code=sector_code,
                title=item.get('docketTitle'),
                utility_name=item.get('companyName'),
                status=status,
                case_type=item.get('caseType'),
                industry_type=industry_type,
                filed_date=filed_date,
                closed_date=closed_date,
                psc_docket_url=psc_docket_url,
                raw_data=item,
            )

        except Exception as e:
            logger.debug(f"Error parsing Florida docket: {e}")
            return None

    def scrape_docket_list(
        self,
        year: Optional[int] = None,
        status: Optional[str] = None,
        limit: int = 1000
    ) -> Iterator[DocketRecord]:
        """
        Scrape Florida dockets using the REST API.

        This method yields standard DocketRecord objects for compatibility
        with the base scraper interface.

        Args:
            year: Filter by year (applied client-side)
            status: 'open', 'closed', or None for all
            limit: Maximum number of dockets to return

        Yields:
            DocketRecord objects
        """
        for docket_data in self.scrape_florida_dockets(year=year, status=status, limit=limit):
            yield docket_data.to_docket_record()

    def scrape_florida_dockets(
        self,
        year: Optional[int] = None,
        status: Optional[str] = None,
        limit: int = 1000,
        industries: Optional[List[str]] = None
    ) -> Iterator[FloridaDocketData]:
        """
        Scrape Florida dockets with full metadata.

        This method yields FloridaDocketData objects with all available
        Florida-specific fields.

        Args:
            year: Filter by year (applied client-side)
            status: 'open', 'closed', or None for all
            limit: Maximum number of dockets to return
            industries: List of industry codes to fetch (E, G, T, W, X)

        Yields:
            FloridaDocketData objects
        """
        logger.info(f"Starting Florida ClerkOffice API docket discovery (limit={limit})...")

        seen_dockets = set()
        total = 0

        # Determine which API calls to make based on status
        if status == 'open':
            docket_types = ['D']  # Just open
        elif status == 'closed':
            docket_types = ['C']  # Just closed
        else:
            docket_types = ['D', 'O', 'C']  # All types

        # Industry types - API doesn't support 'A' for all, must iterate
        industry_types = industries or ['E', 'G', 'T', 'W', 'X']

        # Fetch from each docket type and industry combination
        for dtype in docket_types:
            for itype in industry_types:
                if total >= limit:
                    break

                try:
                    logger.debug(f"Fetching docket type {dtype}, industry {itype}...")
                    dockets = self.client.get_dockets_by_type(
                        docket_type=dtype,
                        industry_type=itype
                    )

                    for docket in dockets:
                        if total >= limit:
                            break

                        docket_num = docket.get('docketnum') or docket.get('docketId')
                        if not docket_num:
                            continue

                        # Skip duplicates
                        if docket_num in seen_dockets:
                            continue
                        seen_dockets.add(docket_num)

                        # Year filter
                        if year:
                            filed_date_str = docket.get('docketedDate')
                            if filed_date_str:
                                try:
                                    docket_year = int(filed_date_str[:4])
                                    if docket_year != year:
                                        continue
                                except (ValueError, TypeError):
                                    pass

                        # Parse and yield
                        docket_data = self._parse_api_result(docket)
                        if docket_data:
                            yield docket_data
                            total += 1

                except Exception as e:
                    logger.error(f"Error fetching docket type {dtype}, industry {itype}: {e}")

            if total >= limit:
                break

        logger.info(f"Scraped {total} dockets from Florida ClerkOffice API")

    def get_docket_detail(self, docket_number: str) -> Optional[DocketRecord]:
        """Get detailed information for a specific docket."""
        docket_data = self.get_florida_docket_detail(docket_number)
        return docket_data.to_docket_record() if docket_data else None

    def get_florida_docket_detail(self, docket_number: str) -> Optional[FloridaDocketData]:
        """Get detailed Florida docket information."""
        try:
            details = self.client.get_docket_details(docket_number)
            if details:
                return self._parse_api_result(details)
        except Exception as e:
            logger.error(f"Error fetching Florida docket {docket_number}: {e}")
        return None

    def test_connection(self) -> bool:
        """Test if scraper can connect to the ClerkOffice API."""
        try:
            # Try to fetch open dockets as a connectivity test
            self.client.get_open_dockets()
            return True
        except Exception as e:
            logger.error(f"Connection test failed for Florida ClerkOffice API: {e}")
            return False
