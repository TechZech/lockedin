import unittest
from unittest.mock import patch

from lockedin.cli import main
from lockedin.tango.model import Board


class FakeSession:
    def __init__(self) -> None:
        self.current = Board.from_strings(("SMSMMS", "SSMMSM", "MSMSSM", "SMSMMS", "MMSSMS", "MSMSSM"))
        self.executed: bool | None = None

    def snapshot_board(self) -> Board:
        return self.current

    def execute_actions(self, plan) -> None:
        self.executed = True

    def close(self) -> None:
        pass


class CliTests(unittest.TestCase):
    @patch("lockedin.cli.WendBrowserSession.connect_over_cdp")
    def test_wend_execution_uses_trial_workflow(self, connect) -> None:
        session = connect.return_value
        session.solve_trials.return_value = True
        self.assertEqual(main(["wend", "--execute"]), 0)
        session.solve_trials.assert_called_once()
        session.close.assert_called_once()

    @patch("lockedin.gui.main", return_value=0)
    def test_ui_command_opens_desktop_interface(self, gui_main) -> None:
        self.assertEqual(main(["ui"]), 0)
        gui_main.assert_called_once_with()

    @patch("lockedin.cli.TangoBrowserSession.connect_over_cdp")
    def test_tango_defaults_to_dry_run(self, connect) -> None:
        session = FakeSession()
        connect.return_value = session

        exit_code = main(["tango"])

        self.assertEqual(exit_code, 0)
        self.assertIsNone(session.executed)

    @patch("lockedin.cli.TangoBrowserSession.connect_over_cdp")
    def test_tango_execute_flag_is_explicit(self, connect) -> None:
        session = FakeSession()
        connect.return_value = session

        exit_code = main(["tango", "--execute"])

        self.assertEqual(exit_code, 0)
        self.assertTrue(session.executed)