"""Safe LintErrors / QW:TODO fixes."""

from __future__ import annotations

import unittest

from src.Yugong.extensions.lint_fixes import lint_fixes_job
from tests.support import run_job


def fix(text: str) -> str:
    return run_job(lint_fixes_job, text)


class ObsoleteTagTest(unittest.TestCase):
    def test_font_colour_and_face_become_span_style(self) -> None:
        result = fix('<font color="red" face="Arial">文字</font>')
        self.assertEqual(result, '<span style="color: red; font-family: Arial">文字</span>')

    def test_font_with_size_is_left_for_a_human(self) -> None:
        text = '<font color="red" size="2">文字</font>'
        self.assertEqual(fix(text), text)

    def test_center_becomes_the_center_template(self) -> None:
        self.assertEqual(fix("<center>文字</center>"), "{{Center|文字}}")
        self.assertEqual(
            fix('<center style="color:red">文字</center>'),
            "{{Center|style=color:red|文字}}",
        )

    def test_center_with_top_level_pipe_escapes_it(self) -> None:
        self.assertEqual(fix("<center>a|b</center>"), "{{Center|a{{!}}b}}")
        self.assertEqual(
            fix("<center>[[A|B]]</center>"), "{{Center|[[A|B]]}}"
        )

    def test_center_escapes_pipes_inside_html_attributes(self) -> None:
        self.assertEqual(
            fix('<center><span style="a|b">x</span></center>'),
            '{{Center|1=<span style="a{{!}}b">x</span>}}',
        )

    def test_center_with_other_attributes_is_left_untouched(self) -> None:
        text = '<center class="x">文字</center>'
        self.assertEqual(fix(text), text)

    def test_center_around_a_table_is_left_untouched(self) -> None:
        text = '<center>\n{| class="wikitable"\n| a\n|}\n</center>'
        self.assertEqual(fix(text), text)

    def test_big_tt_and_strike(self) -> None:
        self.assertEqual(fix("<big>大</big>"), '<span style="font-size: larger">大</span>')
        self.assertEqual(fix("<tt>码</tt>"), "<code>码</code>")
        self.assertEqual(fix("<strike>旧</strike>"), "<s>旧</s>")


class AttributeTest(unittest.TestCase):
    def test_align_valign_width_height_bgcolor_border(self) -> None:
        result = fix(
            '<td align="center" valign="top" width="20" height="30" '
            'bgcolor="#fff" border="1">x</td>'
        )
        for declaration in (
            "text-align: center",
            "vertical-align: top",
            "width: 20px",
            "height: 30px",
            "background-color: #fff",
            "border: 1px solid",
        ):
            self.assertIn(declaration, result)
        for attribute in ("align=", "valign=", "width=", "height=", "bgcolor=", "border="):
            self.assertNotIn(attribute, result)

    def test_existing_style_is_not_overridden(self) -> None:
        result = fix('<td align="left" style="color: red">x</td>')
        self.assertIn("color: red", result)
        self.assertIn("text-align: left", result)

    def test_wikitable_cell_attributes_are_converted(self) -> None:
        result = fix('{| class="wikitable"\n| align=center width="20" | text\n|}')
        self.assertIn('style="text-align: center; width: 20px"', result)
        self.assertNotIn("align=center", result)

    def test_dynamic_values_are_left_alone(self) -> None:
        text = '<td align="{{{align}}}">x</td>'
        self.assertEqual(fix(text), text)


class SelfClosingTagTest(unittest.TestCase):
    def test_non_void_tags_are_paired(self) -> None:
        self.assertEqual(fix("<div/>"), "<div></div>")
        self.assertEqual(fix('<span class="x"/>'), '<span class="x"></span>')

    def test_void_and_extension_tags_are_kept(self) -> None:
        for text in ("<br/>", '<ref name="x"/>', "<nowiki/>", "<math/>"):
            self.assertEqual(fix(text), text)


class ProtectedContentTest(unittest.TestCase):
    def test_nowiki_is_not_touched(self) -> None:
        text = '<nowiki><font color="red">x</font></nowiki>'
        self.assertEqual(fix(text), text)

    def test_template_argument_values_are_fixed_but_names_are_kept(self) -> None:
        text = '{{T|p=<font color="red">y</font>}}'
        self.assertEqual(fix(text), '{{T|p=<span style="color: red">y</span>}}')

    def test_argument_defaults_are_fixed(self) -> None:
        text = '{{{arg|<font color="red">y</font>}}}'
        self.assertIn('<span style="color: red">y</span>', fix(text))


class HeadingTest(unittest.TestCase):
    def test_empty_and_comment_only_headings_are_removed(self) -> None:
        self.assertEqual(fix("a\n== ==\nb"), "a\n\nb")
        self.assertEqual(fix("a\n== <!-- x --> ==\nb"), "a\n\nb")

    def test_non_empty_heading_is_kept(self) -> None:
        text = "== 标题 =="
        self.assertEqual(fix(text), text)


class ImageOptionTest(unittest.TestCase):
    def test_duplicate_bare_sizes_are_removed(self) -> None:
        self.assertEqual(
            fix("[[File:X|240px|thumb|200px|Caption]]"),
            "[[File:X|240px|thumb|Caption]]",
        )

    def test_single_size_is_kept(self) -> None:
        text = "[[File:X|240px|thumb|Caption]]"
        self.assertEqual(fix(text), text)

    def test_nested_template_in_a_file_link_is_skipped(self) -> None:
        text = "[[File:X|240px|thumb|200px|{{T|a|b}}]]"
        self.assertEqual(fix(text), text)


class CategorySortKeyTest(unittest.TestCase):
    def test_only_empty_sort_keys_are_removed(self) -> None:
        self.assertEqual(fix("[[Category:X|  ]]"), "[[Category:X]]")
        self.assertEqual(fix("[[Category:X|key]]"), "[[Category:X|key]]")


class EmptyListItemTest(unittest.TestCase):
    def test_empty_items_left_by_template_deletion_are_removed(self) -> None:
        self.assertEqual(fix("* \n文字"), "文字")
        self.assertEqual(fix("*\n## \n** \n== 标题 =="), "== 标题 ==")

    def test_non_empty_list_items_are_kept(self) -> None:
        text = "* 有内容\n# 也有"
        self.assertEqual(fix(text), text)


class IdempotenceTest(unittest.TestCase):
    def test_running_twice_changes_nothing_more(self) -> None:
        text = '<font color="red">A</font><div/><td align="center">B</td>[[Category:X| ]]'
        once = fix(text)
        self.assertEqual(fix(once), once)


if __name__ == "__main__":
    unittest.main()
