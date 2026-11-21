#!/usr/bin/env python3
"""Generic MediaWiki bot infrastructure: env loading, HTTP, auth, page fetch/edit.

No project-specific logic lives here.
"""
from __future__ import annotations

import contextlib
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Callable

import brotli
import requests

# ---------------------------------------------------------------------------
# Operational constants — not exposed as CLI flags or env vars.
# ---------------------------------------------------------------------------

_MAXLAG: int = 3
_TIMEOUT: int = 30
_MAX_RETRIES: int = 3
_RETRY_BACKOFF_BASE: float = 2.0

_TRANSIENT_ERRORS = (
    requests.exceptions.Timeout,
    requests.exceptions.ConnectionError,
    requests.exceptions.ChunkedEncodingError,
)

# ---------------------------------------------------------------------------
# Environment loading
# ---------------------------------------------------------------------------


def load_env_file(env_path: str) -> None:
    """Load key=value pairs from *env_path* into os.environ via setdefault.

    Values already present in os.environ (e.g. injected by GitHub Actions
    via ``env:``) are never overwritten.
    """
    path = Path(env_path)
    if not path.exists() or not path.is_file():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue

        if ((value.startswith('"') and value.endswith('"'))
                or (value.startswith("'") and value.endswith("'"))):
            value = value[1:-1]

        os.environ.setdefault(key, value)


def load_env_files() -> None:
    """Load both env files with the correct priority order.

    Priority (highest to lowest):
      1. Variables already in os.environ  (e.g. GHA ``env:`` injection)
      2. .env.pwd                         (private credentials, gitignored)
      3. .env                             (public config, version-controlled)
    """
    load_env_file(".env.pwd")
    load_env_file(".env")


def _parse_bool_env(key: str, *, default: bool) -> bool:
    """Read a boolean from os.environ[key].

    Accepts 1/true/yes -> True, 0/false/no -> False, absent/empty -> default.
    """
    raw = os.environ.get(key, "").strip().lower()
    if not raw:
        return default
    if raw in ("1", "true", "yes"):
        return True
    if raw in ("0", "false", "no"):
        return False
    raise RuntimeError(
        f"Environment variable {key!r} must be true/false/1/0/yes/no, got {raw!r}."
    )


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------


def _request_with_retry(
    make_request: Callable[[], requests.Response],
    error_context: str,
) -> requests.Response:
    """Retry *make_request* on transient network errors with backoff.

    Only retries on connection-level failures (timeout, connection reset,
    chunked encoding errors) — not on HTTP error status codes or JSON
    decoding issues, which are handled by their respective callers.
    """
    last_exc: Exception | None = None
    for attempt in range(_MAX_RETRIES + 1):
        try:
            return make_request()
        except _TRANSIENT_ERRORS as exc:
            last_exc = exc
            if attempt >= _MAX_RETRIES:
                break
            wait = _RETRY_BACKOFF_BASE * (2**attempt)
            print(
                f"[RETRY] {error_context}: attempt {attempt + 1} failed ({last_exc}); "
                f"retrying in {wait:.1f}s",
                file=sys.stderr,
            )
            time.sleep(wait)
    assert last_exc is not None
    raise last_exc


def safe_get_json(response: requests.Response) -> dict[str, Any]:
    try:
        data = response.json()
    except ValueError as exc:
        raise RuntimeError(
            f"API returned non-JSON response, HTTP {response.status_code}"
        ) from exc
    if not isinstance(data, dict):
        raise RuntimeError("API JSON response is not an object.")
    return data


def parse_response_json(response: requests.Response) -> dict[str, Any]:
    # 1) Normal path: requests handles JSON (and often compression) for us.
    with contextlib.suppress(RuntimeError):
        return safe_get_json(response)

    # 2) Fallback: some endpoints return brotli bytes without reliable headers.
    with contextlib.suppress(brotli.error, UnicodeDecodeError,
                             json.JSONDecodeError):
        decoded = brotli.decompress(response.content).decode("utf-8")
        data = json.loads(decoded)
        if isinstance(data, dict):
            return data

    preview = response.text[:160].replace("\n", " ")
    raise RuntimeError(
        f"API returned non-JSON response, HTTP {response.status_code}, body={preview!r}"
    )


def build_session(user_agent: str) -> requests.Session:
    session = requests.Session()
    session.headers.update({"User-Agent": user_agent})
    return session


def api_get_json(
    session: requests.Session,
    wiki_api: str,
    params: dict[str, Any],
    timeout: int,
    error_context: str,
) -> dict[str, Any]:
    try:
        response = _request_with_retry(
            lambda: session.get(wiki_api, params=params, timeout=timeout),
            error_context,
        )
        response.raise_for_status()
        return parse_response_json(response)
    except Exception as exc:
        raise RuntimeError(f"{error_context}: {exc}") from exc


def api_post_json(
    session: requests.Session,
    wiki_api: str,
    data: dict[str, Any],
    timeout: int,
    error_context: str,
) -> dict[str, Any]:
    try:
        response = _request_with_retry(
            lambda: session.post(wiki_api, data=data, timeout=timeout),
            error_context,
        )
        response.raise_for_status()
        return parse_response_json(response)
    except Exception as exc:
        raise RuntimeError(f"{error_context}: {exc}") from exc


# ---------------------------------------------------------------------------
# MediaWiki auth
# ---------------------------------------------------------------------------


def get_login_token(
    session: requests.Session,
    wiki_api: str,
) -> str:
    data = api_get_json(
        session=session,
        wiki_api=wiki_api,
        params={
            "action": "query",
            "meta": "tokens",
            "type": "login",
            "format": "json",
            "maxlag": _MAXLAG,
        },
        timeout=_TIMEOUT,
        error_context="Failed to fetch login token",
    )
    token = data.get("query", {}).get("tokens", {}).get("logintoken")
    if not isinstance(token, str) or not token:
        raise RuntimeError(f"Login token missing: {data}")
    return token


def normalise_assert_user(bot_username: str) -> str:
    # MediaWiki assertuser does not accept suffixes like @group or @host.
    return bot_username.split("@", 1)[0]


def login_with_bot_password(
    session: requests.Session,
    wiki_api: str,
    bot_username: str,
    bot_password: str,
) -> None:
    login_token = get_login_token(session=session, wiki_api=wiki_api)
    result = api_post_json(
        session=session,
        wiki_api=wiki_api,
        data={
            "action": "login",
            "lgname": bot_username,
            "lgpassword": bot_password,
            "lgtoken": login_token,
            "format": "json",
            "maxlag": _MAXLAG,
        },
        timeout=_TIMEOUT,
        error_context="Login request failed",
    )
    if result.get("login", {}).get("result") != "Success":
        raise RuntimeError(f"Login failed: {result}")


def get_csrf_token(
    session: requests.Session,
    wiki_api: str,
    assert_user: str,
) -> str:
    data = api_get_json(
        session=session,
        wiki_api=wiki_api,
        params={
            "action": "query",
            "meta": "tokens",
            "format": "json",
            "assertuser": assert_user,
            "maxlag": _MAXLAG,
        },
        timeout=_TIMEOUT,
        error_context="Failed to fetch CSRF token",
    )
    token = data.get("query", {}).get("tokens", {}).get("csrftoken")
    if not isinstance(token, str) or not token:
        raise RuntimeError(f"CSRF token missing: {data}")
    return token


# ---------------------------------------------------------------------------
# Page helpers
# ---------------------------------------------------------------------------


def allowbots(text: str, user: str) -> bool:
    escaped_user = re.escape(user)
    pattern = (r"\{\{(nobots|bots\|"
               r"(allow=none|deny=.*?" + escaped_user + r".*?"
               r"|optout=all|deny=all))\}\}")
    return not re.search(pattern, text, flags=re.IGNORECASE)


def extract_main_content(page: dict[str, Any]) -> str | None:
    revisions = page.get("revisions")
    if not isinstance(revisions, list) or not revisions:
        return None
    rev0 = revisions[0]
    if not isinstance(rev0, dict):
        return None
    slots = rev0.get("slots")
    if not isinstance(slots, dict):
        content = rev0.get("content")
        return content if isinstance(content, str) else None
    main = slots.get("main")
    if not isinstance(main, dict):
        return None
    content = main.get("content")
    return content if isinstance(content, str) else None


def extract_baserevid(page: dict[str, Any]) -> str:
    revisions = page.get("revisions")
    if not isinstance(revisions, list) or not revisions:
        return ""
    rev0 = revisions[0]
    if not isinstance(rev0, dict):
        return ""
    revid = rev0.get("revid")
    return str(revid) if revid is not None else ""


# ---------------------------------------------------------------------------
# Paginated fetch helpers
# ---------------------------------------------------------------------------


def _merge_generated_pages_with_revisions(
    data: dict[str, Any],
    pageids: list[int],
    seen: set[int],
    pages_by_id: dict[int, dict[str, Any]],
) -> None:
    pages = data.get("query", {}).get("pages", [])
    if not isinstance(pages, list):
        return

    for page in pages:
        if not isinstance(page, dict):
            continue
        pageid = page.get("pageid")
        if not isinstance(pageid, int):
            continue

        if pageid not in seen:
            seen.add(pageid)
            pageids.append(pageid)

        merged = dict(pages_by_id.get(pageid, {}))
        for key, value in page.items():
            if key == "revisions":
                existing_revisions = merged.get("revisions")
                if isinstance(value, list) and (
                        value or not isinstance(existing_revisions, list)):
                    merged[key] = value
                continue
            merged[key] = value
        pages_by_id[pageid] = merged


def fetch_transcluded_pages_with_revisions(
    session: requests.Session,
    wiki_api: str,
    template_title: str,
) -> tuple[list[int], dict[int, dict[str, Any]], str]:
    pageids: list[int] = []
    seen: set[int] = set()
    pages_by_id: dict[int, dict[str, Any]] = {}
    curtimestamp = ""

    request_data: dict[str, Any] = {
        "action": "query",
        "format": "json",
        "maxlag": _MAXLAG,
        "prop": "revisions",
        "titles": template_title,
        "generator": "transcludedin",
        "formatversion": 2,
        "rvprop": "content|ids",
        "rvslots": "main",
        "gtilimit": "max",
        "curtimestamp": 1,
    }

    while True:
        response_data = api_post_json(
            session=session,
            wiki_api=wiki_api,
            data=request_data,
            timeout=_TIMEOUT,
            error_context="Failed to fetch transcluded pages with revisions",
        )
        if "error" in response_data:
            raise RuntimeError(
                f"API error on transcluded revisions query: {response_data['error']}"
            )

        if warnings := response_data.get("warnings", {}).get("result", {}):
            if warning_msg := warnings.get("warnings", ""):
                print(f"\033[93m[API WARNING] {warning_msg}\033[0m",
                      file=sys.stderr)

        if not curtimestamp and isinstance(response_data.get("curtimestamp"),
                                           str):
            curtimestamp = response_data["curtimestamp"]

        _merge_generated_pages_with_revisions(
            response_data,
            pageids,
            seen,
            pages_by_id,
        )

        cont = response_data.get("continue")
        if not isinstance(cont, dict):
            break
        request_data |= cont

    return pageids, pages_by_id, curtimestamp


def fetch_pages_by_pageids_with_revisions(
    session: requests.Session,
    wiki_api: str,
    pageids: list[int],
) -> tuple[list[int], dict[int, dict[str, Any]], str]:
    target_ids = [pid for pid in pageids if isinstance(pid, int) and pid > 0]
    if not target_ids:
        return [], {}, ""

    ordered_pageids: list[int] = []
    pages_by_id: dict[int, dict[str, Any]] = {}
    curtimestamp = ""

    chunk_size = 50
    for i in range(0, len(target_ids), chunk_size):
        chunk = target_ids[i:i + chunk_size]
        response_data = api_post_json(
            session=session,
            wiki_api=wiki_api,
            data={
                "action": "query",
                "format": "json",
                "formatversion": 2,
                "maxlag": _MAXLAG,
                "prop": "revisions",
                "pageids": "|".join(str(pid) for pid in chunk),
                "rvprop": "content|ids",
                "rvslots": "main",
                "curtimestamp": 1,
            },
            timeout=_TIMEOUT,
            error_context="Failed to fetch pages by pageid with revisions",
        )
        if "error" in response_data:
            raise RuntimeError(
                f"API error on pageid revisions query: {response_data['error']}"
            )

        if not curtimestamp and isinstance(response_data.get("curtimestamp"),
                                           str):
            curtimestamp = response_data["curtimestamp"]

        pages = response_data.get("query", {}).get("pages", [])
        if not isinstance(pages, list):
            continue

        for page in pages:
            if not isinstance(page, dict):
                continue
            pageid = page.get("pageid")
            if not isinstance(pageid, int):
                continue
            if pageid not in ordered_pageids:
                ordered_pageids.append(pageid)
            pages_by_id[pageid] = page

    ordered = [pid for pid in target_ids if pid in pages_by_id]
    return ordered, pages_by_id, curtimestamp


# ---------------------------------------------------------------------------
# Edit
# ---------------------------------------------------------------------------


def edit_page_text(
    session: requests.Session,
    wiki_api: str,
    pageid: int,
    text: str,
    summary: str,
    csrf_token: str,
    assert_user: str,
    bot: bool,
    baserevid: str = "",
    starttimestamp: str = "",
    tags: str = "Bot",
) -> dict[str, Any]:
    data: dict[str, Any] = {
        "action": "edit",
        "format": "json",
        "maxlag": _MAXLAG,
        "assertuser": assert_user,
        "pageid": str(pageid),
        "text": text,
        "summary": summary,
        "token": csrf_token,
        "minor": 1,
    }
    if tags:
        data["tags"] = tags
    if bot:
        data["bot"] = "1"
    if baserevid:
        data["baserevid"] = baserevid
    if starttimestamp:
        data["starttimestamp"] = starttimestamp

    result = api_post_json(
        session=session,
        wiki_api=wiki_api,
        data=data,
        timeout=_TIMEOUT,
        error_context=f"Failed to edit pageid={pageid}",
    )
    if "error" in result:
        error_code = result.get("error", {}).get("code", "")
        if error_code == "editconflict":
            raise RuntimeError(
                f"[editconflict] pageid={pageid}: {result['error']}")
        raise RuntimeError(
            f"API edit error for pageid={pageid}: {result['error']}")
    return result


def edit_page_by_title(
    session: requests.Session,
    wiki_api: str,
    title: str,
    text: str,
    summary: str,
    csrf_token: str,
    assert_user: str,
    bot: bool = False,
    tags: str = "Bot",
) -> dict[str, Any]:
    """Overwrite a page identified by *title* (not pageid) with *text*.

    Unlike edit_page_text, this does not take a baserevid/starttimestamp:
    it's meant for simple, low-stakes status-page style overwrites (e.g.
    Special:MyPage/Status) where edit-conflict protection is unnecessary
    and the page may not exist yet.
    """
    data: dict[str, Any] = {
        "action": "edit",
        "format": "json",
        "maxlag": _MAXLAG,
        "assertuser": assert_user,
        "title": title,
        "text": text,
        "summary": summary,
        "token": csrf_token,
        "minor": 1,
    }
    if tags:
        data["tags"] = tags
    if bot:
        data["bot"] = "1"

    result = api_post_json(
        session=session,
        wiki_api=wiki_api,
        data=data,
        timeout=_TIMEOUT,
        error_context=f"Failed to edit title={title!r}",
    )
    if "error" in result:
        raise RuntimeError(
            f"API edit error for title={title!r}: {result['error']}")
    return result


def purge_embedding_pages(
    session: requests.Session,
    wiki_api: str,
    title: str,
) -> int:
    """Purge the parser cache of every page transcluding *title*.

    Pages outside the Template namespace (e.g. User: subpages) do not get
    their embedding pages automatically invalidated on edit the way
    templates do, so callers who overwrite a transcluded non-template page
    must purge its embedders manually. Handles API continuation and
    returns the number of pages purged.
    """
    purged = 0
    request_data: dict[str, Any] = {
        "action": "purge",
        "format": "json",
        "formatversion": 2,
        "maxlag": _MAXLAG,
        "generator": "embeddedin",
        "geititle": title,
        "geilimit": "max",
    }

    while True:
        response_data = api_post_json(
            session=session,
            wiki_api=wiki_api,
            data=request_data,
            timeout=_TIMEOUT,
            error_context=f"Failed to purge pages embedding {title!r}",
        )
        if "error" in response_data:
            raise RuntimeError(
                f"API error on purge for {title!r}: {response_data['error']}")

        purge_result = response_data.get("purge", [])
        if isinstance(purge_result, list):
            purged += len(purge_result)

        cont = response_data.get("continue")
        if not isinstance(cont, dict):
            break
        request_data |= cont

    return purged
