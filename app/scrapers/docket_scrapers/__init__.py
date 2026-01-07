"""
Docket scrapers for various PSC websites.
"""

from typing import Dict, Type, List
from .base import BaseDocketScraper, DocketRecord, MockDocketScraper

# Import state scrapers as they're implemented
# These will be added as scrapers are developed
DOCKET_SCRAPERS: Dict[str, Type[BaseDocketScraper]] = {}

# Track which states have implemented scrapers
IMPLEMENTED_STATES: List[str] = []

try:
    # Prefer API-based scraper for faster bulk access
    from .states.florida_api import FloridaDocketScraperAPI
    DOCKET_SCRAPERS['FL'] = FloridaDocketScraperAPI
    IMPLEMENTED_STATES.append('FL')
except ImportError:
    try:
        # Fall back to Playwright-based scraper
        from .states.florida import FloridaDocketScraper
        DOCKET_SCRAPERS['FL'] = FloridaDocketScraper
        IMPLEMENTED_STATES.append('FL')
    except ImportError:
        pass

try:
    # Georgia API now returns HTML instead of JSON, use Playwright scraper
    from .states.georgia import GeorgiaDocketScraper
    DOCKET_SCRAPERS['GA'] = GeorgiaDocketScraper
    IMPLEMENTED_STATES.append('GA')
except ImportError:
    pass

try:
    from .states.texas import TexasDocketScraper
    DOCKET_SCRAPERS['TX'] = TexasDocketScraper
    IMPLEMENTED_STATES.append('TX')
except ImportError:
    pass

try:
    from .states.california import CaliforniaDocketScraper
    DOCKET_SCRAPERS['CA'] = CaliforniaDocketScraper
    IMPLEMENTED_STATES.append('CA')
except ImportError:
    pass

try:
    from .states.ohio import OhioDocketScraper
    DOCKET_SCRAPERS['OH'] = OhioDocketScraper
    IMPLEMENTED_STATES.append('OH')
except ImportError:
    pass

try:
    from .states.arizona import ArizonaDocketScraper
    DOCKET_SCRAPERS['AZ'] = ArizonaDocketScraper
    IMPLEMENTED_STATES.append('AZ')
except ImportError:
    pass


def get_scraper(state_code: str) -> BaseDocketScraper:
    """
    Get scraper instance for a state.

    Args:
        state_code: Two-letter state code

    Returns:
        Scraper instance

    Raises:
        ValueError: If no scraper implemented for state
    """
    state_code = state_code.upper()
    if state_code not in DOCKET_SCRAPERS:
        raise ValueError(f"No scraper implemented for {state_code}")
    return DOCKET_SCRAPERS[state_code]()


def get_available_states() -> List[str]:
    """Get list of states with implemented scrapers."""
    return list(DOCKET_SCRAPERS.keys())


def is_scraper_available(state_code: str) -> bool:
    """Check if a scraper is available for a state."""
    return state_code.upper() in DOCKET_SCRAPERS


__all__ = [
    'BaseDocketScraper',
    'DocketRecord',
    'MockDocketScraper',
    'get_scraper',
    'get_available_states',
    'is_scraper_available',
    'DOCKET_SCRAPERS',
    'IMPLEMENTED_STATES',
]
