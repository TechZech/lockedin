"""A small desktop interface for the game-solving pipelines."""

from __future__ import annotations

import queue
import sys
import threading
import traceback
from pathlib import Path
from typing import Callable, Generic, Protocol, TypeVar

from .browser import BrowserSessionError
from .tango.browser import TangoBrowserSession
from .tango.workflow import solve_and_report
from .mini_sudoku.browser import MiniSudokuBrowserSession
from .mini_sudoku.workflow import solve_and_report as solve_sudoku_and_report

PROFILE = Path.home() / ".lockedin" / "chromium-profile"
SUDOKU_PROFILE = Path.home() / ".lockedin" / "sudoku-chromium-profile"


Progress = Callable[[int, int], None]


class GameSession(Protocol):
    def wait_for_board(self, stop: threading.Event) -> None: ...
    def keep_alive(self) -> None: ...
    def close(self) -> None: ...


SessionT = TypeVar("SessionT", bound=GameSession)


class GameAdapter(Protocol[SessionT]):
    name: str

    def launch(self, profile: Path, test: bool) -> SessionT: ...
    def open(self, session: SessionT, test: bool, stop: threading.Event) -> None: ...
    def solve(self, session: SessionT, stop: threading.Event, progress: Progress,
              on_start: Callable[[], None]) -> None: ...


class TangoAdapter:
    name = "Tango"

    def launch(self, profile: Path, test: bool) -> TangoBrowserSession:
        return (TangoBrowserSession.launch_temporary() if test
                else TangoBrowserSession.launch_persistent(profile))

    def open(self, session: TangoBrowserSession, test: bool, stop: threading.Event) -> None:
        if test:
            session.open_tango()
        else:
            session.open_logged_in_tango(stop)

    def solve(self, session: TangoBrowserSession, stop: threading.Event, progress: Progress,
              on_start: Callable[[], None]) -> None:
        plan = solve_and_report(session)
        on_start()
        session.execute_actions(plan, stop=stop, progress=progress)


class MiniSudokuAdapter:
    name = "Mini Sudoku"

    def launch(self, profile: Path, test: bool) -> MiniSudokuBrowserSession:
        return (MiniSudokuBrowserSession.launch_temporary() if test
                else MiniSudokuBrowserSession.launch_persistent(profile))

    def open(self, session: MiniSudokuBrowserSession, test: bool, stop: threading.Event) -> None:
        if test:
            session.open_sudoku()
        else:
            session.open_logged_in_sudoku(stop)

    def solve(self, session: MiniSudokuBrowserSession, stop: threading.Event, progress: Progress,
              on_start: Callable[[], None]) -> None:
        plan = solve_sudoku_and_report(session)
        on_start()
        session.execute_actions(plan, stop=stop, progress=progress)


class GameWorker(Generic[SessionT]):
    """Keep Playwright and its browser on one background thread."""

    def __init__(self, adapter: GameAdapter[SessionT], profile: Path, test: bool = False) -> None:
        self.adapter = adapter
        self.profile = profile
        self.test = test
        self.messages: queue.Queue[tuple[str, str]] = queue.Queue()
        self.requests: queue.Queue[None] = queue.Queue()
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self._run, name=f"{adapter.name.lower()}-browser")

    def start(self) -> None:
        self.requests.put(None)
        self.thread.start()

    def request_solve(self) -> None:
        self.requests.put(None)

    def _run(self) -> None:
        session = None
        try:
            if self.test:
                self.messages.put(("status", "Opening a signed-out test browser..."))
            else:
                self.messages.put(("status", "Opening the LinkedIn browser..."))
            session = self.adapter.launch(self.profile, self.test)
            while not self.stop.is_set():
                try:
                    self.requests.get_nowait()
                except queue.Empty:
                    session.keep_alive()
                    continue
                try:
                    if self.test:
                        self.adapter.open(session, True, self.stop)
                        self.messages.put(("status", f"Test mode: start {self.adapter.name} in the browser."))
                    else:
                        self.messages.put(("status", "Sign in to LinkedIn in the browser; complete any verification."))
                        self.adapter.open(session, False, self.stop)
                        self.messages.put(("status", f"Signed in. Start {self.adapter.name} in the browser."))
                    session.wait_for_board(self.stop)
                    if self.stop.is_set():
                        break
                    self.messages.put(("status", "Reading and solving the board..."))
                    if self.test:
                        start_message = "Test mode: clicking the board..."
                        progress_prefix = "Test mode"
                        ready_message = "Test board matches the solution; game completion was not verified."
                    else:
                        start_message = "Clicking the signed-in game board..."
                        progress_prefix = "Signed-in game"
                        ready_message = "Board matches the solution; game completion was not verified."
                    def report_progress(done: int, total: int) -> None:
                        self.messages.put(("status", f"{progress_prefix}: filled {done}/{total} cells."))
                    self.adapter.solve(
                        session, self.stop, report_progress,
                        lambda: self.messages.put(("status", start_message)),
                    )
                    self.messages.put(("ready", ready_message))
                except (BrowserSessionError, ValueError) as error:
                    if not self.stop.is_set():
                        print(f"error: {error}", file=sys.stderr, flush=True)
                        suffix = (
                            " The test board may be partially filled; retry to re-read it."
                            if self.test
                            else " The game board may be partially filled; retry to re-read it."
                        )
                        self.messages.put(("ready", f"Could not solve: {error}.{suffix}"))
        except Exception as error:
            if not self.stop.is_set():
                traceback.print_exc()
                self.messages.put(("error", f"Browser error: {error}"))
        finally:
            try:
                if session is not None:
                    session.close()
            except Exception:
                traceback.print_exc()
            self.messages.put(("stopped", ""))


class TangoWorker(GameWorker[TangoBrowserSession]):
    def __init__(self, profile: Path = PROFILE, test: bool = False) -> None:
        super().__init__(TangoAdapter(), profile, test)


class MiniSudokuWorker(GameWorker[MiniSudokuBrowserSession]):
    def __init__(self, profile: Path = SUDOKU_PROFILE, test: bool = False) -> None:
        super().__init__(MiniSudokuAdapter(), profile, test)


def main() -> int:
    try:
        import tkinter as tk
        from tkinter import ttk
    except ImportError as error:
        print(
            f"error: Tkinter is required for the desktop UI ({error}). "
            "Install Tk support for your Python interpreter.",
            file=sys.stderr,
        )
        return 1

    try:
        root = tk.Tk()
    except tk.TclError as error:
        print(f"error: could not open the desktop window: {error}", file=sys.stderr)
        return 1
    root.title("LockedIn")
    root.resizable(False, False)
    frame = ttk.Frame(root, padding=24)
    frame.grid()
    ttk.Label(frame, text="LinkedIn game solvers", font=("Helvetica", 18, "bold")).grid(pady=(0, 12))
    status = tk.StringVar(value="Solve today's game, or use the test button for a signed-out practice board.")
    ttk.Label(frame, textvariable=status, wraplength=380).grid(pady=(0, 12))
    workers: dict[tuple[str, bool], TangoWorker | MiniSudokuWorker] = {}
    buttons: dict[tuple[str, bool], ttk.Button] = {}
    worker_types = {"Tango": TangoWorker, "Mini Sudoku": MiniSudokuWorker}
    closing = False

    def solve(game: str, test: bool) -> None:
        key = (game, test)
        buttons[key].configure(state="disabled")
        worker = workers.get(key)
        if worker is None or not worker.thread.is_alive():
            worker = workers[key] = worker_types[game](test=test)
            worker.start()
        else:
            worker.request_solve()
        status.set(f"Opening {game}{' test' if test else ''}...")

    for game in worker_types:
        for test in (False, True):
            key = (game, test)
            buttons[key] = ttk.Button(frame, text=f"Solve {game}{' Test' if test else ''}",
                                      command=lambda game=game, test=test: solve(game, test))
            buttons[key].grid(pady=(8, 0))
    ttk.Label(
        frame,
        text="Solve plays your signed-in game. Test uses a separate signed-out browser.",
        wraplength=380,
        padding=(0, 12, 0, 0),
    ).grid()

    def poll() -> None:
        for key, worker in workers.items():
            while True:
                try:
                    kind, message = worker.messages.get_nowait()
                except queue.Empty:
                    break
                if message and not closing:
                    status.set(message)
                if kind == "ready" and not closing:
                    buttons[key].configure(state="normal")
            if not worker.thread.is_alive() and not closing:
                buttons[key].configure(state="normal")
        if closing and not any(worker.thread.is_alive() for worker in workers.values()):
            root.destroy()
            return
        root.after(100, poll)

    def close() -> None:
        nonlocal closing
        closing = True
        for button in buttons.values():
            button.configure(state="disabled")
        status.set("Closing browsers...")
        for worker in workers.values():
            worker.stop.set()

    root.protocol("WM_DELETE_WINDOW", close)
    root.after(100, poll)
    root.mainloop()
    return 0
