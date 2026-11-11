"""Browser adapter for LinkedIn Mini Sudoku."""

from __future__ import annotations

from threading import Event
from time import monotonic
from typing import Any, Callable, Iterator
from urllib.parse import urlsplit

from playwright.sync_api import Error as PlaywrightError

from ..browser import BrowserSession, BrowserSessionError
from ..timing import prepare_timer, wait_for_game_time
from .actions import ActionPlan, create_action_plan
from .dom import SNAPSHOT_SCRIPT, board_from_json
from .model import BOARD_SIZE, Board
from .solver import Solver
from .workflow import plan_board

SUDOKU_URL = "https://www.linkedin.com/games/mini-sudoku/"
GRID_CELLS = '[data-sudoku-grid="true"] .sudoku-cell[data-cell-idx]'
GRID = '[data-sudoku-grid="true"]'
NOTES = '[data-control-btn="notes"]'
START_BUTTON = "#launch-footer-start-button"
CLICK_TIMEOUT_MS = 2000
STATE_TIMEOUT = 2.0
POLL_INTERVAL_MS = 50


class MiniSudokuBrowserSession(BrowserSession):
    """Interact with a Mini Sudoku game in a LinkedIn browser."""

    def open_sudoku(self) -> None:
        self.open_game(SUDOKU_URL, "Mini Sudoku")

    def open_logged_in_sudoku(self, stop: Event, timeout: float = 300) -> None:
        self.open_logged_in_game(SUDOKU_URL, "Mini Sudoku", stop, timeout)

    def _game_frames(self) -> Iterator[Any]:
        for frame in self.page.frames:
            url = urlsplit(frame.url)
            if (url.scheme == "https" and url.hostname in ("linkedin.com", "www.linkedin.com")
                    and url.path.rstrip("/") in ("/games/mini-sudoku", "/games/view/mini-sudoku/desktop")):
                yield frame

    def _game_frame(self) -> Any:
        for frame in self._game_frames():
            grid = frame.locator(GRID)
            if grid.count() == 1 and grid.is_visible() and frame.locator(GRID_CELLS).count() == 36:
                return frame
        raise BrowserSessionError("Mini Sudoku board not found in the game page")

    def wait_for_board(self, stop: Event, timeout: float = 300) -> None:
        deadline = monotonic() + timeout
        started = False
        while not stop.is_set():
            self._check_execution_page(stop)
            try:
                frame = self._game_frame()
            except BrowserSessionError:
                pass
            else:
                notes = frame.locator(NOTES)
                keypad = frame.locator('button.sudoku-input-button[data-number]')
                if (notes.count() == 1 and notes.is_visible() and
                        all(frame.locator(f'button.sudoku-input-button[data-number="{number}"]').is_visible()
                            for number in range(1, 7)) and keypad.count() >= 6):
                    self.mark_board_ready()
                    return
            if not started:
                for frame in self._game_frames():
                    button = frame.locator(START_BUTTON)
                    if button.count() == 1 and button.is_visible():
                        self._check_execution_page(stop)
                        try:
                            button.click(timeout=CLICK_TIMEOUT_MS)
                        except PlaywrightError as error:
                            raise BrowserSessionError(f"could not start Mini Sudoku: {error}") from error
                        started = True
                        break
            if monotonic() >= deadline:
                raise BrowserSessionError("timed out waiting for the Mini Sudoku board; start the game")
            self.page.wait_for_timeout(250)
        raise BrowserSessionError("the solve was cancelled")

    def snapshot_board(self) -> Board:
        try:
            board = board_from_json(self._game_frame().evaluate(SNAPSHOT_SCRIPT))
            self.board_started_at()
            return board
        except (PlaywrightError, ValueError, BrowserSessionError) as error:
            raise BrowserSessionError(f"could not read a Mini Sudoku board: {error}") from error

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
        try:
            if create_action_plan(plan.current, plan.solved) != plan:
                raise BrowserSessionError("action plan does not match the boards")
            if Solver().solve(plan.current) != plan.solved:
                raise BrowserSessionError("solution does not match the current board")
        except ValueError as error:
            raise BrowserSessionError(f"invalid action plan: {error}") from error
        self._check_execution_page(stop)
        expected = plan.current
        self._require_board(expected, "board changed since the plan was created")
        timed = (prepare_timer(self._game_frame(), target_seconds, started_at=self.board_started_at(),
                               status=status) if plan.actions else None)
        for completed, action in enumerate(plan.actions, start=1):
            self._check_execution_page(stop)
            self._require_board(expected, f"board changed before cell {action.index}")
            frame = self._game_frame()
            self._check_notes_off(frame)
            cell = frame.locator(f'{GRID_CELLS}[data-cell-idx="{action.index}"]')
            try:
                cell.click(timeout=CLICK_TIMEOUT_MS)
                if "sudoku-cell-active" not in (cell.get_attribute("class") or "").split():
                    raise BrowserSessionError(f"cell {action.index} was not selected")
                self._check_execution_page(stop)
                self._require_board(expected, f"board changed while selecting cell {action.index}")
                self._check_notes_off(frame)
                if timed and completed == len(plan.actions):
                    def check() -> None:
                        self._check_execution_page(stop)
                        self._require_board(expected, "board changed while waiting for the game timer")
                        self._check_notes_off(frame)
                        if "sudoku-cell-active" not in (cell.get_attribute("class") or "").split():
                            raise BrowserSessionError("selected cell changed while waiting for the game timer")
                    wait_for_game_time(self.page, frame, target_seconds, check, timer=timed, status=status)
                frame.locator(f'button.sudoku-input-button[data-number="{action.target}"]').click(
                    timeout=CLICK_TIMEOUT_MS
                )
            except PlaywrightError as error:
                raise BrowserSessionError(f"could not enter cell {action.index}: {error}") from error
            row, column = divmod(action.index, BOARD_SIZE)
            rows = [list(values) for values in expected.cells]
            rows[row][column] = action.target
            next_board = Board(tuple(tuple(values) for values in rows))
            self._wait_for_transition(expected, next_board, action.index, stop)
            expected = next_board
            if progress is not None:
                progress(completed, len(plan.actions))
        self._check_execution_page(stop)
        self._require_board(plan.solved, "final board does not match the solution")

    @staticmethod
    def _check_notes_off(frame: Any) -> None:
        notes = frame.locator(NOTES)
        if notes.count() != 1 or notes.locator(".sudoku-under-board__text--disabled").count() != 1:
            raise BrowserSessionError("turn Notes OFF before solving Mini Sudoku")

    def _check_execution_page(self, stop: Event | None) -> None:
        if stop is not None and stop.is_set():
            raise BrowserSessionError("the solve was cancelled; the board may be partially filled")
        if self.page.is_closed():
            raise BrowserSessionError("the Mini Sudoku browser was closed")
        url = urlsplit(self.page.url)
        if (url.scheme != "https" or url.hostname not in ("linkedin.com", "www.linkedin.com")
                or url.path.rstrip("/") not in ("/games/mini-sudoku", "/games/view/mini-sudoku/desktop")):
            raise BrowserSessionError("the browser is no longer on the Mini Sudoku page")
        self.check_login()

    def _require_board(self, expected: Board, message: str) -> None:
        if self.snapshot_board() != expected:
            raise BrowserSessionError(message)

    def _wait_for_transition(self, before: Board, after: Board, index: int, stop: Event | None) -> None:
        deadline = monotonic() + STATE_TIMEOUT
        while True:
            self._check_execution_page(stop)
            observed = self.snapshot_board()
            if observed == after:
                return
            if observed != before:
                raise BrowserSessionError(f"unexpected board change after entering cell {index}")
            if monotonic() >= deadline:
                raise BrowserSessionError(f"timed out waiting for cell {index} to update")
            self.page.wait_for_timeout(POLL_INTERVAL_MS)
