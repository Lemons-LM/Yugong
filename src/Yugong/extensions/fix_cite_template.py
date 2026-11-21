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
follows.  Anonymous parameters before the first named parameter are left
untouched, because the source of their pipes cannot be determined safely.
This behaviour is locked down by tests/test_extensions.py.
"""

from __future__ import annotations

import re

import mwparserfromhell as mph

from src.Yugong.core.wikitext import Wikitext
from src.Yugong.utilities.mark_job_intro import intro, job

#: Matches "Cite web", "Cite_web", "Cite book", ...
_CITE_RE = re.compile(r"^Cite[\s_]", re.IGNORECASE)


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


def _rebuild(template: mph.wikicode.Template) -> str:
    """Render *template*, folding fragments into the parameter they follow."""
    fragments = _fragment_indices(template)
    parts = ["{{", str(template.name).strip()]

    for index, param in enumerate(template.params):
        value = str(param.value)
        if param.showkey:
            parts.append(f"|{param.name}={value}")
        elif index in fragments:
            # Attach to the previous parameter's rendered text.
            parts[-1] += f"{{{{!}}}}{value}"
        else:
            parts.append(f"|{value}")

    parts.append("}}")
    return "".join(parts)


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
    for template in wikitext.templates():
        if not _still_attached(wikitext, template):
            continue
        if not _CITE_RE.match(str(template.name).strip()):
            continue
        if not _fragment_indices(template):
            continue

        new_text = _rebuild(template)
        if new_text != str(template):
            wikitext.wikitext.replace(template, new_text)


@intro
def fix_cite_template_intro() -> str:
    return "Fix Cite templates: rejoin fragments split by an unescaped pipe"
