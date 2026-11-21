# Deprecated-template review

The target wiki marks templates with `{{Deprecated template|old|new}}`.  These
templates are reviewed **one by one**; a template is only changed when its
replacement is known to be safe.  The rules live in `template_rules/*.toml` —
there is no automatic "rename every deprecated template" pass.

The wiki currently lists 208 pages (including `/doc` pages) using the notice,
covering 185 parent templates.

## Automated rules

| Rule file | Old template(s) | What it does | Why safe |
|-----------|-----------------|--------------|----------|
| `internal_link_helper.toml` | `Internal link helper`, `Internal link helper/<lang>` (92), `Link-<lang>` (90), `Ilh` | `[[{{{1|}}}]]` | The wiki documentation says the whole family is unused on Qiuwen ("请移除并直接替换为内部链接"); the first parameter is the local title. |
| `translink.toml` | `Translink`, `Tsl` | Internal link to param 3 (Chinese title), else param 2 (foreign title); display param 4 if present | Params documented in `Template:Translink/doc`; parser functions handle the empty-param fallback. |
| `interlanguage_link_multi.toml` | `Interlanguage link multi` | Rename to `多語言連結` | The new template is the documented replacement and is literally `[[{{{1}}}]]`; extra params are ignored harmlessly. |
| `deprecated_city.toml` | `城市` | Exact expansion of the wiki wrapper into `{{Infobox settlement|...}}` | `Template:城市` is a pure parameter mapping; generated from the template body. |
| `deprecated_country_infobox.toml` | `國家基礎資訊` | Exact expansion of the wiki wrapper into `{{Infobox country|...}}` | Pure wrapper; large expansion (~3.5k chars), so raise the diff limit for runs that use it. |
| `double_image.toml` | `Double image` | Reviewed `Multiple image` mapping for positional params 1–9 and `valign` | The old template is a wrapper; parser functions are left for MediaWiki to evaluate. |
| `short_description.toml` | `Short description` | Delete the template | `Template:Short description/doc` says it was imported from English Wikipedia but is not enabled on Qiuwen, and tells editors to delete it. |
| `font_color.toml` | `Font color` | `{{color|fg|text}}`, including named `fg`/`text` | The doc says to use `{{color}}`; background and link coloring are not supported by the new template. |
| `extensions/nowrap_fixes.py` | `.w`, `!w`, `-w` | Navbox `list`/`group`/`above`/`below` values become unordered lists (newline after `=`); already-wrapped values and non-navbox uses are left alone | The `.w` doc requires `nowrap begin/end` pairing; navboxes carry `hlist`, and QW:TODO recommends a list. A flat `{{·}}` replacement would be wrong outside the dot case. |
| `china_mainland_link.toml` | `中国大陆` | `[[中国大陆]]` | The template is a direct link wrapper. |
| `china_interior_link.toml` | `中国内地` | `[[中国内地]]` | The template is a direct link wrapper. |
| `china_film_origin.toml` | `中國電影產地` | `[[中国]]` | The template expands to `[[中国]]` for the film infobox. |
| `roc_1940.toml` | `ROC-1940` | `[[汪伪政权]]` | The template is a direct link wrapper. |
| `roc_1938.toml` | `ROC-1938` | `伪“[[中華民國維新政府]]”` | The template expands to this text + link. |
| `chn_1928.toml` | `CHN-1928` | `[[中华民国|中国]]` | The template is a direct link wrapper. |

The `internal_link_helper.toml` rule contains 184 names: the base template, 92
language subpages, 90 `Link-*` redirects, and `Ilh`.

## Reviewed as manual — no rule on purpose

Each of these needs either a parameter-aware mapping that the rule engine
cannot express safely, a module transformation, or an editorial decision
(e.g. whether to keep a flag).

| Family / template | Reason |
|-------------------|--------|
| `PRC`, `CHN-1862`, `CHN-1889`, `CHN-QING`, `QING-1862`, `QING-1889`, `QING-S` | Flag-bearing templates. The deprecation note says to use links directly, but dropping the flag is an editorial choice; not handled silently. |
| `CHN-all` | Documentation/index template listing the flag templates; not an article-content template. |
| `Note`, `Ref`, `Note label`, `Ref label` | Paired footnote templates; the documented replacement (`refn`/`efn`) needs a note-list migration, not a rename. |
| `Cite GB` | Documented replacement `Cite standard` has a different parameter set; a rename would silently drop `year`, `publisher_*`, `pages`, etc. |
| `Cite Q`, `Cite doi`, `PBB`, `NYPL-image` | Different citation/licence parameter models or Wikidata/module-driven replacements. |
| `Cc-sa-1.0`, `PD-in`, `MONCopyright`, `PolishSenateCopyright`, `BnFMandragorePic` | Licence tags; replacement depends on the current licence decision. |
| `Expand` | The doc provides several context-specific replacements (`Expand language`, `stub`, `Empty section`, `Expand section`, `Lead too short`, `Missing information`, `Explain`, `Expand list`); the bot cannot choose the editor's intent. |
| `Infosplit`, `Float begin`, `Dablink`, `!w`, `-w`, `User sandbox` | The recommended replacement depends on context or is a different template family. |
| `BS`, `BS2`–`BS38`, `BSrow`, `Start rail box`, `上海地铁RDT`, `武汉地铁车站列表` | Railway diagram/list templates; the documented replacement is `Module:Routemap` or a subpage, not a template rename. |
| `Infobox DRCongo province`, `Infobox star`, `Markup`, `Clickable button`, `Respell`, `Ping2`, `Demography 4col`, `Vertical images list`, `DisestcatCountry`, `DisestcatUSstate` | Different parameter models, module-backed replacements, or custom markup; reviewed and left for a parameter-aware migration. |
| `Historical template`, `Ja Pref Route Sign/get Pref Type`, `Interlanguage link`/`Ill` | Generic/historical or not marked deprecated; left unchanged. |

Templates that are deprecated on the wiki but not in this table or in an
automated rule remain unchanged.  Add a reviewed `template_rules/*.toml` entry
(or extend an existing family rule) before automating one.
