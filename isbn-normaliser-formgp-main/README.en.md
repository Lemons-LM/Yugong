[![Update Range File](https://github.com/Kelly-Hsueh/ISBN-normaliser-forMGP/actions/workflows/update-rangemessage.yml/badge.svg?event=schedule)](https://github.com/Kelly-Hsueh/ISBN-normaliser-forMGP/actions/workflows/update-rangemessage.yml)

[中文](README.md) | [English](README.en.md)

# ISBN Normaliser

A standalone normalisation tool and MediaWiki bot for the {{[ISBN](https://mzh.moegirl.org.cn/Template:ISBN)}} template in MoegirlPedia wikitext. The normaliser script can also run independently.

## Core Features

- **isbn_normalise.py** — Pure ISBN normalisation library
  - Hyphenate ISBN-10/13 per international registration group rules
  - Optional: Convert ISBN-10 to ISBN-13

- **isbn_template_normalise.py** — Wikitext template normalisation tool
  - Batch-process `{{ISBN}}` template parameters
  - Optional: Convert ISBN-10 to ISBN-13
  - Optional: When parameter 1 and 2 are semantically identical, replace the template with `{{ISBNT|$1}}`, where `$1` is the hyphenated ISBN

- **mw_bot_core.py** — Generic MediaWiki infrastructure layer
  - Environment loading, HTTP helpers, login/CSRF auth, page read/write
  - No ISBN-specific logic; can be reused by other MediaWiki bot scripts

- **mw_isbn_bot.py** — MediaWiki bot runtime
  - Supports multiple page fetch strategies (selected via `--query` / `-q`)
  - `transcludedin`: fetch pages transcluding Template:ISBN and their revisions via `generator=transcludedin`
  - `booksource-search`: find pages containing `Special:BookSources/` links via `insource:` full-text search
  - Automatic pagination via API continue and revision version continuation (rvcontinue)
  - Detect and log API size limit warnings while continuing to fetch remaining data
  - Allowbots compliance check before editing
  - Configurable edit count limit per run
  - Automatically composes per-page edit summaries based on the actual types of changes made

## Dependencies

- `RangeMessage.xml` — Range message file from International ISBN Agency

## Environment And Packages

- Python 3.10+ (3.11 recommended, consistent with GitHub Actions)
- Third-party packages (not required if only processing one single ISBN, not wikitext):
  - `requests`
  - `brotli`
  - `mwparserfromhell`

Quick install:

```bash
python -m pip install --upgrade pip
pip install requests brotli mwparserfromhell
```

## Quick Start

```bash
git clone https://github.com/Kelly-Hsueh/ISBN-normaliser-forMGP.git
cd ISBN-normaliser-forMGP
python -m pip install --upgrade pip
pip install requests brotli mwparserfromhell
```

Then ensure `RangeMessage.xml` is available (already included in this repository), and run the commands below.

## Usage

### Command-line Tool

**Normalise a single ISBN:**
```bash
python isbn_normalise.py \
  --xml RangeMessage.xml \
  9787302511625
```

**Format templates in a single file:**
```bash
python isbn_template_normalise.py \
  --xml RangeMessage.xml \
  --text-file your_wikitext.txt \
  -format \
  --in-place
```

**Format + convert to ISBN-13:**
```bash
python isbn_template_normalise.py \
  --xml RangeMessage.xml \
  --text-file your_wikitext.txt \
  -format -to13 \
  --in-place
```

**Format + convert semantically equal params to ISBNT:**
```bash
python isbn_template_normalise.py \
  --xml RangeMessage.xml \
  --text-file your_wikitext.txt \
  -format \
  --rehyphenate-equal-label \
  --in-place
```

### MediaWiki Bot

Once `.env.pwd` is configured (see below), you only need:

```bash
# Dry run (test without saving)
python mw_isbn_bot.py --dry-run

# Live run with edit limit
python mw_isbn_bot.py --max-edits 10

# Specify a fetch strategy
python mw_isbn_bot.py -q ti --dry-run         # transcludedin, short form
python mw_isbn_bot.py -q bs --dry-run         # booksource-search, short form
```

Credentials can also be passed directly on the command line (not recommended for regular use):

```bash
python mw_isbn_bot.py \
  --bot-username MyBot \
  --bot-password MyBotPassword \
  --max-edits 10
```

#### Fetch Strategies (`--query` / `-q`)

| Value | Alias | Description |
|-------|-------|-------------|
| `transcludedin` | `ti` | Fetch all pages transcluding Template:ISBN (default) |
| `booksource-search` | `booksource`, `bs` | Full-text search for pages containing `Special:BookSources/` links |

The default strategy is controlled by `DEFAULT_QUERY` in `.env`, falling back to `transcludedin` if unset.

## GitHub Actions Automation

### 1) ISBN Bot Workflow

File: `.github/workflows/isbn-normaliser-bot.yml`

1. **Manual trigger (workflow_dispatch)**
  - `query` — Fetch strategy (leave empty to use `DEFAULT_QUERY` from `.env`)
  - `dry_run` — Whether to run without saving edits
  - `max_edits` — Edit count limit for this run (leave empty for unlimited)
  - Open the Actions tab and click "Run workflow"

2. **Scheduled execution**
  - Runs automatically on the 1st of every other month at UTC `20:15` (cron: `15 20 1 */2 *`)

3. **Running multiple strategies (optional)**
  - Use a GHA matrix to run strategies in parallel:
    ```yaml
    strategy:
      matrix:
        query: [transcludedin, booksource-search]
    steps:
      - run: python mw_isbn_bot.py --query ${{ matrix.query }}
    ```

### 2) RangeMessage Auto-update Workflow

File: `.github/workflows/update-rangemessage.yml`

1. **Trigger modes**
  - Manual trigger (`workflow_dispatch`)
  - Weekly scheduled run every Wednesday at UTC `03:05` (cron: `05 3 * * 3`)

2. **Behaviour**
  - Downloads the latest `RangeMessage.xml`
  - Commits and pushes only when the file content changes

3. **Required permission**
  - Workflow declares `contents: write` to allow commit and push

### 3) Booksource Aliases Auto-update Workflow

File: `.github/workflows/update-booksource-aliases.yml`

1. **Trigger modes**
  - Manual trigger (`workflow_dispatch`)
  - Biannual scheduled run on January 1st and July 1st at UTC `03:05` (cron: `05 3 1 1,7 *`)

2. **Behaviour**
  - Fetches all localised aliases for the `Booksources` special page from the MoegirlPedia API
  - Canonicalises them (casefold, strip spaces and underscores) and updates the `BOOKSOURCE_PAGE_ALIASES` constant in `isbn_template_normalise.py` in-place
  - Idempotent — commits only when the value actually changes

3. **Required permission**
  - Workflow declares `contents: write` to allow commit and push

## File Overview

- `isbn_normalise.py`:
  - Core ISBN normalisation logic
  - Only handles single-ISBN input/output

- `isbn_template_normalise.py`:
  - Batch rewrite logic for `{{ISBN}}` templates in wikitext
  - `ChangeReport` dataclass tracks four change types: BookSources link replacement, hyphen normalisation, ISBN-10 conversion, ISBNT merge
  - Reused by `mw_isbn_bot.py` and template-oriented CLI workflows

- `mw_bot_core.py`:
  - Generic MediaWiki infrastructure (env loading, HTTP, auth, page read/write)
  - No ISBN-specific dependencies; can be reused by other bot scripts directly

- `mw_isbn_bot.py`:
  - MediaWiki bot entrypoint
  - Handles login, paginated page fetch, Allowbots checks, per-page summary composition, and edit submission

- `RangeMessage.xml`:
  - ISBN range rule source file
  - Published by the International ISBN Agency and used by the normalisation logic

- `.env`:
  - Public configuration (wiki URL, user-agent, template names, default query strategy); version-controlled

- `.env.pwd`:
  - Private bot credentials (username and password); listed in `.gitignore`, **never committed**

- `.env.pwd.example`:
  - Template for `.env.pwd`; version-controlled

- `.github/workflows/isbn-normaliser-bot.yml`:
  - Bot execution workflow (manual trigger + bimonthly schedule)

- `.github/workflows/update-rangemessage.yml`:
  - Workflow to update `RangeMessage.xml` automatically (weekly)

- `.github/workflows/update-booksource-aliases.yml`:
  - Workflow to update `BOOKSOURCE_PAGE_ALIASES` automatically (biannual)

## Environment Configuration

The project uses a two-file configuration scheme to separate public settings from private credentials:

| File | Version-controlled | Purpose |
|------|--------------------|---------|
| `.env` | ✅ Committed | Wiki URL, user-agent, template names, default query strategy |
| `.env.pwd` | ❌ Listed in `.gitignore` | Bot credentials (username and password) |

### `.env` (public, ships with the repository)

The repository already contains defaults for MoegirlPedia:

```ini
WIKI_API=https://mzh.moegirl.org.cn/api.php
USER_AGENT=ISBNNormaliser-Bot/1.1 (...)
TEMPLATE_TITLE=Template:ISBN|Template:ISBNT|Template:Cite book
DEFAULT_QUERY=transcludedin
XML_PATH=RangeMessage.xml
REHYPHENATE_EQUAL_LABEL=false
TO13=false
SUMMARY=根据 ISO 2108:2017（...）自动调整ISBN（...）
EDIT_TAGS=Bot
```

| Variable | CLI flag | Description |
|----------|----------|-------------|
| `WIKI_API` | `--wiki-api` | MediaWiki API endpoint |
| `USER_AGENT` | `--user-agent` | HTTP User-Agent string |
| `TEMPLATE_TITLE` | `--template-title` | Template name(s), `\|`-separated |
| `DEFAULT_QUERY` | `--query` / `-q` | Default fetch strategy |
| `XML_PATH` | `--xml` | Path to RangeMessage.xml |
| `REHYPHENATE_EQUAL_LABEL` | `--rehyphenate-equal-label` | Merge semantically equal params into ISBNT |
| `TO13` | `-to13` | Convert ISBN-10 to ISBN-13 |
| `SUMMARY` | `--summary` | ISO 2108 notice appended to every edit summary |
| `EDIT_TAGS` | `--edit-tags` | Change tag(s) applied to edits; multiple tags are pipe-separated (e.g. `Bot\|test`); set to an empty string to apply no tag |

To adapt to a different wiki, edit this file and commit the change. All fields can be overridden temporarily via the corresponding CLI flag.

### `.env.pwd` (private, local/server use only)

Copy `.env.pwd.example` and fill in real values:

```ini
BOT_USERNAME=YourBot@BotPassword
BOT_PASSWORD=your_bot_password_here
```

### GitHub Actions

Only `BOT_USERNAME` and `BOT_PASSWORD` need to be added to GitHub Secrets. Public configuration is carried in by `actions/checkout` automatically — no extra steps required.

### Priority

```
CLI flag > system env var (including GHA env: injection) > .env.pwd > .env > built-in default
```

## Normalisation Rules

- Always normalise template parameter 1 (when valid)
- Keep parameter 2 unchanged by default
- Only when explicitly enabled and semantically identical: rewrite the template as `{{ISBNT|$1}}` and keep parameter 1 hyphenated
- Edit summaries are composed automatically per page based on the actual types of changes made, with components joined by fullwidth semicolons (`；`) and the ISO 2108 notice always appended last:

  | Trigger | Summary component |
  |---------|-------------------|
  | Replaced `[[Special:BookSources/…]]` links | `替换[[Special:BookSources/]]为{{[[T:ISBN\|ISBN]]}}` |
  | Converted ISBN-10 to ISBN-13 | `将 ISBN-10 转换为 ISBN-13` |
  | Merged semantically equal params into `{{ISBNT}}` | `自动使用{{[[T:ISBNT\|ISBNT]]}}` |
  | Any change (always appended) | `根据 ISO 2108:2017（…）自动调整ISBN（…）` |

  The ISO 2108 notice text is configurable via the `SUMMARY` env var or `--summary` flag.

## Troubleshooting

- `ModuleNotFoundError`:
  - Run `pip install requests brotli mwparserfromhell`

- `RangeMessage.xml` not found:
  - Ensure the file exists in the current directory, or pass the correct path using `--xml`

- `BOT_USERNAME` / `BOT_PASSWORD` missing:
  - Ensure `.env.pwd` exists and is filled in, or pass `--bot-username` / `--bot-password` on the command line

- Bot does not make edits:
  - Run with `--dry-run` first and check whether candidate pages are detected
  - Check whether `--max-edits` is set to 0
  - Verify bot permissions and local Allowbots/editing policy on the target wiki

- GitHub Actions run has no commit:
  - For `update-rangemessage` and `update-booksource-aliases`, "No changes to commit" is expected when upstream data did not change

## References

- [ISO 2108:2017](https://www.iso.org/standard/65483.html)
- [International ISBN Agency](https://www.isbn-international.org/range_file_generation)
