"""
Base Stage class for pipeline stages.

Each stage handles one step of the pipeline (download, transcribe, analyze, extract).
This is the abstract base that specific implementations extend.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, Protocol, TypeVar, Generic


@dataclass
class StageResult:
    """Result of a stage execution."""
    success: bool
    output: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    cost_usd: float = 0.0
    should_retry: bool = True  # False for permanent failures
    skip_remaining: bool = False  # True to skip all remaining stages


class BaseStage(ABC):
    """
    Abstract base class for pipeline stages.

    Each stage must define:
    - name: Unique stage identifier (e.g., 'download', 'transcribe')
    - in_progress_status: Status while stage is running (e.g., 'downloading')
    - complete_status: Status after successful completion (e.g., 'transcribing')

    Subclasses implement validate() and execute() for their specific logic.
    The on_start/on_success/on_error hooks can be overridden for lifecycle events.
    """

    name: str
    in_progress_status: str
    complete_status: str

    @abstractmethod
    def validate(self, item: Any, db: Any) -> bool:
        """
        Check if item can be processed by this stage.

        Returns True if all prerequisites are met, False otherwise.
        Should NOT modify anything - just validate.
        """
        pass

    @abstractmethod
    def execute(self, item: Any, db: Any) -> StageResult:
        """
        Execute the stage processing.

        Returns StageResult with success/failure, output data, and cost.
        Should handle its own errors and return appropriate StageResult.
        """
        pass

    def on_start(self, item: Any, job: Any, db: Any):
        """
        Hook called before execution starts.

        Override to perform setup (e.g., create temp directories).
        """
        pass

    def on_success(self, item: Any, job: Any, result: StageResult, db: Any):
        """
        Hook called after successful execution.

        Override to perform cleanup or additional processing.
        """
        pass

    def on_error(self, item: Any, job: Any, result: StageResult, db: Any):
        """
        Hook called after failed execution.

        Override to perform error cleanup.
        """
        pass

    def __repr__(self):
        return f"<{self.__class__.__name__}(name={self.name})>"


__all__ = ['StageResult', 'BaseStage']
