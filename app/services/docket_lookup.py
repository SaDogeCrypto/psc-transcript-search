"""
Docket Lookup Service

Queries state PSC websites to verify docket numbers and retrieve metadata.
Used by smart extraction pipeline to validate new docket candidates.
"""

import re
import logging
import httpx
from typing import Optional, Dict, Any
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Timeout for HTTP requests
TIMEOUT = 10.0


@dataclass
class DocketLookupResult:
    """Result from looking up a docket on a state PSC website."""
    found: bool
    docket_number: str
    state_code: str
    title: Optional[str] = None
    company: Optional[str] = None
    filing_date: Optional[str] = None
    status: Optional[str] = None
    url: Optional[str] = None
    error: Optional[str] = None


# State PSC URL patterns
STATE_LOOKUP_URLS = {
    "GA": "https://psc.ga.gov/facts-advanced-search/docket/?docketId={docket}",
    "TX": "https://interchange.puc.texas.gov/search/filings/?UtilityType=A&ControlNumber={docket}&ItemMatch=Equal",
    "FL": "https://www.floridapsc.com/ClerkOffice/DocketFiling?docket={docket}",
    "OH": "https://dis.puc.state.oh.us/CaseRecord.aspx?CaseNo={docket}",
    "CA": "https://apps.cpuc.ca.gov/apex/f?p=401:56::::RP,57,RIR:P5_PROCEEDING_SELECT:{docket}",
}


async def lookup_docket(docket_number: str, state_code: str) -> DocketLookupResult:
    """
    Look up a docket number on the state's PSC website.

    Returns DocketLookupResult with found=True if the docket exists,
    along with any metadata we can extract.
    """
    state_code = state_code.upper()

    if state_code not in STATE_LOOKUP_URLS:
        return DocketLookupResult(
            found=False,
            docket_number=docket_number,
            state_code=state_code,
            error=f"No lookup URL configured for state {state_code}"
        )

    url = STATE_LOOKUP_URLS[state_code].format(docket=docket_number)

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=True) as client:
            response = await client.get(url)

            if response.status_code != 200:
                return DocketLookupResult(
                    found=False,
                    docket_number=docket_number,
                    state_code=state_code,
                    url=url,
                    error=f"HTTP {response.status_code}"
                )

            html = response.text

            # Parse based on state
            if state_code == "GA":
                return _parse_georgia_docket(html, docket_number, state_code, url)
            elif state_code == "TX":
                return _parse_texas_docket(html, docket_number, state_code, url)
            elif state_code == "FL":
                return _parse_florida_docket(html, docket_number, state_code, url)
            elif state_code == "OH":
                return _parse_ohio_docket(html, docket_number, state_code, url)
            else:
                # Generic check - just see if docket number appears on page
                if docket_number in html:
                    return DocketLookupResult(
                        found=True,
                        docket_number=docket_number,
                        state_code=state_code,
                        url=url
                    )
                return DocketLookupResult(
                    found=False,
                    docket_number=docket_number,
                    state_code=state_code,
                    url=url
                )

    except httpx.TimeoutException:
        return DocketLookupResult(
            found=False,
            docket_number=docket_number,
            state_code=state_code,
            url=url,
            error="Timeout"
        )
    except Exception as e:
        logger.warning(f"Docket lookup error for {state_code}-{docket_number}: {e}")
        return DocketLookupResult(
            found=False,
            docket_number=docket_number,
            state_code=state_code,
            url=url,
            error=str(e)
        )


def lookup_docket_sync(docket_number: str, state_code: str) -> DocketLookupResult:
    """Synchronous version of lookup_docket."""
    import asyncio
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    return loop.run_until_complete(lookup_docket(docket_number, state_code))


def _parse_georgia_docket(html: str, docket_number: str, state_code: str, url: str) -> DocketLookupResult:
    """Parse Georgia PSC docket page."""
    # Check if docket exists - look for the docket number in the page
    if f"#{docket_number}" not in html and f"Docket {docket_number}" not in html:
        # Check for "no results" or error messages
        if "not found" in html.lower() or "no docket" in html.lower():
            return DocketLookupResult(
                found=False,
                docket_number=docket_number,
                state_code=state_code,
                url=url
            )

    # Extract title - look for common patterns
    title = None
    title_patterns = [
        r'<h1[^>]*>([^<]+)</h1>',
        r'<title>([^<]+)</title>',
        r'Description[:\s]*([^<\n]+)',
        r'Subject[:\s]*([^<\n]+)',
    ]
    for pattern in title_patterns:
        match = re.search(pattern, html, re.IGNORECASE)
        if match:
            title = match.group(1).strip()
            # Clean up title
            title = re.sub(r'\s+', ' ', title)
            if docket_number not in title.lower() and len(title) > 10:
                break
            title = None

    # Extract company name
    company = None
    company_patterns = [
        r'(?:Company|Utility|Applicant)[:\s]*([^<\n]+)',
        r'Georgia\s+Power\s+Company',
        r'Atlanta\s+Gas\s+Light',
    ]
    for pattern in company_patterns:
        match = re.search(pattern, html, re.IGNORECASE)
        if match:
            company = match.group(1).strip() if match.lastindex else match.group(0)
            break

    # Extract filing date
    filing_date = None
    date_match = re.search(r'(\d{1,2}/\d{1,2}/\d{4})', html)
    if date_match:
        filing_date = date_match.group(1)

    return DocketLookupResult(
        found=True,
        docket_number=docket_number,
        state_code=state_code,
        title=title,
        company=company,
        filing_date=filing_date,
        url=url
    )


def _parse_texas_docket(html: str, docket_number: str, state_code: str, url: str) -> DocketLookupResult:
    """Parse Texas PUC docket page."""
    # Check if we got results
    if "No filings found" in html or "0 results" in html.lower():
        return DocketLookupResult(
            found=False,
            docket_number=docket_number,
            state_code=state_code,
            url=url
        )

    # Look for the control number in results
    if docket_number not in html:
        return DocketLookupResult(
            found=False,
            docket_number=docket_number,
            state_code=state_code,
            url=url
        )

    # Extract title/description
    title = None
    title_match = re.search(rf'{docket_number}[^<]*<[^>]*>([^<]+)', html)
    if title_match:
        title = title_match.group(1).strip()

    return DocketLookupResult(
        found=True,
        docket_number=docket_number,
        state_code=state_code,
        title=title,
        url=url
    )


def _parse_florida_docket(html: str, docket_number: str, state_code: str, url: str) -> DocketLookupResult:
    """Parse Florida PSC docket page."""
    # Florida format: YYYYNNNN-XX
    if "Docket not found" in html or "No records" in html:
        return DocketLookupResult(
            found=False,
            docket_number=docket_number,
            state_code=state_code,
            url=url
        )

    # Extract title
    title = None
    title_match = re.search(r'<h2[^>]*>([^<]+)</h2>', html)
    if title_match:
        title = title_match.group(1).strip()

    # Extract company
    company = None
    company_match = re.search(r'(?:Utility|Company):\s*([^<\n]+)', html)
    if company_match:
        company = company_match.group(1).strip()

    return DocketLookupResult(
        found=True,
        docket_number=docket_number,
        state_code=state_code,
        title=title,
        company=company,
        url=url
    )


def _parse_ohio_docket(html: str, docket_number: str, state_code: str, url: str) -> DocketLookupResult:
    """Parse Ohio PUC docket page."""
    if "Case not found" in html or "Invalid case" in html.lower():
        return DocketLookupResult(
            found=False,
            docket_number=docket_number,
            state_code=state_code,
            url=url
        )

    # Extract title
    title = None
    title_match = re.search(r'Case\s+Title[:\s]*([^<\n]+)', html, re.IGNORECASE)
    if title_match:
        title = title_match.group(1).strip()

    # Extract company
    company = None
    company_match = re.search(r'(?:Company|Utility)[:\s]*([^<\n]+)', html, re.IGNORECASE)
    if company_match:
        company = company_match.group(1).strip()

    return DocketLookupResult(
        found=True,
        docket_number=docket_number,
        state_code=state_code,
        title=title,
        company=company,
        url=url
    )


# Batch lookup for multiple dockets
async def lookup_dockets_batch(
    dockets: list[tuple[str, str]]  # List of (docket_number, state_code)
) -> list[DocketLookupResult]:
    """Look up multiple dockets concurrently."""
    import asyncio
    tasks = [lookup_docket(d, s) for d, s in dockets]
    return await asyncio.gather(*tasks)
