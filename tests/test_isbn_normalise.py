"""ISBN core rules and the {{ISBN}}/BookSources normalisation job."""

from __future__ import annotations

import unittest
from contextlib import contextmanager
from typing import Iterator
from unittest import mock

from src.Yugong.extensions import isbn_normalise
from src.Yugong.utilities import isbn as isbn_core
from src.Yugong.utilities.path_helper import PROJECT_ROOT
from tests.support import run_job

ISBN13_RAW = "9787302511625"
ISBN13_HYPHENATED = "978-7-302-51162-5"
ISBN10_RAW = "0306406152"
ISBN10_HYPHENATED = "0-306-40615-2"
ISBN10_AS13 = "9780306406157"
ISBN10_AS13_HYPHENATED = "978-0-306-40615-7"

#: A valid EAN-13 that is not an ISBN (does not start with 978/979).
EAN13_NON_ISBN = "4006381333931"


@contextmanager
def isbn_settings(
    *,
    enabled: bool = True,
    style: str = "qiuwen",
    to13: bool = False,
    merge: bool = False,
    overwrite_para_name: bool = True,
    overwrite_template_name: bool = True,
    template_names: list[str] | None = None,
    range_path: str = "",
) -> Iterator[None]:
    patch = mock.patch.multiple(
        isbn_normalise.settings,
        enable_isbn_normalise=enabled,
        isbn_template_style=style,
        isbn_convert_10_to_13=to13,
        isbn_rehyphenate_equal_label=merge,
        overwrite_para_name=overwrite_para_name,
        overwrite_template_name=overwrite_template_name,
        isbn_template_names=(
            template_names if template_names is not None else []
        ),
        isbn_range_message_path=range_path,
    )
    with patch:
        yield


def fix(text: str, **kwargs: object) -> str:
    with isbn_settings(**kwargs):  # type: ignore[arg-type]
        return run_job(isbn_normalise.isbn_normalise_job, text)


class IsbnCoreTest(unittest.TestCase):
    def test_bundled_range_file_is_usable(self) -> None:
        groups = isbn_core.load_groups(isbn_core.RANGE_MESSAGE_PATH)
        self.assertGreater(len(groups), 100)

    def test_isbn13_is_hyphenated(self) -> None:
        self.assertEqual(isbn_core.normalise(ISBN13_RAW), ISBN13_HYPHENATED)
        self.assertEqual(
            isbn_core.normalise(ISBN13_HYPHENATED), ISBN13_HYPHENATED
        )

    def test_isbn10_is_hyphenated(self) -> None:
        self.assertEqual(isbn_core.normalise(ISBN10_RAW), ISBN10_HYPHENATED)

    def test_isbn10_can_be_converted_to_isbn13(self) -> None:
        self.assertEqual(
            isbn_core.normalise(ISBN10_RAW, convert_10_to_13=True),
            ISBN10_AS13_HYPHENATED,
        )

    def test_invalid_check_digit_raises(self) -> None:
        with self.assertRaises(ValueError):
            isbn_core.normalise("9787302511624")

    def test_isbn13_requires_a_978_or_979_prefix(self) -> None:
        self.assertTrue(isbn_core.is_valid_gs1(EAN13_NON_ISBN))
        self.assertFalse(isbn_core.is_valid_isbn13(EAN13_NON_ISBN))

    def test_isbn10_and_isbn13_share_an_equivalence_key(self) -> None:
        self.assertEqual(
            isbn_core.isbn_equivalence_key(ISBN10_RAW),
            isbn_core.isbn_equivalence_key(ISBN10_AS13),
        )
        self.assertEqual(
            isbn_core.isbn_equivalence_key(ISBN10_RAW), ISBN10_AS13
        )

    def test_is_isbn_token_rejects_text_around_the_isbn(self) -> None:
        self.assertTrue(isbn_core.is_isbn_token(ISBN13_HYPHENATED))
        self.assertTrue(isbn_core.is_isbn_token("030640615X"))
        self.assertFalse(isbn_core.is_isbn_token(f"精装 {ISBN13_RAW}"))
        self.assertFalse(isbn_core.is_isbn_token("ISBN 978-7-302-51162-5"))

    def test_missing_range_file_raises(self) -> None:
        with self.assertRaises(FileNotFoundError):
            isbn_core.load_groups(PROJECT_ROOT / "does-not-exist.xml")


class QiuwenTemplateTest(unittest.TestCase):
    """Qiuwen: parameters 1–9 are ISBNs; parameter 2 is not a display label."""

    def test_disabled_is_a_no_op(self) -> None:
        text = f"{{{{ISBN|{ISBN13_RAW}}}}}"
        self.assertEqual(fix(text, enabled=False), text)

    def test_numbered_parameter_is_hyphenated(self) -> None:
        self.assertEqual(
            fix(f"{{{{ISBN|{ISBN13_RAW}}}}}"),
            f"{{{{ISBN|{ISBN13_HYPHENATED}}}}}",
        )

    def test_multiple_isbns_are_all_hyphenated(self) -> None:
        self.assertEqual(
            fix(f"{{{{ISBN|{ISBN13_RAW}|{ISBN10_RAW}}}}}"),
            f"{{{{ISBN|{ISBN13_HYPHENATED}|{ISBN10_HYPHENATED}}}}}",
        )

    def test_named_options_are_not_touched(self) -> None:
        self.assertEqual(
            fix(
                f"{{{{ISBN|{ISBN13_RAW}|{ISBN10_RAW}"
                "|plainlink=yes|leadout=和|invalid1=yes}}"
            ),
            f"{{{{ISBN|{ISBN13_HYPHENATED}|{ISBN10_HYPHENATED}"
            "|plainlink=yes|leadout=和|invalid1=yes}}",
        )

    def test_second_isbn_is_not_merged_even_when_enabled(self) -> None:
        self.assertEqual(
            fix(
                f"{{{{ISBN|{ISBN13_RAW}|{ISBN13_RAW}}}}}",
                merge=True,
            ),
            f"{{{{ISBN|{ISBN13_HYPHENATED}|{ISBN13_HYPHENATED}}}}}",
        )

    def test_isbnt_template_is_hyphenated(self) -> None:
        self.assertEqual(
            fix(f"{{{{ISBNT|{ISBN13_RAW}}}}}"),
            f"{{{{ISBNT|{ISBN13_HYPHENATED}}}}}",
        )

    def test_cite_book_isbn_parameter_is_hyphenated(self) -> None:
        self.assertEqual(
            fix(f"{{{{Cite book|title=X|isbn={ISBN13_RAW}}}}}"),
            f"{{{{Cite book|title=X|isbn={ISBN13_HYPHENATED}}}}}",
        )

    def test_citation_isbn_parameter_is_hyphenated(self) -> None:
        self.assertEqual(
            fix(f"{{{{Citation|title=X|isbn={ISBN13_RAW}}}}}"),
            f"{{{{Citation|title=X|isbn={ISBN13_HYPHENATED}}}}}",
        )

    def test_uppercase_isbn_parameter_is_lowercased(self) -> None:
        self.assertEqual(
            fix(f"{{{{Cite book|title=X|ISBN={ISBN13_RAW}}}}}"),
            f"{{{{Cite book|title=X|isbn={ISBN13_HYPHENATED}}}}}",
        )

    def test_uppercase_parameter_is_kept_when_renames_are_disabled(self) -> None:
        self.assertEqual(
            fix(
                f"{{{{Cite book|title=X|ISBN={ISBN13_RAW}}}}}",
                overwrite_para_name=False,
            ),
            f"{{{{Cite book|title=X|ISBN={ISBN13_HYPHENATED}}}}}",
        )

    def test_invalid_isbn_is_left_alone(self) -> None:
        text = "{{ISBN|9787302511624}}"
        self.assertEqual(fix(text), text)

    def test_isbn10_can_be_converted_to_isbn13(self) -> None:
        self.assertEqual(
            fix(f"{{{{ISBN|{ISBN10_RAW}}}}}", to13=True),
            f"{{{{ISBN|{ISBN10_AS13_HYPHENATED}}}}}",
        )

    def test_custom_template_name_is_handled(self) -> None:
        self.assertEqual(
            fix(
                f"{{{{书籍ISBN|{ISBN13_RAW}}}}}",
                template_names=["书籍ISBN"],
            ),
            f"{{{{书籍ISBN|{ISBN13_HYPHENATED}}}}}",
        )

    def test_idempotence(self) -> None:
        once = fix(
            f"{{{{ISBN|{ISBN10_RAW}}}}}"
            f"\n[[Special:BookSources/{ISBN13_RAW}|某书]]"
        )
        self.assertEqual(fix(once), once)


class MoegirlTemplateTest(unittest.TestCase):
    """Moegirl: parameter 1 is the ISBN and parameter 2 is a display label."""

    def test_display_label_is_preserved(self) -> None:
        self.assertEqual(
            fix(f"{{{{ISBN|{ISBN13_RAW}|某书}}}}", style="moegirl"),
            f"{{{{ISBN|{ISBN13_HYPHENATED}|某书}}}}",
        )

    def test_isbn_inside_a_longer_label_is_hyphenated(self) -> None:
        self.assertEqual(
            fix(
                f"{{{{ISBN|{ISBN13_RAW}|精装 {ISBN13_RAW}}}}}",
                style="moegirl",
            ),
            f"{{{{ISBN|{ISBN13_HYPHENATED}|精装 {ISBN13_HYPHENATED}}}}}",
        )

    def test_second_parameter_is_a_label_not_an_isbn(self) -> None:
        # The same text is two ISBNs on Qiuwen but a label on Moegirl.
        self.assertEqual(
            fix(f"{{{{ISBN|{ISBN13_RAW}|{ISBN10_RAW}}}}}", style="moegirl"),
            f"{{{{ISBN|{ISBN13_HYPHENATED}|{ISBN10_HYPHENATED}}}}}",
        )

    def test_equal_parameters_become_isbnt(self) -> None:
        self.assertEqual(
            fix(
                f"{{{{ISBN|{ISBN13_RAW}|{ISBN13_RAW}}}}}",
                style="moegirl",
                merge=True,
            ),
            f"{{{{ISBNT|{ISBN13_HYPHENATED}}}}}",
        )

    def test_isbn10_label_equal_to_isbn13_is_merged(self) -> None:
        self.assertEqual(
            fix(
                f"{{{{ISBN|{ISBN10_RAW}|{ISBN10_AS13}}}}}",
                style="moegirl",
                merge=True,
            ),
            f"{{{{ISBNT|{ISBN10_HYPHENATED}}}}}",
        )

    def test_merge_is_skipped_when_template_renames_are_disabled(self) -> None:
        self.assertEqual(
            fix(
                f"{{{{ISBN|{ISBN13_RAW}|{ISBN13_RAW}}}}}",
                style="moegirl",
                merge=True,
                overwrite_template_name=False,
            ),
            f"{{{{ISBN|{ISBN13_HYPHENATED}|{ISBN13_HYPHENATED}}}}}",
        )

    def test_different_labels_are_not_merged(self) -> None:
        self.assertEqual(
            fix(
                f"{{{{ISBN|{ISBN13_RAW}|某书}}}}",
                style="moegirl",
                merge=True,
            ),
            f"{{{{ISBN|{ISBN13_HYPHENATED}|某书}}}}",
        )

    def test_custom_template_name_gets_parameter_1_normalised(self) -> None:
        self.assertEqual(
            fix(
                f"{{{{书籍ISBN|{ISBN13_RAW}}}}}",
                style="moegirl",
                template_names=["书籍ISBN"],
            ),
            f"{{{{书籍ISBN|{ISBN13_HYPHENATED}}}}}",
        )


class QiuwenBookSourcesTest(unittest.TestCase):
    def test_isbn_only_label_becomes_an_isbn_template(self) -> None:
        self.assertEqual(
            fix(f"[[Special:BookSources/{ISBN13_RAW}|ISBN {ISBN13_RAW}]]"),
            f"{{{{ISBN|{ISBN13_HYPHENATED}}}}}",
        )
        # A bare-number label uses the no-prefix template so the rendered
        # text keeps its original form.
        self.assertEqual(
            fix(f"[[Special:BookSources/{ISBN13_RAW}|{ISBN13_RAW}]]"),
            f"{{{{ISBNT|{ISBN13_HYPHENATED}}}}}",
        )

    def test_custom_label_keeps_the_link_and_normalises_its_target(self) -> None:
        self.assertEqual(
            fix(f"[[Special:BookSources/{ISBN13_RAW}|某书]]"),
            f"[[Special:BookSources/{ISBN13_HYPHENATED}|某书]]",
        )

    def test_valid_non_isbn_ean13_link_is_left_alone(self) -> None:
        text = f"[[Special:BookSources/{EAN13_NON_ISBN}|某书]]"
        self.assertEqual(fix(text), text)

    def test_non_gs1_link_becomes_plain_text_with_a_note(self) -> None:
        result = fix("[[Special:BookSources/foobar|某书]]")
        self.assertNotIn("[[Special:BookSources/", result)
        self.assertIn("某书<!--", result)
        self.assertIn("链接目标：foobar", result)

    def test_invalid_check_digit_is_marked_when_the_label_is_the_isbn(self) -> None:
        result = fix("[[Special:BookSources/9787302511624|9787302511624]]")
        self.assertIn("{{ISBNT|", result)
        self.assertIn("校验未通过", result)
        self.assertIn("校验位为5", result)

    def test_invalid_check_digit_link_with_a_label_is_left_alone(self) -> None:
        text = "[[Special:BookSources/9787302511624|某书]]"
        self.assertEqual(fix(text), text)

    def test_localised_namespace_and_page_name_are_recognised(self) -> None:
        self.assertEqual(
            fix(f"[[特殊:網絡書源/{ISBN13_RAW}|ISBN {ISBN13_RAW}]]"),
            f"{{{{ISBN|{ISBN13_HYPHENATED}}}}}",
        )


class MoegirlBookSourcesTest(unittest.TestCase):
    def test_isbn_link_becomes_an_isbn_template(self) -> None:
        self.assertEqual(
            fix(
                f"[[Special:BookSources/{ISBN13_RAW}|ISBN {ISBN13_RAW}]]",
                style="moegirl",
            ),
            f"{{{{ISBN|{ISBN13_HYPHENATED}}}}}",
        )

    def test_non_isbn_label_is_preserved_as_parameter_2(self) -> None:
        self.assertEqual(
            fix(
                f"[[Special:BookSources/{ISBN13_RAW}|某书]]",
                style="moegirl",
            ),
            f"{{{{ISBN|{ISBN13_HYPHENATED}|某书}}}}",
        )


class IsbnConfigTest(unittest.TestCase):
    def test_empty_template_list_uses_style_defaults(self) -> None:
        self.assertEqual(
            fix(f"{{{{ISBN|{ISBN13_RAW}}}}}", template_names=[]),
            f"{{{{ISBN|{ISBN13_HYPHENATED}}}}}",
        )

    def test_unsupported_style_fails_loudly(self) -> None:
        with self.assertRaises(ValueError):
            fix(f"{{{{ISBN|{ISBN13_RAW}}}}}", style="other")

    def test_missing_range_file_fails_loudly(self) -> None:
        with self.assertRaises(FileNotFoundError):
            fix(
                f"{{{{ISBN|{ISBN13_RAW}}}}}",
                range_path="does-not-exist.xml",
            )


if __name__ == "__main__":
    unittest.main()
