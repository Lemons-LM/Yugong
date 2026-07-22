"""Develop mode: run extensions against a local wikitext file without connecting to a wiki."""

import importlib
from pathlib import Path

from src.Yugong.core.wikitext import Wikitext
from src.Yugong.utilities.mark_job_intro import JOBS
from src.Yugong.utilities.path_helper import PROJECT_ROOT


def run_dev_mode(input_path: str, output_path: str) -> None:
    """
    Read wikitext from input_path, run all registered @job extensions against it,
    and write the processed result to output_path.

    No wiki connection is needed.
    """
    # Load extensions (same as confirm_settings does)
    steps_path = PROJECT_ROOT / 'src' / 'Yugong' / 'extensions'
    for f in steps_path.glob("*.py"):
        if f.name != "__init__.py":
            module_name = f"src.Yugong.extensions.{f.stem}"
            importlib.import_module(module_name)

    if not JOBS:
        print(f"Warning: No extensions loaded from {steps_path}")

    # Read input
    input_file = Path(input_path)
    if not input_file.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    content = input_file.read_text(encoding='utf-8')
    print(f"Read {len(content)} chars from {input_path}")

    # Minimal metadata for local testing
    metadata = {
        'title': input_file.stem,
        'page_id': '0',
        'pageid': '0',
        'revid': '0',
        'namespace': '0',
        'permission': '',
    }

    wikitext = Wikitext(metadata)
    wikitext.parse(content)

    # Run all jobs
    step = 0
    for job in JOBS:
        old_content = str(wikitext.wikitext)
        job(wikitext)
        new_content = str(wikitext.wikitext)
        wikitext.processed_content = new_content

        if old_content != new_content:
            step += 1
            print(f"  Step {step}: {job.__name__} — changed ({len(new_content)} chars)")

    if step == 0:
        print("No extensions made any changes.")
    else:
        print(f"Total: {step} extension(s) applied changes.")

    # Write output
    output_file = Path(output_path)
    output_file.write_text(str(wikitext.wikitext), encoding='utf-8')
    print(f"Output written to {output_path} ({len(str(wikitext.wikitext))} chars)")
