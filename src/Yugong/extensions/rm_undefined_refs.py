"""
Remove undefined named <ref> tags.

When a page uses ``<ref name="foo" />`` (self-closing) to reference a full
citation defined elsewhere, but no ``<ref name="foo">...</ref>`` with actual
content exists on the page, the self-closing tag is broken — it produces a
citation error.  This extension removes those orphaned references.

Uses mwparserfromhell for tag parsing to preserve wikitext fidelity.
"""

from src.Yugong.core.wikitext import Wikitext
from src.Yugong.utilities.mark_job_intro import job, intro


def _get_ref_name(tag) -> str | None:
    """Extract the ``name`` attribute from an mwparserfromhell Tag, if any."""
    if not tag.has("name"):
        return None
    attr = tag.get("name")
    if attr is None:
        return None
    return str(attr.value).strip().strip('"')


def _ref_has_content(tag) -> bool:
    """Return True if the <ref> tag has non-empty contents."""
    if tag.self_closing:
        return False
    content = str(tag.contents).strip()
    return len(content) > 0


@job
def rm_undefined_refs_job(wikitext: Wikitext) -> None:
    """
    Find <ref name="..."> tags with no content that have no corresponding
    full definition elsewhere on the page, and remove them.
    """

    # First pass: collect names that DO have a content definition
    defined_names: set[str] = set()
    all_named_refs: list = []

    for tag in wikitext.wikitext.filter_tags():
        if str(tag.tag).strip().lower() != "ref":
            continue

        name = _get_ref_name(tag)
        if name is None:
            continue

        all_named_refs.append((tag, name))

        if _ref_has_content(tag):
            defined_names.add(name)

    # Second pass: remove self-closing refs whose name has no full definition
    removed = 0
    for tag, name in all_named_refs:
        if not _ref_has_content(tag) and name not in defined_names:
            try:
                wikitext.wikitext.remove(tag)
                removed += 1
            except Exception:
                pass


@intro
def rm_undefined_refs_intro() -> str:
    return "Remove <ref name='...' /> tags with no full definition on the page"
