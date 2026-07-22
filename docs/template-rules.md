# Template Rules Reference

Template rules are TOML files in the `template_rules/` directory. They define automated transformations applied to wiki templates during processing.

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
| `introduction` | `str` | Human-readable description, shown during confirmation |
| `apply_websites` | `list[str]` | Domains this rule applies to. Empty = all wikis |
| `names` | `list[str]` | Template names to match. First is the canonical/preferred name. Case-insensitive first letter |

## `[template_level]`

Actions applied to the template as a whole:

| Field | Type | Description |
|-------|------|-------------|
| `rename` | `bool` | If true, rename the template to `names[0]` |
| `delete` | `bool` | If true, remove the template entirely |
| `replace` | `str` | Replace the entire template with this string. Use `{{{param_name}}}` for parameter values, `{{{1}}}` for anonymous params. Supports defaults: `{{{foo\|default}}}` |

## `[[params]]`

Per-parameter rules. You can have multiple `[[params]]` sections. Each matches parameters by name (regex supported):

| Field | Type | Description |
|-------|------|-------------|
| `names` | `list[str]` | Parameter names to match (regex patterns allowed). Use `"1"` for anonymous param #1 |
| `new_name` | `str` | New name if `rename` is true |
| `rename` | `bool` | If true, rename matched parameters to `new_name` |
| `delete` | `bool` | If true, remove matched parameters |

## `[[params.match]]`

Conditional value transformations within a parameter:

| Field | Type | Description |
|-------|------|-------------|
| `condition` | `str` | Regex to test the param value against |
| `mode` | `bool` | `true` = apply when condition matches; `false` = apply when it doesn't |
| `match` | `str` | Regex capture pattern for substitution |
| `replacement` | `str` | Replacement string (supports `\1`, `\2` backreferences) |

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

During startup, `TemplateFormatter.get_ruleset()` scans all `*.toml` files in `template_rules/`. For each rule, it:

1. Checks `apply_websites` against the configured `api_endpoint` domain (via `check_same_website`). Non-matching rules are skipped.
2. Registers the rule keyed by the capitalized first `names` entry.
3. Later, during page processing, `format_template()` matches each template in the page against registered rules and applies transformations.
