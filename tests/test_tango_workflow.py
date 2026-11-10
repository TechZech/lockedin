import io
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import Mock

from lockedin.tango.actions import CellAction
from lockedin.tango.model import Board, Cell
from lockedin.tango.solver import DeductionStalled
from lockedin.tango.workflow import plan_board, solve_and_report


SOLVED = Board.from_strings(("SMSMMS", "SSMMSM", "MSMSSM", "SMSMMS", "MMSSMS", "MSMSSM"))


class TangoWorkflowTests(unittest.TestCase):
    def test_plans_and_reports_the_same_board_without_clicking(self) -> None:
        current = Board.from_strings(("?M?MMS",) + SOLVED.as_strings()[1:])
        reader = Mock()
        reader.snapshot_board.return_value = current
        output = io.StringIO()

        with redirect_stdout(output):
            plan = solve_and_report(reader)

        self.assertEqual(plan, plan_board(current))
        self.assertEqual(plan.solved, SOLVED)
        self.assertEqual(plan.actions, (CellAction(0, Cell.SUN, 1), CellAction(2, Cell.SUN, 1)))
        reader.snapshot_board.assert_called_once_with()
        reader.execute_actions.assert_not_called()
        self.assertIn("Current board:\n?M?MMS", output.getvalue())
        self.assertIn("Solved board:\nSMSMMS", output.getvalue())
        self.assertIn("cell 0 -> SUN (1 click)", output.getvalue())

    def test_reports_deduction_stall_and_does_not_create_plan(self) -> None:
        reader = Mock()
        reader.snapshot_board.return_value = Board.from_strings(("??????",) * 6)
        output, errors = io.StringIO(), io.StringIO()

        with redirect_stdout(output), redirect_stderr(errors), self.assertRaises(DeductionStalled):
            solve_and_report(reader)

        self.assertIn("Current board:", output.getvalue())
        self.assertNotIn("Solved board:", output.getvalue())
        self.assertIn("Solver status: deduction stalled.", errors.getvalue())
        reader.execute_actions.assert_not_called()
