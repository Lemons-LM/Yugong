"""End-to-end checks that go through the real command line entry point.

These are the regression tests for the wiring bugs: ``main.py --dev`` used to
fail with ``ModuleNotFoundError: src.Yugong.processor.dev_mode`` and a production
run used to crash while importing ``wiki``.
"""

from __future__ import annotations

import os
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

REPO_ROOT = Path(__file__).resolve().parents[1]
MAIN = REPO_ROOT / "main.py"


def run_main(
    *args: str, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    """Run ``main.py`` in a subprocess and capture its output."""
    return subprocess.run(
        [sys.executable, str(MAIN), *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
        env=env,
    )


class MainEntryPointTest(unittest.TestCase):
    def test_help_lists_the_dev_mode_flag(self) -> None:
        result = run_main("--help")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--dev", result.stdout)

    def test_dev_mode_processes_a_file(self) -> None:
        with TemporaryDirectory() as tmp:
            source = Path(tmp) / "in.wikitext"
            target = Path(tmp) / "out.wikitext"
            source.write_text('A<ref name="orphan" />B', encoding="utf-8")

            result = run_main("--dev", str(source), str(target))

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(target.read_text(encoding="utf-8"), "AB")

    def test_dev_mode_can_skip_template_rules(self) -> None:
        with TemporaryDirectory() as tmp:
            source = Path(tmp) / "in.wikitext"
            target = Path(tmp) / "out.wikitext"
            source.write_text("plain", encoding="utf-8")

            result = run_main("--dev", str(source), str(target), "--no-template-rules")

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("--no-template-rules", result.stdout)

    def test_production_run_validates_the_settings_file(self) -> None:
        with TemporaryDirectory() as tmp:
            config = Path(tmp) / "settings.toml"
            config.write_text(
                'api_endpoint = "https://wiki.example.com/"\n'
                "is_owner_only = true\n"
                "bot_name = \"TestBot\"\n",
                encoding="utf-8",
            )
            env = {**os.environ, "YUGONG_SETTINGS": str(config)}

            result = run_main(env=env)

            self.assertEqual(result.returncode, 1)
            self.assertIn("About Task", result.stderr)

    def test_production_run_reports_a_missing_settings_file(self) -> None:
        env = {**os.environ, "YUGONG_SETTINGS": "/nonexistent/settings.toml"}

        result = run_main(env=env)

        self.assertEqual(result.returncode, 1)
        self.assertIn("not found", result.stderr)


class PywikibotDataDirTest(unittest.TestCase):
    def test_creates_the_directory_and_a_user_config(self) -> None:
        import main as main_module

        with TemporaryDirectory() as tmp:
            target = Path(tmp) / "pwb"
            self.assertEqual(main_module.ensure_pywikibot_dir(target), target)
            self.assertTrue((target / "user-config.py").exists())
            # Calling it again must be harmless.
            main_module.ensure_pywikibot_dir(target)

    def test_an_existing_user_config_is_never_overwritten(self) -> None:
        import main as main_module

        with TemporaryDirectory() as tmp:
            target = Path(tmp) / "pwb"
            target.mkdir()
            config_file = target / "user-config.py"
            config_file.write_text("# hand written\n", encoding="utf-8")

            main_module.ensure_pywikibot_dir(target)

            self.assertEqual(config_file.read_text(encoding="utf-8"), "# hand written\n")

    def test_pywikibot_uses_the_project_data_directory(self) -> None:
        """Regression: pywikibot used to fall back to the current directory."""
        code = "import main; from pywikibot import config; print(config.base_dir)"
        result = subprocess.run(
            [sys.executable, "-c", code],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            result.stdout.strip(), str(REPO_ROOT / "data" / "pwb")
        )


if __name__ == "__main__":
    unittest.main()
