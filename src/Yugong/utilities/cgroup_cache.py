"""Fetch, parse and cache the wiki's ``CGroup`` conversion data.

``Module:NoteTA`` resolves ``G1``/``G2``/... by looking for
``Module:CGroup/<name>`` first and then ``Template:CGroup/<name>``.  This module
does the same, caches the parsed rules in the per-wiki SQLite database, and
follows module ``import`` entries recursively.

The cache is keyed by the group name the article asked for (not the redirect
target), so ``G1=LS`` and ``G1=Lifesciences`` are separate entries even though
they resolve to the same page.  Rows expire after :data:`CGROUP_TTL_SECONDS` so
a correction to a CGroup eventually reaches the bot.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Protocol

from src.Yugong.core.logger import utilities_logger
from src.Yugong.utilities.note_ta import (
    NoteTAConfig,
    parse_cgroup_lua,
    parse_cgroup_wikitext,
)

#: bot_db table holding parsed CGroup data.
CGROUP_TABLE: str = "cgroup"

#: How long a parsed CGroup is trusted before it is fetched again.
CGROUP_TTL_SECONDS: int = 7 * 24 * 60 * 60

#: Guard against a pathological import chain.
MAX_IMPORT_DEPTH: int = 6


class _WikiLike(Protocol):
    def api_query(self, params: dict[str, Any]) -> dict[str, Any] | None: ...


class _DBLike(Protocol):
    def search(
        self,
        table: str,
        conditions: dict[str, Any] | None = None,
        columns: list[str] | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]: ...

    def insert(self, table: str, data: dict[str, Any]) -> bool: ...

    def update(
        self, table: str, data: dict[str, Any], conditions: dict[str, Any]
    ) -> bool: ...


class _Missing:
    """Sentinel meaning "the page does not exist" (as opposed to a failure)."""


MISSING = _Missing()


def resolve_note_ta_rules(
    config: NoteTAConfig, *, wiki_obj: _WikiLike, db: _DBLike
) -> list[str]:
    """Return every conversion rule declared by *config* and its groups."""
    rules: list[str] = list(config.local_rules)
    if config.title_rules.strip():
        rules.append(config.title_rules.strip())

    for group in config.groups:
        rules.extend(resolve_group(group, wiki_obj=wiki_obj, db=db))

    return _dedupe(rules)


def resolve_group(
    name: str,
    *,
    wiki_obj: _WikiLike,
    db: _DBLike,
    _visited: set[str] | None = None,
    _depth: int = 0,
) -> list[str]:
    """Return the rules of conversion group *name*, following imports."""
    key = str(name).strip()
    if not key:
        return []

    visited = set() if _visited is None else _visited
    if key in visited or _depth > MAX_IMPORT_DEPTH:
        utilities_logger.warning(f"CGroup import cycle/depth limit at {key!r}")
        return []
    visited.add(key)

    row = _cached(db, key)
    if row is None:
        row = _fetch_and_store(key, wiki_obj=wiki_obj, db=db)

    rules = _as_string_list(row.get("rules"))
    imports = _as_string_list(row.get("imports"))

    for imported in imports:
        rules.extend(
            resolve_group(
                imported,
                wiki_obj=wiki_obj,
                db=db,
                _visited=visited,
                _depth=_depth + 1,
            )
        )

    return _dedupe(rules)


# ── Cache ─────────────────────────────────────────────────────────────


def _cached(db: _DBLike, name: str) -> dict[str, Any] | None:
    rows = db.search(CGROUP_TABLE, {"title": name})
    if not rows:
        return None
    row = rows[0]
    if not _is_fresh(row.get("fetched_at")):
        return None
    return row


def _is_fresh(value: Any) -> bool:
    if not isinstance(value, str) or not value:
        return False
    try:
        fetched_at = datetime.fromisoformat(value)
    except ValueError:
        return False
    if fetched_at.tzinfo is None:
        fetched_at = fetched_at.replace(tzinfo=timezone.utc)
    age = (datetime.now(timezone.utc) - fetched_at).total_seconds()
    return 0 <= age <= CGROUP_TTL_SECONDS


def _fetch_and_store(name: str, *, wiki_obj: _WikiLike, db: _DBLike) -> dict[str, Any]:
    record: dict[str, Any] = {
        "title": name,
        "page_title": "",
        "kind": "missing",
        "revid": "",
        "rules": "[]",
        "imports": "[]",
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }

    for kind, prefix in (("module", "Module:CGroup/"), ("template", "Template:CGroup/")):
        fetched = _fetch_page(wiki_obj, prefix + name)
        if fetched is MISSING:
            continue
        content, revid, page_title = fetched
        if kind == "module":
            rules, imports = parse_cgroup_lua(content)
        else:
            rules, imports = parse_cgroup_wikitext(content)
        record.update(
            page_title=page_title,
            kind=kind,
            revid=revid,
            rules=json.dumps(rules, ensure_ascii=False),
            imports=json.dumps(imports, ensure_ascii=False),
        )
        utilities_logger.info(
            f"CGroup {name!r}: loaded {len(rules)} rule(s) from {page_title}"
        )
        break
    else:
        utilities_logger.info(f"CGroup {name!r}: no module or template found")

    existing = db.search(CGROUP_TABLE, {"title": name})
    if existing:
        db.update(CGROUP_TABLE, record, {"title": name})
    else:
        db.insert(CGROUP_TABLE, record)
    return record


def _fetch_page(wiki_obj: _WikiLike, title: str) -> Any:
    """Return ``(content, revid, resolved_title)``, ``MISSING``, or raise."""
    data = wiki_obj.api_query(
        {
            "action": "query",
            "titles": title,
            "prop": "revisions",
            "rvprop": "content|ids",
            "rvslots": "main",
            "redirects": 1,
            "format": "json",
            "formatversion": 2,
        }
    )
    if data is None:
        raise RuntimeError(f"Could not query {title}; see logs/wiki.log")
    if "error" in data:
        raise RuntimeError(f"The wiki API rejected {title}: {data['error']}")

    query = data.get("query", {})
    pages = query.get("pages") if isinstance(query, dict) else None
    if isinstance(pages, dict):
        page = next(iter(pages.values()), None)
    elif isinstance(pages, list):
        page = pages[0] if pages else None
    else:
        page = None

    if not isinstance(page, dict) or page.get("missing"):
        return MISSING

    revisions = page.get("revisions")
    if not revisions:
        return MISSING
    revision = revisions[0]

    content = _revision_content(revision)
    if content is None:
        return MISSING

    return content, str(revision.get("revid", "")), str(page.get("title", title))


def _revision_content(revision: dict[str, Any]) -> str | None:
    slots = revision.get("slots")
    if isinstance(slots, dict):
        main = slots.get("main")
        if isinstance(main, dict) and isinstance(main.get("content"), str):
            return str(main["content"])
    for key in ("content", "*"):
        value = revision.get(key)
        if isinstance(value, str):
            return str(value)
    return None


# ── Helpers ───────────────────────────────────────────────────────────


def _as_string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if item]
    if isinstance(value, str) and value:
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return []
        if isinstance(parsed, list):
            return [str(item) for item in parsed if item]
    return []


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result
