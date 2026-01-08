"""
Florida Entity Linking Stage.

Pipeline stage that extracts and links entities (dockets, utilities, topics)
from analyzed hearing transcripts.

Runs after the Analyze stage.
"""
import logging
from dataclasses import dataclass
from typing import Optional, Dict, Any, List

from sqlalchemy.orm import Session

from florida.models import FLHearing
from florida.services.entity_linking import FloridaEntityLinker, EntityLinkingResult

logger = logging.getLogger(__name__)


@dataclass
class EntityLinkingStageResult:
    """Result from entity linking stage."""
    success: bool
    hearings_processed: int = 0
    total_dockets: int = 0
    total_utilities: int = 0
    total_topics: int = 0
    needs_review: int = 0
    errors: List[str] = None

    def __post_init__(self):
        if self.errors is None:
            self.errors = []


class FLEntityLinkingStage:
    """
    Entity Linking Stage for Florida pipeline.

    Processes analyzed hearings to:
    1. Extract docket numbers from transcripts using regex
    2. Match utilities from LLM analysis against canonical records
    3. Match topics from LLM analysis against canonical records
    4. Create junction table entries with confidence scores
    5. Flag low-confidence items for review
    """

    name = "entity_linking"

    def __init__(self, db: Session):
        self.db = db
        self.linker = FloridaEntityLinker(db)

    def validate(self, hearing: FLHearing) -> tuple[bool, str]:
        """Check if hearing can have entity linking run."""
        from florida.models.linking import FLHearingDocket

        # Must be analyzed
        if hearing.transcript_status != "analyzed":
            return False, f"Not analyzed (status: {hearing.transcript_status})"

        # Check if already linked
        existing = self.db.query(FLHearingDocket).filter(
            FLHearingDocket.hearing_id == hearing.id
        ).count()
        if existing > 0:
            return False, "Already has entity links"

        return True, ""

    def execute(self, hearing: FLHearing) -> EntityLinkingResult:
        """Run entity linking for a single hearing."""
        return self.linker.link_hearing(hearing.id, skip_existing=False)

    def run_batch(
        self,
        limit: Optional[int] = None,
        on_progress: Optional[callable] = None
    ) -> EntityLinkingStageResult:
        """
        Run entity linking on all eligible hearings.

        Args:
            limit: Max hearings to process
            on_progress: Progress callback

        Returns:
            EntityLinkingStageResult with statistics
        """
        result = EntityLinkingStageResult(success=True)

        try:
            stats = self.linker.link_all_hearings(
                status="analyzed",
                limit=limit,
                on_progress=on_progress
            )

            result.hearings_processed = stats['total_processed']
            result.total_dockets = stats['total_dockets']
            result.total_utilities = stats['total_utilities']
            result.total_topics = stats['total_topics']
            result.needs_review = stats['needs_review']
            result.errors = stats['errors']

            if stats['errors']:
                result.success = len(stats['errors']) < stats['total_processed']

        except Exception as e:
            logger.exception("Entity linking stage failed")
            result.success = False
            result.errors.append(str(e))

        return result


__all__ = ['FLEntityLinkingStage', 'EntityLinkingStageResult']
