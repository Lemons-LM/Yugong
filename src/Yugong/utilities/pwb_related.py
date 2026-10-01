"""pywikibot family registration for the wiki described by ``settings.toml``.

pywikibot does **not** auto-register :class:`pywikibot.family.Family`
subclasses: ``Family.load()`` first looks the name up in ``Family._families``
and only otherwise tries to import a module from ``pywikibot.families``.  A
custom wiki therefore has to insert its family object into that registry itself,
which is what :func:`register_family` does.  It has to run *before*
``pywikibot.Site(...)`` is called for the first time.
"""

from __future__ import annotations

from pywikibot import family

from src.Yugong.core.settings import settings


class YugongFamily(family.Family):
    """Family for the wiki configured in ``settings.toml``."""

    name: str = str(settings.wiki_family)
    langs: dict[str, str] = {str(settings.wiki_lang): str(settings.wiki_domain)}

    def scriptpath(self, code: str) -> str:
        return ""

    def protocol(self, code: str) -> str:
        return "HTTPS"

    def isPublic(self, code: str) -> bool:
        # pywikibot calls this as ``isPublic(code)``.  The original
        # ``isPublic(self)`` signature raised TypeError as soon as the family was
        # actually used.
        return False


def register_family() -> None:
    """Register (or refresh) the configured family so ``pywikibot.Site`` finds it."""
    family.Family._families[YugongFamily.name] = YugongFamily()
