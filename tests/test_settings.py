"""Configuration loading and validation."""

from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from src.Yugong.core.settings import MAX_PAGEID_SPAN, Settings

VALID: dict[str, Any] = {
    "api_endpoint": "https://wiki.example.com/",
    "is_owner_only": True,
    "bot_name": "TestBot",
    "wiki_domain": "wiki.example.com",
    "edit_comment": "Test edit",
    "category": "Some category",
}


def make_settings(**overrides: Any) -> Settings:
    values = dict(VALID)
    values.update(overrides)
    return Settings.from_dict(values)


class SettingsValidationTest(unittest.TestCase):
    def test_valid_configuration_passes(self) -> None:
        make_settings().validate()

    def test_missing_api_endpoint_is_rejected(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            make_settings(api_endpoint="").validate()
        self.assertIn("api_endpoint", str(ctx.exception))

    def test_api_endpoint_must_be_an_absolute_http_url(self) -> None:
        for bad in ("wiki.example.com", "ftp://wiki.example.com/", "https:///x"):
            with self.assertRaises(ValueError) as ctx:
                make_settings(api_endpoint=bad).validate()
            self.assertIn("absolute", str(ctx.exception))

    def test_api_endpoint_accepts_an_api_php_url(self) -> None:
        make_settings(api_endpoint="https://wiki.example.com/api.php").validate()

    def test_unknown_option_is_rejected(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            make_settings(safe_tag_lst=["ref"]).validate()
        self.assertIn("unknown option", str(ctx.exception))
        self.assertIn("safe_tag_lst", str(ctx.exception))

    def test_mistyped_string_list_is_rejected(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            make_settings(safe_tag_list="script").validate()
        self.assertIn("list of strings", str(ctx.exception))

    def test_mistyped_integer_is_rejected(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            make_settings(request_max_tries="three").validate()
        self.assertIn("integer", str(ctx.exception))

    def test_wiki_tag_cannot_escape_the_cache_directory(self) -> None:
        for bad in ("../../etc/passwd", "a/b", "..", ""):
            with self.assertRaises(ValueError) as ctx:
                make_settings(wiki_tag=bad).validate()
            self.assertIn("wiki_tag", str(ctx.exception))

    def test_is_owner_only_must_be_true(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            make_settings(is_owner_only=False).validate()
        self.assertIn("is_owner_only", str(ctx.exception))

    def test_a_task_selector_is_required(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            make_settings(category="", linked_template="", page_id_start=0).validate()
        self.assertIn("About Task", str(ctx.exception))

    def test_empty_bot_name_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            make_settings(bot_name="   ").validate()

    def test_empty_edit_comment_is_rejected(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            make_settings(edit_comment="").validate()
        self.assertIn("edit_comment", str(ctx.exception))

    def test_empty_user_agent_is_rejected(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            make_settings(user_agent="").validate()
        self.assertIn("user_agent", str(ctx.exception))

    def test_safe_and_unsafe_tag_lists_are_mutually_exclusive(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            make_settings(safe_tag_list=["ref"], unsafe_tag_list=["script"]).validate()
        self.assertIn("cannot both be set", str(ctx.exception))

    def test_diff_size_must_be_positive(self) -> None:
        with self.assertRaises(ValueError):
            make_settings(max_acceptable_diff_size=0).validate()

    def test_request_max_tries_must_be_at_least_one(self) -> None:
        with self.assertRaises(ValueError):
            make_settings(request_max_tries=0).validate()

    def test_request_timeout_must_be_positive(self) -> None:
        with self.assertRaises(ValueError):
            make_settings(request_timeout=-1).validate()

    def test_invalid_log_level_is_rejected(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            make_settings(log_level=9).validate()
        self.assertIn("log_level", str(ctx.exception))

    def test_enable_cangjie_is_accepted(self) -> None:
        make_settings(enable_cangjie=True).validate()

    def test_isbn_style_accepts_known_conventions(self) -> None:
        for style in ("qiuwen", "moegirl", "Qiuwen"):
            make_settings(isbn_template_style=style).validate()

    def test_unknown_isbn_style_is_rejected(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            make_settings(isbn_template_style="other").validate()
        self.assertIn("isbn_template_style", str(ctx.exception))

    def test_mistyped_isbn_template_names_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            make_settings(isbn_template_names="ISBN").validate()

    def test_invisible_character_settings_are_accepted(self) -> None:
        make_settings(
            enable_invisible_chars_fix=True,
            invisible_chars_aggressive=True,
        ).validate()

    def test_page_id_end_lower_than_start_is_rejected(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            make_settings(category="", page_id_start=10, page_id_end=5).validate()
        self.assertIn("page_id_end", str(ctx.exception))

    def test_page_id_span_is_capped(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            make_settings(
                category="", page_id_start=1, page_id_end=MAX_PAGEID_SPAN + 10
            ).validate()
        self.assertIn("safety limit", str(ctx.exception))


class PageidRangeTest(unittest.TestCase):
    def test_disabled_when_start_is_zero(self) -> None:
        self.assertIsNone(make_settings(page_id_start=0, page_id_end=99).pageid_range())

    def test_end_zero_means_single_page(self) -> None:
        self.assertEqual(make_settings(page_id_start=7, page_id_end=0).pageid_range(), (7, 7))

    def test_inclusive_range(self) -> None:
        self.assertEqual(make_settings(page_id_start=3, page_id_end=9).pageid_range(), (3, 9))


class SettingsLoadingTest(unittest.TestCase):
    def test_reads_a_toml_file(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "settings.toml"
            path.write_text(
                'api_endpoint = "https://x.example/"\n'
                'is_owner_only = true\n'
                'category = "C"\n'
                'log_level = 4\n',
                encoding="utf-8",
            )
            loaded = Settings(path)
            loaded.validate()
            self.assertEqual(loaded.api_endpoint, "https://x.example/")
            self.assertEqual(loaded.log_level, 4)
            # Untouched keys keep their declared defaults.
            self.assertEqual(loaded.request_max_tries, 3)

    def test_missing_file_is_reported(self) -> None:
        with self.assertRaises(ValueError):
            Settings(Path("/nonexistent/settings.toml"))

    def test_describe_lists_effective_values(self) -> None:
        described = make_settings().describe()
        self.assertIn("api_endpoint is set to 'https://wiki.example.com/'", described)
        self.assertIn("request_max_tries", described)


if __name__ == "__main__":
    unittest.main()
