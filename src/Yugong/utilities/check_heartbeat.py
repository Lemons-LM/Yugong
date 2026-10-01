"""Daily-run de-duplication for unattended (cron) runs.

The caller stores a per-day token in a heartbeat file.  Reading and writing are
separate on purpose: a run should only claim the day once it has got far enough
to actually start editing, so a failed connection does not consume the day's
quota and block the retry.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone


def heartbeat_content(*, wiki_tag: str, moment: datetime | None = None) -> str:
    """Return the token identifying "run of *wiki_tag* on this UTC day"."""
    moment = moment or datetime.now(timezone.utc)
    return f"{wiki_tag}:{moment:%Y-%m-%d}"


def read_heartbeat(*, file: str | os.PathLike[str]) -> str:
    """Return the stored heartbeat token, or ``""`` when there is none."""
    try:
        with open(os.fspath(file), "r", encoding="utf-8") as f:
            return f.read().strip()
    except (FileNotFoundError, OSError):
        return ""


def heartbeat_matches(*, file: str | os.PathLike[str], content: str) -> bool:
    """Return ``True`` when *content* has already been recorded."""
    return read_heartbeat(file=file) == content


def record_heartbeat(*, file: str | os.PathLike[str], content: str) -> None:
    """Store *content* as this run's heartbeat token."""
    path = os.fspath(file)
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def check_heartbeat(*, file: str | os.PathLike[str], content: str) -> bool:
    """Record *content* and report whether this is the first run today.

    Convenience wrapper for callers that want "check and claim" in one step.

    Returns:
        ``True`` when the heartbeat was missing or different (safe to run),
        ``False`` when it already matches (a duplicate run).
    """
    if heartbeat_matches(file=file, content=content):
        return False
    record_heartbeat(file=file, content=content)
    return True
