"""
Florida state implementation.

Florida PSC data sources:
- ClerkOffice API: Docket metadata
- Thunderstone: Document search (filings, orders, tariffs)
- RSS/YouTube: Hearing recordings

Docket format: YYYYNNNN-XX
- YYYY: Year
- NNNN: Sequence number
- XX: Sector code (EI=Electric, GU=Gas, WU=Water, etc.)
"""

from src.states.registry import StateRegistry

# Import Florida components
from src.states.florida.models import FLDocketDetails, FLDocumentDetails, FLHearingDetails
from src.states.florida.scrapers import ClerkOfficeScraper, ThunderstoneScraper, RSSHearingScraper

STATE_CODE = "FL"

# Register metadata
StateRegistry.register_metadata(STATE_CODE, {
    "full_name": "Florida",
    "commission_name": "Florida Public Service Commission",
    "commission_abbrev": "FPSC",
    "website": "https://www.psc.state.fl.us",
    "docket_format": r"^\d{8}-[A-Z]{2}$",  # YYYYNNNN-XX
    "docket_example": "20240001-EI",
})

# Register configuration
StateRegistry.register_config(STATE_CODE, {
    "clerk_office_api": "https://www.psc.state.fl.us/api/ClerkOffice",
    "thunderstone_base": "https://www.psc.state.fl.us",
    "rss_feed": "https://www.youtube.com/feeds/videos.xml?channel_id=UCw4KPSs7zVOUHMQJglvDOyw",
    "youtube_channel_id": "UCw4KPSs7zVOUHMQJglvDOyw",
})

# Register scrapers
StateRegistry.register_scraper(STATE_CODE, "clerk_office", ClerkOfficeScraper)
StateRegistry.register_scraper(STATE_CODE, "thunderstone", ThunderstoneScraper)
StateRegistry.register_scraper(STATE_CODE, "rss_hearings", RSSHearingScraper)

# Sector codes
FL_SECTOR_CODES = {
    "EI": "Electric",
    "GU": "Gas Utility",
    "WU": "Water Utility",
    "WS": "Water/Sewer",
    "TL": "Telecommunications",
    "TP": "Transportation Pipeline",
    "EC": "Electric Cogeneration",
    "EM": "Electric Miscellaneous",
    "GM": "Gas Miscellaneous",
    "WM": "Water Miscellaneous",
    "TM": "Telecommunications Miscellaneous",
}

__all__ = [
    "STATE_CODE",
    "FL_SECTOR_CODES",
    "FLDocketDetails",
    "FLDocumentDetails",
    "FLHearingDetails",
    "ClerkOfficeScraper",
    "ThunderstoneScraper",
    "RSSHearingScraper",
]
