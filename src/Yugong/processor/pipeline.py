"""The "run every step against one page" machinery, shared by both entry points.

A *step* is a named callable that mutates a :class:`~src.Yugong.core.wikitext.Wikitext`
in place.  Jobs registered with ``@job(pre_template=True)`` run first so that
they can normalise the page before template matching (for example, removing
invisible characters from template names).  The template-rule formatter runs
next, followed by the remaining ``@job`` functions in import order.
"""

from __future__ import annotations

from functools import partial
from typing import Any, Callable, Iterable

from src.Yugong.core.logger import logger
from src.Yugong.core.template_formatter import formatter
from src.Yugong.core.wikitext import Wikitext
from src.Yugong.utilities.mark_job_intro import (
    JOBS,
    job_needs_wiki,
    job_runs_before_template_rules,
)

#: A named, zero-argument callable that mutates the page it was built for.
Step = tuple[str, Callable[[], None]]

#: Name reported for the template-rule step.
TEMPLATE_RULE_STEP: str = "template_rules"


def build_steps(
    wikitext: Wikitext,
    *,
    apply_rules: bool = True,
    include_wiki_jobs: bool = True,
    jobs: Iterable[Callable[..., Any]] | None = None,
) -> tuple[list[Step], list[str]]:
    """Build the step list for one page.

    Args:
        wikitext: The page the steps will be bound to.
        apply_rules: Include the ``template_rules/*.toml`` formatter step.
        include_wiki_jobs: Include jobs registered with ``needs_wiki=True``.
        jobs: Override the global registry (used by tests).

    Returns:
        ``(steps, skipped_job_names)``.
    """
    selected = list(JOBS if jobs is None else jobs)

    skipped = [
        job.__name__
        for job in selected
        if job_needs_wiki(job) and not include_wiki_jobs
    ]

    included = [
        job for job in selected if include_wiki_jobs or not job_needs_wiki(job)
    ]
    pre_template = [job for job in included if job_runs_before_template_rules(job)]
    remaining = [job for job in included if not job_runs_before_template_rules(job)]

    steps: list[Step] = [
        (job.__name__, partial(job, wikitext)) for job in pre_template
    ]
    if apply_rules:
        steps.append((TEMPLATE_RULE_STEP, partial(formatter.format_template, wikitext)))

    steps.extend((job.__name__, partial(job, wikitext)) for job in remaining)
    return steps, skipped


def apply_steps(wikitext: Wikitext, page_name: str, steps: Iterable[Step]) -> list[str]:
    """Run every step in order, returning the names that changed the page."""
    applied: list[str] = []
    for name, step in steps:
        before = str(wikitext.wikitext)
        step()
        after = str(wikitext.wikitext)
        wikitext.processed_content = after
        if before != after:
            applied.append(name)
            logger.info(f"[{page_name}] applied: {name}")
    return applied
