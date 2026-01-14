from pathlib import Path

import toml

from src.Yugong.models.settings import settings


def get_settings() -> None:

    project_root = Path(__file__).parent.parent.parent.parent
    text_path = project_root / "settings.toml"

    if not text_path.exists():
        raise ValueError(f"Warning: {text_path} not found")

    with open(text_path, 'r', encoding='utf-8') as f:
        settings_dict: dict = toml.load(f)

    for key, value in settings_dict.items():
        if value is not None:
            settings.set(key=key, value=value)


    if not hasattr(settings, 'api_endpoint') or not settings.api_endpoint:
        raise ValueError(f"Warning: Check api_endpoint defined in settings.toml. \nThe program does not know which wiki it is.")

    if not (hasattr(settings, 'page_id_start') and settings.page_id_start != 0
            or hasattr(settings, 'linked_template') and settings.linked_template
            or hasattr(settings, 'category') and settings.category):
        raise ValueError(f"Warning: Check # About Task part defined in settings.toml. \nThe program does not know what to do.")
