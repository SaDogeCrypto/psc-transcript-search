"""
Arizona Corporation Commission eDocket Scraper

API Endpoint: https://efiling.azcc.gov/api/edocket/searchByDocketDetailRequest
Docket format: X-XXXXXX-XX-XXXX (e.g., E-01345A-19-0236, W-02703A-25-0189)

This scraper uses the direct REST API instead of Playwright for much faster bulk access.
"""

import requests
import logging
from datetime import datetime
from typing import Iterator, Optional

from ..base import BaseDocketScraper, DocketRecord

logger = logging.getLogger(__name__)


# Map docket type names to utility sectors
DOCKET_TYPE_TO_SECTOR = {
    'Electric': 'electric',
    'Gas': 'gas',
    'Water': 'water',
    'Sewer': 'water',
    'Telecommunications': 'telecom',
    'Railroad Safety': 'transportation',
    'Securities': 'other',
    'Line Siting Committee': 'electric',
}


class ArizonaDocketScraper(BaseDocketScraper):
    """
    Scraper for Arizona Corporation Commission eDocket.

    Uses the direct REST API at efiling.azcc.gov for fast bulk access.
    Can fetch all ~25,000 dockets in about 30 seconds.
    """

    state_code = 'AZ'
    state_name = 'Arizona'
    base_url = 'https://edocket.azcc.gov'
    search_url = 'https://edocket.azcc.gov/search/docket-search'
    api_url = 'https://efiling.azcc.gov/api/edocket/searchByDocketDetailRequest'

    def __init__(self):
        super().__init__()
        self.session.headers.update({
            'Content-Type': 'application/json',
            'Accept': 'application/json',
        })

    def scrape_docket_list(
        self,
        year: Optional[int] = None,
        status: Optional[str] = None,
        limit: int = 1000
    ) -> Iterator[DocketRecord]:
        """
        Scrape Arizona dockets using direct API access.

        Args:
            year: Filter by year (uses date range filter)
            status: Not used (API doesn't support status filter well)
            limit: Maximum number of dockets to return

        Yields:
            DocketRecord objects
        """
        logger.info(f"Starting Arizona docket discovery (limit={limit})...")

        # Build date filter if year specified
        date_from = None
        date_to = None
        if year:
            date_from = f"{year}-01-01T00:00:00"
            date_to = f"{year}-12-31T23:59:59"

        page = 0
        page_size = min(5000, limit)  # API supports up to 5000 per request
        total_fetched = 0

        while total_fetched < limit:
            skip = page * page_size
            rows_to_fetch = min(page_size, limit - total_fetched)

            payload = {
                "companyID": None,
                "entityName": None,
                "docketID": None,
                "yearMatter": None,
                "docketTypeID": None,
                "documentID": None,
                "caseTypeID": None,
                "docketStatusID": None,
                "docketNumber": None,
                "searchAsString": True,
                "descriptionContains": None,
                "docketDateSearchFrom": date_from,
                "docketDateSearchTo": date_to,
                "currentPageIndex": page,
                "rowsPerPage": rows_to_fetch,
                "rowsToSkip": skip,
            }

            try:
                response = self.session.post(self.api_url, json=payload, timeout=60)
                response.raise_for_status()
                data = response.json()
            except Exception as e:
                logger.error(f"Error fetching page {page}: {e}")
                break

            results = data.get("searchResult", [])
            if not results:
                logger.info(f"No more results at page {page}")
                break

            logger.info(f"Page {page}: fetched {len(results)} dockets (total: {total_fetched + len(results)})")

            for item in results:
                if total_fetched >= limit:
                    break

                record = self._parse_api_result(item)
                if record:
                    yield record
                    total_fetched += 1

            # Check if we've reached the end
            if len(results) < rows_to_fetch:
                break

            page += 1

        logger.info(f"Scraped {total_fetched} dockets from Arizona")

    def _parse_api_result(self, item: dict) -> Optional[DocketRecord]:
        """Parse an API result into a DocketRecord."""
        try:
            docket_number = item.get("docketNumber")
            if not docket_number:
                return None

            # Parse filing date
            filing_date = None
            filed_date_str = item.get("filedDate")
            if filed_date_str:
                try:
                    # Format: "2025-12-31T00:00:00"
                    dt = datetime.fromisoformat(filed_date_str.replace('Z', '+00:00'))
                    filing_date = dt.strftime('%Y-%m-%d')
                except (ValueError, AttributeError):
                    pass

            # Map docket type to sector
            docket_type = item.get("docketType", "")
            sector = DOCKET_TYPE_TO_SECTOR.get(docket_type)

            # Build source URL
            docket_id = item.get("docketID")
            source_url = f"https://edocket.azcc.gov/search/docket-search/item-detail/{docket_id}" if docket_id else None

            return DocketRecord(
                docket_number=docket_number,
                title=item.get("description", "").strip() if item.get("description") else None,
                utility_name=item.get("companyName"),
                filing_date=filing_date,
                status="open",  # API doesn't clearly indicate status
                case_type=item.get("caseType") or docket_type,
                source_url=source_url,
                description=item.get("description", "").strip() if item.get("description") else None,
            )

        except Exception as e:
            logger.debug(f"Error parsing docket: {e}")
            return None

    def get_docket_detail(self, docket_number: str) -> Optional[DocketRecord]:
        """
        Get detailed information for a specific docket.

        Uses the API with docketNumber filter.
        """
        payload = {
            "docketNumber": docket_number,
            "searchAsString": True,
            "currentPageIndex": 0,
            "rowsPerPage": 10,
            "rowsToSkip": 0,
        }

        try:
            response = self.session.post(self.api_url, json=payload, timeout=30)
            response.raise_for_status()
            data = response.json()

            results = data.get("searchResult", [])
            if results:
                return self._parse_api_result(results[0])

        except Exception as e:
            logger.error(f"Error fetching docket {docket_number}: {e}")

        return None
