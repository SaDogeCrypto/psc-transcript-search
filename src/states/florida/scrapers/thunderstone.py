"""
Florida Thunderstone document scraper.

Scrapes documents from Florida PSC Thunderstone search.
Searches across multiple profiles:
- library: Library documents
- filingsCurrent: Current filings
- orders: Commission orders
- tariffs: Utility tariffs
"""

import logging
import re
from datetime import datetime
from typing import Optional, Dict, Any, List
from xml.etree import ElementTree

import httpx
from sqlalchemy.orm import Session

from src.core.scrapers.base import Scraper, ScraperResult
from src.core.models.docket import Docket
from src.core.models.document import Document
from src.states.florida.models.document import FLDocumentDetails

logger = logging.getLogger(__name__)

THUNDERSTONE_BASE = "https://www.psc.state.fl.us"

# Thunderstone search profiles with their endpoints
THUNDERSTONE_PROFILES = {
    "library": f"{THUNDERSTONE_BASE}/library/websearch.asp",
    "filingsCurrent": f"{THUNDERSTONE_BASE}/dockets/websearch.asp",
    "orders": f"{THUNDERSTONE_BASE}/orders/websearch.asp",
    "tariffs": f"{THUNDERSTONE_BASE}/tariffs/websearch.asp",
}


class ThunderstoneScraper(Scraper):
    """
    Scrape documents from Florida PSC Thunderstone search.

    Thunderstone is a document search system that indexes:
    - Library documents (historical records)
    - Current filings (recent submissions)
    - Orders (commission decisions)
    - Tariffs (utility rate schedules)

    Usage:
        scraper = ThunderstoneScraper(db)
        result = scraper.scrape(docket_number="20240001-EI", profile="filingsCurrent")
    """

    name = "thunderstone"
    state_code = "FL"

    def __init__(self, db: Session):
        self.db = db
        self.client = httpx.Client(timeout=60.0, follow_redirects=True)

    def scrape(
        self,
        docket_number: Optional[str] = None,
        profile: str = "filingsCurrent",
        query: Optional[str] = None,
        max_results: int = 100,
        **kwargs
    ) -> ScraperResult:
        """
        Search Thunderstone for documents.

        Args:
            docket_number: Filter by docket number
            profile: Search profile (library, filingsCurrent, orders, tariffs)
            query: Free-text search query
            max_results: Maximum results to return

        Returns:
            ScraperResult with counts
        """
        if profile not in THUNDERSTONE_PROFILES:
            return ScraperResult(
                success=False,
                errors=[f"Unknown profile: {profile}. Valid: {list(THUNDERSTONE_PROFILES.keys())}"]
            )

        search_query = docket_number or query or ""
        logger.info(f"Searching Thunderstone {profile} for: {search_query}")

        try:
            # Build search URL
            search_url = THUNDERSTONE_PROFILES[profile]
            params = {
                "query": search_query,
                "max": max_results,
                "fmt": "xml",  # Request XML format for easier parsing
            }

            response = self.client.get(search_url, params=params)
            response.raise_for_status()

            # Parse results
            results = self._parse_response(response.text, profile)
            logger.info(f"Found {len(results)} documents in {profile}")

            # Look up docket if searching by docket number
            docket = None
            if docket_number:
                docket = self.db.query(Docket).filter(
                    Docket.state_code == "FL",
                    Docket.docket_number == docket_number
                ).first()

            items_created = 0
            items_updated = 0
            errors = []

            for doc_data in results:
                try:
                    created = self._upsert_document(doc_data, profile, docket)
                    if created:
                        items_created += 1
                    else:
                        items_updated += 1
                except Exception as e:
                    error_msg = f"Error: {e}"
                    logger.error(error_msg)
                    errors.append(error_msg)

            self.db.commit()

            return ScraperResult(
                success=True,
                items_found=len(results),
                items_created=items_created,
                items_updated=items_updated,
                errors=errors
            )

        except httpx.HTTPError as e:
            logger.exception("Thunderstone request failed")
            return ScraperResult(success=False, errors=[f"HTTP error: {e}"])
        except Exception as e:
            logger.exception("Thunderstone scrape failed")
            return ScraperResult(success=False, errors=[str(e)])

    def get_item(self, thunderstone_id: str) -> Optional[Dict[str, Any]]:
        """
        Fetch document by Thunderstone ID.

        Note: Thunderstone doesn't have a direct ID lookup API,
        so this returns cached data from the database.
        """
        fl_details = self.db.query(FLDocumentDetails).filter(
            FLDocumentDetails.thunderstone_id == thunderstone_id
        ).first()

        if fl_details and fl_details.document:
            return fl_details.document.to_dict()

        return None

    def _parse_response(self, content: str, profile: str) -> List[Dict[str, Any]]:
        """
        Parse Thunderstone search results.

        Thunderstone returns HTML or XML depending on request.
        This attempts XML parsing first, then falls back to HTML.
        """
        results = []

        try:
            # Try XML parsing
            root = ElementTree.fromstring(content)

            for item in root.findall(".//result") or root.findall(".//doc"):
                doc_data = {
                    "id": item.findtext("id") or item.get("id"),
                    "title": item.findtext("title"),
                    "url": item.findtext("url") or item.findtext("link"),
                    "score": float(item.findtext("score") or 0),
                    "date": item.findtext("date"),
                    "description": item.findtext("description") or item.findtext("snippet"),
                }
                if doc_data["id"] or doc_data["url"]:
                    results.append(doc_data)

        except ElementTree.ParseError:
            # Fall back to HTML/text parsing
            results = self._parse_html_results(content, profile)

        return results

    def _parse_html_results(self, content: str, profile: str) -> List[Dict[str, Any]]:
        """
        Parse HTML search results (fallback parser).

        This is a basic parser that extracts links and titles from HTML.
        """
        results = []

        # Extract document links using regex
        # Pattern matches links to documents with various extensions
        link_pattern = r'href="([^"]+\.(?:pdf|doc|docx|txt))"[^>]*>([^<]+)'

        for match in re.finditer(link_pattern, content, re.IGNORECASE):
            url, title = match.groups()

            # Make URL absolute if relative
            if not url.startswith("http"):
                url = f"{THUNDERSTONE_BASE}{url}"

            # Generate ID from URL
            doc_id = re.sub(r'[^\w]', '_', url)[-50:]

            results.append({
                "id": doc_id,
                "title": title.strip(),
                "url": url,
                "score": 0,
            })

        return results

    def _upsert_document(
        self,
        data: Dict[str, Any],
        profile: str,
        docket: Optional[Docket]
    ) -> bool:
        """
        Insert or update document.

        Args:
            data: Document data from search results
            profile: Thunderstone profile
            docket: Associated docket (if known)

        Returns:
            True if created, False if updated
        """
        thunderstone_id = data.get("id")
        if not thunderstone_id:
            thunderstone_id = data.get("url", "")[-50:]

        # Check if exists
        existing_detail = self.db.query(FLDocumentDetails).filter(
            FLDocumentDetails.thunderstone_id == thunderstone_id
        ).first()

        if existing_detail:
            # Update existing
            doc = existing_detail.document
            doc.title = data.get("title") or doc.title
            doc.updated_at = datetime.utcnow()
            existing_detail.thunderstone_score = data.get("score")
            return False

        # Create new document
        doc = Document(
            state_code="FL",
            docket_id=docket.id if docket else None,
            title=data.get("title") or "Untitled Document",
            document_type=self._infer_document_type(profile, data),
            file_url=data.get("url"),
            filed_date=self._parse_date(data.get("date")),
            source_system="thunderstone",
            external_id=thunderstone_id,
        )
        self.db.add(doc)
        self.db.flush()

        # Create FL details
        fl_details = FLDocumentDetails(
            document_id=doc.id,
            thunderstone_id=thunderstone_id,
            profile=profile,
            thunderstone_score=data.get("score"),
        )
        self.db.add(fl_details)

        return True

    def _infer_document_type(self, profile: str, data: Dict) -> str:
        """Infer document type from profile and data."""
        profile_types = {
            "orders": "order",
            "tariffs": "tariff",
            "filingsCurrent": "filing",
            "library": "document",
        }

        title = (data.get("title") or "").lower()

        # Check title for specific document types
        if "order" in title:
            return "order"
        if "testimony" in title:
            return "testimony"
        if "exhibit" in title:
            return "exhibit"
        if "motion" in title:
            return "motion"
        if "brief" in title:
            return "brief"
        if "tariff" in title:
            return "tariff"

        return profile_types.get(profile, "document")

    def _parse_date(self, date_str: Optional[str]):
        """Parse date from search result."""
        if not date_str:
            return None

        try:
            for fmt in ["%Y-%m-%d", "%m/%d/%Y", "%B %d, %Y"]:
                try:
                    return datetime.strptime(date_str, fmt).date()
                except ValueError:
                    continue
        except Exception:
            pass

        return None
