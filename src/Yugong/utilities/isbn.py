"""ISBN-10/13 validation and hyphenation using ISBN registration ranges.

The range data comes from the International ISBN Agency's ``RangeMessage.xml``
(the bundled copy lives in ``src/Yugong/resources/RangeMessage.xml``).  The parser and
the hyphenation algorithm are ported from the standalone
``ISBN-normaliser-forMGP`` project, but the wiki/HTTP/robot layers are not: in
YuGong the :mod:`src.Yugong.extensions.isbn_normalise` job supplies the pages.

Only *valid* ISBNs are hyphenated by default.  Callers that walk arbitrary page
text should treat :class:`ValueError` as "not an ISBN, leave it alone"; a caller
that needs to format an ISBN-shaped typo can pass
``validate_check_digit=False``.  Configuration and range-file problems
(missing/unreadable XML) raise their own loud errors.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from src.Yugong.utilities.path_helper import PROJECT_ROOT

#: Bundled range file.  ``settings.isbn_range_message_path`` may override it.
RANGE_MESSAGE_PATH: Path = (
    PROJECT_ROOT / "src" / "Yugong" / "resources" / "RangeMessage.xml"
)

#: GS1 lengths accepted by :func:`canonical_gs1` (GS1 General Specifications
#: Release 26.0, section 7.9.1).
GS1_LENGTHS: frozenset[int] = frozenset({8, 12, 13, 14, 17, 18})


@dataclass(frozen=True)
class Rule:
    """One registrant range inside a registration group."""

    start: int
    end: int
    registrant_length: int


@dataclass(frozen=True)
class Group:
    """One ``<Group>`` entry: the GS1 prefix, registration group and its rules."""

    gs1: str
    group: str
    rules: tuple[Rule, ...]


# ── Check digits and conversions ──────────────────────────────────────

def only_digits(text: str) -> str:
    """Strip everything that is not an ASCII digit."""
    return re.sub(r"\D", "", text)


def canonical_gs1(text: str) -> str | None:
    """Return digits from a GS1 code written with optional separators.

    ``None`` means the text is not GS1-shaped (non-digit characters other than
    spaces/hyphens) or has an unsupported length.
    """
    stripped = text.strip()
    if not stripped or re.fullmatch(r"[0-9][0-9 -]*", stripped) is None:
        return None
    digits = only_digits(stripped)
    return digits if len(digits) in GS1_LENGTHS else None


def compute_gs1_check_digit(first_digits: str) -> int:
    """Return the GS1 modulo-10 check digit for *first_digits*."""
    total = sum(
        int(digit) * (3 if index % 2 == 0 else 1)
        for index, digit in enumerate(reversed(first_digits))
    )
    return (10 - total % 10) % 10


def is_valid_gs1(text: str) -> bool:
    """Whether *text* is a GS1 code with a correct check digit."""
    digits = canonical_gs1(text)
    return (
        digits is not None
        and compute_gs1_check_digit(digits[:-1]) == int(digits[-1])
    )


def canonical_isbn10(text: str) -> str:
    """Keep digits and a trailing ``X`` check digit, upper-cased."""
    return re.sub(r"[^0-9Xx]", "", text).upper()


def compute_isbn13_check_digit(first12: str) -> int:
    """Return the ISBN-13 check digit; ISBN-13 uses the GS1 checksum."""
    return compute_gs1_check_digit(first12)


def is_valid_isbn13(digits13: str) -> bool:
    """Whether *digits13* is a valid ISBN-13 (978/979 + GS1 check digit)."""
    if (
        len(digits13) != 13
        or not digits13.isdigit()
        or not digits13.startswith(("978", "979"))
    ):
        return False
    return is_valid_gs1(digits13)


def compute_isbn10_check_digit(first9: str) -> str:
    """Return the ISBN-10 check character for the first nine digits."""
    total = sum((10 - index) * int(char) for index, char in enumerate(first9))
    value = (11 - total % 11) % 11
    return "X" if value == 10 else str(value)


def is_valid_isbn10(code10: str) -> bool:
    """Whether *code10* is a 10-character ISBN with a correct check digit."""
    if len(code10) != 10:
        return False
    if not code10[:9].isdigit():
        return False
    if not (code10[9].isdigit() or code10[9] == "X"):
        return False
    return compute_isbn10_check_digit(code10[:9]) == code10[9]


def isbn10_to_isbn13_digits(code10: str) -> str:
    """Convert a valid ISBN-10 to bare ISBN-13 digits (``978`` prefix)."""
    first12 = f"978{code10[:9]}"
    return f"{first12}{compute_isbn13_check_digit(first12)}"


def isbn_equivalence_key(raw_isbn: str) -> str | None:
    """Canonical ISBN-13 digits for semantic equality, or ``None``.

    Returns ISBN-13 digits for a valid ISBN-13, or for a valid ISBN-10 converted
    to ISBN-13 (so ``0-306-40615-2`` and ``978-0-306-40615-7`` compare equal).
    Non-ISBN strings return ``None`` instead of raising.
    """
    code13 = only_digits(raw_isbn)
    if len(code13) == 13 and is_valid_isbn13(code13):
        return code13

    code10 = canonical_isbn10(raw_isbn)
    if len(code10) == 10 and is_valid_isbn10(code10):
        return isbn10_to_isbn13_digits(code10)

    return None


def is_isbn_token(text: str) -> bool:
    """Whether the *whole* text is a single ISBN, not just containing one.

    Spaces and hyphens may separate the digits, and an ISBN-10 may end in
    ``X``.  ``"精装 9787302511625"`` is therefore not an ISBN token, while
    ``"978-7-302-51162-5"`` is.
    """
    stripped = text.strip()
    if not stripped or re.fullmatch(r"[0-9Xx][0-9Xx -]*", stripped) is None:
        return False
    if (
        len(only_digits(stripped)) == 13
        and re.fullmatch(r"[0-9][0-9 -]*", stripped) is not None
    ):
        return True
    return len(canonical_isbn10(stripped)) == 10


# ── Range file loading ────────────────────────────────────────────────

def resolve_range_message_path(value: str = "") -> Path:
    """Resolve ``settings.isbn_range_message_path``.

    An empty value selects the bundled file.  Relative paths are resolved
    against the project root (not the process working directory), so a run from
    cron or another directory behaves the same.
    """
    text = value.strip()
    if not text:
        return RANGE_MESSAGE_PATH

    path = Path(text).expanduser()
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path


def _parse_range_text(range_text: str) -> tuple[int, int]:
    start_text, end_text = range_text.split("-", 1)
    return int(start_text), int(end_text)


def _parse_groups(xml_path: Path) -> list[Group]:
    try:
        root = ET.parse(xml_path).getroot()
    except ET.ParseError as exc:
        raise ValueError(
            f"Unable to parse the ISBN range file {xml_path}: {exc}"
        ) from exc

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

            start, end = _parse_range_text(range_text)
            rules.append(
                Rule(start=start, end=end, registrant_length=registrant_length)
            )

        if rules:
            groups.append(Group(gs1=gs1, group=group, rules=tuple(rules)))

    if not groups:
        raise ValueError(
            f"The ISBN range file {xml_path} contains no usable registration groups."
        )

    # Longest registration group first, so 99901 is tried before 9.
    groups.sort(key=lambda item: len(item.group), reverse=True)
    return groups


@lru_cache(maxsize=4)
def _load_groups_cached(
    resolved_path: str, _mtime_ns: int, _size: int
) -> tuple[Group, ...]:
    return tuple(_parse_groups(Path(resolved_path)))


def load_groups(xml_path: Path | str = RANGE_MESSAGE_PATH) -> tuple[Group, ...]:
    """Load (and cache) the registration groups from an ISBN range file.

    The cache key includes the file's modification time and size, so replacing
    ``RangeMessage.xml`` takes effect without restarting the process.  A missing
    or unusable file raises instead of silently disabling normalisation.
    """
    path = Path(xml_path)
    if not path.is_file():
        raise FileNotFoundError(
            f"ISBN range file not found: {path}. Place RangeMessage.xml there or "
            "set isbn_range_message_path in settings.toml."
        )

    stat = path.stat()
    return _load_groups_cached(
        str(path.resolve()), stat.st_mtime_ns, stat.st_size
    )


# ── Hyphenation ───────────────────────────────────────────────────────

def _to_7_digit_interval(reg_pub: str) -> tuple[int, int] | None:
    """Map a registrant/publication fragment onto the 7-digit range scale."""
    if not reg_pub:
        return None

    if len(reg_pub) >= 7:
        head7 = int(reg_pub[:7])
        return head7, head7

    low = int(reg_pub) * (10 ** (7 - len(reg_pub)))
    high = low + (10 ** (7 - len(reg_pub))) - 1
    return low, high


def _match_rule(
    digits13: str, groups: tuple[Group, ...] | list[Group]
) -> tuple[Group, str, str] | None:
    """Return ``(group, registrant, publication)`` for *digits13*, if any."""
    for group in groups:
        prefix_no_hyphen = f"{group.gs1}{group.group}"
        if not digits13.startswith(prefix_no_hyphen):
            continue

        reg_pub = digits13[len(prefix_no_hyphen):12]
        interval = _to_7_digit_interval(reg_pub)
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
            return group, registrant, publication

    return None


def hyphenate_isbn13(
    digits13: str,
    groups: tuple[Group, ...] | list[Group],
    *,
    with_label: bool = False,
    validate_check_digit: bool = True,
) -> str:
    """Hyphenate an ISBN-13.

    Args:
        digits13: Exactly 13 digits.
        groups: Registration groups from :func:`load_groups`.
        with_label: Prefix the result with ``"ISBN "`` when true.
        validate_check_digit: When false, still require the 978/979 prefix and
            a matching range but do not reject a bad check digit.  Used to
            hyphenate an ISBN-shaped typo so it can be flagged in place.

    Raises:
        ValueError: If the value is not a valid ISBN-13 or no registration
            range matches it.
    """
    if not digits13.isdigit() or len(digits13) != 13:
        raise ValueError("ISBN must contain exactly 13 digits.")
    if not digits13.startswith(("978", "979")):
        raise ValueError("ISBN-13 must start with 978 or 979.")
    if validate_check_digit and not is_valid_isbn13(digits13):
        raise ValueError("Invalid ISBN-13 check digit.")

    matched = _match_rule(digits13, groups)
    if matched is None:
        raise ValueError(
            "Could not map ISBN to a registration group/range rule."
        )

    group, registrant, publication = matched
    normalised = (
        f"{group.gs1}-{group.group}-{registrant}-{publication}-{digits13[-1]}"
    )
    return f"ISBN {normalised}" if with_label else normalised


def hyphenate_isbn10(
    code10: str,
    groups: tuple[Group, ...] | list[Group],
    *,
    with_label: bool = False,
    validate_check_digit: bool = True,
) -> str:
    """Hyphenate an ISBN-10 (the check character stays as given)."""
    if validate_check_digit and not is_valid_isbn10(code10):
        raise ValueError("Invalid ISBN-10 check digit.")

    digits13 = isbn10_to_isbn13_digits(code10)
    matched = _match_rule(digits13, groups)
    if matched is None:
        raise ValueError(
            "Could not map ISBN-10 to a registration group/range rule."
        )

    group, registrant, publication = matched
    normalised = f"{group.group}-{registrant}-{publication}-{code10[-1]}"
    return f"ISBN {normalised}" if with_label else normalised


def normalise_token(
    raw_isbn: str,
    groups: tuple[Group, ...] | list[Group],
    *,
    convert_10_to_13: bool = False,
    with_label: bool = False,
) -> str:
    """Normalise one ISBN token, optionally converting ISBN-10 to ISBN-13.

    Raises:
        ValueError: If *raw_isbn* is not a valid ISBN-10/13 or cannot be mapped.
    """
    code13 = only_digits(raw_isbn)
    if len(code13) == 13:
        return hyphenate_isbn13(code13, groups, with_label=with_label)

    code10 = canonical_isbn10(raw_isbn)
    if len(code10) == 10:
        if not is_valid_isbn10(code10):
            raise ValueError("Invalid ISBN-10 check digit.")
        if convert_10_to_13:
            converted = isbn10_to_isbn13_digits(code10)
            return hyphenate_isbn13(converted, groups, with_label=with_label)
        return hyphenate_isbn10(code10, groups, with_label=with_label)

    raise ValueError("ISBN must be a valid ISBN-10 or ISBN-13.")


def normalise(
    raw_isbn: str,
    xml_path: Path | str = RANGE_MESSAGE_PATH,
    *,
    convert_10_to_13: bool = False,
    with_label: bool = False,
) -> str:
    """Load *xml_path* and normalise one ISBN (convenience wrapper)."""
    return normalise_token(
        raw_isbn,
        load_groups(xml_path),
        convert_10_to_13=convert_10_to_13,
        with_label=with_label,
    )
