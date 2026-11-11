import json
import unittest

from lockedin.wend.actions import create_action_plan
from lockedin.wend.dom import snapshot_from_json
from lockedin.wend.model import Board
from lockedin.wend.solver import Solver


class WendSolverTests(unittest.TestCase):
    def test_exact_cover_with_wall_and_repeated_lengths(self):
        board = Board(2, 4, ("C", "A", "T", "", "D", "O", "G", ""), (3, 3))
        paths = Solver(["CAT", "DOG"]).solve(board)
        self.assertEqual(set(paths), {(0, 1, 2), (4, 5, 6)})
        self.assertEqual(create_action_plan(board, paths).paths, paths)

    def test_reversed_paths_are_distinct_solutions(self):
        board = Board(1, 3, ("C", "A", "T"), (3,))
        with self.assertRaisesRegex(ValueError, "multiple"):
            Solver(["CAT", "TAC"]).solve(board)
        self.assertEqual(set(Solver(["CAT", "TAC"]).solutions(board)), {((0, 1, 2),), ((2, 1, 0),)})

    def test_no_solution_and_invalid_paths(self):
        board = Board(2, 3, ("C", "A", "T", "D", "O", "G"), (3, 3))
        with self.assertRaisesRegex(ValueError, "no solution"):
            Solver(["CAT"]).solve(board)
        with self.assertRaisesRegex(ValueError, "adjacent"):
            create_action_plan(board, ((0, 2, 1), (3, 4, 5)))
        with self.assertRaisesRegex(ValueError, "exactly once"):
            create_action_plan(board, ((0, 1, 2), (2, 4, 5)))

    def test_missing_word_is_not_invented(self):
        board = Board(1, 3, ("C", "A", "T"), (3,))
        self.assertEqual(list(Solver(["DOG"]).solutions(board)), [])

    def test_search_supports_cancellation(self):
        board = Board(1, 3, ("C", "A", "T"), (3,))
        def stop():
            raise RuntimeError("cancelled")
        with self.assertRaisesRegex(RuntimeError, "cancelled"):
            list(Solver(["CAT"]).solutions(board, check=stop))

    def test_invalid_board_rejected(self):
        with self.assertRaisesRegex(ValueError, "word lengths"):
            Board(1, 3, ("C", "A", "T"), (2,))
        with self.assertRaisesRegex(ValueError, "uppercase"):
            Board(1, 3, ("C", "a", "T"), (3,))


class WendSnapshotTests(unittest.TestCase):
    def test_snapshot_parses_holes_lengths_and_locked_tiles(self):
        value = json.dumps({
            "rows": 1, "columns": 4,
            "cells": [{"index": i, "letter": letter, "locked": i == 0}
                      for i, letter in enumerate(("C", "A", "T", ""))],
            "slots": [["C", "A", "T"]],
        })
        snapshot = snapshot_from_json(value)
        self.assertEqual(snapshot.board, Board(1, 4, ("C", "A", "T", ""), (3,)))
        self.assertEqual(snapshot.locked, frozenset({0}))
        self.assertEqual(snapshot.words, ("CAT",))

    def test_duplicate_cell_rejected(self):
        value = json.dumps({"rows": 1, "columns": 2, "cells": [
            {"index": 0, "letter": "A", "locked": False},
            {"index": 0, "letter": "B", "locked": False},
        ], "slots": [["", ""]]})
        with self.assertRaisesRegex(ValueError, "duplicate"):
            snapshot_from_json(value)
