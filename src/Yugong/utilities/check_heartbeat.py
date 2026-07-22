import os

from src.Yugong.core.logger import get_logger
from src.Yugong.core.mailer import mailer


def check_heartbeat(*, file: str, content: str):
    """
    Check if heartbeat file exists; create it if not.
    """
    logger = get_logger(__name__)
    if not os.path.exists(file):
        with open(file, 'w', encoding='utf-8') as f:
            f.write(content)
    else:
        with open(file, 'r', encoding='utf-8') as f:
            last_heartbeat = f.read()

        if last_heartbeat != content:
            with open(file, 'w', encoding='utf-8') as f:
                f.write(content)
            logger.info("Heartbeat file updated")
        else:
            logger.info("Already ran today!")
            logger.error("Already ran today!")
            mailer.email(subject="Yugong duplicate run detected!", content="Yugong appears to have already run today — please check!")
            exit(0)