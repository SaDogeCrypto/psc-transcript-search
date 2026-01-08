"""
Florida Channel Scraper

Scrapes The Florida Channel RSS feed for PSC hearing videos.
Adapted from scripts/scrapers/rss.py to work with Florida-specific models.
"""
import re
import logging
import xml.etree.ElementTree as ET
from datetime import datetime, date, timezone
from typing import Optional, List
from dataclasses import dataclass
from enum import Enum
import threading

import httpx

from florida.models import get_db
from florida.models.hearing import FLHearing

logger = logging.getLogger(__name__)

# Florida Channel RSS feed URL
FLORIDA_CHANNEL_RSS = "https://thefloridachannel.org/programs/public-service-commission/feed/"


class ScraperStatus(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    STOPPING = "stopping"
    COMPLETED = "completed"
    ERROR = "error"


@dataclass
class RSSItem:
    """Parsed RSS item."""
    title: str
    link: Optional[str] = None
    description: Optional[str] = None
    pub_date: Optional[date] = None
    video_url: Optional[str] = None
    guid: Optional[str] = None
    categories: List[str] = None

    def __post_init__(self):
        if self.categories is None:
            self.categories = []


@dataclass
class ScraperProgress:
    """Track scraper progress."""
    status: ScraperStatus = ScraperStatus.IDLE
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    items_found: int = 0
    new_hearings: int = 0
    existing_hearings: int = 0
    errors: List[str] = None

    def __post_init__(self):
        if self.errors is None:
            self.errors = []

    def to_dict(self) -> dict:
        return {
            "status": self.status.value,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "current_scraper_type": "rss",
            "current_source_name": "The Florida Channel",
            "current_source_index": 1 if self.status == ScraperStatus.RUNNING else 0,
            "total_sources": 1,
            "sources_completed": 1 if self.status == ScraperStatus.COMPLETED else 0,
            "items_found": self.items_found,
            "new_hearings": self.new_hearings,
            "existing_hearings": self.existing_hearings,
            "errors": self.errors[-10:],
            "error_count": len(self.errors),
        }


# Global scraper state
_scraper_progress = ScraperProgress()
_scraper_lock = threading.Lock()
_stop_requested = False


def get_scraper_status() -> dict:
    """Get current scraper status."""
    with _scraper_lock:
        return _scraper_progress.to_dict()


def request_stop():
    """Request scraper to stop."""
    global _stop_requested
    _stop_requested = True


def _parse_date(date_str: str) -> Optional[date]:
    """Parse various date formats."""
    if not date_str:
        return None

    # Common RSS date formats
    formats = [
        "%a, %d %b %Y %H:%M:%S %z",
        "%a, %d %b %Y %H:%M:%S %Z",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%d",
    ]

    for fmt in formats:
        try:
            dt = datetime.strptime(date_str.strip(), fmt)
            return dt.date()
        except ValueError:
            continue

    return None


def _parse_date_from_title(title: str) -> Optional[date]:
    """Extract date from title (common format: MM/DD/YY or MM/DD/YYYY)."""
    match = re.match(r'(\d{1,2})/(\d{1,2})/(\d{2,4})', title)
    if match:
        try:
            month, day, year = map(int, match.groups())
            if year < 100:
                year += 2000
            return date(year, month, day)
        except ValueError:
            pass
    return None


def _infer_hearing_type(title: str) -> str:
    """Infer hearing type from title."""
    text = title.lower()

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


def _parse_rss_item(item: ET.Element) -> Optional[RSSItem]:
    """Parse RSS item element."""
    title_el = item.find('title')
    if title_el is None or not title_el.text:
        return None

    title = title_el.text.strip()

    link = None
    link_el = item.find('link')
    if link_el is not None and link_el.text:
        link = link_el.text.strip()

    description = None
    desc_el = item.find('description')
    if desc_el is not None and desc_el.text:
        description = desc_el.text.strip()

    pub_date = None
    date_el = item.find('pubDate')
    if date_el is not None and date_el.text:
        pub_date = _parse_date(date_el.text)

    guid = None
    guid_el = item.find('guid')
    if guid_el is not None and guid_el.text:
        guid = guid_el.text.strip()

    categories = []
    for cat_el in item.findall('category'):
        if cat_el.text:
            categories.append(cat_el.text.strip())

    result = RSSItem(
        title=title,
        link=link,
        description=description,
        pub_date=pub_date,
        guid=guid,
        categories=categories,
    )

    # Florida Channel: video pages have the video embedded
    if link and 'thefloridachannel.org/videos/' in link:
        result.video_url = link

    # Try to extract date from title if not in RSS
    if not result.pub_date:
        result.pub_date = _parse_date_from_title(title)

    return result


def fetch_and_parse_feed(feed_url: str = FLORIDA_CHANNEL_RSS) -> List[RSSItem]:
    """Fetch and parse RSS feed."""
    items = []

    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; FloridaPSCScraper/1.0; +https://github.com/canaryscope)",
        "Accept": "application/rss+xml, application/xml, text/xml, */*",
    }

    try:
        with httpx.Client(timeout=30.0, headers=headers) as client:
            response = client.get(feed_url)
            response.raise_for_status()

        root = ET.fromstring(response.content)
        channel = root.find('channel')
        if channel is None:
            logger.warning("No channel element found in RSS feed")
            return items

        for item in channel.findall('item'):
            parsed = _parse_rss_item(item)
            if parsed:
                items.append(parsed)

        logger.info(f"Parsed {len(items)} items from RSS feed")

    except httpx.HTTPError as e:
        logger.error(f"HTTP error fetching RSS feed: {e}")
        raise
    except ET.ParseError as e:
        logger.error(f"XML parse error: {e}")
        raise

    return items


def run_scraper(dry_run: bool = False) -> ScraperProgress:
    """
    Run the Florida Channel scraper.

    Args:
        dry_run: If True, don't save to database

    Returns:
        ScraperProgress with results
    """
    global _scraper_progress, _stop_requested

    with _scraper_lock:
        if _scraper_progress.status == ScraperStatus.RUNNING:
            logger.warning("Scraper already running")
            return _scraper_progress

        _scraper_progress = ScraperProgress(
            status=ScraperStatus.RUNNING,
            started_at=datetime.now(timezone.utc),
        )
        _stop_requested = False

    try:
        # Fetch RSS feed
        items = fetch_and_parse_feed()

        with _scraper_lock:
            _scraper_progress.items_found = len(items)

        if _stop_requested:
            with _scraper_lock:
                _scraper_progress.status = ScraperStatus.IDLE
            return _scraper_progress

        # Process items
        db = None if dry_run else next(get_db())
        try:
            for item in items:
                if _stop_requested:
                    break

                if not item.pub_date:
                    logger.warning(f"Skipping item without date: {item.title}")
                    continue

                if dry_run:
                    logger.info(f"[DRY RUN] Would create hearing: {item.title}")
                    with _scraper_lock:
                        _scraper_progress.new_hearings += 1
                    continue

                # Check if hearing already exists
                existing = db.query(FLHearing).filter(
                    FLHearing.source_url == item.link
                ).first()

                if existing:
                    with _scraper_lock:
                        _scraper_progress.existing_hearings += 1
                    continue

                # Create new hearing
                hearing = FLHearing(
                    title=item.title,
                    hearing_date=item.pub_date,
                    hearing_type=_infer_hearing_type(item.title),
                    source_type="video",
                    source_url=item.link,
                    external_id=item.guid,
                    transcript_status=None,  # Pending transcription
                )

                db.add(hearing)
                db.commit()

                with _scraper_lock:
                    _scraper_progress.new_hearings += 1

                logger.info(f"Created hearing: {item.title}")

        finally:
            if db:
                db.close()

        with _scraper_lock:
            _scraper_progress.status = ScraperStatus.COMPLETED
            _scraper_progress.finished_at = datetime.now(timezone.utc)

    except Exception as e:
        logger.exception("Scraper error")
        with _scraper_lock:
            _scraper_progress.status = ScraperStatus.ERROR
            _scraper_progress.errors.append(str(e))
            _scraper_progress.finished_at = datetime.now(timezone.utc)

    return _scraper_progress


def start_scraper_async(dry_run: bool = False) -> dict:
    """Start scraper in background thread."""
    with _scraper_lock:
        if _scraper_progress.status == ScraperStatus.RUNNING:
            return {"message": "Scraper already running", "status": "running"}

    thread = threading.Thread(target=run_scraper, args=(dry_run,), daemon=True)
    thread.start()

    return {"message": "Scraper started", "status": "running"}


def stop_scraper() -> dict:
    """Request scraper to stop."""
    global _stop_requested

    with _scraper_lock:
        if _scraper_progress.status != ScraperStatus.RUNNING:
            return {"message": "Scraper not running", "status": _scraper_progress.status.value}

    _stop_requested = True
    return {"message": "Stop requested", "status": "stopping"}
