import unittest

from lockedin.tango.model import Board, Constraint, Relation
from lockedin.tango.actions import apply_actions, plan_actions
from lockedin.tango.solver import DeductionStalled, Solver, UnsolvablePuzzle

class TangoSolverTests(unittest.TestCase):
    def test_rejects_a_contradictory_board(self) -> None:
        board = Board.from_strings(("SSS?MM", "M?M?S?", "SM?MS?", "MS?SM?", "S?MSM?", "?MS?SM"))

        self.assertRaises(UnsolvablePuzzle, Solver().solve, board)

    def test_reports_when_deduction_stalls(self) -> None:
        board = Board.from_strings(("??????",) * 6)

        self.assertRaises(DeductionStalled, Solver().solve, board)

    def test_relation_can_use_no_three_rule_to_eliminate_a_pair(self) -> None:
        board = Board.from_strings(
            ("??M???", "SSMSMM", "MMSSMS", "SSMMSM", "MMSSMS", "MMSMSS"),
            (Constraint((0, 0), (0, 1), Relation.EQUAL),),
        )

        solved = Solver().solve(board)

        self.assertEqual(solved.as_strings()[0], "SSMMSM")

    def test_matching_endpoints_force_opposite_inner_cells(self) -> None:
        board = Board.from_strings(
            ("M???SM", "SSMSMM", "SMSMMS", "MSSMSM", "SMMSMS", "MMSMSS"),
        )

        solved = Solver().solve(board)

        self.assertEqual(solved.as_strings()[0], "MSMSSM")

    def test_equal_pair_at_opposite_end_from_known_cell(self) -> None:
        board = Board.from_strings(
            ("?????M", "SSMSMM", "MMSSMS", "SSMMSM", "MMSSMS", "MMSMSS"),
            (Constraint((0, 0), (0, 1), Relation.EQUAL),),
        )

        solved = Solver().solve(board)

        self.assertEqual(solved.as_strings()[0], "SSMMSM")

    def test_august_21_2026_puzzle(self) -> None:
        board = Board.from_strings(
            ("S?????", "S?????", "???S??", "??S???", "?????S", "?????M"),
            (
                Constraint((1, 1), (2, 1), Relation.EQUAL),
                Constraint((2, 1), (2, 2), Relation.OPPOSITE),
                Constraint((3, 3), (3, 4), Relation.EQUAL),
                Constraint((3, 4), (4, 4), Relation.EQUAL),
            ),
        )

        solved = Solver().solve(board)

        self.assertEqual(
            solved.as_strings(),
            ("SMSMMS", "SSMMSM", "MSMSSM", "SMSMMS", "MMSSMS", "MSMSSM"),
        )
        self.assertEqual(apply_actions(board, plan_actions(board, solved)), solved)

    def test_august_20_2026_puzzle(self) -> None:
        board = Board.from_strings(
            ("?????M", "????M?", "???M??", "??M???", "?M????", "M?????"),
            (
                Constraint((0, 0), (0, 1), Relation.EQUAL),
                Constraint((0, 0), (1, 0), Relation.EQUAL),
                Constraint((0, 1), (1, 1), Relation.EQUAL),
                Constraint((1, 0), (1, 1), Relation.EQUAL),
                Constraint((4, 4), (4, 5), Relation.EQUAL),
                Constraint((4, 4), (5, 4), Relation.OPPOSITE),
                Constraint((4, 5), (5, 5), Relation.EQUAL),
                Constraint((5, 4), (5, 5), Relation.OPPOSITE),
            ),
        )

        solved = Solver().solve(board)

        self.assertEqual(
            solved.as_strings(),
            ("SSMMSM", "SSMSMM", "MMSMSS", "SSMSMM", "MMSMSS", "MMSSMS"),
        )
        self.assertEqual(apply_actions(board, plan_actions(board, solved)), solved)

    def test_august_19_2026_puzzle(self) -> None:
        board = Board.from_strings(
            ("M??M?M", "??????", "M?????", "?????M", "??????", "M?M??M"),
            (
                Constraint((1, 4), (2, 4), Relation.EQUAL),
                Constraint((3, 1), (4, 1), Relation.OPPOSITE),
            ),
        )

        solved = Solver().solve(board)

        self.assertEqual(
            solved.as_strings(),
            ("MSSMSM", "SMMSMS", "MMSSMS", "SSMMSM", "SMSMMS", "MSMSSM"),
        )
        self.assertEqual(apply_actions(board, plan_actions(board, solved)), solved)

    def test_august_18_2026_puzzle(self) -> None:
        board = Board.from_strings(
            ("SM??MM", "M????S", "??????", "??????", "M????M", "MS??MS"),
            (
                Constraint((1, 1), (1, 2), Relation.OPPOSITE),
                Constraint((1, 2), (1, 3), Relation.OPPOSITE),
                Constraint((1, 3), (1, 4), Relation.OPPOSITE),
                Constraint((2, 1), (3, 1), Relation.OPPOSITE),
                Constraint((2, 4), (3, 4), Relation.OPPOSITE),
                Constraint((4, 1), (4, 2), Relation.EQUAL),
                Constraint((4, 2), (4, 3), Relation.OPPOSITE),
                Constraint((4, 3), (4, 4), Relation.OPPOSITE),
            ),
        )

        solved = Solver().solve(board)

        self.assertEqual(
            solved.as_strings(),
            ("SMSSMM", "MMSMSS", "SSMMSM", "SMMSMS", "MSSMSM", "MSMSMS"),
        )
        self.assertEqual(apply_actions(board, plan_actions(board, solved)), solved)

    def test_august_17_2026_puzzle(self) -> None:
        board = Board.from_strings(
            ("??S???", "?SSM??", "??????", "??????", "??MSM?", "???M??"),
            (
                Constraint((2, 0), (2, 1), Relation.OPPOSITE),
                Constraint((2, 1), (2, 2), Relation.OPPOSITE),
                Constraint((2, 2), (2, 3), Relation.OPPOSITE),
                Constraint((2, 3), (2, 4), Relation.EQUAL),
                Constraint((3, 1), (3, 2), Relation.OPPOSITE),
                Constraint((3, 2), (3, 3), Relation.OPPOSITE),
                Constraint((3, 3), (3, 4), Relation.OPPOSITE),
                Constraint((3, 4), (3, 5), Relation.OPPOSITE),
            ),
        )

        solved = Solver().solve(board)

        self.assertEqual(
            solved.as_strings(),
            ("SMSSMM", "MSSMMS", "MSMSSM", "SMSMSM", "SMMSMS", "MSMMSS"),
        )
        self.assertEqual(apply_actions(board, plan_actions(board, solved)), solved)

    def test_new_puzzle_requires_terminal_pair_rule(self) -> None:
        board = Board.from_strings(
            ("??MM??", "??????", "??????", "???MSS", "??????", "MS??MS"),
            (
                Constraint((0, 0), (0, 1), Relation.OPPOSITE),
                Constraint((0, 4), (0, 5), Relation.EQUAL),
                Constraint((2, 0), (2, 1), Relation.OPPOSITE),
                Constraint((2, 1), (2, 2), Relation.EQUAL),
                Constraint((5, 2), (5, 3), Relation.OPPOSITE),
            ),
        )

        solved = Solver().solve(board)

        self.assertEqual(
            solved.as_strings(),
            ("MSMMSS", "SMSSMM", "SMMSSM", "MSMMSS", "SMSSMM", "MSSMMS"),
        )
        self.assertEqual(apply_actions(board, plan_actions(board, solved)), solved)

    def test_mixed_chain_puzzle_with_vertical_and_horizontal_relations(self) -> None:
        board = Board.from_strings(
            ("S?????", "??????", "??????", "??????", "??????", "??????"),
            (
                Constraint((0, 1), (0, 2), Relation.OPPOSITE),
                Constraint((0, 2), (0, 3), Relation.EQUAL),
                Constraint((0, 3), (0, 4), Relation.OPPOSITE),
                Constraint((0, 4), (1, 4), Relation.EQUAL),
                Constraint((1, 0), (2, 0), Relation.OPPOSITE),
                Constraint((1, 4), (2, 4), Relation.OPPOSITE),
                Constraint((2, 0), (3, 0), Relation.OPPOSITE),
                Constraint((2, 4), (3, 4), Relation.EQUAL),
                Constraint((3, 0), (4, 0), Relation.EQUAL),
                Constraint((3, 4), (4, 4), Relation.OPPOSITE),
                Constraint((4, 0), (4, 1), Relation.OPPOSITE),
                Constraint((4, 1), (4, 2), Relation.OPPOSITE),
                Constraint((4, 2), (4, 3), Relation.OPPOSITE),
                Constraint((4, 3), (4, 4), Relation.EQUAL),
            ),
        )

        solved = Solver().solve(board)

        self.assertEqual(
            solved.as_strings(),
            ("SSMMSM", "MSMSSM", "SMSMMS", "MMSSMS", "MSMSSM", "SMSMMS"),
        )
        self.assertEqual(apply_actions(board, plan_actions(board, solved)), solved)
