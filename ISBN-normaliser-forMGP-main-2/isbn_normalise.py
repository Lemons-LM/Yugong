#!/usr/bin/env python3
"""Normalise ISBN strings to hyphenated, human-readable form.

This script uses ISBN registration range rules from an ISBNRangeMessage XML file
(such as RangeMessage.xml).
"""

from __future__ import annotations

import argparse
import re
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

GS1_LENGTHS = frozenset({8, 12, 13, 14, 17, 18})
# GS1 General Specifications Release 26.0, 7.9.1


@dataclass(frozen=True)
class Rule:
    start: int
    end: int
    registrant_length: int


@dataclass(frozen=True)
class Group:
    gs1: str
    group: str
    rules: tuple[Rule, ...]


def only_digits(text: str) -> str:
    return re.sub(r"\D", "", text)


def canonical_gs1(text: str) -> str | None:
    """Return digits from a GS1 code written with optional separators."""
    stripped = text.strip()
    if not stripped or re.fullmatch(r"[0-9][0-9 -]*", stripped) is None:
        return None
    digits = only_digits(stripped)
    return digits if len(digits) in GS1_LENGTHS else None


def compute_gs1_check_digit(first_digits: str) -> int:
    total = sum(
        int(digit) * (3 if index % 2 == 0 else 1)
        for index, digit in enumerate(reversed(first_digits)))
    return (10 - total % 10) % 10


def is_valid_gs1(text: str) -> bool:
    digits = canonical_gs1(text)
    return (digits is not None
            and compute_gs1_check_digit(digits[:-1]) == int(digits[-1]))


def canonical_isbn10(text: str) -> str:
    # ISBN-10 may end with X/x check digit.
    return re.sub(r"[^0-9Xx]", "", text).upper()


def compute_isbn13_check_digit(first12: str) -> int:
    return compute_gs1_check_digit(first12)


def is_valid_isbn13(digits13: str) -> bool:
    if (len(digits13) != 13 or not digits13.isdigit()
            or not digits13.startswith(("978", "979"))):
        return False
    return is_valid_gs1(digits13)


def compute_isbn10_check_digit(first9: str) -> str:
    total = sum((10 - idx) * int(ch) for idx, ch in enumerate(first9))
    remainder = total % 11
    value = (11 - remainder) % 11
    return "X" if value == 10 else str(value)


def is_valid_isbn10(code10: str) -> bool:
    if len(code10) != 10:
        return False
    if not code10[:9].isdigit():
        return False
    if not (code10[9].isdigit() or code10[9] == "X"):
        return False
    return compute_isbn10_check_digit(code10[:9]) == code10[9]


def isbn10_to_isbn13_digits(code10: str) -> str:
    first12 = f"978{code10[:9]}"
    check13 = compute_isbn13_check_digit(first12)
    return f"{first12}{check13}"


def isbn_equivalence_key(raw_isbn: str) -> str | None:
    """Build a canonical key for semantic ISBN equality checks.

    Returns ISBN-13 digits for valid ISBN-13 values or valid ISBN-10 values
    converted to ISBN-13 digits. Returns None for non-ISBN strings.
    """
    code13 = only_digits(raw_isbn)
    if len(code13) == 13 and is_valid_isbn13(code13):
        return code13

    code10 = canonical_isbn10(raw_isbn)
    if len(code10) == 10 and is_valid_isbn10(code10):
        return isbn10_to_isbn13_digits(code10)

    return None


def is_isbn_token(text: str) -> bool:
    """Return True when the whole text is a single ISBN.

    The text may hold space and hyphen separators and an ISBN-10 X check
    digit, nothing else. Text that merely contains an ISBN keeps its other
    characters, so it is not an ISBN token.
    """
    stripped = text.strip()
    if not stripped or re.fullmatch(r"[0-9Xx][0-9Xx -]*", stripped) is None:
        return False
    if (len(only_digits(stripped)) == 13
            and re.fullmatch(r"[0-9][0-9 -]*", stripped) is not None):
        return True
    return len(canonical_isbn10(stripped)) == 10


def parse_range_text(range_text: str) -> tuple[int, int]:
    start_text, end_text = range_text.split("-", 1)
    return int(start_text), int(end_text)


def load_groups(xml_path: Path) -> list[Group]:
    root = ET.parse(xml_path).getroot()

    groups: list[Group] = []
    for group_el in root.findall("./RegistrationGroups/Group"):
        prefix = (group_el.findtext("Prefix") or "").strip()
        if "-" not in prefix:
            continue

        gs1, group = prefix.split("-", 1)
        rules: list[Rule] = []
        for rule_el in group_el.findall("./Rules/Rule"):
            range_text = (rule_el.findtext("Range") or "").strip()
            length_text = (rule_el.findtext("Length") or "").strip()
            if not range_text or not length_text:
                continue

            registrant_length = int(length_text)
            if registrant_length <= 0:
                continue

            start, end = parse_range_text(range_text)
            rules.append(
                Rule(
                    start=start,
                    end=end,
                    registrant_length=registrant_length,
                ))

        if rules:
            groups.append(Group(gs1=gs1, group=group, rules=tuple(rules)))

    # Try longest registration group first (e.g. 99901 before 9).
    groups.sort(key=lambda g: len(g.group), reverse=True)
    return groups


def to_7_digit_interval(reg_pub: str) -> tuple[int, int] | None:
    if not reg_pub:
        return None

    if len(reg_pub) >= 7:
        head7 = int(reg_pub[:7])
        return head7, head7

    low = int(reg_pub) * (10**(7 - len(reg_pub)))
    high = low + (10**(7 - len(reg_pub))) - 1
    return low, high


def hyphenate_isbn13(digits13: str,
                     groups: list[Group],
                     with_label: bool = True,
                     validate_check_digit: bool = True) -> str:
    if not digits13.isdigit() or len(digits13) != 13:
        raise ValueError("ISBN must contain exactly 13 digits.")

    if not digits13.startswith(("978", "979")):
        raise ValueError("ISBN-13 must start with 978 or 979.")

    if validate_check_digit and not is_valid_isbn13(digits13):
        raise ValueError("Invalid ISBN-13 check digit.")

    check_digit = digits13[-1]

    for group in groups:
        prefix_no_hyphen = f"{group.gs1}{group.group}"
        if not digits13.startswith(prefix_no_hyphen):
            continue

        reg_pub = digits13[len(prefix_no_hyphen):12]
        interval = to_7_digit_interval(reg_pub)
        if interval is None:
            continue

        low, high = interval
        for rule in group.rules:
            if low < rule.start or high > rule.end:
                continue

            if rule.registrant_length > len(reg_pub):
                continue

            registrant = reg_pub[:rule.registrant_length]
            publication = reg_pub[rule.registrant_length:]
            if not publication:
                continue

            normalised = f"{group.gs1}-{group.group}-{registrant}-{publication}-{check_digit}"
            return f"{normalised}" if with_label else normalised

    raise ValueError("Could not map ISBN to a registration group/range rule.")


def hyphenate_isbn10(code10: str,
                     groups: list[Group],
                     with_label: bool = True,
                     validate_check_digit: bool = True) -> str:
    if validate_check_digit and not is_valid_isbn10(code10):
        raise ValueError("Invalid ISBN-10 check digit.")

    digits13 = isbn10_to_isbn13_digits(code10)

    for group in groups:
        prefix_no_hyphen = f"{group.gs1}{group.group}"
        if not digits13.startswith(prefix_no_hyphen):
            continue

        reg_pub = digits13[len(prefix_no_hyphen):12]
        interval = to_7_digit_interval(reg_pub)
        if interval is None:
            continue

        low, high = interval
        for rule in group.rules:
            if low < rule.start or high > rule.end:
                continue

            if rule.registrant_length > len(reg_pub):
                continue

            registrant = reg_pub[:rule.registrant_length]
            publication = reg_pub[rule.registrant_length:]
            if not publication:
                continue

            normalised = f"{group.group}-{registrant}-{publication}-{code10[-1]}"
            return f"{normalised}" if with_label else normalised

    raise ValueError(
        "Could not map ISBN-10 to a registration group/range rule.")


def normalise_token(raw_isbn: str,
                    groups: list[Group],
                    convert_10_to_13: bool,
                    with_label: bool = True) -> str:
    code13 = only_digits(raw_isbn)
    if len(code13) == 13 and code13.isdigit():
        return hyphenate_isbn13(code13, groups, with_label=with_label)

    code10 = canonical_isbn10(raw_isbn)
    if len(code10) == 10:
        if not is_valid_isbn10(code10):
            raise ValueError("Invalid ISBN-10 check digit.")
        if convert_10_to_13:
            converted = isbn10_to_isbn13_digits(code10)
            return hyphenate_isbn13(converted, groups, with_label=with_label)
        return hyphenate_isbn10(code10, groups, with_label=with_label)

    raise ValueError("ISBN must be valid ISBN-10 or ISBN-13.")


def normalise(raw_isbn: str,
              xml_path: Path,
              with_label: bool = True,
              convert_10_to_13: bool = False) -> str:
    groups = load_groups(xml_path)
    return normalise_token(
        raw_isbn,
        groups,
        convert_10_to_13=convert_10_to_13,
        with_label=with_label,
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Normalise ISBN-10/13 to hyphenated format "
        "using ISBN range XML rules.")
    parser.add_argument(
        "isbn",
        nargs="?",
        help="Single ISBN input (valid ISBN-10 or ISBN-13).",
    )
    parser.add_argument(
        "--xml",
        default="RangeMessage.xml",
        help="Path to ISBN range XML file.",
    )
    parser.add_argument(
        "-to13",
        "--to13",
        action="store_true",
        help="Convert ISBN-10 to ISBN-13 before output.",
    )
    parser.add_argument(
        "--no-label",
        action="store_true",
        help="Do not prefix single-ISBN output with 'ISBN '.",
    )
    parser.add_argument(
        "-format",
        action="store_true",
        help="Compatibility flag; formatting is always enabled.",
    )

    args = parser.parse_args()

    xml_path = Path(args.xml)

    if not args.isbn:
        print("Error: ISBN input is required.", file=sys.stderr)
        return 1

    try:
        result = normalise(
            args.isbn,
            xml_path,
            with_label=not args.no_label,
            convert_10_to_13=args.to13,
        )
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
