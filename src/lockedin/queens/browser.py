"""Browser adapter for LinkedIn Queens."""

from __future__ import annotations

from threading import Event
from time import monotonic
from typing import Callable
from urllib.parse import urlsplit

from playwright.sync_api import Error as PlaywrightError

from ..browser import BrowserSession, BrowserSessionError
from ..timing import prepare_timer, wait_for_game_time
from .actions import ActionPlan, create_action_plan
from .dom import SNAPSHOT_SCRIPT, board_from_json
from .model import Board, Cell
from .workflow import plan_board

QUEENS_URL = "https://www.linkedin.com/games/queens/"
GRID = '#queens-game-board [data-testid="interactive-grid"]'
GRID_CELLS = f'{GRID} [data-cell-idx]'
CLICK_TIMEOUT_MS = 2000
STATE_TIMEOUT = 2.0
POLL_INTERVAL_MS = 50


class QueensBrowserSession(BrowserSession):
    def open_queens(self) -> None:
        self.open_game(QUEENS_URL, "Queens")

    def open_logged_in_queens(self, stop: Event, timeout: float = 300) -> None:
        self.open_logged_in_game(QUEENS_URL, "Queens", stop, timeout)

    def _check_page(self, stop: Event | None = None) -> None:
        if stop is not None and stop.is_set():
            raise BrowserSessionError("the solve was cancelled; the board may be partially filled")
        if self.page.is_closed():
            raise BrowserSessionError("the Queens browser was closed")
        url = urlsplit(self.page.url)
        if (url.scheme != "https" or url.hostname not in ("linkedin.com", "www.linkedin.com")
                or url.path.rstrip("/") != "/games/queens"):
            raise BrowserSessionError("the browser is no longer on the Queens page")
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
                raise BrowserSessionError("timed out waiting for the Queens board; start the game")
            self.page.wait_for_timeout(250)
        raise BrowserSessionError("the solve was cancelled")

    def snapshot_board(self) -> Board:
        try:
            board = board_from_json(self.page.evaluate(SNAPSHOT_SCRIPT))
            self.board_started_at()
            return board
        except (PlaywrightError, ValueError) as error:
            raise BrowserSessionError(f"could not read a Queens board: {error}") from error

    def solve(self) -> Board:
        return self.plan_solution().solved

    def plan_solution(self) -> ActionPlan:
        return plan_board(self.snapshot_board())

    def execute_actions(
        self, plan: ActionPlan, *, stop: Event | None = None,
        progress: Callable[[int, int], None] | None = None,
        target_seconds: int = 0, status: Callable[[str], None] | None = None,
    ) -> None:
        try:
            if create_action_plan(plan.current, plan.solved) != plan:
                raise BrowserSessionError("action plan does not match the boards")
        except ValueError as error:
            raise BrowserSessionError(f"invalid action plan: {error}") from error
        self._check_page(stop)
        expected = plan.current
        self._require_board(expected, "board changed since the plan was created")
        timed = (prepare_timer(self.page, target_seconds, started_at=self.board_started_at(), status=status)
                 if plan.actions else None)
        for done, action in enumerate(plan.actions, 1):
            for click in range(action.clicks):
                self._check_page(stop)
                self._require_board(expected, f"board changed before cell {action.index}")
                if timed and done == len(plan.actions) and click == action.clicks - 1:
                    def check() -> None:
                        self._check_page(stop)
                        self._require_board(expected, "board changed while waiting for the game timer")
                    wait_for_game_time(self.page, self.page, target_seconds, check, timer=timed, status=status)
                after = expected.with_cell(action.index, Cell.CROSS if click == 0 else Cell.QUEEN)
                try:
                    self.page.locator(f'{GRID_CELLS}[data-cell-idx="{action.index}"]').click(
                        timeout=CLICK_TIMEOUT_MS
                    )
                except PlaywrightError as error:
                    raise BrowserSessionError(f"could not click cell {action.index}: {error}") from error
                expected = self._wait_for_transition(expected, after, plan.solved, action.index, stop)
            if progress is not None:
                progress(done, len(plan.actions))
        self._check_page(stop)
        self._require_board(expected, "final board changed after the last click")
        for row in range(expected.size):
            for column in range(expected.size):
                actual = expected.cells[row][column]
                target = plan.solved.cells[row][column]
                if (actual is Cell.QUEEN) != (target is Cell.QUEEN) or (
                    target is Cell.CROSS and actual is not Cell.CROSS
                ):
                    raise BrowserSessionError("final board does not match the solution")

    def _require_board(self, expected: Board, message: str) -> None:
        if self.snapshot_board() != expected:
            raise BrowserSessionError(message)

    def _wait_for_transition(
        self, before: Board, after: Board, solved: Board, index: int, stop: Event | None
    ) -> Board:
        deadline = monotonic() + STATE_TIMEOUT
        while True:
            self._check_page(stop)
            observed = self.snapshot_board()
            if _valid_transition(before, after, solved, observed, index):
                return observed
            if observed != before:
                differences = _describe_changes(after, observed)
                raise BrowserSessionError(
                    f"unexpected board change after clicking cell {index}: {differences}"
                )
            if monotonic() >= deadline:
                raise BrowserSessionError(f"timed out waiting for cell {index} to change")
            try:
                self.page.wait_for_timeout(POLL_INTERVAL_MS)
            except PlaywrightError as error:
                raise BrowserSessionError(f"could not verify cell {index}: {error}") from error


def _valid_transition(before: Board, after: Board, solved: Board, observed: Board, index: int) -> bool:
    if observed.regions != after.regions or observed.size != after.size:
        return False
    row, column = divmod(index, after.size)
    if observed.cells[row][column] is not after.cells[row][column]:
        return False
    queen_placed = (before.cells[row][column] is Cell.CROSS
                    and after.cells[row][column] is Cell.QUEEN)
    for r in range(after.size):
        for c in range(after.size):
            actual, expected = observed.cells[r][c], after.cells[r][c]
            if actual is expected:
                continue
            conflicts = (r == row or c == column or after.regions[r][c] == after.regions[row][column]
                         or (abs(r - row) <= 1 and abs(c - column) <= 1))
            if not (queen_placed and expected is Cell.EMPTY and actual is Cell.CROSS and conflicts
                    and solved.cells[r][c] is not Cell.QUEEN):
                return False
    return True


def _describe_changes(expected: Board, observed: Board) -> str:
    if observed.regions != expected.regions:
        return "board dimensions or regions changed"
    differences = [
        f"cell {r * expected.size + c} expected {expected.cells[r][c].value}, "
        f"observed {observed.cells[r][c].value}"
        for r in range(expected.size) for c in range(expected.size)
        if expected.cells[r][c] is not observed.cells[r][c]
    ]
    return "; ".join(differences[:5])
