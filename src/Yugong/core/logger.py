"""Logging for YuGong.

Every component writes to its own rotating file under ``<project root>/logs``.
The level and timestamp format come from ``settings.toml`` but are applied
through :func:`configure_logging` rather than at import time, so importing a
module never requires a valid ``settings.toml``.  Dev mode and the unit tests
depend on that.
"""

from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

from src.Yugong.utilities.path_helper import PROJECT_ROOT

#: ``settings.toml`` ``log_level`` -> :mod:`logging` level.
LEVEL_MAP: dict[int, int] = {
    0: logging.CRITICAL,
    1: logging.ERROR,
    2: logging.WARNING,
    3: logging.INFO,
    4: logging.DEBUG,
}

#: Default ``log_level`` from ``settings.toml`` (3 == INFO).
DEFAULT_LOG_LEVEL: int = 3

_LOG_DIR: str = os.path.join(PROJECT_ROOT, "logs")
_LOGGERS: dict[str, BotLogger] = {}

_TIMESTAMP_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
_PLAIN_FORMAT = "%(name)s - %(levelname)s - %(message)s"

# Current logging configuration, mutated by configure_logging().
_config: dict[str, Any] = {
    "level": LEVEL_MAP[DEFAULT_LOG_LEVEL],
    "timestamps": True,
}


def level_from_setting(log_level: int) -> int:
    """Translate a ``settings.toml`` ``log_level`` into a :mod:`logging` level."""
    try:
        return LEVEL_MAP[int(log_level)]
    except (KeyError, TypeError, ValueError):
        raise ValueError(
            f"Invalid log_level {log_level!r}: expected one of "
            f"{sorted(LEVEL_MAP)} (0=CRITICAL, 1=ERROR, 2=WARNING, 3=INFO, 4=DEBUG)"
        ) from None


def _file_formatter() -> logging.Formatter:
    return logging.Formatter(_TIMESTAMP_FORMAT if _config["timestamps"] else _PLAIN_FORMAT)


class BotLogger:
    """Thin wrapper around :class:`logging.Logger` that owns one file handler.

    Unknown attributes are forwarded to the wrapped logger, so
    ``logger.info(...)``, ``logger.critical(...)`` etc. work as expected.
    """

    def __init__(self, name: str, level: int | None = None) -> None:
        self.name = name
        self.log_path = os.path.join(_LOG_DIR, f"{name}.log")
        self._logger = logging.getLogger(f"yugong.{name}")
        self._logger.setLevel(level if level is not None else int(_config["level"]))
        self._logger.propagate = False

        if not self._logger.handlers:
            Path(_LOG_DIR).mkdir(parents=True, exist_ok=True)
            file_handler = RotatingFileHandler(
                self.log_path,
                maxBytes=10 * 1024 * 1024,
                backupCount=5,
                encoding="utf-8",
                # Do not create empty log files just because a module was imported.
                delay=True,
            )
            file_handler.setFormatter(_file_formatter())
            file_handler.setLevel(logging.DEBUG)
            self._logger.addHandler(file_handler)

            console_handler = logging.StreamHandler()
            console_handler.setFormatter(logging.Formatter(_PLAIN_FORMAT))
            console_handler.setLevel(logging.WARNING)
            self._logger.addHandler(console_handler)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._logger, name)


def get_logger(name: str, level: int | None = None) -> BotLogger:
    """Return the (cached) :class:`BotLogger` called *name*."""
    if name not in _LOGGERS:
        _LOGGERS[name] = BotLogger(name, level)
    return _LOGGERS[name]


def configure_logging(
    *,
    log_level: int | None = None,
    log_timestamps: bool | None = None,
) -> None:
    """Apply ``settings.toml`` logging options to every existing logger.

    Args:
        log_level: ``settings.toml`` level (0-4).
        log_timestamps: Whether file records carry a timestamp prefix.
    """
    if log_level is not None:
        _config["level"] = level_from_setting(log_level)
    if log_timestamps is not None:
        _config["timestamps"] = bool(log_timestamps)

    formatter = _file_formatter()
    for bot_logger in _LOGGERS.values():
        bot_logger._logger.setLevel(int(_config["level"]))
        for handler in bot_logger._logger.handlers:
            if isinstance(handler, RotatingFileHandler):
                handler.setFormatter(formatter)


utilities_logger = get_logger("utilities")
logger = get_logger("Yugong")
