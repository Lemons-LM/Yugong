"""Shipped rules for reviewed deprecated template families."""

from __future__ import annotations

import contextlib
import io
import unittest

from src.Yugong.core.settings import settings
from src.Yugong.core.template_formatter import formatter
from tests.support import make_wikitext


def apply(text: str) -> str:
    wikitext = make_wikitext(text)
    formatter.format_template(wikitext)
    return str(wikitext)


class _RuleTestBase(unittest.TestCase):
    def setUp(self) -> None:
        self._saved = dict(formatter.RULES)
        self._saved_loaded = formatter.loaded
        formatter.RULES.clear()
        formatter.loaded = False
        with contextlib.redirect_stdout(io.StringIO()):
            formatter.get_ruleset()

    def tearDown(self) -> None:
        formatter.RULES.clear()
        formatter.RULES.update(self._saved)
        formatter.loaded = self._saved_loaded


class InternalLinkHelperRuleTest(_RuleTestBase):
    def test_language_subpage_becomes_a_plain_link(self) -> None:
        self.assertEqual(
            apply("{{Internal link helper/en|本地条目|Foreign title}}"),
            "[[本地条目]]",
        )

    def test_link_alias_becomes_a_plain_link(self) -> None:
        self.assertEqual(
            apply("{{Link-de|本地条目|Fremder Titel}}"), "[[本地条目]]"
        )

    def test_ilh_shortcut_becomes_a_plain_link(self) -> None:
        self.assertEqual(apply("{{Ilh|1=本地条目|lang=en}}"), "[[本地条目]]")

    def test_unrelated_templates_are_untouched(self) -> None:
        self.assertEqual(apply("{{Other|本地条目}}"), "{{Other|本地条目}}")

    def test_missing_target_is_not_replaced_with_an_empty_link(self) -> None:
        self.assertEqual(apply("{{Ilh}}"), "{{Ilh}}")
        self.assertEqual(apply("{{Internal link helper/en}}"), "{{Internal link helper/en}}")


class TranslinkRuleTest(_RuleTestBase):
    def test_missing_chinese_title_falls_back_to_the_foreign_title(self) -> None:
        result = apply("{{Translink|en|OpenVMS}}")
        self.assertTrue(result.startswith("[[{{#if:"))
        self.assertIn("OpenVMS", result)
        self.assertNotIn("{{{3", result)
        self.assertNotIn("{{{4", result)

    def test_explicit_display_name_is_preserved(self) -> None:
        result = apply("{{Tsl|en|pr (Unix)||pr}}")
        self.assertIn("pr (Unix)", result)
        self.assertIn("{{#if:pr|pr|", result)

    def test_chinese_title_wins_over_the_foreign_title(self) -> None:
        result = apply("{{Translink|en|Foreign|中文条目|显示名}}")
        self.assertIn("中文条目", result)
        self.assertIn("显示名", result)

    def test_missing_titles_are_not_replaced_with_an_empty_link(self) -> None:
        self.assertEqual(apply("{{Translink}}"), "{{Translink}}")
        self.assertEqual(apply("{{Translink|en}}"), "{{Translink|en}}")

    def test_a_nested_template_is_replaced_in_the_same_run(self) -> None:
        result = apply("{{Font color|blue|x {{Translink|en|Outer|内层}}}}")
        self.assertNotIn("Translink", result)
        self.assertIn("内层", result)


class InterlanguageLinkMultiRuleTest(_RuleTestBase):
    def test_old_name_is_renamed_to_the_current_template(self) -> None:
        self.assertEqual(
            apply("{{Interlanguage link multi|詐欺罪|ja|詐欺罪}}"),
            "{{多語言連結|詐欺罪|ja|詐欺罪}}",
        )

    def test_current_template_is_not_changed(self) -> None:
        self.assertEqual(
            apply("{{多語言連結|本地条目}}"), "{{多語言連結|本地条目}}"
        )


class OtherReviewedRulesTest(_RuleTestBase):
    def test_short_description_is_deleted(self) -> None:
        self.assertEqual(apply("{{Short description|测试描述}}"), "")

    def test_font_color_becomes_color(self) -> None:
        self.assertEqual(apply("{{Font color|red|文字}}"), "{{color|red|文字}}")
        self.assertEqual(
            apply("{{Font color|fg=red|text=文字}}"), "{{color|red|文字}}"
        )

    def test_dot_w_is_left_to_the_nowrap_extension(self) -> None:
        """A flat {{.w}} -> {{·}} rule would be wrong; navbox lists are handled
        contextually by nowrap_fixes."""
        self.assertEqual(apply("{{.w}}"), "{{.w}}")

    def test_double_image_becomes_multiple_image(self) -> None:
        result = apply("{{Double image|right|A.jpg|200|B.jpg|250|Caption}}")
        self.assertIn("{{multiple image", result)
        self.assertIn("image1 = A.jpg", result)
        self.assertIn("image2 = B.jpg", result)

    def test_direct_link_templates(self) -> None:
        self.assertEqual(apply("{{中国大陆}}"), "[[中国大陆]]")
        self.assertEqual(apply("{{中国内地}}"), "[[中国内地]]")
        self.assertEqual(apply("{{中國電影產地}}"), "[[中国]]")
        self.assertEqual(apply("{{ROC-1940}}"), "[[汪伪政权]]")
        self.assertEqual(apply("{{ROC-1938}}"), "伪“[[中華民國維新政府]]”")
        self.assertEqual(apply("{{CHN-1928}}"), "[[中华民国|中国]]")

    def test_city_and_country_wrappers_only_output_supplied_parameters(self) -> None:
        city = apply("{{城市|城市名称=测试|人口=100}}")
        self.assertIn("{{infobox settlement", city)
        self.assertIn("name=测试", city)
        self.assertIn("population_total=100", city)
        # Parameters the editor did not supply must not be expanded.
        self.assertNotIn("native_name", city)
        self.assertNotIn("settlement_type", city)
        self.assertNotIn("leader_title", city)

        country = apply("{{國家基礎資訊|国家名称=测试|國歌名稱=歌}}")
        self.assertIn("{{Infobox country", country)
        self.assertIn("conventional_long_name  = 测试", country)
        self.assertIn("national_anthem         = 歌", country)
        self.assertNotIn("capital", country)
        self.assertNotIn("membership_type", country)
        self.assertNotIn("established_event2", country)
        # Every parameter placeholder must have a default; a bare {{{name}}}
        # would leak into the article as literal text.
        self.assertNotIn("{{{", country)

    def test_unsupplied_parameters_with_defaults_are_not_expanded(self) -> None:
        city = apply("{{城市}}")
        self.assertNotIn("native_name", city)
        self.assertNotIn("{{{", city)


if __name__ == "__main__":
    unittest.main()
