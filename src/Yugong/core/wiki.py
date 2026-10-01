"""pywikibot wrapper: the wiki connection, throttling and the kill switch.

Two behaviours are worth calling out explicitly:

* **No network access at import time.**  ``Wiki()`` is instantiated at module
  level, so anything it does in ``__init__`` happens for every importer.  The
  previous version called :meth:`Wiki.tick` from ``__init__``, which fired an API
  request before the caller had configured anything (and crashed hard whenever
  the response was not JSON).  Site creation and throttling are now lazy.
* **The kill switch never crashes the run.**  :meth:`Wiki._check_suppressed_action`
  talks to the wiki on every :data:`SUPPRESSION_CHECK_INTERVAL` requests.  A
  challenge page, an HTML error page or a network hiccup must not take the bot
  down, so every failure is logged and treated as "cannot check right now".
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

import pywikibot
from pywikibot import config
from pywikibot.comms import http
from pywikibot.site import BaseSite

from src.Yugong.core.logger import BotLogger
from src.Yugong.core.mailer import mailer
from src.Yugong.core.settings import settings
from src.Yugong.utilities.link import get_user_talk
from src.Yugong.utilities.path_helper import PROJECT_ROOT
from src.Yugong.utilities.pwb_related import register_family

#: Requests between two "is the bot still allowed to run?" checks.
SUPPRESSION_CHECK_INTERVAL: int = 20

#: Accepted spellings of the OAuth access token environment variable.
#: ``MW_OAUTH_TOKEN`` is the documented name; the longer one is kept so existing
#: deployments keep working.
OAUTH_ENV_VARS: tuple[str, ...] = ("MW_OAUTH_TOKEN", "MW_BOT_OAUTH_TOKEN")

#: Page the wiki admins edit to signal "this bot must stop".
SUPPRESSION_PAGE_TEMPLATE: str = "User:{bot_name}/block"


def get_oauth_token() -> str | None:
    """Return the OAuth access token from the environment, if any.

    Read on every use rather than cached at import so that a token exported by a
    wrapper script is picked up even after this module has been imported.
    """
    for name in OAUTH_ENV_VARS:
        value = os.environ.get(name)
        if value:
            return value
    return None


def apply_pywikibot_config() -> None:
    """Push YuGong's settings into pywikibot's global configuration."""
    config.user_agent_format = settings.user_agent_format
    config.cosmetic_changes = True
    config.minthrottle = 2
    # pywikibot defaults to retry_max = 120 with a 5 s wait, which turns a blocked
    # wiki into a multi-minute hang.  Honour the project's own retry budget.
    config.retry_max = max(1, int(settings.request_max_tries))
    config.retry_wait = 2
    config.socket_timeout = (6.05, int(settings.request_timeout))


class Wiki:
    """Lazy wrapper around :class:`pywikibot.Site` plus YuGong's safety checks."""

    def __init__(self, bot_name: str | None = None, api_endpoint: str | None = None) -> None:
        if bot_name is None:
            bot_name = str(getattr(settings, "bot_name", "Yugong-bot"))
        if api_endpoint is None:
            api_endpoint = str(
                getattr(settings, "api_endpoint", "")
                or f"https://{getattr(settings, 'wiki_domain', 'www.qiuwenbaike.cn')}/api.php"
            )
        if not bot_name.strip() or not api_endpoint.strip():
            raise ValueError("Bot name and api endpoint cannot be empty")

        self.bot_name = bot_name
        self.api_endpoint = api_endpoint
        self.logger = BotLogger("wiki")
        self.csrf_token = ""
        self.heartbeat_file = os.path.join(PROJECT_ROOT, "data", "bot", "heartbeat")
        self.heartbeat = ""
        self.request_count = 0
        self._tick_disabled = False
        self._site: BaseSite | None = None
        self.logger.info("WikiBot initialized")

    # ── Raw API access ────────────────────────────────────────────────

    def _api_get(
        self,
        params: dict[str, Any],
        *,
        use_check_user_agent: bool = False,
    ) -> dict[str, Any] | None:
        """GET ``self.api_endpoint`` with retries, returning parsed JSON or ``None``.

        Never raises: callers decide what a missing answer means.  A non-JSON
        body (bot-protection challenge, login form, HTML error page) is retried
        and then reported, instead of blowing up the whole run.
        """
        headers = {
            "User-Agent": (
                settings.user_agent_check if use_check_user_agent else settings.user_agent
            )
        }
        token = get_oauth_token()
        if token:
            headers["Authorization"] = f"Bearer {token}"

        attempts = max(1, int(settings.request_max_tries))
        last_problem = "no attempt made"

        for attempt in range(1, attempts + 1):
            try:
                response = http.session.get(
                    self.api_endpoint,
                    params=params,
                    headers=headers,
                    timeout=float(settings.request_timeout),
                )
            except Exception as exc:  # network error, timeout, DNS, ...
                last_problem = f"{type(exc).__name__}: {exc}"
            else:
                if not response.ok:
                    last_problem = f"HTTP {response.status_code}"
                elif not response.content:
                    return {}
                else:
                    try:
                        data = response.json()
                    except ValueError:
                        last_problem = (
                            "response body was not JSON "
                            f"(content-type: {response.headers.get('Content-Type', '?')})"
                        )
                    else:
                        if isinstance(data, dict):
                            return data
                        last_problem = f"unexpected JSON root type: {type(data).__name__}"

            self.logger.warning(
                f"API request failed (attempt {attempt}/{attempts}): {last_problem}"
            )
            if attempt < attempts:
                time.sleep(min(2 ** attempt, 10))

        self.logger.error(f"API request gave up after {attempts} attempts: {last_problem}")
        return None

    def api_query(self, params: dict[str, Any]) -> dict[str, Any] | None:
        """Public, retrying ``action=query``-style call against the wiki API."""
        return self._api_get(params)

    # ── Kill switch ───────────────────────────────────────────────────

    def _read_heartbeat(self) -> str:
        try:
            return Path(self.heartbeat_file).read_text(encoding="utf-8").strip()
        except (FileNotFoundError, OSError):
            return ""

    def _write_heartbeat(self, revid: str) -> None:
        path = Path(self.heartbeat_file)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(revid, encoding="utf-8")

    def _check_suppressed_action(self) -> None:
        """Stop the bot if an admin changed ``User:<bot>/block``.

        The revision id of that page acts as a "keep running" token: the first
        run stores it, and any later change means the bot has been suppressed.
        """
        self._tick_disabled = True
        try:
            data = self._api_get(
                {
                    "action": "query",
                    "titles": SUPPRESSION_PAGE_TEMPLATE.format(bot_name=self.bot_name),
                    "prop": "revisions",
                    "rvprop": "ids",
                    "format": "json",
                },
                use_check_user_agent=True,
            )
            if not data:
                return

            pages = data.get("query", {}).get("pages")
            if not isinstance(pages, dict) or not pages:
                self.logger.warning("Suppression check: unexpected query result")
                return

            page_data = next(iter(pages.values()))
            revisions = page_data.get("revisions") if isinstance(page_data, dict) else None
            if not revisions:
                # Page missing or empty: nobody has signalled anything yet.
                return

            revid = str(revisions[0]["revid"])
            stored = self._read_heartbeat()

            if not stored:
                self.heartbeat = revid
                self._write_heartbeat(revid)
                self.logger.info(f"Suppression heartbeat initialised at revision {revid}")
                return

            self.heartbeat = stored
            if stored != revid:
                self.logger.critical("Bot has been suppressed")
                try:
                    mailer.email(
                        "Bot has been suppressed",
                        "Bot has been suppressed — check immediately!",
                    )
                except Exception as exc:  # noqa: BLE001 - alerts must never block exit
                    self.logger.error(f"Could not send suppression alert: {exc}")
                sys.exit(1)
        except Exception as exc:  # noqa: BLE001 - a broken check must not kill the run
            self.logger.warning(f"Suppression check skipped: {type(exc).__name__}: {exc}")
        finally:
            self._tick_disabled = False

    def tick(self) -> None:
        """Count one request and run the kill switch every N requests."""
        if self._tick_disabled:
            return
        self.request_count += 1
        if self.request_count >= SUPPRESSION_CHECK_INTERVAL:
            self.request_count = 0
            self._check_suppressed_action()

    # ── Site and page access ──────────────────────────────────────────

    @property
    def site(self) -> BaseSite:
        """The :class:`pywikibot.site.BaseSite`, created on first use and reused after."""
        if self._site is None:
            if not get_oauth_token():
                raise ValueError(
                    f"{' or '.join(OAUTH_ENV_VARS)} environment variable not found"
                )
            apply_pywikibot_config()
            register_family()
            self._site = pywikibot.Site(
                code=str(settings.wiki_lang),
                fam=str(settings.wiki_family),
                user=self.bot_name,
            )
            self.logger.info("Pywikibot Site initialized")

        self.tick()
        return self._site

    def page(self, title: str) -> pywikibot.Page:
        return pywikibot.Page(self.site, title)

    def category(self, title: str) -> pywikibot.Category:
        return pywikibot.Category(self.site, title)

    def user(self, name: str) -> pywikibot.User:
        return pywikibot.User(self.site, name)

    def file(self, title: str) -> pywikibot.FilePage:
        return pywikibot.FilePage(self.site, title)

    # ── Page helpers ──────────────────────────────────────────────────

    def get_sections(self, title: str, *, level: str = "2") -> list[str]:
        """Return the anchor names of all sections of *title* at *level*."""
        data = self._api_get(
            {
                "action": "parse",
                "page": title,
                "prop": "sections",
                "format": "json",
            }
        )
        if not data or "error" in data:
            return []

        sections = data.get("parse", {}).get("sections") or []
        wanted = str(level)
        return [
            str(section.get("linkAnchor", "")).strip()
            for section in sections
            if str(section.get("level")) == wanted
        ]

    def get_message_list(self, *, page: str) -> list[str]:
        """Read a MassMessage target list (JSON) from *page*."""
        text = self.page(page).text
        if not text:
            return []
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{page} is not a valid MassMessage target list: {exc}") from exc
        targets = payload.get("targets", []) if isinstance(payload, dict) else []
        return [str(item.get("title", "")) for item in targets if item.get("title")]

    def check_allow_bots(self, user: str) -> bool:
        """Return ``True`` if *user* has not opted out of bot messages.

        The user talk page's *content* is what carries ``{{nobots}}``; the
        previous implementation regexed the page **title** returned by
        ``get_user_talk()``, so the opt-out was never actually detected.
        """
        talk_title = get_user_talk(user)
        if not talk_title:
            return False

        try:
            text = self.page(talk_title).text
        except Exception as exc:  # noqa: BLE001 - unreadable page, fail closed
            self.logger.warning(f"Could not check bot opt-out for {talk_title}: {exc}")
            return False

        if not text:
            # Nothing on the page means nothing to opt out with.
            return True

        pattern = (
            r"\{\{(nobots|bots\|(allow=none|deny=.*?"
            + re.escape(self.bot_name)
            + r".*?|optout=all|deny=all))\}\}"
        )
        return re.search(pattern, text) is None

    def new_section(self, title: str, section_title: str, content: str, summary: str) -> None:
        """Append a new ``== section_title ==`` section to *title*."""
        page = self.page(title)
        try:
            old_text = page.text
            page.text = f"{old_text.strip()}\n\n== {section_title} ==\n{content}"
            page.save(summary=summary, bot=True)
        except Exception as exc:  # noqa: BLE001 - one failed page must not stop the rest
            self.logger.error(f"Publish failed for {title}: {exc}")

    def mass_message(
        self, mass_message_list: str, title: str, content: str, summary: str
    ) -> None:
        """Send *content* as a section to every target of a MassMessage list."""
        message_list = self.get_message_list(page=mass_message_list)
        self.logger.info(
            f"Sending MassMessage to: {mass_message_list}\n"
            f"Title: {title}\nContent: {content}\nSummary: {summary}"
        )
        for target in message_list:
            try:
                if not self.check_allow_bots(target):
                    self.logger.info(f"Skipping {target}: bot messages not allowed")
                    continue
                self.logger.info(f"\nPublishing to: {target}")
                self.new_section(
                    title=target, section_title=title, content=content, summary=summary
                )
            except Exception as exc:  # noqa: BLE001 - continue with the next target
                self.logger.exception(exc)
                continue


wiki = Wiki()

_original_request = http.session.request


def guarded_request(method: str, url: str, *args: Any, **kwargs: Any) -> Any:
    """Wrap ``requests`` so every pywikibot call is throttled and authenticated."""
    wiki.tick()
    wiki.logger.debug(f"Wiki request: {method} {url} {kwargs}")

    token = get_oauth_token()
    if token:
        headers = kwargs.get("headers") or {}
        if "Authorization" not in headers:
            headers["Authorization"] = f"Bearer {token}"
        kwargs["headers"] = headers

    return _original_request(method, url, *args, **kwargs)


http.session.request = guarded_request  # type: ignore[method-assign]
