"""
Test state registry functionality.
"""

import pytest

from src.states.registry import StateRegistry


def test_get_available_states():
    """Test getting available states."""
    states = StateRegistry.get_available_states()
    assert "FL" in states


def test_get_florida_scrapers():
    """Test getting Florida scrapers."""
    scrapers = StateRegistry.get_state_scrapers("FL")
    assert "clerk_office" in scrapers
    assert "thunderstone" in scrapers
    assert "rss_hearings" in scrapers


def test_get_scraper_class():
    """Test getting scraper class."""
    from src.states.florida.scrapers import ClerkOfficeScraper

    scraper_class = StateRegistry.get_scraper("FL", "clerk_office")
    assert scraper_class == ClerkOfficeScraper


def test_get_unknown_scraper():
    """Test getting non-existent scraper."""
    scraper_class = StateRegistry.get_scraper("FL", "nonexistent")
    assert scraper_class is None


def test_get_florida_metadata():
    """Test getting Florida metadata."""
    metadata = StateRegistry.get_metadata("FL")
    assert metadata["full_name"] == "Florida"
    assert metadata["commission_name"] == "Florida Public Service Commission"
    assert "docket_format" in metadata


def test_get_all_scrapers():
    """Test getting all scrapers."""
    all_scrapers = StateRegistry.get_all_scrapers()
    assert "FL" in all_scrapers
    assert len(all_scrapers["FL"]) >= 3
