import re
from datetime import datetime

# ISO 8601 format detection (for deserialization when reading from the database)
_ISO_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}"
)

# Chinese date parsing (for MarkAsResolved templates with date-only, no time)
_CN_DATE_RE = re.compile(r"(\d{4})年(\d{1,2})月(\d{1,2})日")

# Match wiki discussion page timestamps, e.g. 2026年3月30日 (一) 20:57 (CST)
_TIMESTAMP_RE = re.compile(
    r"(\d{4})年(\d{1,2})月(\d{1,2})日\s*[（(][^）)]*[）)]\s*(\d{1,2}):(\d{2})"
)

# Match username in signatures
_SIGNATURE_USER_RE = re.compile(
    r"\[\[(?:(?:User|用户|U)[ _]talk|UT):([^|\]]+)(?:\|[^\]]+)?\]\]"
)

def parse_timestamp(raw: str) -> datetime | None:
    """
    Parse a string like '2026年3月30日 (一) 20:57' into a datetime.
    Returns None on failure.
    """
    m = _TIMESTAMP_RE.search(raw)
    if not m:
        return None
    try:
        return datetime(
            int(m.group(1)), int(m.group(2)), int(m.group(3)),
            int(m.group(4)), int(m.group(5)),
        )
    except ValueError:
        return None


def parse_cn_date(raw: str) -> datetime | None:
    """
    Parse a Chinese date string like '2026年4月2日' into a datetime (time defaults to 00:00).
    """
    m = _CN_DATE_RE.search(raw)
    if not m:
        return None
    try:
        return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None

def datetime_to_iso(dt: datetime) -> str | None:
    """Convert datetime to ISO 8601 string for storage. Returns None as-is."""
    if dt is None:
        return
    return dt.isoformat()


def iso_to_datetime(raw: str) -> datetime | None:
    """Convert an ISO 8601 string from the database back to datetime. Returns None for empty/null values."""
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw)
    except (ValueError, TypeError):
        return None