"""The production processing loop.

Flow::

    do_jobs()
      ├─ configure logging, record start time, take the run lock
      ├─ settings.validate()                  # all safety limits checked here
      ├─ optional daily-heartbeat duplicate check
      ├─ _get_todo_list()                     # page ids / embeddedin / category
      ├─ Manifest("cache/<wiki_tag>.json")    # merge with what is still queued
      └─ for each page: _process_single_page()
           ├─ tag policy check
           ├─ template rules + every @job
           ├─ diff-size check
           └─ submit, or copy to clipboard and open the browser
"""

from __future__ import annotations

import difflib
import hashlib
import os
import re
import sys
import webbrowser
from urllib.parse import quote

import pyperclip
import pywikibot

from src.Yugong.core.logger import configure_logging, logger
from src.Yugong.core.mailer import mailer
from src.Yugong.core.manifest import Manifest
from src.Yugong.core.settings import settings
from src.Yugong.core.template_formatter import formatter
from src.Yugong.core.wiki import wiki
from src.Yugong.core.wikitext import Wikitext
from src.Yugong.processor.pipeline import apply_steps, build_steps
from src.Yugong.utilities.check_heartbeat import (
    heartbeat_content,
    heartbeat_matches,
    record_heartbeat,
)
from src.Yugong.utilities.lock import lock, unlock
from src.Yugong.utilities.path_helper import PROJECT_ROOT
from src.Yugong.utilities.record_start_time import record_start_time
from src.Yugong.utilities.reporter import reporter
from src.Yugong.utilities.urls import base_url as normalize_base_url

#: How many page ids to ask for in one API call when sweeping a page-id range.
PAGEID_BATCH_SIZE: int = 50

#: Above this combined size the exact character-level diff becomes too slow
#: (it is O(n²); 40k chars already takes seconds).  Larger pages use a
#: line-based estimate instead, which is linear in the number of lines and
#: over-estimates the change, so it can only reject more edits, never accept a
#: too-large one.
EXACT_DIFF_CHARS: int = 20_000

#: Absolute hard cap: refuse to even load/diff absurdly large pages.
MAX_DIFF_CHARS: int = 5_000_000

#: Base name for the file remembering which UTC day the bot last ran.  The
#: effective file is suffixed with ``wiki_tag`` so two wikis cannot overwrite
#: each other's daily claim.
DAILY_HEARTBEAT_FILE: str = os.path.join(PROJECT_ROOT, "data", "bot", "heartbeat_daily")


def daily_heartbeat_file() -> str:
    """Return the per-wiki daily heartbeat path."""
    tag = re.sub(r"[^A-Za-z0-9._-]", "_", str(settings.wiki_tag)) or "wiki"
    return f"{DAILY_HEARTBEAT_FILE}_{tag}"


class SafetyAbort(RuntimeError):
    """Raised when a page looks dangerous enough to stop the whole run."""


# ── Pure helpers ──────────────────────────────────────────────────────

def diff_size(old: str, new: str) -> int:
    """Characters added, removed or rewritten between two revisions.

    Used to enforce ``max_acceptable_diff_size`` before anything is submitted.
    The exact character-level diff is quadratic, so large pages fall back to a
    line-based estimate that over-counts rather than under-counts.
    """
    if old == new:
        return 0

    if len(old) + len(new) <= EXACT_DIFF_CHARS:
        matcher = difflib.SequenceMatcher(None, old, new, autojunk=False)
        total = 0
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag != "equal":
                total += max(i2 - i1, j2 - j1)
        return total

    old_lines = old.splitlines(keepends=True)
    new_lines = new.splitlines(keepends=True)
    # Very line-heavy pages get autojunk so the diff stays fast; it can only
    # inflate the estimate, which is the safe direction.
    autojunk = len(old_lines) + len(new_lines) > 20_000
    matcher = difflib.SequenceMatcher(None, old_lines, new_lines, autojunk=autojunk)
    total = 0
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        old_chars = sum(len(line) for line in old_lines[i1:i2])
        new_chars = sum(len(line) for line in new_lines[j1:j2])
        total += max(old_chars, new_chars)
    return total


def pageid_batches(start: int, end: int, *, size: int = PAGEID_BATCH_SIZE) -> list[list[int]]:
    """Split an inclusive page-id range into API-sized batches."""
    if size < 1:
        raise ValueError("size must be >= 1")
    if end < start:
        return []
    return [
        list(range(head, min(head + size, end + 1)))
        for head in range(start, end + 1, size)
    ]


def strip_namespace_prefix(value: str, namespace: str) -> str:
    """Drop a ``Namespace:`` prefix from a settings value.

    ``linked_template``/``category`` are documented without the prefix, but
    users routinely paste ``Template:Navbox`` or ``Category:Foo``; accepting
    both avoids the ``Template:Template:Navbox`` bug.
    """
    value = str(value).strip()
    prefix = f"{namespace}:"
    if value.lower().startswith(prefix.lower()):
        return value[len(prefix):].strip()
    return value


def disallowed_tags(present: set[str], *, safe: list[str], unsafe: list[str]) -> set[str]:
    """Which of the tags on a page violate the configured tag policy.

    ``unsafe_tag_list`` and ``safe_tag_list`` are mutually exclusive: the former
    is a deny-list, the latter an allow-list.  With both empty nothing is
    restricted.
    """
    if safe and unsafe:
        raise ValueError("safe_tag_list and unsafe_tag_list cannot both be set")

    tags = {tag.strip().lower() for tag in present}
    if unsafe:
        return tags & {tag.strip().lower() for tag in unsafe}
    if safe:
        return tags - {tag.strip().lower() for tag in safe}
    return set()


# ── Entry point ───────────────────────────────────────────────────────

def do_jobs() -> None:
    """Process every page in the todo list, holding the run lock."""
    configure_logging(
        log_level=settings.log_level,
        log_timestamps=settings.log_timestamp,
    )
    started = record_start_time()
    logger.info(f"Run started at {started.isoformat()}")

    if not lock():
        raise RuntimeError(
            f"Another YuGong process already holds {PROJECT_ROOT / 'data' / 'lock'}; "
            "refusing to run two bots at once."
        )

    try:
        _do_jobs_locked()
    finally:
        unlock()
        reporter.print_report()
        try:
            reporter.report()
        except Exception as exc:  # noqa: BLE001 - reporting must not mask the result
            logger.error(f"Could not send the run report: {exc}")


def _do_jobs_locked() -> None:
    settings.validate()

    # A production run normally loads the rules in confirm_settings(); doing it
    # here as well keeps do_jobs() self-sufficient when called directly.
    formatter.ensure_ruleset()

    if settings.enable_heartbeat and not _heartbeat_ok():
        return

    if not settings.submit_changes and not sys.stdin.isatty():
        raise RuntimeError(
            "submit_changes = false requires an interactive terminal: the bot "
            "would copy each page to the clipboard and wait for a human to "
            "paste it. Set submit_changes = true for unattended runs."
        )

    # Set api_endpoint from settings before anything touches the site.
    wiki.api_endpoint = settings.api_endpoint

    # Cheap read-only preflight through the raw API (which understands the
    # configured endpoint and detects WAF/CAPTCHA pages) before pywikibot's
    # heavier Site initialisation can fail with a less useful error.
    probe = wiki.api_query({"action": "query", "meta": "siteinfo", "format": "json"})
    if probe is None:
        raise RuntimeError(
            f"Could not reach the wiki API at {wiki.api_url}. Check api_endpoint "
            "and logs/wiki.log; a WAF/CAPTCHA challenge is reported there."
        )
    if "error" in probe:
        raise RuntimeError(
            f"The wiki API rejected the preflight request: {probe['error']}. "
            "Check MW_OAUTH_TOKEN and the bot account's rights."
        )

    _ = wiki.site  # triggers lazy init + OAuth validation

    manifest = Manifest(os.path.join(PROJECT_ROOT, "cache", f"{settings.wiki_tag}.json"))
    todo_list = _prepare_manifest(manifest, _get_todo_list())

    # Claim the day only now that the connection works and there is work to do,
    # so a failed connection does not block a retry later today.
    if settings.enable_heartbeat:
        record_heartbeat(
            file=daily_heartbeat_file(),
            content=heartbeat_content(wiki_tag=settings.wiki_tag),
        )

    for page_name in list(todo_list):
        try:
            handled = _process_single_page(page_name)
        except SafetyAbort:
            raise
        except (pywikibot.exceptions.NoPageError, pywikibot.exceptions.InvalidPageError):
            # The page was deleted or renamed after it entered the manifest.
            # Removing it prevents an endless "page not found" loop.
            message = f"{page_name}: page no longer exists; removed from the todo list"
            reporter.add("do_jobs", message)
            logger.warning(message)
            handled = True
        except Exception as exc:  # noqa: BLE001 - one bad page must not stop the run
            reporter.add("do_jobs", f"{page_name}: {type(exc).__name__}: {exc}")
            logger.error(f"[{page_name}] failed: {exc}")
            continue

        if not handled:
            # Skipped for safety: keep it queued so a later run retries it.
            continue

        manifest.data["todo"] = [
            name for name in manifest.data.get("todo", []) if name != page_name
        ]
        manifest.save()

    print("All done!")


def _heartbeat_ok() -> bool:
    """Return ``False`` when the bot has already run today."""
    token = heartbeat_content(wiki_tag=settings.wiki_tag)
    if not heartbeat_matches(file=daily_heartbeat_file(), content=token):
        return True

    message = f"YuGong already ran today ({token}); stopping to avoid editing twice."
    logger.warning(message)
    mailer.email("Yugong duplicate run detected!", message)
    return False


def _prepare_manifest(manifest: Manifest, todo_list: list[str]) -> list[str]:
    """Merge freshly discovered pages with the pages still queued from last time."""
    current_url = wiki.base_url or wiki.api_endpoint
    cached_raw = manifest.data.get("url")
    # Normalise the cached value too: older versions stored the api.php URL,
    # and comparing that verbatim against the base URL would abort a run after
    # an upgrade even though it is the same wiki.
    cached_url = (
        (normalize_base_url(str(cached_raw)) or str(cached_raw)) if cached_raw else ""
    )
    if cached_url and cached_url != current_url:
        raise ValueError(
            f"Instance Url does not match the one in cache ({cached_url!r} vs "
            f"{current_url!r}). You might need to change the wiki_tag in the "
            "settings.toml"
        )

    merged = sorted(set(manifest.data.get("todo", [])) | set(todo_list))
    manifest.data["url"] = current_url
    manifest.data["todo"] = merged
    manifest.save()
    return merged


def _get_todo_list() -> list[str]:
    """Collect the pages to process.

    Sources are combined: the ``page_id_start``/``page_id_end`` range, pages
    transcluding ``linked_template``, and members of ``category``.
    """
    todo: set[str] = set()

    page_range = settings.pageid_range()
    if page_range is not None:
        todo.update(_titles_for_pageids(*page_range))

    linked_template = strip_namespace_prefix(settings.linked_template, "Template")
    if linked_template:
        template_page = pywikibot.Page(wiki.site, f"Template:{linked_template}")
        transcluding = [page.title() for page in template_page.embeddedin(namespaces=[0])]
        logger.info(f"Template:{linked_template} is used by {len(transcluding)} pages")
        todo.update(transcluding)

    category_name = strip_namespace_prefix(settings.category, "Category")
    if category_name:
        category = pywikibot.Category(wiki.site, f"Category:{category_name}")
        todo.update(page.title() for page in category.members(namespaces=[0]))

    if not todo:
        raise ValueError(
            "No pages found for the configured page_id range, linked_template or "
            "category. Check the '# About Task' part of settings.toml."
        )

    return sorted(todo)


def _titles_for_pageids(start: int, end: int) -> list[str]:
    """Resolve a page-id range into titles, batching the API calls."""
    titles: list[str] = []
    for batch in pageid_batches(start, end, size=PAGEID_BATCH_SIZE):
        data = wiki.api_query(
            {
                "action": "query",
                "pageids": "|".join(str(page_id) for page_id in batch),
                "format": "json",
            }
        )
        if not data:
            continue

        pages = data.get("query", {}).get("pages")
        if not isinstance(pages, dict):
            logger.warning(f"Unexpected pageid query result for {batch[0]}..{batch[-1]}")
            continue

        for page in pages.values():
            if not isinstance(page, dict) or "missing" in page:
                continue
            title = page.get("title")
            if title:
                titles.append(str(title))

    return titles


# ── Per-page processing ───────────────────────────────────────────────

def _process_single_page(page_name: str) -> bool:
    """Process one page.

    Returns:
        ``True`` when the page is fully handled and can leave the todo list,
        ``False`` when it was skipped for a safety reason (and should be retried
        on a later run).
    """
    pwb_page = wiki.page(page_name)
    # ``Page.latest_revision`` requests exactly one revision *with* content, so
    # one API call yields both the text and the revid.  Do NOT use
    # ``latest_revision_id`` here: in pywikibot 11 it calls
    # ``revisions(rvdir=False)``, which makes the generator paginate the page's
    # ENTIRE history before returning.
    revision = getattr(pwb_page, "latest_revision")
    base_revid = int(revision.revid)
    content = str(revision.text or "")
    # pywikibot 11 returns a Namespace object here, whose ``str()`` is e.g.
    # ``":"`` for the main namespace — not a number.  ``int()`` yields the id.
    namespace_id = int(pwb_page.namespace())
    metadata: dict[str, str] = {
        "title": pwb_page.title(),
        "pageid": str(pwb_page.pageid),
        "revid": str(base_revid),
        "namespace": str(namespace_id),
        "permission": "",
    }

    wikitext = Wikitext(metadata)
    wikitext.parse(content)

    logger.info(f"Page: {page_name}")
    logger.debug(f"[{page_name}] before: {len(content)} chars")
    print(f"Begin processing {page_name}:")

    offending = disallowed_tags(
        {str(tag.tag) for tag in wikitext.tags()},
        safe=settings.safe_tag_list,
        unsafe=settings.unsafe_tag_list,
    )
    if offending:
        message = (
            f"{page_name} uses tag(s) {sorted(offending)} that the configured tag "
            "policy forbids"
        )
        if settings.is_dangerous_tag_unacceptable:
            raise SafetyAbort(f"{message}; is_dangerous_tag_unacceptable = true, aborting")
        reporter.add("safety", f"{message}; page skipped")
        logger.warning(message)
        return False

    steps, skipped_jobs = build_steps(wikitext)
    if skipped_jobs:
        logger.debug(f"[{page_name}] skipped wiki jobs: {skipped_jobs}")
    applied = apply_steps(wikitext, page_name, steps)

    new_text = str(wikitext.wikitext)
    logger.debug(f"[{page_name}] after: {len(new_text)} chars; applied: {applied}")

    if new_text == content:
        print(f"No changes made to {page_name}, continue.")
        return True

    max_diff = int(settings.max_acceptable_diff_size)
    if abs(len(content) - len(new_text)) > max_diff:
        message = (
            f"{page_name}: length changes by at least "
            f"{abs(len(content) - len(new_text))} characters, above "
            f"max_acceptable_diff_size={max_diff}; skipped"
        )
        reporter.add("safety", message)
        logger.warning(message)
        return False

    if len(content) + len(new_text) > MAX_DIFF_CHARS:
        message = (
            f"{page_name}: page is too large to diff safely "
            f"({len(content)} + {len(new_text)} chars); skipped"
        )
        reporter.add("safety", message)
        logger.warning(message)
        return False

    size = diff_size(content, new_text)
    if size > max_diff:
        message = (
            f"{page_name}: change of {size} characters exceeds "
            f"max_acceptable_diff_size={max_diff}; skipped"
        )
        reporter.add("safety", message)
        logger.warning(message)
        return False

    if settings.submit_changes:
        try:
            pwb_page.text = new_text
            pwb_page.save(
                summary=settings.edit_comment,
                bot=True,
                baserevid=base_revid,
                apply_cosmetic_changes=False,
            )
        except Exception as exc:  # noqa: BLE001 - report and keep the page queued
            reporter.add("submit", f"{page_name}: {type(exc).__name__}: {exc}")
            logger.error(f"Failed to submit {page_name}: {exc}")
            return False

        print(f"Successfully submitted changes to {page_name} ({size} chars changed)")
        logger.info(f"[{page_name}] submitted ({size} chars changed)")
        return True

    # Manual mode: clipboard + browser, the human pastes and saves.
    try:
        pyperclip.copy(new_text)
        copied = "copied to your clipboard"
    except Exception as exc:  # noqa: BLE001 - headless machines have no clipboard
        fallback = _save_manual_copy(page_name, new_text)
        copied = f"could not be copied ({type(exc).__name__}); saved to {fallback}"
        logger.warning(f"[{page_name}] clipboard unavailable: {exc}; wrote {fallback}")

    webbrowser.open(f"{wiki.base_url}index.php?title={quote(page_name)}&action=edit")
    print(f"{size} characters changed.")
    input(
        f"The new wikitext {copied}.\n"
        "Due to settings, you need to manually paste and submit it.\n"
        "Press any key to continue..."
    )
    return True


def _save_manual_copy(page_name: str, text: str) -> str:
    """Write *text* to ``cache/manual/<page>.wikitext`` and return the path."""
    safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", page_name).strip("_") or "page"
    # Titles can sanitise to the same name ("A/B" and "A:B"); the digest keeps
    # their copies apart instead of silently overwriting each other.
    digest = hashlib.sha1(page_name.encode("utf-8")).hexdigest()[:8]
    directory = os.path.join(PROJECT_ROOT, "cache", "manual")
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, f"{safe_name}_{digest}.wikitext")
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)
    return path
