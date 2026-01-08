"""
Admin API routes.

Requires authentication via X-API-Key header.
"""

from src.api.routes.admin import pipeline, scrapers

__all__ = ["pipeline", "scrapers"]
