"""Load extensions and rules, show the user what is about to run, ask to confirm."""

from __future__ import annotations

from src.Yugong.core.logger import configure_logging, logger
from src.Yugong.core.settings import settings
from src.Yugong.core.template_formatter import formatter
from src.Yugong.utilities.extensions import load_extensions
from src.Yugong.utilities.mark_job_intro import INTROS


def confirm_settings(all_confirmed: bool = False) -> None:
    """Load everything, print a summary, and prompt unless in robot mode.

    Args:
        all_confirmed: Skip the interactive prompts entirely.
    """
    configure_logging(
        log_level=settings.log_level,
        log_timestamps=settings.log_timestamp,
    )

    loaded = load_extensions()

    intro_strs = "The following extensions are loaded:\n"
    if loaded:
        intro_strs += "".join(f"{intro()}\n" for intro in INTROS)
    else:
        intro_strs += "(no extensions found)\n"

    print("The following Template TOML rules are loaded:\n")
    formatter.get_ruleset()

    setting_str = settings.describe()

    # Audit trail, kept even in robot mode.
    logger.info(f"Settings:\n{setting_str}")
    logger.info(f"Extensions loaded:\n{intro_strs}")

    # Fail loudly before anything is touched.  ``do_jobs`` validates again, which
    # is harmless and keeps the processing loop safe when called on its own.
    settings.validate()

    if all_confirmed or settings.bypass_confirm_settings:
        return

    if_know_to_use = input(
        "YuGong is a tool to help you to do some jobs on specific wiki.\n"
        "It it released \"as-is\", so we won't guarantee it works as expected.\n"
        "You need to take full responsibility to using the program.\n"
        "You are solely responsible for ensuring that your use of this software "
        "complies with all applicable laws and regulations in your jurisdiction.\n"
        "Including but not limited to the laws of the People's Republic of China.\n"
        "Besides that, it is a free software, which means you never need to pay for it.\n"
        "Do you know that? (y/[n]): "
    ).lower()
    if if_know_to_use not in ["y", "yes"]:
        print("Goodbye")
        raise SystemExit(0)

    if_confirmed_job = input(
        f"The following settings are confirmed:\n{setting_str}\n"
        f"Do you want to continue? (y/[n]): "
    ).lower()
    if if_confirmed_job not in ["y", "yes"]:
        print("Please check again the settings.toml")
        raise SystemExit(0)

    if_confirmed_extensions = input(
        f"{intro_strs}\nDo you want to continue? (y/[n]): "
    ).lower()
    if if_confirmed_extensions not in ["y", "yes"]:
        print("Please check again the settings.toml")
        raise SystemExit(0)

    if input("Do you want to continue? (y/[n]): ").lower() not in ["y", "yes"]:
        print("Please check again the rulesets")
        raise SystemExit(0)
