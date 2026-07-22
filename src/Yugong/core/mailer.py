import os
import smtplib
import traceback
from email.header import Header
from email.mime.text import MIMEText

from src.Yugong.core.logger import BotLogger
from src.Yugong.core.settings import settings


class Mailer:
    """
    Email sending module.
    """

    def __init__(self):
        self.mail_account = os.environ.get("MAIL_ACCOUNT")
        self.mail_password = os.environ.get("MAIL_PASSWORD")
        self.logger = BotLogger("mailer")
        self.status = True

        if not self.mail_account or not self.mail_password:
            self.logger.info("Warning: MAIL_ACCOUNT or MAIL_PASSWORD not configured, skipping email")
            self.status = False
            return

    def email(self, subject: str, content: str) -> None:
        """
        Send email via SMTP.

        Args:
            subject: Email subject
            content: Email body
        """

        if not self.status:
            self.logger.info("MAIL_ACCOUNT or MAIL_PASSWORD not configured, skipping email")
            return
        self.logger.info("Sending email...")
        smtp_server = "smtp.office365.com"
        smtp_port = 587

        # Recipients from settings, with env-var override
        recipients = getattr(settings, 'mail_recipients', []) or []

        msg = MIMEText(content, 'plain', 'utf-8')
        msg['From'] = self.mail_account
        msg['To'] = ", ".join(recipients)
        msg['Subject'] = Header(subject, 'utf-8').encode()

        try:
            server = smtplib.SMTP(smtp_server, smtp_port)
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(self.mail_account, self.mail_password)
            server.sendmail(self.mail_account, recipients, msg.as_string())
            server.quit()
            self.logger.info(f"Email sent to: {recipients}")
        except Exception as e:
            self.logger.info(f"Failed to send email: {e}")
            self.logger.error(f"Failed to send email: {e}")
            traceback.print_exc()

mailer = Mailer()