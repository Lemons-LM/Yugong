"""Offline dev mode: run the whole pipeline against a local wikitext file.

No wiki connection, no OAuth token and no ``settings.toml`` validation are
needed, which makes this the fast loop for developing extensions.  Extensions
registered as ``@job(needs_wiki=True)`` are skipped unless the caller opts in.
"""

from __future__ import annotations

from pathlib import Path

from src.Yugong.core.logger import configure_logging
from src.Yugong.core.template_formatter import formatter
from src.Yugong.core.wikitext import Wikitext
from src.Yugong.processor.pipeline import apply_steps, build_steps
from src.Yugong.utilities.extensions import load_extensions


def run_dev_mode(
    input_path: str,
    output_path: str,
    *,
    include_wiki_jobs: bool = False,
    apply_rules: bool = True,
) -> None:
    """Read *input_path*, run every step against it, write the result to *output_path*.

    Args:
        input_path: File holding the wikitext to process.
        output_path: File the processed wikitext is written to.
        include_wiki_jobs: Also run extensions marked ``needs_wiki=True``.
        apply_rules: Apply ``template_rules/*.toml`` before the extensions.
    """
    configure_logging()

    loaded = load_extensions()
    print(f"Loaded extensions: {', '.join(loaded) if loaded else '(none)'}")

    if apply_rules:
        formatter.get_ruleset()
    else:
        print("Template rules: skipped (--no-template-rules)")

    input_file = Path(input_path)
    if not input_file.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    content = input_file.read_text(encoding="utf-8")
    print(f"Read {len(content)} chars from {input_path}")

    wikitext = Wikitext({
        "title": input_file.stem,
        "pageid": "0",
        "revid": "0",
        "namespace": "0",
        "permission": "",
    })
    wikitext.parse(content)

    steps, skipped = build_steps(
        wikitext,
        apply_rules=apply_rules,
        include_wiki_jobs=include_wiki_jobs,
    )
    if skipped:
        print(f"Skipped (need a wiki connection): {', '.join(skipped)}")

    applied = apply_steps(wikitext, input_file.stem, steps)
    if applied:
        print(f"Applied: {', '.join(applied)}")
    else:
        print("No extensions made any changes.")

    result = str(wikitext.wikitext)
    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(result, encoding="utf-8")
    print(f"Output written to {output_path} ({len(result)} chars)")
