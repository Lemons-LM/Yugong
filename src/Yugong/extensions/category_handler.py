"""
Category handler: convert categories to zh-Hans, follow redirect templates,
and cache results in the database to avoid repeated API requests.

When a category name differs from its zh-Hans form, the extension checks the
category page for a ``{{分类重定向|目标分类|分类索引}}`` template.  If found,
the original wikitext category link is rewritten to the redirect target.

All lookups are cached in the ``category`` table of bot_db.
"""

import re

import pywikibot

from src.Yugong.core.bot_db import bot_db
from src.Yugong.core.wiki import wiki
from src.Yugong.core.wikitext import Wikitext
from src.Yugong.utilities.mark_job_intro import job, intro

#TODO: Cr names
# Category namespace prefixes (Chinese + English)
_CATEGORY_PREFIXES = (
    "category:", "catégorie:",
    "分类:", "分類:",
)

# Category redirect template names
_CAT_REDIRECT_NAMES = frozenset({
    "分类重定向", "分類重新導向", "Category redirect",
    "cr", "Catredirect", "Cat-redirect",
})

_CAT_REDIRECT_RE = re.compile(
    r'\{\{(?:分类重定向|分類重新導向|Category redirect|cr|Catredirect|Cat-redirect)'
    r'\s*\|\s*(?P<target>[^|}\n]+?)'
    r'(?:\s*\|\s*(?P<index>[^|}\n]+?))?'
    r'\s*\}\}',
    re.IGNORECASE,
)


def _to_zh_hans(text: str) -> str:
    """Convert *text* to Simplified Chinese (zh-Hans).  No-op if converter unavailable."""
    try:
        import opencc
        converter = opencc.OpenCC("t2s.json")  # Traditional → Simplified
        return converter.convert(text)
    except (ImportError, Exception):
        return text


def _strip_category_prefix(title: str) -> str:
    """Remove the category namespace prefix, returning the bare category name."""
    lowered = title.lower()
    for prefix in _CATEGORY_PREFIXES:
        if lowered.startswith(prefix):
            return title[len(prefix):]
    return title


def _parse_redirect_template(text: str) -> tuple[str | None, str | None]:
    """Return (target_category_name, index) from a redirect template, or (None, None)."""
    m = _CAT_REDIRECT_RE.search(text)
    if m:
        return m.group("target").strip(), (m.group("index") or "").strip()
    return None, None


@job
def category_handler_job(wikitext: Wikitext) -> None:
    """Process all category wikilinks on the page."""

    for link in list(wikitext.wikitext.filter_wikilinks()):
        original_title = str(link.title).strip()
        lowered = original_title.lower()

        # Only process category links
        if not any(lowered.startswith(p) for p in _CATEGORY_PREFIXES):
            continue

        cat_name = _strip_category_prefix(original_title)

        # Check DB cache first
        cached = bot_db.search("category", {"title": cat_name})
        if cached:
            record = cached[0]
            target = record.get("target")
            if target and target != cat_name:
                _rewrite_category_link(link, original_title, target)
            continue

        # Convert to zh-Hans
        zh_hans_name = _to_zh_hans(cat_name)

        target_cat = cat_name  # default: no change
        cat_index = ""

        if zh_hans_name and zh_hans_name != cat_name:
            # Check if the zh-Hans category page has a redirect template
            try:
                cat_page = pywikibot.Page(wiki.site, f"Category:{zh_hans_name}")
                page_text = cat_page.text

                redirect_target, cat_index = _parse_redirect_template(page_text)
                if redirect_target:
                    target_cat = redirect_target
            except Exception:
                pass

        # Record in DB (always, to avoid repeated lookups)
        bot_db.insert("category", {
            "title": cat_name,
            "target": target_cat,
            "sort_index": cat_index,
        })

        # Rewrite the link if the target changed
        if target_cat != cat_name:
            _rewrite_category_link(link, original_title, target_cat)


def _rewrite_category_link(link, original_title: str, target: str) -> None:
    """Update a category wikilink to point to *target* instead of *original_title*."""
    prefix = ""
    for p in _CATEGORY_PREFIXES:
        if original_title.lower().startswith(p):
            prefix = original_title[:len(p)]
            break

    new_title = prefix + target
    # Preserve sort key if present
    split = original_title.split("|", 1)
    if len(split) > 1:
        new_title += "|" + split[1]

    link.title = new_title


@intro
def category_handler_intro() -> str:
    return "Category handler: zh-Hans conversion + redirect following (DB cached)"
