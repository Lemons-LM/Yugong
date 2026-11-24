"""Remove named ``<ref>`` tags that have no content and no definition.

A page may write ``<ref name="foo" />`` to reuse a citation defined elsewhere on
the *same* page.  When no ``<ref name="foo">...</ref>`` with actual content
exists, that tag renders as a citation error, so it is removed.  The same is
true for an empty definition (``<ref name="foo"></ref>`` or one containing only
whitespace) and for a ref whose name is empty (``<ref name="" />``).
"""

from __future__ import annotations

import re

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


def _find_parent(
    code: mph.wikicode.Wikicode, target: mph.nodes.Node
) -> mph.wikicode.Wikicode | None:
    """Return the ``Wikicode`` whose direct children include *target*."""
    for node in code.nodes:
        if node is target:
            return code
        if isinstance(node, mph.nodes.Template):
            for param in node.params:
                found = _find_parent(param.value, target)
                if found is not None:
                    return found
        elif isinstance(node, mph.nodes.Tag):
            if node.contents is not None:
                found = _find_parent(node.contents, target)
                if found is not None:
                    return found
        elif isinstance(node, mph.nodes.Wikilink):
            if node.text is not None:
                found = _find_parent(node.text, target)
                if found is not None:
                    return found
        elif isinstance(node, mph.nodes.ExternalLink):
            if node.title is not None:
                found = _find_parent(node.title, target)
                if found is not None:
                    return found
        elif isinstance(node, mph.nodes.Heading):
            found = _find_parent(node.title, target)
            if found is not None:
                return found
        elif isinstance(node, mph.nodes.Argument):
            if node.default is not None:
                found = _find_parent(node.default, target)
                if found is not None:
                    return found
    return None


def _starts_own_line(nodes: list[mph.nodes.Node], index: int) -> bool:
    """Return whether the node at *index* starts its own line."""
    for previous in reversed(nodes[:index]):
        if isinstance(previous, mph.nodes.Text):
            text = str(previous)
            if not text:
                continue
            return text.endswith("\n")
        return False
    return True


def _remove_ref(code: mph.wikicode.Wikicode, tag: mph.wikicode.Tag) -> None:
    """Remove *tag* and, if it occupied a whole line, the extra newline.

    A bare ``<ref ... />`` on its own line is removed together with one of the
    surrounding newlines; otherwise the page gains a blank line, which renders
    as a paragraph break between the remaining footnote markers.
    """
    parent = _find_parent(code, tag)
    if parent is None:
        code.remove(tag)
        return

    nodes = parent.nodes
    index = next(i for i, node in enumerate(nodes) if node is tag)
    starts_line = _starts_own_line(nodes, index)
    next_node = nodes[index + 1] if index + 1 < len(nodes) else None

    parent.remove(tag)

    if not starts_line or not isinstance(next_node, mph.nodes.Text):
        return
    match = re.match(r"[ \t]*\n", str(next_node))
    if match:
        next_node.value = str(next_node)[match.end():]


@job
def rm_undefined_refs_job(wikitext: Wikitext) -> None:
    """Drop contentless named refs whose name is never defined on the page."""
    defined_names: set[str] = set()
    named_refs: list[tuple[mph.wikicode.Tag, str]] = []

    for tag in wikitext.tags():
        if str(tag.tag).strip().lower() != "ref":
            continue

        name = _get_ref_name(tag)
        if name is None:
            continue

        named_refs.append((tag, name))
        # An empty name cannot define anything; otherwise it would collide
        # with every other malformed empty-name ref on the page.
        if name and _ref_has_content(tag):
            defined_names.add(name)

    for tag, name in named_refs:
        if not _ref_has_content(tag) and (not name or name not in defined_names):
            # Let a failure propagate: a broken removal means a broken extension.
            _remove_ref(wikitext.wikitext, tag)


@intro
def rm_undefined_refs_intro() -> str:
    return (
        "Remove named <ref> tags with no content and no full definition "
        "on the page"
    )
