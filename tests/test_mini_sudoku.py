import unittest
from unittest.mock import patch

from lockedin.cli import main
from lockedin.mini_sudoku.actions import create_action_plan
from lockedin.mini_sudoku.dom import InvalidDomSnapshot, board_from_snapshot
from lockedin.mini_sudoku.model import Board, InvalidBoard
from lockedin.mini_sudoku.solver import AmbiguousPuzzle, Solver, UnsolvablePuzzle


SOLVED = Board.from_strings(("354216", "612345", "126534", "543621", "435162", "261453"))
PUZZLE = Board.from_strings(("??????", "?1234?", "12??34", "54??21", "?3516?", "??????"))


class MiniSudokuTests(unittest.TestCase):
    def test_solve_puzzle_and_preserve_givens(self):
        solved = Solver().solve(PUZZLE)
        self.assertEqual(solved, SOLVED)
        plan = create_action_plan(PUZZLE, solved)
        self.assertEqual(len(plan.actions), 20)
        self.assertEqual((plan.actions[0].index, plan.actions[0].target), (0, 3))

    def test_invalid_and_ambiguous_boards_are_rejected(self):
        with self.assertRaises(InvalidBoard):
            Board.from_strings(("123456",) * 5)
        with self.assertRaises(InvalidBoard):
            Board.from_strings(("12345x",) * 6)
        with self.assertRaises(UnsolvablePuzzle):
            Solver().solve(Board.from_strings(("114216",) + SOLVED.as_strings()[1:]))
        with self.assertRaises(AmbiguousPuzzle):
            Solver().solve(Board.from_strings(("??????",) * 6))

    def test_action_plan_rejects_bad_solution_and_changed_givens(self):
        with self.assertRaises(ValueError):
            create_action_plan(PUZZLE, Board.from_strings(("??????",) * 6))
        current = Board.from_strings(("4?????",) + PUZZLE.as_strings()[1:])
        with self.assertRaises(ValueError):
            create_action_plan(current, SOLVED)

    def test_snapshot_reorders_cells_and_rejects_duplicates_and_invalid_values(self):
        cells = [{"index": i, "value": str(v) if v else ""}
                 for i, v in enumerate(sum(PUZZLE.cells, ()))]
        self.assertEqual(board_from_snapshot({"cells": list(reversed(cells))}), PUZZLE)
        cells[1]["index"] = 0
        with self.assertRaises(InvalidDomSnapshot):
            board_from_snapshot({"cells": cells})
        cells[1]["index"] = 1
        cells[0]["value"] = "9"
        with self.assertRaises(InvalidDomSnapshot):
            board_from_snapshot({"cells": cells})

    @patch("lockedin.cli.MiniSudokuBrowserSession.connect_over_cdp")
    def test_cli_is_dry_run_unless_execution_is_requested(self, connect):
        session = connect.return_value
        session.snapshot_board.return_value = PUZZLE
        self.assertEqual(main(["mini-sudoku"]), 0)
        session.execute_actions.assert_not_called()
        self.assertEqual(main(["mini-sudoku", "--execute"]), 0)
        session.execute_actions.assert_called_once()


if __name__ == "__main__":
    unittest.main()
