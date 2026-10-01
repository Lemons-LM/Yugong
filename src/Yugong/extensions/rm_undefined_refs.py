"""Remove undefined named ``<ref>`` tags.

A page may write ``<ref name="foo" />`` to reuse a citation defined elsewhere on
the *same* page.  When no ``<ref name="foo">...</ref>`` with actual content
exists, that self-closing tag renders as a citation error, so it is removed.
"""

from __future__ import annotations

import mwparserfromhell as mph

from src.Yugong.core.wikitext import Wikitext
from src.Yugong.utilities.mark_job_intro import intro, job


def _get_ref_name(tag: mph.wikicode.Tag) -> str | None:
    """Return the ``name`` attribute of a ``<ref>`` tag, or ``None``."""
    if not tag.has("name"):
        return None
    attribute = tag.get("name")
    if attribute is None:
        return None
    return str(attribute.value).strip().strip('"')


def _ref_has_content(tag: mph.wikicode.Tag) -> bool:
    """Return ``True`` if the ``<ref>`` tag carries a non-empty body."""
    if tag.self_closing:
        return False
    return len(str(tag.contents).strip()) > 0


@job
def rm_undefined_refs_job(wikitext: Wikitext) -> None:
    """Drop self-closing named refs whose name is never defined on the page."""
    defined_names: set[str] = set()
    named_refs: list[tuple[mph.wikicode.Tag, str]] = []

    for tag in wikitext.tags():
        if str(tag.tag).strip().lower() != "ref":
            continue

        name = _get_ref_name(tag)
        if name is None:
            continue

        named_refs.append((tag, name))
        if _ref_has_content(tag):
            defined_names.add(name)

    for tag, name in named_refs:
        if name not in defined_names and not _ref_has_content(tag):
            # Let a failure propagate: a broken removal means a broken extension.
            wikitext.wikitext.remove(tag)


@intro
def rm_undefined_refs_intro() -> str:
    return "Remove <ref name='...' /> tags with no full definition on the page"
