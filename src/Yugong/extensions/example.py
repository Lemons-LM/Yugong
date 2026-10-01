"""Starting point for a new extension.

To write your own:

1. Copy this file into the same directory under a name that describes the
   template it deals with, e.g. ``fix_infobox.py``.  Keep the ``.py`` suffix —
   every ``*.py`` file in ``extensions/`` is imported automatically.
2. Rename ``template_example_job`` to ``<your_name>_job`` and implement the
   transformation inside it.
3. Rename ``template_example_intro`` to ``<your_name>_intro`` and return a
   one-line description of what the job changes; it is shown to the user before
   anything is edited.
4. Test offline with ``python main.py --dev input.wikitext output.wikitext``.

A job receives the page as a :class:`~src.Yugong.core.wikitext.Wikitext` and
mutates it in place.  Its return value is ignored.  Use ``@job(needs_wiki=True)``
if the job has to talk to the wiki; offline dev mode then skips it.

A minimal implementation would look like this::

    @job
    def template_example_job(wikitext: Wikitext) -> None:
        for template in wikitext.templates():
            if "infobox" not in str(template.name).lower():
                continue
            for param in template.params:
                if str(param.name).strip() == "old_param":
                    param.name = "new_param"

It is intentionally left as a no-op here: this file is loaded by default, so it
must never modify a page.
"""

from __future__ import annotations

from src.Yugong.core.wikitext import Wikitext
from src.Yugong.utilities.mark_job_intro import intro, job


@job
def template_example_job(wikitext: Wikitext) -> None:
    """Do nothing — this is the copy-me template, not a real transformation."""
    return None


@intro
def template_example_intro() -> str:
    return "Example: does nothing (copy this file to add your own extension)"
