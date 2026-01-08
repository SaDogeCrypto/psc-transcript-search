#!/usr/bin/env python3
"""
YouTube Data API client for fetching video metadata.

Uses the YouTube Data API v3 to batch fetch video details including upload dates.
Much faster than yt-dlp for metadata-only requests (50 videos per request).
"""

import os
import logging
from datetime import datetime, date
from typing import Optional
from dataclasses import dataclass

import requests

logger = logging.getLogger(__name__)

YOUTUBE_API_BASE = "https://www.googleapis.com/youtube/v3"


@dataclass
class VideoMetadata:
    """Video metadata from YouTube API."""
    video_id: str
    title: str
    published_at: Optional[date]
    duration_seconds: Optional[int]
    channel_id: Optional[str]
    channel_title: Optional[str]


class YouTubeAPI:
    """Client for YouTube Data API v3."""

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize YouTube API client.

        Args:
            api_key: YouTube Data API key. If not provided, reads from YOUTUBE_API_KEY env var.
        """
        self.api_key = api_key or os.getenv("YOUTUBE_API_KEY")
        if not self.api_key:
            raise ValueError("YouTube API key required. Set YOUTUBE_API_KEY environment variable.")

    def get_video_details(self, video_ids: list[str]) -> dict[str, VideoMetadata]:
        """
        Fetch details for multiple videos in a single request.

        Args:
            video_ids: List of YouTube video IDs (max 50 per request)

        Returns:
            Dict mapping video_id to VideoMetadata
        """
        if not video_ids:
            return {}

        # API allows max 50 videos per request
        if len(video_ids) > 50:
            raise ValueError("Maximum 50 video IDs per request")

        params = {
            "key": self.api_key,
            "part": "snippet,contentDetails",
            "id": ",".join(video_ids),
        }

        response = requests.get(
            f"{YOUTUBE_API_BASE}/videos",
            params=params,
            timeout=30
        )
        response.raise_for_status()
        data = response.json()

        results = {}
        for item in data.get("items", []):
            video_id = item["id"]
            snippet = item.get("snippet", {})
            content = item.get("contentDetails", {})

            # Parse published date
            published_at = None
            if snippet.get("publishedAt"):
                try:
                    published_at = datetime.fromisoformat(
                        snippet["publishedAt"].replace("Z", "+00:00")
                    ).date()
                except ValueError:
                    pass

            # Parse duration (ISO 8601 format like PT1H30M45S)
            duration_seconds = None
            if content.get("duration"):
                duration_seconds = self._parse_duration(content["duration"])

            results[video_id] = VideoMetadata(
                video_id=video_id,
                title=snippet.get("title", ""),
                published_at=published_at,
                duration_seconds=duration_seconds,
                channel_id=snippet.get("channelId"),
                channel_title=snippet.get("channelTitle"),
            )

        return results

    def get_video_details_batch(self, video_ids: list[str], batch_size: int = 50) -> dict[str, VideoMetadata]:
        """
        Fetch details for any number of videos, batching automatically.

        Args:
            video_ids: List of YouTube video IDs (any length)
            batch_size: Number of videos per API request (max 50)

        Returns:
            Dict mapping video_id to VideoMetadata
        """
        results = {}
        batch_size = min(batch_size, 50)

        for i in range(0, len(video_ids), batch_size):
            batch = video_ids[i:i + batch_size]
            try:
                batch_results = self.get_video_details(batch)
                results.update(batch_results)
                logger.debug(f"Fetched {len(batch_results)} videos (batch {i // batch_size + 1})")
            except requests.RequestException as e:
                logger.error(f"API request failed for batch {i // batch_size + 1}: {e}")

        return results

    def _parse_duration(self, duration_str: str) -> Optional[int]:
        """
        Parse ISO 8601 duration string to seconds.

        Examples:
            PT1H30M45S -> 5445
            PT45M -> 2700
            PT30S -> 30
        """
        import re

        if not duration_str or not duration_str.startswith("PT"):
            return None

        total_seconds = 0

        # Extract hours, minutes, seconds
        hours_match = re.search(r"(\d+)H", duration_str)
        minutes_match = re.search(r"(\d+)M", duration_str)
        seconds_match = re.search(r"(\d+)S", duration_str)

        if hours_match:
            total_seconds += int(hours_match.group(1)) * 3600
        if minutes_match:
            total_seconds += int(minutes_match.group(1)) * 60
        if seconds_match:
            total_seconds += int(seconds_match.group(1))

        return total_seconds if total_seconds > 0 else None


def backfill_dates_from_api(db_path: str = "data/psc_dev.db", limit: int = None):
    """
    Backfill missing dates using YouTube API.

    Args:
        db_path: Path to SQLite database
        limit: Maximum number of videos to process
    """
    import sqlite3

    api = YouTubeAPI()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Get videos missing dates
    query = """
        SELECT id, external_id
        FROM hearings
        WHERE status = 'discovered'
          AND hearing_date IS NULL
          AND external_id LIKE 'yt_%'
    """
    if limit:
        query += f" LIMIT {limit}"

    cursor.execute(query)
    rows = cursor.fetchall()

    if not rows:
        logger.info("No videos missing dates")
        return

    logger.info(f"Found {len(rows)} videos missing dates")

    # Extract video IDs
    id_map = {}  # video_id -> hearing_id
    for hearing_id, external_id in rows:
        video_id = external_id.replace("yt_", "")
        id_map[video_id] = hearing_id

    video_ids = list(id_map.keys())

    # Fetch from API in batches
    logger.info(f"Fetching metadata from YouTube API...")
    results = api.get_video_details_batch(video_ids)

    # Update database
    updated = 0
    for video_id, metadata in results.items():
        if metadata.published_at:
            hearing_id = id_map[video_id]
            cursor.execute(
                "UPDATE hearings SET hearing_date = ? WHERE id = ?",
                (metadata.published_at.isoformat(), hearing_id)
            )
            updated += 1

    conn.commit()
    conn.close()

    logger.info(f"Updated {updated} of {len(rows)} videos with dates")


if __name__ == "__main__":
    import argparse
    from dotenv import load_dotenv

    load_dotenv()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s"
    )

    parser = argparse.ArgumentParser(description="Backfill dates using YouTube API")
    parser.add_argument("--limit", type=int, help="Maximum videos to process")
    parser.add_argument("--db", type=str, default="data/psc_dev.db", help="Database path")

    args = parser.parse_args()
    backfill_dates_from_api(db_path=args.db, limit=args.limit)
