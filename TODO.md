- [x] Change the Wikitext Parser to `mwparserfromhell` — done on `dev` branch
- [x] Change Wiki's interact method to `pywikibot` — done on `dev` branch
- [x] Robot/auto mode — `bypass_confirm_settings` + `submit_changes` enables unattended runs
- [x] Package restructure — `models/` deleted (including `marks.py`, which moved to `utilities/marks.py`), `utils/` → `utilities/`
- [x] Page selection — `page_id_start`/`page_id_end` (batched `pageids` queries, 50 per request), `linked_template` (`embeddedin`) and `category` (category members) are all implemented; the sources combine and deduplicate
- [x] Safety checks enforced — `max_acceptable_diff_size`, `safe_tag_list`/`unsafe_tag_list` and `is_dangerous_tag_unacceptable` are all checked in the processing loop
- [x] Wire up BotDB — `rm_void_template` caches template redirects and `category_handler` caches category redirects in `data/db/db.sqlite3`
- [x] Write tests — 202 stdlib `unittest` cases under `tests/`, run with `python -m unittest discover`
- [x] Tag handling — `Wikitext.tags()` exposes the tags on a page and the processing loop enforces the `safe_tag_list`/`unsafe_tag_list` policy before running any step
- [x] `check_allow_bots` in wiki.py — now fetches the user talk page *content* and fails closed when it cannot be read
- [x] `settings.toml` — `is_owner_only` must be `true` (only OAuth supported); the file is validated before anything touches the wiki

## Pending

- [ ] **Implement Cangjie (Chinese variant conversion)** — `enable_cangjie` is deliberately not wired up: setting it to `true` now raises `NotImplementedError` instead of silently doing nothing. `category_handler` uses OpenCC only when it happens to be installed (it is not a declared dependency) and only for category titles
- [ ] **Login methods other than OAuth** — currently only the `MW_OAUTH_TOKEN` env var is supported (`MW_BOT_OAUTH_TOKEN` is a legacy fallback)
- [ ] **Non-Qiuwen wikis** — `wiki_family`, `wiki_lang` and `wiki_domain` are configurable and the family is registered by `pwb_related.py`, but support has not been tested against a second wiki
- [ ] **Ship template rules** — there are no `template_rules/*.toml` rules yet; `template_rules/example.toml.disabled` is a copy-me template that the loader deliberately ignores (it only globs `*.toml`)
- [ ] **Use the public helpers** — `calculate_length.py`, `signature_parser.py`, `sections_to_page.py` and `marks.py` all have unit tests but no in-repo callers yet
- [ ] **Use the messaging helpers** — `Wiki.mass_message()`, `new_section()` and `get_sections()` are implemented but not called by the processing loop
- [ ] **Write tag-transforming extensions** — the policy check inspects tags, but no shipped extension rewrites them
