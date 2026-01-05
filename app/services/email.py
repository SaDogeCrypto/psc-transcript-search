"""
Email notification service for CanaryScope alerts.

Supports multiple providers:
- Azure Communication Services (default for production)
- SMTP (fallback/development)
- Console (development/testing)
"""
import os
import logging
from abc import ABC, abstractmethod
from typing import Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class EmailMessage:
    """Email message structure."""
    to: str
    subject: str
    html_body: str
    text_body: Optional[str] = None
    from_email: Optional[str] = None


class EmailProvider(ABC):
    """Abstract base class for email providers."""

    @abstractmethod
    async def send(self, message: EmailMessage) -> bool:
        """Send an email message."""
        pass


class ConsoleEmailProvider(EmailProvider):
    """Console-based email provider for development."""

    async def send(self, message: EmailMessage) -> bool:
        logger.info(f"[EMAIL] To: {message.to}")
        logger.info(f"[EMAIL] Subject: {message.subject}")
        logger.info(f"[EMAIL] Body: {message.text_body or message.html_body[:200]}...")
        return True


class AzureEmailProvider(EmailProvider):
    """Azure Communication Services email provider for production."""

    def __init__(self, connection_string: str, sender_address: str):
        self.connection_string = connection_string
        self.sender_address = sender_address

    async def send(self, message: EmailMessage) -> bool:
        try:
            from azure.communication.email import EmailClient

            client = EmailClient.from_connection_string(self.connection_string)

            email_message = {
                "senderAddress": message.from_email or self.sender_address,
                "recipients": {
                    "to": [{"address": message.to}]
                },
                "content": {
                    "subject": message.subject,
                    "html": message.html_body,
                }
            }

            if message.text_body:
                email_message["content"]["plainText"] = message.text_body

            poller = client.begin_send(email_message)
            result = poller.result()

            logger.info(f"Azure email sent: {result.message_id}")
            return True

        except ImportError:
            logger.error("azure-communication-email package not installed. Run: pip install azure-communication-email")
            return False
        except Exception as e:
            logger.error(f"Azure email failed: {e}")
            return False


class SMTPEmailProvider(EmailProvider):
    """SMTP email provider."""

    def __init__(self, host: str, port: int, username: str, password: str):
        self.host = host
        self.port = port
        self.username = username
        self.password = password

    async def send(self, message: EmailMessage) -> bool:
        try:
            import smtplib
            from email.mime.text import MIMEText
            from email.mime.multipart import MIMEMultipart

            msg = MIMEMultipart("alternative")
            msg["Subject"] = message.subject
            msg["From"] = message.from_email or self.username
            msg["To"] = message.to

            if message.text_body:
                msg.attach(MIMEText(message.text_body, "plain"))
            msg.attach(MIMEText(message.html_body, "html"))

            with smtplib.SMTP(self.host, self.port) as server:
                server.starttls()
                server.login(self.username, self.password)
                server.send_message(msg)

            return True
        except Exception as e:
            logger.error(f"SMTP email failed: {e}")
            return False


class EmailService:
    """Email service with provider abstraction."""

    def __init__(self):
        self.provider = self._get_provider()

    def _get_provider(self) -> EmailProvider:
        """Get the appropriate email provider based on environment."""
        # Azure Communication Services (preferred)
        azure_conn_string = os.getenv("AZURE_COMMUNICATION_CONNECTION_STRING")
        azure_sender = os.getenv("AZURE_EMAIL_SENDER", "DoNotReply@canaryscope.com")
        if azure_conn_string:
            return AzureEmailProvider(azure_conn_string, azure_sender)

        # SMTP fallback
        smtp_host = os.getenv("SMTP_HOST")
        if smtp_host:
            return SMTPEmailProvider(
                host=smtp_host,
                port=int(os.getenv("SMTP_PORT", "587")),
                username=os.getenv("SMTP_USERNAME", ""),
                password=os.getenv("SMTP_PASSWORD", ""),
            )

        # Console for development
        return ConsoleEmailProvider()

    async def send_watchlist_alert(
        self,
        to_email: str,
        docket_id: str,
        docket_company: str,
        hearing_title: str,
        hearing_date: str,
        summary: str,
        hearing_url: str,
    ) -> bool:
        """Send a watchlist alert email."""
        subject = f"[CanaryScope] New activity on {docket_id}"

        html_body = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background: #2563eb; color: white; padding: 20px; border-radius: 8px 8px 0 0; }}
                .content {{ background: #f9fafb; padding: 20px; border: 1px solid #e5e7eb; }}
                .docket {{ font-family: monospace; font-size: 18px; font-weight: bold; }}
                .hearing {{ background: white; padding: 15px; border-radius: 8px; margin: 15px 0; border: 1px solid #e5e7eb; }}
                .btn {{ display: inline-block; background: #2563eb; color: white; padding: 12px 24px; text-decoration: none; border-radius: 6px; margin-top: 15px; }}
                .footer {{ padding: 20px; color: #6b7280; font-size: 12px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1 style="margin: 0;">New Hearing Activity</h1>
                </div>
                <div class="content">
                    <p>A docket you're watching was mentioned in a new hearing:</p>

                    <div class="hearing">
                        <div class="docket">{docket_id}</div>
                        <div style="color: #6b7280; margin-top: 5px;">{docket_company}</div>
                        <hr style="border: none; border-top: 1px solid #e5e7eb; margin: 15px 0;">
                        <div style="font-weight: 600;">{hearing_title}</div>
                        <div style="color: #6b7280; font-size: 14px; margin-top: 5px;">{hearing_date}</div>
                        <p style="margin-top: 10px;">{summary}</p>
                    </div>

                    <a href="{hearing_url}" class="btn">View Hearing Details</a>
                </div>
                <div class="footer">
                    <p>You're receiving this because you're watching {docket_id} on CanaryScope.</p>
                    <p><a href="#">Manage notification settings</a> | <a href="#">Unsubscribe</a></p>
                </div>
            </div>
        </body>
        </html>
        """

        text_body = f"""
New Hearing Activity on CanaryScope

Docket: {docket_id}
Company: {docket_company}

Hearing: {hearing_title}
Date: {hearing_date}

Summary:
{summary}

View details: {hearing_url}

---
You're receiving this because you're watching {docket_id}.
        """

        message = EmailMessage(
            to=to_email,
            subject=subject,
            html_body=html_body,
            text_body=text_body,
        )

        return await self.provider.send(message)

    async def send_daily_digest(
        self,
        to_email: str,
        activities: list[dict],
        date_str: str,
    ) -> bool:
        """Send a daily digest email."""
        if not activities:
            return True

        subject = f"[CanaryScope] Daily Digest - {date_str}"

        activities_html = ""
        for activity in activities:
            activities_html += f"""
            <div style="background: white; padding: 15px; border-radius: 8px; margin: 10px 0; border: 1px solid #e5e7eb;">
                <div style="font-weight: 600;">{activity['hearing_title']}</div>
                <div style="color: #6b7280; font-size: 14px;">{activity['state_name']} | {activity['date']}</div>
                <div style="margin-top: 8px;">
                    {''.join(f'<span style="background: #dbeafe; color: #1e40af; padding: 2px 8px; border-radius: 4px; font-size: 12px; margin-right: 5px;">{d["normalized_id"]}</span>' for d in activity.get('dockets_mentioned', []))}
                </div>
            </div>
            """

        html_body = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background: #2563eb; color: white; padding: 20px; border-radius: 8px 8px 0 0; }}
                .content {{ background: #f9fafb; padding: 20px; border: 1px solid #e5e7eb; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1 style="margin: 0;">Daily Digest</h1>
                    <p style="margin: 5px 0 0 0; opacity: 0.9;">{date_str}</p>
                </div>
                <div class="content">
                    <p>{len(activities)} new hearing(s) from your watched dockets:</p>
                    {activities_html}
                    <a href="https://app.canaryscope.com/dashboard" style="display: inline-block; background: #2563eb; color: white; padding: 12px 24px; text-decoration: none; border-radius: 6px; margin-top: 15px;">View Dashboard</a>
                </div>
            </div>
        </body>
        </html>
        """

        message = EmailMessage(
            to=to_email,
            subject=subject,
            html_body=html_body,
        )

        return await self.provider.send(message)


# Singleton instance
email_service = EmailService()
