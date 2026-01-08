"""
Pipeline base classes.

Provides abstract interfaces that all pipeline stages must implement.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TypeVar, Generic, Tuple, Any, Optional
from sqlalchemy.orm import Session

# Generic type for the model being processed
T = TypeVar('T')


@dataclass
class StageResult:
    """
    Result from pipeline stage execution.

    Attributes:
        success: Whether the stage completed successfully
        data: Optional dict with stage-specific output data
        error: Error message if success is False
        cost_usd: Processing cost in USD (for paid APIs)
        model: Model/service used for processing
        skipped: Whether item was skipped (already processed, etc.)
    """
    success: bool
    data: Optional[dict] = None
    error: str = ""
    cost_usd: float = 0.0
    model: str = ""
    skipped: bool = False

    def __post_init__(self):
        if self.data is None:
            self.data = {}


@dataclass
class BatchResult:
    """
    Result from processing a batch of items.

    Aggregates individual StageResults.
    """
    total: int = 0
    successful: int = 0
    failed: int = 0
    skipped: int = 0
    total_cost_usd: float = 0.0
    errors: list = field(default_factory=list)
    results: list = field(default_factory=list)

    def add_result(self, item_id: Any, result: StageResult):
        """Add a stage result to the batch."""
        self.total += 1
        self.results.append({"id": str(item_id), "result": result})

        if result.skipped:
            self.skipped += 1
        elif result.success:
            self.successful += 1
        else:
            self.failed += 1
            if result.error:
                self.errors.append({"id": str(item_id), "error": result.error})

        self.total_cost_usd += result.cost_usd

    @property
    def success_rate(self) -> float:
        """Calculate success rate (excluding skipped)."""
        processed = self.total - self.skipped
        if processed == 0:
            return 0.0
        return self.successful / processed


class PipelineStage(ABC, Generic[T]):
    """
    Abstract base class for pipeline stages.

    Stages process items (typically Hearings) through
    the pipeline. Each stage must implement:
    - name: Unique identifier for the stage
    - validate(): Check if item can be processed
    - execute(): Process the item

    Example implementation:
        class TranscribeStage(PipelineStage[Hearing]):
            name = "transcribe"

            def validate(self, hearing, db):
                if not hearing.audio_url:
                    return False, "No audio URL"
                return True, ""

            def execute(self, hearing, db):
                # Transcription logic here
                return StageResult(success=True, data={"words": 1000})
    """

    name: str  # Stage identifier (e.g., "transcribe", "analyze")

    @abstractmethod
    def validate(self, item: T, db: Session) -> Tuple[bool, str]:
        """
        Check if item can be processed by this stage.

        Args:
            item: The item to validate
            db: Database session

        Returns:
            Tuple of (can_process, reason)
            - can_process: True if item can be processed
            - reason: If False, explains why (for logging)
        """
        pass

    @abstractmethod
    def execute(self, item: T, db: Session) -> StageResult:
        """
        Execute the stage on an item.

        Args:
            item: The item to process
            db: Database session (stage should commit changes)

        Returns:
            StageResult with success status and any output data
        """
        pass

    def process(self, item: T, db: Session) -> StageResult:
        """
        Validate and execute stage on item.

        Convenience method that combines validate + execute.
        """
        can_process, reason = self.validate(item, db)
        if not can_process:
            return StageResult(success=True, skipped=True, error=reason)

        return self.execute(item, db)
