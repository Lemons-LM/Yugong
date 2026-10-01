"""The ``@job`` / ``@intro`` decorator registries and the ``Marks`` constants."""

from __future__ import annotations

import unittest

from src.Yugong.core.wikitext import Wikitext
from src.Yugong.utilities.mark_job_intro import (
    INTROS,
    JOBS,
    intro,
    job,
    job_needs_wiki,
)
from src.Yugong.utilities.marks import Marks


class JobDecoratorTest(unittest.TestCase):
    def setUp(self) -> None:
        self._jobs = list(JOBS)
        self._intros = list(INTROS)
        JOBS.clear()
        INTROS.clear()

    def tearDown(self) -> None:
        JOBS[:] = self._jobs
        INTROS[:] = self._intros

    def test_bare_decorator_registers_the_function(self) -> None:
        @job
        def my_job(wikitext: Wikitext) -> None:
            return None

        self.assertEqual(JOBS, [my_job])
        self.assertFalse(job_needs_wiki(my_job))

    def test_decorator_can_declare_that_it_needs_a_wiki(self) -> None:
        @job(needs_wiki=True)
        def my_wiki_job(wikitext: Wikitext) -> None:
            return None

        self.assertEqual(JOBS, [my_wiki_job])
        self.assertTrue(job_needs_wiki(my_wiki_job))

    def test_jobs_keep_their_registration_order(self) -> None:
        @job
        def first(wikitext: Wikitext) -> None:
            return None

        @job
        def second(wikitext: Wikitext) -> None:
            return None

        self.assertEqual([func.__name__ for func in JOBS], ["first", "second"])

    def test_intro_registers_the_description(self) -> None:
        @intro
        def my_intro() -> str:
            return "does something"

        self.assertEqual(INTROS, [my_intro])
        self.assertEqual(INTROS[0](), "does something")

    def test_undecorated_functions_never_claim_to_need_a_wiki(self) -> None:
        def plain(wikitext: Wikitext) -> None:
            return None

        self.assertFalse(job_needs_wiki(plain))


class MarksTest(unittest.TestCase):
    def test_common_punctuation(self) -> None:
        self.assertEqual(Marks.lbrace, "{")
        self.assertEqual(Marks.rbrace, "}")
        self.assertEqual(Marks.lbracket + Marks.rbracket, "[]")
        self.assertEqual(Marks.langle + Marks.rangle, "<>")
        self.assertEqual(Marks.lparen + Marks.rparen, "()")
        self.assertEqual(Marks.pipe, "|")


if __name__ == "__main__":
    unittest.main()
