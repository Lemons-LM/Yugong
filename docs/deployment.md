# Deployment Guide

How to configure and run YuGong as an automated robot (bot).

## Prerequisites

- Python 3.10+
- A wiki account with bot permissions
- An OAuth token for the bot account

## Configuration

### 1. `settings.toml`

All wiki connection information lives in `settings.toml`; there is no need to edit `wiki.py` or `pwb_related.py`.

Minimum configuration for robot mode:

```toml
# Wiki connection
api_endpoint = "https://your-wiki.example.com/"   # directory holding api.php, or the api.php URL itself
user_agent = "Yugong/1.0 (YourName; contact@example.com)"
is_owner_only = true                               # must stay true: only OAuth is supported
bot_name = "YourBotName"
wiki_domain = "your-wiki.example.com"
wiki_lang = "zh"
wiki_family = "qiuwen"
wiki_tag = "yourwiki"                              # names cache/<wiki_tag>.json — use one tag per wiki

# Task definition (set at least one)
linked_template = "Navbox"           # pages transcluding Template:Navbox (no "Template:" prefix)
category = "Pages needing cleanup"   # members of Category:Pages needing cleanup (no "Category:" prefix)
# page_id_start = 1                  # or a page-id range
# page_id_end = 500

# Robot behavior
bypass_confirm_settings = true
submit_changes = true
edit_comment = "Bot: automated cleanup (Yugong)"
enable_cangjie = false              # true = NoteTA/CGroup-based zh-cn text conversion
mail_recipients = ["admin@example.com"]

# Safety limits
max_acceptable_diff_size = 1000       # reject edits whose changed-character count exceeds this
is_dangerous_tag_unacceptable = true  # abort the run when a forbidden tag is found
# unsafe_tag_list = ["script"]        # deny-list; or safe_tag_list (allow-list) — never both
enable_heartbeat = true               # refuse to run twice on the same UTC day
request_max_tries = 3
request_timeout = 30
log_level = 3                         # 0=CRITICAL, 1=ERROR, 2=WARNING, 3=INFO, 4=DEBUG
```

`settings.toml` is validated before anything touches the wiki. Missing or contradictory values abort with a descriptive message; see `Settings.validate()` in `src/Yugong/core/settings.py` for the full list. To use a second configuration file (e.g. a second wiki), set the `YUGONG_SETTINGS` environment variable to its path.

### 2. Environment variables

```bash
export MW_OAUTH_TOKEN="your_oauth_access_token"
export MAIL_ACCOUNT="bot@example.com"      # optional, for alert emails
export MAIL_PASSWORD="your_app_password"    # optional, for alert emails
```

`MW_BOT_OAUTH_TOKEN` is still accepted as a legacy fallback, but `MW_OAUTH_TOKEN` is the documented name and takes precedence.

### 3. Install dependencies

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Running

### Read-only preflight

Before configuring a page selector, check that this machine can reach the wiki:

```bash
python main.py --check
```

It validates `api_endpoint`, requires `MW_OAUTH_TOKEN`, queries `siteinfo` and
exits. It never edits anything. A WAF/CAPTCHA block is reported here instead of
showing up as a confusing page-processing failure later.

### One-shot run

```bash
python main.py
```

With `bypass_confirm_settings = true`, it runs without prompts. With `submit_changes = true`, it saves changes directly.

The program holds a PID-based lock in `data/lock` for the whole run, so a second invocation refuses to start while the first is alive. Stale locks from crashed processes are reclaimed automatically.

### Cron / scheduled task

Run daily at 3 AM:

```cron
0 3 * * * cd /path/to/Yugong && /path/to/Yugong/.venv/bin/python main.py >> /var/log/yugong.log 2>&1
```

With `enable_heartbeat = true`, a duplicate run on the same UTC day logs, sends an alert email and stops instead of editing twice.

## Robot vs manual mode

| Setting | Robot mode | Manual mode |
|---------|-----------|-------------|
| `bypass_confirm_settings` | `true` | `false` |
| `submit_changes` | `true` | `false` |
| User prompts | None | Up to 4 confirmation prompts |
| After processing | Saves directly with `edit_comment` | Clipboard + browser for manual paste, blocks until a key is pressed |

## Page selection

The three selectors combine and deduplicate:

- `page_id_start`/`page_id_end` — resolved through batched `action=query&pageids=` calls, 50 ids per request. `page_id_end = 0` means "just `page_id_start`"; a span larger than `MAX_PAGEID_SPAN = 5000` is rejected.
- `linked_template` — every page transcluding `Template:<value>` (`embeddedin`).
- `category` — every member of `Category:<value>`.

The resolved todo list is merged with the pages still queued in `cache/<wiki_tag>.json`. If that cache was written for a different `api_endpoint`, the run aborts and asks you to change `wiki_tag`.

## Safety mechanisms

- **OAuth only.** Bot password login is not supported. The OAuth token is read from the `MW_OAUTH_TOKEN` environment variable — never hardcode it.
- **Tag policy.** `unsafe_tag_list` is a deny-list and `safe_tag_list` an allow-list; setting both is rejected. A forbidden tag aborts the whole run by default (`is_dangerous_tag_unacceptable = true`) or skips just that page (`false`).
- **Diff limit.** Edits whose changed-character count exceeds `max_acceptable_diff_size` are skipped and reported, and the page stays in the todo list.
- **Suppression check.** Every 20 API requests, the bot checks `User:<bot_name>/block` on the wiki. If the revision has changed (indicating a block), it emails the configured recipients and exits immediately.
- **Edit comments.** Every edit is tagged with `edit_comment`. Set this to something descriptive so other editors can identify the bot's edits.
- **Cangjie.** `enable_cangjie = true` converts visible article text to `zh-cn` using the page's NoteTA/CGroup rules, then OpenCC `tw2s` (`opencc` is now installed by `requirements.txt`). Pages without NoteTA still get the OpenCC script conversion; template names/parameters, category/file links, `-{...-}`, URLs and code tags are left intact. The normal diff limit still applies. Because NoteTA-less pages have no regional-term guard, review the first run before enabling it wiki-wide, especially for Hong Kong/Macau/Taiwan-heavy content.
- **Lint / obsolete syntax.** `lint_fixes` handles `<font>`, every `<center>` (via `{{Center|…}}`, with top-level pipes escaped; table/unknown-attribute cases are left alone), `<big>/<tt>/<strike>`, `align/valign/width/height/bgcolor/border` on HTML and wikitable cells, self-closing non-void tags, empty headings, empty list items, duplicate bare image sizes, and empty category sort keys. Template-caused lint errors and the riskier categories listed in the extension docstring remain manual work.
- **Category policy / Void redirects.** `category_policy` applies the automatable QW:CAT rules (prefix, duplicate links, redundant sort keys, `{{catnav|auto=1}}`). `rm_void_template` preloads the 1,300+ `Template:Void` redirects and removes those no-op templates from pages. Reading `Category:` page content needs the bot account's read permission.
- **Reviewed deprecated-template rules.** `template_rules/` contains the rules reviewed one template at a time: the `Internal link helper` family (plain internal links), `Translink`/`Tsl`, `Interlanguage link multi` → `多語言連結`, `城市`/`國家基礎資訊` exact wrappers, `Double image`, `Short description` deletion, `Font color` → `Color`, and several direct-link country templates. The `.w`/`!w`/`-w` series is handled by `nowrap_fixes` (navbox list rows → unordered lists; non-navbox uses reported). Templates that need parameter-aware migration or a module rewrite are left unchanged; see `docs/deprecated-template-review.md`. The `國家基礎資訊` rule expands to a ~6.5k-character `{{Infobox country}}` call, so a run using it needs `max_acceptable_diff_size` well above the default 1000.
- **Dry-run testing.** Before deploying to production, test against a small page set by using `linked_template` pointing to a test template, or test locally with dev mode.

## Alert emails

If `mail_recipients` is configured and `MAIL_ACCOUNT`/`MAIL_PASSWORD` environment variables are set, the bot sends email alerts for:

- **Duplicate run detected** — the bot's daily heartbeat indicates it already ran today
- **Bot suppressed** — the wiki admin has blocked the bot
- **End-of-run report** — pages skipped or failed during the run (`Yugong Report`)

Email is sent via SMTP (smtp.office365.com). To use a different SMTP server, edit `src/Yugong/core/mailer.py`.

## Logs

Logs are written to the `logs/` directory. Each major component gets its own log file: `wiki.log`, `Yugong.log`, etc. Log files rotate at 10 MB with 5 backups kept. The verbosity comes from `log_level` (0-4, see the table above); `log_timestamp` controls the timestamp prefix in the files.
