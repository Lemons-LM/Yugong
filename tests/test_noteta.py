"""NoteTA / CGroup parsing and the per-wiki group cache."""

from __future__ import annotations

import unittest
from typing import Any

from src.Yugong.utilities import cgroup_cache
from src.Yugong.utilities.note_ta import (
    NoteTAConfig,
    apply_replacements,
    build_replacements,
    parse_cgroup_lua,
    parse_cgroup_wikitext,
    parse_note_ta,
    rule_mappings,
)


class ParseNoteTATest(unittest.TestCase):
    def test_groups_inline_and_title_rules_are_collected(self) -> None:
        config = parse_note_ta(
            "{{NoteTA|G1=Unit|G2=LS|1=zh-cn:米; zh-tw:公尺;|T=zh-cn:米; zh-tw:公尺;}}"
        )
        self.assertEqual(config.groups, ["Unit", "LS"])
        self.assertEqual(config.local_rules, ["zh-cn:米; zh-tw:公尺;"])
        self.assertEqual(config.title_rules, "zh-cn:米; zh-tw:公尺;")

    def test_lowercase_tag_and_hidden_rules(self) -> None:
        config = parse_note_ta("{{noteTA|G1=LS}}\n-{H|zh-cn:千克; zh-tw:公斤;}-")
        self.assertEqual(config.groups, ["LS"])
        self.assertEqual(config.local_rules, ["zh-cn:千克; zh-tw:公斤;"])

    def test_no_noteta_is_empty(self) -> None:
        self.assertTrue(parse_note_ta("plain text [[Category:X]]").is_empty())


class ParseCGroupTemplateTest(unittest.TestCase):
    def test_citem_and_citemhidden_rules(self) -> None:
        text = (
            "{{CGroupH|name=Unit}}"
            "{{CItem|zh-cn:米;zh-tw:公尺;|original=[[米|m]]}}"
            "{{CItemHidden|1=公尺=>zh-cn:米;}}"
            "{{CGroupF}}"
        )
        self.assertEqual(
            parse_cgroup_wikitext(text),
            (["zh-cn:米;zh-tw:公尺;", "公尺=>zh-cn:米;"], []),
        )

    def test_unrelated_templates_are_ignored(self) -> None:
        self.assertEqual(parse_cgroup_wikitext("{{Other|zh-cn:米;zh-tw:公尺;}}"), ([], []))


class ParseCGroupLuaTest(unittest.TestCase):
    LUA = """
    -- comment with a fake rule: zh-cn:comment; zh-tw:comment;
    return {
        name = 'Unit',
        description = '單位',
        content = {
            { type = 'item', rule = 'zh-cn:米; zh-tw:公尺;' },
            { type = 'item', original = 'm', rule = '公尺=>zh-cn:米;' },
            'zh-cn:千克; zh-tw:公斤;',
            { 'original', 'zh-cn:克; zh-tw:公克;' },
            Item('orig', 'zh-cn:纳米; zh-tw:奈米;'),
            { type = 'variants', ['zh-cn'] = '埃', ['zh-tw'] = '埃米' },
            { type = 'import', name = 'Length' },
            { import = 'Mass' },
        },
    }
    """

    def test_items_strings_calls_variants_and_imports(self) -> None:
        rules, imports = parse_cgroup_lua(self.LUA)
        for expected in (
            "zh-cn:米; zh-tw:公尺;",
            "公尺=>zh-cn:米;",
            "zh-cn:千克; zh-tw:公斤;",
            "zh-cn:克; zh-tw:公克;",
            "zh-cn:纳米; zh-tw:奈米;",
            "zh-cn:埃;zh-tw:埃米",
        ):
            self.assertIn(expected, rules)
        self.assertNotIn("zh-cn:comment; zh-tw:comment;", rules)
        self.assertEqual(imports, ["Length", "Mass"])

    def test_fallback_when_the_lua_is_not_a_table(self) -> None:
        rules, _ = parse_cgroup_lua("local x = 'zh-cn:米; zh-tw:公尺;'")
        self.assertIn("zh-cn:米; zh-tw:公尺;", rules)

    def test_a_module_wrapper_becomes_an_import(self) -> None:
        rules, imports = parse_cgroup_lua("return require( 'Module:CGroup/Lifesciences' );")
        self.assertEqual(rules, [])
        self.assertEqual(imports, ["Lifesciences"])

    def test_mw_loaddata_wrapper_is_also_followed(self) -> None:
        _, imports = parse_cgroup_lua("return mw.loadData( 'Module:CGroup/Unit' )")
        self.assertEqual(imports, ["Unit"])


class RuleMappingTest(unittest.TestCase):
    def test_variant_rule_maps_the_other_variant_to_mainland(self) -> None:
        self.assertEqual(
            rule_mappings("zh-cn:米; zh-tw:公尺;", ("zh-cn",)),
            [("公尺", "米")],
        )

    def test_one_way_rule_only_applies_to_its_variant(self) -> None:
        self.assertEqual(
            rule_mappings("公尺=>zh-cn:米;", ("zh-cn",)), [("公尺", "米")]
        )
        self.assertEqual(rule_mappings("公尺=>zh-cn:米;", ("zh-tw",)), [])

    def test_zh_hans_is_the_fallback_target(self) -> None:
        self.assertEqual(
            rule_mappings("zh-hans:纳米; zh-tw:奈米;", ("zh-cn", "zh-hans")),
            [("奈米", "纳米")],
        )

    def test_build_and_apply_replacements(self) -> None:
        replacements = build_replacements(
            ["zh-cn:米; zh-tw:公尺;", "zh-cn:千克; zh-tw:公斤;"]
        )
        self.assertEqual(apply_replacements("平方公尺", replacements), "平方米")
        self.assertEqual(apply_replacements("公斤", replacements), "千克")

    def test_existing_target_is_not_converted_again(self) -> None:
        """Regression: 胞器=>细胞器 must not turn 细胞器 into 细细胞器."""
        self.assertEqual(
            apply_replacements("细胞器", [("胞器", "细胞器")]), "细胞器"
        )
        self.assertEqual(
            apply_replacements("细胞器", [("胞器", "细胞器")]),
            apply_replacements(
                apply_replacements("细胞器", [("胞器", "细胞器")]),
                [("胞器", "细胞器")],
            ),
        )

    def test_longest_source_wins_in_one_pass(self) -> None:
        replacements = [("细胞", "A"), ("细胞器", "B")]
        self.assertEqual(apply_replacements("细胞器", replacements), "B")


class FakeCacheDB:
    def __init__(self) -> None:
        self.rows: dict[str, list[dict[str, Any]]] = {}

    def search(self, table: str, conditions: dict[str, Any] | None = None,
               columns: list[str] | None = None, limit: int | None = None) -> list[dict[str, Any]]:
        rows = self.rows.get(table, [])
        if not conditions:
            return [dict(row) for row in rows]
        return [
            dict(row) for row in rows
            if all(row.get(key) == value for key, value in conditions.items())
        ]

    def insert(self, table: str, data: dict[str, Any]) -> bool:
        self.rows.setdefault(table, []).append(dict(data))
        return True

    def update(self, table: str, data: dict[str, Any], conditions: dict[str, Any]) -> bool:
        changed = False
        for row in self.rows.get(table, []):
            if all(row.get(key) == value for key, value in conditions.items()):
                row.update(data)
                changed = True
        return changed


class FakeWiki:
    def __init__(self, pages: dict[str, Any]) -> None:
        self.pages = pages
        self.calls: list[str] = []

    def api_query(self, params: dict[str, Any]) -> dict[str, Any]:
        title = str(params["titles"])
        self.calls.append(title)
        if title not in self.pages:
            return {"query": {"pages": [{"title": title, "missing": True}]}}
        content = self.pages[title]
        return {
            "query": {
                "pages": [{
                    "title": title,
                    "revisions": [{
                        "revid": 123,
                        "slots": {"main": {"content": content}},
                    }],
                }]
            }
        }


class GroupCacheTest(unittest.TestCase):
    MODULE = """
    return { name = 'Unit', content = {
        { type = 'item', rule = 'zh-cn:米; zh-tw:公尺;' },
        { type = 'import', name = 'Length' },
    } }
    """
    TEMPLATE = "{{CItem|zh-cn:千克;zh-tw:公斤;}}"

    def test_module_is_preferred_and_imports_are_followed(self) -> None:
        wiki = FakeWiki({
            "Module:CGroup/Unit": self.MODULE,
            "Template:CGroup/Unit": self.TEMPLATE,
            "Module:CGroup/Length": "return { content = { { type='item', rule='zh-cn:长;zh-tw:長;' } } }",
        })
        db = FakeCacheDB()
        rules = cgroup_cache.resolve_group("Unit", wiki_obj=wiki, db=db)
        self.assertIn("zh-cn:米; zh-tw:公尺;", rules)
        self.assertIn("zh-cn:长;zh-tw:長;", rules)
        self.assertNotIn("zh-cn:千克;zh-tw:公斤;", rules)
        self.assertNotIn("Template:CGroup/Unit", wiki.calls)

    def test_template_is_the_fallback(self) -> None:
        wiki = FakeWiki({"Template:CGroup/Unit": self.TEMPLATE})
        db = FakeCacheDB()
        self.assertEqual(
            cgroup_cache.resolve_group("Unit", wiki_obj=wiki, db=db),
            ["zh-cn:千克;zh-tw:公斤;"],
        )

    def test_results_are_cached(self) -> None:
        wiki = FakeWiki({"Template:CGroup/Unit": self.TEMPLATE})
        db = FakeCacheDB()
        cgroup_cache.resolve_group("Unit", wiki_obj=wiki, db=db)
        calls = len(wiki.calls)
        cgroup_cache.resolve_group("Unit", wiki_obj=wiki, db=db)
        self.assertEqual(len(wiki.calls), calls)
        self.assertEqual(len(db.rows[cgroup_cache.CGROUP_TABLE]), 1)

    def test_missing_group_is_cached_as_empty(self) -> None:
        wiki = FakeWiki({})
        db = FakeCacheDB()
        self.assertEqual(cgroup_cache.resolve_group("Nope", wiki_obj=wiki, db=db), [])
        calls = len(wiki.calls)
        self.assertEqual(cgroup_cache.resolve_group("Nope", wiki_obj=wiki, db=db), [])
        self.assertEqual(len(wiki.calls), calls)

    def test_import_cycles_are_broken(self) -> None:
        wiki = FakeWiki({
            "Module:CGroup/A": "return { content = { { type='import', name='B' } } }",
            "Module:CGroup/B": "return { content = { { type='import', name='A' } } }",
        })
        db = FakeCacheDB()
        self.assertEqual(cgroup_cache.resolve_group("A", wiki_obj=wiki, db=db), [])

    def test_resolve_note_ta_rules_includes_inline_title_and_groups(self) -> None:
        wiki = FakeWiki({"Template:CGroup/Unit": self.TEMPLATE})
        db = FakeCacheDB()
        config = NoteTAConfig(
            local_rules=["zh-cn:米; zh-tw:公尺;"],
            title_rules="zh-cn:纳米; zh-tw:奈米;",
            groups=["Unit"],
        )
        rules = cgroup_cache.resolve_note_ta_rules(config, wiki_obj=wiki, db=db)
        self.assertIn("zh-cn:米; zh-tw:公尺;", rules)
        self.assertIn("zh-cn:纳米; zh-tw:奈米;", rules)
        self.assertIn("zh-cn:千克;zh-tw:公斤;", rules)


if __name__ == "__main__":
    unittest.main()
