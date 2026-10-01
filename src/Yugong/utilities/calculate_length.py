"""Effective-length calculation for wikitext.

The rules documented on :func:`effective_length` used to live in the legacy
``models/`` package.  Note that the previous revision built an
``INVISIBLE_RE`` regex by scanning all 0x110000 code points at import time; that
regex was never used and cost roughly a second on every import, so it is gone.
"""

from __future__ import annotations

import re
import string

import mwparserfromhell
from mwparserfromhell.nodes import (
    Comment,
    ExternalLink,
    Heading,
    HTMLEntity,
    Tag,
    Template,
    Text,
    Wikilink,
)

ASCII_HALF: set[str] = set(string.ascii_letters + string.digits)

FILE_PREFIXES: tuple[str, ...] = (
    "file:",
    "image:",
    "文件:",
    "檔案:",
)

CATEGORY_PREFIXES: tuple[str, ...] = (
    "category:",
    "分类:",
    "分類:",
)

#: Zero-width, bidirectional and invisible-operator characters.
INVISIBLE_CHARS: set[str] = {
    # Zero-width
    "\u200B",  # ZERO WIDTH SPACE
    "\u200C",  # ZERO WIDTH NON-JOINER
    "\u200D",  # ZERO WIDTH JOINER
    "\u2060",  # WORD JOINER
    "\uFEFF",  # ZERO WIDTH NO-BREAK SPACE / BOM
    # Bidirectional formatting
    "\u202A",  # LEFT-TO-RIGHT EMBEDDING
    "\u202B",  # RIGHT-TO-LEFT EMBEDDING
    "\u202C",  # POP DIRECTIONAL FORMATTING
    "\u202D",  # LEFT-TO-RIGHT OVERRIDE
    "\u202E",  # RIGHT-TO-LEFT OVERRIDE
    # Bidirectional isolates
    "\u2066",  # LEFT-TO-RIGHT ISOLATE
    "\u2067",  # RIGHT-TO-LEFT ISOLATE
    "\u2068",  # FIRST STRONG ISOLATE
    "\u2069",  # POP DIRECTIONAL ISOLATE
    # Invisible operators
    "\u2061",  # FUNCTION APPLICATION
    "\u2062",  # INVISIBLE TIMES
    "\u2063",  # INVISIBLE SEPARATOR
    "\u2064",  # INVISIBLE PLUS
}

REMOVE_TABLE = str.maketrans("", "", "".join(INVISIBLE_CHARS))

REF_RE = re.compile(r"<ref\b[^>]*?>.*?</ref\s*>|<ref\b[^>]*?/?>", re.I | re.S)
COMMENT_RE = re.compile(r"<!--.*?-->", re.S)
MAGICWORD_RE = re.compile(r"__\w+__")


def has_invisible(text: str) -> bool:
    """Return ``True`` if *text* contains any invisible character."""
    return any(char in INVISIBLE_CHARS for char in text)


def remove_invisible(text: str) -> str:
    """Drop every invisible character from *text*."""
    return text.translate(REMOVE_TABLE)


def strip_invisible(text: str) -> str:
    """Return only the printable, non-whitespace characters of *text*."""
    return "".join(ch for ch in text if ch.isprintable() and not ch.isspace())


def text_length(text: str) -> float:
    """Plain-text length: ASCII letters and digits count as half."""
    total = 0.0
    for char in text:
        if not char.isprintable() or char.isspace():
            continue
        total += 0.5 if char in ASCII_HALF else 1.0
    return total


def code_length(
    code: str | mwparserfromhell.wikicode.Wikicode | list[mwparserfromhell.nodes.Node],
) -> float:
    """Effective length of a ``Wikicode``, a node list or raw wikitext."""
    if isinstance(code, str):
        code = mwparserfromhell.parse(code)

    nodes = code.nodes if isinstance(code, mwparserfromhell.wikicode.Wikicode) else code
    return sum(node_length(node) for node in nodes)


def node_length(node: mwparserfromhell.nodes.Node) -> float:
    """Recursively compute the effective length of a single node."""
    if isinstance(node, Text):
        return text_length(str(node))

    if isinstance(node, Comment):
        return 0

    if isinstance(node, HTMLEntity):
        return 1

    if isinstance(node, Heading):
        return code_length(node.title)

    if isinstance(node, Wikilink):
        title = str(node.title).strip().lower()
        if title.startswith(FILE_PREFIXES) or title.startswith(CATEGORY_PREFIXES):
            return 0
        if node.text:
            return code_length(node.text)
        return code_length(node.title)

    if isinstance(node, ExternalLink):
        return code_length(node.title) if node.title else 0

    if isinstance(node, Template):
        return sum(code_length(param.value) for param in node.params)

    if isinstance(node, Tag):
        if str(node.tag).lower() == "gallery":
            return 0
        if node.contents:
            return code_length(node.contents)
        return 0

    if hasattr(node, "value"):
        return code_length(node.value)

    return 0


def is_infobox(template: Template) -> bool:
    """Return ``True`` for templates with at least 3 named and no anonymous params."""
    named = 0
    unnamed = 0
    for param in template.params:
        if param.showkey:
            named += 1
        else:
            unnamed += 1
    return named >= 3 and unnamed == 0


def remove_top_templates(code: mwparserfromhell.wikicode.Wikicode) -> mwparserfromhell.wikicode.Wikicode:
    """Remove consecutive templates at the top of a page, keeping any Infobox.

    Whitespace and comments are skipped; the first Infobox or the first piece of
    real content stops the removal.
    """
    index = 0
    while index < len(code.nodes):
        node = code.nodes[index]

        if isinstance(node, Comment):
            index += 1
            continue

        if isinstance(node, Text):
            if str(node).strip():
                break
            index += 1
            continue

        if isinstance(node, Template):
            if is_infobox(node):
                break
            del code.nodes[index]
            continue

        break

    return code


def effective_length(wikitext: str) -> float:
    """Effective length of *wikitext*.

    Rules:
        1. ``<ref>...</ref>`` tags are not counted.
        2. Comments and magic words are not counted.
        3. Invisible characters are removed first.
        4. ASCII letters and digits count as 0.5, everything else as 1.
        5. Templates only count their parameter values.
        6. Consecutive top-of-page templates are dropped (until an Infobox).
        7. File and category links are not counted.
    """
    wikitext = REF_RE.sub("", wikitext)
    wikitext = COMMENT_RE.sub("", wikitext)
    wikitext = MAGICWORD_RE.sub("", wikitext)
    wikitext = remove_invisible(wikitext)

    code = mwparserfromhell.parse(wikitext)
    remove_top_templates(code)
    return code_length(code)
