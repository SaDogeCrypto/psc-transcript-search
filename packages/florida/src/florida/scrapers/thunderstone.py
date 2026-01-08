"""
Florida PSC Thunderstone Document Search Scraper.

Scrapes documents from the Florida PSC Thunderstone full-text search API.

API Base: https://pscweb.floridapsc.com/api/thunderstone

Key endpoints:
- /getprofiles - List available search profiles
- /getcategories/{profile} - Get categories for a profile
- /search - Full-text document search
"""

import logging
import re
import time
from datetime import datetime, date
from typing import Iterator, Optional, List, Dict, Any
from dataclasses import dataclass, field
from urllib.parse import urljoin, quote

import requests

from florida.config import get_config, FloridaConfig

logger = logging.getLogger(__name__)


# Known search profiles from the Thunderstone API
THUNDERSTONE_PROFILES = {
    'library': 'All PSC Documents',
    'filingsCurrent': 'Current Year Filings',
    'filings': 'Older Filings (Pre-2014)',
    'orders': 'Commission Orders',
    'financials': 'Financial Reports',
    'tariffs': 'Tariff Filings',
    'everything': 'Everything',
    'website': 'Website Content',
}

# Default sort orders
LIST_ORDERS = {
    'relevance': 'Relevance',
    'date_desc': 'Newest First',
    'date_asc': 'Oldest First',
}


@dataclass
class ThunderstoneDocument:
    """
    Document result from Thunderstone search.

    Contains document metadata and content excerpts.
    """
    # Document identifiers
    thunderstone_id: Optional[str] = None
    document_number: Optional[str] = None

    # Metadata
    title: str = ""
    document_type: Optional[str] = None
    profile: Optional[str] = None

    # Docket association
    docket_number: Optional[str] = None

    # File info
    file_url: Optional[str] = None
    file_type: Optional[str] = None
    file_size_bytes: Optional[int] = None

    # Dates
    filed_date: Optional[date] = None
    effective_date: Optional[date] = None

    # Content
    content_excerpt: Optional[str] = None
    content_highlight: Optional[str] = None

    # Florida-specific
    filer_name: Optional[str] = None
    category: Optional[str] = None

    # Search metadata
    relevance_score: Optional[float] = None

    # Raw data
    raw_data: Optional[Dict[str, Any]] = None


@dataclass
class ThunderstoneProfile:
    """Search profile available in Thunderstone."""
    id: str
    name: str
    description: Optional[str] = None
    document_count: Optional[int] = None


class FloridaThunderstoneClient:
    """Low-level client for Florida PSC Thunderstone REST API."""

    def __init__(self, config: Optional[FloridaConfig] = None):
        self.config = config or get_config()
        self.base_url = self.config.thunderstone_base_url
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

    def get_profiles(self) -> List[Dict[str, Any]]:
        """Get available search profiles."""
        self._rate_limit()
        response = self.session.get(
            f"{self.base_url}/getprofiles",
            timeout=30
        )
        response.raise_for_status()
        data = response.json()
        return data.get('result', []) if isinstance(data, dict) else data

    def get_categories(self, profile: str) -> List[Dict[str, Any]]:
        """Get categories for a specific profile."""
        self._rate_limit()
        response = self.session.get(
            f"{self.base_url}/getcategories/{profile}",
            timeout=30
        )
        response.raise_for_status()
        data = response.json()
        return data.get('result', []) if isinstance(data, dict) else data

    def search(
        self,
        search_text: str,
        profile: str = 'library',
        page: int = 1,
        per_page: int = 50,
        order: str = 'relevance',
        category: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Execute a full-text search.

        Args:
            search_text: Query text
            profile: Search profile (library, filingsCurrent, orders, etc.)
            page: Page number (1-based)
            per_page: Results per page
            order: Sort order (relevance, date_desc, date_asc)
            category: Optional category filter

        Returns:
            Dict with results, total_count, and pagination info
        """
        self._rate_limit()

        params = {
            'SelectedProfile': profile,
            'SearchText': search_text,
            'ListOrder': order,
            'ElementPerPage': per_page,
            'CurrentPage': page,
        }

        if category:
            params['Category'] = category

        response = self.session.get(
            f"{self.base_url}/search",
            params=params,
            timeout=60
        )
        response.raise_for_status()
        return response.json()


class FloridaThunderstoneScraper:
    """
    Florida PSC document scraper using the Thunderstone search API.

    This scraper provides full-text document search across:
    - Commission orders
    - Filings and testimony
    - Financial reports
    - Tariffs
    - All PSC documents

    Search results include:
    - Document title and type
    - File URL for download
    - Docket association
    - Filing date
    - Content excerpts with search term highlighting
    """

    # Pattern to extract docket number from text
    DOCKET_PATTERN = re.compile(r'\b(\d{4}\d{4})-?([A-Z]{2})\b')

    def __init__(self, config: Optional[FloridaConfig] = None):
        self.config = config or get_config()
        self.client = FloridaThunderstoneClient(self.config)

    def _parse_date(self, date_str: Optional[str]) -> Optional[date]:
        """Parse a date string from the API."""
        if not date_str:
            return None
        try:
            # Try various formats
            for fmt in ['%Y-%m-%dT%H:%M:%S', '%Y-%m-%d', '%m/%d/%Y', '%m-%d-%Y']:
                try:
                    return datetime.strptime(date_str.split('T')[0], fmt.split('T')[0]).date()
                except ValueError:
                    continue
            # ISO format with timezone
            dt = datetime.fromisoformat(date_str.replace('Z', '+00:00').split('+')[0])
            return dt.date()
        except (ValueError, AttributeError):
            return None

    def _parse_file_size(self, size_str: Optional[str]) -> Optional[int]:
        """Parse file size string like '22K' or '1.1M' to bytes."""
        if not size_str:
            return None
        if isinstance(size_str, int):
            return size_str
        try:
            size_str = size_str.strip().upper()
            if size_str.endswith('K'):
                return int(float(size_str[:-1]) * 1024)
            elif size_str.endswith('M'):
                return int(float(size_str[:-1]) * 1024 * 1024)
            elif size_str.endswith('G'):
                return int(float(size_str[:-1]) * 1024 * 1024 * 1024)
            return int(size_str)
        except (ValueError, AttributeError):
            return None

    def _extract_docket_number(self, text: str) -> Optional[str]:
        """Extract a docket number from text."""
        match = self.DOCKET_PATTERN.search(text)
        if match:
            return f"{match.group(1)}-{match.group(2)}"
        return None

    def _parse_search_result(
        self,
        item: Dict[str, Any],
        profile: str
    ) -> Optional[ThunderstoneDocument]:
        """Parse a search result into a ThunderstoneDocument."""
        try:
            title = item.get('title') or item.get('Title', '')
            if not title:
                return None

            # Extract file URL
            file_url = item.get('url') or item.get('FileUrl') or item.get('Link')
            if file_url and not file_url.startswith('http'):
                file_url = urljoin('https://pscweb.floridapsc.com', file_url)

            # Determine file type from URL or content type
            file_type = None
            if file_url:
                if '.pdf' in file_url.lower():
                    file_type = 'PDF'
                elif '.doc' in file_url.lower():
                    file_type = 'DOC'
                elif '.xls' in file_url.lower():
                    file_type = 'XLS'

            # Extract docket number from title or content
            docket_number = (
                item.get('DocketNumber') or
                item.get('docket') or
                self._extract_docket_number(title) or
                self._extract_docket_number(item.get('Content', '') or '')
            )

            # Parse dates
            filed_date = self._parse_date(
                item.get('date_modified') or
                item.get('FiledDate') or
                item.get('Date') or
                item.get('date')
            )

            return ThunderstoneDocument(
                thunderstone_id=str(item.get('thunderstone_id') or item.get('Id') or item.get('id', '')),
                document_number=item.get('DocumentNumber'),
                title=title,
                document_type=item.get('DocumentType') or item.get('Type'),
                profile=profile,
                docket_number=docket_number,
                file_url=file_url,
                file_type=file_type,
                file_size_bytes=self._parse_file_size(item.get('size') or item.get('FileSize')),
                filed_date=filed_date,
                content_excerpt=item.get('document_abstract') or item.get('Content') or item.get('snippet'),
                content_highlight=item.get('Highlight'),
                filer_name=item.get('FilerName') or item.get('Company'),
                category=item.get('Category'),
                relevance_score=item.get('Score') or item.get('relevance'),
                raw_data=item,
            )

        except Exception as e:
            logger.debug(f"Error parsing Thunderstone result: {e}")
            return None

    def get_profiles(self) -> List[ThunderstoneProfile]:
        """Get available search profiles."""
        try:
            profiles = self.client.get_profiles()
            return [
                ThunderstoneProfile(
                    id=p.get('Id') or p.get('id', ''),
                    name=p.get('Name') or p.get('name', ''),
                    description=p.get('Description'),
                    document_count=p.get('DocumentCount'),
                )
                for p in profiles
            ]
        except Exception as e:
            logger.error(f"Error fetching Thunderstone profiles: {e}")
            return []

    def search(
        self,
        query: str,
        profile: str = 'library',
        docket_number: Optional[str] = None,
        document_type: Optional[str] = None,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
        limit: int = 100,
    ) -> Iterator[ThunderstoneDocument]:
        """
        Search for documents.

        Args:
            query: Search query text
            profile: Search profile (library, orders, filingsCurrent, etc.)
            docket_number: Filter by docket number
            document_type: Filter by document type
            date_from: Filter by date range start
            date_to: Filter by date range end
            limit: Maximum results to return

        Yields:
            ThunderstoneDocument objects
        """
        # Build enhanced query with filters
        search_text = query

        if docket_number:
            # Add docket number to search
            search_text = f"{search_text} {docket_number}"

        if document_type:
            search_text = f"{search_text} type:{document_type}"

        logger.info(f"Searching Thunderstone: '{search_text}' (profile={profile}, limit={limit})")

        page = 1
        per_page = min(50, limit)
        total_yielded = 0

        while total_yielded < limit:
            try:
                result = self.client.search(
                    search_text=search_text,
                    profile=profile,
                    page=page,
                    per_page=per_page,
                )

                # Extract results from response
                items = []
                if isinstance(result, dict):
                    items = (
                        result.get('result', {}).get('thunderstoneResults', []) or
                        result.get('result', {}).get('Results', []) or
                        result.get('thunderstoneResults', []) or
                        result.get('Results', []) or
                        result.get('results', []) or
                        []
                    )
                elif isinstance(result, list):
                    items = result

                if not items:
                    break

                for item in items:
                    if total_yielded >= limit:
                        break

                    doc = self._parse_search_result(item, profile)
                    if doc:
                        # Apply client-side date filtering
                        if date_from and doc.filed_date and doc.filed_date < date_from:
                            continue
                        if date_to and doc.filed_date and doc.filed_date > date_to:
                            continue

                        yield doc
                        total_yielded += 1

                # Check if more pages available
                total_results = 0
                if isinstance(result, dict):
                    total_results = (
                        result.get('result', {}).get('TotalResults', 0) or
                        result.get('TotalResults', 0) or
                        result.get('total', 0)
                    )

                if page * per_page >= total_results:
                    break

                page += 1

            except Exception as e:
                logger.error(f"Error searching Thunderstone page {page}: {e}")
                break

        logger.info(f"Returned {total_yielded} documents from Thunderstone")

    def search_by_docket(
        self,
        docket_number: str,
        profile: str = 'library',
        limit: int = 100,
    ) -> Iterator[ThunderstoneDocument]:
        """
        Search for all documents associated with a docket.

        Args:
            docket_number: Docket number to search for
            profile: Search profile
            limit: Maximum results

        Yields:
            ThunderstoneDocument objects
        """
        # Clean docket number for search
        clean_docket = docket_number.replace('-', ' ')
        yield from self.search(
            query=clean_docket,
            profile=profile,
            docket_number=docket_number,
            limit=limit,
        )

    def get_orders(
        self,
        query: str = '',
        limit: int = 100,
    ) -> Iterator[ThunderstoneDocument]:
        """
        Search for commission orders.

        Args:
            query: Optional search query
            limit: Maximum results

        Yields:
            ThunderstoneDocument objects (orders only)
        """
        search_query = query if query else '*'
        yield from self.search(
            query=search_query,
            profile='orders',
            limit=limit,
        )

    def get_recent_filings(
        self,
        query: str = '',
        limit: int = 100,
    ) -> Iterator[ThunderstoneDocument]:
        """
        Get recent filings from the current year.

        Args:
            query: Optional search query
            limit: Maximum results

        Yields:
            ThunderstoneDocument objects
        """
        search_query = query if query else '*'
        yield from self.search(
            query=search_query,
            profile='filingsCurrent',
            limit=limit,
        )

    def test_connection(self) -> bool:
        """Test if scraper can connect to the Thunderstone API."""
        try:
            profiles = self.client.get_profiles()
            return len(profiles) > 0
        except Exception as e:
            logger.error(f"Connection test failed for Florida Thunderstone API: {e}")
            return False
