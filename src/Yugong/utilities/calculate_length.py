import re
import string
import unicodedata

import mwparserfromhell
from mwparserfromhell.nodes import (
    Comment,
    ExternalLink,
    Heading,
    HTMLEntity,
    Tag,
    Template,
    Text,
    Wikilink,
)

ASCII_HALF = set(string.ascii_letters + string.digits)


FILE_PREFIXES = (
    "file:",
    "image:",
    "文件:",
    "檔案:",
)

CATEGORY_PREFIXES = (
    "category:",
    "分类:",
    "分類:",
)
_INVISIBLE_CATEGORIES = frozenset({"Cf", "Cc", "Cs", "Co", "Cn", "Zs", "Zl", "Zp"})

INVISIBLE_CHARS = {
    # Zero-width
    "\u200B",  # ZERO WIDTH SPACE
    "\u200C",  # ZERO WIDTH NON-JOINER
    "\u200D",  # ZERO WIDTH JOINER
    "\u2060",  # WORD JOINER
    "\uFEFF",  # ZERO WIDTH NO-BREAK SPACE / BOM

    # Bidirectional formatting
    "\u202A",  # LEFT-TO-RIGHT EMBEDDING
    "\u202B",  # RIGHT-TO-LEFT EMBEDDING
    "\u202C",  # POP DIRECTIONAL FORMATTING
    "\u202D",  # LEFT-TO-RIGHT OVERRIDE
    "\u202E",  # RIGHT-TO-LEFT OVERRIDE

    # Bidirectional isolates
    "\u2066",  # LEFT-TO-RIGHT ISOLATE
    "\u2067",  # RIGHT-TO-LEFT ISOLATE
    "\u2068",  # FIRST STRONG ISOLATE
    "\u2069",  # POP DIRECTIONAL ISOLATE

    # Invisible operators
    "\u2061",  # FUNCTION APPLICATION
    "\u2062",  # INVISIBLE TIMES
    "\u2063",  # INVISIBLE SEPARATOR
    "\u2064",  # INVISIBLE PLUS
}

INVISIBLE_RE = re.compile(
    "".join(
        ch for ch in map(chr, range(0x110000))
        if unicodedata.category(ch) in _INVISIBLE_CATEGORIES
    )
)

REF_RE = re.compile(
    r"<ref\b[^>]*?>.*?</ref\s*>|<ref\b[^>]*?/?>",
    re.I | re.S,
)
COMMENT_RE = re.compile(r"<!--.*?-->", re.S)

MAGICWORD_RE = re.compile(r"__\w+__")

def has_invisible(text: str) -> bool:
    return any(c in INVISIBLE_CHARS for c in text)

REMOVE_TABLE = str.maketrans("", "", "".join(INVISIBLE_CHARS))

def remove_invisible(text: str) -> str:
    return text.translate(REMOVE_TABLE)

def strip_invisible(text: str) -> str:
    # Approach A: list comprehension (simplest)
    return ''.join(ch for ch in text if ch.isprintable() and not ch.isspace())


def text_length(text: str) -> float:
    """Calculate plain text length."""
    total = 0.0
    # print("NAME:", text_length.__name__)
    # print("INPUT: ", text)
    for ch in text:
        if not ch.isprintable() or ch.isspace():
            continue
        if ch in ASCII_HALF:
            total += 0.5
        else:
            total += 1
    # print("OUTPUT: ", total)
    return total


def code_length(code) -> float:
    """Calculate the effective length of a Wikicode or NodeList."""
    # print("NAME:", code_length.__name__)
    # print("INPUT: ", code)

    if isinstance(code, str):
        code = mwparserfromhell.parse(code)

    nodes = code.nodes if hasattr(code, "nodes") else code

    total = 0.0
    for node in nodes:
        total += node_length(node)

    # print("OUTPUT: ", total)
    return total


def node_length(node) -> float:
    """Recursively calculate the length of a single Node."""

    if isinstance(node, Text):
        return text_length(str(node))

    if isinstance(node, Comment):
        return 0

    if isinstance(node, HTMLEntity):
        return 1

    if isinstance(node, Heading):
        return code_length(node.title)

    if isinstance(node, Wikilink):
        title = str(node.title).strip().lower()

        if title.startswith(FILE_PREFIXES):
            return 0

        if title.startswith(CATEGORY_PREFIXES):
            return 0

        if node.text:
            return code_length(node.text)

        return code_length(node.title)

    if isinstance(node, ExternalLink):
        # print(node.__dict__)
        if node.title:
            return code_length(node.title)
        return 0

    if isinstance(node, Template):
        total = 0.0
        for param in node.params:
            total += code_length(param.value)
        return total

    if isinstance(node, Tag):
        if isinstance(node, Tag):
            if str(node.tag).lower() == "gallery":
                return 0
        if node.contents:
            return code_length(node.contents)
        return 0

    if hasattr(node, "value"):
        return code_length(node.value)

    return 0


def is_infobox(template: Template) -> bool:
    """
    Determine whether a template looks like an Infobox.

    Conditions:
    - At least 3 named parameters
    - No anonymous parameters
    """
    # print("NAME:", is_infobox.__name__)
    # print("INPUT: ", template)
    named = 0
    unnamed = 0

    for param in template.params:
        if param.showkey:
            named += 1
        else:
            unnamed += 1

    # print("OUTPUT: ", named >= 3 and unnamed == 0)
    return named >= 3 and unnamed == 0

def remove_top_templates(code):
    """
    Remove consecutive templates at the top of a page.

    Removal rules:
    - Ignore whitespace and comments
    - Remove templates consecutively
    - Stop at the first Infobox (Infobox is preserved)
    - Stop when regular content is encountered
    """

    i = 0
    # print("NAME:", remove_top_templates.__name__)
    # print("INPUT: ", code)
    while i < len(code.nodes):
        node = code.nodes[i]

        if isinstance(node, Comment):
            i += 1
            continue

        if isinstance(node, Text):
            if str(node).strip():
                break
            i += 1
            continue

        if isinstance(node, Template):
            if is_infobox(node):
                break

            del code.nodes[i]
            continue

        break

    # print("OUTPUT: ", code)
    return code


def effective_length(wikitext: str) -> float:
    """
    Calculate the effective length of wikitext.

    Rules:
    1. <ref>...</ref> tags are not counted.
    2. ASCII letters and digits count as 0.5.
    3. Templates only count parameter values.
    4. Remove consecutive top-of-page templates (until Infobox).
    5. File / Category links are not counted.
    """

    # Strip ref tags
    wikitext = REF_RE.sub("", wikitext)
    wikitext = COMMENT_RE.sub("", wikitext)
    wikitext = MAGICWORD_RE.sub("", wikitext)
    wikitext = remove_invisible(wikitext)


    # Parse
    code = mwparserfromhell.parse(wikitext)

    # Remove top-of-page templates
    remove_top_templates(code)

    # Count length
    return code_length(code)
