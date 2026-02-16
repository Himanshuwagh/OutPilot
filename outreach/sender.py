"""
Gmail SMTP sender with rate limiting, bounce tracking, and proper headers.
Uses App Password (free, no API needed).
"""

import os
import json
import logging
import random
import smtplib
import time
from datetime import date
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

QUOTA_FILE = Path("./browser_data/quotas/email_sender.json")


class EmailSender:
    def __init__(self):
        self.gmail_email = os.getenv("GMAIL_EMAIL", "")
        self.app_password = os.getenv("GMAIL_APP_PASSWORD", "")

        if not self.gmail_email or not self.app_password:
            raise ValueError("GMAIL_EMAIL and GMAIL_APP_PASSWORD must be set in .env")

        with open("config/settings.yaml") as f:
            cfg = yaml.safe_load(f)["outreach"]
        self.max_per_day = cfg["max_emails_per_day"]
        self.delay_min = cfg["send_delay_min"]
        self.delay_max = cfg["send_delay_max"]

        self.your_name = os.getenv("YOUR_NAME", "")
        self.your_email = self.gmail_email

        self._sent_today = self._load_quota()

    # ------------------------------------------------------------------
    # Quota
    # ------------------------------------------------------------------

    def _load_quota(self) -> int:
        QUOTA_FILE.parent.mkdir(parents=True, exist_ok=True)
        if QUOTA_FILE.exists():
            data = json.loads(QUOTA_FILE.read_text())
            if data.get("date") == date.today().isoformat():
                return data.get("count", 0)
        return 0

    def _save_quota(self) -> None:
        QUOTA_FILE.parent.mkdir(parents=True, exist_ok=True)
        QUOTA_FILE.write_text(
            json.dumps({"date": date.today().isoformat(), "count": self._sent_today})
        )

    def can_send(self) -> bool:
        return self._sent_today < self.max_per_day

    def remaining_today(self) -> int:
        return max(0, self.max_per_day - self._sent_today)

    # ------------------------------------------------------------------
    # Send
    # ------------------------------------------------------------------

    def send(self, to_email: str, subject: str, body: str) -> bool:
        """
        Send a single email. Returns True on success, False on failure.
        """
        if not self.can_send():
            logger.warning("Daily email limit reached (%d). Skipping.", self.max_per_day)
            return False

        if not to_email or "@" not in to_email:
            logger.warning("Invalid email: %s", to_email)
            return False

        msg = MIMEMultipart("alternative")
        msg["From"] = f"{self.your_name} <{self.your_email}>"
        msg["To"] = to_email
        msg["Subject"] = subject
        msg["Reply-To"] = self.your_email

        html_body = body.replace("\n", "<br>")
        html_part = MIMEText(
            f"<html><body><p>{html_body}</p></body></html>", "html"
        )
        text_part = MIMEText(body, "plain")
        msg.attach(text_part)
        msg.attach(html_part)

        try:
            with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=15) as server:
                server.login(self.your_email, self.app_password)
                server.sendmail(self.your_email, to_email, msg.as_string())

            self._sent_today += 1
            self._save_quota()
            logger.info(
                "Sent email to %s (%d/%d today)",
                to_email,
                self._sent_today,
                self.max_per_day,
            )
            return True

        except smtplib.SMTPRecipientsRefused:
            logger.warning("Recipient refused (bounce): %s", to_email)
            return False
        except smtplib.SMTPAuthenticationError:
            logger.error("Gmail auth failed. Check GMAIL_APP_PASSWORD.")
            return False
        except Exception as exc:
            logger.error("Failed to send to %s: %s", to_email, exc)
            return False

    def send_with_delay(self, to_email: str, subject: str, body: str) -> bool:
        """Send with a random delay to avoid spam detection."""
        result = self.send(to_email, subject, body)
        if result:
            delay = random.uniform(self.delay_min, self.delay_max)
            logger.info("Waiting %.0f seconds before next send...", delay)
            time.sleep(delay)
        return result
