import os

from src.Yugong.core.logger import get_logger
from src.Yugong.core.mailer import mailer


def check_heartbeat(*, file: str, content: str):
    """
    检查心跳文件是否存在，不存在则创建
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
            logger.info(f"已更新心跳文件")
        else:
            logger.info(f"今日已运行过！")
            logger.error("今日已运行过！")
            mailer.email(subject="Yugong出现了重复运行的问题！", content="Yugong出现了重复运行的问题，请检查！")
            exit(0)