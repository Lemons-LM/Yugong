"""Apply the automatable parts of ``QW:CAT`` (category style guideline).

Read from the wiki's ``Qiuwen:格式手册/分类``:

* Category links use a single canonical ``Category:`` prefix and a page is
  listed at most once.
* Redundant manual sort keys are removed: empty keys, keys equal to the page
  title (with or without namespace), and keys made only of deprecated/full-width
  punctuation.  Meaningful keys (``*``, ``#``, prefixes, pinyin corrections) are
  kept.
* Category pages get ``{{catnav|auto=1}}`` at the top when they do not have it
  and are not redirects.

Not automated: whether a page *should* be in a category, abstract-category
inheritance, navigation-box consistency, and moving category links to the
bottom of an article.
"""

from __future__ import annotations

import re

import mwparserfromhell as mph

from src.Yugong.core.wikitext import Wikitext
from src.Yugong.utilities.mark_job_intro import intro, job

#: Category namespace id.
CATEGORY_NAMESPACE: int = 14

CATEGORY_PREFIXES: tuple[str, ...] = (
    "category:", "分类:", "分類:", "catégorie:",
)

#: Sort keys made only of these are deprecated by QW:CAT.
REDUNDANT_PUNCT: frozenset[str] = frozenset("·：；？，。！￥＄@:$")

_CATEGORY_REDIRECT_RE = re.compile(
    r"\{\{\s*(?:分类重定向|分類重新導向|Category redirect|cr|Catredirect)\b",
    re.IGNORECASE,
)


def _category_bare(title: str) -> str | None:
    """Return the bare category name, or ``None`` for a non-category link."""
    text = title.strip()
    if text.startswith(":"):
        # ``[[:Category:X]]`` is a link, not a category membership.
        return None
    lowered = text.lower()
    for prefix in CATEGORY_PREFIXES:
        if lowered.startswith(prefix):
            return text[len(prefix):].strip()
    return None


def _redundant_sort_key(sort: str, page_title: str) -> bool:
    sort = sort.strip()
    if not sort:
        return True
    if sort in ("*", "#"):
        return False

    bare_title = page_title.split(":", 1)[1] if ":" in page_title else page_title
    if sort in (page_title, bare_title):
        return True

    if sort[0] in "@:$＠":
        return True

    return all(char in REDUNDANT_PUNCT for char in sort)


def _normalise_links(wikitext: Wikitext) -> None:
    seen: set[str] = set()
    for link in list(wikitext.wikilinks()):
        bare = _category_bare(str(link.title))
        if bare is None:
            continue

        key = bare.lower()
        if key in seen:
            wikitext.wikitext.remove(link)
            continue
        seen.add(key)

        link.title = f"Category:{bare}"
        if link.text is not None and _redundant_sort_key(
            str(link.text), wikitext.title
        ):
            link.text = None


def _ensure_catnav(wikitext: Wikitext) -> None:
    if wikitext.namespace != CATEGORY_NAMESPACE:
        return

    content = str(wikitext.wikitext)
    stripped = content.lstrip()
    if not stripped:
        return
    if stripped.upper().startswith("#REDIRECT"):
        return
    if _CATEGORY_REDIRECT_RE.search(content):
        return

    try:
        code = mph.parse(content)
    except Exception:  # noqa: BLE001 - leave malformed text alone
        return

    for template in code.filter_templates(recursive=True):
        if str(template.name).strip().lower() == "catnav":
            return

    wikitext.update(f"{{{{catnav|auto=1}}}}\n\n{stripped}")


@job
def category_policy_job(wikitext: Wikitext) -> None:
    """Normalise category links and add ``catnav`` to category pages."""
    _normalise_links(wikitext)
    _ensure_catnav(wikitext)


@intro
def category_policy_intro() -> str:
    return (
        "Category policy (QW:CAT): Category: prefix, one link per category, "
        "remove redundant sort keys, add {{catnav|auto=1}} to category pages"
    )
