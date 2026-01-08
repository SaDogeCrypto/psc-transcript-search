"""
Florida PSC API.

FastAPI application for Florida regulatory intelligence:
- /api/fl/dockets: Docket listing and search
- /api/fl/documents: Document search
- /api/fl/hearings: Hearing transcripts
- /api/fl/health: Health check
- /api/fl/status: Pipeline status
"""

from florida.api.app import app, create_app

__all__ = ['app', 'create_app']
