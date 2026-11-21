"""Handle the deprecated ``.w`` / ``!w`` / ``-w`` nowrap separator series.

The wiki's ``Template:.w/doc`` says these fragments are only valid when the
whole sequence is wrapped in ``{{nowrap begin}}`` … ``{{nowrap end}}``; it also
recommends replacing a navbox row with an unordered list (navboxes already carry
the ``hlist`` class).

This job therefore only automates the safe, clear case:

* a navbox template parameter named ``list…`` whose value uses ``.w``/``!w``/
  ``-w`` at the top level is converted to an unordered list, with the list
  starting on a new line after ``=``;
* a value that already contains ``nowrap begin``/``nowrap end`` is left alone;
* a value containing a newline inside one item is left alone (a nested list
  needs editorial judgement);
* every other ``.w`` use (inline article text, non-navbox templates, other
  parameters) is left unchanged.

This is intentionally an extension rather than a TOML ``replace`` rule: the
correct output depends on the surrounding template/parameter and on line
breaks.
"""

from __future__ import annotations

import re

import mwparserfromhell as mph

from src.Yugong.core.logger import utilities_logger
from src.Yugong.core.wikitext import Wikitext
from src.Yugong.utilities.mark_job_intro import intro, job
from src.Yugong.utilities.reporter import reporter

SEPARATORS: frozenset[str] = frozenset({".w", "!w", "-w"})
NAVBOX_RE = re.compile(r"navbox|导航框|導航框", re.IGNORECASE)
NOWRAP_NAMES: frozenset[str] = frozenset({"nowrap begin", "nowrap end"})

#: Navbox parameters whose values are rows/lists of items.  ``title`` and
#: ``image`` are deliberately excluded: a bullet list there is not a row.
LIST_PARAMS: tuple[str, ...] = ("list", "group", "above", "below", "列表")


def _template_name(template: mph.wikicode.Template) -> str:
    return str(template.name).strip().lower()


def _is_separator(node: object) -> bool:
    return (
        isinstance(node, mph.nodes.Template)
        and _template_name(node) in SEPARATORS
    )


def _split_items(value: mph.wikicode.Wikicode) -> list[str] | None:
    """Split a navbox list value on top-level separators, or return ``None``.

    ``None`` means "do not touch this value" (no separators, a newline in an
    item, or an empty item list).
    """
    if any(
        isinstance(node, mph.nodes.Template) and _template_name(node) in NOWRAP_NAMES
        for node in value.filter_templates()
    ):
        return None

    segments: list[list[mph.nodes.Node]] = []
    current: list[mph.nodes.Node] = []
    found = False
    for node in value.nodes:
        if _is_separator(node):
            found = True
            segments.append(current)
            current = []
        else:
            current.append(node)
    if not found:
        return None
    segments.append(current)

    items: list[str] = []
    for segment in segments:
        # A bare top-level pipe would become a template parameter separator
        # once the value is rewritten as a list.
        if any(
            isinstance(node, mph.nodes.Text) and "|" in str(node)
            for node in segment
        ):
            return None
        text = "".join(str(node) for node in segment).strip()
        if not text:
            continue
        if "\n" in text:
            return None
        items.append(text)
    return items or None


def _convert_navbox_list(template: mph.wikicode.Template) -> bool:
    changed = False
    for param in template.params:
        name = str(param.name).strip().lower()
        if not name.startswith(LIST_PARAMS):
            continue
        items = _split_items(param.value)
        if not items:
            continue
        param.value = "\n" + "\n".join(f"* {item}" for item in items) + "\n"
        changed = True
    return changed


def _walk(code: mph.wikicode.Wikicode) -> None:
    for node in list(code.nodes):
        if isinstance(node, mph.nodes.Template):
            if NAVBOX_RE.search(_template_name(node)):
                _convert_navbox_list(node)
            for param in node.params:
                _walk(param.value)

        elif isinstance(node, mph.nodes.Tag):
            if node.contents is not None:
                _walk(node.contents)

        elif isinstance(node, mph.nodes.Heading):
            _walk(node.title)

        elif isinstance(node, mph.nodes.Wikilink):
            if node.text is not None:
                _walk(node.text)

        elif isinstance(node, mph.nodes.ExternalLink):
            if node.title is not None:
                _walk(node.title)


@job
def nowrap_fixes_job(wikitext: Wikitext) -> None:
    """Convert navbox ``list*`` values that use the ``.w`` series to lists."""
    _walk(wikitext.wikitext)

    remaining = [
        template
        for template in wikitext.templates()
        if _template_name(template) in SEPARATORS
    ]
    if remaining:
        message = (
            f"{wikitext.title}: {len(remaining)} .w/!w/-w use(s) left for "
            "manual nowrap/list review"
        )
        utilities_logger.info(message)
        reporter.add("nowrap", message)


@intro
def nowrap_fixes_intro() -> str:
    return (
        "Nowrap fixes: convert navbox list parameters using .w/!w/-w into "
        "unordered lists; leave nowrap-wrapped, nested or inline uses unchanged"
    )
