"""Service abstractions for transcription, LLM, storage, etc."""

from core.services.transcription import (
    TranscriptionService,
    TranscriptionResult,
    TranscriptionSegment,
)
from core.services.llm import (
    LLMService,
    LLMResponse,
    Message,
)

__all__ = [
    'TranscriptionService',
    'TranscriptionResult',
    'TranscriptionSegment',
    'LLMService',
    'LLMResponse',
    'Message',
]
