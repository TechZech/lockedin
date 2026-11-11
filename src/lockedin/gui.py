"""A small desktop interface for the game-solving pipelines."""

from __future__ import annotations

import queue
import sys
import threading
import traceback
from pathlib import Path
from typing import Callable, Generic, Protocol, TypeVar

from playwright.sync_api import Error as PlaywrightError

from .browser import BrowserPage, BrowserSessionError
from .tango.browser import TangoBrowserSession
from .tango.workflow import solve_and_report
from .mini_sudoku.browser import MiniSudokuBrowserSession
from .mini_sudoku.workflow import solve_and_report as solve_sudoku_and_report
from .zip.browser import ZipBrowserSession
from .zip.workflow import solve_and_report as solve_zip_and_report
from .queens.browser import QueensBrowserSession
from .queens.workflow import solve_and_report as solve_queens_and_report
from .patches.browser import PatchesBrowserSession
from .patches.workflow import solve_and_report as solve_patches_and_report
from .wend.browser import WendBrowserSession

PROFILE = Path.home() / ".lockedin" / "chromium-profile"
SUDOKU_PROFILE = Path.home() / ".lockedin" / "sudoku-chromium-profile"
ZIP_PROFILE = Path.home() / ".lockedin" / "zip-chromium-profile"
QUEENS_PROFILE = Path.home() / ".lockedin" / "queens-chromium-profile"
PATCHES_PROFILE = Path.home() / ".lockedin" / "patches-chromium-profile"
WEND_PROFILE = Path.home() / ".lockedin" / "wend-chromium-profile"


Progress = Callable[[int, int], None]


class GameSession(Protocol):
    page: BrowserPage

    def wait_for_board(self, stop: threading.Event) -> None: ...
    def keep_alive(self) -> None: ...
    def close(self) -> None: ...


SessionT = TypeVar("SessionT", bound=GameSession)


class GameAdapter(Protocol[SessionT]):
    name: str

    def launch(self, profile: Path, test: bool) -> SessionT: ...
    def open(self, session: SessionT, test: bool, stop: threading.Event) -> None: ...
    def solve(self, session: SessionT, stop: threading.Event, progress: Progress,
              on_start: Callable[[], None], target_seconds: int, test: bool,
              status: Callable[[str], None]) -> bool | None: ...


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
              on_start: Callable[[], None], target_seconds: int, _test: bool,
              status: Callable[[str], None]) -> None:
        plan = solve_and_report(session)
        on_start()
        session.execute_actions(plan, stop=stop, progress=progress, target_seconds=target_seconds,
                                status=status)


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
              on_start: Callable[[], None], target_seconds: int, _test: bool,
              status: Callable[[str], None]) -> None:
        plan = solve_sudoku_and_report(session)
        on_start()
        session.execute_actions(plan, stop=stop, progress=progress, target_seconds=target_seconds,
                                status=status)


class ZipAdapter:
    name = "Zip"

    def launch(self, profile: Path, test: bool) -> ZipBrowserSession:
        return (ZipBrowserSession.launch_temporary() if test
                else ZipBrowserSession.launch_persistent(profile))

    def open(self, session: ZipBrowserSession, test: bool, stop: threading.Event) -> None:
        if test:
            session.open_zip()
        else:
            session.open_logged_in_zip(stop)

    def solve(self, session: ZipBrowserSession, stop: threading.Event, progress: Progress,
              on_start: Callable[[], None], target_seconds: int, _test: bool,
              status: Callable[[str], None]) -> None:
        plan = solve_zip_and_report(session)
        on_start()
        session.execute_actions(plan, stop=stop, progress=progress, target_seconds=target_seconds,
                                status=status)


class QueensAdapter:
    name = "Queens"

    def launch(self, profile: Path, test: bool) -> QueensBrowserSession:
        return (QueensBrowserSession.launch_temporary() if test
                else QueensBrowserSession.launch_persistent(profile))

    def open(self, session: QueensBrowserSession, test: bool, stop: threading.Event) -> None:
        if test:
            session.open_queens()
        else:
            session.open_logged_in_queens(stop)

    def solve(self, session: QueensBrowserSession, stop: threading.Event, progress: Progress,
              on_start: Callable[[], None], target_seconds: int, _test: bool,
              status: Callable[[str], None]) -> None:
        plan = solve_queens_and_report(session)
        on_start()
        session.execute_actions(plan, stop=stop, progress=progress, target_seconds=target_seconds,
                                status=status)


class PatchesAdapter:
    name = "Patches"

    def launch(self, profile: Path, test: bool) -> PatchesBrowserSession:
        return (PatchesBrowserSession.launch_temporary() if test
                else PatchesBrowserSession.launch_persistent(profile))

    def open(self, session: PatchesBrowserSession, test: bool, stop: threading.Event) -> None:
        if test:
            session.open_patches()
        else:
            session.open_logged_in_patches(stop)

    def solve(self, session: PatchesBrowserSession, stop: threading.Event, progress: Progress,
              on_start: Callable[[], None], target_seconds: int, _test: bool,
              status: Callable[[str], None]) -> None:
        plan = solve_patches_and_report(session)
        on_start()
        session.execute_actions(plan, stop=stop, progress=progress, target_seconds=target_seconds,
                                status=status)


class WendAdapter:
    name = "Wend"

    def launch(self, profile: Path, test: bool) -> WendBrowserSession:
        return (WendBrowserSession.launch_temporary() if test
                else WendBrowserSession.launch_persistent(profile))

    def open(self, session: WendBrowserSession, test: bool, stop: threading.Event) -> None:
        if test:
            session.open_wend()
        else:
            session.open_logged_in_wend(stop)

    def solve(self, session: WendBrowserSession, stop: threading.Event, progress: Progress,
              on_start: Callable[[], None], target_seconds: int, _test: bool,
              status: Callable[[str], None]) -> bool:
        on_start()
        return session.solve_trials(stop=stop, progress=progress, target_seconds=target_seconds, status=status)


class GameWorker(Generic[SessionT]):
    """Keep Playwright and its browser on one background thread."""

    def __init__(self, adapter: GameAdapter[SessionT], profile: Path, test: bool = False) -> None:
        self.adapter = adapter
        self.profile = profile
        self.test = test
        self.messages: queue.Queue[tuple[str, str]] = queue.Queue()
        self.requests: queue.Queue[int] = queue.Queue()
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self._run, name=f"{adapter.name.lower()}-browser")

    def start(self, target_seconds: int = 0) -> None:
        self.requests.put(target_seconds)
        self.thread.start()

    def request_solve(self, target_seconds: int = 0) -> None:
        self.requests.put(target_seconds)

    def _run(self) -> None:
        session = None
        last_result = ""
        try:
            if self.test:
                self.messages.put(("status", "Opening a signed-out test browser..."))
            else:
                self.messages.put(("status", "Opening the LinkedIn browser..."))
            session = self.adapter.launch(self.profile, self.test)
            while not self.stop.is_set():
                try:
                    target_seconds = self.requests.get_nowait()
                except queue.Empty:
                    try:
                        session.keep_alive()
                    except (BrowserSessionError, PlaywrightError):
                        if not session.page.is_closed():
                            raise
                        if not self.stop.is_set():
                            message = "Browser closed. Choose a game to open it again."
                            self.messages.put(("closed", f"{last_result} {message}".strip()))
                        break
                    continue
                last_result = ""
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
                        start_message = ("Test mode: drawing the path..." if self.adapter.name == "Zip"
                                         else "Test mode: drawing patches..." if self.adapter.name == "Patches"
                                         else "Test mode: drawing words..." if self.adapter.name == "Wend"
                                         else "Test mode: clicking the board...")
                        progress_prefix = "Test mode"
                        ready_message = "Practice board matches the solution."
                    else:
                        start_message = ("Drawing the signed-in game path..." if self.adapter.name == "Zip"
                                         else "Drawing the signed-in game patches..." if self.adapter.name == "Patches"
                                         else "Drawing the signed-in game words..." if self.adapter.name == "Wend"
                                         else "Clicking the signed-in game board...")
                        progress_prefix = "Signed-in game"
                        ready_message = "Board matches the solution."
                    def report_progress(done: int, total: int) -> None:
                        unit = ("patches" if self.adapter.name == "Patches"
                                else "words" if self.adapter.name == "Wend" else "cells")
                        self.messages.put(("status", f"{progress_prefix}: filled {done}/{total} {unit}."))
                    timing_notice = ""
                    def report_timing(message: str) -> None:
                        nonlocal timing_notice
                        if message.startswith("Game timer unavailable;"):
                            timing_notice = f" {message}"
                            print(message, flush=True)
                        self.messages.put(("status", message))
                    result = self.adapter.solve(
                        session, self.stop, report_progress,
                        lambda: self.messages.put(("status", start_message)),
                        target_seconds, self.test, report_timing,
                    )
                    if self.adapter.name == "Wend":
                        ready_message = ("Wend solved; LinkedIn confirmed completion." if result
                                         else "All Wend words locked; game completion was not verified.")
                    last_result = ready_message + timing_notice
                    self.messages.put(("ready", last_result))
                except (BrowserSessionError, ValueError) as error:
                    if not self.stop.is_set():
                        print(f"error: {error}", file=sys.stderr, flush=True)
                        suffix = (
                            " The test board may be partially filled; retry to re-read it."
                            if self.test
                            else " The game board may be partially filled; retry to re-read it."
                        )
                        if self.adapter.name in ("Zip", "Wend"):
                            suffix = " The path may be partially drawn; reset the board before retrying."
                        elif self.adapter.name == "Queens":
                            suffix = (" The board may be partially filled; check X marks before retrying, "
                                      "especially on the last attempted cell.")
                        last_result = f"Could not solve: {error}.{suffix}"
                        self.messages.put(("ready", last_result))
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


class ZipWorker(GameWorker[ZipBrowserSession]):
    def __init__(self, profile: Path = ZIP_PROFILE, test: bool = False) -> None:
        super().__init__(ZipAdapter(), profile, test)


class QueensWorker(GameWorker[QueensBrowserSession]):
    def __init__(self, profile: Path = QUEENS_PROFILE, test: bool = False) -> None:
        super().__init__(QueensAdapter(), profile, test)


class PatchesWorker(GameWorker[PatchesBrowserSession]):
    def __init__(self, profile: Path = PATCHES_PROFILE, test: bool = False) -> None:
        super().__init__(PatchesAdapter(), profile, test)


class WendWorker(GameWorker[WendBrowserSession]):
    def __init__(self, profile: Path = WEND_PROFILE, test: bool = False) -> None:
        super().__init__(WendAdapter(), profile, test)


def parse_target_seconds(value: str) -> int:
    value = value.strip()
    if not value:
        return 0
    if not value.isascii() or not value.isdigit():
        raise ValueError("Time must be a non-negative whole number of seconds.")
    try:
        return int(value)
    except ValueError as error:
        raise ValueError("Time is too large.") from error


def main() -> int:
    try:
        import tkinter as tk
        from tkinter import font as tkfont
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

    bg, card_bg, border = "#F3F5F7", "#FFFFFF", "#DDE1E6"
    text, muted, field_border = "#1B1F23", "#5B6470", "#AEB5BD"
    blue, blue_hover, blue_disabled = "#0A66C2", "#084E96", "#9DBFE0"
    shadow, pale_blue, status_bg = "#E3E8EE", "#F2F7FC", "#F9FBFD"
    green, amber, red, gray = "#1A7F4B", "#B26A00", "#B42318", "#98A1AB"
    tooltip_text = (
        "Enter the target time in seconds. "
        "Leave target time blank or 0 to finish as fast as possible."
    )
    game_styles = {
        "Tango": ("Fill the grid with suns and moons.", "#FDEBD3", "#9A4A00"),
        "Mini Sudoku": ("Complete the 6×6 number grid.", "#DDEBFA", "#0A4F96"),
        "Zip": ("Draw one path through every number.", "#DFF3E6", "#17653A"),
        "Queens": ("Place one queen in every region.", "#F3E4F8", "#7A2E91"),
        "Patches": ("Divide the board into shaped patches.", "#FCE3E7", "#A3243B"),
        "Wend": ("Trace the words across the board.", "#DDF1F3", "#0E6470"),
    }

    class FlatButton(tk.Label):
        """A colored, keyboard-operable button that also works on macOS."""

        def __init__(self, parent: tk.Misc, label: str, command: Callable[[], None],
                     primary: bool) -> None:
            super().__init__(
                parent, text=label, font=font(12, "bold" if primary else "normal"),
                borderwidth=0, highlightthickness=1, pady=9, takefocus=True,
            )
            self._command = command
            self._primary = primary
            self._enabled = True
            self._hover = False
            self._focused = False
            self.bind("<Enter>", lambda _event: self._set_hover(True))
            self.bind("<Leave>", lambda _event: self._set_hover(False))
            self.bind("<FocusIn>", lambda _event: self._set_focus(True))
            self.bind("<FocusOut>", lambda _event: self._set_focus(False))
            self.bind("<ButtonRelease-1>", self._click)
            self.bind("<Key-Return>", self._activate)
            self.bind("<Key-space>", self._activate)
            self._paint()

        def _set_hover(self, value: bool) -> None:
            self._hover = value
            self._paint()

        def _set_focus(self, value: bool) -> None:
            self._focused = value
            self._paint()

        def _click(self, event: tk.Event) -> None:
            if 0 <= event.x < self.winfo_width() and 0 <= event.y < self.winfo_height():
                self._activate(event)

        def _activate(self, _event: tk.Event) -> None:
            if self._enabled:
                self._command()

        def configure(self, cnf=None, **kwargs):
            if "state" in kwargs:
                self._enabled = kwargs.pop("state") != "disabled"
                self._paint()
            if cnf is not None or kwargs:
                return super().configure(cnf, **kwargs)
            return None

        config = configure

        def _paint(self) -> None:
            if self._primary:
                color = blue_disabled if not self._enabled else blue_hover if self._hover else blue
                foreground, outline = card_bg, color
            else:
                color = pale_blue if self._hover and self._enabled else card_bg
                foreground = blue if self._hover and self._enabled else text if self._enabled else gray
                outline = blue if self._hover and self._enabled else field_border if self._enabled else border
            if self._focused and self._enabled:
                outline = text if self._primary else blue
            tk.Label.configure(
                self, bg=color, fg=foreground, highlightbackground=outline,
                highlightcolor=outline, cursor="hand2" if self._enabled else "arrow",
                takefocus=self._enabled,
            )

    class InfoIcon(tk.Canvas):
        def __init__(self, parent: tk.Misc) -> None:
            super().__init__(
                parent, width=22, height=22, bg=card_bg, highlightthickness=0,
                cursor="question_arrow", takefocus=True,
            )
            self._ring = self.create_oval(2, 2, 20, 20, outline=muted, width=1.5)
            self._glyph = self.create_text(11, 11, text="i", fill=muted, font=font(10, "bold"))
            self._tip: tk.Toplevel | None = None
            self.bind("<Enter>", self._show)
            self.bind("<Leave>", self._hide)
            self.bind("<FocusIn>", self._show)
            self.bind("<FocusOut>", self._hide)
            self.bind("<Destroy>", self._hide)

        def _show(self, _event: tk.Event) -> None:
            self.itemconfigure(self._ring, outline=blue)
            self.itemconfigure(self._glyph, fill=blue)
            if self._tip is not None:
                return
            self._tip = tk.Toplevel(self)
            self._tip.wm_overrideredirect(True)
            tk.Label(
                self._tip, text=tooltip_text, font=font(11), bg=text, fg=card_bg,
                justify="left", wraplength=230, padx=12, pady=9,
            ).pack()
            self._tip.update_idletasks()
            x = max(0, min(
                self.winfo_rootx() + self.winfo_width() - self._tip.winfo_reqwidth(),
                self.winfo_screenwidth() - self._tip.winfo_reqwidth(),
            ))
            y = max(0, self.winfo_rooty() - self._tip.winfo_reqheight() - 8)
            self._tip.wm_geometry(f"+{x}+{y}")

        def _hide(self, _event: tk.Event) -> None:
            if self._tip is not None:
                self._tip.destroy()
                self._tip = None
            if self.winfo_exists():
                self.itemconfigure(self._ring, outline=muted)
                self.itemconfigure(self._glyph, fill=muted)

    def rounded_tile(canvas: tk.Canvas, color: str) -> None:
        canvas.create_polygon(
            10, 2, 34, 2, 42, 2, 42, 10, 42, 34, 42, 42,
            34, 42, 10, 42, 2, 42, 2, 34, 2, 10, 2, 2,
            smooth=True, fill=color, outline=color,
        )

    def icon_tile(parent: tk.Misc, game: str, tile_bg: str, icon_fg: str) -> tk.Canvas:
        tile = tk.Canvas(parent, width=44, height=44, bg=card_bg, highlightthickness=0)
        rounded_tile(tile, tile_bg)
        line = {"fill": icon_fg, "width": 2, "capstyle": "round", "joinstyle": "round"}
        if game == "Tango":
            tile.create_oval(14, 14, 22, 22, outline=icon_fg, width=2)
            tile.create_arc(23, 23, 33, 33, start=80, extent=200, style="arc",
                            outline=icon_fg, width=2)
        elif game == "Mini Sudoku":
            tile.create_rectangle(14, 14, 30, 30, outline=icon_fg, width=2)
            for offset in (19.3, 24.7):
                tile.create_line(offset, 14, offset, 30, **line)
                tile.create_line(14, offset, 30, offset, **line)
        elif game == "Zip":
            tile.create_line(14, 28, 20, 28, 20, 20, 28, 20, 28, 15, **line)
        elif game == "Queens":
            tile.create_line(14, 28, 16, 19, 20, 23, 22, 16, 24, 23, 28, 19,
                             30, 28, 14, 28, **line)
        elif game == "Patches":
            for coords in ((14, 14, 23, 23), (25, 14, 30, 23), (14, 25, 30, 30)):
                tile.create_rectangle(*coords, outline=icon_fg, width=2)
        else:
            tile.create_line(13, 25, 17, 19, 22, 25, 26, 31, 31, 25, smooth=True, **line)
        return tile

    families = set(tkfont.families(root))
    face = next(
        (name for name in ("Inter", "SF Pro Text", "Segoe UI", "Helvetica Neue", "Helvetica")
         if name in families),
        "TkDefaultFont",
    )

    def font(size: int, weight: str = "normal") -> tuple[str, int, str]:
        return face, size, weight

    root.title("LockedIn")
    root.configure(bg=bg)
    root.resizable(False, False)
    viewport = tk.Canvas(root, bg=bg, highlightthickness=0, borderwidth=0)
    scrollbar = tk.Scrollbar(root, orient="vertical", command=viewport.yview)
    viewport.configure(yscrollcommand=scrollbar.set)
    viewport.pack(side="left", fill="both", expand=True)
    outer = tk.Frame(viewport, bg=bg, padx=28, pady=18)
    viewport_window = viewport.create_window(0, 0, anchor="nw", window=outer)

    def fit_window(_event: tk.Event | None = None) -> None:
        root.update_idletasks()
        width, height = outer.winfo_reqwidth(), outer.winfo_reqheight()
        max_width, max_height = root.maxsize()
        needs_scroll = height > max_height
        if needs_scroll:
            scrollbar.pack(side="right", fill="y")
        else:
            scrollbar.pack_forget()
        viewport.configure(scrollregion=(0, 0, width, height))
        viewport.itemconfigure(viewport_window, width=width)
        scroll_width = scrollbar.winfo_reqwidth() if needs_scroll else 0
        root.resizable(True, True)
        root.geometry(f"{min(width + scroll_width, max_width)}x{min(height, max_height)}")
        root.resizable(False, False)

    def scroll_wheel(event: tk.Event) -> None:
        if event.num == 4:
            viewport.yview_scroll(-1, "units")
        elif event.num == 5:
            viewport.yview_scroll(1, "units")
        elif event.delta:
            viewport.yview_scroll(-max(1, abs(event.delta) // 120) if event.delta > 0
                                  else max(1, abs(event.delta) // 120), "units")

    def reveal_focus(event: tk.Event) -> None:
        widget = event.widget
        if widget.winfo_toplevel() != root or not str(widget).startswith(f"{outer}."):
            return
        top = widget.winfo_rooty() - outer.winfo_rooty()
        bottom = top + widget.winfo_height()
        visible_top = viewport.canvasy(0)
        visible_bottom = visible_top + viewport.winfo_height()
        if top < visible_top:
            viewport.yview_moveto(top / outer.winfo_height())
        elif bottom > visible_bottom:
            viewport.yview_moveto((bottom - viewport.winfo_height()) / outer.winfo_height())

    outer.bind("<Configure>", lambda _event: root.after_idle(fit_window))
    root.bind_all("<MouseWheel>", scroll_wheel)
    root.bind_all("<Button-4>", scroll_wheel)
    root.bind_all("<Button-5>", scroll_wheel)
    root.bind_all("<FocusIn>", reveal_focus, add="+")

    header = tk.Frame(outer, bg=bg)
    header.pack(fill="x")
    mark = tk.Canvas(header, width=44, height=44, bg=bg, highlightthickness=0)
    rounded_tile(mark, blue)
    mark.create_arc(15, 8, 29, 26, start=0, extent=180, style="arc", outline=card_bg, width=2)
    mark.create_rectangle(14, 19, 30, 32, outline=card_bg, width=2)
    mark.create_oval(21, 24, 23, 26, fill=card_bg, outline=card_bg)
    mark.pack(side="left", padx=(0, 12))
    titles = tk.Frame(header, bg=bg)
    titles.pack(side="left")
    tk.Label(titles, text="TechZech's LockedIn", font=font(24, "bold"), bg=bg, fg=text).pack(anchor="w")
    tk.Label(titles, text="LinkedIn game solvers", font=font(12), bg=bg, fg=muted).pack(anchor="w")
    tk.Label(
        header, text="Solve plays your signed-in game\nPractice uses a signed-out test board",
        font=font(11), bg=bg, fg=muted, justify="right",
    ).pack(side="right", anchor="s")

    pill = tk.Frame(
        outer, bg=status_bg, highlightbackground=border, highlightthickness=1, padx=14, pady=10,
    )
    pill.pack(fill="x", pady=(18, 12))
    dot = tk.Canvas(pill, width=12, height=12, bg=status_bg, highlightthickness=0)
    dot_item = dot.create_oval(1, 1, 11, 11, fill=green, outline=green)
    dot.pack(side="left", padx=(0, 10))
    status = tk.StringVar(value="Ready. Choose a game below to open its browser and start solving.")
    status_label = tk.Label(
        pill, textvariable=status, font=font(12), bg=status_bg, fg=text,
        anchor="w", justify="left", wraplength=680, height=2, takefocus=True,
    )
    status_label.pack(side="left", fill="x", expand=True)
    status_measure = tk.Label(
        status_label, textvariable=status, font=font(12), wraplength=680, justify="left",
    )

    status_tip: tk.Toplevel | None = None

    def show_status_tip(_event: tk.Event) -> None:
        nonlocal status_tip
        if status_tip is not None:
            return
        root.update_idletasks()
        if status_measure.winfo_reqheight() <= status_label.winfo_height():
            return
        status_tip = tk.Toplevel(status_label)
        status_tip.wm_overrideredirect(True)
        tk.Label(
            status_tip, textvariable=status, font=font(11), bg=text, fg=card_bg,
            justify="left", wraplength=680, padx=12, pady=9,
        ).pack()
        status_tip.update_idletasks()
        x = max(0, min(status_label.winfo_rootx(),
                       status_label.winfo_screenwidth() - status_tip.winfo_reqwidth()))
        y = max(0, status_label.winfo_rooty() - status_tip.winfo_reqheight() - 8)
        status_tip.wm_geometry(f"+{x}+{y}")

    def hide_status_tip(_event: tk.Event) -> None:
        nonlocal status_tip
        if status_tip is not None:
            status_tip.destroy()
            status_tip = None

    status_label.bind("<Enter>", show_status_tip)
    status_label.bind("<Leave>", hide_status_tip)
    status_label.bind("<FocusIn>", show_status_tip)
    status_label.bind("<FocusOut>", hide_status_tip)

    def set_dot(color: str) -> None:
        dot.itemconfigure(dot_item, fill=color, outline=color)

    workers: dict[tuple[str, bool], TangoWorker | MiniSudokuWorker | ZipWorker | QueensWorker | PatchesWorker | WendWorker] = {}
    buttons: dict[tuple[str, bool], FlatButton] = {}
    worker_types = {"Tango": TangoWorker, "Mini Sudoku": MiniSudokuWorker, "Zip": ZipWorker,
                    "Queens": QueensWorker, "Patches": PatchesWorker, "Wend": WendWorker}
    times = {game: tk.StringVar(value="") for game in worker_types}
    closing = False

    def solve(game: str, test: bool) -> None:
        key = (game, test)
        try:
            target_seconds = parse_target_seconds(times[game].get())
        except ValueError as error:
            status.set(str(error))
            set_dot(red)
            return
        buttons[key].configure(state="disabled")
        worker = workers.get(key)
        if worker is None or not worker.thread.is_alive():
            worker = workers[key] = worker_types[game](test=test)
            worker.start(target_seconds)
        else:
            worker.request_solve(target_seconds)
        status.set(f"Opening {game}{' practice' if test else ''}...")
        set_dot(amber)

    grid = tk.Frame(outer, bg=bg)
    grid.pack(fill="x")
    for column in range(3):
        grid.columnconfigure(column * 2, weight=1, uniform="cards")
    for column in (1, 3):
        grid.columnconfigure(column, minsize=12)
    for index, game in enumerate(worker_types):
        description, tile_bg, icon_fg = game_styles[game]
        card_shadow = tk.Frame(grid, bg=shadow)
        card_shadow.grid(
            row=index // 3, column=(index % 3) * 2, sticky="nsew",
            pady=(0 if index < 3 else 12, 0),
        )
        card = tk.Frame(card_shadow, bg=card_bg, highlightbackground=border, highlightthickness=1)
        card.pack(fill="both", expand=True, padx=(0, 2), pady=(0, 2))
        tk.Frame(card, bg=tile_bg, height=4).pack(fill="x")
        body = tk.Frame(card, bg=card_bg, padx=20, pady=12)
        body.pack(fill="both", expand=True)
        head = tk.Frame(body, bg=card_bg)
        head.pack(fill="x")
        icon_tile(head, game, tile_bg, icon_fg).pack(side="left")
        tk.Label(head, text=game, font=font(15, "bold"), bg=card_bg, fg=text).pack(
            side="left", padx=(12, 0),
        )
        tk.Label(
            body, text=description, font=font(12), bg=card_bg, fg=muted,
            wraplength=220, justify="left", anchor="nw", height=2,
        ).pack(fill="x", pady=(8, 8))
        tk.Frame(body, bg=border, height=1).pack(fill="x", pady=(0, 6))
        row = tk.Frame(body, bg=card_bg)
        row.pack(fill="x")
        tk.Label(row, text="Target time", font=font(12, "bold"), bg=card_bg, fg=text).pack(side="left")
        InfoIcon(row).pack(side="right")
        tk.Label(row, text="sec", font=font(11), bg=card_bg, fg=muted).pack(side="right", padx=4)
        tk.Entry(
            row, textvariable=times[game], width=7, justify="right", font=font(12),
            relief="flat", bg=card_bg, fg=text, insertbackground=text, highlightthickness=1,
            highlightbackground=field_border, highlightcolor=blue,
        ).pack(side="right", ipady=4)
        for test in (False, True):
            key = (game, test)
            buttons[key] = FlatButton(
                body, "Practice run" if test else f"Solve today's {game}",
                command=lambda game=game, test=test: solve(game, test), primary=not test,
            )
            buttons[key].pack(fill="x", pady=(8 if test else 16, 0))

    def poll() -> None:
        for key, worker in workers.items():
            while True:
                try:
                    kind, message = worker.messages.get_nowait()
                except queue.Empty:
                    break
                if message and not closing:
                    status.set(message)
                    if kind == "error" or message.startswith("Could not solve"):
                        set_dot(red)
                    elif kind in ("ready", "closed"):
                        set_dot(green)
                    else:
                        set_dot(amber)
                if kind == "ready" and not closing:
                    buttons[key].configure(state="normal")
                elif kind == "closed" and not closing:
                    buttons[key].configure(state="disabled")
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
        set_dot(gray)
        for worker in workers.values():
            worker.stop.set()

    root.protocol("WM_DELETE_WINDOW", close)
    root.after_idle(fit_window)
    root.after(100, poll)
    root.mainloop()
    return 0
