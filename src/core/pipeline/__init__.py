"""
Pipeline module - processing stages for hearings.

Provides:
- PipelineStage: Abstract base class for all stages
- StageResult: Result container for stage execution
- PipelineOrchestrator: Runs stages on hearings
- TranscribeStage: Whisper transcription (shared)
- AnalyzeStage: LLM analysis (shared)
"""

from src.core.pipeline.base import PipelineStage, StageResult
from src.core.pipeline.orchestrator import PipelineOrchestrator
from src.core.pipeline.transcribe import TranscribeStage
from src.core.pipeline.analyze import AnalyzeStage

__all__ = [
    "PipelineStage",
    "StageResult",
    "PipelineOrchestrator",
    "TranscribeStage",
    "AnalyzeStage",
]
