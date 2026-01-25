import importlib
from pathlib import Path

from src.Yugong.models.logger import logger
from src.Yugong.models.settings import settings
from src.Yugong.utils.mark_job_intro import INTROS
from src.Yugong.utils.path_helper import PROJECT_ROOT


def confirm_settings():
    if_know_to_use = input("YuGong is a tool to help you to do some jobs on specific wiki.\n"
                           "It it released \"as-is\", so we won't guarantee it works as expected.\n"
                           "You need to take full responsibility to using the program.\n"
                           "You are solely responsible for ensuring that your use of this software complies with all applicable laws and regulations in your jurisdiction.\n"
                           "Including but not limited to the laws of the People's Republic of China.\n"
                           "Besides that, it is a free software, which means you never need to pay for it.\n"
                           "Do you know that? (y/n): ").lower()
    if if_know_to_use not in ["y", "yes"]:
        print("Goodbye")
        return

    setting_list_str = []
    for attr_name in dir(settings):
        if not attr_name.startswith('_') and not callable(getattr(settings, attr_name)):
            attr_value = getattr(settings, attr_name)
            setting_list_str.append(f"{attr_name} is set to {attr_value}")

    setting_str = "\n".join(setting_list_str)

    if_confirmed_job = input(
        f"The following settings are confirmed:\n{setting_str}\nDo you want to continue? (y/n): ").lower()
    if if_confirmed_job not in ["y", "yes"]:
        print("Please check again the settings.toml")
        return

    if settings.log_level >= 1:
        logger.log_summary(f"## Settings\n\n{setting_str}")

    steps_path = PROJECT_ROOT / 'src' / 'Yugong' / "Extensions"
    for f in steps_path.glob("*.py"):
        if f.name != "__init__.py":
            module_name = f"src.Yugong.Extensions.{f.stem}"
            importlib.import_module(module_name)

    intro_strs: str = "The following Extensions are loaded:\n"
    for f in INTROS:
        intro_str: str = f()
        intro_strs += f"{intro_str}\n"

    if_confirmed_extensions = input(f"{intro_strs}\nDo you want to continue? (y/n): ")
    if if_confirmed_extensions not in ["y", "yes"]:
        print("Please check again the settings.toml")
        return

    if settings.log_level >= 1:
        logger.log_summary(f"## Extensions\n\n{intro_strs}")