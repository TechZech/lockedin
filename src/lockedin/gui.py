"""A small desktop interface for the Tango pipeline."""

from __future__ import annotations

import queue
import sys
import threading
import traceback
from pathlib import Path

from .tango.browser import BrowserSessionError, TangoBrowserSession
from .tango.workflow import solve_and_report

PROFILE = Path.home() / ".lockedin" / "chromium-profile"


class TangoWorker:
    """Keep Playwright and its browser on one background thread."""

    def __init__(self, profile: Path = PROFILE, test: bool = False) -> None:
        self.profile = profile
        self.test = test
        self.messages: queue.Queue[tuple[str, str]] = queue.Queue()
        self.requests: queue.Queue[None] = queue.Queue()
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self._run, name="tango-browser")

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
                session = TangoBrowserSession.launch_temporary()
            else:
                self.messages.put(("status", "Opening the LinkedIn browser..."))
                session = TangoBrowserSession.launch_persistent(self.profile)
            while not self.stop.is_set():
                try:
                    self.requests.get_nowait()
                except queue.Empty:
                    session.keep_alive()
                    continue
                try:
                    if self.test:
                        session.open_tango()
                        self.messages.put(("status", "Test mode: start Tango in the browser."))
                    else:
                        self.messages.put(("status", "Sign in to LinkedIn in the browser; complete any verification."))
                        session.open_logged_in_tango(self.stop)
                        self.messages.put(("status", "Signed in. Start Tango in the browser."))
                    session.wait_for_board(self.stop)
                    if self.stop.is_set():
                        break
                    self.messages.put(("status", "Reading and solving the board..."))
                    plan = solve_and_report(session)
                    if self.test:
                        start_message = "Test mode: clicking the board..."
                        progress_prefix = "Test mode"
                        ready_message = "Test board matches the solution; game completion was not verified."
                    else:
                        start_message = "Clicking the signed-in game board..."
                        progress_prefix = "Signed-in game"
                        ready_message = "Board matches the solution; game completion was not verified."
                    self.messages.put(("status", start_message))
                    session.execute_actions(
                        plan,
                        stop=self.stop,
                        progress=lambda done, total: self.messages.put(
                            ("status", f"{progress_prefix}: filled {done}/{total} cells.")
                        ),
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
    ttk.Label(frame, text="Tango solver", font=("Helvetica", 18, "bold")).grid(pady=(0, 12))
    status = tk.StringVar(value="Solve today's game, or use the test button for a signed-out practice board.")
    ttk.Label(frame, textvariable=status, wraplength=380).grid(pady=(0, 12))
    workers: dict[bool, TangoWorker] = {}
    buttons: dict[bool, ttk.Button] = {}
    closing = False

    def solve(test: bool) -> None:
        buttons[test].configure(state="disabled")
        worker = workers.get(test)
        if worker is None or not worker.thread.is_alive():
            worker = workers[test] = TangoWorker(test=test)
            worker.start()
        else:
            worker.request_solve()
        status.set("Opening Tango test..." if test else "Opening Tango...")

    buttons[False] = ttk.Button(frame, text="Solve Tango", command=lambda: solve(False))
    buttons[False].grid()
    buttons[True] = ttk.Button(frame, text="Solve Tango Test", command=lambda: solve(True))
    buttons[True].grid(pady=(8, 0))
    ttk.Label(
        frame,
        text="Solve Tango plays your signed-in game. Test uses a separate signed-out browser.",
        wraplength=380,
        padding=(0, 12, 0, 0),
    ).grid()

    def poll() -> None:
        for test, worker in workers.items():
            while True:
                try:
                    kind, message = worker.messages.get_nowait()
                except queue.Empty:
                    break
                if message and not closing:
                    status.set(message)
                if kind == "ready" and not closing:
                    buttons[test].configure(state="normal")
            if not worker.thread.is_alive() and not closing:
                buttons[test].configure(state="normal")
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
