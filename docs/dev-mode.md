# Dev Mode

Dev mode lets you test extensions locally against a wikitext file — no wiki connection, no OAuth token, no `pywikibot` or `toml` dependency needed.

## Usage

```bash
python main.py --dev input.wikitext output.wikitext
```

1. Reads wikitext from `input.wikitext`
2. Loads all extensions from `src/Yugong/extensions/`
3. Runs every `@job` function against the parsed wikitext
4. Writes the processed result to `output.wikitext`

## Example

Create `test_input.wikitext`:
```
{{Infobox
| name = Foo
| old_param = bar
}}
Some article text.
```

Run dev mode:
```bash
python main.py --dev test_input.wikitext test_output.wikitext
```

Console output:
```
Read 52 chars from test_input.wikitext
  Step 1: fix_infobox_job — changed (50 chars)
Total: 1 extension(s) applied changes.
Output written to test_output.wikitext (50 chars)
```

## What it doesn't do

- No wiki connection (no API calls, no page listing, no saving)
- No template rules loading (only extensions)
- No settings validation (no `settings.toml` needed)
- No user prompts

## Use cases

- **Developing a new extension** — iterate quickly without risking real wiki edits
- **Regression testing** — keep a set of input/output pairs to verify extensions don't break
- **CI/CD** — run dev mode in automated tests (just needs Python + `mwparserfromhell`)

## Writing test files

Keep input/output wikitext pairs in a test directory:

```
tests/
  fix_infobox/
    input.wikitext
    expected_output.wikitext
  fix_citations/
    input.wikitext
    expected_output.wikitext
```

Then verify:
```bash
python main.py --dev tests/fix_infobox/input.wikitext /tmp/actual.wikitext
diff tests/fix_infobox/expected_output.wikitext /tmp/actual.wikitext
```
