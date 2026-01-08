"""
API schemas - Pydantic models for request/response validation.
"""

from src.api.schemas.common import PaginatedResponse, MessageResponse
from src.api.schemas.docket import DocketResponse, DocketListResponse, DocketDetail
from src.api.schemas.document import DocumentResponse, DocumentListResponse
from src.api.schemas.hearing import (
    HearingResponse,
    HearingListResponse,
    HearingDetail,
    TranscriptSegmentResponse,
    AnalysisResponse,
)
from src.api.schemas.search import SearchRequest, SearchResponse, SearchResult
from src.api.schemas.pipeline import (
    PipelineRunRequest,
    PipelineStatusResponse,
    StageResultResponse,
)
from src.api.schemas.scraper import (
    ScraperRunRequest,
    ScraperResultResponse,
)

__all__ = [
    # Common
    "PaginatedResponse",
    "MessageResponse",
    # Docket
    "DocketResponse",
    "DocketListResponse",
    "DocketDetail",
    # Document
    "DocumentResponse",
    "DocumentListResponse",
    # Hearing
    "HearingResponse",
    "HearingListResponse",
    "HearingDetail",
    "TranscriptSegmentResponse",
    "AnalysisResponse",
    # Search
    "SearchRequest",
    "SearchResponse",
    "SearchResult",
    # Pipeline
    "PipelineRunRequest",
    "PipelineStatusResponse",
    "StageResultResponse",
    # Scraper
    "ScraperRunRequest",
    "ScraperResultResponse",
]
