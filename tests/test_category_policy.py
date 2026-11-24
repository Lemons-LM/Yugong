"""Automatable parts of QW:CAT (category style guideline)."""

from __future__ import annotations

import unittest

from src.Yugong.core.wikitext import Wikitext
from src.Yugong.extensions.category_policy import category_policy_job
from tests.support import run_job


def fix(text: str, *, title: str = "Test page", namespace: int = 0) -> str:
    wikitext = Wikitext({
        "title": title,
        "pageid": "1",
        "revid": "1",
        "namespace": str(namespace),
    })
    wikitext.parse(text)
    category_policy_job(wikitext)
    return str(wikitext)


class SortKeyTest(unittest.TestCase):
    def test_empty_and_page_title_keys_are_removed(self) -> None:
        self.assertEqual(fix("[[Category:X|  ]]"), "[[Category:X]]")
        self.assertEqual(
            fix("[[Category:X|Test page]]", title="Test page"), "[[Category:X]]"
        )
        self.assertEqual(
            fix("[[Category:X|Page]]", title="Template:Page", namespace=10),
            "[[Category:X]]",
        )

    def test_meaningful_keys_are_kept(self) -> None:
        for key in ("*", "#", "上海", "epang宫"):
            self.assertEqual(
                fix(f"[[Category:X|{key}]]"), f"[[Category:X|{key}]]"
            )

    def test_pinyin_and_english_keys_are_removed(self) -> None:
        for key in ("key", "nasty_test", "Japan", "Riben", "Abcd"):
            self.assertEqual(fix(f"[[Category:X|{key}]]"), "[[Category:X]]")

    def test_numeric_keys_are_kept(self) -> None:
        self.assertEqual(fix("[[Category:X|2000]]"), "[[Category:X|2000]]")

    def test_key_equal_to_the_category_name_is_removed(self) -> None:
        self.assertEqual(
            fix("[[Category:第四分类|第四分类]]"), "[[Category:第四分类]]"
        )

    def test_deprecated_punctuation_keys_are_removed(self) -> None:
        for key in ("·", "：", "；", "？", "，", "。", "！", "￥", "@", ":", "$", "@abc"):
            self.assertEqual(fix(f"[[Category:X|{key}]]"), "[[Category:X]]")

    def test_full_width_punctuation_only_is_removed(self) -> None:
        self.assertEqual(fix("[[Category:X|·：]]"), "[[Category:X]]")


class LinkNormalisationTest(unittest.TestCase):
    def test_prefix_is_normalised(self) -> None:
        for prefix in ("分类", "分類", "catégorie"):
            self.assertEqual(
                fix(f"[[{prefix}:X]]"), "[[Category:X]]"
            )

    def test_a_leading_colon_link_is_not_a_category_membership(self) -> None:
        self.assertEqual(fix("[[:Category:X]]"), "[[:Category:X]]")

    def test_duplicate_category_links_are_removed(self) -> None:
        self.assertEqual(
            fix("[[Category:X]][[Category:X|key]]"),
            "[[Category:X]]",
        )


class CatnavTest(unittest.TestCase):
    def test_category_page_without_catnav_gets_it_at_the_top(self) -> None:
        result = fix("介绍\n[[Category:Bar]]", title="Category:Foo", namespace=14)
        self.assertTrue(result.startswith("{{catnav|auto=1}}"))
        self.assertIn("[[Category:Bar]]", result)

    def test_existing_catnav_is_not_duplicated(self) -> None:
        text = "{{catnav|auto=1}}\n介绍"
        self.assertEqual(
            fix(text, title="Category:Foo", namespace=14), text
        )

    def test_category_redirects_get_no_catnav(self) -> None:
        text = "{{分类重定向|Bar}}\n"
        self.assertEqual(
            fix(text, title="Category:Foo", namespace=14), text
        )
        self.assertEqual(
            fix("#REDIRECT [[Category:Bar]]", title="Category:Foo", namespace=14),
            "#REDIRECT [[Category:Bar]]",
        )

    def test_article_pages_get_no_catnav(self) -> None:
        self.assertEqual(fix("text", title="Test page", namespace=0), "text")


if __name__ == "__main__":
    unittest.main()
