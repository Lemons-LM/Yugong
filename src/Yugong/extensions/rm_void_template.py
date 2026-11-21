"""Remove templates that redirect to ``Template:Void``.

Some maintenance templates are retired by redirecting them to ``Template:Void``,
which renders nothing; pages should stop transcluding them.  ``Template:Void``
currently has over a thousand redirects, so the extension preloads that alias
set from the wiki's ``list=backlinks&blfilterredir=redirects`` API into the
per-wiki ``template`` table.  Direct aliases are then removed without any
per-template API request.

Redirect chains are followed up to :data:`MAX_REDIRECT_DEPTH` levels, so
``Template:A -> Template:B -> Template:Void`` is recognised too.  The alias
snapshot is refreshed after :data:`VOID_ALIAS_TTL_SECONDS`.

Real failures (a network problem, a broken site connection) propagate instead
of being reported as "not a Void template", so a broken run cannot silently
skip work.  A failed alias preload only logs a warning and falls back to the
per-template redirect lookup.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pywikibot

from src.Yugong.core.bot_db import bot_db
from src.Yugong.core.logger import utilities_logger
from src.Yugong.core.wiki import wiki
from src.Yugong.core.wikitext import Wikitext
from src.Yugong.utilities.mark_job_intro import intro, job

#: Normalised redirect target that means "this template renders nothing".
VOID_TARGET: str = "void"

#: Canonical page title.
VOID_TITLE: str = "Template:Void"

#: bot_db table holding template redirect information.
TEMPLATE_TABLE: str = "template"

#: Marker row remembering when the alias snapshot was taken.
VOID_ALIAS_MARKER: str = "__void_aliases__"

#: How long the alias snapshot is trusted.
VOID_ALIAS_TTL_SECONDS: int = 7 * 24 * 60 * 60

#: Maximum redirect levels to follow (A -> B -> Void).
MAX_REDIRECT_DEPTH: int = 5

#: In-process normalised alias set, loaded once per process/day.
_alias_keys: set[str] | None = None
_aliases_loaded: bool = False


def _normalize_title(title: str) -> str:
    """Lower-case, strip whitespace and drop a template namespace prefix."""
    normalized = title.strip().lower().replace("_", " ")
    for prefix in ("template:", "模板:"):
        if normalized.startswith(prefix):
            normalized = normalized[len(prefix):]
            break
    return normalized.strip()


def _is_void_target(title: str) -> bool:
    """Return ``True`` if *title* is some spelling of ``Template:Void``."""
    return _normalize_title(title) == VOID_TARGET


def _cache_keys(name: str) -> tuple[str, ...]:
    """Lookup keys for both ``Foo`` and ``Template:Foo`` spellings."""
    bare = name.strip()
    if bare.lower().startswith(("template:", "模板:")):
        bare = bare.split(":", 1)[1].strip()
    return tuple(dict.fromkeys((bare, f"Template:{bare}")))


def _cached_type(name: str) -> str | None:
    for key in _cache_keys(name):
        rows = bot_db.search(TEMPLATE_TABLE, {"title": key})
        if rows:
            cached = rows[0].get("type")
            if cached in ("void", "normal"):
                return str(cached)
    return None


def _is_fresh(value: object) -> bool:
    if not isinstance(value, str) or not value:
        return False
    try:
        moment = datetime.fromisoformat(value)
    except ValueError:
        return False
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    age = (datetime.now(timezone.utc) - moment).total_seconds()
    return 0 <= age <= VOID_ALIAS_TTL_SECONDS


def _read_alias_rows() -> set[str]:
    rows = bot_db.search(TEMPLATE_TABLE, {"type": "void"})
    return {
        _normalize_title(str(row.get("title", "")))
        for row in rows
        if row.get("title")
    }


def _load_void_aliases() -> None:
    """Populate the ``template`` table with every redirect to ``Template:Void``.

    A failed API call is logged and leaves the cache untouched; callers then use
    the slower per-template redirect lookup.
    """
    global _alias_keys, _aliases_loaded

    if _aliases_loaded:
        return

    marker = bot_db.search(TEMPLATE_TABLE, {"title": VOID_ALIAS_MARKER})
    if marker and _is_fresh(marker[0].get("target")):
        if _alias_keys is None:
            _alias_keys = _read_alias_rows()
        _aliases_loaded = True
        return

    aliases: set[str] = {VOID_TITLE}
    continuation: dict[str, object] = {}

    while True:
        params: dict[str, object] = {
            "action": "query",
            "list": "backlinks",
            "bltitle": VOID_TITLE,
            "blfilterredir": "redirects",
            "blnamespace": 10,
            "bllimit": 500,
            "format": "json",
            "formatversion": 2,
        }
        params.update(continuation)
        data = wiki.api_query(params)
        if data is None:
            utilities_logger.warning(
                "Could not load Template:Void aliases; falling back to "
                "per-template redirect lookups"
            )
            if _alias_keys is None:
                _alias_keys = _read_alias_rows()
            _aliases_loaded = True
            return
        if "error" in data:
            utilities_logger.warning(
                f"Template:Void alias query failed: {data['error']}"
            )
            if _alias_keys is None:
                _alias_keys = _read_alias_rows()
            _aliases_loaded = True
            return

        for page in data.get("query", {}).get("backlinks", []):
            title = page.get("title") if isinstance(page, dict) else None
            if title:
                aliases.add(str(title))

        cont = data.get("continue") or {}
        if not cont.get("blcontinue"):
            break
        continuation = {"blcontinue": cont["blcontinue"]}

    # One row per spelling, so a template invocation ``{{Commonscat}}`` and the
    # page title ``Template:Commonscat`` both hit the persistent cache.
    rows: list[tuple[str, list[object]]] = []
    for title in aliases:
        bare = title.split(":", 1)[1] if ":" in title else title
        for key in dict.fromkeys((title, bare)):
            rows.append(("INSERT INTO template (title, target, type) VALUES (?, ?, ?)",
                         [key, VOID_TITLE, "void"]))

    if bot_db.search(TEMPLATE_TABLE, {"type": "void"}):
        bot_db.delete(TEMPLATE_TABLE, {"type": "void"})
    if rows:
        bot_db.execute_transaction(rows)

    stamp = datetime.now(timezone.utc).isoformat()
    if marker:
        bot_db.update(TEMPLATE_TABLE, {"target": stamp, "type": "meta"},
                      {"title": VOID_ALIAS_MARKER})
    else:
        bot_db.insert(TEMPLATE_TABLE, {
            "title": VOID_ALIAS_MARKER,
            "target": stamp,
            "type": "meta",
        })

    _alias_keys = {_normalize_title(title) for title in aliases}
    _aliases_loaded = True
    utilities_logger.info(
        f"Loaded {len(aliases)} Template:Void aliases into the template cache"
    )


def _is_void_title(title: str) -> bool:
    """Return ``True`` for ``Template:Void`` and any preloaded alias."""
    if _is_void_target(title):
        return True
    if _alias_keys is not None and _normalize_title(title) in _alias_keys:
        return True
    return _cached_type(title) == "void"


def _resolve_redirect_target(name: str) -> str | None:
    """Follow ``Template:<name>``'s redirect chain and return a Void title."""
    page = pywikibot.Page(wiki.site, f"Template:{name}")
    seen: set[str] = set()

    for _ in range(MAX_REDIRECT_DEPTH):
        try:
            if not page.isRedirectPage():
                return None
            target = page.getRedirectTarget()
        except pywikibot.exceptions.NoPageError:
            return None

        title = str(target.title())
        if _is_void_title(title):
            return title

        key = _normalize_title(title)
        if key in seen:
            return None
        seen.add(key)
        page = target

    return None


def _is_void_template(name: str) -> bool:
    """Return ``True`` if ``Template:<name>`` redirects to ``Template:Void``."""
    name = name.strip()
    if name.lower().startswith(("template:", "模板:")):
        name = name.split(":", 1)[1].strip()

    _load_void_aliases()

    if _is_void_title(name):
        return True

    cached = _cached_type(name)
    if cached is not None:
        return cached == "void"

    target = _resolve_redirect_target(name)
    is_void = target is not None and _is_void_title(target)
    row = {
        "title": name,
        "target": target or f"Template:{name}",
        "type": "void" if is_void else "normal",
    }

    existing = bot_db.search(TEMPLATE_TABLE, {"title": name})
    if existing:
        bot_db.update(TEMPLATE_TABLE, row, {"title": name})
    else:
        bot_db.insert(TEMPLATE_TABLE, row)
    return is_void


def _still_attached(wikitext: Wikitext, template: object) -> bool:
    """Return whether *template* is still in the page tree.

    ``wikitext.templates()`` is a snapshot: removing an outer Void template
    detaches a Void template nested inside it, and removing a detached node
    raises ``ValueError``.
    """
    return any(node is template for node in wikitext.wikitext.filter_templates())


@job(needs_wiki=True)
def rm_void_template_job(wikitext: Wikitext) -> None:
    """Remove every template on the page that redirects to ``Template:Void``."""
    for template in wikitext.templates():
        if not _still_attached(wikitext, template):
            continue
        name = str(template.name).strip().replace("_", " ")
        if not name:
            continue
        if _is_void_template(name):
            wikitext.wikitext.remove(template)


@intro
def rm_void_template_intro() -> str:
    return (
        "Remove templates redirecting to Template:Void "
        "(preloaded alias set + chain following + DB cache)"
    )
