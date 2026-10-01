"""Behaviour of the shipped extensions, locked down as input/output pairs."""

from __future__ import annotations

import unittest
from unittest import mock

from src.Yugong.core.wikitext import Wikitext
from src.Yugong.extensions import category_handler as ch
from src.Yugong.extensions import example as ex
from src.Yugong.extensions import fix_cite_template as fc
from src.Yugong.extensions import rm_undefined_refs as rr
from src.Yugong.extensions import rm_void_template as rv

from tests.support import FakeBotDB, run_job


class ExampleExtensionTest(unittest.TestCase):
    def test_example_is_a_no_op(self) -> None:
        text = "{{Infobox|old_param=1}} text"
        self.assertEqual(run_job(ex.template_example_job, text), text)

    def test_intro_describes_itself(self) -> None:
        self.assertIn("Example", ex.template_example_intro())


class FixCiteTemplateTest(unittest.TestCase):
    def test_joins_later_anonymous_params_with_the_pipe_magic_word(self) -> None:
        self.assertEqual(
            run_job(fc.fix_cite_template_job, "{{Cite web|http://example.com|Foo|title=Bar}}"),
            "{{Cite web|http://example.com{{!}}Foo|title=Bar}}",
        )

    def test_named_only_templates_are_untouched(self) -> None:
        text = "{{Cite web|url=http://x|title=Foo}}"
        self.assertEqual(run_job(fc.fix_cite_template_job, text), text)

    def test_single_anonymous_param_is_untouched(self) -> None:
        text = "{{Citation|http://x}}"
        self.assertEqual(run_job(fc.fix_cite_template_job, text), text)

    def test_non_cite_templates_are_untouched(self) -> None:
        text = "{{Infobox|a|b}}"
        self.assertEqual(run_job(fc.fix_cite_template_job, text), text)

    def test_template_without_anonymous_params_is_untouched(self) -> None:
        self.assertEqual(run_job(fc.fix_cite_template_job, "{{Cite book}}"), "{{Cite book}}")

    def test_intro_mentions_cite(self) -> None:
        self.assertIn("Cite", fc.fix_cite_template_intro())


class RmUndefinedRefsTest(unittest.TestCase):
    def test_removes_an_orphaned_self_closing_ref(self) -> None:
        self.assertEqual(
            run_job(rr.rm_undefined_refs_job, 'Some text.<ref name="orphan" />'),
            "Some text.",
        )

    def test_keeps_a_ref_that_is_defined_later_on_the_page(self) -> None:
        text = 'A<ref name="x" />B<ref name="x">C</ref>'
        self.assertEqual(run_job(rr.rm_undefined_refs_job, text), text)

    def test_keeps_a_ref_that_has_its_own_content(self) -> None:
        text = 'A<ref name="ok">Real</ref>B<ref name="ok" />'
        self.assertEqual(run_job(rr.rm_undefined_refs_job, text), text)

    def test_ignores_unnamed_refs(self) -> None:
        text = "A<ref>plain</ref>"
        self.assertEqual(run_job(rr.rm_undefined_refs_job, text), text)

    def test_removes_every_ref_when_none_is_defined(self) -> None:
        self.assertEqual(run_job(rr.rm_undefined_refs_job, 'A<ref name="q" />B<ref name="q" />'), "AB")

    def test_intro_mentions_ref(self) -> None:
        self.assertIn("ref", rr.rm_undefined_refs_intro())


class RmVoidTemplateTest(unittest.TestCase):
    def test_normalises_void_targets(self) -> None:
        for title in ("Template:Void", "template:void", "  TEMPLATE: VOID ", "模板:Void"):
            self.assertTrue(rv._is_void_target(title), title)

    def test_other_targets_are_not_void(self) -> None:
        for title in ("Template:Void2", "Template:Foo", ""):
            self.assertFalse(rv._is_void_target(title), title)

    def test_resolved_target_is_cached_and_reused(self) -> None:
        fake = FakeBotDB()
        with mock.patch.object(rv, "bot_db", fake), \
             mock.patch.object(rv, "_resolve_redirect_target", return_value="Template:Void") as resolver:
            self.assertTrue(rv._is_void_template("Navbox"))
            self.assertTrue(rv._is_void_template("Navbox"))
            resolver.assert_called_once()

        self.assertEqual(fake.rows["template"][0]["type"], "void")
        self.assertEqual(fake.rows["template"][0]["target"], "Template:Void")

    def test_non_void_target_is_cached_as_normal(self) -> None:
        fake = FakeBotDB()
        with mock.patch.object(rv, "bot_db", fake), \
             mock.patch.object(rv, "_resolve_redirect_target", return_value="Template:Other"):
            self.assertFalse(rv._is_void_template("Navbox"))

        self.assertEqual(fake.rows["template"][0]["type"], "normal")
        self.assertEqual(fake.rows["template"][0]["target"], "Template:Other")

    def test_missing_template_is_not_void(self) -> None:
        fake = FakeBotDB()
        with mock.patch.object(rv, "bot_db", fake), \
             mock.patch.object(rv, "_resolve_redirect_target", return_value=None):
            self.assertFalse(rv._is_void_template("Navbox"))

        self.assertEqual(fake.rows["template"][0]["type"], "normal")

    def test_job_removes_void_templates_only(self) -> None:
        with mock.patch.object(rv, "_is_void_template", side_effect=lambda name: name == "Void"):
            result = run_job(rv.rm_void_template_job, "a{{Void}}b{{Keep}}c")
        self.assertEqual(result, "ab{{Keep}}c")

    def test_job_is_marked_as_needing_a_wiki(self) -> None:
        self.assertTrue(getattr(rv.rm_void_template_job, "needs_wiki", False))


class CategoryHandlerTest(unittest.TestCase):
    def test_strip_category_prefix(self) -> None:
        self.assertEqual(ch._strip_category_prefix("Category:Foo"), "Foo")
        self.assertEqual(ch._strip_category_prefix("分类:南京"), "南京")
        self.assertEqual(ch._strip_category_prefix("Foo"), "Foo")

    def test_category_prefix_preserves_spelling(self) -> None:
        self.assertEqual(ch._category_prefix("分类:南京"), "分类:")
        self.assertEqual(ch._category_prefix("category:Foo"), "category:")
        self.assertEqual(ch._category_prefix("Foo"), "")

    def test_parse_redirect_template(self) -> None:
        target, index = ch._parse_redirect_template("{{分类重定向|目标分类|索引}}")
        self.assertEqual((target, index), ("目标分类", "索引"))

    def test_parse_redirect_template_without_index(self) -> None:
        self.assertEqual(ch._parse_redirect_template("{{分类重定向|目标}}"), ("目标", ""))

    def test_parse_redirect_template_absent(self) -> None:
        self.assertEqual(ch._parse_redirect_template("plain text"), (None, ""))

    def test_rewrite_keeps_namespace_prefix_and_sort_key(self) -> None:
        wikitext = Wikitext({"title": "T"})
        wikitext.parse("[[Category:Old|sort key]]")
        link = wikitext.wikilinks()[0]
        ch._rewrite_category_link(link, "New")
        self.assertEqual(str(wikitext), "[[Category:New|sort key]]")

    def test_job_uses_the_cache_without_touching_the_wiki(self) -> None:
        fake = FakeBotDB()
        fake.insert("category", {"title": "Old", "target": "New", "sort_index": ""})
        with mock.patch.object(ch, "bot_db", fake), \
             mock.patch.object(ch, "_to_zh_hans", side_effect=AssertionError("should not convert")):
            result = run_job(ch.category_handler_job, "text [[Category:Old]] more")
        self.assertEqual(result, "text [[Category:New]] more")

    def test_job_leaves_links_alone_when_nothing_is_cached_as_redirected(self) -> None:
        fake = FakeBotDB()
        with mock.patch.object(ch, "bot_db", fake), \
             mock.patch.object(ch, "_to_zh_hans", return_value="Old"):
            text = "text [[Category:Old]] [[Foo]] more"
            self.assertEqual(run_job(ch.category_handler_job, text), text)

    def test_opencc_missing_is_not_fatal(self) -> None:
        with mock.patch.dict("sys.modules", {"opencc": None}):
            ch._converter = None
            self.assertEqual(ch._to_zh_hans("測試"), "測試")
        ch._converter = None

    def test_job_is_marked_as_needing_a_wiki(self) -> None:
        self.assertTrue(getattr(ch.category_handler_job, "needs_wiki", False))

    def test_intro_describes_itself(self) -> None:
        self.assertIn("Category", ch.category_handler_intro())


if __name__ == "__main__":
    unittest.main()
