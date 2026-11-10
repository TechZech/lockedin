import json
import unittest
from threading import Event
from unittest.mock import Mock

from lockedin.tango.browser import BrowserSessionError, FEED_URL, TANGO_URL, TangoBrowserSession


class FakePage:
    def __init__(self, snapshot: dict) -> None:
        self.snapshot = json.dumps(snapshot)
        self.clicked: list[str] = []

    def evaluate(self, expression: str) -> str:
        return self.snapshot

    def click(self, selector: str) -> None:
        self.clicked.append(selector)


def snapshot() -> dict:
    return {
        "cells": [{"index": index, "state": "?"} for index in range(36)],
        "relations": [],
    }


class TangoBrowserSessionTests(unittest.TestCase):
    def test_existing_login_opens_tango_after_verifying_feed(self) -> None:
        page = Mock()
        page.url = FEED_URL
        page.is_closed.return_value = False
        context = Mock()
        context.cookies.return_value = [{"name": "li_at", "expires": -1}]

        TangoBrowserSession(page, _context=context).open_logged_in_tango(Event())

        self.assertEqual([call.args[0] for call in page.goto.call_args_list], [FEED_URL, TANGO_URL])

    def test_waits_until_user_reaches_feed_with_valid_login(self) -> None:
        page = Mock()
        page.url = "https://www.linkedin.com/login"
        page.is_closed.return_value = False
        context = Mock()
        context.cookies.return_value = [{"name": "li_at", "expires": -1}]
        page.wait_for_timeout.side_effect = lambda _: setattr(page, "url", FEED_URL)

        TangoBrowserSession(page, _context=context).open_logged_in_tango(Event())

        page.wait_for_timeout.assert_called_once_with(250)
        self.assertEqual(page.goto.call_args_list[-1].args[0], TANGO_URL)

    def test_does_not_open_tango_for_anonymous_or_expired_session(self) -> None:
        for cookies in ([], [{"name": "li_at", "expires": 1}]):
            with self.subTest(cookies=cookies):
                page = Mock()
                page.url = FEED_URL
                page.is_closed.return_value = False
                context = Mock()
                context.cookies.return_value = cookies
                with self.assertRaisesRegex(BrowserSessionError, "timed out"):
                    TangoBrowserSession(page, _context=context).open_logged_in_tango(Event(), timeout=0)
                self.assertEqual([call.args[0] for call in page.goto.call_args_list], [FEED_URL])

    def test_auth_cookie_on_login_or_unrelated_page_is_not_enough(self) -> None:
        for url in ("https://www.linkedin.com/login", "https://example.com/feed/"):
            with self.subTest(url=url):
                page = Mock()
                page.url = url
                page.is_closed.return_value = False
                context = Mock()
                context.cookies.return_value = [{"name": "li_at", "expires": -1}]
                with self.assertRaisesRegex(BrowserSessionError, "timed out"):
                    TangoBrowserSession(page, _context=context).open_logged_in_tango(Event(), timeout=0)
                self.assertEqual([call.args[0] for call in page.goto.call_args_list], [FEED_URL])

    def test_closed_browser_during_sign_in_is_reported(self) -> None:
        page = Mock()
        page.is_closed.return_value = True
        with self.assertRaisesRegex(BrowserSessionError, "closed during sign-in"):
            TangoBrowserSession(page, _context=Mock()).open_logged_in_tango(Event())

    def test_sign_in_can_be_cancelled(self) -> None:
        stop = Event()
        stop.set()
        page = Mock()
        with self.assertRaisesRegex(BrowserSessionError, "cancelled"):
            TangoBrowserSession(page, _context=Mock()).open_logged_in_tango(stop)
        page.goto.assert_not_called()

    def test_test_session_accepts_board_without_login_and_opens_tango(self) -> None:
        page = Mock()
        page.url = TANGO_URL
        page.is_closed.return_value = False
        page.locator.return_value.count.return_value = 36
        context = Mock()
        context.cookies.return_value = []
        session = TangoBrowserSession(page, _context=context, require_login=False)

        session.open_tango()
        session.wait_for_board(Event())

        page.goto.assert_called_once_with(TANGO_URL, wait_until="domcontentloaded")

    def test_closing_test_session_closes_context_browser_and_playwright(self) -> None:
        context, browser, playwright = Mock(), Mock(), Mock()
        session = TangoBrowserSession(
            Mock(), _playwright=playwright, _browser=browser, _context=context, _owns_browser=True
        )

        session.close()

        context.close.assert_called_once_with()
        browser.close.assert_called_once_with()
        playwright.stop.assert_called_once_with()

    def test_board_wait_rejects_expired_sign_in(self) -> None:
        page = Mock()
        page.url = TANGO_URL
        page.is_closed.return_value = False
        page.locator.return_value.count.return_value = 36
        context = Mock()
        context.cookies.return_value = []
        with self.assertRaisesRegex(BrowserSessionError, "sign-in expired"):
            TangoBrowserSession(page, _context=context).wait_for_board(Event())

    def test_wait_for_board_only_accepts_tango_page_with_36_cells(self) -> None:
        page = Mock()
        page.url = "https://www.linkedin.com/games/tango/"
        page.is_closed.return_value = False
        page.locator.return_value.count.side_effect = [0, 36]
        session = TangoBrowserSession(page)

        session.wait_for_board(Event(), timeout=1)

        page.wait_for_timeout.assert_called_once_with(250)

    def test_wait_for_board_does_not_read_an_unrelated_page(self) -> None:
        page = Mock()
        page.url = "https://example.com/games/tango/"
        page.is_closed.return_value = False

        with self.assertRaisesRegex(BrowserSessionError, "timed out"):
            TangoBrowserSession(page).wait_for_board(Event(), timeout=0)
        page.locator.assert_not_called()

    def test_wait_for_board_stops_when_cancelled(self) -> None:
        stop = Event()
        stop.set()
        with self.assertRaisesRegex(BrowserSessionError, "cancelled"):
            TangoBrowserSession(Mock()).wait_for_board(stop)

    def test_snapshot_board_uses_existing_dom_adapter(self) -> None:
        session = TangoBrowserSession(FakePage(snapshot()))

        board = session.snapshot_board()

        self.assertEqual(board.as_strings(), ("??????",) * 6)
