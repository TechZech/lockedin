import json
import unittest
from itertools import combinations
from unittest.mock import patch

from lockedin.cli import main
from lockedin.zip.actions import ActionPlan, create_action_plan
from lockedin.zip.dom import snapshot_from_json
from lockedin.zip.model import Board
from lockedin.zip.solver import Solver


class ZipSolverTests(unittest.TestCase):
    def test_solver_handles_waypoints_and_walls(self):
        board = Board(3, 3, (0, 4, 8), frozenset({(1, 2), (4, 5)}))
        path = Solver().solve(board)
        plan = create_action_plan(board, path)
        self.assertEqual(len(plan.path), 9)
        self.assertEqual(tuple(i for i in path if i in board.waypoints), board.waypoints)
        self.assertEqual(len(plan.moves), 8)

    def test_solver_reports_unsolvable_board(self):
        board = Board(2, 2, (0, 3), frozenset({(0, 1), (0, 2)}))
        with self.assertRaisesRegex(ValueError, "no solution"):
            Solver().solve(board)

    def test_solver_matches_brute_force_for_small_boards(self):
        edges = [(0, 1), (1, 2), (3, 4), (4, 5), (0, 3), (1, 4), (2, 5)]

        def brute(board, path):
            if len(path) == 6:
                return tuple(i for i in path if i in board.waypoints) == board.waypoints
            return any(brute(board, path + [n]) for n in board.neighbors(path[-1]) if n not in path)

        for wall_count in range(3):
            for walls in combinations(edges, wall_count):
                for start, end in combinations(range(6), 2):
                    board = Board(2, 3, (start, end), frozenset(walls))
                    possible = brute(board, [start])
                    try:
                        path = Solver().solve(board)
                    except ValueError:
                        self.assertFalse(possible, board)
                    else:
                        self.assertTrue(possible, board)
                        create_action_plan(board, path)

    def test_rejects_invalid_walls_and_paths(self):
        with self.assertRaises(ValueError):
            Board(2, 2, (0, 1), frozenset({(1, 2)}))
        board = Board(2, 2, (0, 3), frozenset({(0, 1)}))
        for path in ((0, 1, 3, 2), (0, 2, 1, 3), (0, 2, 3, 3), (3, 2, 0, 1)):
            with self.subTest(path=path), self.assertRaises(ValueError):
                create_action_plan(board, path)

    def test_single_cell(self):
        self.assertEqual(create_action_plan(Board(1, 1, (0,)), Solver().solve(Board(1, 1, (0,)))).moves, ())


class ZipSnapshotTests(unittest.TestCase):
    def test_snapshot_reconstructs_walls_and_waypoints(self):
        cells = [
            {"index": i, "clue": {0: "1", 3: "2"}.get(i, ""), "filled": i == 0,
             "right": i == 0, "down": i == 1}
            for i in range(4)
        ]
        snapshot = snapshot_from_json(json.dumps({"rows": 2, "columns": 2, "cells": cells}))
        self.assertEqual(snapshot.board, Board(2, 2, (0, 3), frozenset({(0, 1), (1, 3)})))
        self.assertEqual(snapshot.filled, frozenset({0}))

    def test_rejects_duplicate_missing_and_invalid_clues(self):
        cells = [{"index": i, "clue": v, "filled": False, "right": False, "down": False}
                 for i, v in enumerate(("1", "3"))]
        with self.assertRaises(ValueError):
            snapshot_from_json(json.dumps({"rows": 1, "columns": 2, "cells": cells}))
        cells[1]["clue"] = "1"
        with self.assertRaises(ValueError):
            snapshot_from_json(json.dumps({"rows": 1, "columns": 2, "cells": cells}))


class ZipCliTests(unittest.TestCase):
    @patch("lockedin.cli.ZipBrowserSession.connect_over_cdp")
    def test_dry_run_and_explicit_execution(self, connect):
        board = Board(2, 2, (0, 1))
        session = connect.return_value
        session.snapshot_board.return_value = board
        self.assertEqual(main(["zip"]), 0)
        session.execute_actions.assert_not_called()
        self.assertEqual(main(["zip", "--execute"]), 0)
        self.assertIsInstance(session.execute_actions.call_args.args[0], ActionPlan)
