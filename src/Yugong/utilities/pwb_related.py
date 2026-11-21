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
from src.Yugong.utilities.urls import host_of, scheme_of, script_path


class YugongFamily(family.Family):
    """Family for the wiki configured in ``settings.toml``.

    ``wiki_domain`` is the fallback host; when ``api_endpoint`` is set it wins,
    and its path becomes pywikibot's ``scriptpath``.  Otherwise a wiki installed
    under ``/w/`` would be contacted at the domain root.
    """

    name: str = str(settings.wiki_family)
    langs: dict[str, str] = {
        str(settings.wiki_lang): host_of(settings.api_endpoint) or str(settings.wiki_domain)
    }

    def scriptpath(self, code: str) -> str:
        return script_path(settings.api_endpoint)

    def protocol(self, code: str) -> str:
        return scheme_of(settings.api_endpoint)

    def isPublic(self, code: str) -> bool:
        # pywikibot calls this as ``isPublic(code)``.  The original
        # ``isPublic(self)`` signature raised TypeError as soon as the family was
        # actually used.
        return False


def register_family() -> None:
    """Register (or refresh) the configured family so ``pywikibot.Site`` finds it."""
    instance = YugongFamily()
    # Refresh in case settings were overridden after import (tests, wrappers).
    instance.langs = {
        str(settings.wiki_lang): host_of(settings.api_endpoint) or str(settings.wiki_domain)
    }
    family.Family._families[YugongFamily.name] = instance
