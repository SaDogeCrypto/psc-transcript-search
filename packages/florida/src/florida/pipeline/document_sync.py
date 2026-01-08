"""
Florida Document Sync Stage.

Indexes documents from the Florida PSC Thunderstone search API to the FL_DOCUMENTS table.
This discovers and catalogs PSC documents associated with dockets.
"""

import logging
from datetime import datetime, date
from typing import Optional, Dict, Any, List
from dataclasses import dataclass

from sqlalchemy.orm import Session

from core.pipeline.base import StageResult
from florida.config import get_config, FloridaConfig
from florida.scrapers.thunderstone import FloridaThunderstoneScraper, ThunderstoneDocument
from florida.models.document import FLDocument
from florida.models.docket import FLDocket

logger = logging.getLogger(__name__)


@dataclass
class DocumentSyncResult:
    """Result of document sync operation."""
    total_indexed: int = 0
    new_documents: int = 0
    updated_documents: int = 0
    dockets_processed: int = 0
    errors: List[str] = None
    duration_seconds: float = 0.0

    def __post_init__(self):
        if self.errors is None:
            self.errors = []


class DocumentSyncStage:
    """
    Index documents from Florida PSC Thunderstone search.

    This stage:
    1. Searches for documents associated with known dockets
    2. Indexes document metadata into FL_DOCUMENTS table
    3. Links documents to their parent dockets

    Can be run in several modes:
    - By docket: Index all documents for a specific docket
    - By search: Index documents matching a search query
    - For recent orders: Index recent commission orders
    - Bulk: Index documents across all open dockets
    """

    name = "document_sync"

    def __init__(
        self,
        db: Session,
        config: Optional[FloridaConfig] = None,
        scraper: Optional[FloridaThunderstoneScraper] = None
    ):
        self.db = db
        self.config = config or get_config()
        self.scraper = scraper or FloridaThunderstoneScraper(self.config)

    def _upsert_document(self, doc: ThunderstoneDocument) -> bool:
        """
        Upsert a document into the database.

        Returns True if inserted (new), False if updated (existing).
        """
        # Check for existing by thunderstone_id or title+docket combination
        existing = None
        if doc.thunderstone_id:
            existing = self.db.query(FLDocument).filter(
                FLDocument.thunderstone_id == doc.thunderstone_id
            ).first()

        if not existing and doc.docket_number and doc.title:
            existing = self.db.query(FLDocument).filter(
                FLDocument.docket_number == doc.docket_number,
                FLDocument.title == doc.title
            ).first()

        # Validate docket_number exists if provided (skip FK if docket not in DB)
        validated_docket_number = None
        if doc.docket_number:
            docket_exists = self.db.query(FLDocket).filter(
                FLDocket.docket_number == doc.docket_number
            ).first()
            if docket_exists:
                validated_docket_number = doc.docket_number

        if existing:
            # Update existing document
            existing.document_type = doc.document_type or existing.document_type
            existing.profile = doc.profile or existing.profile
            existing.file_url = doc.file_url or existing.file_url
            existing.file_type = doc.file_type or existing.file_type
            existing.file_size_bytes = doc.file_size_bytes or existing.file_size_bytes
            existing.filed_date = doc.filed_date or existing.filed_date
            existing.filer_name = doc.filer_name or existing.filer_name
            existing.scraped_at = datetime.utcnow()
            # Only update docket_number if the docket exists
            if validated_docket_number:
                existing.docket_number = validated_docket_number
            return False
        else:
            # Insert new document
            document = FLDocument(
                thunderstone_id=doc.thunderstone_id,
                title=doc.title,
                document_type=doc.document_type,
                profile=doc.profile,
                docket_number=validated_docket_number,  # Only set if docket exists
                file_url=doc.file_url,
                file_type=doc.file_type,
                file_size_bytes=doc.file_size_bytes,
                filed_date=doc.filed_date,
                filer_name=doc.filer_name,
                document_number=doc.document_number,
                scraped_at=datetime.utcnow(),
            )
            self.db.add(document)
            return True

    def index_docket_documents(
        self,
        docket_number: str,
        profile: str = 'library',
        limit: int = 100,
    ) -> DocumentSyncResult:
        """
        Index all documents for a specific docket.

        Args:
            docket_number: The docket number to search for
            profile: Thunderstone profile to search
            limit: Maximum documents to index

        Returns:
            DocumentSyncResult with stats
        """
        import time
        start_time = time.time()
        result = DocumentSyncResult()

        try:
            for doc in self.scraper.search_by_docket(
                docket_number=docket_number,
                profile=profile,
                limit=limit
            ):
                try:
                    is_new = self._upsert_document(doc)
                    if is_new:
                        result.new_documents += 1
                    else:
                        result.updated_documents += 1
                    result.total_indexed += 1
                except Exception as e:
                    logger.warning(f"Error indexing document: {e}")
                    result.errors.append(str(e))

            result.dockets_processed = 1
            self.db.commit()

        except Exception as e:
            logger.exception(f"Error indexing docket {docket_number}: {e}")
            result.errors.append(str(e))
            self.db.rollback()

        result.duration_seconds = time.time() - start_time
        return result

    def search_and_index(
        self,
        query: str,
        profile: str = 'library',
        limit: int = 100,
        on_progress: Optional[callable] = None,
    ) -> DocumentSyncResult:
        """
        Search for documents and index results.

        Args:
            query: Search query
            profile: Thunderstone profile
            limit: Maximum documents to index
            on_progress: Progress callback

        Returns:
            DocumentSyncResult with stats
        """
        import time
        start_time = time.time()
        result = DocumentSyncResult()

        try:
            if on_progress:
                on_progress(f"Searching Thunderstone: '{query}'...")

            for doc in self.scraper.search(
                query=query,
                profile=profile,
                limit=limit
            ):
                try:
                    is_new = self._upsert_document(doc)
                    if is_new:
                        result.new_documents += 1
                    else:
                        result.updated_documents += 1
                    result.total_indexed += 1

                    if result.total_indexed % 50 == 0:
                        self.db.commit()
                        if on_progress:
                            on_progress(f"Indexed {result.total_indexed} documents...")

                except Exception as e:
                    logger.warning(f"Error indexing document: {e}")
                    result.errors.append(str(e))

            self.db.commit()

        except Exception as e:
            logger.exception(f"Error during search: {e}")
            result.errors.append(str(e))
            self.db.rollback()

        result.duration_seconds = time.time() - start_time
        return result

    def index_recent_orders(
        self,
        limit: int = 100,
        on_progress: Optional[callable] = None,
    ) -> DocumentSyncResult:
        """Index recent commission orders."""
        import time
        start_time = time.time()
        result = DocumentSyncResult()

        try:
            if on_progress:
                on_progress("Fetching recent orders...")

            for doc in self.scraper.get_orders(query='', limit=limit):
                try:
                    is_new = self._upsert_document(doc)
                    if is_new:
                        result.new_documents += 1
                    else:
                        result.updated_documents += 1
                    result.total_indexed += 1
                except Exception as e:
                    logger.warning(f"Error indexing order: {e}")
                    result.errors.append(str(e))

            self.db.commit()

        except Exception as e:
            logger.exception(f"Error fetching orders: {e}")
            result.errors.append(str(e))
            self.db.rollback()

        result.duration_seconds = time.time() - start_time
        return result

    def index_open_dockets(
        self,
        docs_per_docket: int = 50,
        max_dockets: int = 100,
        on_progress: Optional[callable] = None,
    ) -> DocumentSyncResult:
        """
        Index documents for all open dockets.

        Args:
            docs_per_docket: Max documents per docket
            max_dockets: Max dockets to process
            on_progress: Progress callback

        Returns:
            DocumentSyncResult with aggregated stats
        """
        import time
        start_time = time.time()
        result = DocumentSyncResult()

        try:
            # Get open dockets
            open_dockets = self.db.query(FLDocket).filter(
                FLDocket.status == 'open'
            ).limit(max_dockets).all()

            for i, docket in enumerate(open_dockets):
                if on_progress:
                    on_progress(f"Indexing docket {i+1}/{len(open_dockets)}: {docket.docket_number}...")

                try:
                    docket_result = self.index_docket_documents(
                        docket_number=docket.docket_number,
                        limit=docs_per_docket
                    )
                    result.total_indexed += docket_result.total_indexed
                    result.new_documents += docket_result.new_documents
                    result.updated_documents += docket_result.updated_documents
                    result.dockets_processed += 1
                    result.errors.extend(docket_result.errors)
                except Exception as e:
                    logger.warning(f"Error indexing docket {docket.docket_number}: {e}")
                    result.errors.append(f"{docket.docket_number}: {e}")

        except Exception as e:
            logger.exception(f"Error during bulk indexing: {e}")
            result.errors.append(str(e))

        result.duration_seconds = time.time() - start_time

        logger.info(
            f"Document sync complete: {result.total_indexed} indexed across "
            f"{result.dockets_processed} dockets in {result.duration_seconds:.1f}s"
        )

        return result

    def get_document_stats(self) -> Dict[str, Any]:
        """Get statistics about indexed documents."""
        from sqlalchemy import func

        total = self.db.query(func.count(FLDocument.id)).scalar() or 0

        # By document type
        by_type = {}
        type_counts = self.db.query(
            FLDocument.document_type,
            func.count(FLDocument.id)
        ).group_by(FLDocument.document_type).all()

        for doc_type, count in type_counts:
            if doc_type:
                by_type[doc_type] = count

        # By profile
        by_profile = {}
        profile_counts = self.db.query(
            FLDocument.profile,
            func.count(FLDocument.id)
        ).group_by(FLDocument.profile).all()

        for profile, count in profile_counts:
            if profile:
                by_profile[profile] = count

        # Documents with dockets vs orphaned
        with_docket = self.db.query(func.count(FLDocument.id)).filter(
            FLDocument.docket_number.isnot(None)
        ).scalar() or 0

        return {
            'total': total,
            'with_docket': with_docket,
            'orphaned': total - with_docket,
            'by_type': by_type,
            'by_profile': by_profile,
        }

    def execute(self, item: Any = None, db: Session = None) -> StageResult:
        """Execute the stage (implements BaseStage interface)."""
        try:
            result = self.index_recent_orders(limit=50)
            return StageResult(
                success=len(result.errors) == 0,
                output={
                    'total_indexed': result.total_indexed,
                    'new_documents': result.new_documents,
                    'updated_documents': result.updated_documents,
                },
                error='; '.join(result.errors) if result.errors else None,
            )
        except Exception as e:
            return StageResult(
                success=False,
                error=str(e),
            )
