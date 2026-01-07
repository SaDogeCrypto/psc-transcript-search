"""
Docket Discovery Stage

Scrapes PSC websites for authoritative docket data.
Runs before hearing discovery to populate known_dockets table.

Unlike other stages that process hearings, this processes docket_sources.
"""

import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.models.database import DocketSource, KnownDocket
from app.scrapers.docket_scrapers import get_scraper, is_scraper_available
from app.services.docket_parser import parse_docket

logger = logging.getLogger(__name__)


@dataclass
class DiscoveryResult:
    """Result of docket discovery for a single source."""
    state_code: str
    scraped: int = 0
    new: int = 0
    updated: int = 0
    error: Optional[str] = None


class DocketDiscoveryStage:
    """
    Scrape PSC websites for known dockets.

    Unlike other stages that process hearings, this processes docket_sources.
    It populates the known_dockets table with authoritative data from PSC websites.
    """

    name = "docket_discovery"

    def __init__(self, db: Session):
        self.db = db

    def get_pending_count(self) -> int:
        """Get number of sources due for scraping."""
        try:
            # Check for sources that haven't been scraped recently
            result = self.db.execute(text("""
                SELECT COUNT(*) FROM docket_sources
                WHERE enabled = TRUE
                AND scraper_type IS NOT NULL
                AND (
                    last_scraped_at IS NULL
                    OR last_scraped_at < datetime('now', '-7 days')
                )
            """))
            return result.scalar() or 0
        except Exception:
            # Fallback for different SQL dialects
            sources = self.db.query(DocketSource).filter(
                DocketSource.enabled == True,
                DocketSource.scraper_type.isnot(None)
            ).all()

            cutoff = datetime.utcnow() - timedelta(days=7)
            return sum(
                1 for s in sources
                if s.last_scraped_at is None or s.last_scraped_at < cutoff
            )

    def get_sources_to_scrape(self, states: List[str] = None) -> List[DocketSource]:
        """Get docket sources that need scraping."""
        query = self.db.query(DocketSource).filter(
            DocketSource.enabled == True,
            DocketSource.scraper_type.isnot(None)
        )

        if states:
            states_upper = [s.upper() for s in states]
            query = query.filter(DocketSource.state_code.in_(states_upper))

        # Filter by scrape frequency
        cutoff = datetime.utcnow() - timedelta(hours=168)  # Weekly default
        sources = query.all()

        return [
            s for s in sources
            if s.last_scraped_at is None or s.last_scraped_at < cutoff
        ]

    def run(
        self,
        states: List[str] = None,
        year: int = None,
        limit_per_state: int = 1000,
        on_progress: callable = None
    ) -> Dict[str, Any]:
        """
        Run docket discovery for all enabled sources.

        Args:
            states: Optional list of state codes to scrape
            year: Optional year filter
            limit_per_state: Max dockets to scrape per state
            on_progress: Callback for progress updates (receives status message)

        Returns:
            Dict with stats: {total_scraped, by_state, errors}
        """
        sources = self.get_sources_to_scrape(states)

        results = {
            'total_scraped': 0,
            'total_new': 0,
            'total_updated': 0,
            'by_state': {},
            'errors': []
        }

        for source in sources:
            try:
                # Check if scraper is available
                if not is_scraper_available(source.state_code):
                    logger.info(f"No scraper available for {source.state_code}")
                    continue

                if on_progress:
                    on_progress(f"Scanning {source.state_code} dockets...")

                scraper = get_scraper(source.state_code)
                state_count = 0
                state_new = 0
                state_updated = 0
                seen_in_batch = set()  # Track dockets seen in this batch to avoid duplicates

                for docket_data in scraper.scrape_docket_list(
                    year=year,
                    limit=limit_per_state
                ):
                    # Skip duplicates within this batch (API can return same docket multiple times)
                    docket_key = (source.state_code, docket_data.docket_number)
                    if docket_key in seen_in_batch:
                        continue
                    seen_in_batch.add(docket_key)

                    # Parse docket number
                    parsed = parse_docket(
                        docket_data.docket_number,
                        source.state_code
                    )

                    # Upsert into known_dockets (use state_code + docket_number for uniqueness)
                    existing = self.db.query(KnownDocket).filter(
                        KnownDocket.state_code == source.state_code,
                        KnownDocket.docket_number == docket_data.docket_number
                    ).first()

                    if existing:
                        # Update existing
                        existing.title = docket_data.title or existing.title
                        existing.utility_name = docket_data.utility_name or existing.utility_name
                        existing.status = docket_data.status or existing.status
                        existing.case_type = docket_data.case_type or existing.case_type
                        existing.source_url = docket_data.source_url or existing.source_url
                        existing.updated_at = datetime.utcnow()
                        state_updated += 1
                    else:
                        # Insert new
                        # Use full docket number in normalized_id to avoid collisions
                        # (e.g., FL dockets 20000121A and 20000121C have different suffixes)
                        full_normalized_id = f"{source.state_code}-{docket_data.docket_number}"
                        known = KnownDocket(
                            state_code=source.state_code,
                            docket_number=docket_data.docket_number,
                            normalized_id=full_normalized_id,
                            year=parsed.year,
                            case_number=parsed.case_number,
                            suffix=parsed.suffix,
                            sector=parsed.utility_sector,
                            title=docket_data.title,
                            utility_name=docket_data.utility_name,
                            filing_date=datetime.strptime(docket_data.filing_date, '%Y-%m-%d').date() if docket_data.filing_date else None,
                            status=docket_data.status,
                            case_type=docket_data.case_type,
                            source_url=docket_data.source_url,
                        )
                        self.db.add(known)
                        state_new += 1

                    state_count += 1

                # Update source tracking
                source.last_scraped_at = datetime.utcnow()
                source.last_scrape_count = state_count
                source.last_error = None

                self.db.commit()

                results['by_state'][source.state_code] = {
                    'scraped': state_count,
                    'new': state_new,
                    'updated': state_updated
                }
                results['total_scraped'] += state_count
                results['total_new'] += state_new
                results['total_updated'] += state_updated

                logger.info(f"Scraped {state_count} dockets from {source.state_code} ({state_new} new)")

            except Exception as e:
                self.db.rollback()  # Clear any pending failed transactions
                logger.exception(f"Error scraping {source.state_code}: {e}")
                source = self.db.query(DocketSource).filter(
                    DocketSource.state_code == source.state_code
                ).first()  # Re-fetch after rollback
                if source:
                    source.last_error = str(e)[:500]
                    self.db.commit()
                results['errors'].append({
                    'state': source.state_code,
                    'error': str(e)
                })

        return results
