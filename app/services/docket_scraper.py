"""
Unified Docket Scraper Service

Fetches and parses docket metadata from state PSC websites using
configuration from state_psc_configs table.

Some states (FL, OH) require Playwright for JavaScript rendering or
to bypass bot protection. OH uses Bright Data proxy to bypass Shape Security.
"""
import re
import httpx
import asyncio
import logging
from datetime import datetime, date
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field, asdict
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.settings import get_settings

logger = logging.getLogger(__name__)

# Playwright is optional - only needed for FL, OH
try:
    from playwright.async_api import async_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False


@dataclass
class ScrapedDocket:
    """Standardized docket data scraped from a state PSC website."""
    state_code: str
    docket_number: str
    found: bool = False

    # Core metadata
    title: Optional[str] = None
    description: Optional[str] = None
    utility_name: Optional[str] = None
    utility_type: Optional[str] = None  # Electric, Gas, Water, Telephone
    industry: Optional[str] = None
    filing_party: Optional[str] = None

    # Dates
    filing_date: Optional[date] = None
    decision_date: Optional[date] = None
    last_activity_date: Optional[date] = None

    # Classification
    status: Optional[str] = None  # open, closed, pending
    docket_type: Optional[str] = None  # Rate Case, Merger, Certificate, etc.
    sub_type: Optional[str] = None

    # People
    assigned_commissioner: Optional[str] = None
    assigned_judge: Optional[str] = None

    # Related
    related_dockets: List[str] = field(default_factory=list)
    parties: List[Dict[str, str]] = field(default_factory=list)

    # Documents
    documents_url: Optional[str] = None
    documents_count: Optional[int] = None

    # Source
    source_url: Optional[str] = None
    error: Optional[str] = None

    # State-specific extras
    extra_data: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        d = asdict(self)
        # Convert date objects to strings
        for key in ['filing_date', 'decision_date', 'last_activity_date']:
            if d[key] and isinstance(d[key], date):
                d[key] = d[key].isoformat()
        return d


class DocketScraper:
    """Multi-state docket scraper using configuration from database."""

    def __init__(self, db: Session):
        self.db = db
        self._configs: Dict[str, Dict] = {}
        self._load_configs()

    def _load_configs(self):
        """Load state configurations from database."""
        result = self.db.execute(text(
            "SELECT * FROM state_psc_configs WHERE enabled = TRUE"
        ))
        for row in result.mappings():
            self._configs[row['state_code']] = dict(row)

    def get_enabled_states(self) -> List[str]:
        """Get list of states with enabled scrapers."""
        return list(self._configs.keys())

    def get_config(self, state_code: str) -> Optional[Dict]:
        """Get configuration for a state."""
        return self._configs.get(state_code)

    async def scrape_docket(self, state_code: str, docket_number: str) -> ScrapedDocket:
        """
        Scrape docket metadata from a state PSC website.

        Args:
            state_code: Two-letter state code (e.g., 'GA', 'TX')
            docket_number: The docket number to look up

        Returns:
            ScrapedDocket with all available metadata
        """
        result = ScrapedDocket(state_code=state_code, docket_number=docket_number)

        # Get config (may not be in cache if not enabled)
        config = self._configs.get(state_code)
        if not config:
            # Try to load from database even if not enabled
            row = self.db.execute(text(
                "SELECT * FROM state_psc_configs WHERE state_code = :code"
            ), {"code": state_code}).mappings().fetchone()
            if row:
                config = dict(row)
            else:
                result.error = f"No configuration found for state {state_code}"
                return result

        # Build URL from template
        url_template = config.get('docket_detail_url_template')
        if not url_template:
            result.error = f"No detail URL template for {state_code}"
            return result

        # States that require Playwright for JavaScript rendering / bot protection
        playwright_states = ('FL', 'OH', 'NY', 'CA', 'AZ')
        if state_code in playwright_states:
            if not PLAYWRIGHT_AVAILABLE:
                result.error = f"Playwright not installed - required for {state_code} scraping"
                return result
            return await self._scrape_with_playwright(state_code, docket_number, result, config)

        # Special URL handling for certain states
        if state_code == 'WA':
            # WA format: UE-220066 -> year=2022, number=220066
            wa_match = re.match(r'^[A-Z]{2}-(\d{2})(\d+)$', docket_number.upper())
            if wa_match:
                year = f"20{wa_match.group(1)}"
                number = wa_match.group(1) + wa_match.group(2)
                url = f"https://www.utc.wa.gov/casedocket/{year}/{number}"
            else:
                url = url_template.format(docket=docket_number)
        else:
            url = url_template.format(docket=docket_number)
        result.source_url = url

        try:
            async with httpx.AsyncClient(timeout=15.0, follow_redirects=True, verify=False) as client:
                response = await client.get(url)

                if response.status_code != 200:
                    result.error = f"HTTP {response.status_code}"
                    return result

                html = response.text

                # Route to state-specific parser
                scraper_type = config.get('scraper_type', 'html')
                if state_code == 'GA':
                    return await self._parse_georgia(html, result, config)
                elif state_code == 'TX':
                    return await self._parse_texas(html, result, config, client)
                elif state_code == 'PA':
                    return self._parse_pennsylvania(html, result, config)
                elif state_code == 'NJ':
                    return self._parse_newjersey(html, result, config)
                elif state_code == 'WA':
                    return self._parse_washington(html, result, config)
                elif state_code == 'CO':
                    return self._parse_colorado(html, result, config)
                elif state_code == 'NC':
                    return self._parse_northcarolina(html, result, config)
                elif state_code == 'SC':
                    return self._parse_southcarolina(html, result, config)
                elif state_code == 'MO':
                    return self._parse_missouri(html, result, config)
                else:
                    # Generic parsing attempt
                    return self._parse_generic(html, result, config)

        except Exception as e:
            result.error = str(e)
            return result

    async def _parse_georgia(self, html: str, result: ScrapedDocket, config: Dict) -> ScrapedDocket:
        """Parse Georgia PSC docket page."""
        # Check if docket exists
        if result.docket_number not in html and f"#{result.docket_number}" not in html:
            result.found = False
            return result

        result.found = True

        # Extract using h6 tag pattern
        # Title
        match = re.search(r'<h6[^>]*>\s*Title[:\s]*</h6>\s*([^<]+)', html, re.IGNORECASE)
        if match:
            result.title = match.group(1).strip()

        # Industry (utility type)
        match = re.search(r'<h6[^>]*>\s*Industry[:\s]*</h6>\s*([^<]+)', html, re.IGNORECASE)
        if match:
            industry = match.group(1).strip()
            result.industry = industry
            # Map to standard utility_type
            industry_lower = industry.lower()
            if 'electric' in industry_lower:
                result.utility_type = 'Electric'
            elif 'gas' in industry_lower:
                result.utility_type = 'Gas'
            elif 'telecom' in industry_lower or 'telephone' in industry_lower:
                result.utility_type = 'Telephone'
            elif 'water' in industry_lower:
                result.utility_type = 'Water'

        # Date
        match = re.search(r'<h6[^>]*>\s*Date[:\s]*</h6>\s*([^<]+)', html, re.IGNORECASE)
        if match:
            date_str = match.group(1).strip()
            result.filing_date = self._parse_date(date_str)

        # Status
        match = re.search(r'<h6[^>]*>\s*Status[:\s]*</h6>\s*([^<]+)', html, re.IGNORECASE)
        if match:
            result.status = match.group(1).strip().lower()

        # Try to find company name
        company_patterns = [
            r'Georgia\s+Power\s+Company',
            r'Atlanta\s+Gas\s+Light',
            r'Southern\s+Company\s+Gas',
            r'Liberty\s+Utilities',
        ]
        for pattern in company_patterns:
            match = re.search(pattern, html, re.IGNORECASE)
            if match:
                result.utility_name = match.group(0)
                break

        return result

    async def _parse_texas(self, html: str, result: ScrapedDocket, config: Dict,
                          client: httpx.AsyncClient) -> ScrapedDocket:
        """Parse Texas PUC documents page."""
        # Check for no results
        if "No filings found" in html or "0 results" in html.lower():
            result.found = False
            return result

        if result.docket_number not in html:
            result.found = False
            return result

        result.found = True

        # Case Style (title)
        match = re.search(r'<strong>Case Style</strong>\s*(?:&nbsp;|\s)*([^<]+)', html, re.IGNORECASE)
        if match:
            result.title = match.group(1).strip()

        # File Stamp (filing date)
        match = re.search(r'<strong>File Stamp</strong>\s*(?:&nbsp;|\s)*([^<]+)', html, re.IGNORECASE)
        if match:
            result.filing_date = self._parse_date(match.group(1).strip())

        # Filing Party
        match = re.search(r'<strong>Filing Party</strong>\s*(?:&nbsp;|\s)*([^<]+)', html, re.IGNORECASE)
        if match:
            result.filing_party = match.group(1).strip()

        # Try to get utility type from PDF
        pdf_match = re.search(r'href="(https://interchange\.puc\.texas\.gov/Documents/[^"]+\.PDF)"',
                              html, re.IGNORECASE)
        if pdf_match:
            pdf_url = pdf_match.group(1)
            try:
                pdf_response = await client.get(pdf_url)
                if pdf_response.status_code == 200:
                    result.utility_type = self._extract_tx_utility_type(pdf_response.content)
            except Exception:
                pass

        # Documents URL
        result.documents_url = result.source_url

        return result

    def _extract_tx_utility_type(self, pdf_bytes: bytes) -> Optional[str]:
        """Extract utility type from Texas PUC PDF using checkbox detection."""
        try:
            import fitz  # PyMuPDF

            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            text = ""
            for page in doc:
                text += page.get_text() + "\n"
            doc.close()

            # Look for checkbox markers - '~' before the type name indicates checked
            lines = text.split('\n')
            checked_types = []

            for line in lines:
                line_stripped = line.strip()
                if line_stripped.startswith('~'):
                    parts = line_stripped.split()
                    if len(parts) >= 2:
                        type_name = parts[1].upper()
                        if type_name in ['ELECTRIC', 'TELEPHONE', 'WATER', 'OTHER']:
                            checked_types.append(type_name.capitalize())

            if checked_types:
                return ", ".join(checked_types)

            # Fallback to keyword detection
            text_upper = text.upper()
            if "ERCOT" in text_upper or "POWER" in text_upper:
                return "Electric"
            if "TELECOM" in text_upper or "COMMUNICATIONS" in text_upper:
                return "Telephone"

            return None
        except Exception:
            return None

    async def _scrape_with_playwright(self, state_code: str, docket_number: str,
                                        result: ScrapedDocket, config: Dict) -> ScrapedDocket:
        """
        Scrape using Playwright for states that need JavaScript rendering or bot evasion.

        FL: Angular SPA that loads data dynamically
        OH: Has bot protection (Shape Security) that blocks simple HTTP requests
        NY: ASPX app that needs JS rendering
        CA: Oracle APEX app with form submission
        """
        try:
            settings = get_settings()

            async with async_playwright() as p:
                # States with government sites that have Shape Security (need residential proxy)
                shape_security_states = ('OH',)

                # Check if residential proxy is available for Shape Security sites
                use_residential = (
                    state_code in shape_security_states
                    and settings.brightdata.residential_enabled
                    and settings.brightdata.residential_proxy_config
                )

                # Check if we should use Bright Data Browser API (not for gov sites)
                use_brightdata_browser = (
                    state_code not in shape_security_states
                    and state_code in settings.scraper.proxy_states
                    and settings.brightdata.browser_enabled
                    and settings.brightdata.browser_ws
                )

                # Standard launch args for local browser
                launch_args = [
                    '--disable-blink-features=AutomationControlled',
                    '--no-sandbox',
                    '--disable-dev-shm-usage',
                    '--disable-infobars',
                    '--window-size=1920,1080',
                ]

                if use_residential:
                    # Use residential proxy with local browser for Shape Security sites
                    logger.info(f"Using Bright Data residential proxy for {state_code}")
                    browser = await p.chromium.launch(
                        headless=True,
                        args=launch_args + ['--ignore-certificate-errors']
                    )
                    context = await browser.new_context(
                        proxy=settings.brightdata.residential_proxy_config,
                        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                        viewport={"width": 1920, "height": 1080},
                        ignore_https_errors=True  # Required for proxy SSL inspection
                    )
                    page = await context.new_page()
                    # Anti-detection for residential proxy
                    await page.add_init_script("""
                        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                        window.chrome = { runtime: {} };
                    """)
                elif use_brightdata_browser:
                    # Connect to Bright Data's remote browser via CDP (non-government sites)
                    logger.info(f"Using Bright Data Browser API for {state_code}")
                    browser = await p.chromium.connect_over_cdp(settings.brightdata.browser_ws)
                    context = browser.contexts[0] if browser.contexts else await browser.new_context()
                    page = await context.new_page()
                else:
                    # Launch local browser without proxy
                    browser = await p.chromium.launch(
                        headless=True,
                        args=launch_args
                    )
                    context = await browser.new_context(
                        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                        viewport={"width": 1920, "height": 1080},
                        locale="en-US",
                        timezone_id="America/New_York",
                        extra_http_headers={
                            "Accept-Language": "en-US,en;q=0.9",
                        }
                    )
                    page = await context.new_page()

                    # Remove webdriver detection (only for local browser)
                    await page.add_init_script("""
                        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                        Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
                        Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
                        window.chrome = { runtime: {} };
                    """)

                # Route to state-specific scraper
                if state_code == 'FL':
                    result = await self._scrape_florida_playwright(page, docket_number, result)
                elif state_code == 'OH':
                    result = await self._scrape_ohio_playwright(page, docket_number, result)
                elif state_code == 'NY':
                    result = await self._scrape_newyork_playwright(page, docket_number, result)
                elif state_code == 'CA':
                    result = await self._scrape_california_playwright(page, docket_number, result)
                elif state_code == 'AZ':
                    result = await self._scrape_arizona_playwright(page, docket_number, result)

                await browser.close()
                return result

        except Exception as e:
            error_msg = str(e)
            # Provide helpful error for Ohio connection failures
            if state_code == 'OH' and ('Target' in error_msg or 'closed' in error_msg.lower()):
                result.error = (
                    "Ohio PUCO connection failed (Shape Security WAF). "
                    f"Visit https://dis.puc.state.oh.us/CaseRecord.aspx?CaseNo={docket_number} directly."
                )
            else:
                result.error = f"Playwright error: {error_msg}"
            return result

        return result

    async def _scrape_florida_playwright(self, page, docket_number: str, result: ScrapedDocket) -> ScrapedDocket:
        """Scrape Florida PSC using Playwright."""
        # FL uses 8-digit format without suffix: 20240001-EI -> 20240001
        # Extract just the 8-digit number
        match = re.match(r'(\d{8})', docket_number.replace('-', ''))
        if not match:
            result.error = "Invalid FL docket format - expected 8-digit number"
            return result

        docket_num = match.group(1)
        url = f"https://www.floridapsc.com/clerks-office-dockets-level2?DocketNo={docket_num}"
        result.source_url = url

        try:
            await page.goto(url, timeout=30000)
            await asyncio.sleep(5)  # Wait for Angular to load

            text = await page.inner_text("body")

            # Check for 404
            if "404" in text and "PAGE NOT FOUND" in text.upper():
                result.found = False
                result.error = "Docket not found"
                return result

            # Parse the docket info from text
            # Format: "Docket : 20240001 (CLOSED) - Title here"
            docket_match = re.search(r'Docket\s*:\s*(\d+)\s*\((\w+)\)\s*-\s*(.+?)(?=Empty heading|CASR|$)', text, re.DOTALL)
            if docket_match:
                result.found = True
                result.status = docket_match.group(2).lower()
                result.title = docket_match.group(3).strip()
            else:
                # Try alternate pattern
                if docket_num in text:
                    result.found = True
                else:
                    result.found = False
                    result.error = "Could not parse docket info"
                    return result

            # Extract utility type from docket suffix
            suffix_match = re.search(r'-([A-Z]{2})$', docket_number)
            if suffix_match:
                suffix = suffix_match.group(1)
                sector_map = {
                    'EU': 'Electric', 'EI': 'Electric', 'EP': 'Electric',
                    'GU': 'Gas', 'GP': 'Gas',
                    'WU': 'Water', 'WP': 'Water', 'WS': 'Water',
                    'TU': 'Telephone', 'TL': 'Telephone', 'TP': 'Telephone',
                }
                result.utility_type = sector_map.get(suffix)

            return result

        except Exception as e:
            result.error = f"FL scrape error: {str(e)}"
            return result

    async def _scrape_ohio_playwright(self, page, docket_number: str, result: ScrapedDocket) -> ScrapedDocket:
        """Scrape Ohio PUCO using Playwright with stealth settings.

        NOTE: Ohio PUCO uses Shape Security WAF which blocks most automated access.
        Both Bright Data (blocks gov sites by policy) and Browserless (datacenter IPs
        detected) are blocked. Residential proxy with local browser may be required.
        """
        url = f"https://dis.puc.state.oh.us/CaseRecord.aspx?CaseNo={docket_number}"
        result.source_url = url

        try:
            # First visit homepage to establish session/cookies
            # Residential proxies can be slower, use longer timeouts
            await page.goto("https://dis.puc.state.oh.us/", timeout=60000)
            await asyncio.sleep(3)

            # Now navigate to the specific case
            await page.goto(url, timeout=60000, wait_until="networkidle")
            await asyncio.sleep(5)  # Wait for JS challenge and page load

            text = await page.inner_text("body")

            # Check for rejection by Shape Security
            if "Request Rejected" in text or "URL was rejected" in text:
                result.error = (
                    "Ohio PUCO blocked by Shape Security WAF. "
                    "This site requires residential IP access. "
                    "Visit https://dis.puc.state.oh.us/CaseRecord.aspx?CaseNo={} directly."
                ).format(docket_number)
                result.found = False
                return result

            # Parse case info
            # Pattern: "Case Record For: XX-XXXX-XX-XXX"
            if docket_number not in text:
                result.found = False
                result.error = "Docket not found"
                return result

            result.found = True

            # Extract Case Title
            title_match = re.search(r'Case Title:\s*(.+?)(?=Status:|Industry Code:|$)', text, re.DOTALL)
            if title_match:
                result.title = title_match.group(1).strip()

            # Extract Status
            status_match = re.search(r'Status:\s*(\S+)', text)
            if status_match:
                status = status_match.group(1).lower()
                if 'open' in status:
                    result.status = 'open'
                elif 'closed' in status:
                    result.status = 'closed'
                else:
                    result.status = status

            # Extract Industry Code
            industry_match = re.search(r'Industry Code:\s*([A-Z]+)-([A-Za-z]+)', text)
            if industry_match:
                code = industry_match.group(1)
                name = industry_match.group(2)
                result.industry = name.upper()

                code_map = {
                    'EL': 'Electric',
                    'GA': 'Gas',
                    'WW': 'Water',
                    'WS': 'Water',
                    'TL': 'Telephone',
                    'TR': 'Transportation',
                }
                result.utility_type = code_map.get(code, name.title())

            # Extract Purpose Code (docket type)
            purpose_match = re.search(r'Purpose Code:\s*([A-Z]+)-(.+?)(?=Date Opened:|$)', text)
            if purpose_match:
                code = purpose_match.group(1)
                desc = purpose_match.group(2).strip()
                result.sub_type = desc

                type_map = {
                    'AIR': 'Rate Case',
                    'SSO': 'Standard Service Offer',
                    'ATA': 'Alternative Regulation',
                    'UNC': 'Uncollectible Expense',
                    'RDR': 'Rider',
                    'GCR': 'Gas Cost Recovery',
                    'EEC': 'Energy Efficiency',
                }
                result.docket_type = type_map.get(code, desc)

            # Extract Date Opened
            date_match = re.search(r'Date Opened:\s*(\d{1,2}/\d{1,2}/\d{4})', text)
            if date_match:
                result.filing_date = self._parse_date(date_match.group(1))

            # Extract Date Closed
            closed_match = re.search(r'Date Closed:\s*(\d{1,2}/\d{1,2}/\d{4})', text)
            if closed_match:
                result.decision_date = self._parse_date(closed_match.group(1))

            return result

        except Exception as e:
            result.error = f"OH scrape error: {str(e)}"
            return result

    async def _scrape_newyork_playwright(self, page, docket_number: str, result: ScrapedDocket) -> ScrapedDocket:
        """Scrape New York PSC using Playwright."""
        # NY format: YY-X-NNNN (e.g., 24-E-0314)
        url = f"https://documents.dps.ny.gov/public/MatterManagement/CaseMaster.aspx?MatterCaseNo={docket_number}"
        result.source_url = url

        try:
            # NY site can be slow - use longer timeout
            await page.goto(url, timeout=60000)
            await asyncio.sleep(4)

            text = await page.inner_text("body")

            # Check if case found
            if "does not exist" in text or "Case not found" in text or "No records" in text.lower():
                result.found = False
                result.error = "Docket not found"
                return result

            if docket_number not in text:
                result.found = False
                result.error = "Docket not found"
                return result

            result.found = True

            # Extract Industry Affected (utility type)
            industry_match = re.search(r'Industry Affected[:\s]*(\w+)', text)
            if industry_match:
                industry = industry_match.group(1).strip()
                result.industry = industry
                if 'electric' in industry.lower():
                    result.utility_type = 'Electric'
                elif 'gas' in industry.lower():
                    result.utility_type = 'Gas'
                elif 'water' in industry.lower():
                    result.utility_type = 'Water'
                elif 'telecom' in industry.lower():
                    result.utility_type = 'Telephone'

            # Fallback to docket number for utility type
            if not result.utility_type:
                sector_match = re.search(r'-([EGWCM])-', docket_number.upper())
                if sector_match:
                    sector_map = {'E': 'Electric', 'G': 'Gas', 'W': 'Water', 'C': 'Telephone', 'M': 'Other'}
                    result.utility_type = sector_map.get(sector_match.group(1), 'Other')

            # Extract Company/Organization
            company_match = re.search(r'Company/Organization[:\s]*\n?([^\n\t]+)', text)
            if company_match:
                company = company_match.group(1).strip()
                if company and len(company) > 2:
                    result.utility_name = company
                    result.filing_party = company

            # Extract Matter Type (docket type)
            type_match = re.search(r'Matter Type[:\s]*(\w+)', text)
            if type_match:
                result.docket_type = type_match.group(1).strip()

            # Extract Matter Subtype
            subtype_match = re.search(r'Matter Subtype[:\s]*([^\n\t]+)', text)
            if subtype_match:
                result.sub_type = subtype_match.group(1).strip()

            # Extract Title of Matter/Case
            title_match = re.search(r'Title of Matter/Case[:\s]*([^\n\t]+?)(?:Expand|Related|$)', text)
            if title_match:
                title = title_match.group(1).strip()
                if title and len(title) > 3:
                    result.title = title[:500]

            # If no title, try to get from document titles
            if not result.title:
                doc_title_match = re.search(r'Document Title\s+.*?\n.*?\n.*?([A-Z][^\n]{10,200})', text, re.DOTALL)
                if doc_title_match:
                    result.title = doc_title_match.group(1).strip()[:500]

            # Extract filing date from first document
            date_match = re.search(r'\d{1,2}/\d{1,2}/\d{4}', text)
            if date_match:
                result.filing_date = self._parse_date(date_match.group(0))

            return result

        except Exception as e:
            result.error = f"NY scrape error: {str(e)}"
            return result

    async def _scrape_california_playwright(self, page, docket_number: str, result: ScrapedDocket) -> ScrapedDocket:
        """Scrape California PUC using Playwright via search form."""
        # CA format: X.YY-MM-NNN (e.g., A.24-07-003)
        # The CPUC uses an Oracle APEX application - need to use search form

        search_url = "https://apps.cpuc.ca.gov/apex/f?p=401:1"
        result.source_url = search_url

        try:
            await page.goto(search_url, timeout=30000)
            await asyncio.sleep(2)

            # Fill the proceeding number search field
            await page.fill('#P1_PROCEEDING_NUM', docket_number)
            await asyncio.sleep(1)

            # Click search button
            await page.click('#P1_SEARCH')
            await asyncio.sleep(4)

            text = await page.inner_text("body")

            # Check if results found - looking for the docket in results
            docket_clean = docket_number.replace('.', '').replace('-', '').upper()
            if "0 of 0" in text or "No data found" in text:
                result.found = False
                result.error = "Proceeding not found"
                return result

            if docket_clean not in text.replace('.', '').replace('-', '').upper():
                result.found = False
                result.error = "Proceeding not found"
                return result

            result.found = True

            # Extract data from search results table
            # Format: A2407003\nACTIVE\tJuly 08, 2024\tFiler\tDescription\tAssignment

            # Extract status (ACTIVE, CLOSED, REOPENED)
            status_match = re.search(rf'{docket_clean}\s*(ACTIVE|CLOSED|REOPENED)', text, re.IGNORECASE)
            if status_match:
                result.status = status_match.group(1).lower()

            # Extract filing date (format: "July 08, 2024" or similar)
            date_match = re.search(rf'{docket_clean}\s*(?:ACTIVE|CLOSED|REOPENED)?\s+([A-Za-z]+\s+\d{{1,2}},\s+\d{{4}})', text)
            if date_match:
                result.filing_date = self._parse_date(date_match.group(1))

            # Extract filer/company (after date)
            filer_match = re.search(rf'{docket_clean}.*?(?:ACTIVE|CLOSED|REOPENED)?\s+[A-Za-z]+\s+\d{{1,2}},\s+\d{{4}}\s+([^\t\n]+?)(?:\t|In the Matter)', text, re.DOTALL)
            if filer_match:
                filer = filer_match.group(1).strip()
                if filer and len(filer) < 200:
                    result.filing_party = filer
                    result.utility_name = filer

            # Extract description (title) - "In the Matter of..." text
            desc_match = re.search(r'In the Matter of[^\t\n]{10,500}', text, re.DOTALL)
            if desc_match:
                result.title = desc_match.group(0).strip()[:500]

            # Extract docket type from prefix
            type_match = re.match(r'^([ARCI])\.', docket_number.upper())
            if type_match:
                type_map = {
                    'A': 'Application',
                    'R': 'Rulemaking',
                    'C': 'Complaint',
                    'I': 'Investigation'
                }
                result.docket_type = type_map.get(type_match.group(1))

            # Infer utility type from title/description
            title_lower = (result.title or '').lower()
            if 'water' in title_lower:
                result.utility_type = 'Water'
            elif 'electric' in title_lower or 'power' in title_lower:
                result.utility_type = 'Electric'
            elif 'gas' in title_lower:
                result.utility_type = 'Gas'
            elif 'telecom' in title_lower or 'communication' in title_lower:
                result.utility_type = 'Telephone'

            return result

        except Exception as e:
            result.error = f"CA scrape error: {str(e)}"
            return result

    async def _scrape_arizona_playwright(self, page, docket_number: str, result: ScrapedDocket) -> ScrapedDocket:
        """Scrape Arizona Corporation Commission eDocket using Playwright.

        AZ uses an Angular SPA that requires search-based navigation.
        URL: https://edocket.azcc.gov/
        """
        result.source_url = f"https://edocket.azcc.gov/search/docket-search?docket={docket_number}"

        try:
            # Go to eDocket homepage
            await page.goto("https://edocket.azcc.gov/", timeout=30000)
            await asyncio.sleep(2)

            # Use quick search to find docket
            search_input = await page.query_selector("#quickSearchInput")
            if not search_input:
                result.error = "Could not find search input on Arizona eDocket"
                return result

            await search_input.fill(docket_number)
            await page.keyboard.press("Enter")
            await asyncio.sleep(5)

            # Update source URL to actual page
            result.source_url = page.url

            # Get page content
            text = await page.inner_text("body")

            # Check if docket was found
            if "No results found" in text or docket_number not in text:
                result.found = False
                result.error = "Docket not found"
                return result

            result.found = True

            # Extract Company Name
            company_match = re.search(r'Company Name\s*([^\n]+)', text)
            if company_match:
                result.utility_name = company_match.group(1).strip()

            # Extract Docket Type (utility type)
            type_match = re.search(r'Docket Type\s*([^\n]+)', text)
            if type_match:
                docket_type = type_match.group(1).strip().lower()
                if 'electric' in docket_type:
                    result.utility_type = 'Electric'
                elif 'gas' in docket_type:
                    result.utility_type = 'Gas'
                elif 'water' in docket_type or 'sewer' in docket_type:
                    result.utility_type = 'Water'
                elif 'telecom' in docket_type or 'telephone' in docket_type:
                    result.utility_type = 'Telephone'

            # Extract Case Type
            case_match = re.search(r'Case Type\s*([^\n]+)', text)
            if case_match:
                result.docket_type = case_match.group(1).strip()

            # Extract Status
            status_match = re.search(r'Docket Status\s*([^\n]+)', text)
            if status_match:
                status = status_match.group(1).strip().lower()
                if 'open' in status or 'active' in status or 'pending' in status or 'compliance' in status:
                    result.status = 'open'
                elif 'closed' in status:
                    result.status = 'closed'
                else:
                    result.status = status[:50]

            # Extract Filed Date
            date_match = re.search(r'Filed Date\s*(\d{2}/\d{2}/\d{4})', text)
            if date_match:
                result.filing_date = self._parse_date(date_match.group(1))

            # Extract Description as title
            desc_match = re.search(r'Description\s*(.+?)(?=Year Matter|Special Instructions|$)', text, re.DOTALL)
            if desc_match:
                description = desc_match.group(1).strip()
                if len(description) > 10:
                    result.title = description[:500]

            # If no description, create title from company and case type
            if not result.title and result.utility_name:
                result.title = f"{result.utility_name} - {result.docket_type or 'Case'}"

            return result

        except Exception as e:
            result.error = f"AZ scrape error: {str(e)}"
            return result

    def _parse_pennsylvania(self, html: str, result: ScrapedDocket, config: Dict) -> ScrapedDocket:
        """Parse Pennsylvania PUC docket page."""
        # PA format: X-YYYY-NNNNNNN (e.g., R-2025-3057164)
        if result.docket_number not in html:
            result.found = False
            result.error = "Docket not found"
            return result

        result.found = True

        # Extract title
        match = re.search(r'<h1[^>]*>([^<]+)</h1>', html)
        if match:
            result.title = match.group(1).strip()

        # Extract docket type from prefix (R=Rate Case, C=Complaint, M=Merger, P=Petition)
        type_match = re.match(r'^([RCMP])-', result.docket_number.upper())
        if type_match:
            type_map = {'R': 'Rate Case', 'C': 'Complaint', 'M': 'Merger', 'P': 'Petition'}
            result.docket_type = type_map.get(type_match.group(1))

        # Extract status
        status_match = re.search(r'Status[:\s]*([^<\n]+)', html, re.IGNORECASE)
        if status_match:
            result.status = status_match.group(1).strip().lower()

        # Extract filing date
        date_match = re.search(r'Filed[:\s]*(\d{1,2}/\d{1,2}/\d{4})', html)
        if date_match:
            result.filing_date = self._parse_date(date_match.group(1))

        return result

    def _parse_newjersey(self, html: str, result: ScrapedDocket, config: Dict) -> ScrapedDocket:
        """Parse New Jersey BPU docket page."""
        # NJ format: XXYYMMNNNNN (e.g., ER25040190)
        if result.docket_number not in html:
            result.found = False
            result.error = "Docket not found"
            return result

        result.found = True

        # Extract title
        match = re.search(r'<h1[^>]*>([^<]+)</h1>|Matter Name[:\s]*([^<\n]+)', html, re.IGNORECASE)
        if match:
            result.title = (match.group(1) or match.group(2)).strip()

        # Parse NJ docket format: XXYYMMNNNNN
        # XX = sector (E=Electric, G=Gas, W=Water, A=Admin)
        # R/O suffix = Rate case or Other
        nj_match = re.match(r'^([EGWA])([RO])?(\d{2})(\d{2})(\d+)', result.docket_number.upper())
        if nj_match:
            sector = nj_match.group(1)
            case_type = nj_match.group(2)
            sector_map = {'E': 'Electric', 'G': 'Gas', 'W': 'Water', 'A': 'Other'}
            result.utility_type = sector_map.get(sector)
            if case_type == 'R':
                result.docket_type = 'Rate Case'

        return result

    def _parse_washington(self, html: str, result: ScrapedDocket, config: Dict) -> ScrapedDocket:
        """Parse Washington UTC docket page."""
        # Check if docket exists by looking for docket number in page
        if result.docket_number not in html and result.docket_number.replace('-', '') not in html:
            result.found = False
            result.error = "Docket not found"
            return result

        result.found = True

        # Extract Company from table
        company_match = re.search(r'<th>Company</th>\s*<td>\s*([^<]+)', html, re.DOTALL)
        if company_match:
            result.utility_name = company_match.group(1).strip()

        # Extract Filing Type as title
        type_match = re.search(r'<th>Filing Type</th>\s*<td>([^<]+)</td>', html, re.DOTALL)
        if type_match:
            result.docket_type = type_match.group(1).strip()
            result.title = f"{result.utility_name or 'Unknown'} - {result.docket_type}"

        # Extract Industry
        industry_match = re.search(r'<th>Industry \(Code\)</th>\s*<td>([^<]+)</td>', html, re.DOTALL)
        if industry_match:
            industry = industry_match.group(1).strip().lower()
            if 'electric' in industry:
                result.utility_type = 'Electric'
            elif 'gas' in industry:
                result.utility_type = 'Gas'
            elif 'water' in industry:
                result.utility_type = 'Water'
            elif 'telecom' in industry or 'telephone' in industry:
                result.utility_type = 'Telephone'

        # Extract Status
        status_match = re.search(r'<th>Status</th>\s*<td>([^<]+)</td>', html, re.DOTALL)
        if status_match:
            status = status_match.group(1).strip().lower()
            result.status = 'open' if 'open' in status or 'pending' in status else 'closed'

        # Extract Filed Date
        date_match = re.search(r'<th>Filed Date</th>\s*<td>(\d{2}/\d{2}/\d{4})</td>', html, re.DOTALL)
        if date_match:
            result.filing_date = self._parse_date(date_match.group(1))

        return result

    def _parse_colorado(self, html: str, result: ScrapedDocket, config: Dict) -> ScrapedDocket:
        """Parse Colorado PUC docket page."""
        # CO format: YYX-NNNN[XX] (e.g., 21A-0625EG)
        if result.docket_number not in html:
            result.found = False
            result.error = "Docket not found"
            return result

        result.found = True

        # Extract title
        match = re.search(r'<h1[^>]*>([^<]+)</h1>|Case Title[:\s]*([^<\n]+)', html, re.IGNORECASE)
        if match:
            result.title = (match.group(1) or match.group(2)).strip()

        # Parse CO docket format: YYX-NNNN or YYX-NNNNXX
        # X = case type (A=Application, R=Rulemaking, etc.)
        # XX suffix = sector (EG=Electric/Gas, E=Electric, G=Gas)
        co_match = re.match(r'^(\d{2})([A-Z])-(\d+)([EG]{1,2})?', result.docket_number.upper())
        if co_match:
            case_type = co_match.group(2)
            suffix = co_match.group(4)
            type_map = {'A': 'Application', 'R': 'Rulemaking', 'I': 'Investigation', 'C': 'Complaint'}
            result.docket_type = type_map.get(case_type)
            if suffix:
                if 'E' in suffix:
                    result.utility_type = 'Electric'
                elif 'G' in suffix:
                    result.utility_type = 'Gas'

        return result

    def _parse_northcarolina(self, html: str, result: ScrapedDocket, config: Dict) -> ScrapedDocket:
        """Parse North Carolina UC docket page."""
        # NC format: X-N,SUB NNN (e.g., E-2,SUB 1300)
        if result.docket_number not in html and result.docket_number.replace(' ', '') not in html:
            result.found = False
            result.error = "Docket not found"
            return result

        result.found = True

        # Extract title
        match = re.search(r'<h1[^>]*>([^<]+)</h1>|Caption[:\s]*([^<\n]+)', html, re.IGNORECASE)
        if match:
            result.title = (match.group(1) or match.group(2)).strip()

        # Extract utility type from prefix (E=Electric, G=Gas, W=Water, T=Telecom)
        nc_match = re.match(r'^([EGWT])-', result.docket_number.upper())
        if nc_match:
            sector = nc_match.group(1)
            sector_map = {'E': 'Electric', 'G': 'Gas', 'W': 'Water', 'T': 'Telephone'}
            result.utility_type = sector_map.get(sector)

        return result

    def _parse_southcarolina(self, html: str, result: ScrapedDocket, config: Dict) -> ScrapedDocket:
        """Parse South Carolina PSC docket page."""
        # SC format: YYYY-NNN-X (e.g., 2023-189-E)
        if result.docket_number not in html:
            result.found = False
            result.error = "Docket not found"
            return result

        result.found = True

        # Extract title
        match = re.search(r'<h1[^>]*>([^<]+)</h1>|Case Title[:\s]*([^<\n]+)', html, re.IGNORECASE)
        if match:
            result.title = (match.group(1) or match.group(2)).strip()

        # Extract utility type from suffix (E=Electric, G=Gas, W=Water, C=Telecom, T=Transportation)
        sc_match = re.search(r'-([EGWCT])$', result.docket_number.upper())
        if sc_match:
            suffix = sc_match.group(1)
            sector_map = {'E': 'Electric', 'G': 'Gas', 'W': 'Water', 'C': 'Telephone', 'T': 'Transportation'}
            result.utility_type = sector_map.get(suffix)

        return result

    def _parse_missouri(self, html: str, result: ScrapedDocket, config: Dict) -> ScrapedDocket:
        """Parse Missouri PSC EFIS docket page."""
        # Check if docket exists - title format is "Docket Sheet - XX-YYYY-NNNN"
        if result.docket_number not in html:
            result.found = False
            return result

        result.found = True

        # Extract title from page title: "Docket Sheet - TO-2024-0033 - EFIS"
        title_match = re.search(r'<title>Docket Sheet - ([^<]+) - EFIS</title>', html)
        if title_match:
            result.title = f"Case {title_match.group(1).strip()}"

        # Extract status: "Closed (4/21/2024)" or "Open"
        status_match = re.search(r'Status\s*</div>\s*<div[^>]*>\s*(\w+)', html, re.DOTALL)
        if status_match:
            status = status_match.group(1).lower()
            result.status = 'open' if 'open' in status else 'closed' if 'closed' in status else status

        # Extract utility type
        utility_match = re.search(r'Utility Type\s*</div>\s*<div[^>]*>([^<]+)</div>', html, re.DOTALL)
        if utility_match:
            utility_type = utility_match.group(1).strip()
            type_map = {
                'electric': 'Electric',
                'gas': 'Gas',
                'telephone': 'Telephone',
                'water': 'Water',
                'sewer': 'Water',
            }
            for key, value in type_map.items():
                if key in utility_type.lower():
                    result.utility_type = value
                    break

        # Extract company name from link
        company_match = re.search(r'/Company/Display/\d+[^>]*>([^<]+)</a>', html)
        if company_match:
            result.utility_name = company_match.group(1).strip()

        # Extract case type from docket number prefix
        # MO format: XX-YYYY-NNNN where XX is type code
        type_code_match = re.match(r'^([A-Z]{2})-', result.docket_number)
        if type_code_match:
            type_code = type_code_match.group(1)
            type_map = {
                'ER': 'Rate Case',
                'EO': 'Other Electric',
                'EA': 'Application',
                'EC': 'Complaint',
                'GR': 'Rate Case',
                'GO': 'Other Gas',
                'TO': 'Other Telephone',
                'TR': 'Rate Case',
                'WR': 'Rate Case',
                'WO': 'Other Water',
            }
            result.docket_type = type_map.get(type_code, type_code)

        return result

    def _parse_generic(self, html: str, result: ScrapedDocket, config: Dict) -> ScrapedDocket:
        """Generic parsing for unconfigured states."""
        if result.docket_number not in html:
            result.found = False
            return result

        result.found = True

        # Try common patterns
        # Title in h1
        match = re.search(r'<h1[^>]*>([^<]+)</h1>', html)
        if match:
            result.title = match.group(1).strip()

        # Status
        match = re.search(r'status[:\s]*([^<\n]+)', html, re.IGNORECASE)
        if match:
            result.status = match.group(1).strip()[:50]

        return result

    def _parse_date(self, date_str: str) -> Optional[date]:
        """Parse various date formats."""
        if not date_str:
            return None

        date_str = date_str.strip()

        formats = [
            "%m/%d/%Y",
            "%Y-%m-%d",
            "%B %d, %Y",
            "%b %d, %Y",
            "%m-%d-%Y",
            "%d/%m/%Y",
        ]

        for fmt in formats:
            try:
                return datetime.strptime(date_str, fmt).date()
            except ValueError:
                continue

        return None

    async def verify_and_save(self, state_code: str, docket_number: str,
                              extraction_id: Optional[int] = None) -> ScrapedDocket:
        """
        Verify a docket and save the results to the database.

        Creates or updates the known_dockets record and logs to docket_verifications.
        """
        result = await self.scrape_docket(state_code, docket_number)

        # Save verification record
        self.db.execute(text("""
            INSERT INTO docket_verifications
            (docket_id, extraction_id, state_code, docket_number, verified, source_url,
             scraped_title, scraped_utility_type, scraped_company, scraped_filing_date,
             scraped_status, scraped_metadata, verified_at, error_message)
            VALUES
            (NULL, :extraction_id, :state_code, :docket_number, :verified, :source_url,
             :title, :utility_type, :company, :filing_date, :status, :metadata,
             CURRENT_TIMESTAMP, :error)
        """), {
            "extraction_id": extraction_id,
            "state_code": state_code,
            "docket_number": docket_number,
            "verified": result.found,
            "source_url": result.source_url,
            "title": result.title,
            "utility_type": result.utility_type,
            "company": result.utility_name or result.filing_party,
            "filing_date": result.filing_date,
            "status": result.status,
            "metadata": "{}",  # JSON
            "error": result.error
        })
        self.db.commit()

        # If found, create or update known_docket
        if result.found:
            normalized_id = f"{state_code}-{docket_number}"

            existing = self.db.execute(text(
                "SELECT id FROM known_dockets WHERE normalized_id = :nid"
            ), {"nid": normalized_id}).fetchone()

            if existing:
                # Update existing
                self.db.execute(text("""
                    UPDATE known_dockets SET
                        title = COALESCE(:title, title),
                        utility_type = COALESCE(:utility_type, utility_type),
                        industry = COALESCE(:industry, industry),
                        utility_name = COALESCE(:utility_name, utility_name),
                        filing_party = COALESCE(:filing_party, filing_party),
                        filing_date = COALESCE(:filing_date, filing_date),
                        status = COALESCE(:status, status),
                        source_url = :source_url,
                        verification_status = 'verified',
                        verified_at = CURRENT_TIMESTAMP,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE normalized_id = :nid
                """), {
                    "nid": normalized_id,
                    "title": result.title,
                    "utility_type": result.utility_type,
                    "industry": result.industry,
                    "utility_name": result.utility_name,
                    "filing_party": result.filing_party,
                    "filing_date": result.filing_date,
                    "status": result.status,
                    "source_url": result.source_url
                })
            else:
                # Create new
                self.db.execute(text("""
                    INSERT INTO known_dockets
                    (state_code, docket_number, normalized_id, title, utility_type, industry,
                     utility_name, filing_party, filing_date, status, source_url,
                     verification_status, verified_at, scraped_at, updated_at)
                    VALUES
                    (:state_code, :docket_number, :nid, :title, :utility_type, :industry,
                     :utility_name, :filing_party, :filing_date, :status, :source_url,
                     'verified', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """), {
                    "state_code": state_code,
                    "docket_number": docket_number,
                    "nid": normalized_id,
                    "title": result.title,
                    "utility_type": result.utility_type,
                    "industry": result.industry,
                    "utility_name": result.utility_name,
                    "filing_party": result.filing_party,
                    "filing_date": result.filing_date,
                    "status": result.status,
                    "source_url": result.source_url
                })

            self.db.commit()

        return result
