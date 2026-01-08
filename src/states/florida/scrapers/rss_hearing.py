"""
Florida RSS/YouTube hearing scraper.

Scrapes hearing recordings from Florida PSC YouTube channel RSS feed.
YouTube Channel: UCw4KPSs7zVOUHMQJglvDOyw

Extracts:
- Video metadata (title, date, duration)
- Docket numbers from titles
- Hearing type classification
"""

import re
import logging
from datetime import datetime
from typing import Optional, Dict, Any, List
from xml.etree import ElementTree

import httpx
from sqlalchemy.orm import Session

from src.core.scrapers.base import Scraper, ScraperResult
from src.core.models.docket import Docket
from src.core.models.hearing import Hearing
from src.states.florida.models.hearing import FLHearingDetails

logger = logging.getLogger(__name__)

# Florida PSC YouTube channel
FL_YOUTUBE_CHANNEL_ID = "UCw4KPSs7zVOUHMQJglvDOyw"
RSS_FEED_URL = f"https://www.youtube.com/feeds/videos.xml?channel_id={FL_YOUTUBE_CHANNEL_ID}"

# Namespace for YouTube RSS feed
YOUTUBE_NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "yt": "http://www.youtube.com/xml/schemas/2015",
    "media": "http://search.yahoo.com/mrss/",
}


class RSSHearingScraper(Scraper):
    """
    Scrape hearing recordings from Florida PSC YouTube RSS feed.

    The Florida PSC posts hearing recordings to YouTube. This scraper:
    1. Fetches the RSS feed
    2. Extracts video metadata
    3. Parses docket numbers from titles
    4. Creates Hearing records

    Usage:
        scraper = RSSHearingScraper(db)
        result = scraper.scrape()
    """

    name = "rss_hearings"
    state_code = "FL"

    def __init__(self, db: Session):
        self.db = db
        self.client = httpx.Client(timeout=30.0, follow_redirects=True)

    def scrape(
        self,
        limit: int = 50,
        **kwargs
    ) -> ScraperResult:
        """
        Scrape hearings from YouTube RSS feed.

        Args:
            limit: Maximum videos to process

        Returns:
            ScraperResult with counts
        """
        logger.info("Scraping FL hearings from YouTube RSS feed")

        try:
            # Fetch RSS feed
            response = self.client.get(RSS_FEED_URL)
            response.raise_for_status()

            # Parse feed
            videos = self._parse_rss_feed(response.text)
            logger.info(f"Found {len(videos)} videos in RSS feed")

            items_created = 0
            items_updated = 0
            errors = []

            for video_data in videos[:limit]:
                try:
                    created = self._upsert_hearing(video_data)
                    if created:
                        items_created += 1
                    else:
                        items_updated += 1
                except Exception as e:
                    error_msg = f"Error processing {video_data.get('video_id')}: {e}"
                    logger.error(error_msg)
                    errors.append(error_msg)

            self.db.commit()

            return ScraperResult(
                success=True,
                items_found=len(videos),
                items_created=items_created,
                items_updated=items_updated,
                errors=errors
            )

        except httpx.HTTPError as e:
            logger.exception("RSS feed request failed")
            return ScraperResult(success=False, errors=[f"HTTP error: {e}"])
        except Exception as e:
            logger.exception("RSS scrape failed")
            return ScraperResult(success=False, errors=[str(e)])

    def get_item(self, video_id: str) -> Optional[Dict[str, Any]]:
        """
        Fetch video metadata by YouTube video ID.

        Note: This returns cached data from database.
        For fresh data, use YouTube Data API.
        """
        fl_details = self.db.query(FLHearingDetails).filter(
            FLHearingDetails.youtube_video_id == video_id
        ).first()

        if fl_details and fl_details.hearing:
            return fl_details.hearing.to_dict()

        return None

    def _parse_rss_feed(self, content: str) -> List[Dict[str, Any]]:
        """
        Parse YouTube RSS feed.

        Returns list of video metadata dicts.
        """
        videos = []

        try:
            root = ElementTree.fromstring(content)

            for entry in root.findall("atom:entry", YOUTUBE_NS):
                video_id = entry.find("yt:videoId", YOUTUBE_NS)
                title = entry.find("atom:title", YOUTUBE_NS)
                published = entry.find("atom:published", YOUTUBE_NS)
                link = entry.find("atom:link", YOUTUBE_NS)

                # Get media group for thumbnail
                media_group = entry.find("media:group", YOUTUBE_NS)
                thumbnail = None
                description = None

                if media_group is not None:
                    thumb_elem = media_group.find("media:thumbnail", YOUTUBE_NS)
                    if thumb_elem is not None:
                        thumbnail = thumb_elem.get("url")

                    desc_elem = media_group.find("media:description", YOUTUBE_NS)
                    if desc_elem is not None:
                        description = desc_elem.text

                if video_id is not None:
                    videos.append({
                        "video_id": video_id.text,
                        "title": title.text if title is not None else "",
                        "published": published.text if published is not None else None,
                        "url": link.get("href") if link is not None else f"https://www.youtube.com/watch?v={video_id.text}",
                        "thumbnail": thumbnail,
                        "description": description,
                    })

        except ElementTree.ParseError as e:
            logger.error(f"Failed to parse RSS feed: {e}")

        return videos

    def _upsert_hearing(self, data: Dict[str, Any]) -> bool:
        """
        Insert or update hearing from video data.

        Args:
            data: Video metadata dict

        Returns:
            True if created, False if updated
        """
        video_id = data.get("video_id")
        if not video_id:
            raise ValueError("Missing video ID")

        # Check if exists
        existing_detail = self.db.query(FLHearingDetails).filter(
            FLHearingDetails.youtube_video_id == video_id
        ).first()

        if existing_detail:
            # Update existing
            hearing = existing_detail.hearing
            hearing.title = data.get("title") or hearing.title
            hearing.updated_at = datetime.utcnow()
            return False

        # Parse video metadata
        title = data.get("title") or ""
        docket_number = self._extract_docket_number(title)
        hearing_date = self._parse_published_date(data.get("published"))
        hearing_type = self._classify_hearing_type(title)

        # Look up docket
        docket = None
        if docket_number:
            docket = self.db.query(Docket).filter(
                Docket.state_code == "FL",
                Docket.docket_number == docket_number
            ).first()

        # Create hearing
        hearing = Hearing(
            state_code="FL",
            docket_id=docket.id if docket else None,
            docket_number=docket_number,
            title=title,
            hearing_type=hearing_type,
            hearing_date=hearing_date,
            video_url=f"https://www.youtube.com/watch?v={video_id}",
            transcript_status="pending",
            source_system="youtube_rss",
            external_id=video_id,
        )
        self.db.add(hearing)
        self.db.flush()

        # Create FL details
        fl_details = FLHearingDetails(
            hearing_id=hearing.id,
            youtube_video_id=video_id,
            youtube_channel_id=FL_YOUTUBE_CHANNEL_ID,
            youtube_thumbnail_url=data.get("thumbnail"),
            rss_guid=video_id,
            rss_published_at=self._parse_iso_datetime(data.get("published")),
        )
        self.db.add(fl_details)

        return True

    def _extract_docket_number(self, title: str) -> Optional[str]:
        """
        Extract Florida docket number from video title.

        Florida format: YYYYNNNN-XX (e.g., 20240001-EI)
        """
        # Pattern matches Florida docket format
        pattern = r'\b(\d{8}-[A-Z]{2})\b'
        match = re.search(pattern, title)

        if match:
            return match.group(1)

        return None

    def _classify_hearing_type(self, title: str) -> str:
        """
        Classify hearing type based on title.
        """
        title_lower = title.lower()

        if "agenda" in title_lower:
            return "agenda"
        if "evidentiary" in title_lower:
            return "evidentiary"
        if "public hearing" in title_lower or "public comment" in title_lower:
            return "public_hearing"
        if "workshop" in title_lower:
            return "workshop"
        if "prehearing" in title_lower:
            return "prehearing"
        if "oral argument" in title_lower:
            return "oral_argument"

        return "hearing"

    def _parse_published_date(self, date_str: Optional[str]):
        """Parse published date from RSS feed."""
        if not date_str:
            return None

        try:
            # ISO format from YouTube
            dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            return dt.date()
        except Exception:
            pass

        return None

    def _parse_iso_datetime(self, date_str: Optional[str]):
        """Parse ISO datetime from RSS feed."""
        if not date_str:
            return None

        try:
            return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        except Exception:
            pass

        return None
