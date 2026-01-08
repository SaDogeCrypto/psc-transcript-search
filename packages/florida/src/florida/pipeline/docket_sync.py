"""
Florida Docket Sync Stage.

Syncs dockets from the Florida PSC ClerkOffice API to the FL_DOCKETS table.
This runs periodically to keep the local database in sync with the official records.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from dataclasses import dataclass

from sqlalchemy.orm import Session

from core.pipeline.base import StageResult
from florida.config import get_config, FloridaConfig
from florida.scrapers.clerkoffice import FloridaClerkOfficeScraper, FloridaDocketData
from florida.models.docket import FLDocket

logger = logging.getLogger(__name__)


@dataclass
class DocketSyncResult:
    """Result of docket sync operation."""
    total_scraped: int = 0
    new_dockets: int = 0
    updated_dockets: int = 0
    errors: List[str] = None
    duration_seconds: float = 0.0

    def __post_init__(self):
        if self.errors is None:
            self.errors = []


class DocketSyncStage:
    """
    Sync dockets from Florida PSC ClerkOffice API.

    This stage:
    1. Fetches dockets from the ClerkOffice API
    2. Upserts them into the FL_DOCKETS table
    3. Preserves any locally-enriched data (commissioner assignments, etc.)

    Can be run in several modes:
    - Full sync: All dockets across all industries
    - Year sync: Dockets from a specific year
    - Open only: Only currently open dockets
    - Incremental: Recently opened/closed dockets
    """

    name = "docket_sync"

    def __init__(
        self,
        db: Session,
        config: Optional[FloridaConfig] = None,
        scraper: Optional[FloridaClerkOfficeScraper] = None
    ):
        self.db = db
        self.config = config or get_config()
        self.scraper = scraper or FloridaClerkOfficeScraper(self.config)

    def _upsert_docket(self, data: FloridaDocketData) -> bool:
        """
        Upsert a docket into the database.

        Returns True if inserted (new), False if updated (existing).
        """
        existing = self.db.query(FLDocket).filter(
            FLDocket.docket_number == data.docket_number
        ).first()

        if existing:
            # Update existing docket (preserve locally-enriched fields)
            existing.title = data.title or existing.title
            existing.utility_name = data.utility_name or existing.utility_name
            existing.status = data.status or existing.status
            existing.case_type = data.case_type or existing.case_type
            existing.industry_type = data.industry_type or existing.industry_type
            existing.filed_date = data.filed_date or existing.filed_date
            existing.closed_date = data.closed_date or existing.closed_date
            existing.psc_docket_url = data.psc_docket_url or existing.psc_docket_url
            existing.updated_at = datetime.utcnow()
            return False
        else:
            # Insert new docket
            docket = FLDocket(
                docket_number=data.docket_number,
                year=data.year,
                sequence=data.sequence,
                sector_code=data.sector_code,
                title=data.title,
                utility_name=data.utility_name,
                status=data.status,
                case_type=data.case_type,
                industry_type=data.industry_type,
                filed_date=data.filed_date,
                closed_date=data.closed_date,
                psc_docket_url=data.psc_docket_url,
            )
            self.db.add(docket)
            return True

    def sync_all(
        self,
        year: Optional[int] = None,
        status: Optional[str] = None,
        industries: Optional[List[str]] = None,
        limit: int = 10000,
        on_progress: Optional[callable] = None
    ) -> DocketSyncResult:
        """
        Sync all dockets matching the criteria.

        Args:
            year: Filter by year (None for all years)
            status: 'open', 'closed', or None for all
            industries: List of industry codes ['E', 'G', 'T', 'W', 'X']
            limit: Maximum dockets to sync
            on_progress: Callback for progress updates

        Returns:
            DocketSyncResult with stats
        """
        import time
        start_time = time.time()

        result = DocketSyncResult()
        seen_dockets = set()

        try:
            if on_progress:
                on_progress("Starting Florida docket sync...")

            for docket_data in self.scraper.scrape_florida_dockets(
                year=year,
                status=status,
                industries=industries,
                limit=limit
            ):
                # Skip duplicates
                if docket_data.docket_number in seen_dockets:
                    continue
                seen_dockets.add(docket_data.docket_number)

                try:
                    is_new = self._upsert_docket(docket_data)
                    if is_new:
                        result.new_dockets += 1
                    else:
                        result.updated_dockets += 1
                    result.total_scraped += 1

                    # Commit in batches
                    if result.total_scraped % 100 == 0:
                        self.db.commit()
                        if on_progress:
                            on_progress(f"Synced {result.total_scraped} dockets...")

                except Exception as e:
                    logger.warning(f"Error upserting docket {docket_data.docket_number}: {e}")
                    result.errors.append(str(e))
                    self.db.rollback()

            # Final commit
            self.db.commit()

        except Exception as e:
            logger.exception(f"Error during docket sync: {e}")
            result.errors.append(str(e))
            self.db.rollback()

        result.duration_seconds = time.time() - start_time

        logger.info(
            f"Docket sync complete: {result.total_scraped} scraped, "
            f"{result.new_dockets} new, {result.updated_dockets} updated "
            f"in {result.duration_seconds:.1f}s"
        )

        return result

    def sync_open_dockets(
        self,
        on_progress: Optional[callable] = None
    ) -> DocketSyncResult:
        """Sync only currently open dockets."""
        return self.sync_all(status='open', on_progress=on_progress)

    def sync_recent(
        self,
        on_progress: Optional[callable] = None
    ) -> DocketSyncResult:
        """Sync recently opened/closed dockets (last 30 days activity)."""
        # The API's 'O' and 'C' types cover recent activity
        return self.sync_all(limit=500, on_progress=on_progress)

    def sync_year(
        self,
        year: int,
        on_progress: Optional[callable] = None
    ) -> DocketSyncResult:
        """Sync all dockets from a specific year."""
        return self.sync_all(year=year, on_progress=on_progress)

    def get_sync_stats(self) -> Dict[str, Any]:
        """Get statistics about synced dockets."""
        from sqlalchemy import func

        total = self.db.query(func.count(FLDocket.id)).scalar() or 0
        open_count = self.db.query(func.count(FLDocket.id)).filter(
            FLDocket.status == 'open'
        ).scalar() or 0
        closed_count = self.db.query(func.count(FLDocket.id)).filter(
            FLDocket.status == 'closed'
        ).scalar() or 0

        # Get counts by sector
        by_sector = {}
        sector_counts = self.db.query(
            FLDocket.sector_code,
            func.count(FLDocket.id)
        ).group_by(FLDocket.sector_code).all()

        for sector, count in sector_counts:
            if sector:
                by_sector[sector] = count

        # Get year range
        year_range = self.db.query(
            func.min(FLDocket.year),
            func.max(FLDocket.year)
        ).first()

        return {
            'total': total,
            'open': open_count,
            'closed': closed_count,
            'by_sector': by_sector,
            'year_range': {
                'min': year_range[0] if year_range else None,
                'max': year_range[1] if year_range else None,
            }
        }

    def execute(self, item: Any = None, db: Session = None) -> StageResult:
        """Execute the stage (implements BaseStage interface)."""
        try:
            result = self.sync_recent()
            return StageResult(
                success=len(result.errors) == 0,
                output={
                    'total_scraped': result.total_scraped,
                    'new_dockets': result.new_dockets,
                    'updated_dockets': result.updated_dockets,
                },
                error='; '.join(result.errors) if result.errors else None,
            )
        except Exception as e:
            return StageResult(
                success=False,
                error=str(e),
            )
