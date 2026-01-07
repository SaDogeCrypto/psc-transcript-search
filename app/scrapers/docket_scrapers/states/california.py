"""
California Public Utilities Commission (CPUC) Docket Scraper

CPUC Website: https://www.cpuc.ca.gov
Document Search: https://docs.cpuc.ca.gov/SearchRes.aspx
Proceedings: https://apps.cpuc.ca.gov/apex/f?p=401:1

California proceeding number formats:
- Compact: A2507003 (Application, 2025, July, case 003)
- Display: A.25-07-003

Prefix types:
- A = Application
- R = Rulemaking
- C = Complaint
- I = Investigation
- P = Petition
"""

from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from typing import Iterator, Optional, Set
import time
import logging
import re

from ..base import BaseDocketScraper, DocketRecord

logger = logging.getLogger(__name__)


class CaliforniaDocketScraper(BaseDocketScraper):
    """
    Scraper for California PUC docket data.

    Uses docs.cpuc.ca.gov to find proceeding numbers from document listings.
    """

    state_code = 'CA'
    state_name = 'California'
    base_url = 'https://www.cpuc.ca.gov'
    docs_url = 'https://docs.cpuc.ca.gov'
    search_url = 'https://docs.cpuc.ca.gov/SearchRes.aspx'

    # Proceeding prefix types
    PREFIX_TYPES = {
        'A': 'application',
        'R': 'rulemaking',
        'C': 'complaint',
        'I': 'investigation',
        'P': 'petition',
    }

    def scrape_docket_list(
        self,
        year: Optional[int] = None,
        status: Optional[str] = None,
        limit: int = 1000
    ) -> Iterator[DocketRecord]:
        """
        Scrape California CPUC proceedings from document search.

        California proceeding format: A.25-07-003 (compact: A2507003)
        - A = Application, R = Rulemaking, C = Complaint, I = Investigation
        - 25 = 2-digit year
        - 07 = month
        - 003 = sequence number
        """
        year = year or datetime.now().year
        seen_proceedings: Set[str] = set()
        total = 0

        # Search document listings to extract proceeding numbers
        logger.info(f"Searching California CPUC documents for {year}...")

        # Strategy 1: Search docs.cpuc.ca.gov with date filters
        for record in self._search_docs_by_date(year, seen_proceedings, limit):
            if total >= limit:
                break
            yield record
            total += 1

        # Strategy 2: Search by common proceeding prefixes
        if total < limit:
            logger.info("Searching by proceeding prefix patterns...")
            for record in self._search_by_prefix(year, seen_proceedings, limit - total):
                yield record
                total += 1

        logger.info(f"Scraped {total} proceedings from California CPUC")

    def _search_docs_by_date(
        self, year: int, seen: Set[str], limit: int
    ) -> Iterator[DocketRecord]:
        """Search document database by date to find proceedings."""
        total = 0

        # Search recent months
        end_date = datetime.now()
        start_date = datetime(year, 1, 1)

        # Search in chunks of 30 days
        current_date = end_date
        while current_date >= start_date and total < limit:
            chunk_start = current_date - timedelta(days=30)
            if chunk_start < start_date:
                chunk_start = start_date

            try:
                # Format dates for search
                start_str = chunk_start.strftime('%m/%d/%Y')
                end_str = current_date.strftime('%m/%d/%Y')

                # Build search URL with date parameters
                search_params = {
                    'StartDate': start_str,
                    'EndDate': end_str,
                }

                url = f"{self.search_url}?StartDate={start_str}&EndDate={end_str}"
                response = self.session.get(url, timeout=30)

                if response.status_code != 200:
                    logger.debug(f"Search returned {response.status_code}")
                    current_date = chunk_start - timedelta(days=1)
                    continue

                # Extract proceeding numbers from results
                for record in self._extract_proceedings_from_html(
                    response.text, seen, limit - total
                ):
                    yield record
                    total += 1

                time.sleep(0.3)  # Rate limiting

            except Exception as e:
                logger.debug(f"Error searching date range: {e}")

            current_date = chunk_start - timedelta(days=1)

    def _search_by_prefix(
        self, year: int, seen: Set[str], limit: int
    ) -> Iterator[DocketRecord]:
        """Search for proceedings by prefix pattern."""
        total = 0
        year_short = year % 100

        # Search for each prefix type
        for prefix in ['A', 'R', 'C', 'I']:
            if total >= limit:
                break

            # Try searching by proceeding number pattern
            search_term = f"{prefix}{year_short:02d}"

            try:
                url = f"{self.search_url}?SearchText={search_term}"
                response = self.session.get(url, timeout=30)

                if response.status_code == 200:
                    for record in self._extract_proceedings_from_html(
                        response.text, seen, limit - total
                    ):
                        yield record
                        total += 1

                time.sleep(0.3)

            except Exception as e:
                logger.debug(f"Error searching prefix {prefix}: {e}")

    def _extract_proceedings_from_html(
        self, html: str, seen: Set[str], limit: int
    ) -> Iterator[DocketRecord]:
        """Extract proceeding numbers from search results HTML."""
        total = 0

        # Pattern for compact proceeding numbers: A2507003
        compact_pattern = re.compile(r'\b([ARCIP])(\d{2})(\d{2})(\d{3})\b')

        # Pattern for display format: A.25-07-003
        display_pattern = re.compile(r'\b([ARCIP])\.(\d{2})-(\d{2})-(\d{3})\b')

        soup = BeautifulSoup(html, 'html.parser')
        page_text = soup.get_text()

        # Find all proceeding numbers
        found_proceedings = set()

        # Extract compact format
        for match in compact_pattern.finditer(page_text):
            prefix = match.group(1)
            year = match.group(2)
            month = match.group(3)
            seq = match.group(4)

            # Convert to display format
            proc_num = f"{prefix}.{year}-{month}-{seq}"
            if proc_num not in seen and proc_num not in found_proceedings:
                found_proceedings.add(proc_num)

        # Extract display format
        for match in display_pattern.finditer(page_text):
            proc_num = f"{match.group(1)}.{match.group(2)}-{match.group(3)}-{match.group(4)}"
            if proc_num not in seen and proc_num not in found_proceedings:
                found_proceedings.add(proc_num)

        # Also check links for proceeding numbers
        for link in soup.find_all('a', href=True):
            href = link['href']
            link_text = link.get_text()

            # Check URL and text for proceeding numbers
            for text in [href, link_text]:
                for match in compact_pattern.finditer(text):
                    proc_num = f"{match.group(1)}.{match.group(2)}-{match.group(3)}-{match.group(4)}"
                    if proc_num not in seen and proc_num not in found_proceedings:
                        found_proceedings.add(proc_num)

                for match in display_pattern.finditer(text):
                    proc_num = f"{match.group(1)}.{match.group(2)}-{match.group(3)}-{match.group(4)}"
                    if proc_num not in seen and proc_num not in found_proceedings:
                        found_proceedings.add(proc_num)

        # Yield records for found proceedings
        for proc_num in sorted(found_proceedings, reverse=True):
            if total >= limit:
                break

            seen.add(proc_num)

            # Parse components
            parsed = self.parse_california_docket(proc_num)
            if not parsed:
                continue

            prefix = parsed['prefix']
            case_type = self.PREFIX_TYPES.get(prefix, 'other')

            # Estimate filing date from proceeding number
            proc_year = 2000 + parsed['year']
            proc_month = parsed['month']
            if 1 <= proc_month <= 12:
                filing_date = f"{proc_year}-{proc_month:02d}-01"
            else:
                filing_date = f"{proc_year}-01-01"

            yield DocketRecord(
                docket_number=proc_num,
                title=f"California CPUC {case_type.title()} {proc_num}",
                case_type=case_type,
                filing_date=filing_date,
                status='open',
                source_url=f"https://apps.cpuc.ca.gov/apex/f?p=401:56:::NO:RP,57,RIR:P5_PROCEEDING_SELECT:{proc_num}",
            )
            total += 1

    def parse_california_docket(self, raw: str) -> Optional[dict]:
        """Parse California docket number into components."""
        # Format: A.24-07-003
        match = re.match(r'([ARCIP])\.(\d{2})-(\d{2})-(\d{3})', raw.upper())
        if match:
            return {
                'prefix': match.group(1),
                'year': int(match.group(2)),
                'month': int(match.group(3)),
                'sequence': int(match.group(4)),
            }
        return None

    def get_docket_detail(self, docket_number: str) -> Optional[DocketRecord]:
        """Get details for a specific California proceeding."""
        parsed = self.parse_california_docket(docket_number)
        if not parsed:
            return None

        prefix = parsed['prefix']
        case_type = self.PREFIX_TYPES.get(prefix, 'other')

        proc_year = 2000 + parsed['year']
        proc_month = parsed['month']
        if 1 <= proc_month <= 12:
            filing_date = f"{proc_year}-{proc_month:02d}-01"
        else:
            filing_date = f"{proc_year}-01-01"

        return DocketRecord(
            docket_number=docket_number,
            title=f"California CPUC {case_type.title()} {docket_number}",
            case_type=case_type,
            filing_date=filing_date,
            source_url=f"https://apps.cpuc.ca.gov/apex/f?p=401:56:::NO:RP,57,RIR:P5_PROCEEDING_SELECT:{docket_number}",
        )
