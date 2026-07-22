# Extension Development Guide

Extensions are the core of YuGong — they define the transformations applied to wiki pages.

## Quick start

Copy `src/Yugong/extensions/example.py` and rename it (e.g. `fix_infobox.py`):

```python
from src.Yugong.core.wikitext import Wikitext
from src.Yugong.utilities.mark_job_intro import job, intro
import mwparserfromhell as mph


@job
def fix_infobox_job(wikitext: Wikitext) -> None:
    """Replace `old_param` with `new_param` in infobox templates."""
    for template in wikitext.wikitext.filter_templates():
        if "infobox" in str(template.name).lower():
            for param in template.params:
                if param.name.strip() == "old_param":
                    param.name = "new_param"


@intro
def fix_infobox_intro() -> str:
    return "Fix infobox: rename old_param to new_param"
```

## The `@job` decorator

```python
@job
def my_job(wikitext: Wikitext) -> None:
```

- Receives a `Wikitext` object wrapping the page's parsed wikitext.
- Mutate `wikitext.wikitext` (an `mwparserfromhell.Wikicode` object) in place.
- The return value is ignored.

**`Wikitext` attributes you'll use:**

| Attribute | Type | Description |
|-----------|------|-------------|
| `wikitext.title` | `str` | Page title |
| `wikitext.wikitext` | `mph.Wikicode` | The parsed wikitext — mutate this |
| `wikitext.processed_content` | `str` | Plain string version (auto-synced) |
| `wikitext.revid` | `int` | Latest revision ID |
| `wikitext.namespace` | `int` | Namespace number |

**`mwparserfromhell` quick reference:**

```python
import mwparserfromhell as mph

# Filter all templates
for template in wikitext.wikitext.filter_templates():
    name = str(template.name)        # template name
    for param in template.params:
        pname = str(param.name)      # parameter name
        pvalue = str(param.value)    # parameter value

# Filter all wikilinks
for link in wikitext.wikitext.filter_wikilinks():
    title = str(link.title)
    if link.text:
        display = str(link.text)

# Filter all tags
for tag in wikitext.wikitext.filter_tags():
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

## Testing locally

Use dev mode to test your extension without connecting to a wiki:

```bash
python main.py --dev input.wikitext output.wikitext
```

See [dev-mode.md](dev-mode.md) for details.

## Rules

- **Validate your inputs.** If you expect a template to have certain parameters, check they exist before accessing them.
- **Fail loudly.** Raise exceptions with clear messages — don't silently skip errors. If an extension is broken, the whole program refuses to run.
- **Use type annotations.** All functions must have PEP 484 type hints.
- **One extension per file.** Each `.py` file in the extensions directory should define one logical transformation.
