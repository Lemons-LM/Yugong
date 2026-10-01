"""Fix unnamed-parameter pipe ambiguity in Cite-* templates.

Qiuwen's ``Cite*`` templates are called with anonymous (positional) parameters
whose first value is a URL.  A bare ``|`` inside such a value would be read by
MediaWiki as the next parameter separator, so everything after the first
anonymous parameter is joined onto it with ``{{!}}`` instead::

    {{Cite web|http://example.com|Foo|title=Bar}}
    ->
    {{Cite web|http://example.com{{!}}Foo|title=Bar}}

The first anonymous parameter keeps its plain ``|`` because that pipe is the
template-name separator.  This behaviour is deliberate and locked down by
tests/test_extensions.py.
"""

from __future__ import annotations

import re

import mwparserfromhell as mph

from src.Yugong.core.wikitext import Wikitext
from src.Yugong.utilities.mark_job_intro import intro, job

#: Matches "Cite web", "Cite_web", "Cite book", ...
_CITE_RE = re.compile(r"^Cite[\s_]", re.IGNORECASE)


def _needs_escape(template: mph.wikicode.Template) -> bool:
    """Return ``True`` if *template* has at least one anonymous parameter."""
    return any(not param.showkey for param in template.params)


def _rebuild(template: mph.wikicode.Template) -> str:
    """Render *template*, joining later anonymous parameters with ``{{!}}``."""
    parts = ["{{", str(template.name).strip()]
    seen_anonymous = False

    for param in template.params:
        value = str(param.value)
        if param.showkey:
            parts.append(f"|{param.name}={value}")
        elif not seen_anonymous:
            # The first pipe after the template name is a real separator.
            parts.append(f"|{value}")
            seen_anonymous = True
        else:
            parts.append(f"{{{{!}}}}{value}")

    parts.append("}}")
    return "".join(parts)


@job
def fix_cite_template_job(wikitext: Wikitext) -> None:
    """Rewrite every ``Cite*`` template that has anonymous parameters."""
    for template in wikitext.templates():
        if not _CITE_RE.match(str(template.name).strip()):
            continue
        if not _needs_escape(template):
            continue

        new_text = _rebuild(template)
        if new_text != str(template):
            wikitext.wikitext.replace(template, new_text)


@intro
def fix_cite_template_intro() -> str:
    return "Fix Cite templates: use {{!}} as separator before unnamed params"
