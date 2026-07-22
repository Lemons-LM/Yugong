- [x] Change the Wikitext Parser to `mwparserfromhell` — done on `dev` branch
- [x] Change Wiki's interact method to `pywikibot` — done on `dev` branch
- [x] Robot/auto mode — `bypass_confirm_settings` + `submit_changes` enables unattended runs
- [x] Package restructure — `models/` → `core/`, `utils/` → `utilities/`

## Pending

- [ ] **Design tag processing** — Wikitext currently handles templates and links, but `<tag>` processing is not implemented
- [ ] **Write extensions** — only `example.py` exists; no real extensions have been written
- [ ] **Write tests** — no test infrastructure exists yet
- [ ] **Wire up BotDB** — `bot_db.py` is fully implemented but unused; it should cache template info to avoid repeated API requests
- [ ] **Implement safety checks** — `max_acceptable_diff_size`, `safe_tag_list`/`unsafe_tag_list` are configurable in settings but not enforced in code
- [ ] **Implement Cangjie (Chinese variant conversion)** — `enable_cangjie` exists in settings but is not wired up
- [ ] **Login methods other than OAuth** — currently only `MW_OAUTH_TOKEN` env var is supported
- [ ] **`wikitext.py`** — the `#TODO: Unfinished` comment: needs link manipulation methods beyond basic parse/update
- [ ] **`check_allow_bots` in wiki.py** — `get_user_talk()` returns a page *title* string, but the method regexes it as if it were page *content*; needs to fetch actual page text first
- [ ] **Check comparison logic** — a function that handled Python comparison edge cases was removed; verify no logic is broken
- [ ] **Remote wikis** — currently hardcoded for Qiuwen (`qiuwen` family in `pwb_related.py`); supporting other wikis requires family config changes
- [ ] **`settings.toml`** — `is_owner_only` must be `true` (only OAuth supported); `page_id_start`/`page_id_end` range-based page selection is not implemented in `_get_todo_list()`
- [ ] **Non-Qiuwen wikis** — `check_same_website` in `template_formatter.py` only checks domain match against `settings.api_endpoint`; multi-wiki support not tested
