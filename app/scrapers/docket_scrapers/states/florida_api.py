"""
Florida Public Service Commission API Scraper

API Base: https://pscweb.floridapsc.com/api/ClerkOffice/
Documentation discovered via network interception.

Key endpoints:
- /OpenDockets - List all open dockets
- /PscDocketsByType - List dockets by type/industry
- /DocketDetailsByDocketsNo - Full docket details
- /SearchDocketsByDocketNumber - Autocomplete search
"""

import requests
import logging
from datetime import datetime
from typing import Iterator, Optional, List, Dict, Any

from ..base import BaseDocketScraper, DocketRecord

logger = logging.getLogger(__name__)


# Industry type mappings
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
    'D': 'open',      # Open Dockets
    'O': 'recent',    # Opened Last 30 Days
    'C': 'closed',    # Closed Last 30 Days
}


class FloridaAPIClient:
    """Client for Florida PSC REST API."""

    BASE_URL = "https://pscweb.floridapsc.com/api/ClerkOffice"

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'Accept': 'application/json',
            'User-Agent': 'Mozilla/5.0 (compatible; PSCResearchBot/1.0)',
        })

    def get_open_dockets(self) -> List[Dict[str, Any]]:
        """Get all open dockets."""
        response = self.session.get(f"{self.BASE_URL}/OpenDockets", timeout=60)
        response.raise_for_status()
        data = response.json()
        return data.get('result', []) if isinstance(data, dict) else data

    def get_dockets_by_type(
        self,
        docket_type: str = 'D',  # D=Open, O=Recent, C=Closed
        industry_type: str = 'E',  # E=Electric, G=Gas, T=Telecom, W=Water, X=Other
    ) -> List[Dict[str, Any]]:
        """Get dockets filtered by type and industry."""
        params = {
            'docketType': docket_type,
            'industryType': industry_type,
        }
        response = self.session.get(
            f"{self.BASE_URL}/PscDocketsByType",
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
        params = {'docketNo': docket_no}
        response = self.session.get(
            f"{self.BASE_URL}/DocketDetailsByDocketsNo",
            params=params,
            timeout=30
        )
        response.raise_for_status()
        data = response.json()
        return data.get('result') if isinstance(data, dict) else data


class FloridaDocketScraperAPI(BaseDocketScraper):
    """
    API-based scraper for Florida Public Service Commission.

    Uses the REST API at pscweb.floridapsc.com for fast bulk access.
    """

    state_code = 'FL'
    state_name = 'Florida'
    base_url = 'http://www.psc.state.fl.us'
    search_url = 'http://www.psc.state.fl.us/ClerkOffice/DocketSearch'

    def __init__(self):
        super().__init__()
        self.api = FloridaAPIClient()

    def scrape_docket_list(
        self,
        year: Optional[int] = None,
        status: Optional[str] = None,
        limit: int = 1000
    ) -> Iterator[DocketRecord]:
        """
        Scrape Florida dockets using the REST API.

        Args:
            year: Filter by year (applied client-side)
            status: 'open', 'closed', or None for all
            limit: Maximum number of dockets to return

        Yields:
            DocketRecord objects
        """
        logger.info(f"Starting Florida API docket discovery (limit={limit})...")

        all_dockets = []
        seen_dockets = set()

        # Determine which API calls to make based on status
        if status == 'open':
            docket_types = ['D']  # Just open
        elif status == 'closed':
            docket_types = ['C']  # Just closed
        else:
            docket_types = ['D', 'O', 'C']  # All types

        # Industry types - API doesn't support 'A' for all, must iterate
        industry_types = ['E', 'G', 'T', 'W', 'X']

        # Fetch from each docket type and industry combination
        for dtype in docket_types:
            for itype in industry_types:
                if len(all_dockets) >= limit:
                    break

                try:
                    logger.info(f"Fetching docket type {dtype}, industry {itype}...")
                    dockets = self.api.get_dockets_by_type(docket_type=dtype, industry_type=itype)

                    for docket in dockets:
                        docket_num = docket.get('docketnum') or docket.get('docketId')
                        if not docket_num:
                            continue

                        # Skip duplicates
                        if docket_num in seen_dockets:
                            continue
                        seen_dockets.add(docket_num)

                        # Year filter
                        if year:
                            filed_date = docket.get('docketedDate')
                            if filed_date:
                                try:
                                    docket_year = int(filed_date[:4])
                                    if docket_year != year:
                                        continue
                                except (ValueError, TypeError):
                                    pass

                        all_dockets.append(docket)

                        if len(all_dockets) >= limit:
                            break

                except Exception as e:
                    logger.error(f"Error fetching docket type {dtype}, industry {itype}: {e}")

            if len(all_dockets) >= limit:
                break

        logger.info(f"Fetched {len(all_dockets)} dockets from Florida API")

        # Convert to DocketRecord
        count = 0
        for docket in all_dockets:
            if count >= limit:
                break

            record = self._parse_api_result(docket)
            if record:
                yield record
                count += 1

        logger.info(f"Yielded {count} docket records from Florida")

    def _parse_api_result(self, item: Dict[str, Any]) -> Optional[DocketRecord]:
        """Parse an API result into a DocketRecord."""
        try:
            docket_number = item.get('docketnum') or str(item.get('docketId', ''))
            if not docket_number:
                return None

            # Parse filing date
            filing_date = None
            filed_date_str = item.get('docketedDate')
            if filed_date_str:
                try:
                    # Format: "2024-01-15T00:00:00"
                    dt = datetime.fromisoformat(filed_date_str.replace('Z', '+00:00'))
                    filing_date = dt.strftime('%Y-%m-%d')
                except (ValueError, AttributeError):
                    pass

            # Map industry code to sector
            industry_code = item.get('industryCode', '')
            sector = INDUSTRY_CODES.get(industry_code)

            # Determine status
            close_date = item.get('docketCloseDate')
            status = 'closed' if close_date else 'open'

            # Build source URL
            source_url = f"http://www.psc.state.fl.us/ClerkOffice/DocketFiling?docket={docket_number}"

            return DocketRecord(
                docket_number=docket_number,
                title=item.get('docketTitle'),
                utility_name=item.get('companyName'),
                filing_date=filing_date,
                status=status,
                case_type=item.get('caseType'),
                source_url=source_url,
                description=item.get('docketTitle'),
            )

        except Exception as e:
            logger.debug(f"Error parsing Florida docket: {e}")
            return None

    def get_docket_detail(self, docket_number: str) -> Optional[DocketRecord]:
        """Get detailed information for a specific docket."""
        try:
            details = self.api.get_docket_details(docket_number)
            if details:
                return self._parse_api_result(details)
        except Exception as e:
            logger.error(f"Error fetching Florida docket {docket_number}: {e}")
        return None
