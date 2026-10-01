"""Normalise category links: convert to zh-Hans and follow category redirects.

When a category name differs from its Simplified-Chinese form, the extension
looks up the zh-Hans category page.  If that page carries a
``{{分类重定向|目标分类|分类索引}}`` template, the link on the article is
rewritten to the redirect target.

Lookups are cached in the ``category`` table of :mod:`src.Yugong.core.bot_db`,
so each category is resolved once per machine.  OpenCC is optional: without it
the redirect lookup is simply skipped.
"""

from __future__ import annotations

import re
from typing import Any

import pywikibot

from src.Yugong.core.bot_db import bot_db
from src.Yugong.core.logger import utilities_logger
from src.Yugong.core.wiki import wiki
from src.Yugong.core.wikitext import Wikitext
from src.Yugong.utilities.mark_job_intro import intro, job

#: bot_db table holding category redirect information.
CATEGORY_TABLE: str = "category"

#: Category namespace prefixes (Chinese + English + French).
_CATEGORY_PREFIXES: tuple[str, ...] = (
    "category:", "catégorie:",
    "分类:", "分類:",
)

_CAT_REDIRECT_RE = re.compile(
    r'\{\{(?:分类重定向|分類重新導向|Category redirect|cr|Catredirect|Cat-redirect)'
    r'\s*\|\s*(?P<target>[^|}\n]+?)'
    r'(?:\s*\|\s*(?P<index>[^|}\n]+?))?'
    r'\s*\}\}',
    re.IGNORECASE,
)

# OpenCC is an optional dependency; build the converter once and warn once.
_converter: Any = None
_converter_missing_reported = False


def _to_zh_hans(text: str) -> str:
    """Convert *text* to Simplified Chinese, or return it unchanged."""
    global _converter, _converter_missing_reported

    if _converter is None:
        try:
            import opencc
        except ImportError:
            if not _converter_missing_reported:
                utilities_logger.warning(
                    "opencc is not installed; category names will not be "
                    "converted to zh-Hans (pip install opencc)"
                )
                _converter_missing_reported = True
            return text
        _converter = opencc.OpenCC("t2s.json")  # Traditional -> Simplified

    return str(_converter.convert(text))


def _strip_category_prefix(title: str) -> str:
    """Return the bare category name without its namespace prefix."""
    lowered = title.lower()
    for prefix in _CATEGORY_PREFIXES:
        if lowered.startswith(prefix):
            return title[len(prefix):]
    return title


def _category_prefix(title: str) -> str:
    """Return the namespace prefix *title* uses, preserving its spelling."""
    lowered = title.lower()
    for prefix in _CATEGORY_PREFIXES:
        if lowered.startswith(prefix):
            return title[:len(prefix)]
    return ""


def _parse_redirect_template(text: str) -> tuple[str | None, str]:
    """Return ``(target, index)`` from a category-redirect template."""
    match = _CAT_REDIRECT_RE.search(text)
    if not match:
        return None, ""
    return match.group("target").strip(), (match.group("index") or "").strip()


def _rewrite_category_link(link: Any, target: str) -> None:
    """Point a category wikilink at *target*.

    Only ``link.title`` changes.  The sort key of ``[[Category:A|key]]`` lives in
    ``link.text``, so it is preserved automatically.
    """
    original_title = str(link.title).strip()
    link.title = _category_prefix(original_title) + target


@job(needs_wiki=True)
def category_handler_job(wikitext: Wikitext) -> None:
    """Process every category link on the page."""
    for link in wikitext.wikilinks():
        original_title = str(link.title).strip()
        lowered = original_title.lower()

        if not any(lowered.startswith(prefix) for prefix in _CATEGORY_PREFIXES):
            continue

        cat_name = _strip_category_prefix(original_title).strip()
        if not cat_name:
            continue

        cached = bot_db.search(CATEGORY_TABLE, {"title": cat_name})
        if cached:
            target = cached[0].get("target")
            if target and target != cat_name:
                _rewrite_category_link(link, str(target))
            continue

        zh_hans_name = _to_zh_hans(cat_name)
        target_cat = cat_name
        cat_index = ""

        if zh_hans_name and zh_hans_name != cat_name:
            cat_page = pywikibot.Page(wiki.site, f"Category:{zh_hans_name}")
            redirect_target: str | None = None
            try:
                redirect_target, cat_index = _parse_redirect_template(cat_page.text)
            except pywikibot.exceptions.NoPageError:
                redirect_target = None
            if redirect_target:
                target_cat = redirect_target

        bot_db.insert(CATEGORY_TABLE, {
            "title": cat_name,
            "target": target_cat,
            "sort_index": cat_index,
        })

        if target_cat != cat_name:
            _rewrite_category_link(link, target_cat)


@intro
def category_handler_intro() -> str:
    return "Category handler: zh-Hans conversion + redirect following (DB cached)"
