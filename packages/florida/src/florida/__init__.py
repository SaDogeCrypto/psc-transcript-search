"""
Florida PSC Regulatory Intelligence Platform.

This package provides Florida-specific implementations for:
- Docket tracking from ClerkOffice API
- Document search from Thunderstone
- Hearing transcript processing
- Full-text search across all content

Usage:
    from florida import config
    from florida.scrapers import FloridaClerkOfficeScraper
    from florida.api import app as florida_app
"""

__version__ = "0.1.0"


# Florida sector codes used in docket numbers
FL_SECTOR_CODES = {
    'EI': {'name': 'Electric - Investor Owned', 'industry': 'Electric'},
    'EU': {'name': 'Electric - Municipal/Coop', 'industry': 'Electric'},
    'EP': {'name': 'Electric - Performance', 'industry': 'Electric'},
    'EC': {'name': 'Electric - Conservation', 'industry': 'Electric'},
    'EQ': {'name': 'Electric - Qualifying Facility', 'industry': 'Electric'},
    'GU': {'name': 'Gas - Utility', 'industry': 'Gas'},
    'GP': {'name': 'Gas - Pipeline', 'industry': 'Gas'},
    'WU': {'name': 'Water - Utility', 'industry': 'Water'},
    'WS': {'name': 'Water - Sewer', 'industry': 'Water'},
    'WP': {'name': 'Water - Pass-through', 'industry': 'Water'},
    'SU': {'name': 'Sewer - Utility', 'industry': 'Sewer'},
    'TX': {'name': 'Telecom - Exchange', 'industry': 'Telecom'},
    'TL': {'name': 'Telecom - Long Distance', 'industry': 'Telecom'},
    'TI': {'name': 'Telecom - Interexchange', 'industry': 'Telecom'},
}
