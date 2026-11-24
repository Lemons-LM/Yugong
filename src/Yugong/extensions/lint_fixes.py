"""Safe fixes for common LintErrors and QW:TODO obsolete syntax.

Implemented (all idempotent and confined to the page being processed):

* ``obsolete-tag``: ``<font>`` (color/face), ``<center>``, ``<big>``,
  ``<tt>``, ``<strike>`` -> modern HTML/CSS equivalents.
* Obsolete presentation attributes listed in ``QW:TODO``: ``align``,
  ``valign``, ``width``, ``height``, ``bgcolor``, ``border`` -> ``style``.
  This covers both HTML tags and wikitable cells (mwparserfromhell exposes
  ``| align=... |`` cells as ``td`` tags).
* ``self-closing-tag``: non-void tags such as ``<div/>`` -> ``<div></div>``;
  ``<br/>``, ``<ref name=x/>`` and other legitimately self-closing tags are
  left alone.
* Empty category sort keys: ``[[Category:X|  ]]`` -> ``[[Category:X]]``
  (non-empty sort keys are kept).
* Empty list items left behind by a template deletion (``* `` alone on a
  line) are removed.
* Empty headings (including comment-only headings) are removed.
* ``bogus-image-options`` duplicate bare pixel sizes:
  ``[[File:X|240px|thumb|200px|...]]`` -> ``[[File:X|240px|thumb|...]]``.

Deliberately NOT automated (reported here so the decision is explicit):
``missing-end-tag``/``stripped-tag``/``misnested-tag`` (usually caused by a
transcluded template and requires a human judgement), ``deletable-table-tag``,
image options other than duplicate sizes, ``duplicate-id``,
``wikilink-in-extlink``, ``multi-colon-escape``, ``pwrap-bug-workaround`` and
``tidy-whitespace-bug``.  ``cellspacing``/``cellpadding`` are also left alone:
converting them to ``border-spacing``/per-cell ``padding`` is not a local, safe
substitution.
"""

from __future__ import annotations

import re

import mwparserfromhell as mph

from src.Yugong.core.wikitext import Wikitext
from src.Yugong.utilities.mark_job_intro import intro, job

#: HTML void elements: self-closing is the only valid form.
VOID_TAGS: frozenset[str] = frozenset({
    "area", "base", "br", "col", "embed", "hr", "img", "input", "link",
    "meta", "param", "source", "track", "wbr",
})

#: Extension tags that are legitimately self-closing.
SELF_CLOSING_ALLOWED: frozenset[str] = VOID_TAGS | frozenset({
    "ref", "references", "nowiki", "math", "chem", "gallery", "imagemap",
    "templatedata", "templatestyles", "inputbox", "poem", "section",
    "score", "timeline", "mapframe", "maplink", "graph",
})

#: Contents of these tags are code/data, not page markup.
PROTECTED_TAGS: frozenset[str] = frozenset({
    "nowiki", "pre", "code", "syntaxhighlight", "source", "math", "chem",
    "templatedata", "templatestyles", "gallery", "imagemap",
})

#: Tags whose presentation attributes are safe to fold into ``style``.
ATTRIBUTE_TAGS: frozenset[str] = frozenset({
    "table", "caption", "thead", "tbody", "tfoot", "tr", "td", "th",
    "col", "colgroup", "div", "span", "p", "li", "ul", "ol", "section",
    "img", "font", "center",
})

_OBSOLETE_TAG_MAP: dict[str, str] = {
    "center": "div",
    "big": "span",
    "tt": "code",
    "strike": "s",
}

_CATEGORY_PREFIXES: tuple[str, ...] = (
    "category:", "分类:", "分類:", "catégorie:",
)


def _simple(value: str) -> bool:
    """Reject attribute values that involve templates, links or newlines."""
    return bool(value) and not any(
        marker in value for marker in ("{{", "[[", "|", "\n", "\r", "<", ">")
    )


def _style_map(style: str) -> list[tuple[str, str]]:
    declarations: list[tuple[str, str]] = []
    for part in style.split(";"):
        if ":" not in part:
            continue
        prop, value = part.split(":", 1)
        prop = prop.strip().lower()
        value = value.strip()
        if prop and value:
            declarations.append((prop, value))
    return declarations


def _merge_style(tag: mph.wikicode.Tag, declarations: list[tuple[str, str]]) -> None:
    """Add *declarations* to the tag's ``style`` without overriding existing ones."""
    if not declarations:
        return

    existing_raw = ""
    existing: list[tuple[str, str]] = []
    if tag.has("style"):
        existing_raw = str(tag.get("style").value).strip()
        existing = _style_map(existing_raw)
        tag.remove("style")

    seen = {prop for prop, _ in existing}
    additions = [
        f"{prop}: {value}" for prop, value in declarations if prop not in seen
    ]
    if not additions:
        if existing_raw:
            tag.add("style", existing_raw)
        return

    prefix = existing_raw.rstrip("; ")
    merged = f"{prefix}; {'; '.join(additions)}" if prefix else "; ".join(additions)
    tag.add("style", merged)


def _length_value(value: str) -> str:
    value = value.strip()
    if value.isdigit():
        return f"{value}px"
    return value


def _convert_attributes(tag: mph.wikicode.Tag) -> None:
    """Fold obsolete presentation attributes into a ``style`` attribute."""
    tag_name = str(tag.tag).strip().lower()
    if tag_name not in ATTRIBUTE_TAGS:
        return

    declarations: list[tuple[str, str]] = []
    to_remove: list[str] = []

    for attribute in list(tag.attributes):
        name = str(attribute.name).strip().lower()
        value = str(attribute.value).strip()
        if not _simple(value):
            continue

        declaration: tuple[str, str] | None = None
        if name == "align" and tag_name != "img":
            declaration = ("text-align", value)
        elif name == "valign":
            declaration = ("vertical-align", value)
        elif name == "width":
            declaration = ("width", _length_value(value))
        elif name == "height":
            declaration = ("height", _length_value(value))
        elif name == "bgcolor":
            declaration = ("background-color", value)
        elif name == "border":
            if value in ("0", "none"):
                declaration = ("border", "none")
            elif value.isdigit():
                declaration = ("border", f"{value}px solid")
            else:
                declaration = ("border", value)

        if declaration is not None:
            declarations.append(declaration)
            to_remove.append(str(attribute.name))

    if not declarations:
        return

    for name in to_remove:
        tag.remove(name)
    _merge_style(tag, declarations)


def _convert_font(tag: mph.wikicode.Tag) -> bool:
    """Convert ``<font color=... face=...>`` to a styled ``span``.

    A ``size`` attribute has no faithful CSS equivalent here, so a font tag
    carrying one is left untouched for a human.
    """
    if tag.has("size"):
        return False

    relevant = [
        (str(attribute.name), str(attribute.value).strip())
        for attribute in tag.attributes
        if str(attribute.name).strip().lower() in ("color", "face")
    ]
    if any(not _simple(value) for _name, value in relevant):
        # A dynamic colour/face cannot be moved into style reliably.
        return False

    declarations: list[tuple[str, str]] = []
    for name, value in relevant:
        if name.strip().lower() == "color":
            declarations.append(("color", value))
        else:
            declarations.append(("font-family", value))
        tag.remove(name)

    tag.tag = "span"
    _merge_style(tag, declarations)
    return True


def _escape_top_level_pipes(contents: str) -> str:
    """Escape every pipe that would split the ``{{Center}}`` parameter.

    Pipes inside nested templates, wikilinks or comments are left alone; pipes
    in plain text and in HTML tag attributes are escaped with ``{{!}}``.
    """
    output: list[str] = []
    stack: list[str] = []
    index = 0

    while index < len(contents):
        if contents.startswith("<!--", index):
            end = contents.find("-->", index + 4)
            if end == -1:
                output.append(contents[index:])
                break
            output.append(contents[index : end + 3])
            index = end + 3
            continue

        for opener, closer in (("{{{", "}}}"), ("{{", "}}"), ("[[", "]]")):
            if contents.startswith(opener, index):
                stack.append(closer)
                output.append(opener)
                index += len(opener)
                break
        else:
            for closer in ("}}}", "}}", "]]"):
                if contents.startswith(closer, index):
                    if stack and stack[-1] == closer:
                        stack.pop()
                    output.append(closer)
                    index += len(closer)
                    break
            else:
                character = contents[index]
                if character == "|" and not stack:
                    output.append("{{!}}")
                else:
                    output.append(character)
                index += 1

    return "".join(output)


def _replace_center_template(
    code: mph.wikicode.Wikicode, tag: mph.wikicode.Tag
) -> bool:
    """Replace ``<center>`` with the wiki's ``{{Center}}`` template.

    ``<center>`` is always turned into ``{{Center}}`` — never into a
    ``<div>``/``<span>`` — with top-level pipes escaped as ``{{!}}`` so the
    content stays in parameter 1.  Cases that cannot be expressed safely (extra
    attributes, table markup, dynamic styles) are left untouched for a human.
    """
    if str(tag.tag).strip().lower() != "center":
        return False

    # This tag is handled by this function whatever happens below: never let
    # the generic obsolete-tag conversion turn it into a <div>.
    names = [str(attribute.name).strip().lower() for attribute in tag.attributes]
    if any(name != "style" for name in names) or tag.contents is None:
        return True

    contents = str(tag.contents).strip()
    # Table markup contains its own pipes and line structure; a template call
    # would break it, so leave the (obsolete but valid) tag for a human.
    if not contents or "{|" in contents:
        return True

    style = ""
    if "style" in names:
        style = str(tag.get("style").value).strip()
        if not _simple(style) or "|" in style or "=" in style:
            return True

    escaped = _escape_top_level_pipes(contents)
    positional = "1=" if "=" in escaped else ""
    prefix = f"style={style}|" if style else ""
    replacement = "{{Center|" + prefix + positional + escaped + "}}"

    code.replace(tag, mph.parse(replacement))
    return True


def _convert_obsolete_tag(tag: mph.wikicode.Tag) -> None:
    name = str(tag.tag).strip().lower()

    if name == "font":
        _convert_font(tag)
        return

    replacement = _OBSOLETE_TAG_MAP.get(name)
    if replacement is None:
        return

    tag.tag = replacement
    if name == "center":
        _merge_style(tag, [("text-align", "center")])
    elif name == "big":
        _merge_style(tag, [("font-size", "larger")])


def _fix_self_closing(code: mph.wikicode.Wikicode, tag: mph.wikicode.Tag) -> bool:
    if not tag.self_closing:
        return False

    name = str(tag.tag).strip().lower()
    if name in SELF_CLOSING_ALLOWED:
        return False

    raw = str(tag).rstrip()
    if not raw.endswith("/>"):
        return False

    opening = raw[:-2].rstrip() + ">"
    code.replace(tag, f"{opening}</{name}>")
    return True


def _walk(code: mph.wikicode.Wikicode) -> None:
    for node in list(code.nodes):
        if isinstance(node, mph.nodes.Tag):
            name = str(node.tag).strip().lower()
            if name in PROTECTED_TAGS:
                continue

            if _replace_center_template(code, node):
                continue

            _convert_obsolete_tag(node)
            _convert_attributes(node)
            if _fix_self_closing(code, node):
                continue
            if node.contents is not None:
                _walk(node.contents)

        elif isinstance(node, mph.nodes.Heading):
            title_text = re.sub(
                r"<!--.*?-->", "", str(node.title), flags=re.DOTALL
            ).strip()
            if not title_text:
                code.remove(node)
                continue
            _walk(node.title)

        elif isinstance(node, mph.nodes.Wikilink):
            if node.text is not None:
                _walk(node.text)

        elif isinstance(node, mph.nodes.ExternalLink):
            if node.title is not None:
                _walk(node.title)

        elif isinstance(node, mph.nodes.Template):
            # Tag syntax inside a template *argument value* is still the page's
            # markup and is safe to fix.  Template and parameter names are not
            # touched because only ``param.value`` is walked.
            for param in node.params:
                _walk(param.value)

        elif isinstance(node, mph.nodes.Argument):
            if node.default is not None:
                _walk(node.default)


_FILE_PREFIXES: tuple[str, ...] = (
    "file:", "image:", "文件:", "檔案:", "图像:", "圖像:",
)
_IMAGE_SIZE_RE = re.compile(r"^\s*\d+\s*px\s*$", re.IGNORECASE)


def _fix_duplicate_image_sizes(wikitext: Wikitext) -> None:
    """Drop extra bare pixel sizes from file links (LintErrors bogus-image-options).

    ``[[File:X|240px|thumb|200px|Caption]]`` -> ``[[File:X|240px|thumb|Caption]]``.
    Links containing nested templates/links are skipped because their ``|``
    characters are not simple option separators.
    """
    for link in list(wikitext.wikilinks()):
        lowered = str(link.title).strip().lower()
        if not any(lowered.startswith(prefix) for prefix in _FILE_PREFIXES):
            continue
        if link.text is None:
            continue

        raw = str(link)
        if not (raw.startswith("[[") and raw.endswith("]]")):
            continue
        inner = raw[2:-2]
        if "{{" in inner or "[[" in inner:
            continue

        parts = inner.split("|")
        size_indices = [
            index for index, part in enumerate(parts) if _IMAGE_SIZE_RE.match(part)
        ]
        if len(size_indices) <= 1:
            continue

        drop = set(size_indices[1:])
        rebuilt = "|".join(
            part for index, part in enumerate(parts) if index not in drop
        )
        wikitext.wikitext.replace(link, f"[[{rebuilt}]]")


_EMPTY_LIST_ITEM_RE = re.compile(r"(?m)^[ \t]*[*#]+[ \t]*(?:\r?\n|$)")
_EMPTY_LINE_AFTER_MARKER_RE = re.compile(r"[ \t]*(?:\r?\n|$)")


def _merge_adjacent_text(code: mph.wikicode.Wikicode) -> None:
    """Join neighbouring text nodes.

    Earlier jobs that replace a node can leave the surrounding newline in a
    separate text node.  The list-item check needs the complete line in one
    node (``" \\n"`` rather than ``" "`` + ``"\\n"``).
    """
    index = 0
    while index + 1 < len(code.nodes):
        current = code.nodes[index]
        following = code.nodes[index + 1]
        if isinstance(current, mph.nodes.Text) and isinstance(following, mph.nodes.Text):
            current.value = str(current) + str(following)
            code.remove(following)
        else:
            index += 1


def _remove_empty_list_items(wikitext: Wikitext) -> None:
    """Drop list-item lines that hold nothing (e.g. after template deletion).

    mwparserfromhell represents a list marker (``*``/``#``) as an ``li`` tag
    whose content follows as a sibling text node, so an empty item is a run of
    ``li`` tags followed by a text node starting with a line break.
    """
    nodes = list(wikitext.wikitext.nodes)
    index = 0
    while index < len(nodes):
        node = nodes[index]
        if not (
            isinstance(node, mph.nodes.Tag)
            and str(node.tag).strip().lower() == "li"
        ):
            index += 1
            continue

        end = index
        while end < len(nodes):
            candidate = nodes[end]
            if not (
                isinstance(candidate, mph.nodes.Tag)
                and str(candidate.tag).strip().lower() == "li"
            ):
                break
            end += 1

        following = nodes[end] if end < len(nodes) else None
        match = None
        if following is None:
            pass  # markers at the end of the page: an empty item
        elif isinstance(following, mph.nodes.Text):
            match = re.match(r"[ \t]*\r?\n", str(following))
            if match is None and end == len(nodes) - 1 and not str(following).strip():
                match = _EMPTY_LINE_AFTER_MARKER_RE.match(str(following))
            if match is None:
                index = end
                continue
        else:
            # More content follows the markers (a link, a template, ...).
            index = end
            continue

        for marker in nodes[index:end]:
            wikitext.wikitext.remove(marker)
        if match is not None and isinstance(following, mph.nodes.Text):
            following.value = str(following)[match.end():]
        index = end

    for node in list(wikitext.wikitext.nodes):
        if not isinstance(node, mph.nodes.Text):
            continue
        new_value = _EMPTY_LIST_ITEM_RE.sub("", str(node))
        if new_value != str(node):
            node.value = new_value


def _remove_empty_category_sortkeys(wikitext: Wikitext) -> None:
    for link in wikitext.wikilinks():
        title = str(link.title).strip().lower()
        if not any(title.startswith(prefix) for prefix in _CATEGORY_PREFIXES):
            continue
        if link.text is not None and str(link.text).strip() == "":
            link.text = None


@job
def lint_fixes_job(wikitext: Wikitext) -> None:
    """Apply the safe LintErrors / obsolete-syntax fixes to the page."""
    _walk(wikitext.wikitext)
    _merge_adjacent_text(wikitext.wikitext)
    _remove_empty_list_items(wikitext)
    _remove_empty_category_sortkeys(wikitext)
    _fix_duplicate_image_sizes(wikitext)


@intro
def lint_fixes_intro() -> str:
    return (
        "Lint fixes: obsolete font/center/big/tt/strike tags, align/valign/"
        "width/height/bgcolor/border -> CSS, self-closing non-void tags, "
        "empty headings, duplicate image sizes, empty category sort keys"
    )
