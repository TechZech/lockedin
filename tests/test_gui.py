import queue
import time
import unittest
from pathlib import Path
from threading import Event
from unittest.mock import Mock, patch

from playwright.sync_api import Error as PlaywrightError

from lockedin import gui
from lockedin.gui import TangoWorker, parse_target_seconds
from lockedin.tango.browser import BrowserSessionError
from lockedin.tango.model import Board


class FakeSession:
    def __init__(self) -> None:
        self.closed = False
        self.reads = 0
        self.executed = False
        self.execution_calls = []
        self.login_checks = 0

    def open_logged_in_tango(self, stop: Event) -> None:
        self.login_checks += 1

    def wait_for_board(self, stop: Event) -> None:
        if stop.is_set():
            raise RuntimeError("cancelled")

    def snapshot_board(self) -> Board:
        self.reads += 1
        return Board.from_strings(("SMSMMS", "SSMMSM", "MSMSSM", "SMSMMS", "MMSSMS", "MSMSSM"))

    def keep_alive(self) -> None:
        Event().wait(0.01)

    def execute_actions(self, *args, **kwargs) -> None:
        self.executed = True
        self.execution_calls.append((args, kwargs))
        kwargs["progress"](1, 1)

    def close(self) -> None:
        self.closed = True


class TangoWorkerTests(unittest.TestCase):
    def wait_for(self, worker: TangoWorker, wanted: str, statuses: list[str] | None = None) -> str:
        while True:
            kind, message = worker.messages.get(timeout=3)
            if kind == wanted:
                return message
            if kind == "error":
                self.fail(message)
            if kind == "status" and statuses is not None:
                statuses.append(message)

    @patch("lockedin.gui.TangoBrowserSession.launch_persistent")
    def test_estimated_timer_notice_remains_in_ready_status(self, launch: Mock) -> None:
        session = FakeSession()
        def execute(*args, **kwargs):
            kwargs["status"]("Game timer unavailable; using an estimated timer for the final move.")
            kwargs["status"]("Waiting for the estimated timer to reach 5 seconds before the final move.")
        session.execute_actions = Mock(side_effect=execute)
        launch.return_value = session
        worker = TangoWorker(Path("/test/profile"))
        worker.start(5)
        try:
            message = self.wait_for(worker, "ready")
        finally:
            worker.stop.set()
            worker.thread.join(timeout=3)
        self.assertIn("estimated timer", message)

    @patch("lockedin.gui.TangoBrowserSession.launch_temporary")
    def test_closed_idle_browser_preserves_success_without_reporting_error(self, launch: Mock) -> None:
        for close_during_wait in (False, True):
            with self.subTest(close_during_wait=close_during_wait):
                session = FakeSession()
                session.open_tango = Mock()
                closed = Event()
                entered_wait = Event()
                session.page = Mock()
                session.page.is_closed.side_effect = closed.is_set

                def wait(_timeout):
                    entered_wait.set()
                    if closed.wait(0.01) and close_during_wait:
                        raise PlaywrightError("Page.wait_for_timeout: Target page, context or browser has been closed")

                session.page.wait_for_timeout.side_effect = wait
                session.keep_alive = lambda: gui.TangoBrowserSession.keep_alive(session)
                launch.return_value = session
                worker = TangoWorker(Path("/test/profile"), test=True)
                worker.start()
                try:
                    ready = self.wait_for(worker, "ready")
                    self.assertIn("Practice board matches the solution", ready)
                    self.assertIn("completion wasn't verified", ready)
                    self.assertTrue(entered_wait.wait(3))
                    closed.set()
                    message = self.wait_for(worker, "closed")
                    self.assertIn(ready, message)
                    self.assertIn("Browser closed", message)
                    worker.thread.join(timeout=3)
                    self.assertFalse(worker.thread.is_alive())
                    self.assertEqual(worker.messages.get(timeout=3), ("stopped", ""))
                finally:
                    worker.stop.set()
                    worker.thread.join(timeout=3)
                self.assertTrue(session.closed)

    @patch("lockedin.gui.TangoBrowserSession.launch_persistent")
    def test_idle_browser_error_is_not_hidden_when_page_remains_open(self, launch: Mock) -> None:
        session = FakeSession()
        session.page = Mock()
        session.page.is_closed.return_value = False
        session.keep_alive = Mock(side_effect=PlaywrightError("connection failed"))
        launch.return_value = session
        worker = TangoWorker(Path("/test/profile"))
        worker.start()
        try:
            self.wait_for(worker, "ready")
            kind, message = worker.messages.get(timeout=3)
            self.assertEqual(kind, "error")
            self.assertIn("connection failed", message)
        finally:
            worker.stop.set()
            worker.thread.join(timeout=3)

    @patch("lockedin.gui.TangoBrowserSession.launch_persistent")
    def test_closed_browser_during_solve_remains_a_failure(self, launch: Mock) -> None:
        session = FakeSession()
        session.execute_actions = Mock(side_effect=BrowserSessionError("browser closed during execution"))
        session.page = Mock()
        session.page.is_closed.return_value = True
        session.keep_alive = Mock(side_effect=BrowserSessionError("the browser was closed"))
        launch.return_value = session
        worker = TangoWorker(Path("/test/profile"))
        worker.start()
        try:
            failure = self.wait_for(worker, "ready")
            self.assertIn("Could not solve", failure)
            self.assertIn("partially filled", failure)
            self.assertIn(failure, self.wait_for(worker, "closed"))
        finally:
            worker.stop.set()
            worker.thread.join(timeout=3)

    @patch("lockedin.gui.TangoBrowserSession.launch_persistent")
    def test_solve_and_retry_executes_fresh_plan_then_closes_browser(self, launch: Mock) -> None:
        session = FakeSession()
        launch.return_value = session
        worker = TangoWorker(Path("/test/profile"))
        statuses: list[str] = []
        worker.start()
        try:
            self.assertIn("matches the solution", self.wait_for(worker, "ready", statuses))
            worker.request_solve()
            self.assertIn("matches the solution", self.wait_for(worker, "ready"))
        finally:
            worker.stop.set()
            worker.thread.join(timeout=3)

        self.assertFalse(worker.thread.is_alive())
        self.assertEqual(session.reads, 2)
        self.assertEqual(session.login_checks, 2)
        self.assertTrue(session.executed)
        self.assertEqual(len(session.execution_calls), 2)
        for args, kwargs in session.execution_calls:
            self.assertEqual(args[0].current.as_strings()[0], "SMSMMS")
            self.assertEqual(args[0].solved, args[0].current)
            self.assertIs(kwargs["stop"], worker.stop)
        self.assertIn("Signed-in game: filled 1/1 cells.", statuses)
        self.assertTrue(session.closed)
        launch.assert_called_once_with(Path("/test/profile"))

    @patch("lockedin.gui.TangoBrowserSession.launch_persistent")
    def test_signed_in_execution_failure_is_reported(self, launch: Mock) -> None:
        session = FakeSession()
        session.execute_actions = Mock(side_effect=BrowserSessionError("cell 4 did not update"))
        launch.return_value = session
        worker = TangoWorker(Path("/test/profile"))
        worker.start()
        try:
            message = self.wait_for(worker, "ready")
        finally:
            worker.stop.set()
            worker.thread.join(timeout=3)

        self.assertIn("cell 4 did not update", message)
        self.assertIn("game board may be partially filled", message)
        session.execute_actions.assert_called_once()
        self.assertTrue(session.closed)

    @patch("lockedin.gui.TangoBrowserSession.launch_persistent", side_effect=RuntimeError("launch failed"))
    def test_browser_launch_failure_is_reported(self, launch: Mock) -> None:
        worker = TangoWorker(Path("/test/profile"))
        worker.start()
        try:
            self.assertIn("launch failed", self.wait_for(worker, "error"))
        finally:
            worker.thread.join(timeout=3)
        self.assertFalse(worker.thread.is_alive())

    @patch("lockedin.gui.TangoBrowserSession.launch_persistent")
    def test_failed_sign_in_never_reads_or_solves_board(self, launch: Mock) -> None:
        session = FakeSession()
        session.open_logged_in_tango = Mock(side_effect=BrowserSessionError("sign-in failed"))
        launch.return_value = session
        worker = TangoWorker(Path("/test/profile"))
        worker.start()
        try:
            self.assertIn("sign-in failed", self.wait_for(worker, "ready"))
        finally:
            worker.stop.set()
            worker.thread.join(timeout=3)
        self.assertEqual(session.reads, 0)
        self.assertFalse(session.executed)
        self.assertTrue(session.closed)

    @patch("lockedin.gui.TangoBrowserSession.launch_persistent")
    def test_failed_board_wait_never_executes(self, launch: Mock) -> None:
        session = FakeSession()
        session.wait_for_board = Mock(side_effect=BrowserSessionError("board unavailable"))
        launch.return_value = session
        worker = TangoWorker(Path("/test/profile"))
        worker.start()
        try:
            self.assertIn("board unavailable", self.wait_for(worker, "ready"))
        finally:
            worker.stop.set()
            worker.thread.join(timeout=3)
        self.assertEqual(session.reads, 0)
        self.assertFalse(session.executed)


class TestModeTests(unittest.TestCase):
    @patch("lockedin.gui.TangoBrowserSession.launch_persistent")
    @patch("lockedin.gui.TangoBrowserSession.launch_temporary")
    def test_test_mode_clicks_in_signed_out_browser_and_never_the_live_profile(
        self, temporary: Mock, persistent: Mock
    ) -> None:
        session = FakeSession()
        session.open_tango = Mock()
        session.open_logged_in_tango = Mock()
        temporary.return_value = session
        worker = TangoWorker(Path("/test/profile"), test=True)
        statuses: list[str] = []
        worker.start()
        try:
            while True:
                kind, message = worker.messages.get(timeout=3)
                if kind == "ready":
                    break
                if kind == "error":
                    self.fail(message)
                if kind == "status":
                    statuses.append(message)
        finally:
            worker.stop.set()
            worker.thread.join(timeout=3)

        self.assertIn("matches the solution", message)
        persistent.assert_not_called()
        session.open_tango.assert_called_once_with()
        session.open_logged_in_tango.assert_not_called()
        self.assertEqual(session.reads, 1)
        self.assertTrue(session.executed)
        self.assertIn("Test mode: filled 1/1 cells.", statuses)
        self.assertIs(session.execution_calls[0][1]["stop"], worker.stop)
        self.assertTrue(session.closed)

    @patch("lockedin.gui.TangoBrowserSession.launch_temporary")
    def test_test_mode_reports_execution_failure_and_partial_board(self, temporary: Mock) -> None:
        session = FakeSession()
        session.open_tango = Mock()
        session.execute_actions = Mock(side_effect=BrowserSessionError("cell 4 did not update"))
        temporary.return_value = session
        worker = TangoWorker(Path("/test/profile"), test=True)
        worker.start()
        try:
            while True:
                kind, message = worker.messages.get(timeout=3)
                if kind == "ready":
                    break
                if kind == "error":
                    self.fail(message)
        finally:
            worker.stop.set()
            worker.thread.join(timeout=3)

        self.assertIn("cell 4 did not update", message)
        self.assertIn("may be partially filled", message)
        self.assertTrue(session.closed)

    @patch("lockedin.gui.TangoBrowserSession.launch_persistent")
    def test_each_request_captures_its_own_target(self, launch: Mock) -> None:
        session = FakeSession()
        launch.return_value = session
        worker = TangoWorker(Path("/test/profile"))
        worker.start(5)
        try:
            while worker.messages.get(timeout=3)[0] != "ready":
                pass
            worker.request_solve(12)
            while worker.messages.get(timeout=3)[0] != "ready":
                pass
        finally:
            worker.stop.set()
            worker.thread.join(timeout=3)
        self.assertEqual([kwargs["target_seconds"] for _, kwargs in session.execution_calls], [5, 12])


class TimeInputTests(unittest.TestCase):
    def test_valid_inputs(self):
        for value, expected in (("", 0), ("   ", 0), ("0", 0), (" 5 ", 5), ("120", 120)):
            self.assertEqual(parse_target_seconds(value), expected)

    def test_invalid_inputs(self):
        for value in ("-1", "1.5", "abc", "+2", "１２"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_target_seconds(value)


class DesktopWindowTests(unittest.TestCase):
    def test_cards_controls_status_and_shutdown(self):
        try:
            import tkinter as tk
        except ImportError:
            self.skipTest("Tkinter is unavailable")
        try:
            probe = tk.Tk()
            probe.destroy()
        except tk.TclError as error:
            self.skipTest(f"Tk display is unavailable: {error}")

        created = []

        class FakeThread:
            alive = False

            def is_alive(self):
                return self.alive

        class FakeWorker:
            def __init__(self, test=False):
                self.test = test
                self.thread = FakeThread()
                self.messages = queue.Queue()
                self.stop = Event()
                self.calls = []
                created.append(self)

            def start(self, seconds):
                self.calls.append(("start", seconds))
                self.thread.alive = True

            def request_solve(self, seconds):
                self.calls.append(("retry", seconds))

        def descendants(widget):
            for child in widget.winfo_children():
                yield child
                yield from descendants(child)

        def exercise(root):
            try:
                root.update()
                widgets = list(descendants(root))
                buttons = [widget for widget in widgets if widget.__class__.__name__ == "FlatButton"]
                entries = [widget for widget in widgets if isinstance(widget, tk.Entry)]
                infos = [widget for widget in widgets if widget.__class__.__name__ == "InfoIcon"]
                dot = next(widget for widget in widgets if isinstance(widget, tk.Canvas)
                           and int(widget.cget("width")) == 12)

                def dot_color():
                    return dot.itemcget(dot.find_all()[0], "fill")

                def poll():
                    done = tk.BooleanVar(root, False)
                    root.after(150, lambda: done.set(True))
                    root.wait_variable(done)

                poll()
                self.assertEqual(len(buttons), 12)
                self.assertEqual(len(entries), 6)
                self.assertEqual(len(infos), 6)
                self.assertEqual(len({button.winfo_width() for button in buttons}), 1)
                geometry = (root.winfo_width(), root.winfo_height())
                for canvas in (widget for widget in widgets if isinstance(widget, tk.Canvas)
                               and int(widget.cget("width")) in (12, 44)):
                    x1, y1, x2, y2 = canvas.bbox("all")
                    self.assertGreaterEqual(x1, 0)
                    self.assertGreaterEqual(y1, 0)
                    self.assertLessEqual(x2, canvas.winfo_width())
                    self.assertLessEqual(y2, canvas.winfo_height())
                for widget in buttons + entries + infos:
                    left = widget.winfo_rootx() - root.winfo_rootx()
                    top = widget.winfo_rooty() - root.winfo_rooty()
                    self.assertGreaterEqual(left, 0)
                    self.assertGreaterEqual(top, 0)
                    self.assertLessEqual(left + widget.winfo_width(), geometry[0])
                    self.assertLessEqual(top + widget.winfo_height(), geometry[1])
                status_label = next(
                    widget for widget in widgets
                    if isinstance(widget, tk.Label) and widget.cget("textvariable")
                    and widget.winfo_ismapped()
                )
                self.assertEqual(dot_color(), "#1A7F4B")

                entries[0].insert(0, "-1")
                buttons[0].event_generate("<ButtonRelease-1>", x=5, y=5)
                self.assertFalse(created)
                self.assertEqual(dot_color(), "#B42318")
                entries[0].delete(0, "end")
                entries[0].insert(0, "5")
                buttons[0].event_generate("<ButtonRelease-1>", x=5, y=5)
                self.assertEqual(created[0].calls, [("start", 5)])
                self.assertEqual(dot_color(), "#B26A00")
                buttons[0].event_generate("<ButtonRelease-1>", x=5, y=5)
                self.assertEqual(created[0].calls, [("start", 5)])

                created[0].messages.put(("ready", "Could not solve: example"))
                poll()
                self.assertEqual(dot_color(), "#B42318")
                buttons[0].event_generate("<ButtonRelease-1>", x=5, y=5)
                self.assertEqual(created[0].calls[-1], ("retry", 5))
                created[0].messages.put(("ready", "Board matches the solution"))
                poll()
                self.assertEqual(dot_color(), "#1A7F4B")
                created[0].messages.put(("closed", "Board matches the solution. Browser closed."))
                poll()
                self.assertEqual(dot_color(), "#1A7F4B")
                created[0].messages.put(("closed", "Could not solve: interrupted. Browser closed."))
                poll()
                self.assertEqual(dot_color(), "#B42318")
                self.assertFalse(buttons[0]._enabled)
                created[0].thread.alive = False
                poll()
                self.assertTrue(buttons[0]._enabled)

                infos[0].event_generate("<Enter>")
                root.update()
                self.assertTrue(any(isinstance(widget, tk.Toplevel) for widget in descendants(root)))
                infos[0].event_generate("<Leave>")
                root.update()
                self.assertFalse(any(isinstance(widget, tk.Toplevel) for widget in descendants(root)))

                buttons[1].focus_force()
                root.update()
                buttons[1].event_generate("<Key-space>")
                self.assertTrue(created[1].test)
                self.assertEqual(created[1].calls, [("start", 5)])

                long_error = "Could not solve: " + "error details " * 80
                created[1].messages.put(("ready", long_error))
                poll()
                status_label.event_generate("<Enter>")
                root.update()
                status_tips = [widget for widget in descendants(root)
                               if isinstance(widget, tk.Toplevel)]
                self.assertEqual(len(status_tips), 1)
                self.assertEqual(root.getvar(status_tips[0].winfo_children()[0].cget("textvariable")),
                                 long_error)
                status_label.event_generate("<Leave>")
                root.update()
                self.assertEqual((root.winfo_width(), root.winfo_height()), geometry)

                buttons[0].event_generate("<ButtonRelease-1>", x=5, y=5)
                self.assertEqual(created[2].calls, [("start", 5)])
                self.assertFalse(created[2].test)

                root.tk.call(root.protocol("WM_DELETE_WINDOW"))
                self.assertTrue(all(worker.stop.is_set() for worker in created[1:]))
                self.assertEqual(dot_color(), "#98A1AB")
                for worker in created:
                    worker.thread.alive = False
                time.sleep(0.15)
                root.update()
                with self.assertRaises(tk.TclError):
                    root.winfo_exists()
            finally:
                try:
                    root.destroy()
                except tk.TclError:
                    pass

        worker_types = {
            name: FakeWorker for name in (
                "TangoWorker", "MiniSudokuWorker", "ZipWorker",
                "QueensWorker", "PatchesWorker", "WendWorker",
            )
        }
        with patch.object(tk.Tk, "mainloop", exercise), patch.multiple(gui, **worker_types):
            self.assertEqual(gui.main(), 0)

    def test_short_screen_scrolls_to_focused_button(self):
        try:
            import tkinter as tk
        except ImportError:
            self.skipTest("Tkinter is unavailable")
        try:
            probe = tk.Tk()
            probe.destroy()
        except tk.TclError as error:
            self.skipTest(f"Tk display is unavailable: {error}")

        def descendants(widget):
            for child in widget.winfo_children():
                yield child
                yield from descendants(child)

        def exercise(root):
            try:
                done = tk.BooleanVar(root, False)
                root.after(200, lambda: done.set(True))
                root.wait_variable(done)
                widgets = list(descendants(root))
                scrollbar = next(widget for widget in widgets if isinstance(widget, tk.Scrollbar))
                viewport = next(widget for widget in widgets if isinstance(widget, tk.Canvas)
                                and widget.find_withtag("all")
                                and widget.type(widget.find_withtag("all")[0]) == "window")
                buttons = [widget for widget in widgets if widget.__class__.__name__ == "FlatButton"]
                self.assertTrue(scrollbar.winfo_ismapped())
                self.assertLessEqual(root.winfo_height(), 400)
                self.assertLess(viewport.yview()[1], 1)

                buttons[-1].focus_force()
                root.update()
                self.assertGreater(viewport.yview()[0], 0)
                self.assertGreaterEqual(buttons[-1].winfo_rooty(), viewport.winfo_rooty())
                self.assertLessEqual(buttons[-1].winfo_rooty() + buttons[-1].winfo_height(),
                                     viewport.winfo_rooty() + viewport.winfo_height())
            finally:
                root.destroy()

        with patch.object(tk.Tk, "maxsize", return_value=(1000, 400)), \
                patch.object(tk.Tk, "mainloop", exercise):
            self.assertEqual(gui.main(), 0)
