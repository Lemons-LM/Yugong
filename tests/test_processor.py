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
from src.Yugong.processor.do_jobs import (
    diff_size,
    disallowed_tags,
    pageid_batches,
    strip_namespace_prefix,
)
from src.Yugong.processor.pipeline import TEMPLATE_RULE_STEP, apply_steps, build_steps
from src.Yugong.utilities.check_heartbeat import heartbeat_content, record_heartbeat
from src.Yugong.utilities.mark_job_intro import (
    NEEDS_WIKI_ATTR,
    PRE_TEMPLATE_ATTR,
)

from tests.support import make_wikitext


def _plain_job(wikitext: Wikitext) -> None:
    return None


def _wiki_job(wikitext: Wikitext) -> None:
    return None


def _pre_job(wikitext: Wikitext) -> None:
    return None


setattr(_wiki_job, NEEDS_WIKI_ATTR, True)
setattr(_pre_job, PRE_TEMPLATE_ATTR, True)


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

    def test_large_pages_use_a_line_based_estimate(self) -> None:
        """Above EXACT_DIFF_CHARS the estimate must stay small for a tiny edit."""
        old = "".join(f"line {index}\n" for index in range(3000))
        new = old.replace("line 1500\n", "line 1500 changed\n")
        self.assertLess(diff_size(old, new), 100)

    def test_large_page_rewrite_is_still_rejected_by_size(self) -> None:
        old = "".join(f"line {index}\n" for index in range(3000))
        self.assertGreater(diff_size(old, "completely different\n"), 1000)


class NamespacePrefixTest(unittest.TestCase):
    def test_prefix_is_removed_case_insensitively(self) -> None:
        self.assertEqual(strip_namespace_prefix("Template:Navbox", "Template"), "Navbox")
        self.assertEqual(strip_namespace_prefix("template:Navbox", "Template"), "Navbox")
        self.assertEqual(strip_namespace_prefix("  Navbox  ", "Template"), "Navbox")

    def test_an_unrelated_name_is_untouched(self) -> None:
        self.assertEqual(strip_namespace_prefix("MyTemplate", "Template"), "MyTemplate")


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

    def test_pre_template_jobs_run_before_template_rules(self) -> None:
        wikitext = make_wikitext("a")
        steps, _ = build_steps(wikitext, jobs=[_plain_job, _pre_job])
        self.assertEqual(
            [name for name, _ in steps],
            ["_pre_job", TEMPLATE_RULE_STEP, "_plain_job"],
        )

    def test_pre_template_jobs_stay_out_when_wiki_jobs_are_skipped(self) -> None:
        wikitext = make_wikitext("a")
        setattr(_pre_job, NEEDS_WIKI_ATTR, True)
        try:
            steps, skipped = build_steps(
                wikitext, apply_rules=False, include_wiki_jobs=False, jobs=[_pre_job]
            )
        finally:
            setattr(_pre_job, NEEDS_WIKI_ATTR, False)
        self.assertEqual(steps, [])
        self.assertEqual(skipped, ["_pre_job"])

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

    def test_an_api_php_cache_url_is_normalised_not_rejected(self) -> None:
        """An older cache stored ``.../api.php``; it is the same wiki."""
        with TemporaryDirectory() as tmp:
            manifest = Manifest(Path(tmp) / "cache.json")
            manifest.save({"url": "https://x/api.php", "todo": ["A"]})

            with mock.patch.object(do_jobs.wiki, "api_endpoint", "https://x/"):
                self.assertEqual(do_jobs._prepare_manifest(manifest, ["B"]), ["A", "B"])
            self.assertEqual(manifest.data["url"], "https://x/")


class HeartbeatGuardTest(unittest.TestCase):
    def test_reads_without_claiming_and_refuses_a_second_run(self) -> None:
        with TemporaryDirectory() as tmp:
            base = Path(tmp) / "heartbeat_daily"
            today = heartbeat_content(wiki_tag="wiki")

            with mock.patch.object(do_jobs, "DAILY_HEARTBEAT_FILE", str(base)), \
                 mock.patch.object(do_jobs.settings, "wiki_tag", "wiki"), \
                 mock.patch.object(do_jobs.mailer, "email") as email:
                effective = Path(do_jobs.daily_heartbeat_file())
                self.assertTrue(do_jobs._heartbeat_ok())
                # Checking must not consume the day's slot.
                self.assertFalse(effective.exists())

                record_heartbeat(file=effective, content=today)

                self.assertFalse(do_jobs._heartbeat_ok())

            self.assertEqual(email.call_count, 1)

    def test_each_wiki_gets_its_own_daily_heartbeat(self) -> None:
        with TemporaryDirectory() as tmp:
            with mock.patch.object(do_jobs, "DAILY_HEARTBEAT_FILE", str(Path(tmp) / "hb")), \
                 mock.patch.object(do_jobs.settings, "wiki_tag", "alpha"):
                alpha = do_jobs.daily_heartbeat_file()
            with mock.patch.object(do_jobs, "DAILY_HEARTBEAT_FILE", str(Path(tmp) / "hb")), \
                 mock.patch.object(do_jobs.settings, "wiki_tag", "beta"):
                beta = do_jobs.daily_heartbeat_file()
            self.assertNotEqual(alpha, beta)


class _FakeNamespace:
    """Mimics pywikibot 11's Namespace: ``str()`` is ':' for the main namespace."""

    def __str__(self) -> str:
        return ":"

    def __int__(self) -> int:
        return 0


class SubmitChangesTest(unittest.TestCase):
    def test_save_is_guarded_by_the_revision_that_was_read(self) -> None:
        page = mock.Mock()
        page.title.return_value = "T"
        page.pageid = 1
        page.latest_revision = mock.Mock(revid=42, text="old")
        page.namespace.return_value = _FakeNamespace()

        def add_marker(wikitext: Wikitext, _name: str, _steps: object) -> list[str]:
            wikitext.wikitext.append("!")
            return ["marker"]

        with mock.patch.object(do_jobs.wiki, "page", return_value=page), \
             mock.patch.object(do_jobs.settings, "submit_changes", True), \
             mock.patch.object(do_jobs, "build_steps", return_value=([], [])), \
             mock.patch.object(do_jobs, "apply_steps", side_effect=add_marker):
            self.assertTrue(do_jobs._process_single_page("T"))

        page.save.assert_called_once()
        kwargs = page.save.call_args.kwargs
        self.assertEqual(kwargs["baserevid"], 42)
        self.assertFalse(kwargs["apply_cosmetic_changes"])


class ManualCopyTest(unittest.TestCase):
    def test_pages_whose_names_sanitise_the_same_do_not_overwrite(self) -> None:
        with TemporaryDirectory() as tmp:
            with mock.patch.object(do_jobs, "PROJECT_ROOT", Path(tmp)):
                first = do_jobs._save_manual_copy("A/B", "first")
                second = do_jobs._save_manual_copy("A:B", "second")
            self.assertNotEqual(first, second)
            self.assertEqual(Path(first).read_text(encoding="utf-8"), "first")
            self.assertEqual(Path(second).read_text(encoding="utf-8"), "second")


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
