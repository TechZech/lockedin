"""Verified browser interaction for LinkedIn Wend."""

from __future__ import annotations

from collections import Counter
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
from .solver import Solver
from .workflow import plan_board

WEND_URL = "https://www.linkedin.com/games/wend/"
GRID = '[data-testid="wend-game-board"] [data-testid="interactive-grid"][data-trail-grid]'
STATE_TIMEOUT = 2.0
RESULT_TIMEOUT = 8.0
REJECTION_DELAY = 0.5
POLL_INTERVAL_MS = 50
MAX_ATTEMPTS = 500


def _is_result_page(url: str) -> bool:
    parsed = urlsplit(url)
    path = parsed.path.rstrip("/")
    return (parsed.scheme == "https" and parsed.hostname in ("linkedin.com", "www.linkedin.com")
            and (path == "/games/wend/results" or path.startswith("/games/wend/results/")))


class WendBrowserSession(BrowserSession):
    def open_wend(self) -> None:
        self.open_game(WEND_URL, "Wend")

    def open_logged_in_wend(self, stop: Event, timeout: float = 300) -> None:
        self.open_logged_in_game(WEND_URL, "Wend", stop, timeout)

    def _check_page(self, stop: Event | None = None, *, allow_result: bool = False) -> None:
        if stop is not None and stop.is_set():
            raise BrowserSessionError("the solve was cancelled; the board may be partially filled")
        if self.page.is_closed():
            raise BrowserSessionError("the Wend browser was closed")
        url = urlsplit(self.page.url)
        if (url.scheme != "https" or url.hostname not in ("linkedin.com", "www.linkedin.com")
                or (url.path.rstrip("/") != "/games/wend"
                    and not (allow_result and _is_result_page(self.page.url)))):
            raise BrowserSessionError("the browser is no longer on the Wend page")
        if not self.require_login and self._context is not None and self.has_login_cookie():
            raise BrowserSessionError("Wend trials require a signed-out browser")
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
                raise BrowserSessionError("timed out waiting for the Wend board; start the game")
            self.page.wait_for_timeout(250)
        raise BrowserSessionError("the solve was cancelled")

    def _snapshot(self) -> Snapshot:
        try:
            return snapshot_from_json(self.page.evaluate(SNAPSHOT_SCRIPT))
        except (PlaywrightError, ValueError) as error:
            raise BrowserSessionError(f"could not read a Wend board: {error}") from error

    def snapshot_board(self) -> Board:
        snapshot = self._snapshot()
        if snapshot.locked or any(snapshot.words):
            raise BrowserSessionError("Wend board has existing selections; reset it before solving")
        self.board_started_at()
        return snapshot.board

    def plan_solution(self) -> ActionPlan:
        return plan_board(self.snapshot_board())

    def _wait_for_win(self, expected: Snapshot | None, stop: Event | None) -> bool:
        deadline = monotonic() + RESULT_TIMEOUT
        while monotonic() < deadline:
            self._check_page(stop, allow_result=True)
            if self._won():
                return True
            if expected is not None and urlsplit(self.page.url).path.rstrip("/") == "/games/wend":
                try:
                    observed = self._snapshot()
                except BrowserSessionError as error:
                    navigating = (isinstance(error.__cause__, PlaywrightError)
                                  and "Execution context was destroyed" in str(error.__cause__))
                    on_result = _is_result_page(self.page.url)
                    if not navigating and not on_result:
                        raise
                else:
                    if observed != expected:
                        raise BrowserSessionError("Wend board changed while checking the result")
            self.page.wait_for_timeout(POLL_INTERVAL_MS)
        if self.require_login and expected is not None:
            return False
        raise BrowserSessionError("Wend result page did not confirm a win")

    def _won(self) -> bool:
        if not _is_result_page(self.page.url):
            return False
        try:
            return "Solved in" in self.page.locator("body").inner_text(timeout=2000)
        except PlaywrightError as error:
            raise BrowserSessionError(f"could not verify the Wend result: {error}") from error

    def solve_trials(
        self, *, stop: Event | None = None,
        progress: Callable[[int, int], None] | None = None,
        target_seconds: int = 0, status: Callable[[str], None] | None = None,
    ) -> bool:
        self._check_page(stop)
        board = self.snapshot_board()
        expected = Snapshot(board, frozenset(), tuple("" for _ in board.lengths))
        timer = prepare_timer(self.page, target_seconds, started_at=self.board_started_at(), status=status)
        accepted: set[tuple[int, ...]] = set()
        rejected: set[tuple[int, ...]] = set()
        attempted = 0
        def check_cancelled() -> None:
            if stop is not None and stop.is_set():
                raise BrowserSessionError("the solve was cancelled; the board may be partially filled")
        check_cancelled()
        for paths in Solver().solutions(board, check=check_cancelled):
            check_cancelled()
            create_action_plan(board, paths)
            if not accepted.issubset(paths) or rejected.intersection(paths):
                continue
            for path in paths:
                if path in accepted:
                    continue
                if attempted >= MAX_ATTEMPTS:
                    raise BrowserSessionError(f"stopped after {MAX_ATTEMPTS} Wend word attempts")
                self._check_page(stop)
                if self._snapshot() != expected:
                    raise BrowserSessionError("Wend board changed before the next word")
                if timer and len(accepted) == len(board.lengths) - 1:
                    def check() -> None:
                        self._check_page(stop)
                        if self._snapshot() != expected:
                            raise BrowserSessionError("Wend board changed while waiting for the game timer")
                    wait_for_game_time(self.page, self.page, target_seconds, check, timer=timer, status=status)
                attempted += 1
                word = "".join(board.letters[cell] for cell in path)
                if status is not None:
                    mode = "Signed-in game" if self.require_login else "Test mode"
                    status(f"{mode}: trying {word} ({attempted} attempts; "
                           f"{len(board.lengths) - len(accepted)} words left).")
                self._draw_path(path, stop)
                final = len(accepted) == len(board.lengths) - 1
                observed = self._wait_for_word(expected, path, stop, final=final)
                if isinstance(observed, bool):
                    if not observed:
                        raise BrowserSessionError("Wend result page did not confirm a win")
                    if progress is not None:
                        progress(len(board.lengths), len(board.lengths))
                    return True
                if observed is None:
                    rejected.add(path)
                    self._undo_trial(expected, stop)
                    break
                accepted.add(path)
                expected = observed
                if progress is not None:
                    progress(len(accepted), len(board.lengths))
                if len(accepted) == len(board.lengths):
                    return self._wait_for_win(expected, stop)
        raise BrowserSessionError(f"no verified Wend solution after {attempted} word attempts; "
                                  "the dictionary may be incomplete")

    def _wait_for_word(
        self, expected: Snapshot, path: tuple[int, ...], stop: Event | None, *, final: bool,
    ) -> Snapshot | bool | None:
        word = "".join(expected.board.letters[cell] for cell in path)
        words = Counter(w for w in expected.words if w)
        words[word] += 1
        target_locked = expected.locked | frozenset(path)
        started = monotonic()
        deadline = started + STATE_TIMEOUT
        while True:
            self._check_page(stop, allow_result=final)
            if final and _is_result_page(self.page.url):
                return self._wait_for_win(None, stop)
            try:
                observed = self._snapshot()
            except BrowserSessionError as error:
                if final and _is_result_page(self.page.url):
                    return self._wait_for_win(None, stop)
                if (final and isinstance(error.__cause__, PlaywrightError)
                        and "Execution context was destroyed" in str(error.__cause__)
                        and monotonic() < deadline):
                    self.page.wait_for_timeout(POLL_INTERVAL_MS)
                    continue
                raise
            if (observed.board == expected.board and observed.locked == target_locked
                    and Counter(w for w in observed.words if w) == words):
                return observed
            if (monotonic() - started >= REJECTION_DELAY and observed.board == expected.board
                    and observed.locked == expected.locked
                    and Counter(w for w in observed.words if w) == words):
                return None
            if monotonic() >= deadline:
                raise BrowserSessionError(f"unexpected Wend board state after drawing {word}")
            self.page.wait_for_timeout(POLL_INTERVAL_MS)

    def _undo_trial(self, expected: Snapshot, stop: Event | None) -> None:
        self._check_page(stop)
        try:
            self.page.get_by_role("button", name="Undo", exact=True).click(timeout=2000)
        except PlaywrightError as error:
            raise BrowserSessionError(f"could not undo the rejected Wend word: {error}") from error
        deadline = monotonic() + STATE_TIMEOUT
        while True:
            self._check_page(stop)
            if self._snapshot() == expected:
                return
            if monotonic() >= deadline:
                raise BrowserSessionError("timed out waiting for the rejected Wend word to be undone")
            self.page.wait_for_timeout(POLL_INTERVAL_MS)

    def _draw_path(self, path: tuple[int, ...], stop: Event | None) -> None:
        try:
            boxes = [self.page.locator(f'{GRID} [data-cell-idx="{cell}"]').bounding_box(timeout=2000)
                     for cell in path]
            if any(box is None for box in boxes):
                raise BrowserSessionError("Wend path cells are not visible")
            points = [(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
                      for box in boxes if box is not None]
            self._check_page(stop)
            self.page.mouse.move(*points[0])
            self.page.mouse.down()
            try:
                for point in points[1:]:
                    self._check_page(stop)
                    self.page.mouse.move(*point, steps=4)
            finally:
                self.page.mouse.up()
        except PlaywrightError as error:
            raise BrowserSessionError(f"could not draw Wend word: {error}") from error
