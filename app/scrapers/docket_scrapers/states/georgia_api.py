"""
Georgia Public Service Commission API Scraper

API Base: https://psc.ga.gov/search/facts-service/
Documentation discovered via network interception.

Key endpoints:
- /search/facts-service/ - Main search with filters
- /search/service-facts-docket/ - Docket details
"""

import requests
import logging
from datetime import datetime
from typing import Iterator, Optional, List, Dict, Any

from ..base import BaseDocketScraper, DocketRecord

logger = logging.getLogger(__name__)


# Industry type mappings
INDUSTRY_MAP = {
    'Electric': 'electric',
    'Gas': 'gas',
    'Telecommunications': 'telecom',
    'Pipeline': 'gas',
    'Transportation': 'transportation',
    'Administration': 'other',
    'GUFPA': 'other',
}


class GeorgiaAPIClient:
    """Client for Georgia PSC REST API."""

    BASE_URL = "https://psc.ga.gov/search"

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'Accept': 'application/json',
            'User-Agent': 'Mozilla/5.0 (compatible; PSCResearchBot/1.0)',
        })

    def search_dockets(
        self,
        query: str = "",
        industry: str = "Any",
        status: str = "Any",
        result_type: str = "Docket",
        page_size: int = 500,
        page_number: int = 1,
        sort_column: str = "Filed",
        sort_direction: str = "DESC",
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Search for dockets using the GA PSC API.

        Args:
            query: Search text
            industry: Any, Electric, Gas, Telecommunications, etc.
            status: Any, Open, Closed, Certified, etc.
            result_type: "Docket", "Document", or "Docket OR Document"
            page_size: Results per page (max 500)
            page_number: Page number (1-indexed)
            sort_column: Column to sort by
            sort_direction: ASC or DESC
            from_date: Start date (MM/DD/YYYY)
            to_date: End date (MM/DD/YYYY)

        Returns:
            Dict with resultsCount and resultsItems
        """
        params = {
            'q': query,
            'limit': page_size,
            'type': result_type,
            'industry': industry,
            'status': status,
            'isPublic': 'true',
            'sortColumn': sort_column,
            'sortDirection': sort_direction,
            'pageSize': page_size,
            'pageNumber': page_number,
        }

        if from_date:
            params['date'] = 'Custom Range'
            params['fromDate'] = from_date
        if to_date:
            params['toDate'] = to_date
        else:
            params['date'] = 'Any'

        response = self.session.get(
            f"{self.BASE_URL}/facts-service/",
            params=params,
            timeout=60
        )
        response.raise_for_status()
        return response.json()

    def get_docket_detail(self, docket_id: int) -> Dict[str, Any]:
        """Get detailed information for a specific docket."""
        params = {
            'docketId': docket_id,
            'sortDirection': 'DESC',
            'sortColumn': 'Filed',
            'pageSize': 100,
            'pageNumber': 1,
        }
        response = self.session.get(
            f"{self.BASE_URL}/service-facts-docket/",
            params=params,
            timeout=30
        )
        response.raise_for_status()
        return response.json()


class GeorgiaDocketScraperAPI(BaseDocketScraper):
    """
    API-based scraper for Georgia Public Service Commission.

    Uses the REST API at psc.ga.gov for fast bulk access.
    """

    state_code = 'GA'
    state_name = 'Georgia'
    base_url = 'https://psc.ga.gov'
    search_url = 'https://psc.ga.gov/search/'

    def __init__(self):
        super().__init__()
        self.api = GeorgiaAPIClient()

    def scrape_docket_list(
        self,
        year: Optional[int] = None,
        status: Optional[str] = None,
        limit: int = 1000
    ) -> Iterator[DocketRecord]:
        """
        Scrape Georgia dockets using the REST API.

        Args:
            year: Filter by year
            status: 'open', 'closed', or None for all
            limit: Maximum number of dockets to return

        Yields:
            DocketRecord objects
        """
        logger.info(f"Starting Georgia API docket discovery (limit={limit})...")

        # Build date filter
        from_date = None
        to_date = None
        if year:
            from_date = f"01/01/{year}"
            to_date = f"12/31/{year}"

        # Map status
        api_status = "Any"
        if status == 'open':
            api_status = "Open"
        elif status == 'closed':
            api_status = "Closed"

        page = 1
        page_size = min(500, limit)  # API max is 500
        total_fetched = 0
        seen_ids = set()

        while total_fetched < limit:
            try:
                logger.info(f"Fetching page {page}...")

                result = self.api.search_dockets(
                    query="",
                    industry="Any",
                    status=api_status,
                    result_type="Docket",
                    page_size=page_size,
                    page_number=page,
                    from_date=from_date,
                    to_date=to_date,
                )

                items = result.get('resultsItems', [])
                total_count = result.get('resultsCount', 0)

                if not items:
                    logger.info(f"No more results at page {page}")
                    break

                logger.info(f"Page {page}: {len(items)} items (total available: {total_count})")

                for item in items:
                    if total_fetched >= limit:
                        break

                    # Skip non-docket results
                    if item.get('recordType') != 'Docket':
                        continue

                    # Skip duplicates
                    docket_id = item.get('id')
                    if docket_id in seen_ids:
                        continue
                    seen_ids.add(docket_id)

                    record = self._parse_api_result(item)
                    if record:
                        yield record
                        total_fetched += 1

                # Check if we've gotten all results
                if len(items) < page_size:
                    break

                page += 1

            except Exception as e:
                logger.error(f"Error fetching page {page}: {e}")
                break

        logger.info(f"Scraped {total_fetched} dockets from Georgia API")

    def _parse_api_result(self, item: Dict[str, Any]) -> Optional[DocketRecord]:
        """Parse an API result into a DocketRecord."""
        try:
            docket_id = item.get('id')
            if not docket_id:
                return None

            # Georgia uses numeric IDs, not traditional docket numbers
            docket_number = str(docket_id)

            # Parse filing date
            filing_date = None
            date_str = item.get('docketDate')
            if date_str:
                try:
                    # Format: "2024-01-15T00:00:00"
                    dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                    filing_date = dt.strftime('%Y-%m-%d')
                except (ValueError, AttributeError):
                    pass

            # Map industry to sector
            industry = item.get('industry', '')
            sector = INDUSTRY_MAP.get(industry)

            # Map status
            status_str = item.get('status', '').lower()
            if 'open' in status_str:
                status = 'open'
            elif 'closed' in status_str:
                status = 'closed'
            else:
                status = status_str[:50] if status_str else 'open'

            # Build source URL
            source_url = f"https://psc.ga.gov/search/facts/?docket={docket_id}"

            return DocketRecord(
                docket_number=docket_number,
                title=item.get('title'),
                utility_name=item.get('companyName'),
                filing_date=filing_date,
                status=status,
                case_type=industry,
                source_url=source_url,
                description=item.get('title'),
            )

        except Exception as e:
            logger.debug(f"Error parsing Georgia docket: {e}")
            return None

    def get_docket_detail(self, docket_number: str) -> Optional[DocketRecord]:
        """Get detailed information for a specific docket."""
        try:
            docket_id = int(docket_number)
            details = self.api.get_docket_detail(docket_id)
            if details:
                # The detail endpoint returns document list, not docket info
                # Use the search endpoint to get docket info
                result = self.api.search_dockets(
                    query=str(docket_id),
                    result_type="Docket",
                    page_size=10,
                )
                items = result.get('resultsItems', [])
                for item in items:
                    if item.get('id') == docket_id:
                        return self._parse_api_result(item)
        except Exception as e:
            logger.error(f"Error fetching Georgia docket {docket_number}: {e}")
        return None
