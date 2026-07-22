import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

from src.Yugong.utilities.path_helper import PROJECT_ROOT

_LOGGERS: dict[str, "BotLogger"] = {}
_LOG_DIR = os.path.join(PROJECT_ROOT, "logs")
_FORMATTER = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")


class BotLogger:
    def __init__(self, name: str, level: int = logging.DEBUG):
        self.log_path = os.path.join(_LOG_DIR, f"{name}.log")
        logger_name = f"custom_{self.log_path}"

        self._logger = logging.getLogger(logger_name)
        self._logger.setLevel(level)

        if not self._logger.handlers:
            Path(_LOG_DIR).mkdir(parents=True, exist_ok=True)
            file_handler = RotatingFileHandler(
                self.log_path,
                maxBytes=10 * 1024 * 1024,
                backupCount=5,
                encoding="utf-8"
            )
            file_handler.setFormatter(_FORMATTER)
            self._logger.addHandler(file_handler)

    def __getattr__(self, name):
        return getattr(self._logger, name)


def get_logger(name: str, level: int = logging.DEBUG) -> BotLogger:
    if name not in _LOGGERS:
        _LOGGERS[name] = BotLogger(name, level)
    return _LOGGERS[name]


utilities_logger = get_logger("utilities")
logger = get_logger("Yugong")
