"""Resolve the project root once, from any module depth."""

from __future__ import annotations

from pathlib import Path

MARKER_FILES: tuple[str, ...] = ("pyproject.toml", "settings.toml", ".git")


def find_project_root() -> Path:
    """Walk up from this file until a marker file is found."""
    current = Path(__file__).resolve()
    for parent in current.parents:
        if any((parent / marker).exists() for marker in MARKER_FILES):
            return parent
    raise FileNotFoundError(
        f"Project root not found: none of {MARKER_FILES} exist above {current}"
    )


PROJECT_ROOT: Path = find_project_root()
