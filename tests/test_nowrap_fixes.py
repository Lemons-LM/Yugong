"""Navbox .w / !w / -w handling."""

from __future__ import annotations

import unittest

from src.Yugong.extensions.nowrap_fixes import nowrap_fixes_job
from src.Yugong.utilities.reporter import reporter
from tests.support import run_job


def fix(text: str) -> str:
    return run_job(nowrap_fixes_job, text, title="Test page")


class NavboxListTest(unittest.TestCase):
    def setUp(self) -> None:
        reporter.issues.clear()

    def test_dot_w_sequence_becomes_an_unordered_list(self) -> None:
        result = fix("{{Navbox|list1=A {{.w}} B {{.w}} C}}")
        self.assertIn("list1=\n* A\n* B\n* C", result)
        self.assertNotIn("{{.w}}", result)

    def test_pipe_and_dash_variants_are_supported(self) -> None:
        result = fix("{{Navbox|list1=A {{!w}} B {{-w}} C}}")
        self.assertIn("* A", result)
        self.assertIn("* B", result)
        self.assertIn("* C", result)

    def test_localised_navbox_name_is_supported(self) -> None:
        result = fix("{{导航框|list1=A {{.w}} B}}")
        self.assertIn("* A", result)
        self.assertIn("* B", result)

    def test_above_and_below_rows_are_supported(self) -> None:
        result = fix("{{Navbox|below=A {{.w}} B}}")
        self.assertIn("below=\n* A\n* B", result)
        result = fix("{{Navbox|above=A {{!w}} B}}")
        self.assertIn("above=\n* A\n* B", result)

    def test_title_and_image_are_not_converted(self) -> None:
        for param in ("title", "image"):
            text = f"{{{{Navbox|{param}=A {{{{.w}}}} B}}}}"
            self.assertEqual(fix(text), text)

    def test_items_can_contain_links_and_templates(self) -> None:
        result = fix("{{Navbox|list1=[[A|a]] {{tl|X}} {{.w}} B}}")
        self.assertIn("* [[A|a]] {{tl|X}}", result)
        self.assertIn("* B", result)

    def test_existing_nowrap_pair_is_left_alone(self) -> None:
        text = "{{Navbox|list1={{nowrap begin}}A {{.w}} B{{nowrap end}}}}"
        self.assertEqual(fix(text), text)

    def test_newline_inside_an_item_is_left_alone(self) -> None:
        text = "{{Navbox|list1=A\nB {{.w}} C}}"
        self.assertEqual(fix(text), text)

    def test_top_level_pipe_is_left_alone(self) -> None:
        text = "{{Navbox|list1=A | B {{.w}} C}}"
        self.assertEqual(fix(text), text)

    def test_non_navbox_template_is_left_alone(self) -> None:
        text = "{{Other|list1=A {{.w}} B}}"
        self.assertEqual(fix(text), text)

    def test_top_level_w_is_left_alone_and_reported(self) -> None:
        text = "A {{.w}} B"
        self.assertEqual(fix(text), text)
        self.assertTrue(reporter.issues["nowrap"])

    def test_idempotence(self) -> None:
        once = fix("{{Navbox|list1=A {{.w}} B {{.w}} C}}")
        reporter.issues.clear()
        self.assertEqual(fix(once), once)


if __name__ == "__main__":
    unittest.main()
