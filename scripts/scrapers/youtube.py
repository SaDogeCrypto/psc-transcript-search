#!/usr/bin/env python3
"""
YouTube Channel Scraper

Scrapes video metadata from state PUC/PSC YouTube channels using yt-dlp.
Extracts video IDs, titles, durations, upload dates, and descriptions.
"""

import re
import json
import logging
import subprocess
from datetime import datetime, date
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import urlparse, parse_qs

logger = logging.getLogger(__name__)


@dataclass
class YouTubeVideo:
    """Represents a video scraped from YouTube."""
    video_id: str
    title: str
    upload_date: Optional[date] = None
    duration_seconds: Optional[int] = None
    description: Optional[str] = None
    view_count: Optional[int] = None
    channel_name: Optional[str] = None
    channel_id: Optional[str] = None

    @property
    def video_url(self) -> str:
        return f"https://www.youtube.com/watch?v={self.video_id}"

    @property
    def external_id(self) -> str:
        return f"yt_{self.video_id}"


class YouTubeScraper:
    """Scraper for YouTube channels using yt-dlp."""

    def __init__(self, channel_url: str, timeout: int = 120):
        """
        Initialize scraper for a YouTube channel.

        Args:
            channel_url: YouTube channel URL (various formats supported)
            timeout: Command timeout in seconds
        """
        self.channel_url = self._normalize_channel_url(channel_url)
        self.timeout = timeout

    def _normalize_channel_url(self, url: str) -> str:
        """Normalize various YouTube channel URL formats to videos or streams tab."""
        url = url.rstrip('/')

        # If URL already specifies a tab (videos, streams, playlists), keep it
        if url.endswith('/videos') or url.endswith('/streams') or url.endswith('/playlists'):
            return url

        # Handle @username format
        if '/@' in url:
            url = url + '/videos'
            return url

        # Handle /c/channelname format
        if '/c/' in url:
            url = url + '/videos'
            return url

        # Handle /channel/ID format
        if '/channel/' in url:
            url = url + '/videos'
            return url

        # Handle /user/username format
        if '/user/' in url:
            url = url + '/videos'
            return url

        return url

    def _parse_upload_date(self, date_str: str) -> Optional[date]:
        """Parse upload date from yt-dlp format (YYYYMMDD)."""
        if not date_str:
            return None
        try:
            return datetime.strptime(date_str, "%Y%m%d").date()
        except ValueError:
            return None

    def _parse_date_from_title(self, title: str) -> Optional[date]:
        """Extract date from video title using common patterns."""
        import re
        if not title:
            return None

        # Common date patterns in PSC video titles
        patterns = [
            # "12/18/2025" or "12/18/25"
            (r'(\d{1,2})/(\d{1,2})/(\d{2,4})', lambda m: self._build_date(m.group(3), m.group(1), m.group(2))),
            # "Dec 18, 2025" or "December 18, 2025"
            (r'(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+(\d{1,2}),?\s+(\d{4})',
             lambda m: self._build_date_from_month(m.group(3), m.group(1), m.group(2))),
            # "18 Dec 2025"
            (r'(\d{1,2})\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?,?\s+(\d{4})',
             lambda m: self._build_date_from_month(m.group(3), m.group(2), m.group(1))),
            # "2025-12-18"
            (r'(\d{4})-(\d{2})-(\d{2})', lambda m: self._build_date(m.group(1), m.group(2), m.group(3))),
        ]

        for pattern, builder in patterns:
            match = re.search(pattern, title, re.IGNORECASE)
            if match:
                try:
                    return builder(match)
                except (ValueError, AttributeError):
                    continue
        return None

    def _build_date(self, year_str: str, month_str: str, day_str: str) -> Optional[date]:
        """Build date from string components."""
        year = int(year_str)
        if year < 100:
            year = 2000 + year if year < 50 else 1900 + year
        month = int(month_str)
        day = int(day_str)
        if 1 <= month <= 12 and 1 <= day <= 31:
            return date(year, month, day)
        return None

    def _build_date_from_month(self, year_str: str, month_str: str, day_str: str) -> Optional[date]:
        """Build date from month name string."""
        month_map = {
            'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
            'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12
        }
        month = month_map.get(month_str[:3].lower())
        if month:
            return self._build_date(year_str, str(month), day_str)
        return None

    def _run_ytdlp(self, args: list[str]) -> tuple[int, str, str]:
        """Run yt-dlp with given arguments."""
        cmd = ["yt-dlp"] + args
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout
            )
            return result.returncode, result.stdout, result.stderr
        except subprocess.TimeoutExpired:
            logger.error(f"yt-dlp timed out after {self.timeout}s")
            return -1, "", "Timeout"
        except FileNotFoundError:
            logger.error("yt-dlp not found. Install with: pip install yt-dlp")
            return -1, "", "yt-dlp not found"

    def fetch_videos(self, max_videos: int = 100) -> list[YouTubeVideo]:
        """
        Fetch video metadata from the channel.

        Args:
            max_videos: Maximum number of videos to fetch

        Returns:
            List of YouTubeVideo objects
        """
        videos = []

        # Use yt-dlp to get video metadata as JSON
        args = [
            "--flat-playlist",
            "--no-download",
            "-j",  # JSON output for each video
            "--playlist-end", str(max_videos),
            "--no-warnings",
            "--ignore-errors",
            self.channel_url
        ]

        logger.info(f"Fetching videos from {self.channel_url}")
        returncode, stdout, stderr = self._run_ytdlp(args)

        # If /videos tab fails, try without /videos (some channels don't have videos tab)
        if returncode != 0 and not stdout and self.channel_url.endswith('/videos'):
            base_url = self.channel_url[:-7]  # Remove /videos
            logger.info(f"Videos tab failed, trying channel homepage: {base_url}")
            args[-1] = base_url
            returncode, stdout, stderr = self._run_ytdlp(args)

        if returncode != 0 and not stdout:
            logger.error(f"yt-dlp failed: {stderr}")
            return videos

        # Parse JSON lines
        for line in stdout.strip().split('\n'):
            if not line:
                continue
            try:
                data = json.loads(line)
                video = self._parse_video_entry(data)
                if video:
                    videos.append(video)
            except json.JSONDecodeError as e:
                logger.warning(f"Failed to parse JSON: {e}")
                continue

        logger.info(f"Found {len(videos)} videos")
        return videos

    def _parse_video_entry(self, data: dict) -> Optional[YouTubeVideo]:
        """Parse a video entry from yt-dlp JSON output."""
        video_id = data.get('id')
        if not video_id:
            return None

        title = data.get('title', '')
        if not title or title == '[Deleted video]' or title == '[Private video]':
            return None

        # Try to get upload date from multiple sources
        upload_date = None

        # 1. Try upload_date field (YYYYMMDD format)
        if data.get('upload_date'):
            upload_date = self._parse_upload_date(data.get('upload_date'))

        # 2. Try timestamp field (Unix timestamp)
        if not upload_date and data.get('timestamp'):
            try:
                upload_date = datetime.fromtimestamp(data['timestamp']).date()
            except (ValueError, OSError):
                pass

        # 3. Try release_timestamp
        if not upload_date and data.get('release_timestamp'):
            try:
                upload_date = datetime.fromtimestamp(data['release_timestamp']).date()
            except (ValueError, OSError):
                pass

        # 4. Fall back to parsing date from title
        if not upload_date:
            upload_date = self._parse_date_from_title(title)

        return YouTubeVideo(
            video_id=video_id,
            title=title,
            upload_date=upload_date,
            duration_seconds=data.get('duration'),
            description=data.get('description', '')[:1000] if data.get('description') else None,
            view_count=data.get('view_count'),
            channel_name=data.get('channel') or data.get('uploader'),
            channel_id=data.get('channel_id') or data.get('uploader_id'),
        )

    def fetch_video_details(self, video_id: str) -> Optional[YouTubeVideo]:
        """
        Fetch detailed metadata for a single video.

        Args:
            video_id: YouTube video ID

        Returns:
            YouTubeVideo with full details, or None if failed
        """
        url = f"https://www.youtube.com/watch?v={video_id}"
        args = [
            "--no-download",
            "-j",
            "--no-warnings",
            url
        ]

        returncode, stdout, stderr = self._run_ytdlp(args)

        if returncode != 0 or not stdout:
            logger.warning(f"Failed to fetch details for {video_id}: {stderr}")
            return None

        try:
            data = json.loads(stdout)
            return self._parse_video_entry(data)
        except json.JSONDecodeError:
            return None


def extract_video_id(url: str) -> Optional[str]:
    """Extract video ID from various YouTube URL formats."""
    # Standard watch URL
    if 'youtube.com/watch' in url:
        parsed = urlparse(url)
        params = parse_qs(parsed.query)
        if 'v' in params:
            return params['v'][0]

    # Short URL (youtu.be)
    if 'youtu.be/' in url:
        path = urlparse(url).path
        return path.lstrip('/')

    # Embed URL
    if 'youtube.com/embed/' in url:
        path = urlparse(url).path
        return path.replace('/embed/', '')

    return None


def parse_channel_url(url: str) -> dict:
    """
    Parse a YouTube channel URL to extract channel info.

    Returns:
        Dict with 'type' ('handle', 'custom', 'channel', 'user') and 'value'
    """
    url = url.rstrip('/')

    # @handle format
    match = re.search(r'youtube\.com/@([^/]+)', url)
    if match:
        return {'type': 'handle', 'value': match.group(1)}

    # /c/customname format
    match = re.search(r'youtube\.com/c/([^/]+)', url)
    if match:
        return {'type': 'custom', 'value': match.group(1)}

    # /channel/ID format
    match = re.search(r'youtube\.com/channel/([^/]+)', url)
    if match:
        return {'type': 'channel', 'value': match.group(1)}

    # /user/username format
    match = re.search(r'youtube\.com/user/([^/]+)', url)
    if match:
        return {'type': 'user', 'value': match.group(1)}

    return {'type': 'unknown', 'value': url}


# Keywords to identify relevant PUC/PSC hearing content
HEARING_KEYWORDS = [
    # Meeting types
    "hearing", "meeting", "commission", "docket", "proceeding",
    "workshop", "conference", "session", "agenda",
    # Topics
    "rate case", "rate increase", "rate review",
    "irp", "integrated resource plan", "resource plan",
    "capacity", "energy", "electric", "gas", "utility",
    "puc", "psc", "cpuc", "puct",
    # Regulatory
    "testimony", "witness", "commissioner", "staff",
    "evidentiary", "oral argument",
]

EXCLUDE_KEYWORDS = [
    # Entertainment
    "music", "song", "concert", "entertainment",
    "trailer", "preview", "promo",

    # Educational/promotional content
    "meet your", "who we are", "how the puc works",
    "cold weather rule", "proteccion contra",
    "call before you dig", "don't be like me",
    "be utility wise", "callutilitiesnow",
    "what is energy choice", "how to handle a",
    "need telephone assistance", "what's up (and down)",
    "what does the puc do", "what does the utc do",
    "what is an irp", "what is dc power connect",
    "overview of the public service commission",
    "how the district of columbia gets",
    "we work for you",

    # Training videos
    "professor max powers", "break out room",
    "fusion joints", "phmsa", "plastic pipe",
    "utility damage prevention", "vent limited regulator",

    # Non-utility topics
    "towing task force", "towing industry",

    # 911/Emergency services (not utility regulation)
    "911 enterprise board", "911 task force",
    "esinet", "ipcs task force", "gis informational",
    "9-1-1 leadership",

    # Podcasts
    "behind the meter: an mpsc podcast",

    # Promotional ads and PSAs
    "#winterreadydc", "#here2helpdc",
    "call the commission", "consumer help line",
    "clean energy program",
    "utility bill assistance", "utility assistance day",
    "energy choice 30 spot",
    "small & diverse business", "small and diverse business",

    # Safety campaigns
    "safe digging month", "fix a leak week",
    "rail safety week", "think train",
    "fighting utility scams", "fight utility scams",

    # Supplier training
    "energy choice ohio supplier training",
    "motor carrier registration",
    "electronic log device (eld) training",

    # Reconnect order PSAs
    "special reconnect order", "winter reconnect order",

    # Tutorials and how-tos
    "how to make your voice heard",
    "how to read and understand your",
    "tutorial: how to",
    "using interactive maps", "use puco docketing",
    "navigating a cpuc docket",
    "how to subscribe to case",
    "making an electronic filing",
    "prequalification and basic navigation",
    "application map and application process",

    # History/overview promos
    "history behind the public utilities",
    "behind the scenes with public utilities",

    # Events and celebrations
    "black history month",
    "25th anniversary", "30 year anniversary",
    "pride flag raising",
    "swearing in ceremony",
    "careers in utilities",

    # Conferences (not hearings)
    "cybersecurity conference",
    "tri annual safety conference",
    "clean energy summit",
    "supplier diversity hearing",

    # Press/staff conferences
    "press conference", "press briefing",
    "staff conference",
    "lihwap press conference",

    # Bill education
    "understand your electric bill",
    "managing rising energy costs",

    # Grant programs
    "formula grant program",

    # Rate case educational series
    "revenue requirement: what is",
    "parties in a rate case",
    "review of storm costs in a rate case",
    "review of utility depreciation",
    "take back our grid act",
    "ways to get involved in a rate case",
    "allowed rate of return",
    "overview of rate cases",

    # Other educational
    "african american leaders who shaped",
    "distribution integrity management",
    "kidwind challenge", "k-12 energy benchmarking",
    "gas pipeline safety: filing",
    "request a speaker",
    "what happens when i contact",
    "understanding energy choice",
    "energy assistance program",
    "home energy assistance",
    "annual report overview",
    "annual report webinar",
    "pura parking & building",

    # PowerPath/DC promotional
    "powerpath dc", "community renewable energy facilities",

    # Program announcements
    "program announcement", "check presentation",
    "informational session",

    # Vigilant Guard
    "vigilant guard",

    # Transportation recruiting
    "transportation enforcement recruiting",

    # Time of use promos
    "xcel energy's new time of use",

    # Bill relief announcements
    "delivered $430 million",

    # Conference panels (not hearings)
    "a glimpse of the future",

    # Broadband (different regulatory domain)
    "bead challenge", "bead rebuttal", "bead program",

    # Generic non-hearing content
    "opening remarks", "closing remarks",
    "winter storm tips", "consumer education video",
    "holiday driving tips",
]


def is_hearing_video(video: YouTubeVideo) -> bool:
    """
    Check if a video is likely a PUC/PSC hearing based on title/description.

    Args:
        video: YouTubeVideo to check

    Returns:
        True if video appears to be hearing-related
    """
    text = (video.title + " " + (video.description or "")).lower()

    # Check exclusions first
    if any(kw in text for kw in EXCLUDE_KEYWORDS):
        return False

    # Check for hearing keywords
    if any(kw in text for kw in HEARING_KEYWORDS):
        return True

    # Videos over 30 minutes are likely hearings
    if video.duration_seconds and video.duration_seconds > 1800:
        return True

    return False


if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO)

    parser = argparse.ArgumentParser(description="Scrape YouTube channel videos")
    parser.add_argument("url", nargs="?", default="https://www.youtube.com/@CaliforniaPUC",
                        help="YouTube channel URL")
    parser.add_argument("--limit", type=int, default=10, help="Max videos to fetch")
    parser.add_argument("--filter", action="store_true", help="Filter for hearing content only")
    args = parser.parse_args()

    scraper = YouTubeScraper(args.url)

    print(f"\nScraping: {scraper.channel_url}\n")

    videos = scraper.fetch_videos(max_videos=args.limit)

    if args.filter:
        videos = [v for v in videos if is_hearing_video(v)]
        print(f"Filtered to {len(videos)} hearing-related videos\n")

    for video in videos:
        duration_str = ""
        if video.duration_seconds:
            hours = video.duration_seconds // 3600
            minutes = (video.duration_seconds % 3600) // 60
            if hours:
                duration_str = f"{hours}h {minutes}m"
            else:
                duration_str = f"{minutes}m"

        print(f"  {video.upload_date or 'N/A':10} | {duration_str:>6} | {video.title[:60]}")
        print(f"    URL: {video.video_url}")
        print()
