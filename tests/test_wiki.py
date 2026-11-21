"""The pywikibot wrapper: OAuth handling, throttling and the kill switch."""

from __future__ import annotations

import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from pywikibot import config

from src.Yugong.core import wiki as wiki_module
from src.Yugong.core.settings import settings


class OAuthTokenTest(unittest.TestCase):
    def test_missing_token_is_none(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertIsNone(wiki_module.get_oauth_token())

    def test_documented_variable_name(self) -> None:
        with mock.patch.dict(os.environ, {"MW_OAUTH_TOKEN": "token"}, clear=True):
            self.assertEqual(wiki_module.get_oauth_token(), "token")

    def test_legacy_variable_name_still_works(self) -> None:
        with mock.patch.dict(os.environ, {"MW_BOT_OAUTH_TOKEN": "legacy"}, clear=True):
            self.assertEqual(wiki_module.get_oauth_token(), "legacy")

    def test_documented_name_takes_precedence(self) -> None:
        env = {"MW_OAUTH_TOKEN": "new", "MW_BOT_OAUTH_TOKEN": "old"}
        with mock.patch.dict(os.environ, env, clear=True):
            self.assertEqual(wiki_module.get_oauth_token(), "new")


class WikiConstructionTest(unittest.TestCase):
    def test_construction_never_touches_the_network(self) -> None:
        """Regression: ``Wiki()`` used to fire an API request from __init__."""
        with mock.patch.object(wiki_module.Wiki, "_api_get") as api_get:
            wiki_module.Wiki(bot_name="B", api_endpoint="https://x/api.php")
            api_get.assert_not_called()

    def test_empty_endpoint_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            wiki_module.Wiki(bot_name="B", api_endpoint="")

    def test_empty_bot_name_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            wiki_module.Wiki(bot_name="   ", api_endpoint="https://x/api.php")

    def test_site_requires_an_oauth_token(self) -> None:
        instance = wiki_module.Wiki(bot_name="B", api_endpoint="https://x/api.php")
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ValueError) as ctx:
                _ = instance.site
        self.assertIn("MW_OAUTH_TOKEN", str(ctx.exception))


class PywikibotConfigTest(unittest.TestCase):
    def test_retry_budget_and_timeout_come_from_settings(self) -> None:
        with mock.patch.object(settings, "request_max_tries", 7), \
             mock.patch.object(settings, "request_timeout", 11):
            wiki_module.apply_pywikibot_config()
            self.assertEqual(config.retry_max, 7)
            self.assertEqual(config.socket_timeout, (6.05, 11))

    def test_cosmetic_changes_cannot_rewrite_the_checked_text(self) -> None:
        wiki_module.apply_pywikibot_config()
        self.assertFalse(config.cosmetic_changes)


class WikiUrlTest(unittest.TestCase):
    def test_api_url_is_derived_from_a_directory(self) -> None:
        instance = wiki_module.Wiki(bot_name="B", api_endpoint="https://x.example/")
        self.assertEqual(instance.api_url, "https://x.example/api.php")
        self.assertEqual(instance.base_url, "https://x.example/")

    def test_api_url_accepts_an_api_php_endpoint(self) -> None:
        instance = wiki_module.Wiki(bot_name="B", api_endpoint="https://x.example/api.php")
        self.assertEqual(instance.api_url, "https://x.example/api.php")
        self.assertEqual(instance.base_url, "https://x.example/")

    def test_an_invalid_endpoint_fails_when_used_not_at_import(self) -> None:
        """Importing must never require a valid wiki (dev mode relies on it)."""
        instance = wiki_module.Wiki(bot_name="B", api_endpoint="x.example")
        self.assertEqual(instance.api_url, "")
        with mock.patch.object(settings, "request_max_tries", 1):
            self.assertIsNone(instance._api_get({"action": "query"}))


class ApiGetTest(unittest.TestCase):
    def setUp(self) -> None:
        self.instance = wiki_module.Wiki(bot_name="B", api_endpoint="https://x/api.php")

    @staticmethod
    def make_response(
        *,
        ok: bool = True,
        status: int = 200,
        content: bytes = b"{}",
        payload: object = None,
    ) -> mock.Mock:
        response = mock.Mock()
        response.ok = ok
        response.status_code = status
        response.content = content
        response.headers = {"Content-Type": "application/json"}
        if payload is None:
            response.json.side_effect = ValueError("not json")
        else:
            response.json.return_value = payload
        return response

    def call(self, responses: list[mock.Mock]) -> object:
        with mock.patch.object(settings, "request_max_tries", 3), \
             mock.patch.object(wiki_module.time, "sleep"), \
             mock.patch.object(wiki_module.http.session, "get", side_effect=responses):
            return self.instance._api_get({"action": "query"})

    def test_parses_json(self) -> None:
        response = self.make_response(payload={"query": {"pages": {}}})
        self.assertEqual(self.call([response]), {"query": {"pages": {}}})

    def test_non_json_is_retried_then_succeeds(self) -> None:
        html = self.make_response(content=b"<html>")
        good = self.make_response(payload={"query": {}})
        with mock.patch.object(settings, "request_max_tries", 3), \
             mock.patch.object(wiki_module.time, "sleep"), \
             mock.patch.object(
                 wiki_module.http.session, "get", side_effect=[html, good]
             ) as get:
            self.assertEqual(self.instance._api_get({"action": "query"}), {"query": {}})
            self.assertEqual(get.call_count, 2)

    def test_giving_up_returns_none(self) -> None:
        html = self.make_response(content=b"<html>")
        with mock.patch.object(settings, "request_max_tries", 3), \
             mock.patch.object(wiki_module.time, "sleep"), \
             mock.patch.object(
                 wiki_module.http.session, "get", side_effect=[html, html, html]
             ) as get:
            self.assertIsNone(self.instance._api_get({"action": "query"}))
            self.assertEqual(get.call_count, 3)

    def test_http_error_returns_none(self) -> None:
        error = self.make_response(ok=False, status=503)
        self.assertIsNone(self.call([error, error, error]))

    def test_empty_body_returns_empty_dict(self) -> None:
        empty = self.make_response(content=b"")
        self.assertEqual(self.call([empty]), {})

    def test_network_exception_returns_none(self) -> None:
        with mock.patch.object(settings, "request_max_tries", 2), \
             mock.patch.object(wiki_module.time, "sleep"), \
             mock.patch.object(
                 wiki_module.http.session, "get", side_effect=OSError("down")
             ):
            self.assertIsNone(self.instance._api_get({"action": "query"}))


class SuppressionCheckTest(unittest.TestCase):
    def setUp(self) -> None:
        self.instance = wiki_module.Wiki(bot_name="TestBot", api_endpoint="https://x/api.php")

    @staticmethod
    def payload(revid: int | None) -> dict[str, object]:
        if revid is None:
            return {"query": {"pages": {"1": {}}}}
        return {"query": {"pages": {"1": {"revisions": [{"revid": revid}]}}}}

    def test_malformed_api_results_never_raise(self) -> None:
        results: list[object] = [
            None,
            {},
            {"query": {}},
            {"query": {"pages": []}},
            {"query": {"pages": {"1": {}}}},
            {"query": {"pages": {"1": {"revisions": []}}}},
        ]
        for result in results:
            with mock.patch.object(self.instance, "_api_get", return_value=result):
                self.instance._check_suppressed_action()

    def test_first_run_stores_the_reference_revision(self) -> None:
        with TemporaryDirectory() as tmp:
            self.instance.heartbeat_file = str(Path(tmp) / "heartbeat")
            with mock.patch.object(
                self.instance, "_api_get", return_value=self.payload(42)
            ):
                self.instance._check_suppressed_action()
            self.assertEqual(
                Path(self.instance.heartbeat_file).read_text(encoding="utf-8"), "42"
            )

    def test_unchanged_revision_keeps_running(self) -> None:
        with TemporaryDirectory() as tmp:
            self.instance.heartbeat_file = str(Path(tmp) / "heartbeat")
            Path(self.instance.heartbeat_file).write_text("7", encoding="utf-8")
            with mock.patch.object(
                self.instance, "_api_get", return_value=self.payload(7)
            ):
                self.instance._check_suppressed_action()

    def test_creating_a_previously_absent_signal_page_stops_the_bot(self) -> None:
        """The FIRST edit of the page must stop the bot, not become a baseline."""
        with TemporaryDirectory() as tmp:
            self.instance.heartbeat_file = str(Path(tmp) / "heartbeat")
            with mock.patch.object(
                self.instance, "_api_get", return_value=self.payload(None)
            ):
                self.instance._check_suppressed_action()
            self.assertEqual(
                Path(self.instance.heartbeat_file).read_text(encoding="utf-8"),
                wiki_module.SUPPRESSION_PAGE_ABSENT,
            )

            with mock.patch.object(
                self.instance, "_api_get", return_value=self.payload(99)
            ), mock.patch.object(wiki_module.mailer, "email") as email:
                with self.assertRaises(SystemExit):
                    self.instance._check_suppressed_action()
            self.assertEqual(email.call_count, 1)

    def test_changed_revision_stops_the_bot_and_alerts(self) -> None:
        with TemporaryDirectory() as tmp:
            self.instance.heartbeat_file = str(Path(tmp) / "heartbeat")
            Path(self.instance.heartbeat_file).write_text("1", encoding="utf-8")
            with mock.patch.object(
                self.instance, "_api_get", return_value=self.payload(2)
            ), mock.patch.object(wiki_module.mailer, "email") as email:
                with self.assertRaises(SystemExit):
                    self.instance._check_suppressed_action()
            self.assertEqual(email.call_count, 1)
            # The stored revision is not overwritten on a suppression.
            self.assertEqual(
                Path(self.instance.heartbeat_file).read_text(encoding="utf-8"), "1"
            )


class TickTest(unittest.TestCase):
    def test_kill_switch_runs_every_n_requests(self) -> None:
        instance = wiki_module.Wiki(bot_name="B", api_endpoint="https://x/api.php")
        with mock.patch.object(instance, "_check_suppressed_action") as check:
            for _ in range(wiki_module.SUPPRESSION_CHECK_INTERVAL):
                instance.tick()
            check.assert_called_once()

    def test_ticks_are_ignored_while_checking(self) -> None:
        instance = wiki_module.Wiki(bot_name="B", api_endpoint="https://x/api.php")
        instance._tick_disabled = True
        instance.request_count = wiki_module.SUPPRESSION_CHECK_INTERVAL
        instance.tick()
        self.assertEqual(instance.request_count, wiki_module.SUPPRESSION_CHECK_INTERVAL)


class CheckAllowBotsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.instance = wiki_module.Wiki(bot_name="Yugong-bot", api_endpoint="https://x/api.php")

    def page_with_text(self, text: str) -> mock.Mock:
        page = mock.Mock()
        page.text = text
        return page

    def test_opt_out_template_is_detected(self) -> None:
        with mock.patch.object(self.instance, "page", return_value=self.page_with_text("{{nobots}}")):
            self.assertFalse(self.instance.check_allow_bots("Foo"))

    def test_bot_specific_deny_is_detected(self) -> None:
        page = self.page_with_text("{{bots|deny=Yugong-bot}}")
        with mock.patch.object(self.instance, "page", return_value=page):
            self.assertFalse(self.instance.check_allow_bots("Foo"))

    def test_plain_talk_page_allows_the_bot(self) -> None:
        with mock.patch.object(self.instance, "page", return_value=self.page_with_text("hi")):
            self.assertTrue(self.instance.check_allow_bots("Foo"))

    def test_empty_talk_page_allows_the_bot(self) -> None:
        with mock.patch.object(self.instance, "page", return_value=self.page_with_text("")):
            self.assertTrue(self.instance.check_allow_bots("Foo"))

    def test_unreadable_page_fails_closed(self) -> None:
        with mock.patch.object(self.instance, "page", side_effect=RuntimeError("boom")):
            self.assertFalse(self.instance.check_allow_bots("Foo"))

    def test_unparseable_user_is_refused(self) -> None:
        self.assertFalse(self.instance.check_allow_bots("Some:Namespace"))


if __name__ == "__main__":
    unittest.main()
