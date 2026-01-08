"""
Florida ClerkOffice API scraper.

Scrapes docket information from the Florida PSC ClerkOffice API.
API endpoint: https://www.psc.state.fl.us/api/ClerkOffice

Docket format: YYYYNNNN-XX (e.g., 20240001-EI)
"""

import logging
from datetime import datetime
from typing import Optional, Dict, Any, List

import httpx
from sqlalchemy.orm import Session

from src.core.scrapers.base import Scraper, ScraperResult
from src.core.models.docket import Docket
from src.states.florida.models.docket import FLDocketDetails

logger = logging.getLogger(__name__)

CLERK_OFFICE_API = "https://www.psc.state.fl.us/api/ClerkOffice"


class ClerkOfficeScraper(Scraper):
    """
    Scrape dockets from Florida PSC ClerkOffice API.

    API Endpoints:
    - GET /Dockets - List dockets (supports year filter)
    - GET /Dockets/{docketNumber} - Get single docket details

    Usage:
        scraper = ClerkOfficeScraper(db)
        result = scraper.scrape(year=2024)
    """

    name = "clerk_office"
    state_code = "FL"

    def __init__(self, db: Session):
        self.db = db
        self.client = httpx.Client(timeout=30.0, follow_redirects=True)

    def scrape(
        self,
        year: Optional[int] = None,
        docket_type: Optional[str] = None,
        limit: int = 1000,
        **kwargs
    ) -> ScraperResult:
        """
        Scrape dockets from ClerkOffice API.

        Args:
            year: Filter by year (defaults to current year)
            docket_type: Filter by docket type
            limit: Maximum dockets to fetch

        Returns:
            ScraperResult with counts
        """
        year = year or datetime.now().year
        logger.info(f"Scraping FL dockets for year {year}")

        try:
            # Fetch docket list from API
            params = {"year": year}
            if docket_type:
                params["type"] = docket_type

            response = self.client.get(
                f"{CLERK_OFFICE_API}/Dockets",
                params=params
            )
            response.raise_for_status()
            dockets_data = response.json()

            # Handle both list and dict responses
            if isinstance(dockets_data, dict):
                dockets_data = dockets_data.get("dockets", [])

            items_created = 0
            items_updated = 0
            errors = []

            for docket_data in dockets_data[:limit]:
                try:
                    created = self._upsert_docket(docket_data)
                    if created:
                        items_created += 1
                    else:
                        items_updated += 1
                except Exception as e:
                    error_msg = f"Error processing {docket_data.get('docketNumber', 'unknown')}: {e}"
                    logger.error(error_msg)
                    errors.append(error_msg)

            self.db.commit()

            logger.info(
                f"FL ClerkOffice scrape complete: "
                f"{items_created} created, {items_updated} updated, {len(errors)} errors"
            )

            return ScraperResult(
                success=True,
                items_found=len(dockets_data),
                items_created=items_created,
                items_updated=items_updated,
                errors=errors
            )

        except httpx.HTTPError as e:
            logger.exception("ClerkOffice API request failed")
            return ScraperResult(success=False, errors=[f"HTTP error: {e}"])
        except Exception as e:
            logger.exception("ClerkOffice scrape failed")
            return ScraperResult(success=False, errors=[str(e)])

    def get_item(self, docket_number: str) -> Optional[Dict[str, Any]]:
        """
        Fetch single docket by number.

        Args:
            docket_number: Florida docket number (e.g., "20240001-EI")

        Returns:
            Docket data dict, or None if not found
        """
        try:
            response = self.client.get(f"{CLERK_OFFICE_API}/Dockets/{docket_number}")
            if response.status_code == 200:
                return response.json()
        except Exception as e:
            logger.error(f"Error fetching docket {docket_number}: {e}")

        return None

    def _upsert_docket(self, data: dict) -> bool:
        """
        Insert or update docket.

        Args:
            data: Docket data from API

        Returns:
            True if created, False if updated
        """
        docket_number = data.get("docketNumber") or data.get("number")
        if not docket_number:
            raise ValueError("Missing docket number in API response")

        # Check if exists
        existing = self.db.query(Docket).filter(
            Docket.state_code == "FL",
            Docket.docket_number == docket_number
        ).first()

        if existing:
            # Update existing docket
            existing.title = data.get("title") or data.get("description")
            existing.status = data.get("status")
            existing.docket_type = data.get("docketType") or data.get("type")
            existing.updated_at = datetime.utcnow()

            # Update FL details
            if existing.fl_details:
                existing.fl_details.clerk_office_data = data
                existing.fl_details.last_synced_at = datetime.utcnow()
                existing.fl_details.applicant_name = data.get("applicantName") or data.get("applicant")

            return False

        # Parse docket number components
        parsed = FLDocketDetails.parse_docket_number(docket_number)

        # Create new docket
        docket = Docket(
            state_code="FL",
            docket_number=docket_number,
            title=data.get("title") or data.get("description"),
            status=data.get("status"),
            docket_type=data.get("docketType") or data.get("type"),
            filed_date=self._parse_date(data.get("filedDate") or data.get("openDate")),
            closed_date=self._parse_date(data.get("closedDate")),
            source_system="clerk_office",
            external_id=data.get("id"),
        )
        self.db.add(docket)
        self.db.flush()  # Get docket.id

        # Create FL details
        fl_details = FLDocketDetails(
            docket_id=docket.id,
            year=parsed.get("year"),
            sequence_number=parsed.get("sequence_number"),
            sector_code=parsed.get("sector_code"),
            applicant_name=data.get("applicantName") or data.get("applicant"),
            clerk_office_id=data.get("id"),
            clerk_office_data=data,
            last_synced_at=datetime.utcnow(),
        )
        self.db.add(fl_details)

        return True

    def _parse_date(self, date_str: Optional[str]):
        """Parse date string from API response."""
        if not date_str:
            return None

        try:
            # Try ISO format first
            if "T" in date_str:
                return datetime.fromisoformat(date_str.replace("Z", "+00:00")).date()
            # Try common formats
            for fmt in ["%Y-%m-%d", "%m/%d/%Y", "%m-%d-%Y"]:
                try:
                    return datetime.strptime(date_str, fmt).date()
                except ValueError:
                    continue
        except Exception:
            pass

        return None

    def validate_config(self) -> tuple[bool, str]:
        """Validate that ClerkOffice API is accessible."""
        try:
            response = self.client.get(f"{CLERK_OFFICE_API}/Dockets", params={"year": 2024})
            if response.status_code == 200:
                return True, ""
            return False, f"API returned status {response.status_code}"
        except Exception as e:
            return False, f"Cannot reach ClerkOffice API: {e}"
