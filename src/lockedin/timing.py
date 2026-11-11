"""Read a game's displayed timer and hold its final input."""

from __future__ import annotations

import re
from time import monotonic
from typing import Any, Callable

from playwright.sync_api import Error as PlaywrightError

from .browser import BrowserSessionError

TIMER_SCRIPT = r"""
() => [...document.querySelectorAll('body *')].filter(e => {
  if (e.children.length || !/^\d+:\d{2}(?::\d{2})?$/.test(e.textContent.trim())) return false;
  const style = getComputedStyle(e), rect = e.getBoundingClientRect();
  return style.visibility === 'visible' && style.display !== 'none'
    && rect.width >= 10 && rect.height >= 8 && !e.closest('[aria-hidden="true"]');
}).map(e => e.textContent.trim())
"""
TIMER_STALL_TIMEOUT = 15.0
POLL_INTERVAL_MS = 100


class TimerUnavailable(BrowserSessionError):
    """The game has no visible timer."""


def read_game_time(frame: Any) -> int:
    try:
        values = frame.evaluate(TIMER_SCRIPT)
    except PlaywrightError as error:
        raise BrowserSessionError(f"could not read the game timer: {error}") from error
    if not isinstance(values, list):
        raise BrowserSessionError("unrecognized game timer response")
    if not values:
        raise TimerUnavailable("the game timer is not visible")
    if len(values) != 1 or not isinstance(values[0], str):
        raise BrowserSessionError("game timer is ambiguous")
    text = values[0]
    if not re.fullmatch(r"\d+:\d{2}(?::\d{2})?", text):
        raise BrowserSessionError("unrecognized game timer")
    parts = [int(part) for part in text.split(":")]
    if parts[-1] >= 60 or (len(parts) == 3 and parts[1] >= 60):
        raise BrowserSessionError("invalid game timer")
    return parts[-1] + 60 * parts[-2] + (3600 * parts[0] if len(parts) == 3 else 0)


def prepare_timer(
    frame: Any, target: int, *, allow_missing: bool = False,
    status: Callable[[str], None] | None = None,
) -> bool:
    if type(target) is not int or target < 0:
        raise ValueError("time must be a non-negative whole number of seconds")
    if target == 0:
        return False
    try:
        read_game_time(frame)
    except TimerUnavailable:
        if not allow_missing:
            raise
        if status is not None:
            status("No timer in signed-out Mini Sudoku; completing without a time target.")
        return False
    return True


def wait_for_game_time(
    page: Any, frame: Any, target: int, check: Callable[[], None],
    *, status: Callable[[str], None] | None = None,
) -> None:
    check()
    current = read_game_time(frame)
    last_change = monotonic()
    if current < target and status is not None:
        status(f"Waiting for the game timer to reach {target} seconds before the final move.")
    while current < target:
        check()
        try:
            page.wait_for_timeout(POLL_INTERVAL_MS)
        except PlaywrightError as error:
            raise BrowserSessionError(f"could not wait for the game timer: {error}") from error
        check()
        observed = read_game_time(frame)
        if observed < current:
            raise BrowserSessionError("the game timer moved backwards; the board may have been reset")
        if observed > current:
            current = observed
            last_change = monotonic()
        elif monotonic() - last_change >= TIMER_STALL_TIMEOUT:
            raise BrowserSessionError("the game timer is not advancing; final move was not made")
    check()
