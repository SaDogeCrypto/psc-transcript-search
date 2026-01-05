#!/usr/bin/env python3
"""
CanaryScope Scheduled Tasks Runner

Handles periodic tasks like daily digests and notification processing.
Can be run via cron, Azure Functions Timer Trigger, or Container Apps Jobs.

Usage:
    python scripts/scheduled_tasks.py daily-digest
    python scripts/scheduled_tasks.py process-notifications
    python scripts/scheduled_tasks.py all
"""
import asyncio
import argparse
import logging
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from app.database import SessionLocal
from app.services.notifications import send_daily_digest, notify_watchlist_users

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def run_daily_digest():
    """Send daily digest emails to all subscribed users."""
    logger.info("Starting daily digest task...")

    with SessionLocal() as db:
        count = await send_daily_digest(db)
        logger.info(f"Daily digest complete. Sent {count} emails.")

    return count


async def process_pending_notifications():
    """Process any pending notifications from recent docket mentions."""
    logger.info("Processing pending notifications...")

    with SessionLocal() as db:
        # Find recent hearing-docket links that haven't been notified
        from sqlalchemy import text

        pending = db.execute(text("""
            SELECT
                hd.hearing_id,
                hd.docket_id,
                hd.mention_summary,
                hd.created_at
            FROM hearing_dockets hd
            WHERE hd.created_at > NOW() - INTERVAL '24 hours'
            AND NOT EXISTS (
                SELECT 1 FROM notification_log nl
                WHERE nl.hearing_id = hd.hearing_id
                AND nl.docket_id = hd.docket_id
            )
        """)).fetchall()

        if not pending:
            logger.info("No pending notifications to process.")
            return 0

        total_sent = 0
        for row in pending:
            try:
                count = await notify_watchlist_users(
                    db,
                    docket_id=row.docket_id,
                    hearing_id=row.hearing_id,
                    mention_summary=row.mention_summary or "This docket was mentioned in a hearing.",
                )
                total_sent += count

                # Log the notification (would need notification_log table)
                # For now, just log to console
                logger.info(f"Notified {count} users about docket {row.docket_id} in hearing {row.hearing_id}")

            except Exception as e:
                logger.error(f"Error processing notification: {e}")

        logger.info(f"Notification processing complete. Sent {total_sent} emails.")
        return total_sent


async def run_all_tasks():
    """Run all scheduled tasks."""
    logger.info("Running all scheduled tasks...")

    digest_count = await run_daily_digest()
    notification_count = await process_pending_notifications()

    logger.info(f"All tasks complete. Digest: {digest_count}, Notifications: {notification_count}")
    return {
        "daily_digest": digest_count,
        "notifications": notification_count,
    }


def main():
    parser = argparse.ArgumentParser(description="CanaryScope Scheduled Tasks")
    parser.add_argument(
        "task",
        choices=["daily-digest", "process-notifications", "all"],
        help="Task to run"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Log what would be done without actually sending emails"
    )

    args = parser.parse_args()

    if args.dry_run:
        os.environ["EMAIL_DRY_RUN"] = "true"
        logger.info("DRY RUN MODE - No emails will be sent")

    if args.task == "daily-digest":
        result = asyncio.run(run_daily_digest())
    elif args.task == "process-notifications":
        result = asyncio.run(process_pending_notifications())
    elif args.task == "all":
        result = asyncio.run(run_all_tasks())

    logger.info(f"Task '{args.task}' completed with result: {result}")


if __name__ == "__main__":
    main()
