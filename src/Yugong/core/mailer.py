import os
import smtplib
import traceback
from email.header import Header
from email.mime.text import MIMEText

from src.Yugong.core.logger import BotLogger


class Mailer:
    """
    邮件发送模块
    """

    def __init__(self):
        self.mail_account = os.environ.get("MAIL_ACCOUNT")
        self.mail_password = os.environ.get("MAIL_PASSWORD")
        self.logger = BotLogger("mailer")
        self.status = True

        if not self.mail_account or not self.mail_password:
            self.logger.info("警告：未配置 MAIL_ACCOUNT 或 MAIL_PASSWORD 环境变量，跳过邮件发送")
            self.status = False
            return

    def email(self, subject: str, content: str) -> None:
        """
        通过 SMTP 发送邮件

        Args:
            subject: 邮件主题
            content: 邮件内容
        """

        if not self.status:
            self.logger.info("未配置 MAIL_ACCOUNT 或 MAIL_PASSWORD 环境变量，跳过邮件发送")
            return
        self.logger.info("正在发送邮件...")
        smtp_server = "smtp.office365.com"
        smtp_port = 587

        # 收件人列表，可以从环境变量获取或硬编码
        recipients = ["contact@frontiers.ac"]

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
            self.logger.info(f"邮件已发送至: {recipients}")
        except Exception as e:
            self.logger.info(f"发送邮件失败: {e}")
            self.logger.error(f"发送邮件失败: {e}")
            traceback.print_exc()

mailer = Mailer()