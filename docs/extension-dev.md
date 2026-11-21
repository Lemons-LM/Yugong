# Extension Development Guide

Extensions are the core of YuGong — they define the transformations applied to wiki pages.

## Quick start

Copy `src/Yugong/extensions/example.py` and rename it (e.g. `fix_infobox.py`):

```python
from src.Yugong.core.wikitext import Wikitext
from src.Yugong.utilities.mark_job_intro import job, intro


@job
def fix_infobox_job(wikitext: Wikitext) -> None:
    """Replace `old_param` with `new_param` in infobox templates."""
    for template in wikitext.templates():
        if "infobox" in str(template.name).lower():
            for param in template.params:
                if str(param.name).strip() == "old_param":
                    param.name = "new_param"


@intro
def fix_infobox_intro() -> str:
    return "Fix infobox: rename old_param to new_param"
```

The extension is picked up automatically as soon as the file exists in `src/Yugong/extensions/`. Test it offline with `python main.py --dev input.wikitext output.wikitext`.

## The `@job` decorator

```python
@job
def my_job(wikitext: Wikitext) -> None:
```

- Receives a `Wikitext` object wrapping the page's parsed wikitext.
- Mutate `wikitext.wikitext` (an `mwparserfromhell.Wikicode` object) in place.
- The return value is ignored.

If your job talks to the wiki (API calls, page lookups, category listings), declare it so offline dev mode can skip it instead of failing on a missing OAuth token:

```python
@job(needs_wiki=True)
def my_wiki_job(wikitext: Wikitext) -> None:
    ...
```

`job_needs_wiki(func)` reads that marker; `build_steps()` in `processor/pipeline.py` uses it, and dev mode prints the names it skipped.

**`Wikitext` attributes you'll use:**

| Attribute | Type | Description |
|-----------|------|-------------|
| `wikitext.title` | `str` | Page title |
| `wikitext.wikitext` | `mph.wikicode.Wikicode` | The parsed wikitext — mutate this; raises if `parse()` has not run |
| `wikitext.text` | `str` | The current wikitext as a plain string |
| `wikitext.original_content` | `str` | The page text exactly as it was read from the wiki |
| `wikitext.processed_content` | `str \| None` | Plain-string copy, updated after every step |
| `wikitext.page_id` | `int \| None` | Page id |
| `wikitext.revid` | `int \| None` | Latest revision id |
| `wikitext.namespace` | `int \| None` | Namespace number |
| `wikitext.permission` | `str` | Permission metadata (empty by default) |

`Wikitext` also exposes `templates()`, `wikilinks()` and `tags()`, which return snapshots (plain lists) that are safe to iterate while mutating the page. Prefer them over `wikitext.wikitext.filter_templates()` etc. when you are going to remove or replace nodes.

**`mwparserfromhell` quick reference:**

```python
import mwparserfromhell as mph

# Filter all templates
for template in wikitext.templates():
    name = str(template.name)        # template name
    for param in template.params:
        pname = str(param.name)      # parameter name
        pvalue = str(param.value)    # parameter value

# Filter all wikilinks
for link in wikitext.wikilinks():
    title = str(link.title)
    if link.text:
        display = str(link.text)

# Filter all tags
for tag in wikitext.tags():
    if str(tag.tag) == "ref":
        ...

# Replace nodes
code.replace(old_node, new_node)
code.remove(node)
```

See the [mwparserfromhell docs](https://mwparserfromhell.readthedocs.io/) for full API details.

## The `@intro` decorator

```python
@intro
def my_job_intro() -> str:
    return "Short description shown during confirmation"
```

- Must take no arguments and return a `str`.
- Shown to the user when they confirm which extensions will run.
- Keep it to one line — it's displayed in a list.

## Loading and ordering

Extensions are found and imported by `src/Yugong/utilities/extensions.py`:

- `extension_modules()` lists `src.Yugong.extensions.<stem>` for every `*.py` file in `src/Yugong/extensions/` except `__init__.py`, **sorted by filename**.
- `load_extensions()` imports them in that order; the `@job`/`@intro` decorators register functions as a side effect.

Both the production entry point and dev mode call `load_extensions()`, so the order is always sorted filename order. A file that fails to import aborts the whole run — broken extensions are never skipped silently.

The shipped extensions double as examples:

| File | Wiki needed | What it does |
|------|-------------|--------------|
| `example.py` | No | Deliberately a no-op; copy this to start |
| `fix_cite_template.py` | No | Rejoins parameter fragments split by an unescaped pipe with `{{!}}` |
| `rm_undefined_refs.py` | No | Removes self-closing named refs with no definition |
| `rm_void_template.py` | Yes | Removes templates redirecting to `Template:Void` (preloaded alias set + redirect chains) |
| `category_handler.py` | Yes | Converts/redirects category links (bot_db cached, NoteTA/CGroup + OpenCC) |
| `category_policy.py` | No | QW:CAT prefix / duplicate link / sort key / `catnav` rules |
| `cangjie.py` | Yes | NoteTA/CGroup + OpenCC visible-text conversion (`enable_cangjie`) |
| `lint_fixes.py` | No | Obsolete tags/attributes, self-closing tags, headings, image sizes, sort keys |
| `nowrap_fixes.py` | No | Navbox `.w`/`!w`/`-w` rows → unordered lists; other uses reported |
| `isbn_normalise.py` | No | Hyphenate ISBN-10/13, clean up BookSources links, optional ISBN-13 conversion / ISBNT merge (`enable_isbn_normalise`, `isbn_template_style`) |
| `rm_invisible_chars.py` | No | Remove zero-width/format/control characters, skipping `nowiki`/code/math and comments (`enable_invisible_chars_fix`) |

`isbn_normalise` reads the bundled `src/Yugong/resources/RangeMessage.xml` (override with `isbn_range_message_path`). Its `isbn_template_style` setting exists because the two wikis interpret `{{ISBN}}` differently: Qiuwen uses parameters 1–9 as a list of ISBNs, while Moegirl uses parameter 2 as display text. See [isbn-normalise.md](isbn-normalise.md).

## Testing locally

Use dev mode to test your extension without connecting to a wiki:

```bash
python main.py --dev input.wikitext output.wikitext

# Also run extensions marked needs_wiki=True (needs a real connection):
python main.py --dev input.wikitext output.wikitext --with-wiki-jobs

# Skip template_rules/*.toml and run extensions only:
python main.py --dev input.wikitext output.wikitext --no-template-rules
```

See [dev-mode.md](dev-mode.md) for details.

## Rules

- **Validate your inputs.** If you expect a template to have certain parameters, check they exist before accessing them.
- **Fail loudly.** Raise exceptions with clear messages — don't silently skip errors. If an extension is broken, the whole program refuses to run.
- **Use type annotations.** All functions must have PEP 484 type hints.
- **One extension per file.** Each `.py` file in the extensions directory should define one logical transformation.
- **Declare wiki access.** Mark jobs that talk to the wiki with `@job(needs_wiki=True)` so offline runs stay useful.
