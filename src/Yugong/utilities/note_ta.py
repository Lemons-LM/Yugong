"""Parsing of the target wiki's ``{{NoteTA}}`` and CGroup conversion data.

Qiuwen Baike (like Wikipedia) lets an article declare cross-strait terminology
differences with ``{{NoteTA}}``::

    {{NoteTA
    | G1 = Unit          # public conversion group
    | 1  = zh-cn:米; zh-tw:公尺;
    | T  = zh-cn:米; zh-tw:公尺;
    }}

A conversion group lives either in ``Module:CGroup/<name>`` (a Lua data table,
preferred by ``Module:NoteTA``) or in ``Template:CGroup/<name>`` (``CItem`` /
``CItemHidden`` templates).  This module only *parses* that data; fetching and
caching live in :mod:`src.Yugong.utilities.cgroup_cache`.

Nothing here invents terminology: the replacements are exactly the rules the
wiki itself declares.  ``zh-cn`` is used as the canonical target (Mainland
terminology), with ``zh-hans`` and ``zh`` as fallbacks, mirroring MediaWiki's
variant fallback order.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

import mwparserfromhell as mph

#: Variant order used when choosing the canonical category name.
TARGET_LANGS: tuple[str, ...] = ("zh-cn", "zh-hans", "zh")

#: Language aliases accepted by ``Module:CGroup``.
_LANG_ALIASES: dict[str, str] = {
    "zh": "zh",
    "hans": "zh-hans",
    "hant": "zh-hant",
    "cn": "zh-cn",
    "sg": "zh-sg",
    "my": "zh-my",
    "tw": "zh-tw",
    "hk": "zh-hk",
    "mo": "zh-mo",
}

_ZH_LANG_RE = re.compile(r"^zh(?:-[a-z0-9]+)*$", re.IGNORECASE)
_RULE_PART_RE = re.compile(
    r"^(?:(?P<source>.+?)\s*=>\s*)?"
    r"(?P<lang>[a-z]{2,3}(?:-[a-z0-9]+)*)\s*:\s*"
    r"(?P<text>.+)$",
    re.IGNORECASE,
)
_HIDDEN_RULE_RE = re.compile(r"-\{H\|(.*?)\}-", re.IGNORECASE | re.DOTALL)
_RULE_HINT_RE = re.compile(r"(?:\bzh(?:-[a-z0-9]+)?\s*:)|(?:=>\s*zh)", re.IGNORECASE)

#: Some groups are thin wrappers such as
#: ``return require('Module:CGroup/Lifesciences');`` or use ``mw.loadData``.
_MODULE_REF_RE = re.compile(
    r"(?:require|loadData)\s*\(\s*(['\"])Module:CGroup/([^'\"]+)\1\s*\)",
    re.IGNORECASE,
)


@dataclass
class NoteTAConfig:
    """The conversion data declared by one page's ``{{NoteTA}}``."""

    local_rules: list[str] = field(default_factory=list)
    title_rules: str = ""
    groups: list[str] = field(default_factory=list)

    def is_empty(self) -> bool:
        return not (self.local_rules or self.title_rules or self.groups)


# ── Page-level NoteTA ─────────────────────────────────────────────────


def parse_note_ta(page_text: str) -> NoteTAConfig:
    """Extract inline rules, title rules and group names from *page_text*.

    Multiple ``{{NoteTA}}`` templates and ``-{H|...}-`` hidden rules are
    merged.  ``{{noteTA}}``/``{{NoteTA}}`` are treated the same, as on the wiki.
    """
    config = NoteTAConfig()

    try:
        code = mph.parse(page_text)
    except Exception:  # noqa: BLE001 - malformed page text must not crash a run
        code = None

    if code is not None:
        for template in code.filter_templates(recursive=True):
            if str(template.name).strip().lower() != "noteta":
                continue
            for param in template.params:
                name = str(param.name).strip()
                value = str(param.value).strip()
                if not value:
                    continue
                lowered = name.lower()
                if lowered == "t":
                    config.title_rules = _join_rule_strings(config.title_rules, value)
                elif lowered.startswith("g") and lowered[1:].isdigit():
                    if value not in config.groups:
                        config.groups.append(value)
                elif name.isdigit() and 1 <= int(name) <= 30:
                    config.local_rules.append(value)

    for match in _HIDDEN_RULE_RE.finditer(page_text):
        rule = match.group(1).strip()
        if rule:
            config.local_rules.append(rule)

    return config


def _join_rule_strings(first: str, second: str) -> str:
    if not first:
        return second
    return f"{first.rstrip(';')};{second.lstrip(';')}"


# ── CGroup data: template form ────────────────────────────────────────


def parse_cgroup_wikitext(text: str) -> tuple[list[str], list[str]]:
    """Return ``(rules, imports)`` declared by a ``Template:CGroup/*`` page.

    Template-based groups do not use ``import``; the second element is always
    empty and exists so callers can treat both CGroup forms identically.
    """
    rules: list[str] = []
    try:
        code = mph.parse(text)
    except Exception:  # noqa: BLE001
        return rules, []

    for template in code.filter_templates(recursive=True):
        name = str(template.name).strip().lower()
        if name not in {"citem", "citemhidden"}:
            continue
        rule = _template_rule(template)
        if rule and _looks_like_rule(rule):
            rules.append(rule)
    return _dedupe(rules), []


def _template_rule(template: mph.wikicode.Template) -> str | None:
    """The rule is ``|1=...`` or the first anonymous parameter."""
    if template.has("1"):
        return str(template.get("1").value).strip()
    for param in template.params:
        if not param.showkey:
            return str(param.value).strip()
    return None


# ── CGroup data: Lua module form ──────────────────────────────────────

_LONG_STRING_RE = re.compile(r"\[(=*)\[(.*?)\]\1\]", re.DOTALL)


@dataclass
class _LuaTable:
    items: list[Any] = field(default_factory=list)
    fields: dict[str, Any] = field(default_factory=dict)


@dataclass
class _LuaCall:
    name: str
    args: list[Any] = field(default_factory=list)


class _LuaParser:
    """A tiny parser for the data subset used by ``Module:CGroup/*``.

    It understands strings (including long strings), comments, tables
    (positional and ``key = value`` entries), and calls such as
    ``Item('original', 'rule')``.  Function bodies and arbitrary Lua
    expressions are skipped; the last top-level ``return { ... }`` wins.
    """

    def __init__(self, source: str) -> None:
        self.tokens = self._tokenize(source)
        self.pos = 0

    # -- tokenizer -------------------------------------------------
    @classmethod
    def _tokenize(cls, source: str) -> list[tuple[str, str]]:
        tokens: list[tuple[str, str]] = []
        i = 0
        length = len(source)

        while i < length:
            char = source[i]

            if char.isspace():
                i += 1
                continue

            if source.startswith("--", i):
                long_match = _LONG_STRING_RE.match(source, i + 2) if source.startswith(
                    "--[", i
                ) else None
                if long_match:
                    i = long_match.end()
                else:
                    newline = source.find("\n", i)
                    i = length if newline == -1 else newline + 1
                continue

            long_match = _LONG_STRING_RE.match(source, i)
            if long_match:
                tokens.append(("string", long_match.group(2)))
                i = long_match.end()
                continue

            if char in ("'", '"'):
                value, i = cls._read_quoted(source, i)
                tokens.append(("string", value))
                continue

            if char.isalpha() or char == "_":
                start = i
                while i < length and (source[i].isalnum() or source[i] == "_"):
                    i += 1
                tokens.append(("name", source[start:i]))
                continue

            if char.isdigit():
                start = i
                while i < length and (source[i].isdigit() or source[i] in ".xXabcdefABCDEF"):
                    i += 1
                tokens.append(("number", source[start:i]))
                continue

            tokens.append(("symbol", char))
            i += 1

        return tokens

    @staticmethod
    def _read_quoted(source: str, start: int) -> tuple[str, int]:
        quote = source[start]
        i = start + 1
        parts: list[str] = []
        escapes = {
            "n": "\n",
            "r": "\r",
            "t": "\t",
            "\\": "\\",
            "'": "'",
            '"': '"',
        }
        while i < len(source):
            char = source[i]
            if char == "\\" and i + 1 < len(source):
                parts.append(escapes.get(source[i + 1], source[i + 1]))
                i += 2
                continue
            if char == quote:
                return "".join(parts), i + 1
            parts.append(char)
            i += 1
        return "".join(parts), i

    # -- parser ----------------------------------------------------
    def parse_return_table(self) -> _LuaTable | None:
        candidates: list[_LuaTable] = []
        while self.pos < len(self.tokens):
            kind, value = self.tokens[self.pos]
            if kind == "name" and value == "return":
                self.pos += 1
                try:
                    parsed = self._parse_value()
                except (IndexError, ValueError):
                    continue
                if isinstance(parsed, _LuaTable):
                    candidates.append(parsed)
            else:
                self.pos += 1
        for table in reversed(candidates):
            if "content" in table.fields:
                return table
        return candidates[-1] if candidates else None

    def _parse_value(self) -> Any:
        kind, value = self.tokens[self.pos]
        if kind == "string":
            self.pos += 1
            return value
        if kind == "number":
            self.pos += 1
            return value
        if kind == "symbol" and value == "{":
            return self._parse_table()
        if kind == "name":
            self.pos += 1
            if value in ("true", "false"):
                return value == "true"
            if self._accept("("):
                args: list[Any] = []
                while not self._accept(")"):
                    if self.pos >= len(self.tokens):
                        break
                    args.append(self._parse_value())
                    self._accept(",")
                return _LuaCall(value, args)
            return value
        self.pos += 1
        return None

    def _parse_table(self) -> _LuaTable:
        self._expect("{")
        table = _LuaTable()
        while self.pos < len(self.tokens) and not self._accept("}"):
            if self._accept(",") or self._accept(";"):
                continue

            # [expr] = value, where the key is usually a string.
            if self._accept("["):
                key = self._parse_value()
                self._expect("]")
                self._expect("=")
                table.fields[str(key)] = self._parse_value()
                continue

            if (
                self.tokens[self.pos][0] in ("name", "string")
                and self.pos + 1 < len(self.tokens)
                and self.tokens[self.pos + 1] == ("symbol", "=")
            ):
                key = self.tokens[self.pos][1]
                self.pos += 2
                table.fields[key] = self._parse_value()
                continue

            table.items.append(self._parse_value())
        return table

    def _accept(self, symbol: str) -> bool:
        if self.pos < len(self.tokens) and self.tokens[self.pos] == ("symbol", symbol):
            self.pos += 1
            return True
        return False

    def _expect(self, symbol: str) -> None:
        if not self._accept(symbol):
            raise ValueError(f"expected {symbol!r}")


def parse_cgroup_lua(text: str) -> tuple[list[str], list[str]]:
    """Return ``(rules, imports)`` declared by a ``Module:CGroup/*`` page."""
    rules: list[str] = []
    imports: list[str] = []

    try:
        table = _LuaParser(text).parse_return_table()
    except Exception:  # noqa: BLE001 - fall back to string extraction
        table = None

    # Follow thin wrappers before/alongside the parsed table.  ``core`` is the
    # helper module (``p.Item``); it is not a conversion group.
    imports.extend(
        match.group(2)
        for match in _MODULE_REF_RE.finditer(text)
        if match.group(2).strip().lower() != "core"
    )

    if table is not None:
        _walk_lua(table, rules, imports)
    if not rules:
        rules.extend(_fallback_rules(text))
    if not imports:
        imports.extend(_fallback_imports(text))

    return _dedupe(rules), _dedupe(imports)


def _walk_lua(node: Any, rules: list[str], imports: list[str]) -> None:
    if isinstance(node, _LuaTable):
        lang_pairs = {
            key: value
            for key, value in node.fields.items()
            if _canonical_lang(key) and isinstance(value, str) and value
        }
        if lang_pairs:
            rules.append(
                ";".join(f"{_canonical_lang(key)}:{value}" for key, value in lang_pairs.items())
            )

        rule = node.fields.get("rule")
        if isinstance(rule, str) and _looks_like_rule(rule):
            rules.append(rule)

        imported = node.fields.get("import")
        if isinstance(imported, str) and imported.strip():
            imports.append(imported.strip())
        if str(node.fields.get("type", "")).lower() == "import":
            name = node.fields.get("name")
            if isinstance(name, str) and name.strip():
                imports.append(name.strip())

        for key, value in node.fields.items():
            if key in {"rule", "import", "name", "type", "original", "display", "desc", "description"}:
                continue
            if _canonical_lang(key):
                continue
            _walk_lua(value, rules, imports)

        for item in node.items:
            _walk_lua(item, rules, imports)

    elif isinstance(node, _LuaCall):
        if node.name.lower() in {"item", "citem"}:
            for argument in node.args:
                if isinstance(argument, str) and _looks_like_rule(argument):
                    rules.append(argument)
        for argument in node.args:
            _walk_lua(argument, rules, imports)

    elif isinstance(node, list):
        for item in node:
            _walk_lua(item, rules, imports)

    elif isinstance(node, str) and _looks_like_rule(node):
        rules.append(node)


def _fallback_rules(text: str) -> list[str]:
    """Last-resort extraction when the mini parser cannot read the module."""
    rules: list[str] = []
    for match in re.finditer(r"(['\"])((?:\\.|(?!\1).)*)\1", text, re.DOTALL):
        candidate = match.group(2)
        if _looks_like_rule(candidate):
            rules.append(candidate)
    return rules


def _fallback_imports(text: str) -> list[str]:
    imports: list[str] = []
    for match in re.finditer(
        r"\bimport\s*=\s*(['\"])([^'\"]+)\1"
        r"|\btype\s*=\s*(['\"])import\3[^}]*?\bname\s*=\s*(['\"])([^'\"]+)\4",
        text,
        re.DOTALL,
    ):
        name = match.group(2) or match.group(5)
        if name:
            imports.append(name)
    return imports


# ── Rule semantics ────────────────────────────────────────────────────


def _looks_like_rule(text: str) -> bool:
    return bool(_RULE_HINT_RE.search(text))


def _canonical_lang(lang: str) -> str:
    lowered = str(lang).strip().lower()
    if lowered in _LANG_ALIASES:
        return _LANG_ALIASES[lowered]
    return lowered if _ZH_LANG_RE.fullmatch(lowered) else ""


def _split_rule(rule: str) -> list[str]:
    return [part.strip() for part in re.split(r";\s*", rule) if part.strip()]


def rule_mappings(
    rule: str, target_langs: tuple[str, ...] = TARGET_LANGS
) -> list[tuple[str, str]]:
    """Mirror ``Module:CGroup.convertRule`` for *rule* and the target variants.

    ``Module:CGroup`` turns a rule such as ``zh-cn:米; zh-tw:公尺`` into
    ``公尺 => 米`` when converting to ``zh-cn``.  One-way rules
    (``公尺=>zh-cn:米``) apply only to the variant named after ``=>``.
    """
    parsed: list[tuple[str | None, str, str]] = []
    for part in _split_rule(rule):
        match = _RULE_PART_RE.match(part)
        if not match:
            continue
        lang = _canonical_lang(match.group("lang"))
        if not lang:
            continue
        source = match.group("source")
        parsed.append((source.strip() if source else None, lang, match.group("text").strip()))

    if not parsed:
        return []

    for target in target_langs:
        one_way = [(source, text) for source, lang, text in parsed if source and lang == target]
        variants = {lang: text for source, lang, text in parsed if not source}
        target_text = variants.get(target)

        if not one_way and not target_text:
            continue

        mappings: list[tuple[str, str]] = list(one_way)
        if target_text:
            for lang, text in variants.items():
                if lang != target and text and text != target_text:
                    mappings.append((text, target_text))

        # Within one rule, longer sources must win over shorter prefixes.
        return sorted(
            _dedupe_mappings(mappings),
            key=lambda pair: len(pair[0]),
            reverse=True,
        )

    return []


def build_replacements(
    rules: list[str], target_langs: tuple[str, ...] = TARGET_LANGS
) -> list[tuple[str, str]]:
    """Turn every rule into an ordered ``(source, replacement)`` list."""
    replacements: list[tuple[str, str]] = []
    for rule in rules:
        replacements.extend(rule_mappings(rule, target_langs))
    return _dedupe_mappings(replacements)


@lru_cache(maxsize=32)
def _compiled_replacements(
    replacements: tuple[tuple[str, str], ...],
) -> tuple[re.Pattern[str], dict[str, str]]:
    """Build one longest-match regex for a whole conversion rule set.

    A single pass is important.  Applying ``胞器 => 细胞器`` with repeated
    ``str.replace`` turns the already-correct ``细胞器`` into ``细细胞器``.
    Including every *target* in the alternation (longest first) makes an
    existing target pre-empt a shorter source inside it, which is how the
    wiki's converter behaves in practice.
    """
    source_map: dict[str, str] = {}
    terms: set[str] = set()
    for source, target in replacements:
        if not source or not target or source == target:
            continue
        source_map.setdefault(source, target)
        terms.add(source)
        terms.add(target)

    if not terms:
        return re.compile(r"(?!)"), {}

    ordered = sorted(terms, key=lambda term: (-len(term), term))
    pattern = re.compile("|".join(re.escape(term) for term in ordered))
    return pattern, source_map


def apply_replacements(text: str, replacements: list[tuple[str, str]]) -> str:
    """Apply *replacements* in one longest-match pass.

    Existing target terms win over a shorter source that is a substring of
    them, so the conversion is idempotent and does not cascade.
    """
    if not text or not replacements:
        return text

    pattern, source_map = _compiled_replacements(tuple(replacements))
    if not source_map:
        return text
    return pattern.sub(lambda match: source_map.get(match.group(0), match.group(0)), text)


# ── Helpers ───────────────────────────────────────────────────────────


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _dedupe_mappings(pairs: list[tuple[str, str]]) -> list[tuple[str, str]]:
    seen: set[tuple[str, str]] = set()
    result: list[tuple[str, str]] = []
    for source, replacement in pairs:
        if not source or not replacement or source == replacement:
            continue
        key = (source, replacement)
        if key in seen:
            continue
        seen.add(key)
        result.append(key)
    # Preserve rule order: MediaWiki applies conversion rules in the order the
    # wiki declares them.  rule_mappings() already sorted within each rule.
    return result
