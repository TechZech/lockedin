import unittest
from pathlib import Path
from threading import Event
from unittest.mock import Mock, patch

from lockedin.gui import TangoWorker
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
