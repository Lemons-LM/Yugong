"""Helpers for building and normalising wiki links and user names."""

from __future__ import annotations

import re

from src.Yugong.core.logger import utilities_logger

_TARGET_ESCAPE_TABLE = str.maketrans({
    "#": "&#35;", "<": "&#60;", ">": "&#62;",
    "[": "&#91;", "]": "&#93;", "|": "&#124;",
    "{": "&#123;", "}": "&#125;",
})

_USER_LINK_RE = re.compile(r"^\[\[(.*)\]\]$")


def clean_inner_link(text: str) -> str:
    """Strip markup from a link target and escape characters illegal in anchors."""
    text = re.sub(r'<span\b[^>]*>.*?</span>', '', text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r'\[\[:?(.*?)\]\]', r'\1', text)
    text = re.sub(r'tl\|(.+)', r'Template link: {{\1}}', text)
    return text.translate(_TARGET_ESCAPE_TABLE)


def make_anchor_link(title: str, link: str) -> str:
    """Format a topic name as ``[[PageName#TopicName|TopicName]]``."""
    link_clean = clean_inner_link(link)
    display = link_clean.replace('Template link: ', '')
    return f"[[{title}#{link_clean}|{display}]]"


def _normalize_user(user: str) -> str | None:
    """Return ``User:<Name>`` for any accepted spelling, or ``None`` if unusable."""
    match = _USER_LINK_RE.match(user)
    if match:
        user = match.group(1)

    user = user.split("|")[0].split("/")[0].split("#")[0].replace("_", " ").strip()

    lowered = user.lower()
    if lowered.startswith("user talk:"):
        name = user[10:]
    elif lowered.startswith("user:"):
        name = user[5:]
    elif ":" not in user:
        name = user
    else:
        utilities_logger.warning(f"Username parsing error: invalid username {user!r}")
        return None

    name = name.strip()
    if not name:
        return None

    # MediaWiki upper-cases the first letter of a title.
    return "User:" + name[0].upper() + name[1:]


def get_user_talk(user: str, pure: bool = False) -> str:
    """Return the user talk page title for *user*, or ``""`` if unparseable.

    Args:
        user: Any of ``Foo``, ``User:Foo``, ``User talk:Foo``, ``[[User:Foo|x]]``.
        pure: Return the bare user name instead of the talk page title.
    """
    normalized = _normalize_user(user)
    if normalized is None:
        return ""
    name = normalized[5:]
    return name if pure else "User talk:" + name


def get_username(user: str, pure: bool = False) -> str:
    """Return ``User:<Name>`` for *user*, or ``""`` if unparseable.

    Args:
        user: Any of ``Foo``, ``User:Foo``, ``User talk:Foo``, ``[[User:Foo|x]]``.
        pure: Return the bare user name without the ``User:`` prefix.
    """
    normalized = _normalize_user(user)
    if normalized is None:
        return ""
    return normalized[5:] if pure else normalized
