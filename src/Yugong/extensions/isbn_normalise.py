"""Normalise ISBNs in ``{{ISBN}}``, ``{{ISBNT}}`` and citation templates.

Ported from the standalone ``ISBN-normaliser-forMGP`` bot.  YuGong supplies the
page list and the edit submission; this file is the per-page transformation.

The job is a no-op unless ``enable_isbn_normalise = true`` in
``settings.toml``.  When enabled it:

* hyphenates valid ISBN-10/13 values using the International ISBN Agency's
  range data;
* normalises an ``isbn=`` parameter on citation templates (case-insensitively);
* replaces ``[[Special:BookSources/…]]`` links with ``{{ISBN|…}}`` where the
  link's display text allows it, or with the same link and a corrected ISBN
  target when a display label must be preserved;
* marks ISBN-shaped values that cannot be trusted instead of silently skipping
  them: a bad check digit gets the hyphenated form plus the expected digit in a
  comment, and an unmapped registration range gets a comment saying so;
* optionally converts ISBN-10 to ISBN-13 (``isbn_convert_10_to_13``);
* optionally merges a Moegirl-style template whose parameters 1 and 2 are the
  same ISBN into ``{{ISBNT|…}}`` (``isbn_rehyphenate_equal_label``), unless
  ``overwrite_template_name = false``.

Template conventions differ between wikis, so ``isbn_template_style`` selects
how the positional parameters are read:

``qiuwen`` (default)
    ``{{ISBN|isbn1|isbn2|…|isbn9}}``: parameters 1–9 are all ISBNs, and
    ``plainlink``/``leadout``/``invalid1..9`` are named options.  ``{{ISBNT}}``
    is the same template with ``plainlink``.  Parameter 2 is never a display
    label, so two ISBNs are never merged.

``moegirl``
    ``{{ISBN|isbn|display text}}``: parameter 1 is the ISBN and parameter 2
    replaces the default display text.  This is the upstream bot's behaviour.

A missing or malformed range file raises a descriptive error instead of silently
disabling the job.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import mwparserfromhell as mph
from mwparserfromhell.nodes.extras import Parameter

from src.Yugong.core.logger import utilities_logger
from src.Yugong.core.settings import settings
from src.Yugong.core.wikitext import Wikitext
from src.Yugong.utilities.isbn import (
    Group,
    canonical_gs1,
    canonical_isbn10,
    compute_isbn10_check_digit,
    compute_isbn13_check_digit,
    hyphenate_isbn10,
    hyphenate_isbn13,
    isbn_equivalence_key,
    is_isbn_token,
    is_valid_gs1,
    is_valid_isbn10,
    is_valid_isbn13,
    load_groups,
    normalise_token,
    resolve_range_message_path,
)
from src.Yugong.utilities.mark_job_intro import intro, job

#: Namespaces that redirect to ``Special:BookSources``.
SPECIAL_NAMESPACE_ALIASES: frozenset[str] = frozenset({"special", "特殊"})

#: Localised page names of ``Special:BookSources``.  Both MoegirlPedia and
#: QiuwenPedia use ``网络书源``; the other aliases come from the upstream bot.
BOOKSOURCE_PAGE_ALIASES: frozenset[str] = frozenset(
    {"booksources", "書籍來源", "網絡書源", "網路書源", "网络书源"}
)

#: Template names handled by default, per convention.
STYLE_TEMPLATE_NAMES: dict[str, tuple[str, ...]] = {
    "qiuwen": ("ISBN", "ISBNT", "Cite book", "Citation"),
    "moegirl": ("ISBN", "ISBNT", "Cite book"),
}

#: ``{{ISBN}}``/``{{ISBNT}}``-style display templates in each convention.
DISPLAY_TEMPLATE_KEYS: frozenset[str] = frozenset({"isbn", "isbnt"})

#: Qiuwen's ``{{ISBN}}`` accepts up to nine positional ISBNs.
QIUWEN_MAX_ISBN_PARAMS: int = 9

#: An ISBN-like run inside a longer display label (``精装 9787302511625``).
_ISBN_RUN_RE = re.compile(r"[0-9][0-9 \-]*[0-9Xx]")


@dataclass
class ChangeReport:
    """Counts of each distinct change type made to one page."""

    booksource_links: int = 0  # [[Special:BookSources/…]] → {{ISBN}}
    booksource_links_removed: int = 0  # BookSources links → plain text
    gs1_links_plaintext: int = 0  # Valid non-ISBN GS1 links → plain text
    isbn_normalised: int = 0  # hyphen-only normalisation
    isbn10_converted: int = 0  # ISBN-10 → ISBN-13 conversion
    isbnt_merged: int = 0  # semantically-equal params → {{ISBNT|…}}
    #: Set when an ISBN value's own formatting changed even though the
    #: primary change was a link swap or an ISBNT merge.  Excluded from
    #: :attr:`total`, matching upstream.
    isbn_reformatted: int = 0

    @property
    def total(self) -> int:
        return (
            self.booksource_links
            + self.isbn_normalised
            + self.isbn10_converted
            + self.isbnt_merged
            + self.booksource_links_removed
        )

    def __add__(self, other: ChangeReport) -> ChangeReport:
        return ChangeReport(
            booksource_links=self.booksource_links + other.booksource_links,
            booksource_links_removed=(
                self.booksource_links_removed + other.booksource_links_removed
            ),
            gs1_links_plaintext=(
                self.gs1_links_plaintext + other.gs1_links_plaintext
            ),
            isbn_normalised=self.isbn_normalised + other.isbn_normalised,
            isbn10_converted=self.isbn10_converted + other.isbn10_converted,
            isbnt_merged=self.isbnt_merged + other.isbnt_merged,
            isbn_reformatted=self.isbn_reformatted + other.isbn_reformatted,
        )


@dataclass(frozen=True)
class IsbnConfig:
    """The settings and range data needed for one job invocation."""

    groups: tuple[Group, ...]
    style: str
    convert_10_to_13: bool
    rehyphenate_equal_label: bool
    template_names: frozenset[str]
    display_templates: frozenset[str]
    preferred_names: dict[str, str]
    range_message_path: Path


# ── Small helpers ─────────────────────────────────────────────────────

def canonical_title_fragment(value: str) -> str:
    """Case-fold a title fragment and drop spaces/underscores.

    MediaWiki treats ``Cite book``, ``cite_book`` and ``CITEBOOK`` as the same
    title, so template matching uses the same normalisation.
    """
    return "".join(
        char for char in value.strip().casefold()
        if not char.isspace() and char != "_"
    )


def _try_normalise(raw_value: str, config: IsbnConfig) -> str | None:
    """Return the hyphenated value, or ``None`` when *raw_value* is no ISBN."""
    try:
        return normalise_token(
            raw_value,
            config.groups,
            convert_10_to_13=config.convert_10_to_13,
        )
    except ValueError:
        return None


def _normalise_if_isbn(raw_value: str, config: IsbnConfig) -> str | None:
    """Like :func:`_try_normalise`, but only for a valid ISBN equivalence key."""
    if isbn_equivalence_key(raw_value) is None:
        return None
    return _try_normalise(raw_value, config)


def _normalise_label_isbn(label: str, config: IsbnConfig) -> str:
    """Hyphenate the ISBN inside a display label and keep the other text.

    A display label may carry text beside its ISBN, such as a binding note
    (``精装 9787302511625``).  Only the ISBN run is normalised, so the note
    stays on the page.  A label with no valid ISBN is returned unchanged.
    """
    text = label.strip()
    for match in reversed(list(_ISBN_RUN_RE.finditer(text))):
        normalised = _normalise_if_isbn(match.group(0), config)
        if normalised is not None:
            text = f"{text[:match.start()]}{normalised}{text[match.end():]}"
    return text


def _label_isbn_core(label: str) -> str:
    """Return the label without a leading ``ISBN`` prefix, when it has one."""
    return _split_isbn_prefixed_label(label) or label.strip()


def _is_isbn13_code(code13: str | None) -> bool:
    return (
        code13 is not None
        and len(code13) == 13
        and code13.startswith(("978", "979"))
    )


def _is_isbn_shaped(raw_value: str) -> bool:
    """Whether the value looks like an ISBN even if its check digit is bad."""
    code13 = canonical_gs1(raw_value)
    if code13 is not None and len(code13) == 13:
        return code13.startswith(("978", "979"))
    return len(canonical_isbn10(raw_value)) == 10


def _has_valid_isbn_check_digit(raw_value: str) -> bool:
    code13 = canonical_gs1(raw_value)
    if code13 is not None and _is_isbn13_code(code13):
        return is_valid_isbn13(code13)
    code10 = canonical_isbn10(raw_value)
    return len(code10) == 10 and is_valid_isbn10(code10)


def _is_valid_ean13(raw_value: str) -> bool:
    digits = canonical_gs1(raw_value)
    return (
        digits is not None
        and len(digits) == 13
        and is_valid_gs1(raw_value)
    )


def _try_hyphenate_invalid_isbn(
    raw_value: str, config: IsbnConfig
) -> tuple[str, str] | None:
    """Hyphenate an ISBN-shaped value without trusting its check digit.

    Returns the formatted value and the check digit calculated from its body.
    A missing ISBN range mapping still makes the value unusable here.
    """
    code13 = canonical_gs1(raw_value)
    if code13 is not None and _is_isbn13_code(code13):
        try:
            formatted = hyphenate_isbn13(
                code13,
                config.groups,
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
            config.groups,
            validate_check_digit=False,
        )
    except ValueError:
        return None
    expected = compute_isbn10_check_digit(code10[:9])
    return formatted, expected


def _comment_safe(text: str) -> str:
    """Keep untrusted text from closing the HTML comment early."""
    return text.replace("--", "- -").replace(">", "&gt;")


def _add_invalid_check_digit_note(formatted: str, expected: str) -> str:
    return (
        f"{formatted}<!-- 可匹配组区号与出版者号，但校验未通过。"
        f"可能是手动转换 ISBN-10/13 错误。请勿手动转换。"
        f"若存在，校验位为{expected} -->"
    )


def _add_unmapped_isbn_note(raw_value: str) -> str:
    return (
        f"{raw_value}<!-- 符合 ISBN 格式，但组区号与出版者号无法匹配 -->"
    )


def _add_invalid_unmapped_isbn_note(raw_value: str) -> str:
    return (
        f"{raw_value}<!-- ISBN 校验未通过，且组区号与出版者号无法匹配。"
        "这是什么？ -->"
    )


def _add_removed_booksource_note(
    display_text: str, prefix: str, target: str
) -> str:
    return (
        f"{display_text}<!-- 此处原使用[[{_comment_safe(prefix.lstrip(':'))}]]，"
        f"链接目标：{_comment_safe(target)} -->"
    )


def _semantically_equal(code: str, label: str | None) -> bool:
    """Whether *label* is the same ISBN as *code*.

    Invalid ISBNs cannot produce an equivalence key, but an identical
    ISBN-shaped value should still not be duplicated as a display label.
    """
    if label is None or not is_isbn_token(label):
        return False

    key1 = isbn_equivalence_key(code)
    key2 = isbn_equivalence_key(label)
    if key1 is not None and key1 == key2:
        return True

    code13 = canonical_gs1(code)
    label13 = canonical_gs1(label)
    if _is_isbn13_code(code13) and _is_isbn13_code(label13):
        return code13 == label13

    code10 = canonical_isbn10(code)
    label10 = canonical_isbn10(label)
    return len(code10) == 10 and len(label10) == 10 and code10 == label10


def _param_by_name(template: mph.wikicode.Template, target: str) -> Parameter | None:
    wanted = target.strip().casefold()
    if not wanted:
        return None
    for param in template.params:
        if str(param.name).strip().casefold() == wanted:
            return param
    return None


def _template_key(template: mph.wikicode.Template) -> str:
    return canonical_title_fragment(str(template.name))


def _get_label_value(
    template: mph.wikicode.Template, config: IsbnConfig
) -> str | None:
    """Return the normalised parameter 2, or ``None`` when it is empty."""
    if not template.has("2"):
        return None
    label = str(template.get("2").value).strip()
    if not label:
        return None
    return _normalise_label_isbn(label, config)


def _set_label(template: mph.wikicode.Template, label: str | None) -> None:
    if label is None:
        if template.has("2"):
            template.remove("2")
        return

    if template.has("2"):
        template.get("2").value = label
    else:
        # Numeric names are rendered positionally (``showkey`` defaults to None),
        # so ``{{ISBN|code}}`` becomes ``{{ISBN|code|label}}``, not ``|2=``.
        template.add("2", label)


def _build_isbn_template(
    template_name: str, code_value: str, label_value: str | None = None
) -> mph.nodes.Template:
    template = mph.nodes.Template(template_name)
    template.add("1", code_value)
    if label_value is not None:
        template.add("2", label_value)
    return template


def _preferred_isbn_template_name(config: IsbnConfig) -> str:
    return config.preferred_names.get(
        "isbn", next(iter(config.preferred_names.values()), "ISBN")
    )


def _preferred_plain_isbn_template_name(config: IsbnConfig) -> str:
    """The no-prefix template (``ISBNT``), falling back to ``ISBN``."""
    return config.preferred_names.get("isbnt", _preferred_isbn_template_name(config))


def _parse_booksource_title(title: str) -> tuple[str, str] | None:
    """Split a BookSources title into ``(prefix, isbn)``.

    ``prefix`` keeps a leading colon (which changes link semantics) and the
    namespace/page spelling the page actually used, so a rebuilt link and the
    explanatory comment both refer to the same localised name.
    """
    title_text = title.strip()
    if not title_text:
        return None

    leading_colon = title_text.startswith(":")
    if leading_colon:
        title_text = title_text[1:].strip()

    if "/" not in title_text:
        return None

    prefix_text, suffix_text = title_text.split("/", 1)
    if ":" not in prefix_text:
        return None

    namespace_raw, page_raw = prefix_text.split(":", 1)
    namespace = canonical_title_fragment(namespace_raw)
    page_name = canonical_title_fragment(page_raw)
    if namespace not in SPECIAL_NAMESPACE_ALIASES:
        return None
    if page_name not in BOOKSOURCE_PAGE_ALIASES:
        return None

    isbn_text = suffix_text.strip()
    if not isbn_text:
        return None

    prefix = f"{':' if leading_colon else ''}{prefix_text.strip()}"
    return prefix, isbn_text


def _extract_booksource_isbn(title: str) -> str | None:
    """Return the ISBN from a ``Special:BookSources/<isbn>`` link title."""
    parsed = _parse_booksource_title(title)
    return parsed[1] if parsed is not None else None


def _split_isbn_prefixed_label(label: str) -> str | None:
    """Extract the ISBN from a label such as ``ISBN 978-7-302-51162-5``."""
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


def _booksource_display_text(wikilink: mph.wikicode.Wikilink, target: str) -> str:
    return (
        str(wikilink.text).strip()
        if wikilink.text is not None
        else target.strip()
    )


def _build_non_isbn_booksource_replacement(
    wikilink: mph.wikicode.Wikilink, prefix: str, raw_value: str
) -> tuple[str, str | None]:
    """Replace a non-ISBN BookSources link with its display text.

    A valid non-ISBN EAN-13 target is left alone: it is a legitimate barcode
    lookup rather than an ISBN that needs fixing.
    """
    display_text = _booksource_display_text(wikilink, raw_value)
    if not display_text or _is_valid_ean13(raw_value):
        return "", None
    category = "gs1" if is_valid_gs1(raw_value) else None
    return (
        _add_removed_booksource_note(display_text, prefix, raw_value.strip()),
        category,
    )


def _build_booksource_template_value(
    raw_value: str, config: IsbnConfig
) -> tuple[str, bool, bool]:
    """Build parameter 1 for a BookSources link.

    Returns ``(value, is_isbn, reformatted)``.  ``is_isbn`` distinguishes an
    ISBN replacement (possibly with a comment) from a non-ISBN target.
    """
    normalised = _normalise_if_isbn(raw_value, config)
    if normalised is not None:
        return normalised, True, normalised != raw_value.strip()

    if not _is_isbn_shaped(raw_value):
        return "", False, False

    invalid_isbn = _try_hyphenate_invalid_isbn(raw_value, config)
    if invalid_isbn is not None:
        formatted, expected = invalid_isbn
        return _add_invalid_check_digit_note(formatted, expected), True, True

    if _has_valid_isbn_check_digit(raw_value):
        return _add_unmapped_isbn_note(raw_value.strip()), True, False
    return _add_invalid_unmapped_isbn_note(raw_value.strip()), True, False


def _build_moegirl_booksource_replacement(
    wikilink: mph.wikicode.Wikilink,
    raw_value: str,
    config: IsbnConfig,
) -> tuple[str, bool, str | None, bool]:
    """Upstream behaviour: label is parameter 2, ISBN-only labels are dropped."""
    template_value, is_isbn, reformatted = _build_booksource_template_value(
        raw_value, config
    )
    if not is_isbn:
        return "", False, None, False

    label_raw = _booksource_display_text(wikilink, "")
    display_label: str | None = None
    if label_raw:
        display_label = _normalise_label_isbn(label_raw, config)
        core = _label_isbn_core(display_label)
        if is_isbn_token(core) and _semantically_equal(raw_value, core):
            # The label holds nothing but the ISBN, so the template's default
            # link text already shows it.  Drop the redundant label.
            display_label = None
        else:
            reformatted = reformatted or display_label != label_raw.strip()

    template_node = _build_isbn_template(
        _preferred_isbn_template_name(config), template_value, display_label
    )
    return str(template_node), False, None, reformatted


def _build_qiuwen_booksource_replacement(
    wikilink: mph.wikicode.Wikilink,
    prefix: str,
    raw_value: str,
    config: IsbnConfig,
) -> tuple[str, bool, str | None, bool]:
    """Qiuwen behaviour.

    ``{{ISBN}}`` has no display-text parameter (parameters 1–9 are ISBNs), so
    a link with a custom label cannot be converted faithfully.  Such a link is
    kept and only its ISBN target is normalised.
    """
    template_value, is_isbn, reformatted = _build_booksource_template_value(
        raw_value, config
    )
    if not is_isbn:
        replacement, category = _build_non_isbn_booksource_replacement(
            wikilink, prefix, raw_value
        )
        if not replacement:
            return "", False, None, False
        return replacement, True, category, False

    label_raw = _booksource_display_text(wikilink, "")
    if not label_raw:
        template_node = _build_isbn_template(
            _preferred_isbn_template_name(config), template_value
        )
        return str(template_node), False, None, reformatted

    core = _label_isbn_core(label_raw)
    if is_isbn_token(core) and _semantically_equal(raw_value, core):
        # Keep the original "ISBN " prefix decision: a bare number becomes
        # {{ISBNT}} (plain link), an "ISBN …" label becomes {{ISBN}}.
        has_prefix = _split_isbn_prefixed_label(label_raw) is not None
        template_name = (
            _preferred_isbn_template_name(config)
            if has_prefix
            else _preferred_plain_isbn_template_name(config)
        )
        template_node = _build_isbn_template(template_name, template_value)
        return str(template_node), False, None, reformatted

    # Custom display text: preserve the link and normalise only its target.
    normalised_target = _normalise_if_isbn(raw_value, config)
    if normalised_target is None:
        # Invalid ISBN-shaped targets keep the link; the wiki's own ISBN
        # module/error categories handle them better than a rewritten link.
        return "", False, None, False
    replacement = f"[[{prefix}/{normalised_target}|{label_raw}]]"
    return (
        replacement,
        False,
        None,
        normalised_target != raw_value.strip(),
    )


def _build_booksource_replacement(
    wikilink: mph.wikicode.Wikilink, config: IsbnConfig
) -> tuple[str, bool, str | None, bool]:
    """Build the replacement for one BookSources link.

    Returns ``(replacement, removed, gs1_category, reformatted)``.  An empty
    replacement means "leave this link alone".
    """
    parsed = _parse_booksource_title(str(wikilink.title))
    if parsed is None:
        return "", False, None, False
    prefix, raw_value = parsed

    if config.style == "qiuwen":
        return _build_qiuwen_booksource_replacement(
            wikilink, prefix, raw_value, config
        )
    return _build_moegirl_booksource_replacement(wikilink, raw_value, config)


# ── Transformation sub-routines ───────────────────────────────────────

def _normalise_named_isbn_parameters(
    code: mph.wikicode.Wikicode, config: IsbnConfig
) -> ChangeReport:
    """Normalise ``isbn=`` parameters on citation templates."""
    report = ChangeReport()
    templates = code.filter_templates(
        matches=lambda item: _template_key(item) in config.template_names
    )

    for template in list(templates):
        isbn_param = _param_by_name(template, "isbn")
        if isbn_param is None:
            continue

        raw_value = str(isbn_param.value).strip()
        if not raw_value:
            continue

        normalised = _normalise_if_isbn(raw_value, config)
        if normalised is None or normalised == raw_value:
            continue

        isbn_param.value = normalised
        if settings.overwrite_para_name and str(isbn_param.name).strip() != "isbn":
            isbn_param.name = "isbn"

        if config.convert_10_to_13 and _is_valid_isbn10_input(raw_value):
            report.isbn10_converted += 1
        else:
            report.isbn_normalised += 1

    return report


def _replace_booksource_links(
    code: mph.wikicode.Wikicode, config: IsbnConfig
) -> ChangeReport:
    """Replace or clean up ``[[Special:BookSources/…]]`` links."""
    report = ChangeReport()

    for wikilink in list(code.filter_wikilinks()):
        replacement, removed, gs1_category, reformatted = (
            _build_booksource_replacement(wikilink, config)
        )
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


def _is_valid_isbn10_input(raw: str) -> bool:
    """Whether *raw* is a valid ISBN-10 before any conversion."""
    code10 = canonical_isbn10(raw)
    return len(code10) == 10 and is_valid_isbn10(code10)


def _count_normalised(
    report: ChangeReport, raw_value: str, config: IsbnConfig
) -> None:
    if config.convert_10_to_13 and _is_valid_isbn10_input(raw_value):
        report.isbn10_converted += 1
    else:
        report.isbn_normalised += 1


def _normalise_parameter(
    template: mph.wikicode.Template,
    name: str,
    config: IsbnConfig,
    report: ChangeReport,
) -> None:
    """Normalise one positional parameter in place, if its value is an ISBN."""
    if not template.has(name):
        return
    param = template.get(name)
    raw_value = str(param.value).strip()
    normalised = _try_normalise(raw_value, config)
    if normalised is None or normalised == raw_value:
        return
    param.value = normalised
    _count_normalised(report, raw_value, config)


def _normalise_qiuwen_display_template(
    template: mph.wikicode.Template, config: IsbnConfig
) -> ChangeReport:
    """Normalise parameters 1–9 of Qiuwen's list-style ``{{ISBN}}``."""
    report = ChangeReport()
    for index in range(1, QIUWEN_MAX_ISBN_PARAMS + 1):
        _normalise_parameter(template, str(index), config, report)
    return report


def _normalise_plain_template(
    template: mph.wikicode.Template, config: IsbnConfig
) -> ChangeReport:
    """Normalise parameter 1 of a non-display template (no label handling)."""
    report = ChangeReport()
    _normalise_parameter(template, "1", config, report)
    return report


def _normalise_moegirl_display_template(
    template: mph.wikicode.Template, config: IsbnConfig
) -> ChangeReport:
    """Normalise Moegirl's ``{{ISBN|isbn|display text}}`` and its ISBNT merge."""
    report = ChangeReport()
    if not template.has("1"):
        return report

    param1 = template.get("1")
    code_str = str(param1.value).strip()
    normalised_1 = _try_normalise(code_str, config)
    if normalised_1 is None:
        return report

    output_label = _get_label_value(template, config)
    equal_isbn = _semantically_equal(code_str, output_label)

    if (
        config.rehyphenate_equal_label
        and equal_isbn
        and settings.overwrite_template_name
    ):
        isbnt_name = config.preferred_names.get("isbnt")
        if isbnt_name is not None:
            template.name = isbnt_name
        if normalised_1 != code_str:
            report.isbn_reformatted += 1
        param1.value = normalised_1
        if template.has("2"):
            template.remove("2")
        report.isbnt_merged += 1
        return report

    original_label = (
        str(template.get("2").value).strip() if template.has("2") else None
    )
    if normalised_1 == code_str and output_label == original_label:
        return report

    param1.value = normalised_1
    _set_label(template, output_label)
    _count_normalised(report, code_str, config)
    return report


def _normalise_positional_parameters(
    code: mph.wikicode.Wikicode, config: IsbnConfig
) -> ChangeReport:
    """Normalise positional ISBN parameters.

    Qiuwen's convention makes parameters 1–9 all ISBNs, so every configured
    template can be checked: a value that is not a valid ISBN is left alone,
    which keeps citation templates' author/title positions safe.  Moegirl only
    defines parameter 1 as the ISBN (parameter 2 is a label), so the
    label-aware pass stays limited to ``ISBN``/``ISBNT``.
    """
    report = ChangeReport()
    templates = code.filter_templates(
        matches=lambda item: _template_key(item) in config.template_names
    )
    for template in list(templates):
        if config.style == "qiuwen":
            report += _normalise_qiuwen_display_template(template, config)
        elif _template_key(template) in config.display_templates:
            report += _normalise_moegirl_display_template(template, config)
        else:
            # A configured citation/localised template: parameter 1 is only
            # rewritten when it is a valid ISBN, so author/title positions are
            # safe.
            report += _normalise_plain_template(template, config)
    return report


# ── Configuration and job ─────────────────────────────────────────────

def _style_template_names(style: str) -> tuple[str, ...]:
    try:
        return STYLE_TEMPLATE_NAMES[style]
    except KeyError:
        raise ValueError(
            f"settings.toml: isbn_template_style {style!r} is not supported; "
            f"use one of {sorted(STYLE_TEMPLATE_NAMES)}."
        ) from None


def _build_config() -> IsbnConfig:
    """Validate the ISBN settings and load the range file."""
    style = str(settings.isbn_template_style).strip().casefold() or "qiuwen"
    default_names = _style_template_names(style)

    raw_names = settings.isbn_template_names
    if raw_names is None:
        raw_names = []
    if not isinstance(raw_names, list):
        raise ValueError(
            "settings.toml: isbn_template_names must be a list of template "
            "names (leave it empty to use the defaults for the selected style)."
        )
    names = raw_names or list(default_names)

    preferred_names: dict[str, str] = {}
    for name in names:
        if not isinstance(name, str) or not name.strip():
            raise ValueError(
                "settings.toml: every entry of isbn_template_names must be a "
                "non-empty string."
            )
        key = canonical_title_fragment(name)
        if not key:
            raise ValueError(
                f"settings.toml: isbn_template_names entry {name!r} has no "
                "usable characters."
            )
        preferred_names.setdefault(key, name.strip())

    range_path = resolve_range_message_path(settings.isbn_range_message_path)
    return IsbnConfig(
        groups=load_groups(range_path),
        style=style,
        convert_10_to_13=bool(settings.isbn_convert_10_to_13),
        rehyphenate_equal_label=bool(settings.isbn_rehyphenate_equal_label),
        template_names=frozenset(preferred_names),
        display_templates=frozenset(
            key for key in preferred_names if key in DISPLAY_TEMPLATE_KEYS
        ),
        preferred_names=preferred_names,
        range_message_path=range_path,
    )


@job
def isbn_normalise_job(wikitext: Wikitext) -> None:
    """Normalise ISBN template parameters and BookSources links."""
    if not settings.enable_isbn_normalise:
        return

    config = _build_config()
    code = wikitext.wikitext

    report = ChangeReport()
    report += _normalise_named_isbn_parameters(code, config)
    report += _replace_booksource_links(code, config)
    report += _normalise_positional_parameters(code, config)

    if report.total or report.isbn_reformatted:
        utilities_logger.info(
            f"{wikitext.title}: {report.total} ISBN change(s) "
            f"[{config.style}] "
            f"(booksource={report.booksource_links}, "
            f"removed={report.booksource_links_removed}, "
            f"gs1={report.gs1_links_plaintext}, "
            f"normalised={report.isbn_normalised}, "
            f"converted={report.isbn10_converted}, "
            f"isbnt={report.isbnt_merged}, "
            f"reformatted={report.isbn_reformatted})"
        )


@intro
def isbn_normalise_intro() -> str:
    return (
        "ISBN normaliser: hyphenate ISBN-10/13 in "
        "{{ISBN}}/{{ISBNT}}/citation templates, clean up Special:BookSources "
        "links, optionally convert to ISBN-13 or merge equal Moegirl labels "
        f"(style={settings.isbn_template_style}, "
        f"enabled={settings.enable_isbn_normalise})"
    )
