"""Invisible-character cleanup: safe set, protected regions and all node types."""

from __future__ import annotations

import unittest
from contextlib import contextmanager
from typing import Iterator
from unittest import mock

from src.Yugong.extensions import rm_invisible_chars
from tests.support import run_job

ZWSP = "\u200b"
ZWNJ = "\u200c"
ZWJ = "\u200d"
LRM = "\u200e"
BOM = "\ufeff"
SOFT_HYPHEN = "\u00ad"
WORD_JOINER = "\u2060"


@contextmanager
def invisible_settings(
    *, enabled: bool = True, aggressive: bool = False
) -> Iterator[None]:
    with mock.patch.multiple(
        rm_invisible_chars.settings,
        enable_invisible_chars_fix=enabled,
        invisible_chars_aggressive=aggressive,
    ):
        yield


def fix(text: str, **kwargs: object) -> str:
    with invisible_settings(**kwargs):  # type: ignore[arg-type]
        return run_job(rm_invisible_chars.rm_invisible_chars_job, text)


class InvisibleCharsTest(unittest.TestCase):
    def test_disabled_is_a_no_op(self) -> None:
        text = f"a{ZWSP}b"
        self.assertEqual(fix(text, enabled=False), text)

    def test_safe_set_is_removed(self) -> None:
        self.assertEqual(fix(f"a{ZWSP}b"), "ab")
        self.assertEqual(fix(f"{BOM}Title"), "Title")
        self.assertEqual(fix(f"soft{SOFT_HYPHEN}hyphen"), "softhyphen")
        self.assertEqual(fix(f"word{WORD_JOINER}joiner"), "wordjoiner")

    def test_control_characters_are_removed(self) -> None:
        # NUL is excluded: mwparserfromhell truncates the page at a NUL byte,
        # so it never reaches a node for this job to clean.
        self.assertEqual(fix("a\x07b\x85c\x1fd"), "abcd")

    def test_tab_newline_and_carriage_return_are_kept(self) -> None:
        text = "a\tb\nc\rd"
        self.assertEqual(fix(text), text)

    def test_real_spaces_are_kept(self) -> None:
        text = "a b\u00a0c\u2003d"
        self.assertEqual(fix(text), text)

    def test_variation_selectors_are_kept(self) -> None:
        text = "\u2764\ufe0f"
        self.assertEqual(fix(text), text)

    def test_joiners_and_bidi_marks_are_kept_by_default(self) -> None:
        for char in (ZWNJ, ZWJ, LRM):
            text = f"a{char}b"
            self.assertEqual(fix(text), text)

    def test_joiners_and_bidi_marks_are_removed_in_aggressive_mode(self) -> None:
        self.assertEqual(fix(f"a{ZWNJ}b", aggressive=True), "ab")
        self.assertEqual(fix(f"a{ZWJ}b", aggressive=True), "ab")
        self.assertEqual(fix(f"a{LRM}b", aggressive=True), "ab")

    def test_html_comments_are_untouched(self) -> None:
        text = f"<!-- note{ZWSP} -->"
        self.assertEqual(fix(text), text)


class InvisibleCharsStructureTest(unittest.TestCase):
    def test_template_name_and_parameters_are_cleaned(self) -> None:
        self.assertEqual(
            fix(f"{{{{T{ZWSP}|p{ZWSP}=V{ZWSP}}}}}"),
            "{{T|p=V}}",
        )

    def test_wikilink_target_and_label_are_cleaned(self) -> None:
        self.assertEqual(
            fix(f"[[Foo{ZWSP}|bar{ZWSP}]]"),
            "[[Foo|bar]]",
        )

    def test_external_link_url_is_cleaned(self) -> None:
        self.assertEqual(
            fix(f"https://e{ZWSP}.example/x"),
            "https://e.example/x",
        )

    def test_tag_attribute_and_contents_are_cleaned(self) -> None:
        self.assertEqual(
            fix(f'<span style="a{ZWSP}">x{ZWSP}</span>'),
            '<span style="a">x</span>',
        )

    def test_heading_is_cleaned(self) -> None:
        self.assertEqual(fix(f"== A{ZWSP} =="), "== A ==")

    def test_ref_contents_are_cleaned(self) -> None:
        self.assertEqual(
            fix(f"<ref>a{ZWSP}b</ref>"),
            "<ref>ab</ref>",
        )

    def test_protected_tag_contents_are_untouched(self) -> None:
        for tag in ("nowiki", "pre", "code", "syntaxhighlight", "source",
                    "math", "chem"):
            text = f"<{tag}>a{ZWSP}b</{tag}>"
            self.assertEqual(fix(text), text, tag)

    def test_idempotence(self) -> None:
        once = fix(f"{{{{T{ZWSP}|p{ZWSP}={ZWSP}V}}}} {BOM}x{ZWSP}")
        self.assertEqual(fix(once), once)


class InvisibleCharsWouldBeEmptyTest(unittest.TestCase):
    """Cleaning must not turn a field made only of invisibles into ``""``."""

    def test_template_name_is_kept(self) -> None:
        text = "{{" + ZWSP + "}}"
        self.assertEqual(fix(text), text)

    def test_template_name_with_parameters_is_kept(self) -> None:
        text = "{{" + ZWSP + "|a=b}}"
        self.assertEqual(fix(text), text)

    def test_parameter_name_is_kept(self) -> None:
        text = "{{T|" + ZWSP + "=v}}"
        self.assertEqual(fix(text), text)

    def test_wikilink_title_is_kept(self) -> None:
        text = "[[" + ZWSP + "]]"
        self.assertEqual(fix(text), text)

    def test_tag_name_is_kept(self) -> None:
        text = "<" + ZWSP + ">x</" + ZWSP + ">"
        self.assertEqual(fix(text), text)


if __name__ == "__main__":
    unittest.main()
