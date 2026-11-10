import unittest

from lockedin.tango.model import Board, Cell, Constraint, InvalidBoard, Relation


class BoardModelTests(unittest.TestCase):
    def test_board_round_trips_text_rows_and_exposes_dimensions(self) -> None:
        board = Board.from_strings(("SM?M?S", "M?S?SM", "?SM?MS", "MS?SM?", "S?MSM?", "?MS?SM"))

        self.assertEqual(board.height, 6)
        self.assertEqual(board.width, 6)
        self.assertIs(board.cell((0, 0)), Cell.SUN)
        self.assertEqual(board.as_strings()[0], "SM?M?S")

    def test_constraint_positions_are_checked(self) -> None:
        constraint = Constraint((0, 0), (6, 0), Relation.EQUAL)
        self.assertRaisesRegex(
            InvalidBoard,
            "outside board",
            Board.from_strings,
            ("??????",) * 6,
            (constraint,),
        )

    def test_constraint_cells_must_be_adjacent(self) -> None:
        constraint = Constraint((0, 0), (0, 2), Relation.EQUAL)

        self.assertRaisesRegex(
            InvalidBoard,
            "must be adjacent",
            Board.from_strings,
            ("??????",) * 6,
            (constraint,),
        )

    def test_board_must_be_6x6(self) -> None:
        self.assertRaisesRegex(
            InvalidBoard,
            "6x6",
            Board.from_strings,
            ("SM?", "M?S", "?SM"),
        )