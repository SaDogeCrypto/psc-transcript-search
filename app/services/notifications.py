"""
Notification service for CanaryScope.

Handles sending notifications when watched dockets are mentioned in hearings.
"""
import logging
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.services.email import email_service

logger = logging.getLogger(__name__)


async def notify_watchlist_users(
    db: Session,
    docket_id: int,
    hearing_id: int,
    mention_summary: str,
) -> int:
    """
    Send notifications to all users watching a docket when it's mentioned in a hearing.

    Returns the number of notifications sent.
    """
    # Get docket and hearing details
    result = db.execute(
        text("""
            SELECT
                d.normalized_id,
                d.company,
                h.title as hearing_title,
                h.hearing_date,
                h.id as hearing_id,
                s.name as state_name
            FROM dockets d
            JOIN hearings h ON h.id = :hearing_id
            JOIN states s ON s.id = h.state_id
            WHERE d.id = :docket_id
        """),
        {"docket_id": docket_id, "hearing_id": hearing_id}
    ).fetchone()

    if not result:
        logger.warning(f"Docket {docket_id} or hearing {hearing_id} not found")
        return 0

    # Get all users watching this docket with notifications enabled
    watchers = db.execute(
        text("""
            SELECT DISTINCT a.email
            FROM user_watchlist w
            JOIN alert_subscriptions a ON a.id = w.user_id
            WHERE w.docket_id = :docket_id
            AND w.notify_on_mention = true
            AND a.enabled = true
        """),
        {"docket_id": docket_id}
    ).fetchall()

    if not watchers:
        logger.info(f"No watchers with notifications for docket {docket_id}")
        return 0

    # Format hearing date
    hearing_date = result.hearing_date
    if hearing_date:
        hearing_date_str = hearing_date.strftime("%B %d, %Y")
    else:
        hearing_date_str = "Date TBD"

    # Send notifications
    sent_count = 0
    hearing_url = f"https://app.canaryscope.com/dashboard/hearings/{result.hearing_id}"

    for watcher in watchers:
        try:
            success = await email_service.send_watchlist_alert(
                to_email=watcher.email,
                docket_id=result.normalized_id,
                docket_company=result.company or "Unknown Company",
                hearing_title=result.hearing_title,
                hearing_date=hearing_date_str,
                summary=mention_summary or "This docket was mentioned in the hearing.",
                hearing_url=hearing_url,
            )
            if success:
                sent_count += 1
        except Exception as e:
            logger.error(f"Failed to notify {watcher.email}: {e}")

    logger.info(f"Sent {sent_count} notifications for docket {docket_id}")
    return sent_count


async def send_daily_digest(db: Session) -> int:
    """
    Send daily digest emails to all subscribed users.

    Returns the number of digests sent.
    """
    today = datetime.utcnow().date()
    date_str = today.strftime("%B %d, %Y")

    # Get all users with digest subscriptions
    subscribers = db.execute(
        text("""
            SELECT id, email, config_json
            FROM alert_subscriptions
            WHERE alert_type = 'daily_digest'
            AND enabled = true
        """)
    ).fetchall()

    sent_count = 0

    for subscriber in subscribers:
        # Get activity for this user's watched dockets
        activities = db.execute(
            text("""
                SELECT
                    h.id as hearing_id,
                    h.title as hearing_title,
                    h.hearing_date as date,
                    s.name as state_name,
                    s.code as state_code,
                    json_agg(json_build_object(
                        'normalized_id', d.normalized_id,
                        'title', d.title
                    )) as dockets_mentioned
                FROM hearings h
                JOIN states s ON s.id = h.state_id
                JOIN hearing_dockets hd ON hd.hearing_id = h.id
                JOIN dockets d ON d.id = hd.docket_id
                JOIN user_watchlist w ON w.docket_id = d.id
                WHERE w.user_id = :user_id
                AND DATE(h.created_at) = :today
                GROUP BY h.id, h.title, h.hearing_date, s.name, s.code
                ORDER BY h.hearing_date DESC
            """),
            {"user_id": subscriber.id, "today": today}
        ).fetchall()

        if not activities:
            continue

        # Convert to dict format
        activity_list = [
            {
                "hearing_id": a.hearing_id,
                "hearing_title": a.hearing_title,
                "date": a.date.strftime("%B %d, %Y") if a.date else "TBD",
                "state_name": a.state_name,
                "state_code": a.state_code,
                "dockets_mentioned": a.dockets_mentioned or [],
            }
            for a in activities
        ]

        try:
            success = await email_service.send_daily_digest(
                to_email=subscriber.email,
                activities=activity_list,
                date_str=date_str,
            )
            if success:
                sent_count += 1
        except Exception as e:
            logger.error(f"Failed to send digest to {subscriber.email}: {e}")

    logger.info(f"Sent {sent_count} daily digests")
    return sent_count
