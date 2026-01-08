"""
Florida-specific pipeline stages.

These stages adapt the core transcription and analysis logic to work with
Florida's data models (FLHearing, FLTranscriptSegment, FLAnalysis).
"""

from florida.pipeline.stages.transcribe import FLTranscribeStage
from florida.pipeline.stages.analyze import FLAnalyzeStage

__all__ = [
    'FLTranscribeStage',
    'FLAnalyzeStage',
]
