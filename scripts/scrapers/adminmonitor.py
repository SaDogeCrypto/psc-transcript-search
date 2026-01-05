#!/usr/bin/env python3
"""
AdminMonitor Scraper

Scrapes hearing videos from AdminMonitor.com for state PUCs/PSCs.
Requires browser-like User-Agent header to avoid 403 errors.

Supported states:
- California CPUC: https://www.adminmonitor.com/ca/cpuc/
- Texas PUCT: https://www.adminmonitor.com/tx/puct/
"""

import re
import logging
from datetime import datetime, date
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# Browser-like headers to avoid 403 blocks
DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}


@dataclass
class AdminMonitorMeeting:
    """Represents a meeting scraped from AdminMonitor."""
    external_id: str
    title: str
    meeting_type: str
    meeting_date: date
    source_url: str
    video_url: Optional[str] = None
    duration_seconds: Optional[int] = None
    description: Optional[str] = None


class AdminMonitorScraper:
    """Scraper for AdminMonitor.com hearing archives."""

    BASE_URL = "https://www.adminmonitor.com"

    def __init__(self, state_code: str, agency_code: str, timeout: int = 30):
        """
        Initialize scraper for a specific state/agency.

        Args:
            state_code: Two-letter state code (e.g., 'ca', 'tx')
            agency_code: Agency identifier (e.g., 'cpuc', 'puct')
            timeout: Request timeout in seconds
        """
        self.state_code = state_code.lower()
        self.agency_code = agency_code.lower()
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)
        self.base_agency_url = f"{self.BASE_URL}/{self.state_code}/{self.agency_code}/"

    def _parse_date_from_url(self, url: str) -> Optional[date]:
        """Extract date from AdminMonitor URL path (e.g., /20251218/)."""
        match = re.search(r'/(\d{8})/?', url)
        if match:
            date_str = match.group(1)
            try:
                return datetime.strptime(date_str, "%Y%m%d").date()
            except ValueError:
                pass
        return None

    def _parse_meeting_type_from_url(self, url: str) -> str:
        """Extract meeting type from URL path."""
        # URL pattern: /{state}/{agency}/{meeting_type}/{date}/
        parts = url.rstrip('/').split('/')
        if len(parts) >= 2:
            meeting_type = parts[-2]
            # Convert snake_case to Title Case
            return meeting_type.replace('_', ' ').title()
        return "Meeting"

    def _generate_external_id(self, url: str) -> str:
        """Generate unique external ID from meeting URL."""
        # Extract path after base: /ca/cpuc/voting_meeting/20251218/ -> ca_cpuc_voting_meeting_20251218
        path = url.replace(self.BASE_URL, '').strip('/')
        return path.replace('/', '_')

    def fetch_meeting_list(self, direction: str = "Past Meetings") -> list[AdminMonitorMeeting]:
        """
        Fetch list of meetings from the agency page.

        Args:
            direction: "Past Meetings" or "Future Meetings"

        Returns:
            List of AdminMonitorMeeting objects
        """
        meetings = []

        try:
            # POST request to get meeting list
            response = self.session.post(
                self.base_agency_url,
                data={"dir": direction},
                timeout=self.timeout
            )
            response.raise_for_status()

            soup = BeautifulSoup(response.text, 'html.parser')

            # Find all meeting links in the listing
            # Pattern: <a href="/ca/cpuc/voting_meeting/20251218/">Voting Meeting</a>
            meeting_links = soup.find_all('a', href=re.compile(
                rf'^/{self.state_code}/{self.agency_code}/\w+/\d{{8}}/'
            ))

            seen_urls = set()
            for link in meeting_links:
                href = link.get('href', '')
                full_url = urljoin(self.BASE_URL, href)

                # Skip duplicates
                if full_url in seen_urls:
                    continue
                seen_urls.add(full_url)

                meeting_date = self._parse_date_from_url(href)
                meeting_type = self._parse_meeting_type_from_url(href)
                external_id = self._generate_external_id(href)

                # Title from link text, or construct from type + date
                title = link.get_text(strip=True)
                if meeting_date:
                    title = f"{title} - {meeting_date.strftime('%B %d, %Y')}"

                meetings.append(AdminMonitorMeeting(
                    external_id=external_id,
                    title=title,
                    meeting_type=meeting_type,
                    meeting_date=meeting_date,
                    source_url=full_url,
                ))

            logger.info(f"Found {len(meetings)} meetings from {self.base_agency_url}")

        except requests.RequestException as e:
            logger.error(f"Failed to fetch meeting list: {e}")
            raise

        return meetings

    def fetch_meeting_details(self, meeting: AdminMonitorMeeting) -> AdminMonitorMeeting:
        """
        Fetch detailed information for a single meeting, including video URL.

        Args:
            meeting: Meeting object with source_url set

        Returns:
            Updated meeting object with video_url and other details
        """
        try:
            response = self.session.get(meeting.source_url, timeout=self.timeout)
            response.raise_for_status()

            soup = BeautifulSoup(response.text, 'html.parser')

            # Find video source - AdminMonitor uses HLS streams
            # Pattern: <source src="https://...cloudfront.net/.../master.m3u8" type="application/x-mpegURL" />
            video_source = soup.find('source', type='application/x-mpegURL')
            if video_source:
                meeting.video_url = video_source.get('src')
            else:
                # Fallback: look for any video source
                video_source = soup.find('source', src=re.compile(r'\.m3u8'))
                if video_source:
                    meeting.video_url = video_source.get('src')

            # Try to extract description from page content
            content_div = soup.find('div', id='maincontent')
            if content_div:
                # Look for description paragraphs
                paragraphs = content_div.find_all('p')
                if paragraphs:
                    desc_parts = [p.get_text(strip=True) for p in paragraphs[:3]]
                    meeting.description = ' '.join(desc_parts)[:500]

            logger.debug(f"Fetched details for {meeting.external_id}: video_url={meeting.video_url}")

        except requests.RequestException as e:
            logger.warning(f"Failed to fetch meeting details for {meeting.source_url}: {e}")

        return meeting

    def scrape_all_meetings(self, include_future: bool = False, fetch_details: bool = True) -> list[AdminMonitorMeeting]:
        """
        Scrape all available meetings.

        Args:
            include_future: Whether to include future scheduled meetings
            fetch_details: Whether to fetch video URLs for each meeting

        Returns:
            List of AdminMonitorMeeting objects with full details
        """
        all_meetings = []

        # Fetch past meetings
        past_meetings = self.fetch_meeting_list("Past Meetings")
        all_meetings.extend(past_meetings)

        # Optionally fetch future meetings
        if include_future:
            future_meetings = self.fetch_meeting_list("Future Meetings")
            all_meetings.extend(future_meetings)

        # Fetch details (video URLs) for each meeting
        if fetch_details:
            for meeting in all_meetings:
                self.fetch_meeting_details(meeting)

        return all_meetings


# State/agency configuration for known AdminMonitor sources
ADMINMONITOR_SOURCES = {
    "ca_cpuc": {
        "state_code": "ca",
        "agency_code": "cpuc",
        "state_name": "California",
        "agency_name": "California Public Utilities Commission",
    },
    "tx_puct": {
        "state_code": "tx",
        "agency_code": "puct",
        "state_name": "Texas",
        "agency_name": "Public Utility Commission of Texas",
    },
}


def parse_adminmonitor_url(url: str) -> tuple[str, str]:
    """
    Parse AdminMonitor URL to extract state and agency codes.

    Args:
        url: Full AdminMonitor URL (e.g., https://www.adminmonitor.com/ca/cpuc/)

    Returns:
        Tuple of (state_code, agency_code)

    Raises:
        ValueError: If URL doesn't match expected pattern
    """
    match = re.search(r'adminmonitor\.com/(\w+)/(\w+)/?', url)
    if not match:
        raise ValueError(f"Invalid AdminMonitor URL: {url}")
    return match.group(1), match.group(2)


def create_scraper_from_url(url: str) -> AdminMonitorScraper:
    """Create a scraper instance from an AdminMonitor URL."""
    state_code, agency_code = parse_adminmonitor_url(url)
    return AdminMonitorScraper(state_code, agency_code)


if __name__ == "__main__":
    # Demo/test usage
    import argparse

    logging.basicConfig(level=logging.INFO)

    parser = argparse.ArgumentParser(description="Scrape AdminMonitor meetings")
    parser.add_argument("--state", default="ca", help="State code (e.g., ca, tx)")
    parser.add_argument("--agency", default="cpuc", help="Agency code (e.g., cpuc, puct)")
    parser.add_argument("--limit", type=int, default=5, help="Max meetings to fetch details for")
    args = parser.parse_args()

    scraper = AdminMonitorScraper(args.state, args.agency)

    print(f"\nScraping {args.state.upper()} {args.agency.upper()} from AdminMonitor...\n")

    meetings = scraper.fetch_meeting_list("Past Meetings")
    print(f"Found {len(meetings)} past meetings\n")

    # Fetch details for first N meetings
    for meeting in meetings[:args.limit]:
        scraper.fetch_meeting_details(meeting)
        print(f"  {meeting.meeting_date} | {meeting.meeting_type}")
        print(f"    Title: {meeting.title}")
        print(f"    URL: {meeting.source_url}")
        print(f"    Video: {meeting.video_url or 'N/A'}")
        print()
