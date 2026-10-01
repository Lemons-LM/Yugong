"""Utility modules: locking, heartbeats, cache, links, length, signatures."""

from __future__ import annotations

import contextlib
import io
import json
import os
import unittest
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from src.Yugong.core.bot_db import BotDB
from src.Yugong.core.manifest import Manifest
from src.Yugong.utilities import lock as lock_module
from src.Yugong.utilities.calculate_length import (
    effective_length,
    has_invisible,
    remove_invisible,
    strip_invisible,
    text_length,
)
from src.Yugong.utilities.check_heartbeat import (
    check_heartbeat,
    heartbeat_content,
    heartbeat_matches,
    read_heartbeat,
    record_heartbeat,
)
from src.Yugong.utilities.check_same_website import check_same_website
from src.Yugong.utilities.link import (
    clean_inner_link,
    get_user_talk,
    get_username,
    make_anchor_link,
)
from src.Yugong.utilities.path_helper import PROJECT_ROOT
from src.Yugong.utilities.reporter import Reporter
from src.Yugong.utilities.sections_to_page import sections_to_page
from src.Yugong.utilities.signature_parser import (
    datetime_to_iso,
    iso_to_datetime,
    parse_cn_date,
    parse_timestamp,
)


class LockTest(unittest.TestCase):
    def test_acquires_and_records_the_pid(self) -> None:
        with TemporaryDirectory() as tmp:
            target = Path(tmp) / "lock"
            with mock.patch.object(lock_module, "LOCK_PATH", target):
                self.assertTrue(lock_module.lock())
                self.assertEqual(target.read_text(encoding="utf-8"), str(os.getpid()))
                lock_module.unlock()
                self.assertFalse(target.exists())

    def test_refuses_when_another_live_process_holds_it(self) -> None:
        with TemporaryDirectory() as tmp:
            target = Path(tmp) / "lock"
            target.write_text("99999", encoding="utf-8")
            with mock.patch.object(lock_module, "LOCK_PATH", target), \
                 mock.patch.object(lock_module, "_pid_alive", return_value=True):
                self.assertFalse(lock_module.lock())

    def test_reclaims_a_stale_lock(self) -> None:
        with TemporaryDirectory() as tmp:
            target = Path(tmp) / "lock"
            target.write_text("99999", encoding="utf-8")
            with mock.patch.object(lock_module, "LOCK_PATH", target), \
                 mock.patch.object(lock_module, "_pid_alive", return_value=False):
                self.assertTrue(lock_module.lock())
                self.assertEqual(target.read_text(encoding="utf-8"), str(os.getpid()))

    def test_unlock_ignores_a_missing_file(self) -> None:
        with TemporaryDirectory() as tmp:
            with mock.patch.object(lock_module, "LOCK_PATH", Path(tmp) / "lock"):
                lock_module.unlock()


class HeartbeatTest(unittest.TestCase):
    def test_token_is_per_wiki_and_per_day(self) -> None:
        moment = datetime(2026, 2, 14, 23, 59)
        self.assertEqual(heartbeat_content(wiki_tag="wiki", moment=moment), "wiki:2026-02-14")

    def test_first_run_of_the_day_is_allowed(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "nested" / "heartbeat"
            self.assertTrue(check_heartbeat(file=path, content="wiki:2026-02-14"))
            self.assertEqual(path.read_text(encoding="utf-8"), "wiki:2026-02-14")

    def test_second_run_of_the_same_day_is_refused(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "heartbeat"
            self.assertTrue(check_heartbeat(file=path, content="wiki:2026-02-14"))
            self.assertFalse(check_heartbeat(file=path, content="wiki:2026-02-14"))

    def test_next_day_is_allowed_again(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "heartbeat"
            check_heartbeat(file=path, content="wiki:2026-02-14")
            self.assertTrue(check_heartbeat(file=path, content="wiki:2026-02-15"))

    def test_reading_and_recording_are_separate(self) -> None:
        """A run must not claim the day before it knows it can start."""
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "heartbeat"
            self.assertEqual(read_heartbeat(file=path), "")
            self.assertFalse(heartbeat_matches(file=path, content="wiki:2026-02-14"))

            record_heartbeat(file=path, content="wiki:2026-02-14")

            self.assertEqual(read_heartbeat(file=path), "wiki:2026-02-14")
            self.assertTrue(heartbeat_matches(file=path, content="wiki:2026-02-14"))


class ManifestTest(unittest.TestCase):
    def test_creates_a_new_file(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "sub" / "cache.json"
            manifest = Manifest(path)
            self.assertEqual(manifest.data, {})
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), {})

    def test_round_trip(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "cache.json"
            manifest = Manifest(path)
            manifest.save({"url": "https://x/", "todo": ["A", "B"]})
            self.assertEqual(
                Manifest(path).data, {"url": "https://x/", "todo": ["A", "B"]}
            )

    def test_corrupt_file_is_replaced(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "cache.json"
            path.write_text("{not json", encoding="utf-8")
            self.assertEqual(Manifest(path).data, {})
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), {})

    def test_non_object_json_is_replaced(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "cache.json"
            path.write_text("[1, 2]", encoding="utf-8")
            self.assertEqual(Manifest(path).data, {})


class ReporterTest(unittest.TestCase):
    def test_collects_issues_per_module(self) -> None:
        reporter = Reporter()
        self.assertTrue(reporter.is_empty())
        reporter.add("safety", "page A skipped")
        reporter.add("safety", "page B skipped")
        reporter.add("submit", "page C failed")

        self.assertFalse(reporter.is_empty())
        body = reporter.body()
        self.assertIn("safety:", body)
        self.assertIn("- page A skipped", body)
        self.assertIn("- page C failed", body)

    def test_report_does_not_raise_without_mail_credentials(self) -> None:
        reporter = Reporter()
        reporter.report()  # empty -> nothing to send
        reporter.add("safety", "something")
        reporter.report()  # mailer is disabled in tests, must stay silent

    def test_print_report_does_not_raise(self) -> None:
        reporter = Reporter()
        reporter.print_report()
        reporter.add("safety", "something")
        with contextlib.redirect_stdout(io.StringIO()) as buffer:
            reporter.print_report()
        self.assertIn("something", buffer.getvalue())


class LinkTest(unittest.TestCase):
    def test_username_normalisation(self) -> None:
        self.assertEqual(get_username("Foo"), "User:Foo")
        self.assertEqual(get_username("user:foo"), "User:Foo")
        self.assertEqual(get_username("User talk:Foo"), "User:Foo")
        self.assertEqual(get_username("[[User:Foo|display]]"), "User:Foo")
        self.assertEqual(get_username("User:Foo/Subpage"), "User:Foo")
        self.assertEqual(get_username("Foo_bar"), "User:Foo bar")
        self.assertEqual(get_username("Foo", pure=True), "Foo")

    def test_uplinkable_user_names_return_empty(self) -> None:
        self.assertEqual(get_username("Some:Namespace"), "")
        self.assertEqual(get_user_talk("Some:Namespace"), "")

    def test_user_talk_titles(self) -> None:
        self.assertEqual(get_user_talk("Foo"), "User talk:Foo")
        self.assertEqual(get_user_talk("Foo", pure=True), "Foo")

    def test_anchor_links(self) -> None:
        self.assertEqual(make_anchor_link("Page", "Topic"), "[[Page#Topic|Topic]]")

    def test_anchor_links_escape_illegal_characters(self) -> None:
        self.assertEqual(
            make_anchor_link("Page", "a|b"),
            "[[Page#a&#124;b|a&#124;b]]",
        )

    def test_clean_inner_link_strips_markup(self) -> None:
        self.assertEqual(clean_inner_link("[[Target]]"), "Target")
        self.assertEqual(clean_inner_link("<span>x</span>y"), "y")


class CalculateLengthTest(unittest.TestCase):
    def test_ascii_counts_half(self) -> None:
        self.assertEqual(text_length("abcd"), 2.0)
        self.assertEqual(text_length("ab cd"), 2.0)

    def test_non_ascii_counts_one(self) -> None:
        self.assertEqual(text_length("中文"), 2.0)

    def test_invisible_character_detection(self) -> None:
        self.assertTrue(has_invisible("a\u200bb"))
        self.assertFalse(has_invisible("ab"))
        self.assertEqual(remove_invisible("a\u200bb"), "ab")
        self.assertEqual(strip_invisible("a b\nc"), "abc")

    def test_refs_and_comments_are_not_counted(self) -> None:
        self.assertEqual(effective_length("x<ref>hidden</ref>y"), 1.0)
        self.assertEqual(effective_length("x<!--hidden-->y"), 1.0)

    def test_file_and_category_links_are_not_counted(self) -> None:
        self.assertEqual(effective_length("x[[Category:C]]y"), 1.0)
        self.assertEqual(effective_length("x[[File:A.jpg]]y"), 1.0)

    def test_wikilink_display_text_is_counted(self) -> None:
        self.assertEqual(effective_length("x[[Target|shown]]y"), 0.5 + 2.5 + 0.5)

    def test_top_of_page_templates_are_dropped(self) -> None:
        self.assertEqual(effective_length("{{Navbox}}Text"), 2.0)

    def test_template_parameters_are_counted(self) -> None:
        self.assertEqual(effective_length("x{{t|a=中文}}"), 0.5 + 2.0)


class SignatureParserTest(unittest.TestCase):
    def test_parses_a_wiki_timestamp(self) -> None:
        parsed = parse_timestamp("2026年3月30日 (一) 20:57 (CST)")
        self.assertEqual(parsed, datetime(2026, 3, 30, 20, 57))

    def test_unparseable_timestamp_is_none(self) -> None:
        self.assertIsNone(parse_timestamp("no timestamp here"))

    def test_parses_a_chinese_date(self) -> None:
        self.assertEqual(parse_cn_date("2026年4月2日"), datetime(2026, 4, 2))

    def test_impossible_date_is_none(self) -> None:
        self.assertIsNone(parse_cn_date("2026年13月40日"))

    def test_iso_round_trip(self) -> None:
        moment = datetime(2026, 4, 2, 10, 30)
        self.assertEqual(iso_to_datetime(datetime_to_iso(moment)), moment)

    def test_none_and_invalid_values(self) -> None:
        self.assertIsNone(datetime_to_iso(None))
        self.assertIsNone(iso_to_datetime(None))
        self.assertIsNone(iso_to_datetime("not a date"))


class SectionsToPageTest(unittest.TestCase):
    def test_joins_sections(self) -> None:
        self.assertEqual(sections_to_page(["a", "b"]), "a\n\nb\n\n")

    def test_prepends_original_content(self) -> None:
        self.assertEqual(sections_to_page(["a"], original_content="lead"), "lead\na\n\n")


class CheckSameWebsiteTest(unittest.TestCase):
    def test_same_domain_ignoring_www_and_port(self) -> None:
        self.assertTrue(
            check_same_website(
                "https://www.example.com/x", api_endpoint="https://example.com:8080/api.php"
            )
        )

    def test_bare_domain_is_accepted(self) -> None:
        self.assertTrue(
            check_same_website("example.com", api_endpoint="https://example.com/api.php")
        )

    def test_different_domain_is_rejected(self) -> None:
        self.assertFalse(
            check_same_website("https://other.example/", api_endpoint="https://example.com/")
        )

    def test_empty_input_is_rejected(self) -> None:
        self.assertFalse(check_same_website("", api_endpoint="https://example.com/"))
        self.assertFalse(check_same_website("https://example.com/", api_endpoint=""))
        self.assertFalse(check_same_website("", api_endpoint=""))


class BotDBTest(unittest.TestCase):
    def test_crud_round_trip(self) -> None:
        with TemporaryDirectory() as tmp:
            db = BotDB(db_path=Path(tmp) / "db.sqlite3")

            self.assertTrue(db.insert("template", {"title": "A", "target": "B", "type": "void"}))
            rows = db.search("template", {"title": "A"})
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["type"], "void")

            self.assertTrue(db.update("template", {"type": "normal"}, {"title": "A"}))
            self.assertEqual(db.search("template", {"title": "A"})[0]["type"], "normal")

            self.assertTrue(db.delete("template", {"title": "A"}))
            self.assertEqual(db.search("template", {"title": "A"}), [])

    def test_numeric_looking_titles_stay_strings(self) -> None:
        """Regression: every string used to be fed through json.loads()."""
        with TemporaryDirectory() as tmp:
            db = BotDB(db_path=Path(tmp) / "db.sqlite3")
            db.insert("template", {"title": "2024", "target": "Template:2024"})
            rows = db.search("template", {"title": "2024"})
            self.assertEqual(rows[0]["title"], "2024")
            self.assertIsInstance(rows[0]["title"], str)

    def test_json_containers_round_trip(self) -> None:
        with TemporaryDirectory() as tmp:
            db = BotDB(db_path=Path(tmp) / "db.sqlite3")
            db.insert("alias", {"title": "A", "target": ["x", "y"]})
            self.assertEqual(db.search("alias", {"title": "A"})[0]["target"], ["x", "y"])


class PathHelperTest(unittest.TestCase):
    def test_project_root_contains_the_markers(self) -> None:
        self.assertTrue((PROJECT_ROOT / "pyproject.toml").exists())
        self.assertTrue((PROJECT_ROOT / "settings.toml").exists())


if __name__ == "__main__":
    unittest.main()
