"""
Public Utility Commission of Texas Docket Scraper

PUC Website: https://www.puc.texas.gov
New Filings: https://www.puc.texas.gov/industry/filings/newfilings/
Interchange: https://interchange.puc.texas.gov/
"""

from bs4 import BeautifulSoup
from datetime import datetime
from typing import Iterator, Optional
import time
import re
import logging

from ..base import BaseDocketScraper, DocketRecord

logger = logging.getLogger(__name__)


class TexasDocketScraper(BaseDocketScraper):
    """Scraper for Texas PUC docket data."""

    state_code = 'TX'
    state_name = 'Texas'
    base_url = 'https://www.puc.texas.gov'
    new_filings_url = 'https://www.puc.texas.gov/industry/filings/newfilings/'
    interchange_url = 'https://interchange.puc.texas.gov'

    def scrape_docket_list(
        self,
        year: Optional[int] = None,
        status: Optional[str] = None,
        limit: int = 1000
    ) -> Iterator[DocketRecord]:
        """
        Scrape Texas PUC docket list from the new filings page.

        Texas PUC docket format: NNNNN (Control Number)
        Example: 59204, 55599

        The new filings page shows filings from the last 15 days.
        """
        total = 0

        try:
            logger.info(f"Fetching Texas PUC new filings from {self.new_filings_url}")
            response = self.session.get(self.new_filings_url, timeout=30)
            response.raise_for_status()

            soup = BeautifulSoup(response.text, 'html.parser')

            # Find the filings table - look for table with Control No. header
            tables = soup.find_all('table')
            filings_table = None

            for table in tables:
                header = table.find('th')
                if header and 'Control' in header.get_text():
                    filings_table = table
                    break

            # Alternative: look for table by class or structure
            if not filings_table:
                # Try finding by common table patterns
                filings_table = soup.find('table', class_='table') or \
                               soup.find('table', {'id': re.compile('filing', re.I)})

            if not filings_table:
                # Last resort: find any table with numeric first column
                for table in tables:
                    first_td = table.find('td')
                    if first_td and re.match(r'^\d{4,6}$', first_td.get_text(strip=True)):
                        filings_table = table
                        break

            if not filings_table:
                logger.warning("No filings table found on Texas PUC page")
                # Try parsing the page differently - look for filing patterns in links
                for link in soup.find_all('a', href=re.compile(r'/Search/Filings/\?cn=\d+')):
                    if total >= limit:
                        break

                    control_num = re.search(r'cn=(\d+)', link['href'])
                    if control_num:
                        docket_number = control_num.group(1)
                        title = link.get_text(strip=True) or None

                        yield DocketRecord(
                            docket_number=docket_number,
                            title=title,
                            source_url=f"{self.interchange_url}/Search/Filings/?cn={docket_number}",
                        )
                        total += 1
                return

            # Parse table rows
            rows = filings_table.find_all('tr')

            for row in rows:
                if total >= limit:
                    break

                cells = row.find_all(['td', 'th'])
                if len(cells) < 2:
                    continue

                # Skip header row
                if row.find('th'):
                    continue

                try:
                    # Column structure: Control No. | Date Filed | Description
                    control_text = cells[0].get_text(strip=True)

                    # Extract control number (should be 4-6 digits)
                    control_match = re.search(r'(\d{4,6})', control_text)
                    if not control_match:
                        continue

                    docket_number = control_match.group(1)

                    # Get date filed
                    filing_date = None
                    if len(cells) > 1:
                        date_text = cells[1].get_text(strip=True)
                        for fmt in ['%m/%d/%Y', '%m/%d/%y', '%Y-%m-%d']:
                            try:
                                filing_date = datetime.strptime(date_text, fmt).strftime('%Y-%m-%d')
                                break
                            except ValueError:
                                continue

                    # Get description/title
                    title = None
                    if len(cells) > 2:
                        title = cells[2].get_text(strip=True)
                        # Clean up title
                        title = re.sub(r'\s+', ' ', title)[:500]

                    # Extract utility name from title if possible
                    utility_name = self._extract_utility_from_title(title)

                    # Get case type from title
                    case_type = self._extract_case_type(title)

                    # Get source URL from link if present
                    source_url = f"{self.interchange_url}/Search/Filings/?cn={docket_number}"
                    link = cells[0].find('a')
                    if link and link.get('href'):
                        href = link['href']
                        if href.startswith('http'):
                            source_url = href
                        elif href.startswith('/'):
                            source_url = self.interchange_url + href

                    yield DocketRecord(
                        docket_number=docket_number,
                        title=title,
                        utility_name=utility_name,
                        case_type=case_type,
                        filing_date=filing_date,
                        source_url=source_url,
                        status='open',
                    )
                    total += 1

                except Exception as e:
                    logger.warning(f"Error parsing Texas row: {e}")
                    continue

            logger.info(f"Scraped {total} dockets from Texas PUC")

        except Exception as e:
            logger.error(f"Error scraping Texas PUC: {e}")
            raise

    def _extract_utility_from_title(self, title: Optional[str]) -> Optional[str]:
        """Extract utility company name from filing title."""
        if not title:
            return None

        # Common patterns
        patterns = [
            r'APPLICATION OF ([A-Z][A-Za-z\s&,\.]+(?:LLC|INC|CORP|LP|CO|COMPANY))',
            r'COMPLAINT.*?AGAINST ([A-Z][A-Za-z\s&,\.]+)',
            r'([A-Z][A-Za-z\s&]+(?:ELECTRIC|POWER|ENERGY|GAS|WATER|UTILITY))',
        ]

        for pattern in patterns:
            match = re.search(pattern, title, re.IGNORECASE)
            if match:
                return match.group(1).strip()[:200]

        return None

    def _extract_case_type(self, title: Optional[str]) -> Optional[str]:
        """Extract case type from filing title."""
        if not title:
            return None

        title_lower = title.lower()

        if 'complaint' in title_lower:
            return 'complaint'
        elif 'application' in title_lower:
            return 'application'
        elif 'rate' in title_lower:
            return 'rate_case'
        elif 'certificate' in title_lower:
            return 'certificate'
        elif 'tariff' in title_lower:
            return 'tariff'
        elif 'settlement' in title_lower:
            return 'settlement'
        elif 'report' in title_lower:
            return 'report'

        return None

    def get_docket_detail(self, docket_number: str) -> Optional[DocketRecord]:
        """Get detailed information for a specific Texas docket."""
        try:
            detail_url = f"{self.interchange_url}/Search/Filings/?cn={docket_number}"

            response = self.session.get(detail_url, timeout=30)
            if response.status_code != 200:
                return None

            soup = BeautifulSoup(response.text, 'html.parser')

            # Try to extract title from page
            title = None
            h1 = soup.find('h1')
            if h1:
                title = h1.get_text(strip=True)

            return DocketRecord(
                docket_number=docket_number,
                title=title,
                source_url=detail_url,
            )

        except Exception as e:
            logger.error(f"Error getting docket detail {docket_number}: {e}")
            return None
