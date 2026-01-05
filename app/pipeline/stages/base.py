"""
Base Stage class for pipeline stages.

Each stage handles one step of the pipeline (download, transcribe, analyze, extract).
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session

from app.models.database import Hearing, PipelineJob


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
    - in_progress_status: Hearing status while stage is running (e.g., 'downloading')
    - complete_status: Hearing status after successful completion (e.g., 'transcribing')
    """

    name: str
    in_progress_status: str
    complete_status: str

    @abstractmethod
    def validate(self, hearing: Hearing, db: Session) -> bool:
        """
        Check if hearing can be processed by this stage.

        Returns True if all prerequisites are met, False otherwise.
        Should NOT modify anything - just validate.
        """
        pass

    @abstractmethod
    def execute(self, hearing: Hearing, db: Session) -> StageResult:
        """
        Execute the stage processing.

        Returns StageResult with success/failure, output data, and cost.
        Should handle its own errors and return appropriate StageResult.
        """
        pass

    def on_start(self, hearing: Hearing, job: PipelineJob, db: Session):
        """
        Hook called before execution starts.

        Override to perform setup (e.g., create temp directories).
        """
        pass

    def on_success(self, hearing: Hearing, job: PipelineJob, result: StageResult, db: Session):
        """
        Hook called after successful execution.

        Override to perform cleanup or additional processing.
        """
        pass

    def on_error(self, hearing: Hearing, job: PipelineJob, result: StageResult, db: Session):
        """
        Hook called after failed execution.

        Override to perform error cleanup.
        """
        pass

    def __repr__(self):
        return f"<{self.__class__.__name__}(name={self.name})>"
