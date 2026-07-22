import re
from datetime import datetime

# ISO 8601 格式检测（用于从数据库读取时反序列化）
_ISO_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}"
)

# 中文日期解析（用于 MarkAsResolved 模板中只有日期无时间的情况）
_CN_DATE_RE = re.compile(r"(\d{4})年(\d{1,2})月(\d{1,2})日")

# 匹配维基讨论页中的时间戳，形如：2026年3月30日 (一) 20:57 (CST)
_TIMESTAMP_RE = re.compile(
    r"(\d{4})年(\d{1,2})月(\d{1,2})日\s*[（(][^）)]*[）)]\s*(\d{1,2}):(\d{2})"
)

# 匹配签名中的用户名
_SIGNATURE_USER_RE = re.compile(
    r"\[\[(?:(?:User|用户|U)[ _]talk|UT):([^|\]]+)(?:\|[^\]]+)?\]\]"
)

def parse_timestamp(raw: str) -> datetime | None:
    """
    将形如 '2026年3月30日 (一) 20:57' 的字符串解析为 datetime。
    解析失败返回 None。
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
    将形如 '2026年4月2日' 的纯中文日期解析为 datetime（时间取 00:00）。
    """
    m = _CN_DATE_RE.search(raw)
    if not m:
        return None
    try:
        return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None

def datetime_to_iso(dt: datetime) -> str | None:
    """将 datetime 转为 ISO 8601 字符串用于存储，None 原样返回。"""
    if dt is None:
        return
    return dt.isoformat()


def iso_to_datetime(raw: str) -> datetime | None:
    """将数据库中 ISO 8601 字符串转回 datetime，None 或空值返回 None。"""
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw)
    except (ValueError, TypeError):
        return None