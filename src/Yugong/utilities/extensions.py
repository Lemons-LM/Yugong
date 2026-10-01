"""Discovery and loading of extension modules.

Extensions live in ``src/Yugong/extensions`` and register themselves through the
``@job`` / ``@intro`` decorators as a side effect of being imported.  Both the
interactive entry point and offline dev mode load them through here so the
behaviour cannot drift apart.
"""

from __future__ import annotations

import importlib

from src.Yugong.utilities.path_helper import PROJECT_ROOT

EXTENSIONS_DIR = PROJECT_ROOT / "src" / "Yugong" / "extensions"


def extension_modules() -> list[str]:
    """Importable module names of every extension file, sorted by filename."""
    return [
        f"src.Yugong.extensions.{file.stem}"
        for file in sorted(EXTENSIONS_DIR.glob("*.py"))
        if file.name != "__init__.py"
    ]


def load_extensions() -> list[str]:
    """Import every extension module and return the names that were loaded.

    An extension that fails to import raises: per CONTRIBUTING.md a broken
    extension must stop the program rather than be skipped silently.
    """
    loaded: list[str] = []
    for module_name in extension_modules():
        importlib.import_module(module_name)
        loaded.append(module_name.rsplit(".", 1)[-1])
    return loaded
