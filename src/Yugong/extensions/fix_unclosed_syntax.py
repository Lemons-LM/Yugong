"""Close ``[[``/``{{``/``<!--`` constructs left unterminated on the page.

``mwparserfromhell`` leaves an unterminated construct in a plain text node.
When such a node is at the end of the page, the closers are appended at the end
of the text it covers (before an unterminated comment, if that is the innermost
construct), which is the minimal repair that makes the page parse again:

    [[Link|未闭合的链接          ->  [[Link|未闭合的链接]]
    {{Unclosed|a=b              ->  {{Unclosed|a=b}}
    <!-- 未闭合的注释            ->  <!-- 未闭合的注释 -->

Only text left unparsed by ``mwparserfromhell`` is touched, so balanced
constructs and protected tags (``nowiki``/``code``/``pre``) are never changed.
Other broken markup (unclosed ``<div>``/``'''``, stray ``}}``) is deliberately
left for a human.
"""

from __future__ import annotations

import mwparserfromhell as mph

from src.Yugong.core.logger import utilities_logger
from src.Yugong.core.wikitext import Wikitext
from src.Yugong.utilities.mark_job_intro import intro, job
from src.Yugong.utilities.reporter import reporter


def _unclosed_openers(text: str) -> list[tuple[int, str]]:
    """Return ``(line, closer)`` for every construct left open in *text*.

    ``line`` is the zero-based line on which the opener appears.  A construct
    that starts on its own line is closed at the end of that line, which is the
    natural reading of

        [[Link|未闭合的链接
        {{Unclosed|a=b

    (two separate broken constructs, not one nested inside the other).
    """
    stack: list[tuple[int, str]] = []
    line = 0
    index = 0
    length = len(text)

    while index < length:
        if text.startswith("<!--", index):
            end = text.find("-->", index + 4)
            if end == -1:
                stack.append((line, "-->"))
                break
            line += text.count("\n", index, end)
            index = end + 3
            continue
        if text[index] == "\n":
            line += 1
            index += 1
            continue
        if text.startswith("{{{", index):
            stack.append((line, "}}}"))
            index += 3
            continue
        if text.startswith("{{", index):
            stack.append((line, "}}"))
            index += 2
            continue
        if text.startswith("[[", index):
            stack.append((line, "]]"))
            index += 2
            continue
        if text.startswith("}}}", index) and stack and stack[-1][1] == "}}}":
            stack.pop()
            index += 3
            continue
        if text.startswith("}}", index) and stack and stack[-1][1] == "}}":
            stack.pop()
            index += 2
            continue
        if text.startswith("]]", index) and stack and stack[-1][1] == "]]":
            stack.pop()
            index += 2
            continue
        index += 1

    return stack


def _repair(text: str) -> str:
    """Close the unterminated constructs in one unparsed text node."""
    openers = _unclosed_openers(text)
    if not openers:
        return text

    closers_by_line: dict[int, list[str]] = {}
    for line, closer in openers:
        closers_by_line.setdefault(line, []).append(closer)

    lines = text.splitlines(keepends=True)
    if not lines:
        return text

    for line_index, closers in closers_by_line.items():
        if line_index >= len(lines):
            continue
        raw = lines[line_index]
        ending = ""
        body = raw
        for suffix in ("\r\n", "\n", "\r"):
            if body.endswith(suffix):
                ending = suffix
                body = body[: -len(suffix)]
                break
        # Close the innermost construct first if several start on this line.
        closers = list(reversed(closers))
        body = body.rstrip() + "".join(
            f" {closer}" if closer == "-->" else closer for closer in closers
        )
        lines[line_index] = body + ending

    return "".join(lines)


@job
def fix_unclosed_syntax_job(wikitext: Wikitext) -> None:
    """Append missing closers to unparsed trailing constructs."""
    for node in list(wikitext.wikitext.nodes):
        if not isinstance(node, mph.nodes.Text):
            continue
        original = str(node)
        if "[" not in original and "{" not in original and "<!--" not in original:
            continue
        repaired = _repair(original)
        if repaired == original:
            continue
        node.value = repaired
        message = f"{wikitext.title}: closed unterminated markup at the end of the page"
        utilities_logger.info(message)
        reporter.add("syntax", message)


@intro
def fix_unclosed_syntax_intro() -> str:
    return (
        "Unclosed syntax: append missing ]]/}}/--> to constructs left "
        "unterminated at the end of the page"
    )
