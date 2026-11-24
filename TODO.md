- [x] Change the Wikitext Parser to `mwparserfromhell` — done on `dev` branch
- [x] Change Wiki's interact method to `pywikibot` — done on `dev` branch
- [x] Robot/auto mode — `bypass_confirm_settings` + `submit_changes` enables unattended runs
- [x] Package restructure — `models/` deleted (including `marks.py`, which moved to `utilities/marks.py`), `utils/` → `utilities/`
- [x] Page selection — `page_id_start`/`page_id_end` (batched `pageids` queries, 50 per request), `linked_template` (`embeddedin`) and `category` (category members) are all implemented; the sources combine and deduplicate
- [x] Safety checks enforced — `max_acceptable_diff_size`, `safe_tag_list`/`unsafe_tag_list` and `is_dangerous_tag_unacceptable` are all checked in the processing loop
- [x] Wire up BotDB — `rm_void_template` caches template redirects and `category_handler` caches category redirects in `data/db/<wiki_tag>.sqlite3` (one file per wiki)
- [x] Write tests — 345 stdlib `unittest` cases under `tests/`, run with `python -m unittest discover`
- [x] Tag handling — `Wikitext.tags()` exposes the tags on a page and the processing loop enforces the `safe_tag_list`/`unsafe_tag_list` policy before running any step
- [x] `check_allow_bots` in wiki.py — now fetches the user talk page *content* and fails closed when it cannot be read
- [x] `settings.toml` — `is_owner_only` must be `true` (only OAuth supported); the file is validated before anything touches the wiki
- [x] **Cangjie** — `enable_cangjie = true` enables `extensions/cangjie.py`: visible text is converted to `zh-cn` through the page's NoteTA/CGroup rules, then OpenCC `tw2s` (which also resolves 著/着). Pages without NoteTA still get the OpenCC script conversion. Templates, parameters, category/file links, `-{...}-`, URLs and code tags are skipped
- [x] **Reviewed deprecated-template rules** — `template_rules/` now contains the reviewed rules: `Internal link helper` family (92 language subpages + 90 `Link-*` + `Ilh` → plain links), `Translink`/`Tsl`, `Interlanguage link multi` → `多語言連結`, `城市`/`國家基礎資訊` wrappers (only supplied parameters are emitted), `Double image` → `Multiple image`, `Short description` deletion, `Font color` → `Color`, and direct-link rules for `中国大陆`, `中国内地`, `中國電影產地`, `ROC-1940`, `ROC-1938`, `CHN-1928`. The review decisions are recorded in `docs/deprecated-template-review.md`
- [x] **Nowrap / `.w` series** — `extensions/nowrap_fixes.py` converts navbox `list`/`group`/`above`/`below` values using `.w`/`!w`/`-w` into unordered lists (newline after `=`); nowrap-wrapped, nested/newline, and non-navbox uses are left and reported
- [x] **Lint fixes** — `extensions/lint_fixes.py` handles obsolete tags, obsolete presentation attributes (including wikitable cells), self-closing non-void tags, empty headings, empty list items, duplicate bare image sizes and empty category sort keys; every `<center>` becomes `{{Center|…}}`
- [x] **Category policy (QW:CAT)** — `extensions/category_policy.py` normalises the `Category:` prefix, removes duplicate category links and redundant sort keys (including pure pinyin/English indexes and category-name keys), and adds `{{catnav|auto=1}}` to category pages
- [x] **Void redirects** — `rm_void_template` preloads the 1,300+ redirects to `Template:Void`, follows redirect chains, and removes them without per-template API calls

## Pending

- [ ] **Login methods other than OAuth** — currently only the `MW_OAUTH_TOKEN` env var is supported (`MW_BOT_OAUTH_TOKEN` is a legacy fallback)
- [ ] **Non-Qiuwen wikis** — `wiki_family`, `wiki_lang` and `wiki_domain` are configurable and the family is registered by `pwb_related.py`, but support has not been tested against a second wiki
- [ ] **Deprecated templates still needing parameter mapping** — reviewed and deliberately left manual (see `docs/deprecated-template-review.md`): flag templates (`PRC`, `CHN-*`, `QING-*`), footnotes (`Note`/`Ref` family), `Cite GB`/`Cite Q`/`Cite doi`/`PBB`/`NYPL-image`, licence tags, `Expand`/`Infosplit`/`Float begin`/`Dablink`/`User sandbox`, non-navbox `!w`/`-w` uses, the `BS*`/`Start rail box` railway family, and the remaining infobox/module wrappers (`Infobox DRCongo province`, `Infobox star`, `Markup`, `Clickable button`, `Respell`, `Ping2`, `Demography 4col`, `Vertical images list`, `DisestcatCountry`, `DisestcatUSstate`)
- [ ] **Lint categories left to humans** — `missing-end-tag`, `stripped-tag`, `misnested-tag` (usually template-caused), `deletable-table-tag`, image options other than duplicate sizes, `duplicate-id`, `wikilink-in-extlink`, `multi-colon-escape`, `pwrap-bug-workaround`, `tidy-whitespace-bug`, and `cellspacing`/`cellpadding`
- [ ] **Category policy pieces left to humans** — whether a page belongs in a category, abstract-category inheritance, navigation-box consistency, and moving category links to the bottom of an article
- [ ] **Category namespace read permission** — this token cannot read `Category:` page content on the target wiki (API `accessdenied`), so `{{catnav}}` insertion can only run where the bot account has that right
- [ ] **Use the public helpers** — `calculate_length.py`, `signature_parser.py`, `sections_to_page.py` and `marks.py` all have unit tests but no in-repo callers yet
- [ ] **Use the messaging helpers** — `Wiki.mass_message()`, `new_section()` and `get_sections()` are implemented but not called by the processing loop
