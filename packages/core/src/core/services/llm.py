"""
Abstract LLM service interface.

Provides a protocol for LLM-based analysis services that can be
implemented by different providers (OpenAI, Azure, Anthropic, etc.)
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any


@dataclass
class LLMResponse:
    """Response from an LLM completion."""
    success: bool
    content: str = ""
    parsed_json: Optional[Dict[str, Any]] = None
    model: Optional[str] = None
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    error: Optional[str] = None


@dataclass
class Message:
    """A message in a conversation."""
    role: str  # "system", "user", "assistant"
    content: str


class LLMService(ABC):
    """Abstract base class for LLM services."""

    @abstractmethod
    def complete(
        self,
        messages: List[Message],
        temperature: float = 0.2,
        max_tokens: Optional[int] = None,
        json_mode: bool = False,
    ) -> LLMResponse:
        """
        Generate a completion from the LLM.

        Args:
            messages: Conversation messages
            temperature: Sampling temperature (0.0 to 1.0)
            max_tokens: Maximum tokens to generate
            json_mode: If True, expect JSON output

        Returns:
            LLMResponse with content and metadata
        """
        pass

    @abstractmethod
    def count_tokens(self, text: str) -> int:
        """Count tokens in a text string."""
        pass

    @abstractmethod
    def get_cost_estimate(self, input_tokens: int, output_tokens: int) -> float:
        """Estimate cost for given token counts."""
        pass


__all__ = ['LLMResponse', 'Message', 'LLMService']
