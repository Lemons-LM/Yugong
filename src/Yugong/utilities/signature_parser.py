"""Parsing of wiki discussion timestamps, Chinese dates and ISO 8601 round-trips."""

from __future__ import annotations

import re
from datetime import datetime

# Chinese date parsing (for MarkAsResolved templates with date-only, no time).
_CN_DATE_RE = re.compile(r"(\d{4})年(\d{1,2})月(\d{1,2})日")

# Wiki discussion page timestamps, e.g. 2026年3月30日 (一) 20:57 (CST).
_TIMESTAMP_RE = re.compile(
    r"(\d{4})年(\d{1,2})月(\d{1,2})日\s*[（(][^）)]*[）)]\s*(\d{1,2}):(\d{2})"
)


def parse_timestamp(raw: str) -> datetime | None:
    """Parse ``'2026年3月30日 (一) 20:57 (CST)'`` into a datetime, or ``None``."""
    match = _TIMESTAMP_RE.search(raw)
    if not match:
        return None
    try:
        return datetime(
            int(match.group(1)), int(match.group(2)), int(match.group(3)),
            int(match.group(4)), int(match.group(5)),
        )
    except ValueError:
        return None


def parse_cn_date(raw: str) -> datetime | None:
    """Parse ``'2026年4月2日'`` into a datetime at midnight, or ``None``."""
    match = _CN_DATE_RE.search(raw)
    if not match:
        return None
    try:
        return datetime(int(match.group(1)), int(match.group(2)), int(match.group(3)))
    except ValueError:
        return None


def datetime_to_iso(dt: datetime | None) -> str | None:
    """Serialise a datetime for storage; ``None`` stays ``None``."""
    if dt is None:
        return None
    return dt.isoformat()


def iso_to_datetime(raw: str | None) -> datetime | None:
    """Read back an ISO 8601 string; invalid or empty input becomes ``None``."""
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw)
    except (ValueError, TypeError):
        return None
