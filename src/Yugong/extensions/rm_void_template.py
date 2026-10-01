"""Remove templates that redirect to ``Template:Void``.

Some maintenance templates are retired by redirecting them to ``Template:Void``,
which renders nothing; pages should stop transcluding them.

Every template is looked up at most once: the resolved redirect target is cached
in the ``template`` table of :mod:`src.Yugong.core.bot_db`.  Real failures (a
network problem, a broken site connection) propagate instead of being reported
as "not a Void template", so a broken run cannot silently skip work.
"""

from __future__ import annotations

import pywikibot

from src.Yugong.core.bot_db import bot_db
from src.Yugong.core.wiki import wiki
from src.Yugong.core.wikitext import Wikitext
from src.Yugong.utilities.mark_job_intro import intro, job

#: Normalised redirect target that means "this template renders nothing".
VOID_TARGET: str = "void"

#: bot_db table holding template redirect information.
TEMPLATE_TABLE: str = "template"


def _normalize_title(title: str) -> str:
    """Lower-case, strip whitespace and drop a template namespace prefix."""
    normalized = title.strip().lower().replace("_", " ")
    for prefix in ("template:", "模板:"):
        if normalized.startswith(prefix):
            normalized = normalized[len(prefix):]
            break
    return normalized.strip()


def _is_void_target(title: str) -> bool:
    """Return ``True`` if *title* is some spelling of ``Template:Void``."""
    return _normalize_title(title) == VOID_TARGET


def _resolve_redirect_target(name: str) -> str | None:
    """Return the redirect target of ``Template:<name>``, or ``None``."""
    template_page = pywikibot.Page(wiki.site, f"Template:{name}")
    try:
        if not template_page.isRedirectPage():
            return None
        return str(template_page.getRedirectTarget().title())
    except pywikibot.exceptions.NoPageError:
        # The template does not exist, so it cannot be a Void redirect.
        return None


def _is_void_template(name: str) -> bool:
    """Return ``True`` if ``Template:<name>`` redirects to ``Template:Void``.

    The answer is cached in bot_db, so each template is queried once per machine.
    """
    cached = bot_db.search(TEMPLATE_TABLE, {"title": name})
    if cached:
        return str(cached[0].get("type")) == "void"

    target = _resolve_redirect_target(name)
    is_void = target is not None and _is_void_target(target)

    bot_db.insert(TEMPLATE_TABLE, {
        "title": name,
        "target": target or f"Template:{name}",
        "type": "void" if is_void else "normal",
    })
    return is_void


@job(needs_wiki=True)
def rm_void_template_job(wikitext: Wikitext) -> None:
    """Remove every template on the page that redirects to ``Template:Void``."""
    for template in wikitext.templates():
        name = str(template.name).strip().replace("_", " ")
        if not name:
            continue
        if _is_void_template(name):
            wikitext.wikitext.remove(template)


@intro
def rm_void_template_intro() -> str:
    return "Remove templates that redirect to Template:Void (with DB cache)"
