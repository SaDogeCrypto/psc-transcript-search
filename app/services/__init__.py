"""CanaryScope services package."""
from app.services.email import email_service, EmailService
from app.services.notifications import notify_watchlist_users, send_daily_digest

__all__ = [
    "email_service",
    "EmailService",
    "notify_watchlist_users",
    "send_daily_digest",
]
