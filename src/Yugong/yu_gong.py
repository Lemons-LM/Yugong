from src.Yugong.models.settings import local_settings
from src.Yugong.utils.inits import get_settings
from pathlib import Path
import importlib

from src.Yugong.utils.mark_job_intro import INTROS


def yu_gong():
    """
    [done] 1. Welcome the user to use and ask them to confirm knowing they need to take full responsibility to using the program
    [done]2. Do get_settings and ask the user to confirm the program's settings in settings.toml
    3. Ask the user to confirm the Extensions' job by use all @intro s to print strs that intro each extension's usage
    4. Everything is confirmed, init the wiki_instance and get job list
    5. Do jobs.
    6. (Temporary in MVP) Tell the user result, copy it on the clipboard and then open the browser's action=edit page
    """
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

    get_settings()

    confirm_setting_msgs = {
        "api_endpoint": "The target wiki to edit is set to {value}",
        "user_agent": "The User-Agent for requests is set to {value}",
        "is_owner_only": "Owner-only protection mode is set to {value}",
        "client_id": "OAuth client ID is set to {value}",
        "page_id_start": "Starting page ID for processing is set to {value}",
        "page_id_end": "Ending page ID for processing is set to {value}",
        "linked_template": "Target template to process is set to {value}",
        "category": "Working category is set to {value}",
        "risk_level": "Risk control level is set to {value}",
        "overwrite_para_name": "Parameter name to overwrite is set to {value}",
        "overwrite_template_name": "Template name to overwrite is set to {value}",
        "is_dangerous_tag_unacceptable": "Dangerous HTML tag handling policy is set to {value}",
        "max_acceptable_diff_size": "Maximum acceptable edit diff size is set to {value} bytes",
        "enable_cangjie": "Cangjie auto convert-zh feature is set to {value}"
    }

    setting_list_str = []
    for attr, tpl in confirm_setting_msgs.items():
        value = getattr(local_settings, attr, None)
        # 判断是否“有意义”：存在且非空（可根据需求调整）
        if value is not None and value != "" and value != [] and value != {}:  # 可按需扩展
            setting_list_str.append(tpl.format(value=value))

    result = "\n".join(setting_list_str)

    if_confirmed_job = input(f"The following settings are confirmed:\n{result}\nDo you want to continue? (y/n): ").lower()
    if if_confirmed_job not in ["y", "yes"]:
        print("Please check again the settings.toml")
        return

    steps_path = Path(__file__).parent / "Extensions"
    for f in steps_path.glob("*.py"):
        if f.name != "__init__.py":
            module_name = f"src.Yugong.Extensions.{f.stem}"
            importlib.import_module(module_name)

    intro_strs: str= "The following Extensions are loaded:\n"
    for f in INTROS:
        intro_str: str = f()
        intro_strs += f"{intro_str}\n"

    if_confirmed_extensions = input(f"{intro_strs}\nDo you want to continue? (y/n): ")
    if if_confirmed_extensions not in ["y", "yes"]:
        print("Please check again the settings.toml")
        return

