"""
Core module - shared functionality across all states.

Provides:
- Configuration management
- Database connection and session handling
- Base models and mixins
- Abstract pipeline stages
- Abstract scraper interfaces
"""

from src.core.config import Settings, get_settings
from src.core.database import get_db, init_db, engine

__all__ = [
    "Settings",
    "get_settings",
    "get_db",
    "init_db",
    "engine",
]
