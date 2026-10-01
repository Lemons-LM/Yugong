"""Records when the current run started, for log correlation."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

#: Set to the current UTC+8 (CST) time by :func:`record_start_time`.
START_TIME: datetime | None = None


def record_start_time() -> datetime:
    """Store and return the current UTC+8 (CST) time."""
    global START_TIME
    START_TIME = datetime.now(timezone(timedelta(hours=8)))
    return START_TIME
