"""Core domain objects: Wikitext, TemplateFormatter and the logger."""

from __future__ import annotations

import contextlib
import io
import logging
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from unittest import mock

from src.Yugong.core.logger import LEVEL_MAP, configure_logging, level_from_setting
from src.Yugong.core.settings import settings
from src.Yugong.core.template_formatter import formatter
from src.Yugong.core.wikitext import Wikitext

from tests.support import make_wikitext


class WikitextTest(unittest.TestCase):
    def test_parse_and_text(self) -> None:
        wikitext = make_wikitext("hello {{tpl|a=1}}")
        self.assertEqual(wikitext.text, "hello {{tpl|a=1}}")
        self.assertEqual(wikitext.original_content, "hello {{tpl|a=1}}")
        self.assertEqual(wikitext.title, "Test page")

    def test_metadata_is_converted(self) -> None:
        wikitext = Wikitext({"title": "T", "pageid": "12", "revid": "34", "namespace": "0"})
        self.assertEqual(wikitext.page_id, 12)
        self.assertEqual(wikitext.revid, 34)
        self.assertEqual(wikitext.namespace, 0)

    def test_reading_before_parsing_fails_loudly(self) -> None:
        wikitext = Wikitext({"title": "T"})
        with self.assertRaises(ValueError) as ctx:
            _ = wikitext.wikitext
        self.assertIn("has not been parsed", str(ctx.exception))

    def test_update_accepts_string_and_wikicode(self) -> None:
        wikitext = make_wikitext("a")
        wikitext.update("b")
        self.assertEqual(wikitext.text, "b")
        self.assertEqual(wikitext.processed_content, "b")

        wikitext.update(make_wikitext("c").wikitext)
        self.assertEqual(wikitext.text, "c")

    def test_update_rejects_other_types(self) -> None:
        wikitext = make_wikitext("a")
        with self.assertRaises(TypeError):
            wikitext.update(42)  # type: ignore[arg-type]

    def test_accessor_snapshots(self) -> None:
        wikitext = make_wikitext("{{t|a=1}}[[Link]]<ref>x</ref>")
        self.assertEqual(len(wikitext.templates()), 1)
        self.assertEqual(len(wikitext.wikilinks()), 1)
        self.assertEqual(len(wikitext.tags()), 1)


class TemplateFormatterTest(unittest.TestCase):
    def setUp(self) -> None:
        self._saved = dict(formatter.RULES)
        self._saved_loaded = formatter.loaded
        formatter.RULES.clear()
        formatter.loaded = False

    def tearDown(self) -> None:
        formatter.RULES.clear()
        formatter.RULES.update(self._saved)
        formatter.loaded = self._saved_loaded

    def add_rule(self, **rule: Any) -> None:
        rule.setdefault("introduction", "test rule")
        with contextlib.redirect_stdout(io.StringIO()):
            formatter._add_rule(rule, "test.toml")

    def apply(self, text: str) -> str:
        wikitext = make_wikitext(text)
        formatter.format_template(wikitext)
        return str(wikitext)

    def test_rename_uses_the_first_name_as_canonical(self) -> None:
        self.add_rule(names=["New", "old"], template_level={"rename": True})
        self.assertEqual(self.apply("{{old|a=1}}"), "{{New|a=1}}")
        self.assertEqual(self.apply("{{New|a=1}}"), "{{New|a=1}}")
        self.assertEqual(self.apply("{{other|a=1}}"), "{{other|a=1}}")

    def test_rename_can_be_disabled_by_settings(self) -> None:
        self.add_rule(names=["New", "old"], template_level={"rename": True})
        with mock.patch.object(settings, "overwrite_template_name", False):
            self.assertEqual(self.apply("{{old|a=1}}"), "{{old|a=1}}")

    def test_delete_removes_the_template(self) -> None:
        self.add_rule(names=["old"], template_level={"delete": True})
        self.assertEqual(self.apply("x{{old|a=1}}y"), "xy")

    def test_deleting_an_outer_template_skips_detached_children(self) -> None:
        """Regression: removing a parent then its child raised ValueError."""
        self.add_rule(names=["Outer", "Inner"], template_level={"delete": True})
        self.assertEqual(self.apply("a{{Outer|{{Inner|x=1}}}}b"), "ab")

    def test_replace_expands_positional_and_named_arguments(self) -> None:
        self.add_rule(names=["old"], template_level={"replace": "{{{1}}}-{{{foo|none}}}"})
        self.assertEqual(self.apply("{{old|a|foo=b}}"), "a-b")

    def test_replace_falls_back_to_the_default(self) -> None:
        self.add_rule(names=["old"], template_level={"replace": "{{{bar|fallback}}}"})
        self.assertEqual(self.apply("{{old|a}}"), "fallback")

    def test_nested_default_arguments_do_not_crash_on_detached_nodes(self) -> None:
        """Replacing the outer argument detaches the inner one from the snapshot."""
        self.add_rule(
            names=["old"], template_level={"replace": "{{{missing|{{{inner}}}}}}"}
        )
        self.assertEqual(self.apply("{{old|inner=X}}"), "X")

    def test_param_rename(self) -> None:
        self.add_rule(
            names=["old"],
            params=[{"names": ["year"], "rename": True, "new_name": "date"}],
        )
        self.assertEqual(self.apply("{{old|year=2020}}"), "{{old|date=2020}}")

    def test_param_rename_supports_regex_names(self) -> None:
        self.add_rule(
            names=["old"],
            params=[{"names": ["access[-_]date"], "rename": True, "new_name": "access-date"}],
        )
        self.assertEqual(self.apply("{{old|access_date=1}}"), "{{old|access-date=1}}")

    def test_param_rename_can_be_disabled_by_settings(self) -> None:
        self.add_rule(
            names=["old"],
            params=[{"names": ["year"], "rename": True, "new_name": "date"}],
        )
        with mock.patch.object(settings, "overwrite_para_name", False):
            self.assertEqual(self.apply("{{old|year=2020}}"), "{{old|year=2020}}")

    def test_param_delete(self) -> None:
        self.add_rule(names=["old"], params=[{"names": ["year"], "delete": True}])
        self.assertEqual(self.apply("{{old|year=2020|x=1}}"), "{{old|x=1}}")

    def test_match_replaces_a_whole_value_once(self) -> None:
        """The documented ``match = ".*"`` must not produce "deaddead"."""
        self.add_rule(
            names=["old"],
            params=[{
                "names": ["deadurl"],
                "match": [{
                    "condition": "yes|true|dead",
                    "mode": True,
                    "match": ".*",
                    "replacement": "dead",
                }],
            }],
        )
        self.assertEqual(self.apply("{{old|deadurl=yes}}"), "{{old|deadurl=dead}}")

    def test_match_mode_false_applies_when_the_condition_does_not_match(self) -> None:
        self.add_rule(
            names=["old"],
            params=[{
                "names": ["year"],
                "match": [{
                    "condition": "2020",
                    "mode": False,
                    "match": ".*",
                    "replacement": "later",
                }],
            }],
        )
        self.assertEqual(self.apply("{{old|year=2019}}"), "{{old|year=later}}")
        self.assertEqual(self.apply("{{old|year=2020}}"), "{{old|year=2020}}")

    def test_match_supports_backreferences(self) -> None:
        self.add_rule(
            names=["old"],
            params=[{
                "names": ["d"],
                "match": [{
                    "condition": r"\d{4}",
                    "mode": True,
                    "match": r"(\d{4})-(\d{2})",
                    "replacement": r"\2/\1",
                }],
            }],
        )
        self.assertEqual(self.apply("{{old|d=2020-01}}"), "{{old|d=01/2020}}")

    def test_conflicting_template_level_actions_are_rejected(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            self.add_rule(names=["old"], template_level={"delete": True, "rename": True})
        self.assertIn("conflicting", str(ctx.exception))

    def test_rule_without_names_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.add_rule(names=[])

    def test_invalid_parameter_name_regex_is_rejected_at_load_time(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            self.add_rule(names=["old"], params=[{"names": ["[unclosed"]}])
        self.assertIn("invalid regular expression", str(ctx.exception))

    def test_rename_without_new_name_is_rejected(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            self.add_rule(names=["old"], params=[{"names": ["year"], "rename": True}])
        self.assertIn("requires 'new_name'", str(ctx.exception))

    def test_invalid_condition_regex_is_rejected(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            self.add_rule(
                names=["old"],
                params=[{
                    "names": ["year"],
                    "match": [{"condition": "([", "match": ".*", "replacement": "x"}],
                }],
            )
        self.assertIn("invalid regular expression", str(ctx.exception))

    def test_match_without_condition_is_rejected(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            self.add_rule(
                names=["old"],
                params=[{"names": ["year"], "match": [{"match": ".*", "replacement": "x"}]}],
            )
        self.assertIn("condition", str(ctx.exception))

    def test_apply_websites_must_be_a_string_list(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            self.add_rule(names=["old"], apply_websites="example.com")
        self.assertIn("apply_websites", str(ctx.exception))

    def test_names_must_be_a_list_not_a_string(self) -> None:
        """``names = "xy"`` used to register one-character rules X and Y."""
        with self.assertRaises(ValueError) as ctx:
            self.add_rule(names="xy", template_level={"delete": True})
        self.assertIn("list of strings", str(ctx.exception))

    def test_introduction_must_be_a_string(self) -> None:
        with self.assertRaises(ValueError):
            with contextlib.redirect_stdout(io.StringIO()):
                formatter._add_rule({"names": ["x"], "introduction": 1}, "broken.toml")

    def test_get_ruleset_rejects_apply_websites_before_filtering(self) -> None:
        """A string value used to be iterated per character and skipped."""
        from src.Yugong.core import template_formatter as tf_module

        with TemporaryDirectory() as tmp:
            rules = Path(tmp) / "template_rules"
            rules.mkdir()
            (rules / "bad.toml").write_text(
                'names = ["X"]\n'
                'introduction = "bad"\n'
                'apply_websites = "example.com"\n'
                '[template_level]\ndelete = true\n',
                encoding="utf-8",
            )
            with mock.patch.object(tf_module, "PROJECT_ROOT", Path(tmp)):
                with self.assertRaises(ValueError) as ctx:
                    formatter.get_ruleset()
            self.assertIn("apply_websites", str(ctx.exception))

    def test_rule_without_introduction_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            with contextlib.redirect_stdout(io.StringIO()):
                formatter._add_rule({"names": ["x"]}, "broken.toml")

    def test_duplicate_rule_is_rejected(self) -> None:
        self.add_rule(names=["old"])
        with self.assertRaises(ValueError) as ctx:
            self.add_rule(names=["Old"])
        self.assertIn("Duplicate template rule", str(ctx.exception))

    def test_ruleset_is_reloaded_not_appended(self) -> None:
        formatter.RULES["Stale"] = {"file_name": "stale.toml", "names": ["Stale"]}
        with contextlib.redirect_stdout(io.StringIO()):
            formatter.get_ruleset()
        self.assertNotIn("Stale", formatter.RULES)

    def test_ensure_ruleset_loads_only_once(self) -> None:
        with contextlib.redirect_stdout(io.StringIO()):
            formatter.ensure_ruleset()
        self.assertTrue(formatter.loaded)

        # A second call must not reload (and therefore must not wipe the rules).
        formatter.RULES["Marker"] = {"file_name": "marker.toml", "names": ["Marker"]}
        formatter.ensure_ruleset()
        self.assertIn("Marker", formatter.RULES)

    def test_safe_capitalize(self) -> None:
        self.assertEqual(formatter._safe_capitalize("  infobox "), "Infobox")
        self.assertEqual(formatter._safe_capitalize("2x"), "2x")
        self.assertEqual(formatter._safe_capitalize(""), "")


class LoggerTest(unittest.TestCase):
    def test_level_map_covers_the_documented_scale(self) -> None:
        self.assertEqual(level_from_setting(0), logging.CRITICAL)
        self.assertEqual(level_from_setting(3), logging.INFO)
        self.assertEqual(level_from_setting(4), logging.DEBUG)
        self.assertEqual(set(LEVEL_MAP), {0, 1, 2, 3, 4})

    def test_invalid_level_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            level_from_setting(99)

    def test_configure_logging_applies_and_does_not_raise(self) -> None:
        try:
            configure_logging(log_level=4, log_timestamps=False)
            configure_logging(log_level=1, log_timestamps=True)
        finally:
            configure_logging(log_level=settings.log_level, log_timestamps=True)


if __name__ == "__main__":
    unittest.main()
