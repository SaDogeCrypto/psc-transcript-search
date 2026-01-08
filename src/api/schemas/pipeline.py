"""
Pipeline schemas for admin API.
"""

from typing import Optional, List, Dict, Any
from uuid import UUID
from datetime import datetime

from pydantic import BaseModel


class PipelineRunRequest(BaseModel):
    """Request to run pipeline stage."""
    stage: str  # "transcribe", "analyze"
    state_code: Optional[str] = "FL"
    hearing_ids: Optional[List[UUID]] = None  # Specific hearings, or None for auto-select
    status_filter: Optional[str] = None  # Filter by transcript_status
    limit: int = 10  # Max hearings to process


class StageResultResponse(BaseModel):
    """Result from a single stage execution."""
    hearing_id: str
    success: bool
    skipped: bool = False
    error: Optional[str] = None
    cost_usd: float = 0.0
    model: Optional[str] = None
    data: Optional[Dict[str, Any]] = None


class PipelineStatusResponse(BaseModel):
    """Pipeline execution status."""
    status: str  # "queued", "running", "completed", "failed"
    stage: str
    total: int = 0
    successful: int = 0
    failed: int = 0
    skipped: int = 0
    total_cost_usd: float = 0.0
    results: Optional[List[StageResultResponse]] = None
    errors: Optional[List[Dict[str, str]]] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class PipelinePendingResponse(BaseModel):
    """Response for pending items query."""
    stage: str
    state_code: Optional[str]
    count: int
    hearings: List[Dict[str, Any]]
