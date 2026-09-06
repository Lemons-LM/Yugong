"""
Fix unnamed-parameter pipe ambiguity in Cite templates.

For Cite-* templates, the ``|`` separator before every unnamed (positional)
parameter is replaced with ``{{!}}``.  This prevents MediaWiki from interpreting
bare ``|`` characters inside URLs or other parameter values as parameter
separators when the page is re-rendered.

The extension rebuilds affected templates so the output wikitext uses
``{{!}}`` as the separator for all unnamed parameters.
"""

import re

from src.Yugong.core.wikitext import Wikitext
from src.Yugong.utilities.mark_job_intro import job, intro

import mwparserfromhell as mph

_CITE_RE = re.compile(r"^Cite[\s_]", re.IGNORECASE)


def _build_param_str(param) -> str:
    """Return the wikitext for a single template parameter."""
    value = str(param.value)
    if param.showkey:
        return f"|{param.name}={value}"
    else:
        # Use {{!}} as separator for unnamed params
        return f"{{{{!}}}}{value}"


def _needs_escape(template) -> bool:
    """Return True if *template* has any unnamed (positional) parameter."""
    for param in template.params:
        if not param.showkey:
            return True
    return False


@job
def fix_cite_template_job(wikitext: Wikitext) -> None:
    """Replace pipe separators before unnamed Cite-* params with {{!}}."""

    for template in list(wikitext.wikitext.filter_templates()):
        name = str(template.name).strip()
        if not _CITE_RE.match(name):
            continue
        if not _needs_escape(template):
            continue

        # Rebuild the template wikitext
        parts = ["{{", str(template.name).strip()]
        first = True
        for param in template.params:
            value = str(param.value)
            if param.showkey:
                parts.append(f"|{param.name}={value}")
            else:
                # First unnamed param: | is the template name separator, keep it
                # Subsequent unnamed params: use {{!}}
                if first:
                    parts.append(f"|{value}")
                    first = False
                else:
                    parts.append(f"{{{{!}}}}{value}")
        parts.append("}}")

        new_str = "".join(parts)
        if new_str != str(template):
            wikitext.wikitext.replace(template, new_str)


@intro
def fix_cite_template_intro() -> str:
    return "Fix Cite templates: use {{!}} as separator before unnamed params"
