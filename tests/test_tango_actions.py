import unittest

from lockedin.tango.actions import CellAction, InvalidActionPlan, apply_actions, plan_actions
from lockedin.tango.model import Board, Cell


class TangoActionTests(unittest.TestCase):
    def test_plans_click_counts_for_blank_and_existing_symbols(self) -> None:
        current = Board.from_strings(("?SM???",) + ("??????",) * 5)
        solved = Board.from_strings(("MSMSSM", "SMMSMS", "MSSMSM", "SMSMMS", "SSMMSM", "MSMSMS"))

        actions = plan_actions(current, solved)

        self.assertEqual(
            actions[:4],
            (
                CellAction(0, Cell.MOON, 2),
                CellAction(3, Cell.SUN, 1),
                CellAction(4, Cell.SUN, 1),
                CellAction(5, Cell.MOON, 2),
            ),
        )
        self.assertEqual(apply_actions(current, actions), solved)

    def test_rejects_known_cell_that_differs_from_target(self) -> None:
        solved = Board.from_strings(("SMSMMS", "SSMMSM", "MSMSSM", "SMSMMS", "MMSSMS", "MSMSSM"))
        for given, target in (("M", "S"), ("S", "M")):
            with self.subTest(given=given, target=target):
                index = solved.as_strings()[0].index(target)
                row = list("??????")
                row[index] = given
                current = Board.from_strings(("".join(row),) + ("??????",) * 5)
                with self.assertRaisesRegex(InvalidActionPlan, "known"):
                    plan_actions(current, solved)

    def test_rejects_unknown_in_solution(self) -> None:
        board = Board.from_strings(("??????",) * 6)
        with self.assertRaisesRegex(InvalidActionPlan, "unknown"):
            plan_actions(board, board)