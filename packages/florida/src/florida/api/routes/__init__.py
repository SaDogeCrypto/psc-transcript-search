"""
Florida API routes.

Routers for Florida endpoints:
- dockets: Docket listing, detail, search
- documents: Document search, download
- hearings: Hearing transcripts
- search: Unified full-text search
"""

from florida.api.routes import dockets
from florida.api.routes import documents
from florida.api.routes import hearings
from florida.api.routes import search

__all__ = ['dockets', 'documents', 'hearings', 'search']
