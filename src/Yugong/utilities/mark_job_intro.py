"""The ``@job`` / ``@intro`` decorator registries that make extensions pluggable.

Importing an extension module runs its decorators, which append to :data:`JOBS`
and :data:`INTROS`.  Nothing here imports the rest of YuGong, so extension
modules stay cheap to load.

Extensions that talk to the wiki should declare it::

    @job(needs_wiki=True)
    def my_job(wikitext: Wikitext) -> None: ...

Offline dev mode then skips them instead of failing on a missing OAuth token.

A job that normalises the page *before* template matching (for example, the
invisible-character cleanup) can declare ``pre_template=True``.  It then runs
before the ``template_rules`` step, so cleaning a template name cannot leave
the rule engine looking at the previous, dirty name.
"""

from __future__ import annotations

from typing import Any, Callable, TypeVar, overload

F = TypeVar("F", bound=Callable[..., Any])

#: Functions decorated with ``@job``, in registration (import) order.
JOBS: list[Callable[..., Any]] = []

#: Functions decorated with ``@intro``.
INTROS: list[Callable[[], str]] = []

#: Attribute used to mark a job as requiring a wiki connection.
NEEDS_WIKI_ATTR: str = "needs_wiki"

#: Attribute used to mark a job that must run before the template-rule step.
PRE_TEMPLATE_ATTR: str = "pre_template"


@overload
def job(func: F) -> F: ...


@overload
def job(*, needs_wiki: bool = ..., pre_template: bool = ...) -> Callable[[F], F]: ...


def job(
    func: F | None = None,
    *,
    needs_wiki: bool = False,
    pre_template: bool = False,
) -> F | Callable[[F], F]:
    """Register a processing step ``(wikitext: Wikitext) -> None``.

    Usable both bare (``@job``) and with options (``@job(needs_wiki=True)``).
    ``pre_template=True`` puts the job before the template-rule step.
    """

    def register(target: F) -> F:
        setattr(target, NEEDS_WIKI_ATTR, needs_wiki)
        setattr(target, PRE_TEMPLATE_ATTR, pre_template)
        JOBS.append(target)
        return target

    if func is None:
        return register
    return register(func)


def intro(func: Callable[[], str]) -> Callable[[], str]:
    """Register a one-line description shown during confirmation."""
    INTROS.append(func)
    return func


def job_needs_wiki(func: Callable[..., Any]) -> bool:
    """Return whether *func* was registered with ``needs_wiki=True``."""
    return bool(getattr(func, NEEDS_WIKI_ATTR, False))


def job_runs_before_template_rules(func: Callable[..., Any]) -> bool:
    """Return whether *func* was registered with ``pre_template=True``."""
    return bool(getattr(func, PRE_TEMPLATE_ATTR, False))
