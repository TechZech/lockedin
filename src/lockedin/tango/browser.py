"""Browser-session adapter for interacting with a logged-in Tango page."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from threading import Event
from time import monotonic, time
from typing import Any, Callable, Protocol
from urllib.parse import urlsplit

from playwright.sync_api import Error as PlaywrightError

from .actions import ActionPlan, create_action_plan
from .dom import SNAPSHOT_SCRIPT, board_from_json
from .model import BOARD_SIZE, Board, Cell
from .solver import Solver
from .workflow import plan_board

TANGO_URL = "https://www.linkedin.com/games/tango/"
FEED_URL = "https://www.linkedin.com/feed/"
GRID_CELLS = '[data-testid="interactive-grid"] [data-testid^="cell-"][data-cell-idx]'
CLICK_TIMEOUT_MS = 2000
STATE_TIMEOUT = 2.0
POLL_INTERVAL_MS = 50


class BrowserPage(Protocol):
    url: str

    def evaluate(self, expression: str) -> Any: ...

    def goto(self, url: str, *, wait_until: str) -> Any: ...

    def is_closed(self) -> bool: ...

    def locator(self, selector: str) -> Any: ...

    def wait_for_timeout(self, timeout: float) -> None: ...


class BrowserSessionError(RuntimeError):
    """Raised when a usable Tango browser page cannot be found."""


@dataclass(slots=True)
class TangoBrowserSession:
    """Own a connection to an existing, logged-in Chromium browser."""

    page: BrowserPage
    _playwright: Any = None
    _browser: Any = None
    _context: Any = None
    require_login: bool = True
    _owns_browser: bool = False

    @classmethod
    def launch_temporary(cls) -> TangoBrowserSession:
        """Open a throwaway, signed-out browser so test runs never touch the live profile."""
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as error:
            raise BrowserSessionError("install Playwright before opening the browser") from error

        playwright = sync_playwright().start()
        browser = None
        try:
            browser = playwright.chromium.launch(headless=False)
            context = browser.new_context()
            page = context.new_page()
            return cls(
                page=page,
                _playwright=playwright,
                _browser=browser,
                _context=context,
                require_login=False,
                _owns_browser=True,
            )
        except Exception as error:
            if browser is not None:
                browser.close()
            playwright.stop()
            raise BrowserSessionError(
                f"could not open the test browser: {error}. "
                "Make sure Chromium is installed with 'python -m playwright install chromium'."
            ) from error

    def open_tango(self) -> None:
        """Go straight to the game without requiring a LinkedIn login."""
        try:
            self.page.goto(TANGO_URL, wait_until="domcontentloaded")
        except Exception as error:
            raise BrowserSessionError(f"could not open Tango: {error}") from error

    @classmethod
    def launch_persistent(cls, profile: Path) -> TangoBrowserSession:
        """Open a separate, persistent Chromium profile."""
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as error:
            raise BrowserSessionError("install Playwright before opening the browser") from error

        profile.mkdir(mode=0o700, parents=True, exist_ok=True)
        playwright = sync_playwright().start()
        context = None
        try:
            context = playwright.chromium.launch_persistent_context(str(profile), headless=False)
            page = context.pages[0] if context.pages else context.new_page()
            return cls(page=page, _playwright=playwright, _context=context)
        except Exception as error:
            if context is not None:
                context.close()
            playwright.stop()
            raise BrowserSessionError(
                f"could not open the Tango browser: {error}. "
                "Make sure Chromium is installed with 'python -m playwright install chromium'."
            ) from error

    def open_logged_in_tango(self, stop: Event, timeout: float = 300) -> None:
        """Require a LinkedIn login before navigating to the Tango game."""
        if self._context is None:
            raise BrowserSessionError("a dedicated browser context is required for sign-in")
        if stop.is_set():
            raise BrowserSessionError("the solve was cancelled")
        try:
            self.page.goto(FEED_URL, wait_until="domcontentloaded")
            deadline = monotonic() + timeout
            while not stop.is_set():
                if self.page.is_closed():
                    raise BrowserSessionError("the browser was closed during sign-in")
                url = urlsplit(self.page.url)
                if (
                    url.scheme == "https"
                    and url.hostname in ("linkedin.com", "www.linkedin.com")
                    and url.path.rstrip("/") == "/feed"
                    and self._has_login_cookie()
                ):
                    if stop.is_set():
                        break
                    self.page.goto(TANGO_URL, wait_until="domcontentloaded")
                    return
                if monotonic() >= deadline:
                    raise BrowserSessionError(
                        "timed out waiting for LinkedIn sign-in; sign in and complete any verification, then try again"
                    )
                self.page.wait_for_timeout(250)
        except BrowserSessionError:
            raise
        except Exception as error:
            raise BrowserSessionError(f"could not open LinkedIn or Tango: {error}") from error
        raise BrowserSessionError("the solve was cancelled")

    def _has_login_cookie(self) -> bool:
        return any(
            cookie["name"] == "li_at"
            and (cookie["expires"] == -1 or cookie["expires"] > time())
            for cookie in self._context.cookies("https://www.linkedin.com")
        )

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
                if self.require_login and self._context is not None and not self._has_login_cookie():
                    raise BrowserSessionError("LinkedIn sign-in expired; please try again")
                return
            if monotonic() >= deadline:
                raise BrowserSessionError("timed out waiting for the Tango board; sign in and start the game")
            self.page.wait_for_timeout(250)
        raise BrowserSessionError("the solve was cancelled")

    def keep_alive(self) -> None:
        """Allow Playwright to process browser events while waiting for another request."""
        if self.page.is_closed():
            raise BrowserSessionError("the Tango browser was closed")
        self.page.wait_for_timeout(200)

    @classmethod
    def connect_over_cdp(
        cls,
        cdp_url: str = "http://127.0.0.1:9222",
        page_url_contains: str = "linkedin.com",
    ) -> TangoBrowserSession:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as error:
            raise BrowserSessionError("install Playwright before connecting to a browser") from error

        playwright = sync_playwright().start()
        try:
            browser = playwright.chromium.connect_over_cdp(cdp_url)
            pages = [page for context in browser.contexts for page in context.pages]
            page = next((page for page in pages if page_url_contains in page.url), None)
            if page is None:
                raise BrowserSessionError("no matching LinkedIn page found in the browser")
            return cls(page=page, _playwright=playwright, _browser=browser)
        except BrowserSessionError:
            playwright.stop()
            raise
        except Exception as error:
            playwright.stop()
            raise BrowserSessionError(f"could not connect to browser at {cdp_url}") from error

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

        for completed, action in enumerate(plan.actions, start=1):
            position = divmod(action.index, BOARD_SIZE)
            selector = f'{GRID_CELLS}[data-cell-idx="{action.index}"]'
            for _ in range(action.clicks):
                self._check_execution_page(stop)
                self._require_board(expected, f"board changed before cell {action.index}")
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

    def close(self) -> None:
        try:
            if self._context is not None:
                self._context.close()
            if self._owns_browser and self._browser is not None:
                self._browser.close()
        finally:
            if self._playwright is not None:
                self._playwright.stop()