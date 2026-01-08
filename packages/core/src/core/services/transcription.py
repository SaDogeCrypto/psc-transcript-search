"""
Abstract transcription service interface.

Provides a protocol for audio transcription services (Whisper, etc.)
that can be implemented by different providers.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Protocol
from pathlib import Path


@dataclass
class TranscriptionSegment:
    """A single segment of transcribed audio."""
    index: int
    start: float  # Start time in seconds
    end: float    # End time in seconds
    text: str
    confidence: Optional[float] = None
    speaker: Optional[str] = None


@dataclass
class TranscriptionResult:
    """Result of audio transcription."""
    success: bool
    text: str = ""
    segments: List[TranscriptionSegment] = field(default_factory=list)
    model: Optional[str] = None
    cost_usd: float = 0.0
    duration_seconds: Optional[float] = None
    error: Optional[str] = None


class TranscriptionService(ABC):
    """Abstract base class for transcription services."""

    @abstractmethod
    def transcribe(
        self,
        audio_path: Path,
        language: str = "en",
        initial_prompt: Optional[str] = None,
    ) -> TranscriptionResult:
        """
        Transcribe an audio file.

        Args:
            audio_path: Path to the audio file
            language: Language code (default: "en")
            initial_prompt: Optional context prompt to improve accuracy

        Returns:
            TranscriptionResult with text, segments, and metadata
        """
        pass

    @abstractmethod
    def get_cost_estimate(self, duration_seconds: float) -> float:
        """Estimate cost for transcribing audio of given duration."""
        pass


__all__ = ['TranscriptionSegment', 'TranscriptionResult', 'TranscriptionService']
