from pathlib import Path

import toml

from src.Yugong.utils.path_helper import PROJECT_ROOT


class Settings:
    """
    Default settings for the script.
    """
    user_agent: str = "Yugong/1.0(Gecko-like, Repository/github.com:Lemons-LM/Yugong), Python/3.12"
    request_max_tries: int = 3
    edit_comment: str = "Edited by Yugong (gh:Lemons-LM/Yugong) program"

    is_dangerous_tag_unacceptable: bool = True
    safe_tag_list: list[str] = [
        'ref',
        'br',
        'references'
    ]
    max_acceptable_diff_size: str = 1000
    enable_cangjie: bool = False
    overwrite_para_name: bool = True
    overwrite_template_name: bool = True
    log_level: int = 1
    wiki_tag: str = 'wiki'
    submit_changes: bool = False

    @classmethod
    def set(cls, *, key: str, value: str):
        setattr(cls, key, value)

    def __init__(self):
        text_path = PROJECT_ROOT / "settings.toml"

        if not text_path.exists():
            raise ValueError(f"Warning: {text_path} not found")

        with open(text_path, 'r', encoding='utf-8') as f:
            settings_dict: dict = toml.load(f)

        for key, value in settings_dict.items():
            if value is not None:
                self.set(key=key, value=value)

        if not hasattr(settings, 'api_endpoint') or not settings.api_endpoint:
            raise ValueError(
                f"Warning: Check api_endpoint defined in settings.toml. \nThe program does not know which wiki it is.")

        if not (hasattr(settings, 'page_id_start') and settings.page_id_start != 0
                or hasattr(settings, 'linked_template') and settings.linked_template
                or hasattr(settings, 'category') and settings.category):
            raise ValueError(
                f"Warning: Check # About Task part defined in settings.toml. \nThe program does not know what to do.")


settings: Settings = Settings()