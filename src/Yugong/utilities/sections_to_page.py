"""Join a list of rendered sections into one page body."""

from __future__ import annotations

from typing import Iterable


def sections_to_page(sections: Iterable[object], *, original_content: str = "") -> str:
    """Return *original_content* followed by each section, blank-line separated."""
    result = original_content.strip()

    if result and not result.endswith("\n"):
        result += "\n"

    for section in sections:
        section_code = str(section).strip()
        result += section_code + "\n\n"

    return result
