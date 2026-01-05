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
        """Normalize various YouTube channel URL formats to videos tab."""
        url = url.rstrip('/')

        # Handle @username format
        if '/@' in url:
            if not url.endswith('/videos'):
                url = url + '/videos'
            return url

        # Handle /c/channelname format
        if '/c/' in url:
            if not url.endswith('/videos'):
                url = url + '/videos'
            return url

        # Handle /channel/ID format
        if '/channel/' in url:
            if not url.endswith('/videos'):
                url = url + '/videos'
            return url

        # Handle /user/username format
        if '/user/' in url:
            if not url.endswith('/videos'):
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

        return YouTubeVideo(
            video_id=video_id,
            title=title,
            upload_date=self._parse_upload_date(data.get('upload_date')),
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
    "music", "song", "concert", "entertainment",
    "trailer", "preview", "promo",
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
