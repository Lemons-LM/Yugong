"""SMTP alerts (bot suppressed, duplicate run, end-of-run report).

Email is entirely optional: without ``MAIL_ACCOUNT``/``MAIL_PASSWORD`` in the
environment the mailer turns itself off and every call becomes a log line.
"""

from __future__ import annotations

import os
import smtplib
import ssl
import traceback
from email.header import Header
from email.mime.text import MIMEText

from src.Yugong.core.logger import BotLogger
from src.Yugong.core.settings import settings

SMTP_SERVER: str = "smtp.office365.com"
SMTP_PORT: int = 587


class Mailer:
    """Send plain-text alert emails through SMTP."""

    def __init__(self) -> None:
        self.mail_account: str | None = os.environ.get("MAIL_ACCOUNT")
        self.mail_password: str | None = os.environ.get("MAIL_PASSWORD")
        self.logger = BotLogger("mailer")
        self.status: bool = True

        if not self.mail_account or not self.mail_password:
            self.logger.info(
                "MAIL_ACCOUNT or MAIL_PASSWORD not configured, skipping email"
            )
            self.status = False

    def recipients(self) -> list[str]:
        """Configured recipients, always a list."""
        configured = getattr(settings, "mail_recipients", None) or []
        return [str(address) for address in configured]

    def email(self, subject: str, content: str) -> None:
        """Send *content* to every configured recipient. Never raises."""
        if not self.status or not self.mail_account or not self.mail_password:
            self.logger.info(f"Email disabled, not sending: {subject}")
            return

        recipients = self.recipients()
        if not recipients:
            self.logger.info(f"No mail_recipients configured, not sending: {subject}")
            return

        msg = MIMEText(content, "plain", "utf-8")
        msg["From"] = self.mail_account
        msg["To"] = ", ".join(recipients)
        msg["Subject"] = Header(subject, "utf-8").encode()

        try:
            # A hard timeout: a final report must never hang a cron job.
            with smtplib.SMTP(
                SMTP_SERVER, SMTP_PORT, timeout=max(1, int(settings.request_timeout))
            ) as server:
                server.ehlo()
                # Without an explicit context, smtplib uses an unverified
                # SSLContext (check_hostname=False, verify_mode=0), so a MITM
                # could harvest MAIL_PASSWORD.
                server.starttls(context=ssl.create_default_context())
                server.ehlo()
                server.login(self.mail_account, self.mail_password)
                server.sendmail(self.mail_account, recipients, msg.as_string())
            self.logger.info(f"Email sent to: {recipients}")
        except Exception as exc:  # noqa: BLE001 - alerts must never break a run
            self.logger.error(f"Failed to send email: {exc}")
            traceback.print_exc()


mailer = Mailer()
