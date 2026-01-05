#!/usr/bin/env python3
"""
Scrape YouTube channel sources and save hearings to database.

Usage:
    python scripts/scrape_youtube.py                    # Scrape all YouTube sources
    python scripts/scrape_youtube.py --source-id 11    # Scrape specific source
    python scripts/scrape_youtube.py --state CA        # Scrape by state code
    python scripts/scrape_youtube.py --dry-run         # Preview without saving
    python scripts/scrape_youtube.py --limit 50        # Limit videos per channel
"""

import sys
import os
import argparse
import logging
from datetime import datetime, timezone

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from app.models.database import Source, Hearing, State
from scripts.scrapers.youtube import YouTubeScraper, is_hearing_video

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def scrape_source(
    db,
    source: Source,
    max_videos: int = 100,
    filter_hearings: bool = True,
    dry_run: bool = False
) -> dict:
    """
    Scrape a single YouTube channel source and save hearings to database.

    Args:
        db: Database session
        source: Source model instance
        max_videos: Maximum videos to fetch per channel
        filter_hearings: Whether to filter for hearing-related content
        dry_run: If True, don't save to database

    Returns:
        Dict with scrape results
    """
    results = {
        "source_id": source.id,
        "source_name": source.name,
        "videos_found": 0,
        "videos_filtered": 0,
        "new_hearings": 0,
        "existing_hearings": 0,
        "errors": [],
    }

    try:
        scraper = YouTubeScraper(source.url)

        logger.info(f"Scraping {source.name} ({source.url})")

        # Fetch videos from channel
        videos = scraper.fetch_videos(max_videos=max_videos)
        results["videos_found"] = len(videos)

        logger.info(f"Found {len(videos)} videos")

        # Optionally filter for hearing content
        if filter_hearings:
            videos = [v for v in videos if is_hearing_video(v)]
            results["videos_filtered"] = len(videos)
            logger.info(f"Filtered to {len(videos)} hearing-related videos")

        for video in videos:
            # Check if hearing already exists
            existing = db.query(Hearing).filter(
                Hearing.source_id == source.id,
                Hearing.external_id == video.external_id
            ).first()

            if existing:
                results["existing_hearings"] += 1
                logger.debug(f"Skipping existing hearing: {video.external_id}")
                continue

            # Try to infer hearing type from title
            hearing_type = infer_hearing_type(video.title)

            # Create new hearing
            hearing = Hearing(
                source_id=source.id,
                state_id=source.state_id,
                external_id=video.external_id,
                title=video.title,
                description=video.description,
                hearing_date=video.upload_date,  # Use upload date as proxy for hearing date
                hearing_type=hearing_type,
                source_url=source.url,
                video_url=video.video_url,
                duration_seconds=video.duration_seconds,
                status="discovered",
            )

            if not dry_run:
                db.add(hearing)
                logger.info(f"Added hearing: {video.title[:60]}")
            else:
                logger.info(f"[DRY RUN] Would add: {video.title[:60]}")

            results["new_hearings"] += 1

        # Update source status
        if not dry_run:
            source.last_checked_at = datetime.now(timezone.utc)
            source.status = "active"
            source.error_message = None

            # Update last_hearing_at if we found new hearings
            if results["new_hearings"] > 0 and videos:
                latest_video = max(
                    (v for v in videos if v.upload_date),
                    key=lambda v: v.upload_date,
                    default=None
                )
                if latest_video and latest_video.upload_date:
                    source.last_hearing_at = datetime.combine(
                        latest_video.upload_date,
                        datetime.min.time(),
                        tzinfo=timezone.utc
                    )

            db.commit()

    except Exception as e:
        error_msg = str(e)
        results["errors"].append(error_msg)
        logger.error(f"Error scraping {source.name}: {error_msg}")

        if not dry_run:
            source.status = "error"
            source.error_message = error_msg[:500]
            source.last_checked_at = datetime.now(timezone.utc)
            db.commit()

    return results


def infer_hearing_type(title: str) -> str:
    """Infer hearing type from video title."""
    title_lower = title.lower()

    type_patterns = [
        ("Voting Meeting", ["voting meeting", "business meeting"]),
        ("Public Hearing", ["public hearing", "public comment"]),
        ("Evidentiary Hearing", ["evidentiary hearing", "evidentiary"]),
        ("Workshop", ["workshop", "technical conference"]),
        ("Rate Case", ["rate case", "rate hearing", "rate increase"]),
        ("IRP Hearing", ["irp", "integrated resource plan", "resource plan"]),
        ("Oral Argument", ["oral argument"]),
        ("Commission Meeting", ["commission meeting", "regular meeting", "open meeting"]),
        ("Prehearing Conference", ["prehearing", "pre-hearing"]),
        ("Staff Conference", ["staff conference", "staff meeting"]),
    ]

    for hearing_type, keywords in type_patterns:
        if any(kw in title_lower for kw in keywords):
            return hearing_type

    return "Hearing"


def main():
    parser = argparse.ArgumentParser(description="Scrape YouTube channel sources")
    parser.add_argument("--source-id", type=int, help="Specific source ID to scrape")
    parser.add_argument("--state", help="State code to filter sources (e.g., CA, TX)")
    parser.add_argument("--limit", type=int, default=100, help="Max videos per channel")
    parser.add_argument("--no-filter", action="store_true", help="Don't filter for hearing content")
    parser.add_argument("--dry-run", action="store_true", help="Preview without saving to database")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable debug logging")
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    db = SessionLocal()

    try:
        # Build query for YouTube sources
        query = db.query(Source).filter(
            Source.source_type == "youtube_channel",
            Source.enabled == True
        )

        if args.source_id:
            query = query.filter(Source.id == args.source_id)

        if args.state:
            state = db.query(State).filter(State.code == args.state.upper()).first()
            if not state:
                logger.error(f"State not found: {args.state}")
                return 1
            query = query.filter(Source.state_id == state.id)

        sources = query.all()

        if not sources:
            logger.warning("No YouTube sources found matching criteria")
            return 0

        logger.info(f"Found {len(sources)} YouTube source(s) to scrape")

        total_results = {
            "sources_scraped": 0,
            "total_videos": 0,
            "videos_filtered": 0,
            "new_hearings": 0,
            "existing_hearings": 0,
            "errors": [],
        }

        for source in sources:
            results = scrape_source(
                db,
                source,
                max_videos=args.limit,
                filter_hearings=not args.no_filter,
                dry_run=args.dry_run
            )

            total_results["sources_scraped"] += 1
            total_results["total_videos"] += results["videos_found"]
            total_results["videos_filtered"] += results.get("videos_filtered", 0)
            total_results["new_hearings"] += results["new_hearings"]
            total_results["existing_hearings"] += results["existing_hearings"]
            total_results["errors"].extend(results["errors"])

        # Print summary
        print("\n" + "=" * 60)
        print("SCRAPE SUMMARY")
        print("=" * 60)
        print(f"Sources scraped:    {total_results['sources_scraped']}")
        print(f"Videos found:       {total_results['total_videos']}")
        if not args.no_filter:
            print(f"After filtering:    {total_results['videos_filtered']}")
        print(f"New hearings:       {total_results['new_hearings']}")
        print(f"Existing hearings:  {total_results['existing_hearings']}")
        print(f"Errors:             {len(total_results['errors'])}")

        if args.dry_run:
            print("\n[DRY RUN - No changes saved to database]")

        if total_results["errors"]:
            print("\nErrors:")
            for err in total_results["errors"][:10]:
                print(f"  - {err[:100]}")
            if len(total_results["errors"]) > 10:
                print(f"  ... and {len(total_results['errors']) - 10} more")

        return 0 if not total_results["errors"] else 1

    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
