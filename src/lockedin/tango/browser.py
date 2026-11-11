"""Browser-session adapter for interacting with a logged-in Tango page."""

from __future__ import annotations

from threading import Event
from time import monotonic
from typing import Callable
from urllib.parse import urlsplit

from playwright.sync_api import Error as PlaywrightError

from ..browser import BrowserSession, BrowserSessionError
from ..browser import FEED_URL as FEED_URL
from ..timing import prepare_timer, wait_for_game_time
from .actions import ActionPlan, create_action_plan
from .dom import SNAPSHOT_SCRIPT, board_from_json
from .model import BOARD_SIZE, Board, Cell
from .solver import Solver
from .workflow import plan_board

TANGO_URL = "https://www.linkedin.com/games/tango/"
GRID_CELLS = '[data-testid="interactive-grid"] [data-testid^="cell-"][data-cell-idx]'
CLICK_TIMEOUT_MS = 2000
STATE_TIMEOUT = 2.0
POLL_INTERVAL_MS = 50


class TangoBrowserSession(BrowserSession):
    """Own a connection to an existing, logged-in Chromium browser."""

    def open_tango(self) -> None:
        """Go straight to the game without requiring a LinkedIn login."""
        self.open_game(TANGO_URL, "Tango")

    def open_logged_in_tango(self, stop: Event, timeout: float = 300) -> None:
        """Require a LinkedIn login before navigating to the Tango game."""
        self.open_logged_in_game(TANGO_URL, "Tango", stop, timeout)

    def wait_for_board(self, stop: Event, timeout: float = 300) -> None:
        """Wait for the game to start without blocking the desktop window."""
        deadline = monotonic() + timeout
        while not stop.is_set():
            if self.page.is_closed():
                raise BrowserSessionError("the browser was closed before the board was ready")
            url = urlsplit(self.page.url)
            if (
                url.scheme == "https"
                and url.hostname in ("linkedin.com", "www.linkedin.com")
                and url.path.rstrip("/") == "/games/tango"
                and self.page.locator(GRID_CELLS).count() == 36
            ):
                self.check_login()
                return
            if monotonic() >= deadline:
                raise BrowserSessionError("timed out waiting for the Tango board; sign in and start the game")
            self.page.wait_for_timeout(250)
        raise BrowserSessionError("the solve was cancelled")

    def snapshot_board(self) -> Board:
        try:
            snapshot = self.page.evaluate(SNAPSHOT_SCRIPT)
            return board_from_json(snapshot)
        except Exception as error:
            raise BrowserSessionError(f"could not read a Tango board from the browser: {error}") from error

    def solve(self) -> Board:
        return Solver().solve(self.snapshot_board())

    def plan_solution(self) -> ActionPlan:
        return plan_board(self.snapshot_board())

    def execute_actions(
        self,
        plan: ActionPlan,
        *,
        stop: Event | None = None,
        progress: Callable[[int, int], None] | None = None,
        target_seconds: int = 0,
        status: Callable[[str], None] | None = None,
    ) -> None:
        """Execute a plan only while the observed board matches each expected state."""
        try:
            if create_action_plan(plan.current, plan.solved) != plan:
                raise BrowserSessionError("click plan does not match the boards")
            Solver().solve(plan.solved)
        except ValueError as error:
            raise BrowserSessionError(f"invalid click plan: {error}") from error

        self._check_execution_page(stop)
        expected = plan.current
        self._require_board(expected, "board changed since the plan was created")
        timed = prepare_timer(self.page, target_seconds, status=status) if plan.actions else False

        for completed, action in enumerate(plan.actions, start=1):
            position = divmod(action.index, BOARD_SIZE)
            selector = f'{GRID_CELLS}[data-cell-idx="{action.index}"]'
            for click in range(action.clicks):
                self._check_execution_page(stop)
                self._require_board(expected, f"board changed before cell {action.index}")
                if timed and completed == len(plan.actions) and click == action.clicks - 1:
                    def check() -> None:
                        self._check_execution_page(stop)
                        self._require_board(expected, "board changed while waiting for the game timer")
                    wait_for_game_time(self.page, self.page, target_seconds, check, status=status)
                before = expected.cell(position)
                after = {Cell.UNKNOWN: Cell.SUN, Cell.SUN: Cell.MOON}[before]
                rows = [list(row) for row in expected.cells]
                rows[position[0]][position[1]] = after
                next_board = Board(tuple(tuple(row) for row in rows), expected.constraints)
                try:
                    self.page.locator(selector).click(timeout=CLICK_TIMEOUT_MS)
                except PlaywrightError as error:
                    raise BrowserSessionError(
                        f"could not click cell {action.index}; its state may have changed: {error}"
                    ) from error
                self._wait_for_transition(expected, next_board, action.index, stop)
                expected = next_board
            if progress is not None:
                progress(completed, len(plan.actions))

        self._check_execution_page(stop)
        self._require_board(plan.solved, "final board does not match the solution")

    def _check_execution_page(self, stop: Event | None) -> None:
        if stop is not None and stop.is_set():
            raise BrowserSessionError("the solve was cancelled; the board may be partially filled")
        if self.page.is_closed():
            raise BrowserSessionError("the Tango browser was closed during execution")
        url = urlsplit(self.page.url)
        if (
            url.scheme != "https"
            or url.hostname not in ("linkedin.com", "www.linkedin.com")
            or url.path.rstrip("/") != "/games/tango"
        ):
            raise BrowserSessionError("the browser is no longer on the Tango page")
        self.check_login()

    def _require_board(self, expected: Board, message: str) -> None:
        if self.snapshot_board() != expected:
            raise BrowserSessionError(message)

    def _wait_for_transition(
        self, before: Board, after: Board, index: int, stop: Event | None
    ) -> None:
        deadline = monotonic() + STATE_TIMEOUT
        while True:
            self._check_execution_page(stop)
            observed = self.snapshot_board()
            if observed == after:
                return
            if observed != before:
                position = divmod(index, BOARD_SIZE)
                raise BrowserSessionError(
                    f"unexpected board change after clicking cell {index}; "
                    f"expected {after.cell(position).value}, observed {observed.cell(position).value}"
                )
            if monotonic() >= deadline:
                position = divmod(index, BOARD_SIZE)
                raise BrowserSessionError(
                    f"timed out after clicking cell {index}; "
                    f"expected {after.cell(position).value}, observed {observed.cell(position).value}"
                )
            try:
                self.page.wait_for_timeout(POLL_INTERVAL_MS)
            except PlaywrightError as error:
                raise BrowserSessionError(
                    f"could not verify cell {index} after clicking; its state may have changed: {error}"
                ) from error
