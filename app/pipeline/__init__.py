"""
Pipeline Orchestrator Package

Database-driven pipeline for processing PSC hearings through:
  discovery → download → transcription → analysis → extraction

Usage:
    python -m app.pipeline.orchestrator run --once
    python -m app.pipeline.orchestrator run --states FL,GA --max-cost 50
    python -m app.pipeline.orchestrator status
"""

from app.pipeline.orchestrator import (
    PipelineOrchestrator,
    get_orchestrator,
    PipelineStatus,
    HEARING_STATUSES,
)

__all__ = [
    "PipelineOrchestrator",
    "get_orchestrator",
    "PipelineStatus",
    "HEARING_STATUSES",
]
