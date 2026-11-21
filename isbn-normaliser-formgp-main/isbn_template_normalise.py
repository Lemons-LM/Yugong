#!/usr/bin/env python3
"""Rewrite ISBN templates in wikitext using ISBN normalisation rules."""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import mwparserfromhell

from isbn_normalise import (
    Group,
    canonical_isbn10,
    isbn_equivalence_key,
    is_valid_isbn10,
    load_groups,
    normalise_token,
)

SPECIAL_NAMESPACE_ALIASES = frozenset({"special", "特殊"})
BOOKSOURCE_PAGE_ALIASES = frozenset(
    {"booksources", "書籍來源", "網絡書源", "網路書源", "网络书源"})

# ---------------------------------------------------------------------------
# Change report
# ---------------------------------------------------------------------------


@dataclass
class ChangeReport:
    """Counts of each distinct change type made to a single wikitext string."""

    booksource_links: int = 0  # [[Special:BookSources/…]] → {{ISBN}}
    isbn_normalised: int = 0  # hyphen-only normalisation (incl. Cite book)
    isbn10_converted: int = 0  # ISBN-10 → ISBN-13 conversion
    isbnt_merged: int = 0  # semantically-equal params → {{ISBNT|…}}

    @property
    def total(self) -> int:
        return (self.booksource_links + self.isbn_normalised +
                self.isbn10_converted + self.isbnt_merged)

    def __add__(self, other: ChangeReport) -> ChangeReport:
        return ChangeReport(
            booksource_links=self.booksource_links + other.booksource_links,
            isbn_normalised=self.isbn_normalised + other.isbn_normalised,
            isbn10_converted=self.isbn10_converted + other.isbn10_converted,
            isbnt_merged=self.isbnt_merged + other.isbnt_merged,
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
    normalised = try_normalise_template_value(label_str, groups,
                                              convert_10_to_13)
    return normalised if normalised is not None else label_str


def are_semantically_equal_isbns(
    code_str: str,
    output_label: str | None,
) -> bool:
    if output_label is None:
        return False
    key1 = isbn_equivalence_key(code_str)
    key2 = isbn_equivalence_key(output_label)
    return key1 is not None and key1 == key2


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


def build_isbn_template_node(
    code_value: str,
    label_value: str | None,
    template_name: str = "ISBN",
) -> Any:
    if label_value is None:
        return mwparserfromhell.parse(
            f"{{{{{template_name}|{code_value}}}}}").nodes[0]
    return mwparserfromhell.parse(
        f"{{{{{template_name}|{code_value}|{label_value}}}}}").nodes[0]


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
    wikilinks = list(code.filter_wikilinks())

    for wikilink in wikilinks:
        link_isbn_raw = extract_booksource_isbn_from_title(wikilink.title)
        if link_isbn_raw is None:
            continue

        normalised_link_isbn = normalise_if_isbn(link_isbn_raw, groups,
                                                 convert_10_to_13)
        if normalised_link_isbn is None:
            continue

        if wikilink.text is None:
            continue

        label_raw = str(wikilink.text).strip()
        if not label_raw:
            continue

        label_isbn_raw = split_isbn_prefixed_label(label_raw)

        preferred_template = "ISBN"
        if template_preferred_map:
            if pt := template_preferred_map.get("isbn"):
                preferred_template = pt
            elif vals := list(template_preferred_map.values()):
                preferred_template = vals[0]

        if label_isbn_raw is not None:
            label_isbn_normalised = normalise_if_isbn(label_isbn_raw, groups,
                                                      convert_10_to_13)
            if (label_isbn_normalised is not None
                    and are_semantically_equal_isbns(link_isbn_raw,
                                                     label_isbn_raw)):
                replacement = build_isbn_template_node(normalised_link_isbn,
                                                       None,
                                                       preferred_template)
            else:
                replacement = build_isbn_template_node(
                    normalised_link_isbn,
                    label_isbn_normalised
                    if label_isbn_normalised is not None else label_raw,
                    preferred_template,
                )
        else:
            label_isbn_normalised = normalise_if_isbn(label_raw, groups,
                                                      convert_10_to_13)
            replacement = build_isbn_template_node(
                normalised_link_isbn,
                label_isbn_normalised
                if label_isbn_normalised is not None else label_raw,
                preferred_template,
            )

        code.replace(wikilink, replacement)
        report.booksource_links += 1

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

    templates_found = list(
        code.filter_templates(matches=lambda t: canonicalise_title_fragment(
            str(t.name)) in template_name_aliases))

    for template in templates_found:
        if not template.has("1"):
            continue

        param1 = template.get("1")
        code_str = str(param1.value).strip()

        normalised_1 = try_normalise_template_value(code_str, groups,
                                                    convert_10_to_13)
        if normalised_1 is None:
            continue

        output_label = get_template_label_value(template, groups,
                                                convert_10_to_13)
        equal_isbn = are_semantically_equal_isbns(code_str, output_label)

        if rehyphenate_equal_label and equal_isbn:
            if template_preferred_map:
                preferred_isbnt = template_preferred_map.get("isbnt")
            else:
                preferred_isbnt = None
            if preferred_isbnt:
                template.name = preferred_isbnt
            template.get("1").value = normalised_1
            if template.has("2"):
                template.remove("2")
            report.isbnt_merged += 1
            continue

        original_code = code_str
        original_label = (str(template.get("2").value).strip()
                          if template.has("2") else None)

        if normalised_1 == original_code and output_label == original_label:
            continue

        template.get("1").value = normalised_1
        update_template_label(template, output_label)

        if convert_10_to_13 and _is_isbn10_input(original_code):
            report.isbn10_converted += 1
        else:
            report.isbn_normalised += 1

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
        f"normalised={report.isbn_normalised}, "
        f"converted={report.isbn10_converted}, "
        f"isbnt={report.isbnt_merged})",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
