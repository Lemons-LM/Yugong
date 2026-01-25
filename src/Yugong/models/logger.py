from pathlib import Path
from datetime import datetime

from src.Yugong.utils.path_helper import PROJECT_ROOT


class Logger:
    """
    #TODO: Logger
    Log level (default to 1, in settings.toml default to 3):
        0: No logs at all
        1: Log "Which extension has been used in which page, and processed which page, which errors"
        2: Leven 1 and "The original and last processed version's contents"
        3: Level 1 and "Original and every step of process/extension, for debugging"
    """
    log_path: Path = None

    def __init__(self):
        time: str = f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        self.log_path = PROJECT_ROOT / "logs" / time
        self.log_path.mkdir(parents=True, exist_ok=True)
        self.log_summary(f"Yugong program for cleaning legacy syntax of mediawiki log. \nStarting at {time}\n\n")

    def log_step(self, *, directory: str,file_name: str, content: str):
        if not content or not file_name:
            raise ValueError("file_name and content cannot be empty")
        # 在打开文件前创建目录
        (self.log_path / directory).mkdir(parents=True, exist_ok=True)
        with open(self.log_path / directory / f"{file_name}.log", "w") as f:
            f.write(content)

    def log_summary(self, content: str):
        with open(self.log_path / "logs.log", "a") as f:
            f.write(content)




logger: Logger = Logger()
