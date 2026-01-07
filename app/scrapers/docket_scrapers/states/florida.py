"""
Florida Public Service Commission Docket Scraper

PSC Website: https://www.psc.state.fl.us
Filings Library: https://www.psc.state.fl.us/library/filings/

Florida docket format: YYYYNNNN-XX
- YYYY = year (e.g., 2025)
- NNNN = 4-digit sequence (e.g., 0001)
- XX = sector code:
  - EI = Electric (investor-owned)
  - EU = Electric utility
  - GU = Gas Utility
  - WU = Water Utility
  - WS = Wastewater
  - SU = Sewer Utility
  - TX = Telecommunications
"""

from bs4 import BeautifulSoup
from datetime import datetime
from typing import Iterator, Optional, Set
import time
import re
import logging

from ..base import BaseDocketScraper, DocketRecord

logger = logging.getLogger(__name__)


class FloridaDocketScraper(BaseDocketScraper):
    """
    Scraper for Florida PSC docket data.

    Uses the filing library directory listing to extract docket numbers.
    """

    state_code = 'FL'
    state_name = 'Florida'
    base_url = 'https://www.psc.state.fl.us'
    library_url = 'https://www.psc.state.fl.us/library/filings'

    # Sector codes and their descriptions
    SECTOR_MAP = {
        'EI': 'electric',
        'EU': 'electric',
        'EP': 'electric',
        'GU': 'gas',
        'GP': 'gas',
        'WU': 'water',
        'WS': 'water',
        'WP': 'water',
        'SU': 'sewer',
        'TX': 'telecom',
        'TL': 'telecom',
        'TP': 'transport',
        'OT': 'other',
    }

    def scrape_docket_list(
        self,
        year: Optional[int] = None,
        status: Optional[str] = None,
        limit: int = 1000
    ) -> Iterator[DocketRecord]:
        """
        Scrape Florida PSC dockets from the filing library.

        Florida PSC docket format: YYYYNNNN-XX
        Example: 20250035-GU (Year 2025, Case 35, Gas Utility)
        """
        year = year or datetime.now().year
        seen_dockets: Set[str] = set()
        total = 0

        # Scan current and previous year
        years_to_scan = [year, year - 1] if year == datetime.now().year else [year]

        for scan_year in years_to_scan:
            if total >= limit:
                break

            logger.info(f"Scanning Florida PSC filings for {scan_year}...")

            try:
                # Get the filing directory listing
                filings_url = f"{self.library_url}/{scan_year}/"
                response = self.session.get(filings_url, timeout=30)

                if response.status_code != 200:
                    logger.warning(f"Could not access Florida filings for {scan_year}")
                    continue

                # Parse directory listing
                soup = BeautifulSoup(response.text, 'html.parser')

                # Find all filing directories - they link to XXXXX-YYYY/ directories
                filing_links = soup.find_all('a', href=re.compile(r'\d{5}-\d{4}/?'))

                logger.info(f"Found {len(filing_links)} filing directories for {scan_year}")

                for link in filing_links:
                    if total >= limit:
                        break

                    href = link['href']
                    filing_match = re.search(r'(\d{5})-(\d{4})', href)
                    if not filing_match:
                        continue

                    filing_num = filing_match.group(1)

                    # Get the filing directory to extract docket number
                    filing_dir_url = f"{self.library_url}/{scan_year}/{filing_num}-{scan_year}/"

                    try:
                        dir_response = self.session.get(filing_dir_url, timeout=30)
                        if dir_response.status_code != 200:
                            continue

                        # Extract docket numbers from the filing directory
                        # They appear in PDF filenames or the page content
                        # Pattern: YYYYNNNN-XX (e.g., 20250001-EI)
                        for docket_match in re.finditer(
                            r'(20\d{2})(\d{4})-([A-Z]{2})',
                            dir_response.text
                        ):
                            docket_id = f"{docket_match.group(1)}{docket_match.group(2)}-{docket_match.group(3)}"

                            if docket_id in seen_dockets:
                                continue

                            seen_dockets.add(docket_id)

                            # Parse components
                            docket_year = int(docket_match.group(1))
                            sector_code = docket_match.group(3)
                            sector_name = self.SECTOR_MAP.get(sector_code, 'other')

                            yield DocketRecord(
                                docket_number=docket_id,
                                title=f"Florida PSC Docket {docket_id}",
                                case_type=sector_name,
                                filing_date=f"{docket_year}-01-01",
                                status='open',
                                source_url=f"{self.base_url}/dockets?docket={docket_id}",
                            )
                            total += 1

                            if total >= limit:
                                break

                        time.sleep(0.1)  # Rate limiting

                    except Exception as e:
                        logger.debug(f"Error fetching filing {filing_num}: {e}")
                        continue

            except Exception as e:
                logger.error(f"Error scanning Florida filings for {scan_year}: {e}")
                continue

        logger.info(f"Scraped {total} dockets from Florida PSC")

    def get_docket_detail(self, docket_number: str) -> Optional[DocketRecord]:
        """Get details for a specific Florida docket."""
        match = re.match(r'(\d{4})(\d{4})-([A-Z]{2})', docket_number)
        if not match:
            return None

        docket_year = int(match.group(1))
        sector_code = match.group(3)
        sector_name = self.SECTOR_MAP.get(sector_code, 'other')

        return DocketRecord(
            docket_number=docket_number,
            title=f"Florida PSC Docket {docket_number}",
            case_type=sector_name,
            filing_date=f"{docket_year}-01-01",
            source_url=f"{self.base_url}/dockets?docket={docket_number}",
        )
