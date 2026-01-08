#!/usr/bin/env python3
"""
Backfill missing upload dates for YouTube videos.

Uses yt-dlp to fetch individual video metadata for videos missing dates.
"""

import sqlite3
import logging
import time
import sys
from datetime import datetime
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.scrapers.youtube import YouTubeScraper

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def backfill_dates(db_path: str = "data/psc_dev.db", limit: int = None, state: str = None):
    """
    Backfill missing dates for YouTube videos.

    Args:
        db_path: Path to SQLite database
        limit: Maximum number of videos to process (None = all)
        state: Only process videos from this state (e.g., "UT")
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Build query for videos missing dates
    query = """
        SELECT h.id, h.external_id, h.title, st.code
        FROM hearings h
        JOIN sources s ON h.source_id = s.id
        JOIN states st ON s.state_id = st.id
        WHERE h.status = 'discovered'
          AND h.hearing_date IS NULL
          AND h.external_id LIKE 'yt_%'
    """
    params = []

    if state:
        query += " AND st.code = ?"
        params.append(state)

    query += " ORDER BY st.code"

    if limit:
        query += f" LIMIT {limit}"

    cursor.execute(query, params)
    videos = cursor.fetchall()

    logger.info(f"Found {len(videos)} videos missing dates")

    if not videos:
        return

    scraper = YouTubeScraper("https://www.youtube.com")  # Dummy URL, not used for individual fetches

    updated = 0
    failed = 0

    for i, (hearing_id, external_id, title, state_code) in enumerate(videos):
        video_id = external_id.replace('yt_', '')

        logger.info(f"[{i+1}/{len(videos)}] [{state_code}] Fetching: {title[:50]}...")

        try:
            details = scraper.fetch_video_details(video_id)

            if details and details.upload_date:
                cursor.execute(
                    "UPDATE hearings SET hearing_date = ? WHERE id = ?",
                    (details.upload_date.isoformat(), hearing_id)
                )
                conn.commit()
                updated += 1
                logger.info(f"  → Date: {details.upload_date}")
            else:
                failed += 1
                logger.warning(f"  → No date found")

        except Exception as e:
            failed += 1
            logger.error(f"  → Error: {e}")

        # Rate limit to avoid YouTube blocking
        if (i + 1) % 50 == 0:
            logger.info(f"Progress: {updated} updated, {failed} failed. Pausing 5s...")
            time.sleep(5)
        else:
            time.sleep(0.5)  # Small delay between requests

    conn.close()

    logger.info(f"\n=== Complete ===")
    logger.info(f"Updated: {updated}")
    logger.info(f"Failed: {failed}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Backfill missing YouTube video dates")
    parser.add_argument("--limit", type=int, help="Maximum videos to process")
    parser.add_argument("--state", type=str, help="Only process this state (e.g., UT)")
    parser.add_argument("--db", type=str, default="data/psc_dev.db", help="Database path")

    args = parser.parse_args()

    backfill_dates(db_path=args.db, limit=args.limit, state=args.state)
