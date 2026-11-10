import unittest

from lockedin.tango.dom import InvalidDomSnapshot, board_from_snapshot
from lockedin.tango.model import Constraint, Relation


class TangoDomTests(unittest.TestCase):
    def test_snapshot_converts_cells_and_relations_to_board(self) -> None:
        cells = [{"index": index, "state": "?"} for index in range(36)]
        cells[0]["state"] = "S"
        cells[1]["state"] = "M"
        board = board_from_snapshot(
            {
                "cells": cells,
                "relations": [{"first": 1, "second": 7, "type": "Equal"}],
            }
        )

        self.assertEqual(board.as_strings()[0], "SM????")
        self.assertEqual(board.constraints, (Constraint((0, 1), (1, 1), Relation.EQUAL),))

    def test_snapshot_requires_36_cells(self) -> None:
        with self.assertRaises(InvalidDomSnapshot):
            board_from_snapshot({"cells": []})

    def test_snapshot_rejects_duplicate_indexes(self) -> None:
        cells = [{"index": index, "state": "?"} for index in range(36)]
        cells[-1]["index"] = 0

        with self.assertRaises(InvalidDomSnapshot):
            board_from_snapshot({"cells": cells})

    def test_solved_august_21_relations_match_the_board(self) -> None:
        states = "SMSMMS" "SSMMSM" "MSMSSM" "SMSMMS" "MMSSMS" "MSMSSM"
        cells = [{"index": index, "state": state} for index, state in enumerate(states)]
        board = board_from_snapshot(
            {
                "cells": cells,
                "relations": [
                    {"first": 7, "second": 13, "type": "Equal"},
                    {"first": 13, "second": 14, "type": "Cross"},
                    {"first": 21, "second": 22, "type": "Equal"},
                    {"first": 22, "second": 28, "type": "Equal"},
                ],
            }
        )

        self.assertEqual(board.as_strings(), ("SMSMMS", "SSMMSM", "MSMSSM", "SMSMMS", "MMSSMS", "MSMSSM"))