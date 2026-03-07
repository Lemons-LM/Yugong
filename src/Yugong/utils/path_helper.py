from pathlib import Path


def find_project_root(marker_files: list = ["pyproject.toml", "settings.toml", ".git"]) -> Path:
    current = Path(__file__).resolve()
    for parent in [current, *current.parents]:
        if any((parent / marker).exists() for marker in marker_files):
            return parent
    raise FileNotFoundError("Project root not found")

PROJECT_ROOT: Path = find_project_root()