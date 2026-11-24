# YuGong Bot

> There is a new `dev` branch now! We try to use `mwparserfromhell` there instead of the current one Yugong developed.

## Project Overview

YuGong is a Python-based automated wiki editing tool designed to help users batch process page content on specific wiki sites. The project provides a flexible extension mechanism that allows users to customize various template processing tasks.

## Core Features

- **Automated Wiki Editing**: Supports batch page processing on specified wiki sites
- **Task Processing**: Support template (`{{}}`), link(`[[]]`/`[]`) and tags (`<foo>`)
- **Page Selection**: Pick pages by id range, by the template they transclude (`linked_template`), or by category membership (`category`) — the sources combine and deduplicate
- **Template Rules**: TOML rules in `template_rules/` are applied before the ordinary extensions run (after any `@job(pre_template=True)` normalisation)
- **Safety First**: If something might lead to vandalism, make the entire program doesn't work.
- **Extensible Architecture**: Tasks are registered through the `Extensions` directory
- **Safety Controls**: Built-in risk control mechanisms including diff size checking, dangerous tag detection, a PID-based run lock and a wiki-side kill switch
- **Offline Dev Mode**: `python main.py --dev INPUT OUTPUT` runs the whole pipeline against a local wikitext file without editing anything
- **NoteTA / CGroup category conversion**: the `category_handler` extension reads each page's `{{NoteTA}}` (inline rules, `T=` title rules, `G1`..`G30` groups), follows the wiki's `Module:CGroup/*` / `Template:CGroup/*` data (including `import`/`require` wrappers), and applies those rules to category names for the `zh-cn` target with `zh-hans`/`zh` fallback. Group data is cached in the per-wiki SQLite DB. OpenCC `tw2s` provides the script-level conversion.
- **Cangjie (optional)**: with `enable_cangjie = true`, the `cangjie` extension converts visible article text to `zh-cn` using the same NoteTA/CGroup rules, then OpenCC `tw2s`. Pages without NoteTA still get the OpenCC script-level conversion (no page-specific terminology rules). Template names/parameters, category/file links, `-{...}-` markup, URLs and code-like tags are left untouched.
- **Lint / obsolete-syntax fixes**: `lint_fixes` converts obsolete `<font>`, turns every `<center>` into `{{Center|…}}` (escaping top-level pipes), handles `<big>/<tt>/<strike>`, folds `align/valign/width/height/bgcolor/border` into CSS (including wikitable cells), pairs self-closing non-void tags, removes empty headings and empty list items, drops duplicate bare image sizes, and removes empty category sort keys.
- **Category policy (QW:CAT)**: `category_policy` normalises category links to the `Category:` prefix, removes duplicate category links and redundant sort keys (empty, page title, category name, deprecated/full-width punctuation, and pure pinyin/English indexes), and adds `{{catnav|auto=1}}` to category pages that lack it.
- **Reference and citation hygiene**: `fix_cite_template` rejoins pipe fragments in `Cite*` parameters, deletes unfixable leading anonymous params and removes nested `Cite*` calls; `fix_duplicate_refs` renames later conflicting repeat `<ref>` definitions to `name-1`, `name-2`, …; `fix_unclosed_syntax` closes trailing unclosed `[[`/`{{`/`<!--`; `rm_undefined_refs` drops contentless refs with no definition.
- **Nowrap / `.w` fixes**: `nowrap_fixes` converts navbox `list`/`group`/`above`/`below` values that use `.w`/`!w`/`-w` into unordered lists (with the required newline after `=`); it leaves existing nowrap pairs, nested/newline items and non-navbox uses alone and reports them.
- **ISBN normalisation (optional)**: with `enable_isbn_normalise = true`, the `isbn_normalise` extension hyphenates valid ISBN-10/13 values in `{{ISBN}}`/`{{ISBNT}}`/citation templates using the bundled International ISBN Agency range data, cleans up `Special:网络书源` links, and can convert ISBN-10 to ISBN-13. `isbn_template_style` handles the different `{{ISBN}}` conventions: Qiuwen treats parameters 1–9 as a list of ISBNs, while Moegirl treats parameter 2 as display text.
- **Invisible-character cleanup (optional)**: with `enable_invisible_chars_fix = true`, `rm_invisible_chars` removes zero-width spaces, BOMs, word joiners, soft hyphens and stray control characters from text, template names/parameters, links and tag attributes, skipping `nowiki`/`code`/`math` contents and HTML comments. `invisible_chars_aggressive` additionally removes ZWNJ/ZWJ, bidi controls and the Arabic letter mark.
- **Void redirects**: `rm_void_template` preloads the wiki's 1,300+ redirects to `Template:Void`, follows redirect chains, and removes those no-op templates from pages without per-template API calls.
- **Reviewed deprecated-template rules**: `template_rules/` contains per-family rules that were reviewed one template at a time: the `Internal link helper` family (including 92 language subpages and 90 `Link-*` aliases → plain internal links), `Translink`/`Tsl`, `Interlanguage link multi` → `多語言連結`, `城市`/`國家基礎資訊` exact wrappers, `Double image` → `Multiple image`, `Short description` deletion, `Font color` → `Color`, and several direct-link country templates. The `.w`/`!w`/`-w` series is handled by `extensions/nowrap_fixes.py`: navbox `list`/`group`/`above`/`below` values become unordered lists, while non-navbox and nowrap-wrapped uses are left alone. Templates that need parameter-aware migration or a module rewrite are deliberately left unchanged; see `docs/deprecated-template-review.md`. The `國家基礎資訊` rule expands to a large `{{Infobox country}}` call and needs a higher `max_acceptable_diff_size` than the default 1000.

## Installation and Configuration

### Requirements

- Python 3.10+
- The packages listed in [requirements.txt](requirements.txt)

### Installation Steps

1. Clone the project repository
2. Install the dependency environment
3. Configure [settings.toml](settings.toml)
4. Run:

```shell
cd path_to_project
python3 -m venv .venv
source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -r requirements.txt

python3 main.py
```

For an editable install (needed if you want a stable `src.Yugong...` import from anywhere) and the development tools, use:

```shell
pip install -e ".[dev]"
```

### Configuration Guide

Set up [settings.toml](settings.toml). At minimum you must provide `api_endpoint` plus one way of selecting pages (`page_id_start`/`page_id_end`, `linked_template` or `category`); the program validates the file before touching the wiki and refuses to start with a descriptive message when something is missing or contradictory.

Note that we currently do not support login methods other than OAuth token, and OAuth token requires setting the environment variable `MW_OAUTH_TOKEN` (the older `MW_BOT_OAUTH_TOKEN` still works as a legacy fallback). And now you must set `is_owner_only` to true in setting file.

Set `YUGONG_SETTINGS` to point at an alternative settings file (a second wiki, an isolated test run, …) instead of `<repo>/settings.toml`.

## Extension Development

### Creating New Extensions

Follow these steps to create custom extensions:

1. Copy [example.py](src/Yugong/extensions/example.py) in the `Extensions` directory and rename it
2. Modify the function name and task definition
3. Implement specific template processing logic
4. Add task introduction description

See the [Extension Development Guide](docs/extension-dev.md) for the `needs_wiki` marker and the offline test loop.

## Usage Workflow

1. **Initialization Confirmation**: User confirms understanding of usage responsibilities (skipped when `bypass_confirm_settings = true`)
2. **Configuration Loading**: Read and validate [settings.toml](settings.toml) configuration
3. **Task Preview**: Display all extension task descriptions and the loaded template rules
4. **Execution Processing**: Connect to wiki instance and execute processing
5. **Result Output**: Show processing results and provide follow-up actions:
   1. **Auto submit (`submit_changes = true`)**: The new text is saved with `edit_comment` as the summary
   2. **Manual review (`submit_changes = false`)**: The new text is copied to the clipboard, the editor page is opened in the browser, and the program blocks until the user has pasted and submitted it

## Safety Mechanisms

- **User Confirmation**: Mandatory user confirmation of responsibilities and configurations
- **Risk Control**: Configurable risk level controls
- **Diff Checking**: Validation of edit differences before and after (`max_acceptable_diff_size`)
- **Dangerous Tag Detection**: `unsafe_tag_list` (deny-list) or `safe_tag_list` (allow-list); a forbidden tag aborts the run by default (`is_dangerous_tag_unacceptable = true`) or skips just that page
- **Run Lock**: A PID-based lock in `data/lock` stops two YuGong processes from editing at once; stale locks from dead processes are reclaimed
- **Kill Switch**: Every 20 API requests the bot checks `User:<bot_name>/block` and stops if the page's revision changed
- **Daily Heartbeat**: With `enable_heartbeat = true`, a duplicate run on the same UTC day logs, e-mails and stops
- **Strong Data Type/Checking**: Make sure no error on input data

## Testing

The test suite is plain `unittest` (no pytest dependency):

```shell
python -m unittest discover
```

Type checking uses the configuration in `pyproject.toml`:

```shell
mypy
```

## Important Notes

**Important Reminder**:

- This software is provided "as is" without warranty of any kind
- Users bear full responsibility for usage
- Must ensure usage complies with all applicable laws and regulations in your jurisdiction
- Including but not limited to the laws of the People's Republic of China

## Documentation

- [Extension Development Guide](docs/extension-dev.md) — how to write `@job`/`@intro` extensions
- [Template Rules Reference](docs/template-rules.md) — TOML-based template transformation rules
- [Deployment Guide](docs/deployment.md) — configuring and running as an automated bot
- [Dev Mode](docs/dev-mode.md) — testing extensions locally without a wiki connection
- [Maintainer Guide](docs/maintainer.md) — architecture, patterns, and technical debt for codebase maintainers

## Contributing

Contributions are welcome, as long as follow the [legal terms](LEGAL.md). Please read [CONTRIBUTIONS.md](CONTRIBUTIONS.md).
