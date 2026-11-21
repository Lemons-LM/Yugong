"""Remove Unicode characters that render as nothing but break wikitext.

Copy-pasting from PDFs, web pages and office documents frequently drags in
zero-width spaces, BOMs, word joiners, soft hyphens and stray control
characters.  They are invisible in the editor, break template names and
parameters, and make search/replace fail for no visible reason.

The job is a no-op unless ``enable_invisible_chars_fix = true`` in
``settings.toml``.  It cleans every text-bearing node — article text, template
and parameter names/values, link targets and labels, tag names/attributes and
headings — while skipping:

* HTML comments (deliberate annotations, not page content);
* the contents of code/data tags such as ``<nowiki>``, ``<pre>``, ``<code>``,
  ``<syntaxhighlight>``, ``<math>`` and ``<chem>``;
* characters with a real rendering meaning: ordinary spaces, tabs, newlines,
  non-breaking and other Unicode spaces, and variation selectors.

By default the *safe* set is removed: soft hyphen (U+00AD), zero-width space
(U+200B), word joiner (U+2060), BOM/zero-width no-break space (U+FEFF),
deprecated format controls, interlinear annotation controls, tag characters,
and C0/C1 controls other than TAB/LF/CR.  Zero-width joiners, zero-width
non-joiners, bidi marks/controls and the Arabic letter mark are kept because
they are meaningful in emoji sequences, Indic/Persian text and right-to-left
text; set ``invisible_chars_aggressive = true`` to remove those as well.
"""

from __future__ import annotations

import re

import mwparserfromhell as mph

from src.Yugong.core.logger import utilities_logger
from src.Yugong.core.settings import settings
from src.Yugong.core.wikitext import Wikitext
from src.Yugong.utilities.mark_job_intro import intro, job

#: Contents of these tags are code/data, not page markup.
PROTECTED_TAGS: frozenset[str] = frozenset({
    "nowiki", "pre", "code", "syntaxhighlight", "source", "math", "chem",
    "templatedata", "templatestyles", "gallery", "imagemap",
})

#: Zero-width / format / control characters that are safe to delete.
#:
#: Deliberately *not* included: U+00A0 and the other Unicode space separators
#: (they are real spaces), U+034F (combining grapheme joiner), U+FE00-U+FE0F
#: and U+E0100-U+E01EF (variation selectors), and U+2061-U+2064 (invisible
#: mathematical operators).
SAFE_INVISIBLE_RE = re.compile(
    "["
    "\u00ad"          # soft hyphen
    "\u180e"          # Mongolian vowel separator
    "\u200b"          # zero width space
    "\u2060"          # word joiner
    "\u206a-\u206f"  # deprecated format controls
    "\ufeff"          # BOM / zero width no-break space
    "\ufff9-\ufffb"  # interlinear annotation controls
    "\U000e0000-\U000e007f"  # tag characters
    "\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f"  # C0/C1, except TAB/LF/CR
    "]"
)

#: Characters that are meaningful in some scripts but are removed when
#: ``invisible_chars_aggressive = true``.
AGGRESSIVE_INVISIBLE_RE = re.compile(
    "["
    "\u061c"          # Arabic letter mark
    "\u200c"          # zero width non-joiner
    "\u200d"          # zero width joiner
    "\u200e-\u200f"  # left/right-to-left mark
    "\u202a-\u202e"  # bidi embedding / override
    "\u2066-\u2069"  # bidi isolates
    "]"
)


def _clean_text(text: str, aggressive: bool) -> tuple[str, int]:
    """Return the cleaned text and how many characters were removed."""
    cleaned = SAFE_INVISIBLE_RE.sub("", text)
    if aggressive:
        cleaned = AGGRESSIVE_INVISIBLE_RE.sub("", cleaned)
    return cleaned, len(text) - len(cleaned)


def _clean_wikicode(code: mph.wikicode.Wikicode, aggressive: bool) -> int:
    """Clean every text-bearing node in *code* in place; return the count."""
    removed = 0
    for node in list(code.nodes):
        if isinstance(node, mph.nodes.Text):
            cleaned, count = _clean_text(str(node), aggressive)
            if count:
                node.value = cleaned
                removed += count

        elif isinstance(node, mph.nodes.Tag):
            name, count = _clean_text(str(node.tag), aggressive)
            removed += count
            if count:
                node.tag = name
            if name.strip().lower() in PROTECTED_TAGS:
                continue

            for attribute in node.attributes:
                removed += _clean_wikicode(attribute.name, aggressive)
                attribute_value = attribute.value
                if attribute_value is not None:
                    removed += _clean_wikicode(attribute_value, aggressive)
            contents = node.contents
            if contents is not None:
                removed += _clean_wikicode(contents, aggressive)

        elif isinstance(node, mph.nodes.Heading):
            removed += _clean_wikicode(node.title, aggressive)

        elif isinstance(node, mph.nodes.Wikilink):
            removed += _clean_wikicode(node.title, aggressive)
            if node.text is not None:
                removed += _clean_wikicode(node.text, aggressive)

        elif isinstance(node, mph.nodes.ExternalLink):
            removed += _clean_wikicode(node.url, aggressive)
            if node.title is not None:
                removed += _clean_wikicode(node.title, aggressive)

        elif isinstance(node, mph.nodes.Template):
            removed += _clean_wikicode(node.name, aggressive)
            for param in node.params:
                removed += _clean_wikicode(param.name, aggressive)
                removed += _clean_wikicode(param.value, aggressive)

        elif isinstance(node, mph.nodes.Argument):
            removed += _clean_wikicode(node.name, aggressive)
            if node.default is not None:
                removed += _clean_wikicode(node.default, aggressive)

        # Comments, entities and the remaining node types are left untouched.

    return removed


@job
def rm_invisible_chars_job(wikitext: Wikitext) -> None:
    """Remove invisible Unicode characters from the page."""
    if not settings.enable_invisible_chars_fix:
        return

    aggressive = bool(settings.invisible_chars_aggressive)
    removed = _clean_wikicode(wikitext.wikitext, aggressive)
    if removed:
        utilities_logger.info(
            f"{wikitext.title}: removed {removed} invisible character(s)"
            f"{' (aggressive)' if aggressive else ''}"
        )


@intro
def rm_invisible_chars_intro() -> str:
    return (
        "Invisible characters: remove zero-width/format/control characters, "
        "skipping nowiki/code/math and comments "
        f"(aggressive={settings.invisible_chars_aggressive}, "
        f"enabled={settings.enable_invisible_chars_fix})"
    )
