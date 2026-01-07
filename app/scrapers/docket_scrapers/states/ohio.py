"""
Ohio Public Utilities Commission (PUCO) Docket Scraper

PUCO Website: https://puco.ohio.gov
DIS (Docket Information System): https://dis.puc.state.oh.us
Case Record URL: https://dis.puc.state.oh.us/CaseRecord.aspx?CaseNo=XX-NNNN

Ohio case number format: YY-NNNN-XX-XXX
- YY = 2-digit year
- NNNN = sequence number
- XX-XXX = case type codes:
  - EL-AIR = Electric Annual Increase Request
  - EL-RDR = Electric Rate Design Review
  - GA-AIR = Gas Annual Increase Request
  - WW-AIR = Water/Wastewater Annual Increase Request
"""

from bs4 import BeautifulSoup
from datetime import datetime
from typing import Iterator, Optional, Set
import time
import re
import logging

from ..base import BaseDocketScraper, DocketRecord

logger = logging.getLogger(__name__)


class OhioDocketScraper(BaseDocketScraper):
    """
    Scraper for Ohio PUCO docket data.

    Uses the Ohio Consumers' Counsel factsheets and iterates through
    known case number patterns to find active dockets.
    """

    state_code = 'OH'
    state_name = 'Ohio'
    base_url = 'https://puco.ohio.gov'
    dis_url = 'https://dis.puc.state.oh.us'
    occ_url = 'https://www.occ.ohio.gov'

    # Case type codes
    CASE_TYPES = {
        'EL': 'electric',
        'GA': 'gas',
        'WW': 'water',
        'WS': 'water',
        'TL': 'telecom',
        'TR': 'transport',
        'RR': 'railroad',
    }

    def scrape_docket_list(
        self,
        year: Optional[int] = None,
        status: Optional[str] = None,
        limit: int = 1000
    ) -> Iterator[DocketRecord]:
        """
        Scrape Ohio PUCO dockets.

        Ohio case format: YY-NNNN-XX-XXX
        Example: 25-0594-WW-AIR, 18-1546-EL-RDR
        """
        total = 0
        year = year or datetime.now().year
        seen_cases = set()

        # Strategy 1: Scrape OCC factsheets for current cases
        logger.info("Scraping Ohio Consumers' Counsel factsheets...")
        for record in self._scrape_occ_factsheets(seen_cases, limit):
            if total >= limit:
                break
            yield record
            total += 1

        # Strategy 2: Iterate through recent case numbers
        if total < limit:
            logger.info("Scanning recent Ohio case numbers...")
            years_to_scan = [year % 100, (year - 1) % 100]

            for scan_year in years_to_scan:
                if total >= limit:
                    break

                for case_type in ['EL', 'GA', 'WW']:
                    if total >= limit:
                        break

                    for record in self._scan_case_range(
                        scan_year, case_type, seen_cases, limit - total
                    ):
                        yield record
                        total += 1

        logger.info(f"Scraped {total} dockets from Ohio PUCO")

    def _scrape_occ_factsheets(
        self, seen_cases: Set[str], limit: int
    ) -> Iterator[DocketRecord]:
        """Scrape case info from Ohio Consumers' Counsel factsheets."""
        try:
            response = self.session.get(f"{self.occ_url}/factsheet", timeout=30)
            if response.status_code != 200:
                return

            soup = BeautifulSoup(response.text, 'html.parser')

            # Find all factsheet links that contain case numbers
            for link in soup.find_all('a', href=re.compile(r'/factsheet/')):
                href = link['href']
                text = link.get_text(strip=True)

                # Extract case number from URL or text
                # Pattern: XX-NNNN-XX-XXX
                case_match = re.search(r'(\d{2})-(\d{4})-([A-Z]{2})-([A-Z]{2,3})', href + ' ' + text)
                if not case_match:
                    continue

                case_num = f"{case_match.group(1)}-{case_match.group(2)}-{case_match.group(3)}-{case_match.group(4)}"

                if case_num in seen_cases:
                    continue

                seen_cases.add(case_num)

                # Extract title from link text
                title = text
                # Clean up title
                title = re.sub(r'\d{2}-\d{4}.*$', '', title).strip()

                # Determine sector
                sector_code = case_match.group(3)
                sector = self.CASE_TYPES.get(sector_code, 'other')

                # Extract utility name from title
                utility_name = self._extract_utility(title)

                yield DocketRecord(
                    docket_number=case_num,
                    title=title or f"Ohio PUCO Case {case_num}",
                    utility_name=utility_name,
                    case_type=sector,
                    status='open',
                    source_url=f"{self.dis_url}/CaseRecord.aspx?CaseNo={case_num}",
                )

        except Exception as e:
            logger.warning(f"Error scraping OCC factsheets: {e}")

    def _scan_case_range(
        self,
        year_short: int,
        case_type: str,
        seen_cases: Set[str],
        limit: int
    ) -> Iterator[DocketRecord]:
        """Scan a range of case numbers for valid dockets."""
        total = 0
        consecutive_misses = 0

        # Start from a reasonable sequence number
        for seq in range(1, 2000):
            if total >= limit or consecutive_misses >= 20:
                break

            case_num = f"{year_short:02d}-{seq:04d}-{case_type}"

            if case_num in seen_cases:
                continue

            # Try to verify this case exists
            record = self._check_case_exists(case_num)
            if record:
                seen_cases.add(case_num)
                yield record
                total += 1
                consecutive_misses = 0
            else:
                consecutive_misses += 1

            time.sleep(0.2)  # Rate limiting

    def _check_case_exists(self, case_num: str) -> Optional[DocketRecord]:
        """Check if a case number exists by trying to access it."""
        try:
            # Note: The DIS system may block requests, so we'll use
            # a simplified approach that generates records based on
            # known valid patterns
            url = f"{self.dis_url}/CaseRecord.aspx?CaseNo={case_num}"

            response = self.session.get(url, timeout=15)
            if response.status_code != 200:
                return None

            # Check if the response contains valid case data
            if 'Case not found' in response.text or 'error' in response.text.lower()[:500]:
                return None

            soup = BeautifulSoup(response.text, 'html.parser')

            # Extract title from page
            title = None
            title_elem = soup.find('span', {'id': re.compile(r'CaseTitle', re.I)})
            if title_elem:
                title = title_elem.get_text(strip=True)

            if not title:
                # Look for any h1/h2 with case info
                for header in soup.find_all(['h1', 'h2']):
                    header_text = header.get_text(strip=True)
                    if case_num in header_text or 'case' in header_text.lower():
                        title = header_text
                        break

            if not title:
                title = f"Ohio PUCO Case {case_num}"

            # Determine sector from case type
            type_match = re.search(r'-([A-Z]{2})-', case_num)
            sector = self.CASE_TYPES.get(type_match.group(1), 'other') if type_match else 'other'

            return DocketRecord(
                docket_number=case_num,
                title=title,
                case_type=sector,
                status='open',
                source_url=url,
            )

        except Exception as e:
            logger.debug(f"Error checking case {case_num}: {e}")
            return None

    def _extract_utility(self, text: str) -> Optional[str]:
        """Extract utility company name from text."""
        if not text:
            return None

        # Common Ohio utilities
        utilities = [
            'AEP Ohio', 'Duke Energy', 'FirstEnergy', 'AES Ohio',
            'Aqua Ohio', 'Columbia Gas', 'Dominion Energy',
            'CenterPoint', 'Suburban Natural Gas', 'Ohio Edison',
            'Cleveland Electric', 'Toledo Edison',
        ]

        for utility in utilities:
            if utility.lower() in text.lower():
                return utility

        return None

    def get_docket_detail(self, docket_number: str) -> Optional[DocketRecord]:
        """Get details for a specific Ohio docket."""
        return self._check_case_exists(docket_number)
