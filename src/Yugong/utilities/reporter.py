"""Collects the non-fatal problems a run runs into and reports them at the end.

Skipped pages (diff too large, disallowed tags, failed save, ...) are recorded
here instead of being swallowed, so an unattended run leaves an audit trail.
"""

from __future__ import annotations

from collections import defaultdict

from src.Yugong.core.mailer import mailer


class Reporter:
    """A per-module list of issues plus the ways to surface them."""

    def __init__(self) -> None:
        self.issues: dict[str, list[str]] = defaultdict(list)

    def add(self, module: str, issue: str) -> None:
        """Record one issue under *module*."""
        self.issues[module].append(issue)

    def is_empty(self) -> bool:
        return not self.issues

    def body(self) -> str:
        """Render every collected issue as a plain-text report."""
        lines = ["Yugong Report", ""]
        for module, issues in self.issues.items():
            lines.append(f"{module}:")
            lines.extend(f"- {issue}" for issue in issues)
        return "\n".join(lines)

    def report(self) -> None:
        """E-mail the collected issues, if any."""
        if self.is_empty():
            return
        mailer.email("Yugong Report", self.body())

    def print_report(self) -> None:
        """Print the collected issues, if any."""
        if self.is_empty():
            return
        print(self.body())


reporter: Reporter = Reporter()
