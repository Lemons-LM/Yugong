"""Cangjie: convert article text to the Mainland variant via NoteTA.

The original YuGong description called this "Cangjie auto convert zh-Hans <=>
zh-Hant, and other variants, via NoteTA so make sure no wrong conversions".
This job follows that design:

* The page's own ``{{NoteTA}}`` rules and its public conversion groups
  (``Module:CGroup/*`` / ``Template:CGroup/*``) are the authority for regional
  terminology.  Rules target ``zh-cn`` with ``zh-hans``/``zh`` fallback.
* OpenCC (when installed) performs the script-level Traditional -> Simplified
  conversion on top of those rules.  Without OpenCC only the NoteTA rules run.
* Only visible text is touched.  Template names, parameter names, category and
  file links, ``-{...}-`` conversion markup, URLs, comments and tags such as
  ``<nowiki>``/``<code>``/``<pre>``/``<math>`` are left byte-for-byte intact.
* Pages **without** NoteTA data still go through OpenCC (script-level
  Traditional -> Simplified); there is simply no page-specific terminology
  rule to apply.  Without OpenCC they are left unchanged.

The job is a no-op unless ``enable_cangjie = true`` in ``settings.toml``.
"""

from __future__ import annotations

import re
from typing import Any

import mwparserfromhell as mph

from src.Yugong.core.bot_db import bot_db
from src.Yugong.core.logger import utilities_logger
from src.Yugong.core.settings import settings
from src.Yugong.core.wiki import wiki
from src.Yugong.core.wikitext import Wikitext
from src.Yugong.utilities.cgroup_cache import resolve_note_ta_rules
from src.Yugong.utilities.mark_job_intro import intro, job
from src.Yugong.utilities.note_ta import (
    apply_replacements,
    build_replacements,
    parse_note_ta,
)

#: Tags whose contents must never be converted.
PROTECTED_TAGS: frozenset[str] = frozenset({
    "nowiki", "pre", "code", "syntaxhighlight", "source", "math", "chem",
    "templatedata", "templatestyles", "gallery", "imagemap",
})

#: Link namespaces whose *display text* must not be converted either.
SKIP_LINK_PREFIXES: tuple[str, ...] = (
    "category:", "分类:", "分類:",
    "file:", "image:", "文件:", "檔案:", "图像:", "圖像:",
)

#: ``-{...}-`` conversion markup, bare URLs and signatures are opaque.
_OPAQUE_RE = re.compile(r"-\{.*?\}-|https?://\S+|~~~+", re.IGNORECASE | re.DOTALL)

# OpenCC is optional; build the converter once.
_converter: Any = None
_converter_missing_reported = False


def _opencc_convert(text: str) -> str:
    """Convert Traditional Chinese to Simplified with OpenCC, if available."""
    global _converter, _converter_missing_reported

    if not text:
        return text

    if _converter is None:
        try:
            import opencc
        except ImportError:
            if not _converter_missing_reported:
                utilities_logger.warning(
                    "opencc is not installed; Cangjie will only apply the "
                    "NoteTA/CGroup rules, not script-level conversion "
                    "(pip install opencc)"
                )
                _converter_missing_reported = True
            return text
        # ``tw2s`` (not ``t2s``) resolves the traditional ``著`` particle to the
        # Mainland ``着`` (e.g. 隨著 -> 随着) instead of leaving a mixed
        # "随著"; the phrase table keeps 著名/著作 intact.
        _converter = opencc.OpenCC("tw2s.json")

    return str(_converter.convert(text))


def _convert_text(text: str, convert: Any) -> str:
    """Convert *text* while leaving opaque spans untouched."""
    if not text:
        return text

    pieces: list[str] = []
    last = 0
    for match in _OPAQUE_RE.finditer(text):
        pieces.append(convert(text[last:match.start()]))
        pieces.append(match.group(0))
        last = match.end()
    pieces.append(convert(text[last:]))
    return "".join(pieces)


def _convert_code(code: mph.wikicode.Wikicode, convert: Any) -> None:
    """Convert visible text nodes in *code*, recursively where safe."""
    for node in list(code.nodes):
        if isinstance(node, mph.nodes.Text):
            new_value = _convert_text(str(node), convert)
            if new_value != str(node):
                node.value = new_value

        elif isinstance(node, mph.nodes.Heading):
            _convert_code(node.title, convert)

        elif isinstance(node, mph.nodes.Wikilink):
            title = str(node.title).strip().lower()
            if any(title.startswith(prefix) for prefix in SKIP_LINK_PREFIXES):
                continue
            if node.text is not None:
                _convert_code(node.text, convert)

        elif isinstance(node, mph.nodes.ExternalLink):
            if node.title is not None:
                _convert_code(node.title, convert)

        elif isinstance(node, mph.nodes.Tag):
            tag_name = str(node.tag).strip().lower()
            if tag_name in PROTECTED_TAGS:
                continue
            if node.contents is not None:
                _convert_code(node.contents, convert)

        # Templates, arguments, comments, entities and everything else are
        # deliberately left alone.


@job(needs_wiki=True)
def cangjie_job(wikitext: Wikitext) -> None:
    """Convert the page's visible text to zh-cn when Cangjie is enabled."""
    if not settings.enable_cangjie:
        return

    source = wikitext.original_content or str(wikitext)
    config = parse_note_ta(source)

    # NoteTA gives page-specific terminology; without it OpenCC still performs
    # the script-level Traditional -> Simplified conversion for visible text.
    rules = (
        resolve_note_ta_rules(config, wiki_obj=wiki, db=bot_db)
        if not config.is_empty()
        else []
    )
    replacements = build_replacements(rules)

    def convert(text: str) -> str:
        return _opencc_convert(apply_replacements(text, replacements))

    _convert_code(wikitext.wikitext, convert)


@intro
def cangjie_intro() -> str:
    return (
        "Cangjie: NoteTA/CGroup-based zh-cn text conversion "
        f"(enabled={settings.enable_cangjie}; OpenCC optional)"
    )
