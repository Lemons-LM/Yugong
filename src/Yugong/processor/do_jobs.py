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
import os
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

#: How many page ids to ask for in one API call when sweeping a page-id range.
PAGEID_BATCH_SIZE: int = 50

#: File remembering which UTC day the bot last ran (unattended runs only).
DAILY_HEARTBEAT_FILE: str = os.path.join(PROJECT_ROOT, "data", "bot", "heartbeat_daily")


class SafetyAbort(RuntimeError):
    """Raised when a page looks dangerous enough to stop the whole run."""


# ── Pure helpers ──────────────────────────────────────────────────────

def diff_size(old: str, new: str) -> int:
    """Characters added, removed or rewritten between two revisions.

    Used to enforce ``max_acceptable_diff_size`` before anything is submitted.
    """
    if old == new:
        return 0

    matcher = difflib.SequenceMatcher(None, old, new, autojunk=False)
    total = 0
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag != "equal":
            total += max(i2 - i1, j2 - j1)
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

    # Set api_endpoint from settings before anything touches the site.
    wiki.api_endpoint = settings.api_endpoint
    _ = wiki.site  # triggers lazy init + OAuth validation

    manifest = Manifest(os.path.join(PROJECT_ROOT, "cache", f"{settings.wiki_tag}.json"))
    todo_list = _prepare_manifest(manifest, _get_todo_list())

    # Claim the day only now that the connection works and there is work to do,
    # so a failed connection does not block a retry later today.
    if settings.enable_heartbeat:
        record_heartbeat(
            file=DAILY_HEARTBEAT_FILE,
            content=heartbeat_content(wiki_tag=settings.wiki_tag),
        )

    for page_name in list(todo_list):
        try:
            handled = _process_single_page(page_name)
        except SafetyAbort:
            raise
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
    if not heartbeat_matches(file=DAILY_HEARTBEAT_FILE, content=token):
        return True

    message = f"YuGong already ran today ({token}); stopping to avoid editing twice."
    logger.warning(message)
    mailer.email("Yugong duplicate run detected!", message)
    return False


def _prepare_manifest(manifest: Manifest, todo_list: list[str]) -> list[str]:
    """Merge freshly discovered pages with the pages still queued from last time."""
    cached_url = manifest.data.get("url")
    if cached_url and cached_url != wiki.api_endpoint:
        raise ValueError(
            "Instance Url does not match the one in cache. "
            "You might need to change the wiki_tag in the settings.toml"
        )

    merged = sorted(set(manifest.data.get("todo", [])) | set(todo_list))
    manifest.data["url"] = wiki.api_endpoint
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

    if settings.linked_template:
        template_page = pywikibot.Page(wiki.site, f"Template:{settings.linked_template}")
        transcluding = [page.title() for page in template_page.embeddedin(namespaces=[0])]
        logger.info(f"Template:{settings.linked_template} is used by {len(transcluding)} pages")
        todo.update(transcluding)

    if settings.category:
        category = pywikibot.Category(wiki.site, f"Category:{settings.category}")
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
    metadata: dict[str, str] = {
        "title": pwb_page.title(),
        "pageid": str(pwb_page.pageid),
        "revid": str(pwb_page.latest_revision_id),
        "namespace": str(pwb_page.namespace()),
        "permission": "",
    }

    content = pwb_page.text
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

    size = diff_size(content, new_text)
    if size > int(settings.max_acceptable_diff_size):
        message = (
            f"{page_name}: change of {size} characters exceeds "
            f"max_acceptable_diff_size={settings.max_acceptable_diff_size}; skipped"
        )
        reporter.add("safety", message)
        logger.warning(message)
        return False

    if settings.submit_changes:
        try:
            pwb_page.text = new_text
            pwb_page.save(summary=settings.edit_comment, bot=True)
        except Exception as exc:  # noqa: BLE001 - report and keep the page queued
            reporter.add("submit", f"{page_name}: {type(exc).__name__}: {exc}")
            logger.error(f"Failed to submit {page_name}: {exc}")
            return False

        print(f"Successfully submitted changes to {page_name} ({size} chars changed)")
        logger.info(f"[{page_name}] submitted ({size} chars changed)")
        return True

    # Manual mode: clipboard + browser, the human pastes and saves.
    pyperclip.copy(new_text)
    webbrowser.open(f"{wiki.api_endpoint}index.php?title={quote(page_name)}&action=edit")
    print(f"{size} characters changed.")
    input(
        "The new wikitext has been copied to your clipboard.\n"
        "Due to settings, you need to manually paste and submit it.\n"
        "Press any key to continue..."
    )
    return True
