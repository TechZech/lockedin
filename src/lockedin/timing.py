"""Read a game's displayed timer and hold its final input."""

from __future__ import annotations

import re
from dataclasses import dataclass
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


@dataclass(slots=True)
class GameTimer:
    target: int
    observed: int
    observed_at: float
    estimated: bool = False


def _report_estimate(status: Callable[[str], None] | None) -> None:
    message = "Game timer unavailable; using an estimated timer for the final move."
    if status is not None:
        status(message)
    else:
        print(message, flush=True)


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
    frame: Any, target: int, *, started_at: float | None = None,
    status: Callable[[str], None] | None = None,
) -> GameTimer | None:
    if type(target) is not int or target < 0:
        raise ValueError("time must be a non-negative whole number of seconds")
    if target == 0:
        return None
    try:
        current = read_game_time(frame)
    except TimerUnavailable:
        _report_estimate(status)
        return GameTimer(target, 0, monotonic() if started_at is None else started_at, estimated=True)
    return GameTimer(target, current, monotonic())


def wait_for_game_time(
    page: Any, frame: Any, target: int, check: Callable[[], None],
    *, timer: GameTimer | None = None, status: Callable[[str], None] | None = None,
) -> None:
    check()
    if timer is None:
        timer = prepare_timer(frame, target, status=status)
        if timer is None:
            return
    if timer.target != target:
        raise ValueError("timer target does not match the requested time")
    reported_wait = False
    while True:
        check()
        now = monotonic()
        if timer.estimated:
            current = timer.observed + now - timer.observed_at
        else:
            try:
                observed = read_game_time(frame)
            except TimerUnavailable:
                timer.estimated = True
                _report_estimate(status)
                current = timer.observed + now - timer.observed_at
            else:
                if observed < timer.observed:
                    raise BrowserSessionError("the game timer moved backwards; the board may have been reset")
                if observed > timer.observed:
                    timer.observed = observed
                    timer.observed_at = now
                elif observed < target and now - timer.observed_at >= TIMER_STALL_TIMEOUT:
                    raise BrowserSessionError("the game timer is not advancing; final move was not made")
                current = observed
        if current >= target:
            break
        if not reported_wait and status is not None:
            source = "estimated timer" if timer.estimated else "game timer"
            status(f"Waiting for the {source} to reach {target} seconds before the final move.")
            reported_wait = True
        try:
            page.wait_for_timeout(POLL_INTERVAL_MS)
        except PlaywrightError as error:
            raise BrowserSessionError(f"could not wait for the game timer: {error}") from error
    check()
