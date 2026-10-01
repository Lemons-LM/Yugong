"""Top-level orchestrator for the interactive (production) entry point."""

from __future__ import annotations

from src.Yugong.processor.do_jobs import do_jobs
from src.Yugong.utilities.confirm_settings import confirm_settings


def yu_gong() -> None:
    """Confirm the configuration with the user, then process the todo list."""
    confirm_settings()
    do_jobs()
