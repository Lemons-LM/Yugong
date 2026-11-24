"""Cangjie: NoteTA-driven visible-text conversion with protected regions."""

from __future__ import annotations

import unittest
from unittest import mock

from src.Yugong.extensions import cangjie
from tests.support import run_job


def rules_from(config: object, **_kwargs: object) -> list[str]:
    return list(getattr(config, "local_rules"))


def run_cangjie(text: str, *, enabled: bool = True, opencc: object = None) -> str:
    fake_opencc = opencc or (lambda value: value)
    with mock.patch.object(cangjie.settings, "enable_cangjie", enabled), \
         mock.patch.object(cangjie, "resolve_note_ta_rules", side_effect=rules_from), \
         mock.patch.object(cangjie, "_opencc_convert", side_effect=fake_opencc):
        return run_job(cangjie.cangjie_job, text)


class CangjieTest(unittest.TestCase):
    def test_disabled_is_a_no_op(self) -> None:
        text = "{{NoteTA|1=zh-cn:中国大陆;zh-tw:中國大陸;}}\n中國大陸"
        self.assertEqual(run_cangjie(text, enabled=False), text)

    def test_pages_without_noteta_use_opencc_only(self) -> None:
        text = "實驗體與公尺"
        def fake_opencc(value: str) -> str:
            return value.replace("實", "实").replace("驗", "验").replace("體", "体")

        self.assertEqual(
            run_cangjie(text, opencc=fake_opencc),
            "实验体與公尺",
        )
        # Without OpenCC there is nothing to apply on a NoteTA-less page.
        self.assertEqual(run_cangjie(text), text)

    def test_visible_text_is_converted(self) -> None:
        text = "{{NoteTA|1=zh-cn:中国大陆;zh-tw:中國大陸;}}\n中國大陸"
        self.assertIn("中国大陆", run_cangjie(text))
        self.assertNotIn("\n中國大陸", run_cangjie(text))

    def test_templates_and_arguments_are_untouched(self) -> None:
        text = "{{NoteTA|1=zh-cn:中国大陆;zh-tw:中國大陸;}}\n{{Other|中國大陸}} {{{中國大陸}}}"
        result = run_cangjie(text)
        self.assertIn("{{Other|中國大陸}}", result)
        self.assertIn("{{{中國大陸}}}", result)

    def test_protected_tags_are_untouched(self) -> None:
        text = (
            "{{NoteTA|1=zh-cn:中国大陆;zh-tw:中國大陸;}}\n"
            "中國大陸<nowiki>中國大陸</nowiki><code>中國大陸</code>"
            "<pre>中國大陸</pre><math>中國大陸</math>"
        )
        result = run_cangjie(text)
        self.assertTrue(result.startswith("{{NoteTA|1=zh-cn:中国大陆;zh-tw:中國大陸;}}\n中国大陆"))
        self.assertIn("<nowiki>中國大陸</nowiki>", result)
        self.assertIn("<code>中國大陸</code>", result)
        self.assertIn("<pre>中國大陸</pre>", result)
        self.assertIn("<math>中國大陸</math>", result)

    def test_conversion_markup_urls_and_categories_are_untouched(self) -> None:
        text = (
            "{{NoteTA|1=zh-cn:中国大陆;zh-tw:中國大陸;}}\n"
            "-{zh-cn:中國大陸;zh-tw:中國大陸;}- "
            "http://example.com/中國大陸 "
            "[[Category:中國大陸|中國大陸]] [[File:X|中國大陸]]"
        )
        self.assertEqual(run_cangjie(text), text)

    def test_link_target_is_kept_but_display_text_is_converted(self) -> None:
        text = (
            "{{NoteTA|1=zh-cn:中国大陆;zh-tw:中國大陸;}}\n"
            "[[中國大陸]] [[中國大陸|中國大陸]]"
        )
        result = run_cangjie(text)
        self.assertIn("[[中國大陸]]", result)
        self.assertIn("[[中國大陸|中国大陆]]", result)

    def test_external_link_display_text_is_converted(self) -> None:
        text = "{{NoteTA|1=zh-cn:中国大陆;zh-tw:中國大陸;}}\n[http://example.com 中國大陸]"
        result = run_cangjie(text)
        self.assertIn("[http://example.com 中国大陆]", result)

    def test_opencc_resolves_the_traditional_zhe_particle(self) -> None:
        try:
            import opencc  # noqa: F401
        except ImportError:
            self.skipTest("opencc is not installed")

        self.assertEqual(cangjie._opencc_convert("隨著圖靈機"), "随着图灵机")
        # The phrase table must not turn 著名/著作 into 着名/着作.
        self.assertEqual(cangjie._opencc_convert("著名著作"), "著名著作")

    def test_opencc_runs_after_noteta(self) -> None:
        text = "{{NoteTA|1=zh-cn:米;zh-tw:公尺;}}\n公尺身體"
        result = run_cangjie(text, opencc=lambda value: value.replace("體", "体"))
        self.assertIn("米身", result)
        self.assertNotIn("體", result)


if __name__ == "__main__":
    unittest.main()
