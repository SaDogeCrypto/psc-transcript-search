"""
API module - FastAPI application.

Provides REST API for:
- Public endpoints: dockets, documents, hearings, search
- Admin endpoints: pipeline management, scraper control
"""

from src.api.main import create_app, app

__all__ = ["create_app", "app"]
