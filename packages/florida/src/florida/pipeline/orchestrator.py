"""
Florida Pipeline Orchestrator.

Coordinates the execution of Florida PSC pipeline stages:
1. Docket Sync - Pull dockets from ClerkOffice API
2. Document Sync - Index documents from Thunderstone
3. Hearing Discovery - Find YouTube hearing videos
4. Transcription - Whisper transcription
5. Analysis - LLM analysis
6. Entity Extraction - Extract entities from transcripts
"""

import logging
from datetime import datetime
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from enum import Enum

from sqlalchemy.orm import Session

from florida.config import get_config, FloridaConfig
from florida.pipeline.docket_sync import DocketSyncStage, DocketSyncResult
from florida.pipeline.document_sync import DocumentSyncStage, DocumentSyncResult

logger = logging.getLogger(__name__)


class PipelineStage(Enum):
    """Available pipeline stages."""
    DOCKET_SYNC = "docket_sync"
    DOCUMENT_SYNC = "document_sync"
    HEARING_DISCOVERY = "hearing_discovery"
    TRANSCRIPTION = "transcription"
    ANALYSIS = "analysis"
    ENTITY_EXTRACTION = "entity_extraction"


@dataclass
class PipelineRun:
    """Record of a pipeline run."""
    run_id: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    stages_run: List[str] = field(default_factory=list)
    results: Dict[str, Any] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    success: bool = False


class FloridaPipelineOrchestrator:
    """
    Orchestrates Florida PSC pipeline execution.

    Provides both full pipeline runs and individual stage execution.
    Tracks pipeline history and provides status information.
    """

    def __init__(
        self,
        db: Session,
        config: Optional[FloridaConfig] = None
    ):
        self.db = db
        self.config = config or get_config()

        # Initialize stages
        self.docket_sync = DocketSyncStage(db, config)
        self.document_sync = DocumentSyncStage(db, config)

    def run_full_pipeline(
        self,
        year: Optional[int] = None,
        on_progress: Optional[callable] = None,
    ) -> PipelineRun:
        """
        Run the full Florida pipeline.

        This executes all stages in order:
        1. Docket Sync
        2. Document Sync

        (Hearing discovery, transcription, analysis, and entity extraction
        are implemented in later phases)

        Args:
            year: Optional year filter for docket sync
            on_progress: Progress callback

        Returns:
            PipelineRun with results
        """
        import uuid

        run = PipelineRun(
            run_id=str(uuid.uuid4())[:8],
            started_at=datetime.utcnow(),
        )

        logger.info(f"Starting Florida pipeline run {run.run_id}")

        try:
            # Stage 1: Docket Sync
            if on_progress:
                on_progress("Stage 1/2: Syncing dockets from ClerkOffice API...")

            docket_result = self.docket_sync.sync_all(
                year=year,
                on_progress=on_progress
            )
            run.stages_run.append(PipelineStage.DOCKET_SYNC.value)
            run.results['docket_sync'] = {
                'total_scraped': docket_result.total_scraped,
                'new': docket_result.new_dockets,
                'updated': docket_result.updated_dockets,
                'duration': docket_result.duration_seconds,
            }
            if docket_result.errors:
                run.errors.extend([f"docket_sync: {e}" for e in docket_result.errors])

            # Stage 2: Document Sync (recent orders)
            if on_progress:
                on_progress("Stage 2/2: Indexing recent documents...")

            doc_result = self.document_sync.index_recent_orders(
                limit=100,
                on_progress=on_progress
            )
            run.stages_run.append(PipelineStage.DOCUMENT_SYNC.value)
            run.results['document_sync'] = {
                'total_indexed': doc_result.total_indexed,
                'new': doc_result.new_documents,
                'updated': doc_result.updated_documents,
                'duration': doc_result.duration_seconds,
            }
            if doc_result.errors:
                run.errors.extend([f"document_sync: {e}" for e in doc_result.errors])

            run.success = len(run.errors) == 0

        except Exception as e:
            logger.exception(f"Pipeline run {run.run_id} failed: {e}")
            run.errors.append(f"pipeline: {e}")
            run.success = False

        run.completed_at = datetime.utcnow()

        total_duration = (run.completed_at - run.started_at).total_seconds()
        logger.info(
            f"Pipeline run {run.run_id} {'succeeded' if run.success else 'failed'} "
            f"in {total_duration:.1f}s"
        )

        return run

    def run_docket_sync(
        self,
        year: Optional[int] = None,
        status: Optional[str] = None,
        on_progress: Optional[callable] = None
    ) -> DocketSyncResult:
        """Run just the docket sync stage."""
        return self.docket_sync.sync_all(
            year=year,
            status=status,
            on_progress=on_progress
        )

    def run_document_sync(
        self,
        mode: str = 'orders',
        query: Optional[str] = None,
        docket: Optional[str] = None,
        limit: int = 100,
        on_progress: Optional[callable] = None
    ) -> DocumentSyncResult:
        """
        Run just the document sync stage.

        Args:
            mode: 'orders' (recent orders), 'search' (query search), 'docket' (by docket)
            query: Search query (for mode='search')
            docket: Docket number (for mode='docket')
            limit: Max documents
            on_progress: Progress callback
        """
        if mode == 'orders':
            return self.document_sync.index_recent_orders(
                limit=limit,
                on_progress=on_progress
            )
        elif mode == 'search' and query:
            return self.document_sync.search_and_index(
                query=query,
                limit=limit,
                on_progress=on_progress
            )
        elif mode == 'docket' and docket:
            return self.document_sync.index_docket_documents(
                docket_number=docket,
                limit=limit
            )
        else:
            raise ValueError(f"Invalid mode '{mode}' or missing required argument")

    def get_pipeline_status(self) -> Dict[str, Any]:
        """Get current pipeline status and statistics."""
        docket_stats = self.docket_sync.get_sync_stats()
        document_stats = self.document_sync.get_document_stats()

        return {
            'dockets': docket_stats,
            'documents': document_stats,
            'stages_available': [s.value for s in PipelineStage],
            'stages_implemented': [
                PipelineStage.DOCKET_SYNC.value,
                PipelineStage.DOCUMENT_SYNC.value,
            ],
        }

    def validate_database(self) -> Dict[str, Any]:
        """Validate database connectivity and schema."""
        from florida.models import FLDocket, FLDocument, FLHearing

        issues = []
        checks = {}

        try:
            # Check dockets table
            count = self.db.query(FLDocket).limit(1).count()
            checks['fl_dockets'] = 'ok'
        except Exception as e:
            checks['fl_dockets'] = f'error: {e}'
            issues.append(f"fl_dockets: {e}")

        try:
            # Check documents table
            count = self.db.query(FLDocument).limit(1).count()
            checks['fl_documents'] = 'ok'
        except Exception as e:
            checks['fl_documents'] = f'error: {e}'
            issues.append(f"fl_documents: {e}")

        try:
            # Check hearings table
            count = self.db.query(FLHearing).limit(1).count()
            checks['fl_hearings'] = 'ok'
        except Exception as e:
            checks['fl_hearings'] = f'error: {e}'
            issues.append(f"fl_hearings: {e}")

        return {
            'valid': len(issues) == 0,
            'checks': checks,
            'issues': issues,
        }
