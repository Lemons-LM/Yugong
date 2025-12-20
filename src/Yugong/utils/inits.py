from pathlib import Path

from src.Yugong.models.settings import local_settings, default_settings


def get_settings() -> None:
    settings: list[str] = []

    project_root = Path(__file__).parent.parent.parent.parent
    text_path = project_root / "LocalSettings.txt"

    if not text_path.exists():
        raise ValueError(f"Warning: {text_path} not found")

    with open(text_path, 'r', encoding='utf-8') as f:
        setting_str: str = f.read()

    settings_list: list[str] = setting_str.split('\n')
    for setting in settings_list:
        if '#' in setting:
            setting = setting[:setting.index('#')]
        cleaned_setting: str = setting.strip()
        if cleaned_setting:
            settings.append(cleaned_setting)

    for setting in settings:
        if '=' in setting:
            key, value = setting.split('=', 1)
            key = key.strip()
            value = value.strip()
            if not key or not value:
                continue
            local_settings.add(key=key, value=value)

    attrs_ds = {attr for attr in dir(default_settings) if not attr.startswith('__') and not callable(getattr(default_settings, attr))}

    for attr in attrs_ds:
        if not hasattr(local_settings, attr):
            local_settings.add(key=attr, value=getattr(default_settings, attr))