"""Browser adapter for LinkedIn Zip."""

from __future__ import annotations

from threading import Event
from time import monotonic
from typing import Callable
from urllib.parse import urlsplit

from playwright.sync_api import Error as PlaywrightError

from ..browser import BrowserSession, BrowserSessionError
from ..timing import prepare_timer, wait_for_game_time
from .actions import ActionPlan, create_action_plan
from .dom import SNAPSHOT_SCRIPT, Snapshot, snapshot_from_json
from .model import Board
from .workflow import plan_board

ZIP_URL = "https://www.linkedin.com/games/zip/"
GRID = '[data-testid="interactive-grid"][data-trail-grid]'
STATE_TIMEOUT = 2.0
POLL_INTERVAL_MS = 50


class ZipBrowserSession(BrowserSession):
    def open_zip(self) -> None:
        self.open_game(ZIP_URL, "Zip")

    def open_logged_in_zip(self, stop: Event, timeout: float = 300) -> None:
        self.open_logged_in_game(ZIP_URL, "Zip", stop, timeout)

    def _check_page(self, stop: Event | None = None) -> None:
        if stop is not None and stop.is_set():
            raise BrowserSessionError("the solve was cancelled; the path may be partially drawn")
        if self.page.is_closed():
            raise BrowserSessionError("the Zip browser was closed")
        url = urlsplit(self.page.url)
        if (url.scheme != "https" or url.hostname not in ("linkedin.com", "www.linkedin.com")
                or url.path.rstrip("/") != "/games/zip"):
            raise BrowserSessionError("the browser is no longer on the Zip page")
        self.check_login()

    def wait_for_board(self, stop: Event, timeout: float = 300) -> None:
        deadline = monotonic() + timeout
        while not stop.is_set():
            self._check_page(stop)
            grid = self.page.locator(GRID)
            if grid.count() == 1 and grid.is_visible():
                self.mark_board_ready()
                return
            if monotonic() >= deadline:
                raise BrowserSessionError("timed out waiting for the Zip board; start the game")
            self.page.wait_for_timeout(250)
        raise BrowserSessionError("the solve was cancelled")

    def _snapshot(self) -> Snapshot:
        try:
            return snapshot_from_json(self.page.evaluate(SNAPSHOT_SCRIPT))
        except (PlaywrightError, ValueError) as error:
            raise BrowserSessionError(f"could not read a Zip board: {error}") from error

    def snapshot_board(self) -> Board:
        board = self._snapshot().board
        self.board_started_at()
        return board

    def solve(self) -> tuple[int, ...]:
        return self.plan_solution().path

    def plan_solution(self) -> ActionPlan:
        return plan_board(self.snapshot_board())

    def execute_actions(
        self, plan: ActionPlan, *, stop: Event | None = None,
        progress: Callable[[int, int], None] | None = None,
        target_seconds: int = 0,
        status: Callable[[str], None] | None = None,
    ) -> None:
        try:
            if create_action_plan(plan.board, plan.path) != plan:
                raise BrowserSessionError("action plan does not match the path")
        except ValueError as error:
            raise BrowserSessionError(f"invalid action plan: {error}") from error
        self._check_page(stop)
        expected = Snapshot(plan.board, frozenset((plan.path[0],)))
        if self._snapshot() != expected:
            raise BrowserSessionError("board changed or already has a partial path; reset it and retry")
        timed = (prepare_timer(self.page, target_seconds, started_at=self.board_started_at(), status=status)
                 if plan.moves else None)
        try:
            self.page.locator(GRID).focus(timeout=2000)
        except PlaywrightError as error:
            raise BrowserSessionError(f"could not focus the Zip grid: {error}") from error
        for done, (move, cell) in enumerate(zip(plan.moves, plan.path[1:]), 1):
            self._check_page(stop)
            if self._snapshot() != expected:
                raise BrowserSessionError("Zip board changed before the next move")
            if timed and done == len(plan.moves):
                def check() -> None:
                    self._check_page(stop)
                    if self._snapshot() != expected:
                        raise BrowserSessionError("Zip board changed while waiting for the game timer")
                wait_for_game_time(self.page, self.page, target_seconds, check, timer=timed, status=status)
                try:
                    self.page.locator(GRID).focus(timeout=2000)
                except PlaywrightError as error:
                    raise BrowserSessionError(f"could not focus the Zip grid: {error}") from error
                check()
            try:
                self.page.keyboard.press(move)
            except PlaywrightError as error:
                raise BrowserSessionError(f"could not draw the path to cell {cell}: {error}") from error
            after = Snapshot(plan.board, expected.filled | {cell})
            deadline = monotonic() + STATE_TIMEOUT
            while True:
                self._check_page(stop)
                observed = self._snapshot()
                if observed == after:
                    break
                if observed != expected:
                    raise BrowserSessionError(f"unexpected Zip board change after moving to cell {cell}")
                if monotonic() >= deadline:
                    raise BrowserSessionError(f"timed out waiting for the path to reach cell {cell}")
                self.page.wait_for_timeout(POLL_INTERVAL_MS)
            expected = after
            if progress is not None:
                progress(done, len(plan.moves))
