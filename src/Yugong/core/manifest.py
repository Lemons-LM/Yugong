"""JSON-file backed state that survives between runs.

Used by the processing loop to remember which pages are still queued for a wiki
(``cache/<wiki_tag>.json``).
"""

from __future__ import annotations

import json
import os
from typing import Any

from src.Yugong.core.logger import BotLogger


class Manifest:
    """A dictionary stored as a JSON file."""

    def __init__(self, file: str | os.PathLike[str]) -> None:
        self.logger = BotLogger("manifest")
        self.file = str(file)
        self.data: dict[str, Any] = self.load()

    def load(self) -> dict[str, Any]:
        """Read the file, creating an empty one when missing or unreadable."""
        try:
            with open(self.file, "r", encoding="utf-8") as f:
                data = json.load(f)
        except FileNotFoundError:
            self.logger.info(f"Created new manifest {self.file}")
            self.save(data={})
            return {}
        except json.JSONDecodeError as exc:
            self.logger.warning(f"{self.file} is not valid JSON ({exc}); starting empty")
            self.save(data={})
            return {}
        except (OSError, UnicodeDecodeError) as exc:
            self.logger.warning(f"{self.file} is unreadable ({exc}); starting empty")
            self.save(data={})
            return {}

        if not isinstance(data, dict):
            self.logger.warning(
                f"{self.file} does not contain a JSON object; starting empty"
            )
            self.save(data={})
            return {}

        self.data = data
        self.logger.info(f"Loaded manifest {self.file}")
        return data

    def save(self, data: dict[str, Any] | None = None) -> None:
        """Write *data* (or the current contents) back to the file."""
        if data is None:
            data = self.data

        parent = os.path.dirname(self.file)
        if parent:
            os.makedirs(parent, exist_ok=True)

        # Write to a sibling file and replace atomically: a crash halfway
        # through must not leave a truncated todo list behind.
        temporary = f"{self.file}.tmp"
        try:
            with open(temporary, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(temporary, self.file)
        except OSError as exc:
            self.logger.error(f"Failed to save {self.file}: {exc}")
            try:
                os.unlink(temporary)
            except OSError:
                pass
            return

        self.data = data
