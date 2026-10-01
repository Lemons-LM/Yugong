# Dev Mode

Dev mode runs the whole processing pipeline against a local wikitext file — no wiki connection, no OAuth token and no settings validation. It is the fast loop for developing and regression-testing extensions and template rules.

It is *not* a dependency-free mode: `load_extensions()` imports every extension (including the ones that use pywikibot) and the template rules need `toml`, so install the normal requirements first.

## Usage

```bash
python main.py --dev input.wikitext output.wikitext
```

1. Loads all extensions from `src/Yugong/extensions/` and prints their names
2. Loads `template_rules/*.toml` (unless `--no-template-rules` is given)
3. Reads wikitext from `input.wikitext`
4. Builds the step list — template rules first, then every `@job` function — and runs it against the parsed wikitext
5. Writes the processed result to `output.wikitext`

Two flags change the behaviour:

| Flag | Effect |
|------|--------|
| `--with-wiki-jobs` | Also run extensions marked `@job(needs_wiki=True)` |
| `--no-template-rules` | Do not apply `template_rules/*.toml` |

By default, jobs marked `needs_wiki=True` are skipped and their names are printed under `Skipped (need a wiki connection):`. Passing `--with-wiki-jobs` runs them, which means a real wiki connection (and therefore an OAuth token) is required.

## Example

Create `test_input.wikitext`:
```
A<ref name="orphan" />B
```

Run dev mode:
```bash
python main.py --dev test_input.wikitext test_output.wikitext
```

Console output:
```
Loaded extensions: category_handler, example, fix_cite_template, rm_undefined_refs, rm_void_template
Read 23 chars from test_input.wikitext
Skipped (need a wiki connection): category_handler_job, rm_void_template_job
Applied: rm_undefined_refs_job
Output written to test_output.wikitext (2 chars)
```

`test_output.wikitext` now contains `AB`. When no step changed anything the program prints `No extensions made any changes.` instead, and the output file still receives the (unchanged) text.

## What it doesn't do

- No wiki connection by default (no API calls, no page listing, no saving) — unless `--with-wiki-jobs` is passed
- No settings validation (a `settings.toml` must still exist for the imports to load, but it does not have to be configured for a wiki)
- No tag-policy check and no `max_acceptable_diff_size` check — those live in the production per-page loop, not in the shared pipeline
- No user prompts
- No manifest/todo-list handling; the input file is the whole job

## Use cases

- **Developing a new extension** — iterate quickly without risking real wiki edits
- **Regression testing** — keep a set of input/output pairs to verify extensions don't break
- **CI/CD** — run it as a subprocess in automated tests; the project's own `tests/test_entrypoints.py` does exactly that

## Writing test files

Keep input/output wikitext pairs in a directory outside `tests/` (that directory is for the `unittest` suite):

```
samples/
  fix_cite/
    input.wikitext
    expected_output.wikitext
```

Then verify:
```bash
python main.py --dev samples/fix_cite/input.wikitext /tmp/actual.wikitext
diff samples/fix_cite/expected_output.wikitext /tmp/actual.wikitext
```

For behaviour that needs to be locked down permanently, add a case to `tests/test_extensions.py` instead — those tests run a single job directly through `tests/support.run_job()` and are part of `python -m unittest discover`.
