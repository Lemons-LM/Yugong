"""The processing loop: pure helpers, the step pipeline and offline dev mode."""

from __future__ import annotations

import contextlib
import io
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from src.Yugong.core import wiki as wiki_module
from src.Yugong.core.manifest import Manifest
from src.Yugong.core.wikitext import Wikitext
from src.Yugong.processor import do_jobs
from src.Yugong.processor.dev_mode import run_dev_mode
from src.Yugong.processor.do_jobs import diff_size, disallowed_tags, pageid_batches
from src.Yugong.processor.pipeline import TEMPLATE_RULE_STEP, apply_steps, build_steps
from src.Yugong.utilities.check_heartbeat import heartbeat_content, record_heartbeat
from src.Yugong.utilities.mark_job_intro import NEEDS_WIKI_ATTR

from tests.support import make_wikitext


def _plain_job(wikitext: Wikitext) -> None:
    return None


def _wiki_job(wikitext: Wikitext) -> None:
    return None


setattr(_wiki_job, NEEDS_WIKI_ATTR, True)


class DiffSizeTest(unittest.TestCase):
    def test_identical_text_has_no_diff(self) -> None:
        self.assertEqual(diff_size("abc", "abc"), 0)

    def test_single_character_change(self) -> None:
        self.assertEqual(diff_size("abc", "abd"), 1)

    def test_insertion_is_counted(self) -> None:
        self.assertEqual(diff_size("", "abc"), 3)
        self.assertEqual(diff_size("ac", "abc"), 1)

    def test_deletion_is_counted(self) -> None:
        self.assertEqual(diff_size("abc", ""), 3)
        self.assertEqual(diff_size("abc", "ac"), 1)

    def test_large_rewrite(self) -> None:
        self.assertEqual(diff_size("aaaa", "bbbb"), 4)


class PageidBatchesTest(unittest.TestCase):
    def test_splits_into_inclusive_batches(self) -> None:
        self.assertEqual(pageid_batches(1, 5, size=2), [[1, 2], [3, 4], [5]])

    def test_exact_multiple_does_not_add_an_empty_batch(self) -> None:
        self.assertEqual(pageid_batches(1, 4, size=2), [[1, 2], [3, 4]])

    def test_single_page(self) -> None:
        self.assertEqual(pageid_batches(7, 7), [[7]])

    def test_reversed_range_is_empty(self) -> None:
        self.assertEqual(pageid_batches(5, 1), [])

    def test_invalid_size_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            pageid_batches(1, 5, size=0)


class DisallowedTagsTest(unittest.TestCase):
    def test_no_policy_allows_everything(self) -> None:
        self.assertEqual(disallowed_tags({"ref", "span"}, safe=[], unsafe=[]), set())

    def test_deny_list(self) -> None:
        self.assertEqual(
            disallowed_tags({"ref", "span"}, safe=[], unsafe=["span", "script"]),
            {"span"},
        )

    def test_allow_list_flags_anything_else(self) -> None:
        self.assertEqual(
            disallowed_tags({"ref", "br", "span"}, safe=["ref", "br"], unsafe=[]),
            {"span"},
        )

    def test_matching_is_case_insensitive(self) -> None:
        self.assertEqual(disallowed_tags({"SPAN"}, safe=[], unsafe=["span"]), {"span"})

    def test_both_policies_at_once_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            disallowed_tags({"ref"}, safe=["ref"], unsafe=["script"])


class PipelineTest(unittest.TestCase):
    def test_wiki_jobs_are_skipped_when_asked(self) -> None:
        wikitext = make_wikitext("a")
        steps, skipped = build_steps(
            wikitext, apply_rules=False, include_wiki_jobs=False, jobs=[_plain_job, _wiki_job]
        )
        self.assertEqual([name for name, _ in steps], ["_plain_job"])
        self.assertEqual(skipped, ["_wiki_job"])

    def test_wiki_jobs_are_included_by_default(self) -> None:
        wikitext = make_wikitext("a")
        steps, skipped = build_steps(
            wikitext, apply_rules=False, jobs=[_plain_job, _wiki_job]
        )
        self.assertEqual([name for name, _ in steps], ["_plain_job", "_wiki_job"])
        self.assertEqual(skipped, [])

    def test_template_rules_come_first(self) -> None:
        wikitext = make_wikitext("a")
        steps, _ = build_steps(wikitext, jobs=[_plain_job])
        self.assertEqual(steps[0][0], TEMPLATE_RULE_STEP)

    def test_template_rules_can_be_disabled(self) -> None:
        wikitext = make_wikitext("a")
        steps, _ = build_steps(wikitext, apply_rules=False, jobs=[_plain_job])
        self.assertEqual([name for name, _ in steps], ["_plain_job"])

    def test_apply_steps_reports_only_real_changes(self) -> None:
        wikitext = make_wikitext("a")

        def noop() -> None:
            return None

        def bang() -> None:
            wikitext.wikitext.append("!")

        applied = apply_steps(wikitext, "T", [("noop", noop), ("bang", bang)])
        self.assertEqual(applied, ["bang"])
        self.assertEqual(str(wikitext), "a!")
        self.assertEqual(wikitext.processed_content, "a!")


class GetTodoListTest(unittest.TestCase):
    """The three ways of selecting pages must all reach the todo list."""

    def setUp(self) -> None:
        for name, value in (
            ("page_id_start", 0),
            ("page_id_end", 0),
            ("linked_template", ""),
            ("category", ""),
        ):
            patcher = mock.patch.object(do_jobs.settings, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_a_selector_is_required(self) -> None:
        with self.assertRaises(ValueError):
            do_jobs._get_todo_list()

    def test_page_id_range_is_batched_and_resolved(self) -> None:
        responses = [
            {"query": {"pages": {"1": {"title": "A"}, "2": {"title": "B"}}}},
            {"query": {"pages": {"3": {"title": "C"}, "4": {"missing": ""}}}},
        ]
        with mock.patch.object(do_jobs.settings, "page_id_start", 1), \
             mock.patch.object(do_jobs.settings, "page_id_end", 3), \
             mock.patch.object(do_jobs, "PAGEID_BATCH_SIZE", 2), \
             mock.patch.object(do_jobs.wiki, "api_query", side_effect=responses) as api_query:
            self.assertEqual(do_jobs._get_todo_list(), ["A", "B", "C"])
            self.assertEqual(api_query.call_count, 2)

    def test_missing_page_ids_are_skipped(self) -> None:
        with mock.patch.object(do_jobs.settings, "page_id_start", 1), \
             mock.patch.object(do_jobs.settings, "page_id_end", 1), \
             mock.patch.object(
                 do_jobs.wiki, "api_query", return_value={"query": {"pages": {"1": {"missing": ""}}}}
             ):
            with self.assertRaises(ValueError):
                do_jobs._get_todo_list()

    def test_category_members_are_collected(self) -> None:
        member = mock.Mock()
        member.title.return_value = "Page A"
        category = mock.Mock()
        category.members.return_value = [member]

        with mock.patch.object(do_jobs.settings, "category", "Cleanup"), \
             mock.patch.object(wiki_module.Wiki, "site", mock.PropertyMock(return_value=mock.Mock())), \
             mock.patch.object(do_jobs.pywikibot, "Category", return_value=category):
            self.assertEqual(do_jobs._get_todo_list(), ["Page A"])

    def test_linked_template_members_are_collected(self) -> None:
        page = mock.Mock()
        page.title.return_value = "Page B"
        template = mock.Mock()
        template.embeddedin.return_value = [page]

        with mock.patch.object(do_jobs.settings, "linked_template", "Navbox"), \
             mock.patch.object(wiki_module.Wiki, "site", mock.PropertyMock(return_value=mock.Mock())), \
             mock.patch.object(do_jobs.pywikibot, "Page", return_value=template):
            self.assertEqual(do_jobs._get_todo_list(), ["Page B"])

    def test_duplicate_pages_are_merged(self) -> None:
        member = mock.Mock()
        member.title.return_value = "Page A"
        category = mock.Mock()
        category.members.return_value = [member, member]

        with mock.patch.object(do_jobs.settings, "category", "Cleanup"), \
             mock.patch.object(wiki_module.Wiki, "site", mock.PropertyMock(return_value=mock.Mock())), \
             mock.patch.object(do_jobs.pywikibot, "Category", return_value=category):
            self.assertEqual(do_jobs._get_todo_list(), ["Page A"])


class PrepareManifestTest(unittest.TestCase):
    def test_merges_with_the_pages_still_queued(self) -> None:
        with TemporaryDirectory() as tmp:
            manifest = Manifest(Path(tmp) / "cache.json")
            manifest.save({"url": "https://x/", "todo": ["A"]})

            with mock.patch.object(do_jobs.wiki, "api_endpoint", "https://x/"):
                merged = do_jobs._prepare_manifest(manifest, ["B", "A"])

            self.assertEqual(merged, ["A", "B"])
            self.assertEqual(manifest.data["todo"], ["A", "B"])
            self.assertEqual(manifest.data["url"], "https://x/")

    def test_a_different_wiki_url_is_rejected(self) -> None:
        with TemporaryDirectory() as tmp:
            manifest = Manifest(Path(tmp) / "cache.json")
            manifest.save({"url": "https://other/", "todo": []})

            with mock.patch.object(do_jobs.wiki, "api_endpoint", "https://x/"):
                with self.assertRaises(ValueError) as ctx:
                    do_jobs._prepare_manifest(manifest, ["A"])
            self.assertIn("wiki_tag", str(ctx.exception))


class HeartbeatGuardTest(unittest.TestCase):
    def test_reads_without_claiming_and_refuses_a_second_run(self) -> None:
        with TemporaryDirectory() as tmp:
            target = Path(tmp) / "heartbeat_daily"
            today = heartbeat_content(wiki_tag="wiki")

            with mock.patch.object(do_jobs, "DAILY_HEARTBEAT_FILE", str(target)), \
                 mock.patch.object(do_jobs.settings, "wiki_tag", "wiki"), \
                 mock.patch.object(do_jobs.mailer, "email") as email:
                self.assertTrue(do_jobs._heartbeat_ok())
                # Checking must not consume the day's slot.
                self.assertFalse(target.exists())

                record_heartbeat(file=target, content=today)

                self.assertFalse(do_jobs._heartbeat_ok())

            self.assertEqual(email.call_count, 1)


class DevModeTest(unittest.TestCase):
    def run_dev(self, content: str, *, apply_rules: bool = True) -> tuple[str, str]:
        """Run dev mode over *content*; return ``(output, console)``."""
        with TemporaryDirectory() as tmp:
            source = Path(tmp) / "in.wikitext"
            target = Path(tmp) / "out.wikitext"
            source.write_text(content, encoding="utf-8")

            buffer = io.StringIO()
            with contextlib.redirect_stdout(buffer):
                run_dev_mode(str(source), str(target), apply_rules=apply_rules)
            return target.read_text(encoding="utf-8"), buffer.getvalue()

    def test_runs_the_extensions(self) -> None:
        output, console = self.run_dev('A<ref name="orphan" />B', apply_rules=False)
        self.assertEqual(output, "AB")
        self.assertIn("rm_undefined_refs_job", console)

    def test_template_rules_are_loaded_by_default(self) -> None:
        output, console = self.run_dev('A<ref name="orphan" />B')
        self.assertEqual(output, "AB")
        self.assertNotIn("--no-template-rules", console)

    def test_wiki_jobs_are_reported_as_skipped(self) -> None:
        _, console = self.run_dev("plain text", apply_rules=False)
        self.assertIn("Skipped (need a wiki connection)", console)
        self.assertIn("category_handler_job", console)

    def test_template_rules_can_be_skipped(self) -> None:
        _, console = self.run_dev("plain text", apply_rules=False)
        self.assertIn("--no-template-rules", console)

    def test_unchanged_input_is_copied_through(self) -> None:
        output, console = self.run_dev("plain text", apply_rules=False)
        self.assertEqual(output, "plain text")
        self.assertNotIn("rm_undefined_refs_job", console)

    def test_missing_input_file_is_reported(self) -> None:
        with self.assertRaises(FileNotFoundError):
            with contextlib.redirect_stdout(io.StringIO()):
                run_dev_mode("/nonexistent/in.wikitext", "/tmp/out.wikitext")


if __name__ == "__main__":
    unittest.main()
