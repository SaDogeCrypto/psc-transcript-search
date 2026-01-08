"""
Services module - shared business logic.

Provides:
- StorageService: File storage (local/Azure Blob)
- SearchService: Full-text and semantic search
"""

from src.core.services.storage import StorageService
from src.core.services.search import SearchService

__all__ = [
    "StorageService",
    "SearchService",
]
