# Deployment Guide

How to configure and run YuGong as an automated robot (bot).

## Prerequisites

- Python 3.10+
- A wiki account with bot permissions
- An OAuth token for the bot account

## Configuration

### 1. `settings.toml`

In most cases, you need to set your wiki connection information in wiki.py and pwb_related.py

Minimum configuration for robot mode:

```toml
# Wiki connection
api_endpoint = "https://your-wiki.example.com/"
user_agent = "Yugong/1.0 (YourName; contact@example.com)"
is_owner_only = true
bot_name = "YourBotName"
wiki_domain = "your-wiki.example.com"

# Task definition (choose one or both)
linked_template = "Template:Navbox"   # process pages using this template
category = "Pages needing cleanup"   # process pages in this category

# Robot behavior
bypass_confirm_settings = true
submit_changes = true
edit_comment = "Bot: automated cleanup (Yugong)"
mail_recipients = ["admin@example.com"]
```

### 2. Environment variables

```bash
export MW_OAUTH_TOKEN="your_oauth_access_token"
export MAIL_ACCOUNT="bot@example.com"      # optional, for alert emails
export MAIL_PASSWORD="your_app_password"    # optional, for alert emails
```

### 3. Install dependencies

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Running

### One-shot run

```bash
python main.py
```

With `bypass_confirm_settings = true`, it runs without prompts. With `submit_changes = true`, it saves changes directly.

### Cron / scheduled task

Run daily at 3 AM:

```cron
0 3 * * * cd /path/to/Yugong && /path/to/Yugong/.venv/bin/python main.py >> /var/log/yugong.log 2>&1
```

## Robot vs manual mode

| Setting | Robot mode | Manual mode |
|---------|-----------|-------------|
| `bypass_confirm_settings` | `true` | `false` |
| `submit_changes` | `true` | `false` |
| User prompts | None | 4 confirmation prompts |
| After processing | Saves directly | Clipboard + browser for manual paste |

## Safety mechanisms

- **OAuth only.** Bot password login is not supported. The OAuth token is read from the `MW_OAUTH_TOKEN` environment variable — never hardcode it.
- **Suppression check.** Every 20 API requests, the bot checks `User:<bot_name>/block` on the wiki. If the revision has changed (indicating a block), it emails the configured recipients and exits immediately.
- **Edit comments.** Every edit is tagged with `edit_comment`. Set this to something descriptive so other editors can identify the bot's edits.
- **Dry-run testing.** Before deploying to production, test against a small page set by using `linked_template` pointing to a test template, or test locally with dev mode.

## Alert emails

If `mail_recipients` is configured and `MAIL_ACCOUNT`/`MAIL_PASSWORD` environment variables are set, the bot sends email alerts for:

- **Duplicate run detected** — the bot's daily heartbeat indicates it already ran today
- **Bot suppressed** — the wiki admin has blocked the bot

Email is sent via SMTP (smtp.office365.com). To use a different SMTP server, edit `src/Yugong/core/mailer.py`.

## Logs

Logs are written to the `logs/` directory. Each major component gets its own log file: `wiki.log`, `Yugong.log`, etc. Log files rotate at 10 MB with 5 backups kept.
