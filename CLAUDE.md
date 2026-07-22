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

# Run type checking
mypy src/

# Run the program
python3 main.py
```

## Architecture

**Entry point:** `main.py` → `src/Yugong/yu_gong.py:yu_gong()` — calls `confirm_settings()` then `do_jobs()`.

**Core flow:**
1. `confirm_settings()` — loads and validates `settings.toml`, dynamically imports all extensions from `src/Yugong/extensions/`, prints their `@intro` descriptions, loads template TOML rules, and asks the user to confirm at each step.
2. `do_jobs()` — updates the wiki connection from settings, triggers pywikibot site init, builds a todo list (merging with cached state from `cache/{wiki_tag}.json`), then processes each page by running every registered `@job` function against a `Wikitext` object. Pages with changes are either auto-submitted or copied to clipboard with a browser opened for manual review.

**Package layout:**

| Package | Purpose |
|---------|---------|
| `src/Yugong/core/` | Core domain: `wiki.py` (pywikibot-based `Wiki` class), `wikitext.py` (mwparserfromhell wrapper), `settings.py` (TOML config loader), `template_formatter.py` (template rule engine), `logger.py`, plus `bot_db.py`, `mailer.py`, `manifest.py` |
| `src/Yugong/processor/` | `do_jobs.py` — main processing loop |
| `src/Yugong/utilities/` | Utilities: `confirm_settings.py`, `mark_job_intro.py` (decorator registry), `path_helper.py` (`PROJECT_ROOT`), `link.py`, `lock.py`, `pwb_related.py` (Qiuwen family), `check_same_website.py`, `check_heartbeat.py`, `reporter.py`, etc. |
| `src/Yugong/extensions/` | User-defined processing jobs registered via `@job`/`@intro` decorators |
| `src/Yugong/models/` | Legacy: only `marks.py` remains (common wiki syntax characters) |

**Key design points:**
- `wiki.py` exports a module-level `wiki = Wiki(bot_name="Lemonade-bot")` singleton. Consumers import `wiki` directly.
- `do_jobs.py` uses pywikibot directly — e.g. `wiki.page(title).text` to read, `page.save()` to write, `pywikibot.Page(site, ...).embeddedin()` to list pages, `pywikibot.Category(site, ...).members()` to list category members.
- The `Wiki` class wraps pywikibot with lazy `Site` init (OAuth via `MW_BOT_OAUTH_TOKEN` env var), a heartbeat/suppression check, and convenience helpers (`page()`, `category()`, `user()`, `file()`).
- The `Wikitext` class is a thin wrapper around `mwparserfromhell.Wikicode`. It holds metadata (title, revid, page_id, namespace) and provides `parse(content)` and `update(content)`.

## Extension System

Extensions are Python files in `src/Yugong/extensions/`. Each file uses two decorators from `mark_job_intro.py`:

- `@job` — registers a function `(wikitext: Wikitext) -> None` that mutates page content in-place. Called in registration order for every page.
- `@intro` — registers a function `() -> str` that returns a one-line description shown during the confirmation step.

Copy `src/Yugong/extensions/example.py` as a starting point. Extensions are dynamically imported at runtime by `confirm_settings.py`.

## Template Rules (`template_rules/`)

TOML files defining transformations applied to wiki templates. Each rule file specifies:
- `names` — template names to match (case-insensitive first letter)
- `apply_websites` — optional domain filter; leave empty to apply everywhere
- `template_level` — rename, delete, or replace the entire template
- `params` — per-parameter rename/delete/regex match-and-replace rules

Loaded by `TemplateFormatter.get_ruleset()` and applied during processing.

## Configuration

`settings.toml` at project root. Key settings:
- `api_endpoint` (required) — wiki API URL
- `page_id_start`/`page_id_end` or `linked_template` or `category` (required) — defines what pages to process
- `is_owner_only` — must be `true`; auth via `MW_OAUTH_TOKEN` env var
- `submit_changes` — if false, copies result to clipboard and opens browser for manual review
- `max_acceptable_diff_size` — safety limit on edit diffs

## Important Conventions

- **All functions must have type annotations** (per CONTRIBUTING.md). mypy is configured with `disallow_untyped_defs = true`.
- **Extensions must validate inputs and fail loudly** — raise descriptive exceptions, never fail silently. If an extension is broken, the entire program should refuse to run.
- **Safety-first**: mandatory user confirmations before any wiki edits; diff size limits; dangerous tag detection. The program defaults to manual review (clipboard + browser) rather than auto-submitting.
- Use `PROJECT_ROOT` from `src/Yugong/utilities/path_helper.py` for resolving project-relative paths — it walks up from `__file__` looking for `pyproject.toml`/`settings.toml`/`.git`.
- This is the `dev` branch, migrating to `mwparserfromhell` + `pywikibot`. The legacy `src/Yugong/models/` directory is being phased out in favor of `src/Yugong/core/`.
