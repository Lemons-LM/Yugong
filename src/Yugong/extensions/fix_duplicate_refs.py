"""Give conflicting repeat definitions of a named ``<ref>`` a unique name.

MediaWiki renders the first definition of a named reference and shows
``同一name以不同内容定义了多次`` for every later definition whose body differs.
Renaming the later definitions to ``<name>-1``, ``<name>-2`` … keeps their
content (each becomes its own footnote) and removes the error.
Identical repeat definitions are left alone: MediaWiki accepts them without an
error.
"""

from __future__ import annotations

import mwparserfromhell as mph

from src.Yugong.core.logger import utilities_logger
from src.Yugong.core.wikitext import Wikitext
from src.Yugong.utilities.mark_job_intro import intro, job
from src.Yugong.utilities.reporter import reporter


def _ref_name(tag: mph.wikicode.Tag) -> str | None:
    """Return the stripped ``name`` attribute, or ``None``."""
    if not tag.has("name"):
        return None
    attribute = tag.get("name")
    if attribute is None:
        return None
    return str(attribute.value).strip().strip('"')


def _ref_group(tag: mph.wikicode.Tag) -> str:
    """Return the stripped ``group`` attribute (empty for the default group)."""
    if not tag.has("group"):
        return ""
    attribute = tag.get("group")
    if attribute is None:
        return ""
    return str(attribute.value).strip().strip('"')


def _ref_body(tag: mph.wikicode.Tag) -> str:
    """Return the stripped body of a non-self-closing ``<ref>``."""
    if tag.self_closing or tag.contents is None:
        return ""
    return str(tag.contents).strip()


def _unique_name(name: str, group: str, used: set[tuple[str, str]], start: int) -> tuple[str, int]:
    """Return the first unused ``<name>-N`` and the counter to try next."""
    counter = start
    while True:
        candidate = f"{name}-{counter}"
        if (group, candidate) not in used:
            return candidate, counter + 1
        counter += 1


@job
def fix_duplicate_refs_job(wikitext: Wikitext) -> None:
    """Rename later conflicting same-name definitions to ``name-1`` etc."""
    refs = [
        tag for tag in wikitext.tags() if str(tag.tag).strip().lower() == "ref"
    ]
    used: set[tuple[str, str]] = set()
    for tag in refs:
        name = _ref_name(tag)
        if name:
            used.add((_ref_group(tag), name))

    first_body: dict[tuple[str, str], str] = {}
    next_suffix: dict[tuple[str, str], int] = {}
    changes: list[tuple[mph.wikicode.Tag, str, str, str]] = []

    for tag in refs:
        name = _ref_name(tag)
        if not name:
            continue
        body = _ref_body(tag)
        if not body:
            continue

        group = _ref_group(tag)
        key = (group, name)
        if key not in first_body:
            first_body[key] = body
            continue
        if body == first_body[key]:
            continue

        new_name, next_suffix[key] = _unique_name(
            name, group, used, next_suffix.get(key, 1)
        )
        used.add((group, new_name))
        changes.append((tag, name, group, new_name))

    for tag, name, group, new_name in changes:
        if not any(node is tag for node in wikitext.wikitext.filter_tags(recursive=True)):
            # An outer ref renamed earlier detached this nested one.
            continue
        attribute = tag.get("name")
        if attribute is None:
            continue
        attribute.value = new_name
        message = (
            f"{wikitext.title}: <ref name={name!r}> defined again with a "
            f"different body; renamed to {new_name!r}"
        )
        utilities_logger.info(message)
        reporter.add("ref", message)


@intro
def fix_duplicate_refs_intro() -> str:
    return (
        "Duplicate refs: rename later same-name <ref> definitions with a "
        "different body to name-1, name-2, …"
    )
