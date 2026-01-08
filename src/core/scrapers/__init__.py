"""
Scraper module - data source adapters.

Provides:
- Scraper: Abstract base class for all scrapers
- ScraperResult: Result container for scrape operations
"""

from src.core.scrapers.base import Scraper, ScraperResult

__all__ = [
    "Scraper",
    "ScraperResult",
]
