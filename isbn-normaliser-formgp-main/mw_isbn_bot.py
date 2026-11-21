#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Callable

import requests

from mw_bot_core import (
    _MAXLAG,
    _TIMEOUT,
    _parse_bool_env,
    allowbots,
    api_post_json,
    build_session,
    edit_page_by_title,
    edit_page_text,
    extract_baserevid,
    extract_main_content,
    fetch_pages_by_pageids_with_revisions,
    fetch_transcluded_pages_with_revisions,
    get_csrf_token,
    load_env_files,
    login_with_bot_password,
    normalise_assert_user,
    purge_embedding_pages,
)
from isbn_template_normalise import (
    BOOKSOURCE_PAGE_ALIASES,
    ChangeReport,
    canonicalise_title_fragment,
    normalise_isbn_templates,
)

DEFAULT_USER_AGENT = (
    "ISBNNormaliser-Bot/1.1 "
    "(https://github.com/kelly/ISBN-normaliser; 75931686+Kelly-Hsueh@users.noreply.github.com) "
    "requests/2.33.x")
DEFAULT_WIKI_API = "https://mzh.moegirl.org.cn/api.php"
_FALLBACK_TEMPLATE_TITLE = "Template:ISBN|Template:ISBNT|Template:Cite book"
_FALLBACK_XML_PATH = "RangeMessage.xml"
_FALLBACK_EDIT_TAGS = "Bot"
_DEFAULT_SUMMARY = (
    "根据 ISO 2108:2017（https://www.iso.org/standard/65483.html ）自动"
    "调整ISBN（若阁下对此次修改感到疑惑，可以前往 https://grp.isbn-international.org/"
    " 查找出版社前缀信息）")

# ISBN-bot specific operational constants.
_EDIT_INTERVAL: float = 0.2
_USE_BOT_FLAG: bool = True

# Status-page constants (fun little feature): the bot advertises its own
# run state on a subpage of its own userpage. Special:MyPage is a client-side
# redirect and cannot be targeted by action=edit directly, so the real
# title is built at runtime as f"User:{assert_user}/{_STATUS_SUBPAGE}".
_STATUS_SUBPAGE: str = "Status"
_STATUS_BUSY: str = "busy"
_STATUS_IDLE: str = "holiday"
_STATUS_SUMMARY_TEMPLATE: str = "修改状态为 - {status}"

# Debug-only override: when non-empty, only these pageids are fetched and processed.
# Example: DEBUG_TARGET_PAGEIDS = [12345, 67890]
DEBUG_TARGET_PAGEIDS: list[int] = []

# Query strategy registry.  Values are canonical names; keys include short aliases.
QUERY_ALIASES: dict[str, str] = {
    "transcludedin": "transcludedin",
    "ti": "transcludedin",
    "booksource-search": "booksource-search",
    "booksource": "booksource-search",
    "bs": "booksource-search",
}

# ---------------------------------------------------------------------------
# Status page helper
# ---------------------------------------------------------------------------


def build_status_page_title(assert_user: str) -> str:
    """Build the real (non-Special:) status subpage title for *assert_user*.

    Special:MyPage/Status is a client-side redirect to the current user's
    own userpage and cannot be targeted by action=edit, so we resolve it
    to the concrete User: page ourselves.
    """
    return f"User:{assert_user}/{_STATUS_SUBPAGE}"


def update_status_page(
    session: requests.Session,
    wiki_api: str,
    csrf_token: str,
    assert_user: str,
    status: str,
    dry_run: bool,
    edit_tags: str,
) -> None:
    """Overwrite the bot's status subpage with *status*, best-effort.

    This is a cosmetic feature: failures are logged but never abort the
    bot's main workflow.
    """
    title = build_status_page_title(assert_user)
    summary = _STATUS_SUMMARY_TEMPLATE.format(status=status)

    if dry_run:
        print(f"[DRY-RUN][STATUS] {title} -> {status!r}")
        return

    try:
        edit_page_by_title(
            session=session,
            wiki_api=wiki_api,
            title=title,
            text=status,
            summary=summary,
            csrf_token=csrf_token,
            assert_user=assert_user,
            bot=_USE_BOT_FLAG,
            tags=edit_tags,
        )
        print(f"[STATUS] {title} -> {status!r}")
    except Exception as exc:
        print(
            f"\033[93m[WARNING] Failed to update status page to {status!r}: {exc}\033[0m",
            file=sys.stderr,
        )
        return

    # User: namespace pages (unlike Template:) don't auto-invalidate the
    # parser cache of pages transcluding them, so purge explicitly.
    try:
        purged_count = purge_embedding_pages(
            session=session,
            wiki_api=wiki_api,
            title=title,
        )
        print(
            f"[STATUS] purged {purged_count} page(s) embedding \'/{_STATUS_SUBPAGE}\'"
        )
    except Exception as exc:
        print(
            f"\033[93m[WARNING] Failed to purge pages embedding "
            f"\'/{_STATUS_SUBPAGE}\': {exc}\033[0m",
            file=sys.stderr,
        )


# ---------------------------------------------------------------------------
# Page skip logic
# ---------------------------------------------------------------------------


def is_underconstruction(text: str) -> bool:
    pattern = r"\{\{(施工中|[编編][辑輯]中|inuse)(?:\|[^}]*)?\}\}"
    return bool(re.search(pattern, text, flags=re.IGNORECASE))


def get_skip_reason(content: str, assert_user: str) -> str | None:
    if not allowbots(content, assert_user):
        return "bots"
    return "inuse" if is_underconstruction(content) else None


# ---------------------------------------------------------------------------
# Query strategies
# ---------------------------------------------------------------------------


def search_insource_pages(
    session: requests.Session,
    wiki_api: str,
    search_term: str,
) -> set[int]:
    """Run a single insource: search and return all matching pageids.

    Handles API continuation automatically.
    """
    pageids: set[int] = set()
    request_data: dict[str, Any] = {
        "action": "query",
        "format": "json",
        "list": "search",
        "formatversion": "2",
        "srsearch": f'insource:"{search_term}"',
        "srnamespace": "*",
        "srlimit": "max",
        "srprop": "",
        "maxlag": _MAXLAG,
    }

    while True:
        data = api_post_json(
            session=session,
            wiki_api=wiki_api,
            data=request_data,
            timeout=_TIMEOUT,
            error_context=f"Failed to search insource:{search_term!r}",
        )
        if "error" in data:
            raise RuntimeError(
                f"API error on insource search for {search_term!r}: {data['error']}"
            )

        for result in data.get("query", {}).get("search", []) or []:
            if not isinstance(result, dict):
                continue
            pageid = result.get("pageid")
            if isinstance(pageid, int) and pageid > 0:
                pageids.add(pageid)

        cont = data.get("continue")
        if not isinstance(cont, dict):
            break
        request_data |= cont

    return pageids


def collect_booksource_search_pageids(
    session: requests.Session,
    wiki_api: str,
) -> list[int]:
    """Search every alias in BOOKSOURCE_PAGE_ALIASES via insource:.

    Returns a deduplicated list of pageids across all alias searches.
    """
    all_pageids: set[int] = set()
    for alias in sorted(BOOKSOURCE_PAGE_ALIASES):
        print(f"Searching insource:{alias!r} ...")
        try:
            found = search_insource_pages(
                session=session,
                wiki_api=wiki_api,
                search_term=alias,
            )
        except RuntimeError as exc:
            print(
                f"\033[91m[WARNING] insource search failed for {alias!r}: {exc}\033[0m",
                file=sys.stderr,
            )
            found = set()
        print(f"  \u2192 {len(found)} pages")
        all_pageids |= found
    print(f"Total unique pages (booksource-search): {len(all_pageids)}")
    return list(all_pageids)


def _fetch_by_booksource_search(
    session: requests.Session,
    wiki_api: str,
    template_title: str,  # unused; present for _FetchFn signature compatibility
) -> tuple[list[int], dict[int, dict[str, Any]], str]:
    raw_pageids = collect_booksource_search_pageids(
        session=session,
        wiki_api=wiki_api,
    )
    return fetch_pages_by_pageids_with_revisions(
        session=session,
        wiki_api=wiki_api,
        pageids=raw_pageids,
    )


# Callable type alias for query strategy functions.
_FetchFn = Callable[
    [requests.Session, str, str],
    tuple[list[int], dict[int, dict[str, Any]], str],
]

_QUERY_STRATEGIES: dict[str, _FetchFn] = {
    "transcludedin": fetch_transcluded_pages_with_revisions,
    "booksource-search": _fetch_by_booksource_search,
}

# ---------------------------------------------------------------------------
# ISBN-specific helpers
# ---------------------------------------------------------------------------


def resolve_template_aliases(
    session: requests.Session,
    wiki_api: str,
    template_titles: str | None,
) -> dict[str, str]:
    preferred: dict[str, str] = {}
    if template_titles:
        for title in template_titles.split("|"):
            frag = title.rsplit(":", 1)[-1].strip()
            if not frag:
                continue
            if key := canonicalise_title_fragment(frag):
                preferred.setdefault(key, frag)
    if not template_titles:
        preferred = {}

    try:
        data = api_post_json(
            session=session,
            wiki_api=wiki_api,
            data={
                "action": "query",
                "format": "json",
                "prop": "redirects",
                "titles": template_titles,
                "redirects": 1,
                "formatversion": "2",
                "rdprop": "title",
            },
            timeout=_TIMEOUT,
            error_context="Failed to resolve template redirects",
        )
    except Exception:
        return preferred

    pages = data.get("query", {}).get("pages", [])
    if not isinstance(pages, list):
        return preferred

    for page in pages:
        if not isinstance(page, dict):
            continue
        page_title = page.get("title")
        if not isinstance(page_title, str):
            continue
        page_frag = page_title.rsplit(":", 1)[-1].strip()
        if not page_frag:
            continue
        page_key = canonicalise_title_fragment(page_frag)
        preferred.setdefault(page_key, page_frag)

        for rd in page.get("redirects", []) or []:
            rd_title = rd.get("title")
            if not isinstance(rd_title, str):
                continue
            rd_frag = rd_title.rsplit(":", 1)[-1].strip()
            if not rd_frag:
                continue
            rd_key = canonicalise_title_fragment(rd_frag)
            preferred.setdefault(rd_key, preferred.get(page_key, page_frag))

    return preferred


def normalise_page_isbn_templates(
    content: str,
    args: argparse.Namespace,
    xml_path: Path,
    template_preferred_map: dict[str, str] | None = None,
) -> tuple[str, ChangeReport]:
    return normalise_isbn_templates(
        content,
        xml_path,
        convert_10_to_13=args.to13,
        rehyphenate_equal_label=args.rehyphenate_equal_label,
        template_preferred_map=template_preferred_map,
    )


def compose_summary(report: ChangeReport, iso_summary: str) -> str:
    """Build a per-page edit summary from the change breakdown.

    Components (joined by fullwidth semicolons):
      - booksource link replacement (if any)
      - ISBN-10 → ISBN-13 conversion (if any)
      - {{ISBNT}} merge (if any)
      - ISO 2108 hyphenation notice (always, since every change touches ISBNs)
    """
    parts: list[str] = []
    if report.booksource_links:
        parts.append(
            "替换&lsqb;&lsqb;Special:网络书源/&rsqb;&rsqb;为{{[[T:ISBN|ISBN]]}}")
    if report.isbn10_converted:
        parts.append("将 ISBN-10 转换为 ISBN-13")
    if report.isbnt_merged:
        parts.append("自动使用{{[[T:ISBNT|ISBNT]]}}")
    parts.append(iso_summary)
    return "；".join(parts)


# ---------------------------------------------------------------------------
# Page processing
# ---------------------------------------------------------------------------


def _try_apply_changes(
    session: requests.Session,
    wiki_api: str,
    pageid: int,
    title: str,
    new_text: str,
    replacements: int,
    args: argparse.Namespace,
    csrf_token: str,
    assert_user: str,
    baserevid: str,
    start_timestamp: str,
    summary: str,
) -> tuple[bool, bool]:
    """Apply changes to page (dry-run or real edit).

    Returns: (changed_flag, failed_flag)
    """
    if args.dry_run:
        print(
            f"[DRY-RUN][CHANGE] pageid={pageid} title={title} replacements={replacements}"
        )
        return True, False

    try:
        edit_page_text(
            session=session,
            wiki_api=wiki_api,
            pageid=pageid,
            text=new_text,
            summary=summary,
            csrf_token=csrf_token,
            assert_user=assert_user,
            bot=_USE_BOT_FLAG,
            baserevid=baserevid,
            starttimestamp=start_timestamp,
            tags=args.edit_tags,
        )
        print(
            f"[EDITED] pageid={pageid} title={title} replacements={replacements}"
        )
        time.sleep(_EDIT_INTERVAL)
        return True, False
    except RuntimeError as exc:
        if "editconflict" not in str(exc):
            print(
                f"\033[91m[FAILED] pageid={pageid} title={title} error={exc}\033[0m",
                file=sys.stderr)
            return False, True
        print(f"\033[93m[SKIP][conflict] pageid={pageid} title={title}\033[0m")
        return False, False
    except Exception as exc:
        print(
            f"\033[91m[FAILED] pageid={pageid} title={title} error={exc}\033[0m",
            file=sys.stderr)
        return False, True


def process_pages(
    args: argparse.Namespace,
    session: requests.Session,
    wiki_api: str,
    bot_username: str,
    xml_path: Path,
    pageids: list[int],
    pages_by_id: dict[int, dict[str, Any]],
    csrf_token: str,
    start_timestamp: str = "",
    template_preferred_map: dict[str, str] | None = None,
) -> tuple[int, int, int, int]:
    processed = 0
    skipped_bots = 0
    changed = 0
    failed = 0
    assert_user = normalise_assert_user(bot_username)

    for pageid in pageids:
        page = pages_by_id.get(pageid)
        if page is None:
            continue

        title = page.get("title", "")
        content = extract_main_content(page)
        if content is None:
            continue

        baserevid = extract_baserevid(page)
        processed += 1

        skip_reason = get_skip_reason(content, assert_user)
        if skip_reason is not None:
            skipped_bots += 1
            print(
                f"\033[93m[SKIP][{skip_reason}] pageid={pageid} title={title}\033[0m"
            )
            continue

        new_text, report = normalise_page_isbn_templates(
            content,
            args,
            xml_path,
            template_preferred_map=template_preferred_map,
        )
        if not report.total or new_text == content:
            continue

        if args.max_edits is not None and changed >= args.max_edits:
            print(
                f"\033[93m[LIMIT] Reached max_edits limit ({args.max_edits}), stopping.\033[0m"
            )
            break

        page_summary = compose_summary(report, args.summary)

        changed_flag, failed_flag = _try_apply_changes(
            session=session,
            wiki_api=wiki_api,
            pageid=pageid,
            title=title,
            new_text=new_text,
            replacements=report.total,
            args=args,
            csrf_token=csrf_token,
            assert_user=assert_user,
            baserevid=baserevid,
            start_timestamp=start_timestamp,
            summary=page_summary,
        )
        if changed_flag:
            changed += 1
        if failed_flag:
            failed += 1

    return processed, skipped_bots, changed, failed


# ---------------------------------------------------------------------------
# Runtime config & workflow
# ---------------------------------------------------------------------------


def parse_runtime_config(
        args: argparse.Namespace) -> tuple[str, str, str, str]:
    """Resolve runtime config: CLI flag > env var > built-in default."""
    wiki_api = args.wiki_api or os.environ.get("WIKI_API", DEFAULT_WIKI_API)
    bot_username = (args.bot_username
                    or os.environ.get("BOT_USERNAME", "")).strip()
    bot_password = (args.bot_password
                    or os.environ.get("BOT_PASSWORD", "")).strip()
    user_agent = args.user_agent or os.environ.get("USER_AGENT",
                                                   DEFAULT_USER_AGENT)

    if not wiki_api:
        raise RuntimeError(
            "WIKI_API is required (--wiki-api flag, or WIKI_API in .env).")
    if not bot_username:
        raise RuntimeError(
            "BOT_USERNAME is required (--bot-username flag, or BOT_USERNAME in .env.pwd)."
        )
    if not bot_password:
        raise RuntimeError(
            "BOT_PASSWORD is required (--bot-password flag, or BOT_PASSWORD in .env.pwd)."
        )
    return wiki_api, bot_username, bot_password, user_agent


def validate_xml_path(xml_arg: str) -> Path:
    xml_path = Path(xml_arg)
    if not xml_path.exists():
        raise RuntimeError(f"XML file not found: {xml_path}")
    return xml_path


def run_normalisation_workflow(
    args: argparse.Namespace,
    session: requests.Session,
    wiki_api: str,
    bot_username: str,
    bot_password: str,
    xml_path: Path,
) -> int:
    login_with_bot_password(
        session=session,
        wiki_api=wiki_api,
        bot_username=bot_username,
        bot_password=bot_password,
    )
    assert_user = normalise_assert_user(bot_username)
    csrf_token = get_csrf_token(
        session=session,
        wiki_api=wiki_api,
        assert_user=assert_user,
    )

    # Fun little feature: announce ourselves as busy on our status subpage
    # as soon as we're logged in and hold a CSRF token.
    update_status_page(
        session=session,
        wiki_api=wiki_api,
        csrf_token=csrf_token,
        assert_user=assert_user,
        status=_STATUS_BUSY,
        dry_run=args.dry_run,
        edit_tags=args.edit_tags,
    )

    try:
        template_preferred_map = resolve_template_aliases(
            session=session,
            wiki_api=wiki_api,
            template_titles=args.template_title,
        )

        if DEBUG_TARGET_PAGEIDS:
            pageids, pages_by_id, curtimestamp = fetch_pages_by_pageids_with_revisions(
                session=session,
                wiki_api=wiki_api,
                pageids=DEBUG_TARGET_PAGEIDS,
            )
            print(
                f"Fetched pages with revisions (debug pageids): {len(pages_by_id)}"
            )
        else:
            fetch_fn = _QUERY_STRATEGIES[args.query]
            pageids, pages_by_id, curtimestamp = fetch_fn(
                session,
                wiki_api,
                args.template_title,
            )
            print(f"Fetched pages ({args.query}): {len(pages_by_id)}")

        processed, skipped_bots, changed, failed = process_pages(
            args=args,
            session=session,
            wiki_api=wiki_api,
            bot_username=bot_username,
            xml_path=xml_path,
            pageids=pageids,
            pages_by_id=pages_by_id,
            csrf_token=csrf_token,
            start_timestamp=curtimestamp,
            template_preferred_map=template_preferred_map,
        )

        print(f"Done. processed={processed}, changed={changed}, "
              f"skipped_bots={skipped_bots}, failed={failed}")
        return 0 if failed == 0 else 2
    finally:
        # Always try to flip back to idle before we exit, success or not.
        update_status_page(
            session=session,
            wiki_api=wiki_api,
            csrf_token=csrf_token,
            assert_user=assert_user,
            status=_STATUS_IDLE,
            dry_run=args.dry_run,
            edit_tags=args.edit_tags,
        )


def execute(args: argparse.Namespace) -> int:
    try:
        load_env_files()

        # Resolve query strategy: CLI arg > DEFAULT_QUERY env var > 'transcludedin'
        if args.query is None:
            args.query = os.environ.get("DEFAULT_QUERY", "transcludedin")
        if args.query not in QUERY_ALIASES:
            valid = ", ".join(sorted(set(QUERY_ALIASES.values())))
            raise RuntimeError(
                f"Unknown query strategy: {args.query!r}. Valid: {valid}")
        args.query = QUERY_ALIASES[args.query]

        # Boolean flags: CLI flag (True) wins; otherwise fall back to env var.
        if not args.to13:
            args.to13 = _parse_bool_env("TO13", default=False)
        if not args.rehyphenate_equal_label:
            args.rehyphenate_equal_label = _parse_bool_env(
                "REHYPHENATE_EQUAL_LABEL", default=False)

        # String args: non-empty CLI value > env var > built-in default.
        if not args.template_title:
            args.template_title = os.environ.get("TEMPLATE_TITLE",
                                                 _FALLBACK_TEMPLATE_TITLE)
        if not args.xml:
            args.xml = os.environ.get("XML_PATH", _FALLBACK_XML_PATH)
        if not args.summary:
            args.summary = os.environ.get("SUMMARY", _DEFAULT_SUMMARY)
        # edit_tags uses `is None` (not `not`) so that an explicit empty string
        # from the CLI is honoured as "apply no tags" rather than overridden by
        # the env default.
        if args.edit_tags is None:
            args.edit_tags = os.environ.get("EDIT_TAGS", _FALLBACK_EDIT_TAGS)

        wiki_api, bot_username, bot_password, user_agent = parse_runtime_config(
            args)
        xml_path = validate_xml_path(args.xml)
        session = build_session(user_agent)

        return run_normalisation_workflow(
            args=args,
            session=session,
            wiki_api=wiki_api,
            bot_username=bot_username,
            bot_password=bot_password,
            xml_path=xml_path,
        )
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="MediaWiki runner for ISBN template normalisation.")
    parser.add_argument(
        "--xml",
        default=None,
        help="Path to ISBNRangeMessage XML file. Overrides XML_PATH in .env.",
    )
    parser.add_argument(
        "-to13",
        "--to13",
        action="store_true",
        default=False,
        help="Convert ISBN-10 template values to ISBN-13 before output. "
        "Overrides TO13 in .env.",
    )
    parser.add_argument(
        "--rehyphenate-equal-label",
        action="store_true",
        default=False,
        help=(
            "When template param1 and param2 are semantically the same ISBN, "
            "replace the template with {{ISBNT|$1}} and keep parameter 1 "
            "hyphenated. Overrides REHYPHENATE_EQUAL_LABEL in .env."),
    )
    parser.add_argument(
        "--query",
        "-q",
        choices=list(QUERY_ALIASES),
        metavar="{transcludedin|ti|booksource-search|booksource|bs}",
        default=None,
        help="Page fetch strategy. "
        "Default: DEFAULT_QUERY env var (from .env), or 'transcludedin' if unset.",
    )
    parser.add_argument(
        "--wiki-api",
        default=None,
        help="MediaWiki API endpoint. Overrides WIKI_API in .env.",
    )
    parser.add_argument(
        "--bot-username",
        default=None,
        help="Bot username. Overrides BOT_USERNAME in .env.pwd.",
    )
    parser.add_argument(
        "--bot-password",
        default=None,
        help="Bot password. Overrides BOT_PASSWORD in .env.pwd.",
    )
    parser.add_argument(
        "--user-agent",
        default=None,
        help="HTTP User-Agent. Overrides USER_AGENT in .env.",
    )
    parser.add_argument(
        "--template-title",
        default=None,
        help="Template title(s) for transclusion lookup. "
        "Overrides TEMPLATE_TITLE in .env.",
    )
    parser.add_argument(
        "--summary",
        default=None,
        help="ISO 2108 notice appended to every edit summary. "
        "Overrides SUMMARY in .env.",
    )
    parser.add_argument(
        "--edit-tags",
        default=None,
        help="Change tag(s) applied to edits, pipe-separated (e.g. 'Bot|test'). "
        "Pass an empty string to apply no tag. "
        "Overrides EDIT_TAGS in .env.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run full workflow but do not save edits.",
    )
    parser.add_argument(
        "--max-edits",
        type=int,
        default=None,
        help="Maximum number of edits to perform. Omit for unlimited.",
    )
    return parser


def main() -> int:
    return execute(build_parser().parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
