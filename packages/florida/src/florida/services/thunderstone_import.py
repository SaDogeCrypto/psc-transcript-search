"""
Thunderstone bulk import service.

Imports document metadata from Florida PSC Thunderstone API
and creates/enriches docket records.
"""

import logging
import re
import time
from datetime import datetime, date
from typing import Optional, Dict, Set, Tuple
from dataclasses import dataclass

from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import insert

from florida.models import SessionLocal, FLDocument, FLDocket
from florida.scrapers.thunderstone import FloridaThunderstoneScraper, ThunderstoneDocument

logger = logging.getLogger(__name__)

# Sector code descriptions
SECTOR_CODES = {
    'EI': ('Electric', 'Electric utility'),
    'EU': ('Electric', 'Electric utility'),
    'EM': ('Electric', 'Electric merger/acquisition'),
    'EC': ('Electric', 'Electric certificate'),
    'EQ': ('Electric', 'Electric CPCN'),
    'GU': ('Gas', 'Gas utility'),
    'GM': ('Gas', 'Gas merger/acquisition'),
    'WS': ('Water/Sewer', 'Water and sewer utility'),
    'WU': ('Water/Sewer', 'Water utility'),
    'SU': ('Water/Sewer', 'Sewer utility'),
    'TL': ('Telecom', 'Telecommunications'),
    'TX': ('Telecom', 'Telecommunications'),
    'OT': ('Other', 'Other/miscellaneous'),
    'AA': ('Administrative', 'Administrative action'),
    'RP': ('Rulemaking', 'Rulemaking proceeding'),
    'RR': ('Rulemaking', 'Rulemaking'),
    'CI': ('Complaint', 'Consumer complaint/investigation'),
    'CU': ('Complaint', 'Consumer utility complaint'),
    'PU': ('Pipeline', 'Pipeline utility'),
    'FO': ('Fuel', 'Fuel and purchased power'),
    'OG': ('Oil/Gas', 'Oil and gas'),
}

# Common utility name patterns
UTILITY_PATTERNS = [
    (r'Florida Power\s*&?\s*Light|FPL', 'Florida Power & Light Company'),
    (r'Duke Energy Florida|Duke Energy|DEF', 'Duke Energy Florida'),
    (r'Tampa Electric|TECO', 'Tampa Electric Company'),
    (r'Gulf Power', 'Gulf Power Company'),
    (r'Florida Public Utilities|FPUC', 'Florida Public Utilities Company'),
    (r'JEA', 'JEA'),
    (r'Orlando Utilities|OUC', 'Orlando Utilities Commission'),
    (r'Gainesville Regional|GRU', 'Gainesville Regional Utilities'),
    (r'Peoples Gas', 'Peoples Gas System'),
    (r'Florida City Gas|FCG', 'Florida City Gas'),
]


@dataclass
class ImportStats:
    """Track import statistics."""
    documents_processed: int = 0
    documents_inserted: int = 0
    documents_skipped: int = 0
    dockets_created: int = 0
    dockets_updated: int = 0
    errors: int = 0
    start_time: float = 0.0

    def __post_init__(self):
        self.start_time = time.time()

    @property
    def elapsed(self) -> float:
        return time.time() - self.start_time

    @property
    def rate(self) -> float:
        if self.elapsed > 0:
            return self.documents_processed / self.elapsed
        return 0.0

    def __str__(self) -> str:
        return (
            f"Processed: {self.documents_processed:,} | "
            f"Inserted: {self.documents_inserted:,} | "
            f"Skipped: {self.documents_skipped:,} | "
            f"Dockets: +{self.dockets_created:,}/~{self.dockets_updated:,} | "
            f"Errors: {self.errors} | "
            f"Rate: {self.rate:.1f}/sec | "
            f"Time: {self.elapsed:.0f}s"
        )


class ThunderstoneImporter:
    """Import documents from Thunderstone API."""

    # Docket number pattern: YYYYNNNN-XX (e.g., 20240001-EI)
    # Must include sector suffix to be a valid docket
    DOCKET_PATTERN = re.compile(r'\b((?:19|20)\d{2})(\d{4})-([A-Z]{2})\b')

    # NOTE: We intentionally do NOT extract docket numbers from order patterns.
    # Orders (PSC-YYYY-NNNN-XXX-YY) reference dockets but should not CREATE docket records.
    # The order number is NOT a docket number - they have different sequences.

    # URL filing pattern: /NNNNN-YYYY/ or /NNNNN-YYYY.pdf (filing numbers, not dockets)
    URL_FILING_PATTERN = re.compile(r'/(\d{5})-(\d{4})[./]')

    def __init__(self):
        self.scraper = FloridaThunderstoneScraper()
        self.stats = ImportStats()
        self._existing_thunderstone_ids: Set[str] = set()
        self._existing_dockets: Dict[str, int] = {}  # docket_number -> id

    def _load_existing_data(self, session: Session):
        """Load existing thunderstone IDs and dockets for deduplication."""
        logger.info("Loading existing data for deduplication...")

        # Load existing thunderstone IDs
        existing_docs = session.query(FLDocument.thunderstone_id).filter(
            FLDocument.thunderstone_id.isnot(None)
        ).all()
        self._existing_thunderstone_ids = {d[0] for d in existing_docs}
        logger.info(f"Found {len(self._existing_thunderstone_ids):,} existing documents")

        # Load existing dockets
        existing_dockets = session.query(FLDocket.docket_number, FLDocket.id).all()
        self._existing_dockets = {d[0]: d[1] for d in existing_dockets}
        logger.info(f"Found {len(self._existing_dockets):,} existing dockets")

    def _extract_docket_info(self, text: str) -> Optional[Tuple[str, int, int, str]]:
        """
        Extract docket number components from text.

        Returns: (docket_number, year, sequence, sector_code) or None
        Note: docket_number includes sector suffix (e.g., '20250005-EI')
        """
        # Match standard docket pattern: YYYYNNNN-XX (e.g., 20240001-EI)
        # The hyphen and sector code are REQUIRED - this distinguishes dockets from orders
        match = self.DOCKET_PATTERN.search(text)
        if match:
            year = int(match.group(1))
            sequence = int(match.group(2))
            sector_code = match.group(3)
            # Include sector suffix in docket_number for proper format
            docket_number = f"{year}{match.group(2)}-{sector_code}"
            return (docket_number, year, sequence, sector_code)

        # NOTE: We do NOT extract from order numbers (PSC-YYYY-NNNN-XXX-YY).
        # Order sequences are different from docket sequences.
        # Orders should reference existing dockets, not create new ones.

        return None

    def _extract_utility_name(self, text: str) -> Optional[str]:
        """Extract standardized utility name from text."""
        if not text:
            return None
        for pattern, name in UTILITY_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                return name
        return None

    def _get_or_create_docket(
        self,
        session: Session,
        docket_number: str,
        year: int,
        sequence: int,
        sector_code: str,
        doc: ThunderstoneDocument
    ) -> Optional[int]:
        """Get existing docket ID or create new docket."""

        # Check if we already know this docket
        if docket_number in self._existing_dockets:
            return self._existing_dockets[docket_number]

        # Get sector info
        industry_type, case_type = SECTOR_CODES.get(sector_code, ('Unknown', 'Unknown'))

        # Extract utility name from document
        utility_name = (
            self._extract_utility_name(doc.filer_name or '') or
            self._extract_utility_name(doc.title or '') or
            self._extract_utility_name(doc.content_excerpt or '')
        )

        # Build title from document info
        title = None
        if doc.title and len(doc.title) > 20:
            # Clean up title
            title = doc.title.strip()
            # Remove common prefixes
            for prefix in ['ORDER NO.', 'BEFORE THE', 'Microsoft Word -', 'IN RE:']:
                if title.upper().startswith(prefix):
                    title = title[len(prefix):].strip()
            # Truncate if too long
            if len(title) > 200:
                title = title[:200] + '...'

        # Create new docket
        try:
            new_docket = FLDocket(
                docket_number=docket_number,
                year=year,
                sequence=sequence,
                sector_code=sector_code,
                title=title,
                utility_name=utility_name,
                industry_type=industry_type,
                case_type=case_type,
                filed_date=doc.filed_date,
                psc_docket_url=f"https://www.floridapsc.com/ClerkOffice/DocketFiling?docket={docket_number}",
                created_at=datetime.utcnow(),
            )
            session.add(new_docket)
            session.flush()  # Get the ID

            self._existing_dockets[docket_number] = new_docket.id
            self.stats.dockets_created += 1

            logger.debug(f"Created docket: {docket_number} - {utility_name or 'Unknown'}")
            return new_docket.id

        except Exception as e:
            logger.warning(f"Failed to create docket {docket_number}: {e}")
            return None

    def _import_document(self, session: Session, doc: ThunderstoneDocument) -> bool:
        """Import a single document. Returns True if inserted."""

        # Skip if already exists
        if doc.thunderstone_id and doc.thunderstone_id in self._existing_thunderstone_ids:
            self.stats.documents_skipped += 1
            return False

        # Extract docket info
        docket_number = None
        docket_info = (
            self._extract_docket_info(doc.title or '') or
            self._extract_docket_info(doc.content_excerpt or '') or
            self._extract_docket_info(doc.file_url or '')
        )

        if docket_info:
            docket_number, year, sequence, sector_code = docket_info
            self._get_or_create_docket(session, docket_number, year, sequence, sector_code, doc)

        # Create document record
        try:
            new_doc = FLDocument(
                thunderstone_id=doc.thunderstone_id,
                title=doc.title or 'Untitled',
                document_type=doc.document_type,
                profile=doc.profile,
                docket_number=docket_number,
                file_url=doc.file_url,
                file_type=doc.file_type,
                file_size_bytes=doc.file_size_bytes,
                filed_date=doc.filed_date,
                content_text=doc.content_excerpt,
                filer_name=doc.filer_name,
                document_number=doc.document_number,
                created_at=datetime.utcnow(),
                scraped_at=datetime.utcnow(),
            )
            session.add(new_doc)

            if doc.thunderstone_id:
                self._existing_thunderstone_ids.add(doc.thunderstone_id)

            self.stats.documents_inserted += 1
            return True

        except Exception as e:
            logger.warning(f"Failed to insert document: {e}")
            self.stats.errors += 1
            return False

    def import_profile(
        self,
        profile: str,
        search_term: str = "Florida",
        limit: Optional[int] = None,
        commit_every: int = 100,
    ) -> ImportStats:
        """
        Import all documents from a Thunderstone profile.

        Args:
            profile: Search profile (library, orders, filings, etc.)
            search_term: Search query to use
            limit: Maximum documents to import (None for all)
            commit_every: Commit transaction every N documents
        """
        logger.info(f"Starting import: profile={profile}, search='{search_term}', limit={limit}")

        with SessionLocal() as session:
            self._load_existing_data(session)

            batch_count = 0
            for doc in self.scraper.search(query=search_term, profile=profile, limit=limit or 999999):
                self.stats.documents_processed += 1
                self._import_document(session, doc)
                batch_count += 1

                # Periodic commit
                if batch_count >= commit_every:
                    session.commit()
                    batch_count = 0
                    logger.info(f"Progress: {self.stats}")

                # Check limit
                if limit and self.stats.documents_processed >= limit:
                    break

            # Final commit
            session.commit()

        logger.info(f"Import complete: {self.stats}")
        return self.stats

    def import_all_profiles(
        self,
        search_term: str = "Florida",
        limit_per_profile: Optional[int] = None,
        profiles: Optional[list] = None,
    ) -> ImportStats:
        """
        Import from all Thunderstone profiles.

        Args:
            search_term: Search query to use
            limit_per_profile: Max docs per profile (None for all)
            profiles: List of profiles to import (None for default set)
        """
        if profiles is None:
            profiles = ['library', 'orders', 'filings', 'filingsCurrent', 'financials', 'tariffs']

        logger.info(f"Starting multi-profile import: {profiles}")

        with SessionLocal() as session:
            self._load_existing_data(session)

        for profile in profiles:
            logger.info(f"\n{'='*50}\nImporting profile: {profile}\n{'='*50}")

            try:
                with SessionLocal() as session:
                    # Reload for each profile in case of long runs
                    self._load_existing_data(session)

                    batch_count = 0
                    profile_count = 0

                    for doc in self.scraper.search(
                        query=search_term,
                        profile=profile,
                        limit=limit_per_profile or 999999
                    ):
                        self.stats.documents_processed += 1
                        profile_count += 1
                        self._import_document(session, doc)
                        batch_count += 1

                        if batch_count >= 100:
                            session.commit()
                            batch_count = 0
                            logger.info(f"[{profile}] {self.stats}")

                        if limit_per_profile and profile_count >= limit_per_profile:
                            break

                    session.commit()

            except Exception as e:
                logger.error(f"Error importing profile {profile}: {e}")
                self.stats.errors += 1

        logger.info(f"\nFinal stats: {self.stats}")
        return self.stats


def run_import(
    profiles: Optional[list] = None,
    search_term: str = "Florida",
    limit: Optional[int] = None,
):
    """
    Run Thunderstone import.

    Args:
        profiles: List of profiles to import, or None for all
        search_term: Search term to use
        limit: Max documents per profile
    """
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )

    importer = ThunderstoneImporter()
    return importer.import_all_profiles(
        search_term=search_term,
        limit_per_profile=limit,
        profiles=profiles,
    )


def run_comprehensive_import(
    profiles: Optional[list] = None,
):
    """
    Run comprehensive import using multiple search strategies.

    The Thunderstone API only returns ~100 results per search,
    so we use multiple search terms to maximize coverage.
    """
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )

    importer = ThunderstoneImporter()

    if profiles is None:
        profiles = ['orders', 'library', 'filings', 'filingsCurrent']

    # Search terms to maximize coverage
    search_terms = []

    # Order number range searches: PSC-YYYY-NN for years 1990-2026
    # Each range covers ~100 orders (e.g., PSC-2025-00 covers 0001-0099)
    for year in range(1990, 2027):
        # 2-digit year format for older orders (pre-2000)
        if year < 2000:
            yr = str(year)[2:]  # e.g., 1995 -> "95"
            for prefix in range(25):  # 00-24 should cover most years
                search_terms.append(f"PSC-{yr}-{prefix:02d}")
        else:
            for prefix in range(25):  # 00-24 should cover most years
                search_terms.append(f"PSC-{year}-{prefix:02d}")

    # Add year searches as backup
    search_terms.extend([str(year) for year in range(1990, 2027)])

    # Utilities
    search_terms.extend([
        "Florida Power Light", "FPL", "Duke Energy", "Tampa Electric", "TECO",
        "Gulf Power", "JEA", "FPUC", "Peoples Gas", "Florida City Gas",
    ])

    # Document types and common terms
    search_terms.extend([
        "ORDER", "testimony", "petition", "motion", "tariff", "rate case",
        "EI", "WS", "GU", "TL", "EM", "EC",
        "Commission", "Docket", "hearing", "application", "certificate",
    ])

    with SessionLocal() as session:
        importer._load_existing_data(session)

    logger.info(f"Starting comprehensive import with {len(search_terms)} search terms")
    logger.info(f"Profiles: {profiles}")

    for profile in profiles:
        logger.info(f"\n{'='*60}\nProcessing profile: {profile}\n{'='*60}")

        for search_term in search_terms:
            try:
                with SessionLocal() as session:
                    batch_count = 0
                    term_inserted = 0

                    for doc in importer.scraper.search(
                        query=search_term,
                        profile=profile,
                        limit=100  # API limit
                    ):
                        importer.stats.documents_processed += 1
                        if importer._import_document(session, doc):
                            term_inserted += 1
                        batch_count += 1

                        if batch_count >= 100:
                            session.commit()
                            batch_count = 0

                    session.commit()

                    if term_inserted > 0:
                        logger.info(f"[{profile}] '{search_term}': +{term_inserted} docs | Total: {importer.stats}")

            except Exception as e:
                logger.error(f"Error with search '{search_term}': {e}")

    logger.info(f"\n{'='*60}\nFinal stats: {importer.stats}\n{'='*60}")
    return importer.stats


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='Import Thunderstone documents')
    parser.add_argument('--profiles', nargs='+', help='Profiles to import')
    parser.add_argument('--search', default='Florida', help='Search term')
    parser.add_argument('--limit', type=int, help='Max docs per profile')

    args = parser.parse_args()

    run_import(
        profiles=args.profiles,
        search_term=args.search,
        limit=args.limit,
    )
