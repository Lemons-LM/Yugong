from pathlib import Path
from src.Yugong.models.settings import settings
from datetime import datetime
import os

from src.Yugong.utils.path_helper import PROJECT_ROOT


class Logger:
    """
    #TODO: Logger
    Log level (default to 1, in settings.toml default to 3):
        0: No logs at all
        1: Log "Which extension has been used in which page, and processed which page, which errors"  aka log_summary and log_error
        2: Level 1 and "The original and last processed version's contents" aka log_step
        3: Level 1 and "Original and every step of process/extension, for debugging" aka log_step
    auto add a '\n'
    """
    log_path: Path = None

    def __init__(self) -> None:
        time: str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        if os.name == 'nt':
            time = time.replace(":", "-")  # Windows cannot use ':' in file names   
        self.log_path = PROJECT_ROOT / "logs" / time
        self.log_path.mkdir(parents=True, exist_ok=True)
        self.log_summary(f"Yugong program for cleaning legacy syntax of mediawiki log. \nStarting at {time}\n\n")
    
    def _log(self,directory: str,file_name: str, content: str, writing_type:str='a') -> None:
        outputpath: Path=None
        if directory is None:
            outputpath = self.log_path
        else:
            outputpath = self.log_path / directory
            outputpath.mkdir(parents=True, exist_ok=True)
        with open(self.log_path / file_name, writing_type) as f:
            if settings.log_timestamp:
                timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                f.write(f"[{timestamp}] ")
            f.write(content+'\n')
    
    def log_step(self, *, directory: str,file_name: str, content: str, is_debug: bool = False) -> None:
        if (settings.log_level < 2 and not is_debug) or (settings.log_level < 3 and is_debug):
            return
        if not content or not file_name:
            raise ValueError("file_name and content cannot be empty")
        self._log(directory=directory,file_name=file_name, content=content, writing_type='w')

    def log_summary(self, content: str) -> None:
        if settings.log_level < 1:
            return
        self._log(directory=None, file_name="logs.log", content=content, writing_type='a')
    
    def log_error(self, content: str) -> None:
        if settings.log_level < 1:
            return
        self._log(directory=None, file_name="logs.log", content=content, writing_type='a')

logger: Logger = Logger()