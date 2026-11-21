"""Behaviour of the shipped extensions, locked down as input/output pairs."""

from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from src.Yugong.core.bot_db import BotDB
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
    def test_rejoins_url_fragment_into_the_url_parameter(self) -> None:
        self.assertEqual(
            run_job(fc.fix_cite_template_job, "{{Cite web|url=http://example.com|Foo|title=Bar}}"),
            "{{Cite web|url=http://example.com{{!}}Foo|title=Bar}}",
        )

    def test_rejoins_every_contiguous_url_fragment(self) -> None:
        self.assertEqual(
            run_job(fc.fix_cite_template_job, "{{Cite web|url=http://x|a|b|title=Bar}}"),
            "{{Cite web|url=http://x{{!}}a{{!}}b|title=Bar}}",
        )

    def test_rejoins_fragment_into_a_non_url_parameter(self) -> None:
        self.assertEqual(
            run_job(fc.fix_cite_template_job, "{{Cite web|url=http://x|title=Foo|Bar}}"),
            "{{Cite web|url=http://x|title=Foo{{!}}Bar}}",
        )

    def test_rejoins_fragment_into_each_preceding_parameter(self) -> None:
        self.assertEqual(
            run_job(fc.fix_cite_template_job, "{{Cite web|url=http://x|a|title=Bar|baz}}"),
            "{{Cite web|url=http://x{{!}}a|title=Bar{{!}}baz}}",
        )

    def test_named_only_templates_are_untouched(self) -> None:
        text = "{{Cite web|url=http://x|title=Foo}}"
        self.assertEqual(run_job(fc.fix_cite_template_job, text), text)

    def test_anonymous_url_without_url_key_is_untouched(self) -> None:
        text = "{{Cite web|http://example.com|Foo|title=Bar}}"
        self.assertEqual(run_job(fc.fix_cite_template_job, text), text)

    def test_single_anonymous_param_is_untouched(self) -> None:
        text = "{{Citation|http://x}}"
        self.assertEqual(run_job(fc.fix_cite_template_job, text), text)

    def test_non_cite_templates_are_untouched(self) -> None:
        text = "{{Infobox|a|b}}"
        self.assertEqual(run_job(fc.fix_cite_template_job, text), text)

    def test_template_without_anonymous_params_is_untouched(self) -> None:
        self.assertEqual(run_job(fc.fix_cite_template_job, "{{Cite book}}"), "{{Cite book}}")

    def test_nested_cite_templates_do_not_crash_on_detached_nodes(self) -> None:
        text = "{{Cite web|url=http://x|Foo|title={{Cite book|url=http://y|Bar}}}}"
        result = run_job(fc.fix_cite_template_job, text)
        self.assertIn("{{!}}", result)
        self.assertIn("{{Cite book|url=http://y|Bar}}", result)

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
    def setUp(self) -> None:
        rv._alias_keys = None
        rv._aliases_loaded = False

    def tearDown(self) -> None:
        rv._alias_keys = None
        rv._aliases_loaded = False

    def test_normalises_void_targets(self) -> None:
        for title in ("Template:Void", "template:void", "  TEMPLATE: VOID ", "模板:Void"):
            self.assertTrue(rv._is_void_target(title), title)

    def test_other_targets_are_not_void(self) -> None:
        for title in ("Template:Void2", "Template:Foo", ""):
            self.assertFalse(rv._is_void_target(title), title)

    def test_resolved_target_is_cached_and_reused(self) -> None:
        fake = FakeBotDB()
        with mock.patch.object(rv, "bot_db", fake), \
             mock.patch.object(rv, "_load_void_aliases", return_value=None), \
             mock.patch.object(rv, "_resolve_redirect_target", return_value="Template:Void") as resolver:
            self.assertTrue(rv._is_void_template("Navbox"))
            self.assertTrue(rv._is_void_template("Navbox"))
            resolver.assert_called_once()

        self.assertEqual(fake.rows["template"][0]["type"], "void")
        self.assertEqual(fake.rows["template"][0]["target"], "Template:Void")

    def test_non_void_target_is_cached_as_normal(self) -> None:
        fake = FakeBotDB()
        with mock.patch.object(rv, "bot_db", fake), \
             mock.patch.object(rv, "_load_void_aliases", return_value=None), \
             mock.patch.object(rv, "_resolve_redirect_target", return_value="Template:Other"):
            self.assertFalse(rv._is_void_template("Navbox"))

        self.assertEqual(fake.rows["template"][0]["type"], "normal")
        self.assertEqual(fake.rows["template"][0]["target"], "Template:Other")

    def test_a_legacy_row_without_type_is_refreshed(self) -> None:
        """Rows from before the ``type`` column existed must not look normal."""
        fake = FakeBotDB()
        fake.insert("template", {"title": "Navbox", "target": "Template:Void", "type": None})
        with mock.patch.object(rv, "bot_db", fake), \
             mock.patch.object(rv, "_load_void_aliases", return_value=None), \
             mock.patch.object(rv, "_resolve_redirect_target", return_value="Template:Void"):
            self.assertTrue(rv._is_void_template("Navbox"))

        self.assertEqual(fake.rows["template"][0]["type"], "void")

    def test_missing_template_is_not_void(self) -> None:
        fake = FakeBotDB()
        with mock.patch.object(rv, "bot_db", fake), \
             mock.patch.object(rv, "_load_void_aliases", return_value=None), \
             mock.patch.object(rv, "_resolve_redirect_target", return_value=None):
            self.assertFalse(rv._is_void_template("Navbox"))

        self.assertEqual(fake.rows["template"][0]["type"], "normal")

    def test_preloaded_alias_is_void_without_resolving(self) -> None:
        rv._alias_keys = {"commonscat"}
        rv._aliases_loaded = True
        with mock.patch.object(rv, "bot_db", FakeBotDB()), \
             mock.patch.object(rv, "_resolve_redirect_target") as resolver:
            self.assertTrue(rv._is_void_template("Commonscat"))
            resolver.assert_not_called()

    def test_redirect_chain_to_a_void_alias(self) -> None:
        rv._alias_keys = {"commonscat"}
        rv._aliases_loaded = True
        target = mock.Mock()
        target.title.return_value = "Template:Commonscat"
        first = mock.Mock()
        first.isRedirectPage.return_value = True
        first.getRedirectTarget.return_value = target

        with mock.patch.object(rv, "bot_db", FakeBotDB()), \
             mock.patch.object(rv.pywikibot, "Page", return_value=first):
            self.assertTrue(rv._is_void_template("A"))

    def test_alias_loader_populates_and_reuses_the_cache(self) -> None:
        with TemporaryDirectory() as tmp:
            db = BotDB(Path(tmp) / "db.sqlite3")
            payload = {"query": {"backlinks": [{"title": "Template:Commonscat"}]}}
            with mock.patch.object(rv, "bot_db", db), \
                 mock.patch.object(rv.wiki, "api_query", return_value=payload) as api:
                rv._load_void_aliases()
                self.assertIn("commonscat", rv._alias_keys or set())
                self.assertTrue(rv._is_void_template("Commonscat"))
                rv._load_void_aliases()
                self.assertEqual(api.call_count, 1)

    def test_job_removes_void_templates_only(self) -> None:
        with mock.patch.object(rv, "_is_void_template", side_effect=lambda name: name == "Void"):
            result = run_job(rv.rm_void_template_job, "a{{Void}}b{{Keep}}c")
        self.assertEqual(result, "ab{{Keep}}c")

    def test_nested_void_templates_do_not_crash_on_detached_nodes(self) -> None:
        with mock.patch.object(rv, "_is_void_template", return_value=True):
            self.assertEqual(run_job(rv.rm_void_template_job, "a{{Void|{{Void}}}}b"), "ab")

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

    def test_resolve_category_uses_the_cache_without_touching_the_wiki(self) -> None:
        fake = FakeBotDB()
        fake.insert("category", {"title": "Old", "target": "New", "sort_index": ""})
        with mock.patch.object(ch, "bot_db", fake), \
             mock.patch.object(ch.pywikibot, "Page") as page_cls:
            self.assertEqual(ch._resolve_category("Old"), "New")
            page_cls.assert_not_called()

    def test_resolve_category_reads_a_redirect_and_caches_it(self) -> None:
        page = mock.Mock()
        page.exists.return_value = True
        page.text = "{{分类重定向|New|index}}"
        fake = FakeBotDB()
        with mock.patch.object(ch, "bot_db", fake), \
             mock.patch.object(type(ch.wiki), "site", mock.PropertyMock(return_value=mock.Mock())), \
             mock.patch.object(ch.pywikibot, "Page", return_value=page):
            self.assertEqual(ch._resolve_category("Old"), "New")
        self.assertEqual(fake.rows["category"][0]["target"], "New")

    def test_resolve_category_returns_none_for_a_missing_page(self) -> None:
        page = mock.Mock()
        page.exists.return_value = False
        with mock.patch.object(ch, "bot_db", FakeBotDB()), \
             mock.patch.object(type(ch.wiki), "site", mock.PropertyMock(return_value=mock.Mock())), \
             mock.patch.object(ch.pywikibot, "Page", return_value=page):
            self.assertIsNone(ch._resolve_category("Old"))

    def test_job_rewrites_to_the_noteta_converted_category(self) -> None:
        text = "{{NoteTA|1=zh-cn:米; zh-tw:公尺;}}\n[[Category:公尺]]"

        def resolve(name: str) -> str | None:
            return name if name == "米" else None

        def rules_from(config: object, **_kwargs: object) -> list[str]:
            return list(getattr(config, "local_rules"))

        with mock.patch.object(ch, "_resolve_category", side_effect=resolve), \
             mock.patch.object(ch, "_to_zh_hans", side_effect=lambda value: value), \
             mock.patch.object(ch, "resolve_note_ta_rules", side_effect=rules_from):
            result = run_job(ch.category_handler_job, text)
        self.assertIn("[[Category:米]]", result)

    def test_job_keeps_the_original_when_the_converted_category_is_missing(self) -> None:
        text = "{{NoteTA|1=zh-cn:米; zh-tw:公尺;}}\n[[Category:公尺]]"

        def resolve(name: str) -> str | None:
            return name if name == "公尺" else None

        def rules_from(config: object, **_kwargs: object) -> list[str]:
            return list(getattr(config, "local_rules"))

        with mock.patch.object(ch, "_resolve_category", side_effect=resolve), \
             mock.patch.object(ch, "_to_zh_hans", side_effect=lambda value: value), \
             mock.patch.object(ch, "resolve_note_ta_rules", side_effect=rules_from):
            result = run_job(ch.category_handler_job, text)
        self.assertIn("[[Category:公尺]]", result)

    def test_job_leaves_non_category_links_alone(self) -> None:
        with mock.patch.object(ch, "resolve_note_ta_rules", return_value=[]):
            text = "text [[Foo]] more"
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
