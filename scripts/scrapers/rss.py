#!/usr/bin/env python3
"""
RSS Feed Scraper

Scrapes hearing videos from RSS feeds for state PUCs/PSCs.
Supports various RSS formats including:
- Granicus (Arizona, etc.)
- The Florida Channel
- Standard RSS 2.0 / Atom feeds
"""

import re
import hashlib
import logging
from datetime import datetime, date
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse, urljoin
import xml.etree.ElementTree as ET

import requests

logger = logging.getLogger(__name__)

# Standard headers
DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/rss+xml, application/xml, text/xml, */*",
    "Accept-Language": "en-US,en;q=0.5",
}

# Common RSS namespaces
NAMESPACES = {
    'atom': 'http://www.w3.org/2005/Atom',
    'dc': 'http://purl.org/dc/elements/1.1/',
    'content': 'http://purl.org/rss/1.0/modules/content/',
    'media': 'http://search.yahoo.com/mrss/',
    'granicus': 'http://granicus.com/rss/',
}


@dataclass
class RSSItem:
    """Represents an item scraped from an RSS feed."""
    external_id: str
    title: str
    link: str
    pub_date: Optional[date] = None
    description: Optional[str] = None
    video_url: Optional[str] = None
    duration_seconds: Optional[int] = None
    categories: list = None

    def __post_init__(self):
        if self.categories is None:
            self.categories = []


class RSSFeedScraper:
    """Scraper for RSS/Atom feeds."""

    def __init__(self, feed_url: str, timeout: int = 30):
        """
        Initialize RSS scraper.

        Args:
            feed_url: URL of the RSS/Atom feed
            timeout: Request timeout in seconds
        """
        self.feed_url = feed_url
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)
        self._feed_type = None

    def _generate_external_id(self, item_data: dict) -> str:
        """Generate unique external ID for an RSS item."""
        # Use guid if available
        guid = item_data.get('guid')
        if guid:
            # Hash long guids
            if len(guid) > 50:
                return f"rss_{hashlib.md5(guid.encode()).hexdigest()[:16]}"
            # Clean up guid for use as ID
            clean_guid = re.sub(r'[^a-zA-Z0-9_-]', '_', guid)
            return f"rss_{clean_guid[:50]}"

        # Fall back to hashing link + title
        content = f"{item_data.get('link', '')}{item_data.get('title', '')}"
        return f"rss_{hashlib.md5(content.encode()).hexdigest()[:16]}"

    def _parse_date(self, date_str: str) -> Optional[date]:
        """Parse various date formats from RSS feeds."""
        if not date_str:
            return None

        date_str = date_str.strip()

        # Common RSS date formats
        formats = [
            "%a, %d %b %Y %H:%M:%S %z",      # RFC 822 (standard RSS)
            "%a, %d %b %Y %H:%M:%S %Z",      # RFC 822 with timezone name
            "%Y-%m-%dT%H:%M:%S%z",           # ISO 8601
            "%Y-%m-%dT%H:%M:%SZ",            # ISO 8601 UTC
            "%Y-%m-%d %H:%M:%S",             # Simple datetime
            "%Y-%m-%d",                       # Simple date
            "%m/%d/%Y",                       # US format
            "%d %b %Y",                       # Day Month Year
        ]

        # Handle timezone offset without colon (e.g., +0000)
        date_str = re.sub(r'([+-]\d{2})(\d{2})$', r'\1:\2', date_str)

        for fmt in formats:
            try:
                dt = datetime.strptime(date_str, fmt)
                return dt.date()
            except ValueError:
                continue

        # Try parsing just the date portion
        match = re.search(r'(\d{4})-(\d{2})-(\d{2})', date_str)
        if match:
            try:
                return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
            except ValueError:
                pass

        logger.warning(f"Could not parse date: {date_str}")
        return None

    def _parse_duration(self, duration_str: str) -> Optional[int]:
        """Parse duration string to seconds."""
        if not duration_str:
            return None

        # Try HH:MM:SS format
        match = re.match(r'(\d+):(\d+):(\d+)', duration_str)
        if match:
            hours, minutes, seconds = map(int, match.groups())
            return hours * 3600 + minutes * 60 + seconds

        # Try MM:SS format
        match = re.match(r'(\d+):(\d+)', duration_str)
        if match:
            minutes, seconds = map(int, match.groups())
            return minutes * 60 + seconds

        # Try plain seconds
        match = re.match(r'(\d+)', duration_str)
        if match:
            return int(match.group(1))

        return None

    def _get_text(self, element: ET.Element, path: str, namespaces: dict = None) -> Optional[str]:
        """Safely get text from an XML element."""
        if namespaces is None:
            namespaces = NAMESPACES

        # Try with namespaces first
        for prefix, uri in namespaces.items():
            try:
                child = element.find(path.replace(f'{prefix}:', f'{{{uri}}}'), namespaces)
                if child is not None and child.text:
                    return child.text.strip()
            except:
                pass

        # Try without namespaces
        child = element.find(path.split(':')[-1])
        if child is not None and child.text:
            return child.text.strip()

        return None

    def _parse_rss_item(self, item: ET.Element) -> Optional[RSSItem]:
        """Parse an RSS 2.0 item element."""
        title = self._get_text(item, 'title')
        if not title:
            return None

        link = self._get_text(item, 'link')
        guid = self._get_text(item, 'guid') or link
        pub_date_str = self._get_text(item, 'pubDate')
        description = self._get_text(item, 'description')

        # Get categories
        categories = []
        for cat in item.findall('category'):
            if cat.text:
                categories.append(cat.text.strip())

        # Look for video URL in enclosure or media:content
        video_url = None
        duration = None

        enclosure = item.find('enclosure')
        if enclosure is not None:
            enc_type = enclosure.get('type', '')
            if 'video' in enc_type or 'audio' in enc_type:
                video_url = enclosure.get('url')

        # Check media:content
        for ns_uri in [NAMESPACES.get('media', ''), '']:
            media_tag = f'{{{ns_uri}}}content' if ns_uri else 'media:content'
            media = item.find(media_tag)
            if media is not None:
                video_url = video_url or media.get('url')
                duration = self._parse_duration(media.get('duration'))

        # Check for Granicus-specific elements
        granicus_ns = NAMESPACES.get('granicus', '')
        if granicus_ns:
            clip = item.find(f'{{{granicus_ns}}}clip')
            if clip is not None:
                video_url = video_url or clip.get('url')
                duration = duration or self._parse_duration(clip.get('duration'))

        item_data = {
            'guid': guid,
            'link': link,
            'title': title,
        }

        return RSSItem(
            external_id=self._generate_external_id(item_data),
            title=title,
            link=link or '',
            pub_date=self._parse_date(pub_date_str),
            description=description[:1000] if description else None,
            video_url=video_url,
            duration_seconds=duration,
            categories=categories,
        )

    def _parse_atom_entry(self, entry: ET.Element) -> Optional[RSSItem]:
        """Parse an Atom entry element."""
        atom_ns = NAMESPACES['atom']

        title_el = entry.find(f'{{{atom_ns}}}title')
        title = title_el.text.strip() if title_el is not None and title_el.text else None
        if not title:
            return None

        # Get link (prefer alternate, then self)
        link = None
        for link_el in entry.findall(f'{{{atom_ns}}}link'):
            rel = link_el.get('rel', 'alternate')
            if rel == 'alternate':
                link = link_el.get('href')
                break
            elif rel == 'self' and not link:
                link = link_el.get('href')

        # Get ID
        id_el = entry.find(f'{{{atom_ns}}}id')
        guid = id_el.text.strip() if id_el is not None and id_el.text else link

        # Get published/updated date
        pub_date_str = None
        for date_tag in ['published', 'updated']:
            date_el = entry.find(f'{{{atom_ns}}}{date_tag}')
            if date_el is not None and date_el.text:
                pub_date_str = date_el.text.strip()
                break

        # Get summary/content
        description = None
        for content_tag in ['summary', 'content']:
            content_el = entry.find(f'{{{atom_ns}}}{content_tag}')
            if content_el is not None and content_el.text:
                description = content_el.text.strip()
                break

        # Get categories
        categories = []
        for cat in entry.findall(f'{{{atom_ns}}}category'):
            term = cat.get('term') or cat.get('label')
            if term:
                categories.append(term)

        # Look for video enclosure
        video_url = None
        for link_el in entry.findall(f'{{{atom_ns}}}link'):
            rel = link_el.get('rel', '')
            link_type = link_el.get('type', '')
            if rel == 'enclosure' and ('video' in link_type or 'audio' in link_type):
                video_url = link_el.get('href')
                break

        item_data = {
            'guid': guid,
            'link': link,
            'title': title,
        }

        return RSSItem(
            external_id=self._generate_external_id(item_data),
            title=title,
            link=link or '',
            pub_date=self._parse_date(pub_date_str),
            description=description[:1000] if description else None,
            video_url=video_url,
            categories=categories,
        )

    def fetch_items(self) -> list[RSSItem]:
        """
        Fetch and parse all items from the RSS feed.

        Returns:
            List of RSSItem objects
        """
        items = []

        try:
            logger.info(f"Fetching RSS feed: {self.feed_url}")
            response = self.session.get(self.feed_url, timeout=self.timeout)
            response.raise_for_status()

            # Parse XML
            root = ET.fromstring(response.content)

            # Detect feed type and parse accordingly
            if root.tag == 'rss' or root.find('channel') is not None:
                # RSS 2.0
                self._feed_type = 'rss'
                channel = root.find('channel') or root
                for item in channel.findall('item'):
                    parsed = self._parse_rss_item(item)
                    if parsed:
                        items.append(parsed)

            elif root.tag.endswith('feed') or 'atom' in root.tag.lower():
                # Atom
                self._feed_type = 'atom'
                for entry in root.findall(f'{{{NAMESPACES["atom"]}}}entry'):
                    parsed = self._parse_atom_entry(entry)
                    if parsed:
                        items.append(parsed)

            else:
                # Try RSS anyway
                self._feed_type = 'unknown'
                for item in root.iter('item'):
                    parsed = self._parse_rss_item(item)
                    if parsed:
                        items.append(parsed)

            logger.info(f"Found {len(items)} items in {self._feed_type} feed")

        except requests.RequestException as e:
            logger.error(f"Failed to fetch feed: {e}")
            raise
        except ET.ParseError as e:
            logger.error(f"Failed to parse feed XML: {e}")
            raise

        return items


class GranicusScraper(RSSFeedScraper):
    """Specialized scraper for Granicus video archives."""

    def _parse_rss_item(self, item: ET.Element) -> Optional[RSSItem]:
        """Parse Granicus-specific RSS item with video metadata."""
        result = super()._parse_rss_item(item)
        if not result:
            return None

        # Granicus often includes video URL in the link
        if result.link and not result.video_url:
            # Check if link points to a video player
            if 'granicus.com' in result.link and 'player' in result.link.lower():
                result.video_url = result.link

        # Try to extract meeting date from title (common format: "Meeting Name - December 15, 2025")
        if not result.pub_date:
            date_match = re.search(
                r'(\w+)\s+(\d{1,2}),?\s+(\d{4})',
                result.title
            )
            if date_match:
                try:
                    month_str, day, year = date_match.groups()
                    month_map = {
                        'january': 1, 'february': 2, 'march': 3, 'april': 4,
                        'may': 5, 'june': 6, 'july': 7, 'august': 8,
                        'september': 9, 'october': 10, 'november': 11, 'december': 12
                    }
                    month = month_map.get(month_str.lower())
                    if month:
                        result.pub_date = date(int(year), month, int(day))
                except (ValueError, KeyError):
                    pass

        return result


class FloridaChannelScraper(RSSFeedScraper):
    """Specialized scraper for The Florida Channel RSS feeds."""

    def _parse_rss_item(self, item: ET.Element) -> Optional[RSSItem]:
        """Parse Florida Channel RSS item."""
        result = super()._parse_rss_item(item)
        if not result:
            return None

        # Florida Channel video pages have the video embedded
        # The link is the video page URL
        if result.link and 'thefloridachannel.org/videos/' in result.link:
            result.video_url = result.link  # Video page URL

        # Try to extract date from title (common format: "MM/DD/YY Description")
        if not result.pub_date:
            date_match = re.match(r'(\d{1,2})/(\d{1,2})/(\d{2,4})', result.title)
            if date_match:
                try:
                    month, day, year = map(int, date_match.groups())
                    if year < 100:
                        year += 2000
                    result.pub_date = date(year, month, day)
                except ValueError:
                    pass

        return result


def create_scraper(feed_url: str) -> RSSFeedScraper:
    """
    Create appropriate scraper based on feed URL.

    Args:
        feed_url: URL of the RSS feed

    Returns:
        Appropriate scraper instance
    """
    url_lower = feed_url.lower()

    if 'granicus.com' in url_lower:
        return GranicusScraper(feed_url)
    elif 'thefloridachannel.org' in url_lower:
        return FloridaChannelScraper(feed_url)
    else:
        return RSSFeedScraper(feed_url)


def infer_hearing_type(title: str, categories: list = None) -> str:
    """Infer hearing type from title and categories."""
    text = title.lower()
    if categories:
        text += ' ' + ' '.join(c.lower() for c in categories)

    type_patterns = [
        ("Public Hearing", ["public hearing", "public comment"]),
        ("Pre-Hearing Conference", ["pre-hearing", "prehearing"]),
        ("Evidentiary Hearing", ["evidentiary"]),
        ("Agenda Conference", ["agenda conference"]),
        ("Workshop", ["workshop", "technical conference"]),
        ("Rate Case", ["rate case", "rate hearing", "rate increase"]),
        ("Commission Meeting", ["commission meeting", "open meeting", "regular meeting"]),
        ("Oral Argument", ["oral argument"]),
        ("Staff Conference", ["staff conference"]),
        ("Fuel Cost", ["fuel cost", "fuel recovery"]),
        ("Rulemaking", ["rulemaking", "rule making"]),
    ]

    for hearing_type, keywords in type_patterns:
        if any(kw in text for kw in keywords):
            return hearing_type

    return "Hearing"


if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO)

    parser = argparse.ArgumentParser(description="Scrape RSS feed")
    parser.add_argument("url", nargs="?",
                        default="https://thefloridachannel.org/programs/public-service-commission/feed/",
                        help="RSS feed URL")
    parser.add_argument("--limit", type=int, default=10, help="Max items to display")
    args = parser.parse_args()

    scraper = create_scraper(args.url)

    print(f"\nScraping: {args.url}\n")

    items = scraper.fetch_items()
    print(f"Found {len(items)} items\n")

    for item in items[:args.limit]:
        print(f"  {item.pub_date or 'N/A':10} | {item.title[:60]}")
        print(f"    Link: {item.link}")
        if item.video_url and item.video_url != item.link:
            print(f"    Video: {item.video_url}")
        if item.categories:
            print(f"    Categories: {', '.join(item.categories[:3])}")
        print()
