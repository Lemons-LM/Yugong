# Template Rules Reference

Template rules are TOML files in the `template_rules/` directory. They define automated transformations applied to wiki templates during processing.

Rules are applied by `TemplateFormatter.format_template()`, which is the **first step of every page**, before the `@job` extensions run. Without rules there is nothing to apply; the loader globs `template_rules/*.toml` only, so `template_rules/example.toml.disabled` is deliberately ignored until you rename it.

## File structure

```toml
# template_rules/my_rule.toml

introduction = "What this rule does"
apply_websites = ["example.com"]   # empty list = applies to all wikis
names = ["PreferredName", "AliasName"]

[template_level]
rename = true     # rename to the preferred name (first in names list)
delete = false    # delete the entire template
replace = ""      # replace with a string (uses {{{param}}} as placeholders)

[[params]]
names = ["old_param_name", "alias_name"]
new_name = "new_param_name"
rename = true
delete = false

[[params.match]]
condition = "regex_to_match_value"
mode = true                # true = apply when matched; false = apply when NOT matched
match = "regex_capture"
replacement = "replace_text"
```

## Top-level fields

| Field | Type | Description |
|-------|------|-------------|
| `introduction` | `str` | Human-readable description, shown during confirmation. Required — a rule without it is rejected |
| `apply_websites` | `list[str]` | Domains this rule applies to. Empty = all wikis |
| `names` | `list[str]` | Template names to match. Required and non-empty. First is the canonical/preferred name. Case-insensitive first letter |

`names` entries are matched against a template's name after capitalizing the first letter (only when it is alphabetic, so `2x` stays `2x`). Every entry in `names` is registered as an alias for the same rule; registering the same key twice — from one file or from two — raises a `Duplicate template rule` error.

## `[template_level]`

Actions applied to the template as a whole. At most **one** of them may be set; setting several is rejected as a conflicting rule:

| Field | Type | Description |
|-------|------|-------------|
| `rename` | `bool` | If true, rename the template to `names[0]` (subject to `overwrite_template_name`) |
| `delete` | `bool` | If true, remove the template entirely |
| `replace` | `str` | Replace the entire template with this string. Use `{{{param_name}}}` for parameter values, `{{{1}}}` for anonymous params. Supports defaults and nesting: `{{{foo\|default}}}`, `{{{foo\|{{{1}}}}}}` |

## `[[params]]`

Per-parameter rules. You can have multiple `[[params]]` sections. Each matches parameters by name with `re.fullmatch`, so the patterns must cover the whole parameter name:

| Field | Type | Description |
|-------|------|-------------|
| `names` | `list[str]` | Parameter names to match (regex patterns allowed). Use `"1"` for anonymous param #1. A block with no `names` is ignored |
| `new_name` | `str` | New name if `rename` is true |
| `rename` | `bool` | If true, rename matched parameters to `new_name` (subject to `overwrite_para_name`) |
| `delete` | `bool` | If true, remove matched parameters |
| `match` | `list[table]` | Optional `[[params.match]]` blocks, see below |

## `[[params.match]]`

Conditional value transformations within a parameter:

| Field | Type | Description |
|-------|------|-------------|
| `condition` | `str` | Regex searched in the stripped param value. Required — a missing/empty condition is rejected at load time so a rule cannot silently do nothing |
| `mode` | `bool` | `true` (default) = apply when the condition matches; `false` = apply when it doesn't |
| `match` | `str` | Regex used to rewrite the value |
| `replacement` | `str` | Replacement string (supports `\1`, `\2` backreferences) |

When `match` and `replacement` are both set, the rule tries `re.fullmatch` first and expands the replacement if the pattern covers the whole value; otherwise it runs `re.sub`. This is why the documented `match = ".*"` produces `dead` and not `deaddead`. If only `replacement` is set (no `match`), the whole parameter value is replaced.

## Example

Rename a template and clean up its parameters:

```toml
introduction = "Normalize citation templates"
names = ["Cite", "Citation", "Cite web"]

[template_level]
rename = true

[[params]]
names = ["accessdate", "access-date", "access_date"]
new_name = "access-date"
rename = true

[[params]]
names = ["deadurl", "dead-url"]
new_name = "url-status"
rename = true

[[params.match]]
condition = "yes|true|dead"
match = ".*"
replacement = "dead"

[[params.match]]
condition = "no|false|live"
match = ".*"
replacement = "live"
```

## How rules are loaded

During startup, `TemplateFormatter.get_ruleset()` (re)loads every `*.toml` file in `template_rules/`, sorted by filename. For each rule, it:

1. Checks `apply_websites` against the configured `api_endpoint` domain (via `check_same_website`, which ignores a `www.` prefix and any port). Non-matching rules are logged and skipped.
2. Validates the rule: `names` must be non-empty, `introduction` must be set, `[template_level]` must not combine conflicting actions, every regex (parameter names, `condition`, `match`) must compile, and `rename = true` requires `new_name`. A malformed rule aborts the run with a descriptive error instead of being ignored.
3. Registers the rule under every capitalized `names` entry, rejecting duplicates.

Later, during page processing, `format_template()` runs as the first step: for every template on the page it looks up `_safe_capitalize(name)` in the registry and applies the matching rule (template-level action first, then the `params` blocks).

## Shipped rules

Deprecated templates are reviewed one at a time; the full rationale and the
manual list are in [`docs/deprecated-template-review.md`](deprecated-template-review.md).

| File | What it does |
|------|--------------|
| `internal_link_helper.toml` | `Internal link helper`, its 92 language subpages, 90 `Link-*` aliases and `Ilh` → `[[{{{1\|}}}]]` (Qiuwen has no foreign editions) |
| `translink.toml` | `Translink`/`Tsl` → internal link to param 3, else param 2; display param 4 |
| `interlanguage_link_multi.toml` | `Interlanguage link multi` → rename to `多語言連結` |
| `deprecated_city.toml` | `{{城市}}` → exact wiki-defined `{{Infobox settlement}}` wrapper |
| `deprecated_country_infobox.toml` | `{{國家基礎資訊}}` → exact wiki-defined `{{Infobox country}}` wrapper |
| `double_image.toml` | `Double image` → reviewed `Multiple image` positional mapping |
| `short_description.toml` | Delete `Short description` (not enabled on Qiuwen) |
| `font_color.toml` | `Font color` → `Color` (foreground + text) |
| `china_*`, `roc_*`, `chn_1928.toml` | Direct links for the link-only country templates |

The `.w`/`!w`/`-w` series is handled by `extensions/nowrap_fixes.py`, not a
TOML rule: navbox `list`/`group`/`above`/`below` values are converted to
unordered lists (the list starts on a new line after `=`), while already
nowrap-wrapped values and non-navbox uses are left alone.

All shipped rules use `apply_websites = ["qiuwenbaike.cn"]`. The country
replacement is about 3.5k changed characters after expansion, so a run that
applies it needs `max_acceptable_diff_size` above the default 1000.

Other deprecated templates — flag templates, footnotes, `Cite GB`/`Cite Q`,
licence tags, `Expand`, `Dablink`, the `BS*` railway family, and the
infobox/module wrappers — are deliberately left manual because a blind rename
would lose or misinterpret parameters.
