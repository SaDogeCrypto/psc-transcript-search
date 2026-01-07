"""
Georgia Public Service Commission Docket Scraper

PSC Website: https://psc.ga.gov
Docket Detail: https://psc.ga.gov/search/facts-docket/?docketId=XXXXX
Utilities Page: https://psc.ga.gov/utilities/electric/
"""

from bs4 import BeautifulSoup
from datetime import datetime
from typing import Iterator, Optional, List, Dict
import time
import re
import logging

from ..base import BaseDocketScraper, DocketRecord

logger = logging.getLogger(__name__)


class GeorgiaDocketScraper(BaseDocketScraper):
    """
    Scraper for Georgia PSC docket data.

    Georgia PSC uses a JavaScript-rendered search, so we use two strategies:
    1. Scrape known dockets from static utility pages
    2. Iterate through recent docket IDs and fetch details
    """

    state_code = 'GA'
    state_name = 'Georgia'
    base_url = 'https://psc.ga.gov'
    docket_detail_url = 'https://psc.ga.gov/search/facts-docket/'

    # Known utility pages that list dockets
    utility_pages = [
        '/utilities/electric/',
        '/utilities/natural-gas/',
        '/utilities/telecommunications/',
    ]

    def scrape_docket_list(
        self,
        year: Optional[int] = None,
        status: Optional[str] = None,
        limit: int = 1000
    ) -> Iterator[DocketRecord]:
        """
        Scrape Georgia PSC dockets using multiple strategies.

        Georgia docket format: NNNNN (5-digit number)
        Example: 44280, 42516
        """
        seen_dockets = set()
        total = 0

        # Strategy 1: Scrape known dockets from utility pages
        logger.info("Scraping dockets from Georgia PSC utility pages...")
        for page_url in self.utility_pages:
            if total >= limit:
                break

            try:
                response = self.session.get(f"{self.base_url}{page_url}", timeout=30)
                if response.status_code != 200:
                    continue

                soup = BeautifulSoup(response.text, 'html.parser')

                # Find all links containing docket IDs
                for link in soup.find_all('a', href=True):
                    if total >= limit:
                        break

                    href = link['href']

                    # Look for docket ID patterns in URLs
                    docket_match = re.search(r'docketId=(\d+)', href)
                    if docket_match:
                        docket_id = docket_match.group(1)
                        if docket_id in seen_dockets:
                            continue

                        # Get docket details
                        record = self._fetch_docket_detail(docket_id)
                        if record:
                            seen_dockets.add(docket_id)
                            yield record
                            total += 1

                    # Also look for docket numbers in text like "docket 44280"
                    text = link.get_text()
                    text_match = re.search(r'docket[s]?\s*#?\s*(\d{4,6})', text, re.I)
                    if text_match:
                        docket_id = text_match.group(1)
                        if docket_id in seen_dockets:
                            continue

                        record = self._fetch_docket_detail(docket_id)
                        if record:
                            seen_dockets.add(docket_id)
                            yield record
                            total += 1

                # Also scan page text for docket references
                page_text = soup.get_text()
                for match in re.finditer(r'(?:docket|case)\s*#?\s*(\d{4,6})', page_text, re.I):
                    if total >= limit:
                        break

                    docket_id = match.group(1)
                    if docket_id in seen_dockets:
                        continue

                    record = self._fetch_docket_detail(docket_id)
                    if record:
                        seen_dockets.add(docket_id)
                        yield record
                        total += 1

                time.sleep(0.5)  # Rate limiting

            except Exception as e:
                logger.warning(f"Error scraping {page_url}: {e}")
                continue

        # Strategy 2: Iterate through recent docket IDs
        # Georgia dockets are sequential, recent ones are in 44000-45000 range
        if total < limit:
            logger.info("Scanning recent Georgia docket IDs...")

            # Determine starting point - recent dockets
            year = year or datetime.now().year
            if year >= 2024:
                start_id = 44500
            elif year >= 2022:
                start_id = 44000
            elif year >= 2020:
                start_id = 42000
            else:
                start_id = 40000

            # Scan forward from start
            consecutive_misses = 0
            current_id = start_id

            while total < limit and consecutive_misses < 20:
                if str(current_id) in seen_dockets:
                    current_id += 1
                    continue

                record = self._fetch_docket_detail(str(current_id))
                if record:
                    seen_dockets.add(str(current_id))
                    yield record
                    total += 1
                    consecutive_misses = 0
                else:
                    consecutive_misses += 1

                current_id += 1
                time.sleep(0.3)  # Rate limiting

        logger.info(f"Scraped {total} dockets from Georgia PSC")

    def _fetch_docket_detail(self, docket_id: str) -> Optional[DocketRecord]:
        """Fetch details for a specific docket."""
        try:
            url = f"{self.docket_detail_url}?docketId={docket_id}"
            response = self.session.get(url, timeout=30)

            if response.status_code != 200:
                return None

            soup = BeautifulSoup(response.text, 'html.parser')
            page_text = soup.get_text()

            # Check if this is a valid docket page
            if 'docket not found' in page_text.lower():
                return None

            # Extract docket information using Georgia PSC's page structure
            title = None
            utility_name = None
            filing_date = None
            status = None
            case_type = None

            # Parse the page text line by line to find metadata
            lines = [l.strip() for l in page_text.split('\n') if l.strip()]

            for i, line in enumerate(lines):
                # Look for "Title:" label followed by actual title
                if line == 'Title:' and i + 1 < len(lines):
                    potential_title = lines[i + 1]
                    # Filter out other labels
                    if potential_title and potential_title not in ['Industry:', 'Status:', 'Document']:
                        title = potential_title

                # Look for "Industry:" label
                elif line == 'Industry:' and i + 1 < len(lines):
                    case_type = lines[i + 1].lower()

                # Look for "Status:" label
                elif line == 'Status:' and i + 1 < len(lines):
                    next_line = lines[i + 1].lower()
                    if next_line in ['open', 'closed', 'certified', 'compliance', 'ongoing', 'tariff', 'appeal']:
                        status = next_line

                # Look for filing date patterns
                elif 'filed:' in line.lower() or 'filing date:' in line.lower():
                    date_match = re.search(r'(\d{1,2}/\d{1,2}/\d{4})', line)
                    if date_match:
                        try:
                            filing_date = datetime.strptime(date_match.group(1), '%m/%d/%Y').strftime('%Y-%m-%d')
                        except ValueError:
                            pass

            # Extract utility from title if found
            if title:
                utility_name = self._extract_utility_from_title(title)

            # Only return if we found a title
            if not title:
                return None

            return DocketRecord(
                docket_number=docket_id,
                title=title,
                utility_name=utility_name,
                filing_date=filing_date,
                status=status or 'open',
                case_type=case_type,
                source_url=url,
            )

        except Exception as e:
            logger.debug(f"Error fetching docket {docket_id}: {e}")
            return None

    def _extract_utility_from_title(self, title: str) -> Optional[str]:
        """Extract utility company name from title."""
        if not title:
            return None

        # Common Georgia utilities
        utilities = [
            'Georgia Power', 'Atlanta Gas Light', 'SCANA Energy',
            'Georgia Natural Gas', 'AT&T', 'Verizon', 'Comcast',
            'Southern Company', 'Oglethorpe Power', 'MEAG Power',
        ]

        for utility in utilities:
            if utility.lower() in title.lower():
                return utility

        # Try pattern matching
        patterns = [
            r'^([A-Z][A-Za-z\s&]+(?:Power|Gas|Electric|Energy|Communications?))\b',
            r'(?:Application of|Petition of|Complaint against)\s+([A-Z][A-Za-z\s&,\.]+)',
        ]

        for pattern in patterns:
            match = re.search(pattern, title, re.IGNORECASE)
            if match:
                return match.group(1).strip()[:200]

        return None

    def get_docket_detail(self, docket_number: str) -> Optional[DocketRecord]:
        """Get detailed information for a specific Georgia docket."""
        return self._fetch_docket_detail(docket_number)
