# Maintainer Guide

This document is for developers maintaining the YuGong codebase itself — modifying core logic, fixing bugs, or adding new subsystems.

## Architecture overview

```
main.py
  └─ yu_gong()
       ├─ confirm_settings()          # load extensions, rules, optional user prompts
       └─ do_jobs()                    # connect to wiki, fetch pages, process, save
            ├─ _get_todo_list()        # pywikibot: embeddedin() + category members()
            └─ _process_single_page()
                 ├─ wiki.page(name)    # fetch wikitext
                 ├─ Wikitext.parse()   # mwparserfromhell parsing
                 ├─ @job functions     # extension transformations (in-place mutation)
                 └─ page.save()        # submit back to wiki
```

Two distinct modes share the same extension execution path:

| Mode | Entry | Wiki connection | User prompts |
|------|-------|-----------------|--------------|
| Production | `main.py` (no args) | Yes | Configurable (`bypass_confirm_settings`) |
| Dev | `main.py --dev IN OUT` | No | None |

## Package map

```
src/Yugong/
├── yu_gong.py              # top-level orchestrator
├── core/                   # domain logic (heavy deps: pywikibot, toml)
│   ├── wiki.py             # Wiki class — pywikibot Site wrapper, tick/suppression
│   ├── wikitext.py         # Wikitext class — mwparserfromhell Wikicode wrapper
│   ├── settings.py         # Settings class — loads settings.toml, singleton
│   ├── template_formatter.py # TemplateFormatter — applies TOML rules to templates
│   ├── logger.py           # BotLogger, get_logger(), module-level singletons
│   ├── bot_db.py           # BotDB — SQLite cache (not yet wired up)
│   ├── mailer.py           # Mailer — SMTP alert emails
│   └── manifest.py         # Manifest — JSON file persistence helper
├── processor/              # processing pipeline
│   ├── do_jobs.py          # main processing loop (production)
│   └── dev_mode.py         # offline file-in/file-out processing
├── utilities/              # helpers (no heavy deps)
│   ├── confirm_settings.py # loads extensions + rules, interactive prompts
│   ├── mark_job_intro.py   # @job / @intro decorator registries
│   ├── path_helper.py      # PROJECT_ROOT resolver
│   ├── link.py             # wiki link helpers, get_user_talk(), get_username()
│   ├── pwb_related.py      # QiuwenFamily registration for pywikibot
│   ├── check_heartbeat.py  # daily-run dedup check
│   ├── check_same_website.py # domain matching for template rules
│   ├── lock.py             # file-based process lock
│   ├── reporter.py         # Reporter — collects issues, emails summary
│   ├── calculate_length.py # wikitext effective-length calculation
│   ├── signature_parser.py # Chinese/non-Chinese timestamp and username parsing
│   ├── sections_to_page.py # combine section nodes into page text
│   └── record_start_time.py # UTC+8 start-time recorder
├── extensions/             # user-defined @job/@intro functions
│   ├── __init__.py
│   └── example.py          # copy this to start a new extension
└── models/                 # legacy (to be removed)
    └── marks.py            # common wiki syntax characters
```

## Key patterns

### Module-level singletons

Several modules create global instances at import time. This is intentional — they act as application-wide singletons:

```python
# settings.py
settings: Settings = Settings()          # loads settings.toml on import

# wiki.py
wiki = Wiki()                            # pywikibot wrapper, lazy site init

# logger.py
logger = get_logger("Yugong")            # main application logger
utilities_logger = get_logger("utilities")

# template_formatter.py
formatter: TemplateFormatter = TemplateFormatter()

# bot_db.py
bot_db = BotDB()

# mailer.py
mailer = Mailer()

# reporter.py
reporter: Reporter = Reporter()
```

Consumers import the singleton directly: `from src.Yugong.core.wiki import wiki`.

### Decorator registry (extension system)

`mark_job_intro.py` maintains two global lists:

```python
JOBS = []      # functions decorated with @job
INTROS = []    # functions decorated with @intro
```

Extensions are loaded via dynamic import in `confirm_settings.py` (and `dev_mode.py`). The `importlib.import_module()` call triggers the decorators, which push functions into `JOBS`/`INTROS`. Order in `JOBS` is the order extensions are imported.

### Settings loading

`Settings.__init__()` reads `settings.toml` and calls `setattr(cls, key, value)` for every key. This means any key in the TOML file becomes a class attribute, even if not declared as a class variable. Declared class variables (with type hints) serve as documentation and defaults — the TOML file overrides them.

## Data flow: processing a single page

```
1. wiki.page(page_name)              → pywikibot.Page object
2. pwb_page.text                     → raw wikitext string
3. Wikitext(metadata)                → wraps metadata (title, revid, etc.)
4. wikitext.parse(content)           → mwparserfromhell parses into Wikicode
5. for each @job:                    → extension mutates wikitext.wikitext in place
     old = str(wikitext.wikitext)
     job(wikitext)
     new = str(wikitext.wikitext)
     if changed: log + record step
6. if submit_changes:                → page.text = new; page.save()
   else:                             → clipboard + browser (manual mode)
```

## The Wiki class (`wiki.py`)

The `Wiki` class wraps pywikibot with several key behaviors:

- **Lazy site init**: The `site` property creates the `pywikibot.Site` on first access. This validates the OAuth token and configures the Qiuwen family.
- **Tick/suppression check**: Every 20 API requests, `tick()` calls `_check_suppressed_action()`, which queries `User:<bot_name>/block` for revision changes. If changed, the bot emails recipients and calls `sys.exit(1)` — this is the "kill switch."
- **HTTP monkey-patch**: `guarded_request` wraps `http.session.request` to inject OAuth headers and call `wiki.tick()` on every HTTP request. This ensures suppression checks happen even for pywikibot's internal API calls.

## Adding a new feature

Where to put things:

| Type | Location |
|------|----------|
| New wiki operation | Add method to `Wiki` class in `core/wiki.py` |
| New wikitext manipulation | Add method to `Wikitext` class in `core/wikitext.py` |
| New settings field | Add class attr in `core/settings.py` + entry in `settings.toml` |
| New processing step | Add to `processor/do_jobs.py` `_process_single_page()` |
| New CLI flag | Add to `main.py` argparse, create processor if needed |
| New utility | Add to `utilities/` |
| New extension | Add `.py` file to `extensions/` |

## Testing

There is no test framework yet (see TODO.md). The current testing path is:

- **Dev mode**: `python main.py --dev input.wikitext output.wikitext` — offline extension testing
- **Import check**: `python -c "from src.Yugong.core.wiki import wiki"` — verifies import chain
- **Manual run**: Set `bypass_confirm_settings = true` and `submit_changes = false` in `settings.toml`, point at a small page set, and review the clipboard output

## Dependency tiers

```
Tier 1 (always needed):  mwparserfromhell
Tier 2 (production):     pywikibot, toml, requests, beautifulsoup4
Tier 3 (manual mode):    pyperclip (clipboard)
Tier 4 (dev):            mypy, types-requests
```

`dev_mode.py` only needs Tier 1 — it can run without pywikibot or toml installed.

## Known technical debt

- **`bot_db.py`** — fully implemented but never wired into anything. Intended to cache template info to reduce API requests.
- **`wikitext.py`** — tagged `#TODO: Unfinished`. Missing link and tag manipulation methods beyond basic parse/update.
- **`check_allow_bots`** — `get_user_talk()` returns a page *title* string, but the method regexes it as if it were page *content*. Needs to fetch actual page text.
- **Safety checks not enforced** — `max_acceptable_diff_size`, `safe_tag_list`, `unsafe_tag_list` exist in settings but aren't checked anywhere in the processing pipeline.
- **Cangjie** — `enable_cangjie` setting exists but the Chinese variant conversion is not implemented.
- **`models/` directory** — legacy; only `marks.py` remains. Should be moved to `core/` or `utilities/`.
- **No tests** — the project has no test infrastructure.
- **Qiuwen-only** — the `QiuwenFamily` in `pwb_related.py` hardcodes the wiki family. Supporting other wikis requires additional family registration.
