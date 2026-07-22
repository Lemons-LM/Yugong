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
    # 方式 A：列表推导式（最直观）
    return ''.join(ch for ch in text if ch.isprintable() and not ch.isspace())


def text_length(text: str) -> float:
    """计算普通文本长度"""
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
    """计算 Wikicode 或 NodeList"""
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
    """递归计算单个 Node"""

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
    判断一个模板是否像 Infobox。

    条件：
    - 至少 3 个命名参数
    - 没有匿名参数
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
    删除页面最顶部连续模板。

    删除规则：
    - 忽略空白、注释
    - 连续删除模板
    - 遇到第一个 Infobox 停止（Infobox 保留）
    - 遇到正文停止
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
    计算 Wikitext 有效长度。

    规则：
    1. <ref>...</ref> 不计。
    2. ASCII 字母和数字计 0.5。
    3. 模板仅统计参数值。
    4. 删除页顶连续模板（直到 Infobox）。
    5. File / Category 链接不计。
    """

    # 去掉 ref
    wikitext = REF_RE.sub("", wikitext)
    wikitext = COMMENT_RE.sub("", wikitext)
    wikitext = MAGICWORD_RE.sub("", wikitext)
    wikitext = remove_invisible(wikitext)


    # Parse
    code = mwparserfromhell.parse(wikitext)

    # 删除页顶模板
    remove_top_templates(code)

    # 统计长度
    return code_length(code)
