"""Configuration loading and validation.

``settings.toml`` is read at import time so that every component can simply do
``from src.Yugong.core.settings import settings``.  *Validation* is intentionally
deferred to :meth:`Settings.validate`, which the orchestrator calls once the user
has confirmed the run.  Keeping the two apart means that importing a module (for
dev mode, for the test suite, for tooling) never requires a fully configured
wiki.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import toml

from src.Yugong.core.logger import level_from_setting
from src.Yugong.utilities.path_helper import PROJECT_ROOT

#: Upper bound for a ``page_id_start``/``page_id_end`` sweep, as a guard against
#: accidentally queueing a whole wiki.
MAX_PAGEID_SPAN: int = 5000

#: Environment variable that points at an alternative configuration file, e.g.
#: for a second wiki or for an isolated test run.
SETTINGS_PATH_ENV: str = "YUGONG_SETTINGS"


def default_settings_path() -> Path:
    """Path of the configuration file to load when none is given explicitly."""
    override = os.environ.get(SETTINGS_PATH_ENV)
    return Path(override) if override else PROJECT_ROOT / "settings.toml"


class Settings:
    """Values from ``settings.toml``, falling back to the defaults declared here."""

    # ── Wiki connection ───────────────────────────────────────────────
    api_endpoint: str = ""
    user_agent: str = (
        "Yugong/1.0(Gecko-like, Repository/github.com:Lemons-LM/Yugong), Python/3.12"
    )
    user_agent_format: str = (
        "Yugong/1.0 {username}/{script} ({script_comments}) {pwb}{python} {http_backend}"
    )
    user_agent_check: str = "Yugong/1.0 (Check suppressed)"
    is_owner_only: bool = True
    bot_name: str = "Yugong-bot"
    wiki_domain: str = "www.qiuwenbaike.cn"
    wiki_lang: str = "zh"
    wiki_family: str = "qiuwen"
    wiki_tag: str = "wiki"

    # ── Task definition ───────────────────────────────────────────────
    page_id_start: int = 0
    page_id_end: int = 0
    linked_template: str = ""
    category: str = ""

    # ── Behaviour ─────────────────────────────────────────────────────
    bypass_confirm_settings: bool = False
    submit_changes: bool = False
    overwrite_para_name: bool = True
    overwrite_template_name: bool = True
    enable_cangjie: bool = False
    enable_heartbeat: bool = False
    edit_comment: str = "Edited by Yugong (gh:Lemons-LM/Yugong) program"

    # ── Safety limits ─────────────────────────────────────────────────
    safe_tag_list: list[str] = []
    unsafe_tag_list: list[str] = []
    is_dangerous_tag_unacceptable: bool = True
    max_acceptable_diff_size: int = 1000
    request_max_tries: int = 3
    request_timeout: int = 30

    # ── Notifications and logging ─────────────────────────────────────
    mail_recipients: list[str] = []
    log_level: int = 3
    log_timestamp: bool = True

    def __init__(self, path: Path | None = None) -> None:
        self.path: Path = path if path is not None else default_settings_path()

        if not self.path.exists():
            raise ValueError(f"Warning: {self.path} not found")

        with open(self.path, "r", encoding="utf-8") as f:
            settings_dict: dict[str, Any] = toml.load(f)

        for key, value in settings_dict.items():
            if value is not None:
                self.set(key=key, value=value)

    # ── Loading helpers ───────────────────────────────────────────────

    def set(self, *, key: str, value: Any) -> None:
        """Set one option, shadowing the class-level default."""
        setattr(self, key, value)

    @classmethod
    def from_dict(cls, values: dict[str, Any]) -> Settings:
        """Build a fully-populated instance without touching ``settings.toml``.

        Used by the test suite; ``Settings.path`` points at a non-existent file.
        """
        instance = cls.__new__(cls)
        instance.path = PROJECT_ROOT / "settings.toml"
        for key, value in values.items():
            if value is not None:
                instance.set(key=key, value=value)
        return instance

    def describe(self) -> str:
        """Return a human-readable ``key is set to value`` listing."""
        declared = {name for name in dir(type(self)) if not name.startswith("_")}
        keys = declared | set(self.__dict__)
        lines = []
        for name in sorted(keys):
            value = getattr(self, name)
            if callable(value) or name == "path":
                continue
            lines.append(f"{name} is set to {value!r}")
        return "\n".join(lines)

    # ── Derived values ────────────────────────────────────────────────

    def pageid_range(self) -> tuple[int, int] | None:
        """Return the inclusive ``(start, end)`` page-id range, or ``None``.

        ``page_id_end = 0`` means "just the single page ``page_id_start``".
        """
        start = int(self.page_id_start)
        if start <= 0:
            return None
        end = int(self.page_id_end)
        if end == 0:
            end = start
        return start, end

    # ── Validation ────────────────────────────────────────────────────

    def validate(self) -> None:
        """Raise a descriptive error if the configuration cannot be used.

        Called by the orchestrator after the user has reviewed the settings, so
        that merely importing a module stays possible without a configured wiki.
        """
        if not str(self.api_endpoint).strip():
            raise ValueError(
                "Warning: Check api_endpoint defined in settings.toml. \n"
                "The program does not know which wiki it is."
            )

        if not self.is_owner_only:
            raise ValueError(
                "Warning: is_owner_only must be true in settings.toml. \n"
                "Only OAuth authentication is supported; set the access token in "
                "the MW_OAUTH_TOKEN environment variable."
            )

        if not str(self.bot_name).strip():
            raise ValueError("Warning: bot_name must not be empty in settings.toml.")

        if not str(self.wiki_domain).strip():
            raise ValueError("Warning: wiki_domain must not be empty in settings.toml.")

        if not str(self.edit_comment).strip():
            raise ValueError(
                "Warning: edit_comment must not be empty: every edit must be "
                "attributable to the bot."
            )

        if not (self.pageid_range() or self.linked_template or self.category):
            raise ValueError(
                "Warning: Check # About Task part defined in settings.toml. \n"
                "Set page_id_start (optionally with page_id_end), linked_template "
                "or category so the program knows what to do."
            )

        page_range = self.pageid_range()
        if page_range is not None:
            start, end = page_range
            if end < start:
                raise ValueError(
                    f"Warning: page_id_end ({end}) is smaller than page_id_start "
                    f"({start}) in settings.toml."
                )
            if end - start + 1 > MAX_PAGEID_SPAN:
                raise ValueError(
                    f"Warning: page_id_start..page_id_end spans {end - start + 1} "
                    f"pages, above the {MAX_PAGEID_SPAN} safety limit. Narrow the "
                    "range or raise MAX_PAGEID_SPAN deliberately."
                )

        if self.safe_tag_list and self.unsafe_tag_list:
            raise ValueError(
                "Warning: safe_tag_list and unsafe_tag_list cannot both be set in "
                "settings.toml — pick one allow-list or one deny-list."
            )

        if int(self.max_acceptable_diff_size) <= 0:
            raise ValueError(
                "Warning: max_acceptable_diff_size must be a positive integer; "
                "0 or negative would reject every edit."
            )

        if int(self.request_max_tries) < 1:
            raise ValueError("Warning: request_max_tries must be at least 1.")

        if int(self.request_timeout) < 1:
            raise ValueError("Warning: request_timeout must be at least 1 second.")

        level_from_setting(self.log_level)

        if self.enable_cangjie:
            raise NotImplementedError(
                "enable_cangjie is not implemented: YuGong does not perform "
                "automatic Chinese variant conversion yet. Set enable_cangjie = "
                "false in settings.toml, or use the category_handler extension "
                "which converts category titles through OpenCC when available."
            )


settings: Settings = Settings()
