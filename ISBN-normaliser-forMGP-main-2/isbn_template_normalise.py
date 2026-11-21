#!/usr/bin/env python3
"""Rewrite ISBN templates in wikitext using ISBN normalisation rules."""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import mwparserfromhell

from isbn_normalise import (
    Group,
    canonical_isbn10,
    canonical_gs1,
    compute_isbn10_check_digit,
    compute_isbn13_check_digit,
    isbn_equivalence_key,
    is_valid_gs1,
    is_valid_isbn10,
    is_valid_isbn13,
    is_isbn_token,
    hyphenate_isbn10,
    hyphenate_isbn13,
    load_groups,
    normalise_token,
)

SPECIAL_NAMESPACE_ALIASES = frozenset({"special", "特殊"})
BOOKSOURCE_PAGE_ALIASES = frozenset({"booksources", "書籍來源", "網絡書源", "網路書源", "网络书源"})

# ---------------------------------------------------------------------------
# Change report
# ---------------------------------------------------------------------------


@dataclass
class ChangeReport:
    """Counts of each distinct change type made to a single wikitext string."""

    booksource_links: int = 0  # [[Special:BookSources/…]] → {{ISBN}}
    booksource_links_removed: int = 0  # BookSources links → plain text
    gs1_links_plaintext: int = 0  # Valid non-ISBN GS1 links → plain text
    isbn_normalised: int = 0  # hyphen-only normalisation (incl. Cite book)
    isbn10_converted: int = 0  # ISBN-10 → ISBN-13 conversion
    isbnt_merged: int = 0  # semantically-equal params → {{ISBNT|…}}
    # Auxiliary flag, deliberately excluded from `total`: set when a
    # booksource_links or isbnt_merged change *also* altered an ISBN
    # value's actual formatting, as opposed to being a pure link→template
    # swap or template→ISBNT rename where the code was already correctly
    # formatted. Lets compose_summary() decide whether the ISO 2108 notice
    # is warranted, since isbn_normalised/isbn10_converted always imply an
    # actual format change on their own.
    isbn_reformatted: int = 0

    @property
    def total(self) -> int:
        return (self.booksource_links + self.isbn_normalised +
                self.isbn10_converted + self.isbnt_merged +
                self.booksource_links_removed)

    def __add__(self, other: ChangeReport) -> ChangeReport:
        return ChangeReport(
            booksource_links=self.booksource_links + other.booksource_links,
            booksource_links_removed=(self.booksource_links_removed +
                                      other.booksource_links_removed),
            gs1_links_plaintext=(self.gs1_links_plaintext +
                                 other.gs1_links_plaintext),
            isbn_normalised=self.isbn_normalised + other.isbn_normalised,
            isbn10_converted=self.isbn10_converted + other.isbn10_converted,
            isbnt_merged=self.isbnt_merged + other.isbnt_merged,
            isbn_reformatted=self.isbn_reformatted + other.isbn_reformatted,
        )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _is_isbn10_input(raw: str) -> bool:
    """Return True if *raw* is a valid ISBN-10 (before any conversion)."""
    code10 = canonical_isbn10(raw)
    return len(code10) == 10 and is_valid_isbn10(code10)


def try_normalise_template_value(
    raw_value: str,
    groups: list[Group],
    convert_10_to_13: bool,
) -> str | None:
    try:
        return normalise_token(
            raw_value,
            groups,
            convert_10_to_13=convert_10_to_13,
            with_label=False,
        )
    except ValueError:
        return None


def get_template_label_value(
    template: Any,
    groups: list[Group],
    convert_10_to_13: bool,
) -> str | None:
    if not template.has("2"):
        return None
    label_str = str(template.get("2").value).strip()
    if not label_str:
        return None
    return normalise_label_isbn(label_str, groups, convert_10_to_13)


def are_semantically_equal_isbns(
    code_str: str,
    output_label: str | None,
) -> bool:
    if output_label is None or not is_isbn_token(output_label):
        return False
    key1 = isbn_equivalence_key(code_str)
    key2 = isbn_equivalence_key(output_label)
    if key1 is not None and key1 == key2:
        return True

    # Invalid ISBNs cannot produce an equivalence key, but an identical
    # ISBN-shaped value should still not be duplicated as a display label.
    code13 = canonical_gs1(code_str)
    label13 = canonical_gs1(output_label)
    if is_isbn13_code(code13) and is_isbn13_code(label13):
        return code13 == label13

    code10 = canonical_isbn10(code_str)
    label10 = canonical_isbn10(output_label)
    return (len(code10) == 10 and len(label10) == 10 and code10 == label10)


def update_template_label(template: Any, output_label: str | None) -> None:
    if output_label is None:
        if template.has("2"):
            template.remove("2")
        return
    if template.has("2"):
        template.get("2").value = output_label
    else:
        template.add("2", output_label)


def extract_booksource_isbn_from_title(title: Any) -> str | None:
    title_str = str(title).strip()
    if not title_str:
        return None

    if title_str.startswith(":"):
        title_str = title_str[1:].strip()

    if "/" not in title_str:
        return None

    prefix_text, suffix_text = title_str.split("/", 1)
    if ":" not in prefix_text:
        return None

    namespace_raw, page_raw = prefix_text.split(":", 1)
    namespace = canonicalise_title_fragment(namespace_raw)
    page_name = canonicalise_title_fragment(page_raw)

    if namespace not in SPECIAL_NAMESPACE_ALIASES:
        return None
    if page_name not in BOOKSOURCE_PAGE_ALIASES:
        return None

    isbn_text = suffix_text.strip()
    return isbn_text or None


def canonicalise_title_fragment(value: str) -> str:
    return "".join(ch for ch in value.strip().casefold()
                   if not ch.isspace() and ch != "_")


def parse_template_name_aliases(
        template_preferred_map: dict[str, str] | None) -> frozenset[str]:
    if not template_preferred_map:
        return frozenset()
    return frozenset(template_preferred_map.keys())


def split_isbn_prefixed_label(label: str) -> str | None:
    text = label.strip()
    if len(text) <= 4:
        return None
    if text[:4].casefold() != "isbn":
        return None
    rest = text[4:]
    if not rest or not rest[0].isspace():
        return None
    extracted = rest.strip()
    return extracted or None


def get_template_param_by_name(template: Any, target_name: str) -> Any | None:
    if not (target := target_name.strip().casefold()):
        return None
    return next(
        (param for param in template.params
         if str(param.name).strip().casefold() == target),
        None,
    )


def is_cite_book_template(template: Any) -> bool:
    return canonicalise_title_fragment(str(template.name)) == "citebook"


def normalise_if_isbn(
    raw_value: str,
    groups: list[Group],
    convert_10_to_13: bool,
) -> str | None:
    key = isbn_equivalence_key(raw_value)
    if key is None:
        return None
    return try_normalise_template_value(raw_value, groups, convert_10_to_13)


_ISBN_RUN_RE = re.compile(r"[0-9][0-9 \-]*[0-9Xx]")


def normalise_label_isbn(
    label: str,
    groups: list[Group],
    convert_10_to_13: bool,
) -> str:
    """Hyphenate the ISBN inside a display label and keep the other text.

    A display label may carry text beside its ISBN, such as a binding note
    ("精装 9787302511625"). Only the ISBN run is normalised, so the
    note stays on the page. A label with no valid ISBN is returned unchanged.
    """
    text = label.strip()
    for match in reversed(list(_ISBN_RUN_RE.finditer(text))):
        normalised = normalise_if_isbn(match.group(0), groups,
                                       convert_10_to_13)
        if normalised is not None:
            text = f"{text[:match.start()]}{normalised}{text[match.end():]}"
    return text


def label_isbn_core(label: str) -> str:
    """Return the label without a leading "ISBN" prefix, when it has one."""
    return split_isbn_prefixed_label(label) or label.strip()


def is_isbn_shaped(raw_value: str) -> bool:
    code13 = canonical_gs1(raw_value)
    if code13 is not None and len(code13) == 13:
        return code13.startswith(("978", "979"))
    code10 = canonical_isbn10(raw_value)
    return len(code10) == 10


def is_isbn13_code(code13: str | None) -> bool:
    return (code13 is not None and len(code13) == 13 and code13.startswith(
        ("978", "979")))


def has_valid_isbn_check_digit(raw_value: str) -> bool:
    code13 = canonical_gs1(raw_value)
    if is_isbn13_code(code13):
        return is_valid_isbn13(code13)
    code10 = canonical_isbn10(raw_value)
    return len(code10) == 10 and is_valid_isbn10(code10)


def try_hyphenate_invalid_isbn(
    raw_value: str,
    groups: list[Group],
) -> tuple[str, str] | None:
    """Hyphenate an ISBN-shaped value without trusting its check digit.

    Return the formatted value and the check digit calculated from its body.
    A missing ISBN range mapping still makes the value unusable here.
    """
    code13 = canonical_gs1(raw_value)
    if is_isbn13_code(code13):
        try:
            formatted = hyphenate_isbn13(
                code13,
                groups,
                with_label=False,
                validate_check_digit=False,
            )
        except ValueError:
            return None
        expected = str(compute_isbn13_check_digit(code13[:12]))
        return formatted, expected

    code10 = canonical_isbn10(raw_value)
    if len(code10) != 10:
        return None
    try:
        formatted = hyphenate_isbn10(
            code10,
            groups,
            with_label=False,
            validate_check_digit=False,
        )
    except ValueError:
        return None
    expected = compute_isbn10_check_digit(code10[:9])
    return formatted, expected


def add_invalid_check_digit_note(formatted: str, expected: str) -> str:
    return f"{formatted}<!-- 可匹配组区号与出版者号，但校验未通过。可能是手动转换 ISBN-10/13 错误。请勿手动转换。若存在，校验位为{expected} -->"


def add_unmapped_isbn_note(raw_value: str) -> str:
    return (f"{raw_value}<!-- 符合 ISBN 格式，但组区号与出版者号无法匹配 -->")


def add_invalid_unmapped_isbn_note(raw_value: str) -> str:
    return (f"{raw_value}<!-- ISBN 校验未通过，且组区号与出版者号无法匹配。这是什么？ -->")


def add_removed_booksource_note(display_text: str, target: str) -> str:
    return f"{display_text}<!-- 此处原使用[[Special:网络书源]]，链接目标：{target} -->"


def is_valid_ean13(raw_value: str) -> bool:
    digits = canonical_gs1(raw_value)
    return (digits is not None and len(digits) == 13
            and is_valid_gs1(raw_value))


def build_isbn_template_node(
    code_value: str,
    label_value: str | None,
    template_name: str = "ISBN",
) -> Any:
    template = mwparserfromhell.nodes.Template(template_name)
    template.add("1", code_value)
    if label_value is not None:
        template.add("2", label_value)
    return template


def preferred_isbn_template_name(
        template_preferred_map: dict[str, str] | None) -> str:
    if not template_preferred_map:
        return "ISBN"
    return (template_preferred_map.get("isbn")
            or next(iter(template_preferred_map.values()), "ISBN"))


def get_booksource_display_text(wikilink: Any, target: str) -> str:
    return (str(wikilink.text).strip()
            if wikilink.text is not None else target.strip())


def build_non_isbn_booksource_replacement(
    wikilink: Any,
    raw_value: str,
) -> tuple[str, str | None]:
    display_text = get_booksource_display_text(wikilink, raw_value)
    if not display_text or is_valid_ean13(raw_value):
        return "", None
    category = "gs1" if is_valid_gs1(raw_value) else None
    return (add_removed_booksource_note(display_text,
                                        raw_value.strip()), category)


def build_booksource_template_value(
    raw_value: str,
    groups: list[Group],
    convert_10_to_13: bool,
) -> tuple[str, bool, bool]:
    normalised = normalise_if_isbn(raw_value, groups, convert_10_to_13)
    if normalised is not None:
        return normalised, True, normalised != raw_value.strip()

    if not is_isbn_shaped(raw_value):
        return "", False, False

    invalid_isbn = try_hyphenate_invalid_isbn(raw_value, groups)
    if invalid_isbn is not None:
        formatted, expected = invalid_isbn
        return add_invalid_check_digit_note(formatted, expected), True, True

    if has_valid_isbn_check_digit(raw_value):
        return add_unmapped_isbn_note(raw_value.strip()), True, False
    return add_invalid_unmapped_isbn_note(raw_value.strip()), True, False


def build_booksource_replacement(
    wikilink: Any,
    groups: list[Group],
    convert_10_to_13: bool,
    template_preferred_map: dict[str, str] | None,
) -> tuple[str, bool, str | None, bool]:
    raw_value = extract_booksource_isbn_from_title(wikilink.title)
    if raw_value is None:
        return "", False, None, False

    template_value, is_isbn, reformatted = build_booksource_template_value(
        raw_value, groups, convert_10_to_13)
    if not is_isbn:
        replacement, category = build_non_isbn_booksource_replacement(
            wikilink, raw_value)
        if not replacement:
            return "", False, None, False
        return replacement, True, category, False

    code_reformatted = reformatted
    label_raw = get_booksource_display_text(wikilink, "")
    display_label = None
    if label_raw:
        display_label = normalise_label_isbn(label_raw, groups,
                                             convert_10_to_13)
        core = label_isbn_core(display_label)
        if is_isbn_token(core) and are_semantically_equal_isbns(
                template_value, core):
            # The label holds nothing but the ISBN, so the default link text
            # already shows it. Drop the label and report only whether the
            # ISBN code's own formatting changed.
            display_label = None
        else:
            reformatted = (code_reformatted
                           or display_label != label_raw.strip())
    replacement = build_isbn_template_node(
        template_value,
        display_label,
        preferred_isbn_template_name(template_preferred_map),
    )
    return str(replacement), False, None, reformatted


# ---------------------------------------------------------------------------
# Normalisation sub-routines (each returns ChangeReport)
# ---------------------------------------------------------------------------


def normalise_cite_book_isbn_templates(
    code: Any,
    groups: list[Group],
    convert_10_to_13: bool,
    template_name_aliases: frozenset[str],
) -> ChangeReport:
    report = ChangeReport()
    templates_found = list(
        code.filter_templates(
            matches=lambda template: canonicalise_title_fragment(
                str(template.name)) in template_name_aliases))

    for template in templates_found:
        isbn_param = get_template_param_by_name(template, "isbn")
        if isbn_param is None:
            continue

        raw_value = str(isbn_param.value).strip()
        if not raw_value:
            continue

        normalised_value = normalise_if_isbn(raw_value, groups,
                                             convert_10_to_13)
        if normalised_value is None or normalised_value == raw_value:
            continue

        isbn_param.value = normalised_value
        if str(isbn_param.name).strip() != "isbn":
            isbn_param.name = "isbn"  # Normalise a non-lowercase parameter name
        if convert_10_to_13 and _is_isbn10_input(raw_value):
            report.isbn10_converted += 1
        else:
            report.isbn_normalised += 1

    return report


def replace_booksource_links_with_isbn_templates(
    code: Any,
    groups: list[Group],
    convert_10_to_13: bool,
    template_preferred_map: dict[str, str] | None = None,
) -> ChangeReport:
    report = ChangeReport()
    for wikilink in list(code.filter_wikilinks()):
        replacement, removed, gs1_category, reformatted = (
            build_booksource_replacement(
                wikilink,
                groups,
                convert_10_to_13,
                template_preferred_map,
            ))
        if not replacement:
            continue
        code.replace(wikilink, replacement)
        if removed:
            report.booksource_links_removed += 1
            report.gs1_links_plaintext += int(gs1_category == "gs1")
        else:
            report.booksource_links += 1
            report.isbn_reformatted += int(reformatted)

    return report


def normalise_existing_isbn_template(
    template: Any,
    groups: list[Group],
    convert_10_to_13: bool,
    rehyphenate_equal_label: bool,
    template_preferred_map: dict[str, str] | None,
) -> ChangeReport:
    report = ChangeReport()
    if not template.has("1"):
        return report

    param1 = template.get("1")
    code_str = str(param1.value).strip()
    normalised_1 = try_normalise_template_value(code_str, groups,
                                                convert_10_to_13)
    if normalised_1 is None:
        return report

    output_label = get_template_label_value(template, groups, convert_10_to_13)
    equal_isbn = are_semantically_equal_isbns(code_str, output_label)
    if rehyphenate_equal_label and equal_isbn:
        if preferred_isbnt := (template_preferred_map or {}).get("isbnt"):
            template.name = preferred_isbnt
        if normalised_1 != code_str:
            report.isbn_reformatted += 1
        param1.value = normalised_1
        if template.has("2"):
            template.remove("2")
        report.isbnt_merged += 1
        return report

    original_label = (str(template.get("2").value).strip()
                      if template.has("2") else None)
    if normalised_1 == code_str and output_label == original_label:
        return report

    param1.value = normalised_1
    update_template_label(template, output_label)
    if convert_10_to_13 and _is_isbn10_input(code_str):
        report.isbn10_converted += 1
    else:
        report.isbn_normalised += 1
    return report


def normalise_existing_isbn_templates(
    code: Any,
    groups: list[Group],
    convert_10_to_13: bool,
    rehyphenate_equal_label: bool,
    template_name_aliases: frozenset[str],
    template_preferred_map: dict[str, str] | None,
) -> ChangeReport:
    report = ChangeReport()
    templates = code.filter_templates(
        matches=lambda template: canonicalise_title_fragment(str(
            template.name)) in template_name_aliases)
    for template in list(templates):
        report += normalise_existing_isbn_template(
            template,
            groups,
            convert_10_to_13,
            rehyphenate_equal_label,
            template_preferred_map,
        )
    return report


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def normalise_isbn_templates(
    text: str,
    xml_path: Path,
    convert_10_to_13: bool = False,
    rehyphenate_equal_label: bool = False,
    template_preferred_map: dict[str, str] | None = None,
) -> tuple[str, ChangeReport]:
    groups = load_groups(xml_path)
    report = ChangeReport()
    template_name_aliases = parse_template_name_aliases(template_preferred_map)

    code = mwparserfromhell.parse(text)
    report += normalise_cite_book_isbn_templates(
        code,
        groups,
        convert_10_to_13,
        template_name_aliases,
    )
    report += replace_booksource_links_with_isbn_templates(
        code,
        groups,
        convert_10_to_13,
        template_preferred_map,
    )
    report += normalise_existing_isbn_templates(
        code,
        groups,
        convert_10_to_13,
        rehyphenate_equal_label,
        template_name_aliases,
        template_preferred_map,
    )

    return str(code), report


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Rewrite ISBN templates in wikitext "
        "using ISBN range XML rules.")
    parser.add_argument("--xml",
                        default="RangeMessage.xml",
                        help="Path to ISBN range XML file.")
    parser.add_argument(
        "--text-file",
        required=True,
        help="Path to wikitext file to rewrite ISBN templates.")
    parser.add_argument(
        "--in-place",
        action="store_true",
        help="Write output back to --text-file instead of printing.")
    parser.add_argument("-to13",
                        "--to13",
                        action="store_true",
                        help="Convert ISBN-10 to ISBN-13 before output.")
    parser.add_argument(
        "--rehyphenate-equal-label",
        action="store_true",
        help=("When template parameter 1 and 2 are semantically "
              "the same ISBN, replace the template with "
              "{{ISBNT|$1}} and keep parameter 1 hyphenated."))
    parser.add_argument(
        "-format",
        action="store_true",
        help="Compatibility flag; formatting is always enabled.")

    args = parser.parse_args()

    xml_path = Path(args.xml)
    try:
        input_text = Path(args.text_file).read_text(encoding="utf-8")
        output_text, report = normalise_isbn_templates(
            input_text,
            xml_path,
            convert_10_to_13=args.to13,
            rehyphenate_equal_label=args.rehyphenate_equal_label,
        )
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    if args.in_place:
        Path(args.text_file).write_text(output_text, encoding="utf-8")
    else:
        print(output_text)

    print(
        f"Template replacements: {report.total} "
        f"(booksource={report.booksource_links}, "
        f"removed={report.booksource_links_removed}, "
        f"normalised={report.isbn_normalised}, "
        f"converted={report.isbn10_converted}, "
        f"isbnt={report.isbnt_merged})",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
