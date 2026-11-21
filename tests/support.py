"""Shared helpers for the YuGong test suite."""

from __future__ import annotations

from typing import Any, Callable

from src.Yugong.core.wikitext import Wikitext


def make_wikitext(text: str, *, title: str = "Test page") -> Wikitext:
    """Parse *text* into a :class:`Wikitext` with minimal metadata."""
    wikitext = Wikitext({"title": title, "pageid": "1", "revid": "1", "namespace": "0"})
    wikitext.parse(text)
    return wikitext


def run_job(job: Callable[..., Any], text: str, *, title: str = "Test page") -> str:
    """Run a single ``@job`` function over *text* and return the result."""
    wikitext = make_wikitext(text, title=title)
    job(wikitext)
    return str(wikitext)


class FakeBotDB:
    """In-memory stand-in for :class:`BotDB` so tests never touch SQLite."""

    def __init__(self) -> None:
        self.rows: dict[str, list[dict[str, Any]]] = {}

    def insert(self, table: str, data: dict[str, Any]) -> bool:
        self.rows.setdefault(table, []).append(dict(data))
        return True

    def update(
        self,
        table: str,
        data: dict[str, Any],
        conditions: dict[str, Any],
    ) -> bool:
        changed = False
        for row in self.rows.get(table, []):
            if all(row.get(key) == value for key, value in conditions.items()):
                row.update(data)
                changed = True
        return changed

    def search(
        self,
        table: str,
        conditions: dict[str, Any] | None = None,
        **_kwargs: Any,
    ) -> list[dict[str, Any]]:
        rows = self.rows.get(table, [])
        if not conditions:
            return [dict(row) for row in rows]
        return [
            dict(row)
            for row in rows
            if all(row.get(key) == value for key, value in conditions.items())
        ]
