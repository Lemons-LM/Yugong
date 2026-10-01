# Maintainer Guide

This document is for developers maintaining the YuGong codebase itself — modifying core logic, fixing bugs, or adding new subsystems.

## Architecture overview

```
main.py:main(argv) → int
  ├─ sets PYWIKIBOT_DIR=<repo>/data/pwb and puts the repo root on sys.path
  ├─ catches every exception: logs the traceback, prints one line, returns 1 (130 for Ctrl-C)
  │
  ├─ production: yu_gong()
  │    ├─ confirm_settings()          # load extensions + rules, print, validate, optional prompts
  │    └─ do_jobs()                   # lock → validate → heartbeat → todo list → process → save
  │         ├─ _get_todo_list()       # pageids batches + embeddedin() + category members()
  │         ├─ _prepare_manifest()    # merge with cache/<wiki_tag>.json
  │         └─ _process_single_page()
  │              ├─ tag-policy check
  │              ├─ build_steps()/apply_steps()   # template rules first, then @job functions
  │              ├─ diff_size() check
  │              └─ page.save()  or  clipboard + browser
  │
  └─ dev: run_dev_mode()              # the same pipeline against a local file
```

Two distinct modes share the same extension execution path (`processor/pipeline.py`):

| Mode | Entry | Wiki connection | User prompts |
|------|-------|-----------------|--------------|
| Production | `main.py` (no args) | Yes | Configurable (`bypass_confirm_settings`) |
| Dev | `main.py --dev IN OUT` | No, unless `--with-wiki-jobs` | None |

## Package map

```
src/Yugong/
├── yu_gong.py              # top-level orchestrator (confirm_settings + do_jobs)
├── core/                   # domain logic (heavy deps: pywikibot, toml)
│   ├── wiki.py             # Wiki class — pywikibot Site wrapper, _api_get, tick/suppression
│   ├── wikitext.py         # Wikitext class — mwparserfromhell Wikicode wrapper
│   ├── settings.py         # Settings class — loads settings.toml, deferred validation
│   ├── template_formatter.py # TemplateFormatter — applies TOML rules to templates
│   ├── logger.py           # BotLogger, get_logger(), configure_logging()
│   ├── bot_db.py           # BotDB — SQLite cache + lazy module-level proxy
│   ├── mailer.py           # Mailer — SMTP alert emails (disabled without env credentials)
│   └── manifest.py         # Manifest — JSON file persistence helper
├── processor/              # processing pipeline
│   ├── do_jobs.py          # main processing loop (production)
│   ├── pipeline.py         # build_steps()/apply_steps(), TEMPLATE_RULE_STEP
│   └── dev_mode.py         # offline file-in/file-out processing
├── utilities/              # helpers (mostly light, but template_formatter pulls in toml)
│   ├── extensions.py       # EXTENSIONS_DIR, extension_modules(), load_extensions()
│   ├── confirm_settings.py # loads extensions + rules, interactive prompts
│   ├── mark_job_intro.py   # @job / @intro decorator registries, job_needs_wiki()
│   ├── path_helper.py      # PROJECT_ROOT resolver
│   ├── link.py             # wiki link helpers, get_user_talk(), get_username()
│   ├── pwb_related.py      # family registration for pywikibot
│   ├── check_heartbeat.py  # daily-run dedup check
│   ├── check_same_website.py # domain matching for template rules
│   ├── lock.py             # PID-based process lock in data/lock
│   ├── reporter.py         # Reporter — collects issues, prints/emails summary
│   ├── marks.py            # common wiki syntax characters
│   ├── calculate_length.py # wikitext effective-length calculation
│   ├── signature_parser.py # Chinese/non-Chinese timestamp parsing
│   ├── sections_to_page.py # combine section nodes into page text
│   └── record_start_time.py # UTC+8 start-time recorder
└── extensions/             # shipped @job/@intro functions
    ├── example.py          # deliberate no-op, copy this to start a new extension
    ├── fix_cite_template.py
    ├── rm_undefined_refs.py
    ├── rm_void_template.py # @job(needs_wiki=True)
    └── category_handler.py # @job(needs_wiki=True)
```

## Key patterns

### Module-level singletons

Several modules create global instances at import time. This is intentional — they act as application-wide singletons:

```python
# settings.py
settings: Settings = Settings()          # reads settings.toml; validation is deferred

# wiki.py
wiki = Wiki()                            # pywikibot wrapper, lazy site init, no network here

# logger.py
logger = get_logger("Yugong")            # main application logger
utilities_logger = get_logger("utilities")

# template_formatter.py
formatter: TemplateFormatter = TemplateFormatter()

# bot_db.py
bot_db: Any = _BotDBProxy()              # forwards to get_bot_db(); no file until first use

# mailer.py
mailer = Mailer()

# reporter.py
reporter: Reporter = Reporter()
```

Consumers import the singleton directly: `from src.Yugong.core.wiki import wiki`.

### Settings loading

`Settings.__init__()` reads `settings.toml` and calls `self.set(key=key, value=value)`, which sets an **instance** attribute for every key. Declared class variables (with type hints) provide the defaults; the TOML file overrides them through the instance. `YUGONG_SETTINGS` overrides the file path.

Validation is deliberately separate: `Settings.validate()` raises a descriptive error, and it is only called once the orchestrator is about to do real work (`confirm_settings()` and `do_jobs()` both call it). Importing a module therefore never requires a configured wiki — only an existing `settings.toml` file. `Settings.from_dict()` builds an instance without touching the filesystem, which the test suite uses.

### Decorator registry (extension system)

`mark_job_intro.py` maintains two global lists:

```python
JOBS = []      # functions decorated with @job
INTROS = []    # functions decorated with @intro
```

`@job` can be used bare or as `@job(needs_wiki=True)`; the latter sets a `needs_wiki` attribute that `job_needs_wiki()` reads. Extensions are loaded exclusively through `utilities/extensions.py`:

- `extension_modules()` returns `src.Yugong.extensions.<stem>` for every `*.py` file except `__init__.py`, sorted by filename.
- `load_extensions()` imports them in that order and returns the loaded names.

Importing triggers the decorators, so `JOBS`/`INTROS` follow sorted filename order. An extension that fails to import raises all the way up: CONTRIBUTIONS.md requires a broken extension to stop the program rather than be skipped silently.

### Step pipeline

`processor/pipeline.py` is shared by production and dev mode:

- `build_steps(wikitext, apply_rules=True, include_wiki_jobs=True, jobs=None)` returns `(steps, skipped_job_names)`. When `apply_rules` is true, the first step is always `(TEMPLATE_RULE_STEP, formatter.format_template)`; the selected `@job` functions follow. Jobs marked `needs_wiki` are dropped (and their names returned in `skipped`) when `include_wiki_jobs` is false.
- `apply_steps(wikitext, page_name, steps)` runs each step, snapshots the text before/after, logs the ones that changed something, and returns the changed step names.

## Data flow: processing a single page

```
1. wiki.page(page_name)                  → pywikibot.Page object
2. pwb_page.text                         → raw wikitext string
3. Wikitext(metadata)                    → wraps metadata (title, revid, etc.)
4. wikitext.parse(content)               → mwparserfromhell parses into Wikicode
5. disallowed_tags(wikitext.tags(), …)   → tag policy; abort or skip on a forbidden tag
6. steps, skipped = build_steps(wikitext)→ template rules first, then @job functions
7. apply_steps(wikitext, name, steps)    → each step mutates wikitext.wikitext in place
8. new_text = str(wikitext.wikitext)
   if new_text == content:               → "No changes made", page leaves the todo list
   if diff_size(content, new_text) > max_acceptable_diff_size: skip (stays queued)
9. submit_changes:                       → page.text = new_text; page.save(summary=edit_comment, bot=True)
   else:                                 → pyperclip.copy + webbrowser.open + blocking input()
```

The page returns `True`/`False` from `_process_single_page()`: only a fully handled page is removed from the manifest todo list. Pages skipped for a safety reason (forbidden tag with `is_dangerous_tag_unacceptable = false`, diff too large, failed save) stay queued for a later run, and are recorded in `reporter`.

## The Wiki class (`wiki.py`)

The `Wiki` class wraps pywikibot with several key behaviors:

- **No network at import.** Constructing `Wiki` only stores configuration. The `site` property creates the `pywikibot.Site` on first access, requires the OAuth token there, calls `apply_pywikibot_config()` and `register_family()`, then reuses the instance.
- **OAuth only.** The documented variable is `MW_OAUTH_TOKEN`; `MW_BOT_OAUTH_TOKEN` is accepted as a legacy fallback and the documented name takes precedence.
- **pywikibot configuration.** `apply_pywikibot_config()` pushes `user_agent_format`, `cosmetic_changes`, `minthrottle`, `retry_max` (= `request_max_tries`) and `socket_timeout` into pywikibot. pywikibot's default `retry_max = 120` used to turn an unreachable wiki into a multi-minute hang.
- **Family registration.** pywikibot does not auto-register `Family` subclasses, so `pwb_related.register_family()` inserts an instance into `family.Family._families` before `Site` is created. Its `name`/`langs` come from `wiki_family`/`wiki_lang`/`wiki_domain`, and `isPublic(self, code)` uses the signature pywikibot actually calls.
- **Retrying raw API access.** `Wiki._api_get` / `Wiki.api_query` honour `request_max_tries`, `request_timeout` and an exponential backoff. A non-JSON body (bot-protection challenge, login form, HTML error) is retried and then reported; the method returns `None` instead of raising.
- **Tick/suppression check.** Every 20 API requests (`SUPPRESSION_CHECK_INTERVAL`), `tick()` calls `_check_suppressed_action()`, which queries `User:<bot_name>/block` for its revision id. The first run stores the id in `data/bot/heartbeat`; a later change means suppression, so the bot emails the recipients and calls `sys.exit(1)`. A broken or unreachable check only logs a warning.
- **HTTP monkey-patch.** `guarded_request` wraps `http.session.request` to inject OAuth headers and call `wiki.tick()` on every pywikibot HTTP request, so the kill switch also covers pywikibot's internal calls.
- **Bot opt-out.** `check_allow_bots()` reads the user talk page **content**, not its title, and fails closed (`False`) when the page cannot be read.
- **Unused helpers.** `mass_message()`, `new_section()` and `get_sections()` are implemented but not called by the processing loop.

## Safety and operational behaviour

- **Run lock** (`utilities/lock.py`): a PID written to `data/lock`. A lock whose PID is no longer alive is reclaimed, so a crash does not block the next run.
- **Daily heartbeat** (`utilities/check_heartbeat.py`, `data/bot/heartbeat_daily`): with `enable_heartbeat = true`, a second run on the same UTC day logs, emails and stops. Reading and recording are separate functions (`heartbeat_matches`, `record_heartbeat`) and the day is only claimed *after* the site connects and a non-empty todo list has been built, so a failed connection does not block a retry later the same day.
- **Tag policy**: `unsafe_tag_list` is a deny-list, `safe_tag_list` an allow-list, and `validate()` rejects configuring both. A forbidden tag aborts the whole run via `SafetyAbort` when `is_dangerous_tag_unacceptable = true` (the default); otherwise the page is skipped and reported.
- **Diff limit**: `diff_size()` uses `difflib.SequenceMatcher` to count changed characters before anything is submitted.
- **Todo persistence**: `cache/<wiki_tag>.json` stores `url` and `todo`. A cached URL that disagrees with `api_endpoint` aborts with a "change wiki_tag" message.
- **Reporting**: skipped and failed pages go to `utilities/reporter.py` (`reporter.add(module, issue)`), are printed at the end of the run, and are emailed when `mail_recipients` and `MAIL_ACCOUNT`/`MAIL_PASSWORD` are set.

## Adding a new feature

Where to put things:

| Type | Location |
|------|----------|
| New wiki operation | Add method to `Wiki` class in `core/wiki.py` |
| New wikitext manipulation | Add method to `Wikitext` class in `core/wikitext.py` |
| New settings field | Add class attr in `core/settings.py` + entry in `settings.toml` (+ validation, if required) |
| New processing step | Add a `@job` extension, or a step to `processor/pipeline.py` for machinery shared by both entry points |
| New CLI flag | Add to `main.py` argparse, create processor if needed |
| New utility | Add to `utilities/` |
| New extension | Add `.py` file to `extensions/` |

## Testing

The suite is plain `unittest` — 202 test cases under `tests/`, no pytest dependency:

```bash
python -m unittest discover
```

`mypy` (configured in `pyproject.toml` with `files = ["src", "tests", "main.py"]` and `disallow_untyped_defs = true`) currently reports zero errors:

```bash
mypy
```

Coverage includes:

- extension input/output behaviour (`test_extensions.py`) and template rules (`test_core.py`)
- the `@job`/`@intro` registries and `Marks` (`test_registry.py`)
- settings loading and every `validate()` rule (`test_settings.py`)
- pure helpers: `diff_size`, `pageid_batches`, `disallowed_tags`
- the step pipeline, todo-list selection, manifest merging and offline dev mode (`test_processor.py`)
- lock, heartbeat, manifest, reporter, link/length/signature helpers, `BotDB` and `check_same_website` (`test_utilities.py`)
- the wiki wrapper's retry, OAuth and kill-switch behaviour (`test_wiki.py`)
- subprocess tests that run the real `main.py` (`test_entrypoints.py`)

`tests/support.py` provides `make_wikitext`, `run_job` and an in-memory `FakeBotDB`, so the extension tests never touch the network or a database. The `BotDB` tests create a throwaway SQLite file in a temporary directory instead of using `data/db/db.sqlite3`.

## Dependency tiers

```
Wikitext + rules:   mwparserfromhell, toml
Wiki:               pywikibot (which itself uses requests)
Manual mode:        pyperclip (imported by do_jobs at module level)
Development:        mypy, types-requests
```

`requests` and `beautifulsoup4` are declared dependencies but are not imported directly by YuGong's own code (`wiki.py` goes through `pywikibot.comms.http.session`).

Both entry points pull in the whole set: production obviously needs the wiki stack, and dev mode calls `load_extensions()` (which imports `category_handler`/`rm_void_template`) and `formatter.get_ruleset()`. Dev mode is dependency-light only in the sense that it never connects to a wiki or validates settings — it is not a way to run without `pywikibot` or `toml` installed.

## Known technical debt

- **Cangjie / Chinese variant conversion** — not implemented. `enable_cangjie = true` raises `NotImplementedError` during validation so it can never silently do nothing. `category_handler` converts category titles through OpenCC only when OpenCC is installed, and OpenCC is not a declared dependency.
- **Non-Qiuwen wikis** — `wiki_family`, `wiki_lang` and `wiki_domain` make the family configurable, but support has not been tested against a second wiki.
- **No shipped template rules** — `template_rules/` contains only `example.toml.disabled`; the loader ignores it on purpose.
- **Unused public helpers** — `calculate_length.py`, `signature_parser.py`, `sections_to_page.py` and `marks.py` have no in-repo callers (all four are covered by unit tests).
- **Unused Wiki helpers** — `mass_message()`, `new_section()` and `get_sections()` are implemented but never called by the processing loop.
- **Only OAuth login** — bot password login is not supported.
