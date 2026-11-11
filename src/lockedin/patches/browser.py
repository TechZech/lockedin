"""Verified browser interaction for LinkedIn Patches."""

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
from .model import Board, Patch
from .workflow import plan_board

PATCHES_URL = "https://www.linkedin.com/games/patches/"
GRID = '[data-testid="interactive-grid"][data-trail-grid]'
STATE_TIMEOUT = 2.0
POLL_INTERVAL_MS = 50


class PatchesBrowserSession(BrowserSession):
    def open_patches(self) -> None:
        self.open_game(PATCHES_URL, "Patches")

    def open_logged_in_patches(self, stop: Event, timeout: float = 300) -> None:
        self.open_logged_in_game(PATCHES_URL, "Patches", stop, timeout)

    def _check_page(self, stop: Event | None = None) -> None:
        if stop is not None and stop.is_set():
            raise BrowserSessionError("the solve was cancelled; the board may be partially filled")
        if self.page.is_closed():
            raise BrowserSessionError("the Patches browser was closed")
        url = urlsplit(self.page.url)
        if (url.scheme != "https" or url.hostname not in ("linkedin.com", "www.linkedin.com")
                or url.path.rstrip("/") != "/games/patches"):
            raise BrowserSessionError("the browser is no longer on the Patches page")
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
                raise BrowserSessionError("timed out waiting for the Patches board; start the game")
            self.page.wait_for_timeout(250)
        raise BrowserSessionError("the solve was cancelled")

    def snapshot_board(self) -> Board:
        try:
            board = board_from_json(self.page.evaluate(SNAPSHOT_SCRIPT))
            self.board_started_at()
            return board
        except (PlaywrightError, ValueError) as error:
            raise BrowserSessionError(f"could not read a Patches board: {error}") from error

    def plan_solution(self) -> ActionPlan:
        return plan_board(self.snapshot_board())

    def execute_actions(
        self, plan: ActionPlan, *, stop: Event | None = None,
        progress: Callable[[int, int], None] | None = None,
        target_seconds: int = 0, status: Callable[[str], None] | None = None,
    ) -> None:
        try:
            if create_action_plan(plan.current, plan.solved) != plan:
                raise BrowserSessionError("action plan does not match the solution")
        except ValueError as error:
            raise BrowserSessionError(f"invalid action plan: {error}") from error
        self._check_page(stop)
        expected = plan.current.with_patches(plan.current.patches)
        self._require_board(expected, "board changed since the plan was created")
        timer = (prepare_timer(self.page, target_seconds, started_at=self.board_started_at(), status=status)
                 if plan.actions else None)
        for done, patch in enumerate(plan.actions, 1):
            self._check_page(stop)
            self._require_board(expected, "board changed before the next patch")
            if timer and done == len(plan.actions):
                def check() -> None:
                    self._check_page(stop)
                    self._require_board(expected, "board changed while waiting for the game timer")
                wait_for_game_time(self.page, self.page, target_seconds, check, timer=timer, status=status)
            self._draw_patch(patch, plan.current.columns)
            after = expected.with_patches(expected.patches + (patch,))
            deadline = monotonic() + STATE_TIMEOUT
            while True:
                self._check_page(stop)
                observed = self.snapshot_board()
                if observed == after:
                    break
                if observed != expected:
                    raise BrowserSessionError(f"unexpected board change after drawing {patch}")
                if monotonic() >= deadline:
                    raise BrowserSessionError(f"timed out waiting for patch {patch}")
                try:
                    self.page.wait_for_timeout(POLL_INTERVAL_MS)
                except PlaywrightError as error:
                    raise BrowserSessionError(f"could not verify patch {patch}: {error}") from error
            expected = after
            if progress is not None:
                progress(done, len(plan.actions))
        self._check_page(stop)
        self._require_board(plan.solved.with_patches(plan.solved.patches), "final board does not match the solution")

    def _require_board(self, expected: Board, message: str) -> None:
        if self.snapshot_board() != expected:
            raise BrowserSessionError(message)

    def _draw_patch(self, patch: Patch, columns: int) -> None:
        start, end = patch.top * columns + patch.left, patch.bottom * columns + patch.right
        try:
            first = self.page.locator(f'{GRID} [data-cell-idx="{start}"]').bounding_box(timeout=2000)
            last = self.page.locator(f'{GRID} [data-cell-idx="{end}"]').bounding_box(timeout=2000)
            if first is None or last is None:
                raise BrowserSessionError("patch cells are not visible")
            self.page.mouse.move(first["x"] + first["width"] / 2, first["y"] + first["height"] / 2)
            self.page.mouse.down()
            try:
                self.page.mouse.move(last["x"] + last["width"] / 2, last["y"] + last["height"] / 2, steps=8)
            finally:
                self.page.mouse.up()
        except PlaywrightError as error:
            raise BrowserSessionError(f"could not draw patch {patch}: {error}") from error
