# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

YuGong is a Python-based automated wiki editing tool for batch processing wiki pages. It uses `mwparserfromhell` for wikitext parsing and `pywikibot` for wiki API interaction.

## Commands

```bash
# Create virtual environment and install dependencies
python3 -m venv .venv
source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Install with dev dependencies (includes mypy)
pip install -e ".[dev]"

# Run type checking (configuration lives in pyproject.toml)
mypy

# Run the test suite (stdlib unittest, no pytest)
python -m unittest discover

# Run the program
python3 main.py

# Run the offline pipeline against a local file
python3 main.py --dev input.wikitext output.wikitext
```

## Architecture

**Entry point:** `main.py` defines `main(argv) -> int`. Before importing anything it sets `PYWIKIBOT_DIR` to `<repo>/data/pwb` and puts the repository root on `sys.path`. A production run goes `main()` → `src/Yugong/yu_gong.py:yu_gong()` → `confirm_settings()` then `do_jobs()`. Any uncaught exception is logged with its traceback and reported as one concise stderr line, returning exit code 1 (`130` for `KeyboardInterrupt`).

**Core flow:**
1. `confirm_settings()` — configures logging, imports every extension through `utilities/extensions.py`, prints their `@intro` descriptions, loads template TOML rules via `formatter.get_ruleset()`, prints the effective settings, then calls `settings.validate()` and asks the user to confirm at each step (unless `bypass_confirm_settings`/robot mode).
2. `do_jobs()` — configures logging, records the start time, takes the PID-based run lock, then runs the locked body: `settings.validate()`, the optional daily-heartbeat duplicate check, lazy pywikibot site init, building the todo list (merged with cached state from `cache/{wiki_tag}.json`), and then processing each page. Per page: tag-policy check, template rules plus every registered `@job` function against a `Wikitext` object, a changed-character-count check, and finally auto-submit or clipboard + browser.

**Package layout:**

| Package | Purpose |
|---------|---------|
| `src/Yugong/core/` | Core domain: `wiki.py` (pywikibot-based `Wiki` class), `wikitext.py` (mwparserfromhell wrapper), `settings.py` (TOML config loader + validation), `template_formatter.py` (template rule engine), `logger.py`, plus `bot_db.py`, `mailer.py`, `manifest.py` |
| `src/Yugong/processor/` | `do_jobs.py` — main processing loop; `pipeline.py` — shared `build_steps`/`apply_steps` step machinery; `dev_mode.py` — offline file-in/file-out processing |
| `src/Yugong/utilities/` | Utilities: `extensions.py` (extension discovery/loading), `confirm_settings.py`, `mark_job_intro.py` (decorator registry), `path_helper.py` (`PROJECT_ROOT`), `link.py`, `lock.py`, `marks.py`, `pwb_related.py` (family registration), `check_same_website.py`, `check_heartbeat.py`, `reporter.py`, `calculate_length.py`, `signature_parser.py`, `sections_to_page.py`, `record_start_time.py` |
| `src/Yugong/extensions/` | User-defined processing jobs registered via `@job`/`@intro` decorators |

The legacy `src/Yugong/models/` directory (including `models/marks.py`) was deleted; `Marks` now lives in `src/Yugong/utilities/marks.py`.

**Key design points:**
- `wiki.py` exports a module-level `wiki = Wiki()` singleton. Consumers import `wiki` directly. Constructing `Wiki` performs **no network access**; the pywikibot `Site` is created lazily by the `site` property, which is also where the OAuth token is required.
- The `Wiki` class wraps pywikibot with lazy `Site` init (OAuth via `MW_OAUTH_TOKEN`, with `MW_BOT_OAUTH_TOKEN` as a legacy fallback), a suppression/kill-switch check, and convenience helpers (`page()`, `category()`, `user()`, `file()`).
- All raw API calls go through `Wiki._api_get` / `Wiki.api_query`, which honour `request_max_tries`/`request_timeout`, back off between attempts, tolerate non-JSON bodies (bot-protection challenge pages, HTML errors) and return `None` instead of raising.
- `do_jobs.py` uses pywikibot directly — e.g. `wiki.page(title).text` to read, `page.save()` to write, `pywikibot.Page(site, ...).embeddedin()` to list pages, `pywikibot.Category(site, ...).members()` to list category members.
- The `Wikitext` class is a thin wrapper around `mwparserfromhell.Wikicode`. It holds metadata (title, revid, page_id, namespace) and provides `parse(content)` and `update(content)`, plus `templates()`/`wikilinks()`/`tags()` snapshots for extensions.

## Extension System

Extensions are Python files in `src/Yugong/extensions/`. Each file uses two decorators from `mark_job_intro.py`:

- `@job` — registers a function `(wikitext: Wikitext) -> None` that mutates page content in-place. Called in registration order for every page.
- `@job(needs_wiki=True)` — marks a job that talks to the wiki. Offline dev mode skips those (and prints which ones) unless `--with-wiki-jobs` is passed. `job_needs_wiki()` reads the marker.
- `@intro` — registers a function `() -> str` that returns a one-line description shown during the confirmation step.

Copy `src/Yugong/extensions/example.py` as a starting point (it is deliberately a no-op). Extensions are discovered and imported by `src/Yugong/utilities/extensions.py`: `extension_modules()` returns `src.Yugong.extensions.<stem>` for every `*.py` file except `__init__.py`, sorted by filename, and `load_extensions()` imports them. Both entry points use this module, so ordering is deterministic (import order == sorted filename order). A broken extension aborts the run; it is not skipped silently.

## Template Rules (`template_rules/`)

TOML files defining transformations applied to wiki templates. Each rule file specifies:
- `names` — template names to match (case-insensitive first letter)
- `introduction` — required human-readable description
- `apply_websites` — optional domain filter; leave empty to apply everywhere
- `template_level` — rename, delete, or replace the entire template (exactly one action)
- `params` — per-parameter rename/delete/regex match-and-replace rules

Loaded by `TemplateFormatter.get_ruleset()` (which validates and rejects conflicting or incomplete rules) and applied by `formatter.format_template()`, the first processing step of every page. The loader globs `template_rules/*.toml` only, so the copy-me file `example.toml.disabled` is deliberately ignored.

## Configuration

`settings.toml` at project root. `Settings` loads the TOML at import time but defers *validation* to `Settings.validate()`, which `confirm_settings()` and `do_jobs()` call — importing a module never requires a fully configured wiki. Set `YUGONG_SETTINGS` to override the settings file path.

Key settings:
- `api_endpoint` (required) — wiki API URL
- `page_id_start`/`page_id_end` or `linked_template` or `category` (required) — defines what pages to process; the sources combine and deduplicate
- `is_owner_only` — must be `true`; auth via `MW_OAUTH_TOKEN` env var
- `wiki_lang` (default `"zh"`), `wiki_family` (default `"qiuwen"`), `wiki_domain`
- `submit_changes` — if false, copies result to clipboard and opens browser for manual review
- `max_acceptable_diff_size` (default `1000`) — safety limit on edit diffs
- `is_dangerous_tag_unacceptable` (default `true`), `safe_tag_list` (default `[]`), `unsafe_tag_list`
- `enable_heartbeat` (default `false`) — optional daily duplicate-run guard
- `request_max_tries`/`request_timeout` (defaults `3`/`30`)
- `log_level` — 0=CRITICAL, 1=ERROR, 2=WARNING, 3=INFO, 4=DEBUG

`validate()` enforces a non-empty `api_endpoint`, `is_owner_only`, `bot_name`/`wiki_domain`/`edit_comment`, at least one page selector, `page_id_end >= page_id_start`, a `MAX_PAGEID_SPAN = 5000` cap, mutually exclusive tag lists, positive numeric limits, a valid `log_level`, and raises `NotImplementedError` when `enable_cangjie = true` (automatic Chinese variant conversion is not implemented).

## Important Conventions

- **All functions must have type annotations** (per CONTRIBUTIONS.md). mypy is configured with `disallow_untyped_defs = true`.
- **Extensions must validate inputs and fail loudly** — raise descriptive exceptions, never fail silently. If an extension is broken, the entire program should refuse to run.
- **Safety-first**: mandatory user confirmations before any wiki edits; diff size limits; dangerous tag detection. The program defaults to manual review (clipboard + browser) rather than auto-submitting.
- Use `PROJECT_ROOT` from `src/Yugong/utilities/path_helper.py` for resolving project-relative paths — it walks up from `__file__` looking for `pyproject.toml`/`settings.toml`/`.git`.
- This is the `dev` branch, using `mwparserfromhell` + `pywikibot`. The legacy `models/` package is gone; `core/`, `processor/` and `utilities/` are the only packages.
