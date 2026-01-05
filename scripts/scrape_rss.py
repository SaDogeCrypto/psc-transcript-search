#!/usr/bin/env python3
"""
Scrape RSS feed sources and save hearings to database.

Usage:
    python scripts/scrape_rss.py                    # Scrape all RSS sources
    python scripts/scrape_rss.py --source-id 62    # Scrape specific source
    python scripts/scrape_rss.py --state FL        # Scrape by state code
    python scripts/scrape_rss.py --dry-run         # Preview without saving
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
from scripts.scrapers.rss import create_scraper, infer_hearing_type

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def scrape_source(db, source: Source, dry_run: bool = False) -> dict:
    """
    Scrape a single RSS feed source and save hearings to database.

    Args:
        db: Database session
        source: Source model instance
        dry_run: If True, don't save to database

    Returns:
        Dict with scrape results
    """
    results = {
        "source_id": source.id,
        "source_name": source.name,
        "items_found": 0,
        "new_hearings": 0,
        "existing_hearings": 0,
        "errors": [],
    }

    try:
        scraper = create_scraper(source.url)

        logger.info(f"Scraping {source.name} ({source.url})")

        # Fetch items from feed
        items = scraper.fetch_items()
        results["items_found"] = len(items)

        logger.info(f"Found {len(items)} items")

        for item in items:
            # Check if hearing already exists
            existing = db.query(Hearing).filter(
                Hearing.source_id == source.id,
                Hearing.external_id == item.external_id
            ).first()

            if existing:
                results["existing_hearings"] += 1
                logger.debug(f"Skipping existing hearing: {item.external_id}")
                continue

            # Infer hearing type from title/categories
            hearing_type = infer_hearing_type(item.title, item.categories)

            # Create new hearing
            hearing = Hearing(
                source_id=source.id,
                state_id=source.state_id,
                external_id=item.external_id,
                title=item.title,
                description=item.description,
                hearing_date=item.pub_date,
                hearing_type=hearing_type,
                source_url=item.link,
                video_url=item.video_url,
                duration_seconds=item.duration_seconds,
                status="discovered",
            )

            if not dry_run:
                db.add(hearing)
                logger.info(f"Added hearing: {item.title[:60]}")
            else:
                logger.info(f"[DRY RUN] Would add: {item.title[:60]}")

            results["new_hearings"] += 1

        # Update source status
        if not dry_run:
            source.last_checked_at = datetime.now(timezone.utc)
            source.status = "active"
            source.error_message = None

            # Update last_hearing_at if we found new hearings
            if results["new_hearings"] > 0 and items:
                latest_item = max(
                    (i for i in items if i.pub_date),
                    key=lambda i: i.pub_date,
                    default=None
                )
                if latest_item and latest_item.pub_date:
                    source.last_hearing_at = datetime.combine(
                        latest_item.pub_date,
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


def main():
    parser = argparse.ArgumentParser(description="Scrape RSS feed sources")
    parser.add_argument("--source-id", type=int, help="Specific source ID to scrape")
    parser.add_argument("--state", help="State code to filter sources (e.g., FL, AZ)")
    parser.add_argument("--dry-run", action="store_true", help="Preview without saving to database")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable debug logging")
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    db = SessionLocal()

    try:
        # Build query for RSS sources
        query = db.query(Source).filter(
            Source.source_type == "rss_feed",
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
            logger.warning("No RSS sources found matching criteria")
            return 0

        logger.info(f"Found {len(sources)} RSS source(s) to scrape")

        total_results = {
            "sources_scraped": 0,
            "total_items": 0,
            "new_hearings": 0,
            "existing_hearings": 0,
            "errors": [],
        }

        for source in sources:
            results = scrape_source(db, source, dry_run=args.dry_run)

            total_results["sources_scraped"] += 1
            total_results["total_items"] += results["items_found"]
            total_results["new_hearings"] += results["new_hearings"]
            total_results["existing_hearings"] += results["existing_hearings"]
            total_results["errors"].extend(results["errors"])

        # Print summary
        print("\n" + "=" * 60)
        print("SCRAPE SUMMARY")
        print("=" * 60)
        print(f"Sources scraped:    {total_results['sources_scraped']}")
        print(f"Items found:        {total_results['total_items']}")
        print(f"New hearings:       {total_results['new_hearings']}")
        print(f"Existing hearings:  {total_results['existing_hearings']}")
        print(f"Errors:             {len(total_results['errors'])}")

        if args.dry_run:
            print("\n[DRY RUN - No changes saved to database]")

        if total_results["errors"]:
            print("\nErrors:")
            for err in total_results["errors"]:
                print(f"  - {err[:100]}")

        return 0 if not total_results["errors"] else 1

    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
