"""A thin, typed wrapper around :class:`mwparserfromhell.wikicode.Wikicode`.

An extension never has to worry about "has this page been parsed yet": the
:attr:`wikitext` accessor raises a descriptive error instead of handing out
``None``, which is what used to make broken extensions fail in confusing ways.
"""

from __future__ import annotations

import mwparserfromhell as mph


class Wikitext:
    """One wiki page's source text plus the metadata extensions may need."""

    def __init__(self, metadata: dict[str, str]) -> None:
        self.title: str = metadata.get("title", "")
        self.revid: int | None = int(metadata["revid"]) if metadata.get("revid") else None
        self.page_id: int | None = int(metadata["pageid"]) if metadata.get("pageid") else None
        self.namespace: int | None = (
            int(metadata["namespace"]) if metadata.get("namespace") else None
        )
        self.permission: str = metadata.get("permission", "")

        self._original_content: str | None = None
        self.processed_content: str | None = None
        self._wikicode: mph.wikicode.Wikicode | None = None

    def __str__(self) -> str:
        return str(self._wikicode) if self._wikicode is not None else ""

    def __repr__(self) -> str:
        return f"Wikitext(title={self.title!r}, revid={self.revid!r})"

    @property
    def wikitext(self) -> mph.wikicode.Wikicode:
        """The parsed page. Raises if :meth:`parse` has not run yet."""
        if self._wikicode is None:
            raise ValueError(
                f"Wikitext for {self.title!r} has not been parsed: "
                "call Wikitext.parse() before reading .wikitext"
            )
        return self._wikicode

    @property
    def original_content(self) -> str:
        """The page text exactly as it was read from the wiki."""
        return self._original_content if self._original_content is not None else ""

    @property
    def text(self) -> str:
        """The current (possibly modified) wikitext as a plain string."""
        return str(self)

    def parse(self, content: str) -> None:
        """Parse *content* into a :class:`~mwparserfromhell.wikicode.Wikicode`."""
        self._original_content = content
        self.processed_content = content
        self._wikicode = mph.parse(content)

    def update(self, content: str | mph.wikicode.Wikicode) -> None:
        """Replace the page content with *content* (a string or a ``Wikicode``)."""
        if isinstance(content, str):
            self.processed_content = content
            self._wikicode = mph.parse(content)
        elif isinstance(content, mph.wikicode.Wikicode):
            self.processed_content = str(content)
            self._wikicode = content
        else:
            raise TypeError(f"Content must be str or Wikicode, got {type(content).__name__}")

    # ── Convenience accessors for extensions ──────────────────────────

    def templates(self) -> list[mph.wikicode.Template]:
        """All templates on the page (a snapshot, safe to mutate while iterating)."""
        return list(self.wikitext.filter_templates())

    def wikilinks(self) -> list[mph.wikicode.Wikilink]:
        """All internal links on the page (a snapshot)."""
        return list(self.wikitext.filter_wikilinks())

    def tags(self) -> list[mph.wikicode.Tag]:
        """All HTML tags on the page (a snapshot)."""
        return list(self.wikitext.filter_tags())
