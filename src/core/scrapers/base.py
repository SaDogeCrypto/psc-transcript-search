"""
Scraper base classes.

Provides abstract interface that all state-specific scrapers implement.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List


@dataclass
class ScraperResult:
    """
    Result from scraper execution.

    Attributes:
        success: Whether the scrape completed successfully
        items_found: Total items found from source
        items_created: New items inserted into database
        items_updated: Existing items updated
        errors: List of error messages
    """
    success: bool
    items_found: int = 0
    items_created: int = 0
    items_updated: int = 0
    errors: List[str] = field(default_factory=list)

    @property
    def items_processed(self) -> int:
        """Total items processed (created + updated)."""
        return self.items_created + self.items_updated


class Scraper(ABC):
    """
    Abstract base class for data scrapers.

    Each state implements scrapers for its specific data sources:
    - Florida: ClerkOffice API, Thunderstone, RSS feeds
    - Texas: PUCT API
    - California: CPUC API

    Example implementation:
        class ClerkOfficeScraper(Scraper):
            name = "clerk_office"
            state_code = "FL"

            def scrape(self, year=None):
                # Fetch dockets from API
                return ScraperResult(success=True, items_created=10)
    """

    name: str  # Scraper identifier (e.g., "clerk_office", "thunderstone")
    state_code: str  # Two-letter state code

    @abstractmethod
    def scrape(self, **kwargs) -> ScraperResult:
        """
        Execute scrape operation.

        Args:
            **kwargs: Scraper-specific parameters (date range, filters, etc.)

        Returns:
            ScraperResult with counts of items found/created/updated
        """
        pass

    @abstractmethod
    def get_item(self, item_id: str) -> Optional[Dict[str, Any]]:
        """
        Fetch a single item by ID.

        Args:
            item_id: The source system's ID for the item

        Returns:
            Dict with item data, or None if not found
        """
        pass

    def validate_config(self) -> tuple[bool, str]:
        """
        Validate scraper configuration.

        Override to check for required API keys, endpoints, etc.

        Returns:
            Tuple of (is_valid, error_message)
        """
        return True, ""
