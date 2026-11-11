"""Shared LinkedIn browser lifecycle and sign-in handling."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from threading import Event
from time import monotonic, time
from typing import Any, Protocol, Self
from urllib.parse import urlsplit

FEED_URL = "https://www.linkedin.com/feed/"


class BrowserPage(Protocol):
    url: str
    frames: list[Any]

    def evaluate(self, expression: str) -> Any: ...
    def goto(self, url: str, *, wait_until: str) -> Any: ...
    def is_closed(self) -> bool: ...
    def locator(self, selector: str) -> Any: ...
    def wait_for_timeout(self, timeout: float) -> None: ...


class BrowserSessionError(RuntimeError):
    """Raised when a usable browser session cannot be obtained."""


@dataclass(slots=True)
class BrowserSession:
    page: BrowserPage
    _playwright: Any = None
    _browser: Any = None
    _context: Any = None
    require_login: bool = True
    _owns_browser: bool = False

    @classmethod
    def launch_temporary(cls) -> Self:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as error:
            raise BrowserSessionError("install Playwright before opening the browser") from error
        playwright = sync_playwright().start()
        browser = None
        try:
            browser = playwright.chromium.launch(headless=False)
            context = browser.new_context()
            return cls(page=context.new_page(), _playwright=playwright, _browser=browser,
                       _context=context, require_login=False, _owns_browser=True)
        except Exception as error:
            if browser is not None:
                browser.close()
            playwright.stop()
            raise BrowserSessionError(
                f"could not open the test browser: {error}. "
                "Make sure Chromium is installed with 'python -m playwright install chromium'."
            ) from error

    @classmethod
    def launch_persistent(cls, profile: Path) -> Self:
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
                f"could not open the browser: {error}. "
                "Make sure Chromium is installed with 'python -m playwright install chromium'."
            ) from error

    @classmethod
    def connect_over_cdp(
        cls, cdp_url: str = "http://127.0.0.1:9222", page_url_contains: str = "linkedin.com"
    ) -> Self:
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

    def open_game(self, url: str, name: str) -> None:
        try:
            self.page.goto(url, wait_until="domcontentloaded")
        except Exception as error:
            raise BrowserSessionError(f"could not open {name}: {error}") from error

    def open_logged_in_game(self, url: str, name: str, stop: Event, timeout: float = 300) -> None:
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
                current = urlsplit(self.page.url)
                if (current.scheme == "https"
                        and current.hostname in ("linkedin.com", "www.linkedin.com")
                        and current.path.rstrip("/") == "/feed" and self.has_login_cookie()):
                    if stop.is_set():
                        break
                    self.page.goto(url, wait_until="domcontentloaded")
                    return
                if monotonic() >= deadline:
                    raise BrowserSessionError(
                        "timed out waiting for LinkedIn sign-in; sign in and complete any verification, then try again"
                    )
                self.page.wait_for_timeout(250)
        except BrowserSessionError:
            raise
        except Exception as error:
            raise BrowserSessionError(f"could not open LinkedIn or {name}: {error}") from error
        raise BrowserSessionError("the solve was cancelled")

    def has_login_cookie(self) -> bool:
        if self._context is None:
            return False
        return any(
            cookie["name"] == "li_at"
            and (cookie["expires"] == -1 or cookie["expires"] > time())
            for cookie in self._context.cookies("https://www.linkedin.com")
        )

    def check_login(self) -> None:
        if self.require_login and self._context is not None and not self.has_login_cookie():
            raise BrowserSessionError("LinkedIn sign-in expired; please try again")

    def keep_alive(self) -> None:
        if self.page.is_closed():
            raise BrowserSessionError("the browser was closed")
        self.page.wait_for_timeout(200)

    def close(self) -> None:
        try:
            if self._context is not None:
                self._context.close()
            if self._owns_browser and self._browser is not None:
                self._browser.close()
        finally:
            if self._playwright is not None:
                self._playwright.stop()
