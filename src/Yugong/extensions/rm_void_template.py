"""
Remove templates that redirect to Template:Void.

Checks the bot_db template cache first to avoid repeated API requests.
If a template's redirect target is not yet known, queries the wiki via pywikibot
and records the result in the database.
"""

import pywikibot

from src.Yugong.core.bot_db import bot_db
from src.Yugong.core.wiki import wiki
from src.Yugong.core.wikitext import Wikitext
from src.Yugong.utilities.mark_job_intro import job, intro

#TODO: Void should be target instead of type
_VOID_TARGETS = frozenset({"Template:Void", "Template:void", "Template:Void"})


def _is_void_template(name: str) -> bool:
    """Check whether *name* redirects to Template:Void.  Caches result in bot_db."""

    # 1. Check database cache
    cached = bot_db.search("template", {"title": name, "type": "void"})
    if cached:
        return True

    # Also check if we already know it's NOT a void template
    cached_any = bot_db.search("template", {"title": name})
    if cached_any:
        return False

    # 2. Query wiki for redirect target
    try:
        template_page = pywikibot.Page(wiki.site, f"Template:{name}")
        if template_page.isRedirectPage():
            target = template_page.getRedirectTarget()
            target_title = target.title()
            is_void = target_title in _VOID_TARGETS
        else:
            is_void = False
    except Exception:
        # If the template page doesn't exist or query fails, assume not void
        is_void = False

    # 3. Cache result
    bot_db.insert("template", {
        "title": name,
        "target": f"Template:{name}",
        "type": "void" if is_void else "normal",
    })

    return is_void


@job
def rm_void_template_job(wikitext: Wikitext) -> None:
    """Remove every template on the page that redirects to Template:Void."""
    for template in list(wikitext.wikitext.filter_templates()):
        raw_name = str(template.name).strip()
        # Normalize: remove leading whitespace/newlines and capitalize
        clean_name = raw_name.strip().replace("_", " ")
        if clean_name and _is_void_template(clean_name):
            wikitext.wikitext.remove(template)


@intro
def rm_void_template_intro() -> str:
    return "Remove templates that redirect to Template:Void (with DB cache)"
