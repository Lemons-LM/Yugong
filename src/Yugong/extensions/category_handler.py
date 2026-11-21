"""Normalise category links using the page's ``{{NoteTA}}`` conversion data.

Qiuwen Baike articles declare cross-strait terminology with ``{{NoteTA}}`` and
public conversion groups (``Module:CGroup/*`` / ``Template:CGroup/*``).  This
extension reads that data from the page and rewrites category links to the
Mainland (``zh-cn``) name when the converted category exists on the wiki, then
follows ``{{分类重定向|...}}`` templates.

The conversion rules are parsed from the wiki's own NoteTA/CGroup data — no
built-in term list.  Group data is cached in the ``cgroup`` table of
:mod:`src.Yugong.core.bot_db`; category existence/redirect answers are cached
in the ``category`` table.  Both databases are per-wiki.

OpenCC is still used as a script-level fallback (traditional → simplified) and
is optional: without it, only the NoteTA/CGroup terminology rules apply.
"""

from __future__ import annotations

import re
from typing import Any

import pywikibot

from src.Yugong.core.bot_db import bot_db
from src.Yugong.core.logger import utilities_logger
from src.Yugong.core.wiki import wiki
from src.Yugong.core.wikitext import Wikitext
from src.Yugong.utilities.cgroup_cache import resolve_note_ta_rules
from src.Yugong.utilities.mark_job_intro import intro, job
from src.Yugong.utilities.note_ta import (
    apply_replacements,
    build_replacements,
    parse_note_ta,
)

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
                    "opencc is not installed; category names will only use the "
                    "wiki's NoteTA/CGroup rules, not OpenCC script conversion "
                    "(pip install opencc)"
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


def _resolve_category(name: str) -> str | None:
    """Return the final name for ``Category:<name>``, or ``None`` if missing.

    A category that exists is its own target; one carrying
    ``{{分类重定向|...}}`` resolves to the redirect target.  The answer is cached
    by the *queried* name, which is the converted candidate, so pages with
    different NoteTA groups cannot poison each other's cache.
    """
    cached = bot_db.search(CATEGORY_TABLE, {"title": name})
    if cached:
        target = cached[0].get("target")
        return str(target) if target else None

    cat_page = pywikibot.Page(wiki.site, f"Category:{name}")
    try:
        if not cat_page.exists():
            return None
    except pywikibot.exceptions.APIError as exc:
        # Existence unknown: do not risk rewriting to a red link.
        utilities_logger.warning(f"Could not check Category:{name}: {exc}")
        return None

    try:
        redirect_target, index = _parse_redirect_template(cat_page.text)
    except pywikibot.exceptions.NoPageError:
        return None
    except pywikibot.exceptions.APIError as exc:
        # The category exists but this account may not read its content (some
        # wikis restrict the Category namespace).  Treat it as an ordinary
        # category: the converted name is still the right link target.
        utilities_logger.info(
            f"Category:{name} exists but its text is not readable ({exc}); "
            "treating it as a plain category"
        )
        redirect_target, index = None, ""

    final = redirect_target or name
    bot_db.insert(CATEGORY_TABLE, {
        "title": name,
        "target": final,
        "sort_index": index,
    })
    return final


@job(needs_wiki=True)
def category_handler_job(wikitext: Wikitext) -> None:
    """Process every category link on the page."""
    links = [
        link
        for link in wikitext.wikilinks()
        if any(
            str(link.title).strip().lower().startswith(prefix)
            for prefix in _CATEGORY_PREFIXES
        )
    ]
    if not links:
        return

    # Read NoteTA from the text as it was loaded, before other jobs may have
    # removed the template.
    source = wikitext.original_content or str(wikitext)
    config = parse_note_ta(source)
    rules = resolve_note_ta_rules(config, wiki_obj=wiki, db=bot_db)
    replacements = build_replacements(rules)

    for link in links:
        original_title = str(link.title).strip()
        cat_name = _strip_category_prefix(original_title).strip()
        if not cat_name:
            continue

        converted = apply_replacements(cat_name, replacements)
        converted = _to_zh_hans(converted).strip()

        # Nothing to do when the wiki's own rules leave the name unchanged.
        # This also avoids touching the Category namespace for every link.
        if not converted or converted == cat_name:
            continue

        target = _resolve_category(converted)

        # If the converted name does not exist, fall back to the name on the
        # page (which may itself be a category redirect).
        if target is None:
            target = _resolve_category(cat_name)

        if target and target != cat_name:
            _rewrite_category_link(link, target)


@intro
def category_handler_intro() -> str:
    return (
        "Category handler: NoteTA/CGroup terminology + zh-Hans + redirects "
        "(DB cached)"
    )
