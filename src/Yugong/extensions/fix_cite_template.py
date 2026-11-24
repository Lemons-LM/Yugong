"""Fold unescaped pipes in ``Cite*`` template parameters back into place.

Qiuwen's ``Cite*`` templates take no anonymous (positional) parameters: every
value belongs to a named parameter such as ``url=`` or ``title=``.  A bare
``|`` inside any such value is still read by MediaWiki as a parameter
separator, so the rest of the value ends up as one or more anonymous
parameters::

    {{Cite web|url=http://example.com|Foo|title=Bar}}
    ->
    {{Cite web|url=http://example.com{{!}}Foo|title=Bar}}

    {{Cite web|url=http://x|title=Foo|Bar}}
    ->
    {{Cite web|url=http://x|title=Foo{{!}}Bar}}

Every anonymous parameter is folded back into the named parameter it directly
follows.  Anonymous parameters before the first named parameter cannot be
rejoined safely, so they are removed outright (they would otherwise still
render as ``text ignored`` errors).

A ``Cite*`` template cannot legitimately be nested inside another ``Cite*``
template (the inner call is never rendered as a citation), so such nested
templates are removed from parameter values.  This behaviour is locked down by
tests/test_extensions.py.
"""

from __future__ import annotations

import re

import mwparserfromhell as mph

from src.Yugong.core.wikitext import Wikitext
from src.Yugong.utilities.mark_job_intro import intro, job

#: Matches "Cite web", "Cite_web", "Cite book", ...
_CITE_RE = re.compile(r"^Cite[\s_]", re.IGNORECASE)

#: A rewritten outer ``Cite*`` exposes (and detaches) a nested one, so rescan.
MAX_CITE_PASSES: int = 10


def _fragment_indices(template: mph.wikicode.Template) -> set[int]:
    """Return the positions of anonymous params that continue an earlier one.

    Each anonymous parameter is the tail of the named parameter it directly
    follows: its value was split by an unescaped ``|``.  Anonymous parameters
    before the first named parameter do not qualify.
    """
    indices: set[int] = set()
    previous_is_named = False

    for index, param in enumerate(template.params):
        if param.showkey:
            previous_is_named = True
        elif previous_is_named:
            indices.add(index)

    return indices


def _strip_nested_cites(value: mph.wikicode.Wikicode) -> str:
    """Remove ``Cite*`` templates nested inside a citation parameter.

    MediaWiki never renders a ``Cite*`` call inside another one as a citation,
    so it is never meaningful; dropping it also removes the need to repair its
    anonymous parameters.
    """
    text = str(value)
    if not re.search(r"Cite[\s_]", text, re.IGNORECASE):
        return text

    code = mph.parse(text)
    for nested in list(code.filter_templates(recursive=True)):
        if not _CITE_RE.match(str(nested.name).strip()):
            continue
        try:
            code.remove(nested)
        except ValueError:
            # A detached node was already removed with its parent.
            continue
    return str(code)


def _attach(parts: list[str], value: str) -> None:
    """Append *value* to the previous parameter, escaping the joining pipe."""
    head, separator, tail = parts[-1].partition("=")
    if separator and not tail.strip():
        # The previous parameter has no value; a leading ``{{!}}`` would render
        # a stray pipe.
        parts[-1] = f"{head}={value}"
    else:
        parts[-1] += f"{{{{!}}}}{value}"


def _rebuild(template: mph.wikicode.Template) -> str:
    """Render *template*, folding fragments into the parameter they follow."""
    fragments = _fragment_indices(template)
    parts = ["{{", str(template.name).strip()]

    for index, param in enumerate(template.params):
        if param.showkey:
            value = _strip_nested_cites(param.value)
            parts.append(f"|{param.name}={value}")
        elif index in fragments:
            _attach(parts, _strip_nested_cites(param.value))
        else:
            # Anonymous parameters before the first named one cannot be
            # rejoined safely; drop them.
            continue

    parts.append("}}")
    return "".join(parts)


def _has_leading_anonymous(template: mph.wikicode.Template) -> bool:
    """Return whether the first parameter is anonymous (unfixable)."""
    return bool(template.params) and not template.params[0].showkey


def _has_nested_cite(template: mph.wikicode.Template) -> bool:
    """Return whether a parameter value contains another ``Cite*`` call."""
    for param in template.params:
        for nested in param.value.filter_templates(recursive=True):
            if _CITE_RE.match(str(nested.name).strip()):
                return True
    return False


def _still_attached(wikitext: Wikitext, template: mph.wikicode.Template) -> bool:
    """Return whether *template* is still in the page tree.

    ``wikitext.templates()`` is a snapshot.  Replacing an outer ``Cite*``
    template detaches any ``Cite*`` nested inside it, and replacing a detached
    node raises ``ValueError``.
    """
    return any(node is template for node in wikitext.wikitext.filter_templates())


@job
def fix_cite_template_job(wikitext: Wikitext) -> None:
    """Rejoin parameter fragments split off by an unescaped ``|``."""
    for _ in range(MAX_CITE_PASSES):
        changed = False
        for template in wikitext.templates():
            if not _still_attached(wikitext, template):
                continue
            if not _CITE_RE.match(str(template.name).strip()):
                continue
            if (
                not _fragment_indices(template)
                and not _has_leading_anonymous(template)
                and not _has_nested_cite(template)
            ):
                continue

            new_text = _rebuild(template)
            if new_text != str(template):
                wikitext.wikitext.replace(template, new_text)
                changed = True
        if not changed:
            return


@intro
def fix_cite_template_intro() -> str:
    return (
        "Fix Cite templates: rejoin pipe fragments, drop unusable leading "
        "anonymous params and nested Cite templates"
    )
