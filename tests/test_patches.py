import json

import pytest

from lockedin.patches.actions import create_action_plan
from lockedin.patches.dom import board_from_json
from lockedin.patches.model import Board, Clue, Patch, Shape
from lockedin.patches.solver import AmbiguousPuzzle, Solver, UnsolvablePuzzle


def test_shape_and_area_constraints():
    for shape, valid, invalid in (
        (Shape.SQUARE, Patch(0, 0, 1, 1), Patch(0, 0, 0, 1)),
        (Shape.WIDE, Patch(0, 0, 0, 1), Patch(0, 0, 1, 0)),
        (Shape.TALL, Patch(0, 0, 1, 0), Patch(0, 0, 0, 1)),
        (Shape.FREEFORM, Patch(0, 0, 1, 1), Patch(1, 1, 1, 1)),
    ):
        board = Board(2, 2, (Clue(0, shape),))
        assert board.valid_patch(valid)
        assert not board.valid_patch(invalid)
    board = Board(2, 2, (Clue(0, Shape.FREEFORM, 2),))
    assert board.valid_patch(Patch(0, 0, 0, 1))
    assert not board.valid_patch(Patch(0, 0, 1, 1))


def test_solver_covers_board_preserves_existing_patch_and_plans_only_missing():
    existing = Patch(0, 0, 0, 2)
    board = Board(2, 3, (Clue(0, Shape.WIDE, 3), Clue(5, Shape.WIDE, 3)), (existing,))
    solved = Solver().solve(board)
    assert solved.patches == (existing, Patch(1, 0, 1, 2))
    assert create_action_plan(board, solved).actions == (Patch(1, 0, 1, 2),)
    assert create_action_plan(solved, solved).actions == ()


def test_solver_handles_shape_only_and_single_cell_clues():
    board = Board(2, 2, (Clue(0, Shape.SQUARE),))
    assert Solver().solve(board).patches == (Patch(0, 0, 1, 1),)
    board = Board(1, 1, (Clue(0, Shape.FREEFORM, 1),))
    assert Solver().solve(board).patches == (Patch(0, 0, 0, 0),)


def test_unsolvable_and_ambiguous_boards_are_rejected():
    with pytest.raises(UnsolvablePuzzle):
        Solver().solve(Board(1, 3, (Clue(0, Shape.FREEFORM, 2),)))
    with pytest.raises(AmbiguousPuzzle):
        Solver().solve(Board(2, 2, (Clue(0, Shape.FREEFORM), Clue(3, Shape.FREEFORM))))


def test_invalid_patches_and_invalid_solution_are_rejected():
    clues = (Clue(0, Shape.FREEFORM), Clue(3, Shape.FREEFORM))
    with pytest.raises(ValueError, match="invalid or overlap"):
        Board(2, 2, clues, (Patch(0, 0, 1, 1),))
    with pytest.raises(ValueError, match="invalid or overlap"):
        Board(2, 2, clues, (Patch(0, 0, 0, 1), Patch(0, 1, 1, 1)))
    board = Board(2, 2, clues)
    with pytest.raises(ValueError, match="cover"):
        create_action_plan(board, board)
    with pytest.raises(ValueError, match="duplicate clue"):
        Board(2, 2, (clues[0], clues[0]))


def snapshot(labels, rows, columns):
    return json.dumps({"rows": rows, "columns": columns,
                       "cells": [{"index": i, "label": label} for i, label in enumerate(labels)]})


def test_parse_accessible_clues_and_drawn_region():
    data = snapshot([
        "Row 1, column 1, wide rectangle clue, 2 cells, in drawn region",
        "Row 1, column 2, in region with clue at row 1, column 1",
        "Row 2, column 1, square clue",
        "Row 2, column 2",
    ], 2, 2)
    board = board_from_json(data)
    assert board.clues == (Clue(0, Shape.WIDE, 2), Clue(2, Shape.SQUARE))
    assert board.patches == (Patch(0, 0, 0, 1),)


@pytest.mark.parametrize("labels", [
    ["Row 1, column 1, freeform clue, 2 cells, in drawn region",
     "Row 1, column 2, in region with clue at row 2, column 1"],
    ["Row 1, column 1, mysterious clue", "Row 1, column 2"],
    ["Row 1, column 2, freeform clue, 2 cells", "Row 1, column 2"],
    ["Row 1, column 1, freeform clue, 2 cells, in drawn region", "Row 1, column 2"],
])
def test_parse_rejects_unrecognized_or_incomplete_state(labels):
    with pytest.raises(ValueError):
        board_from_json(snapshot(labels, 1, 2))


def test_parse_rejects_nonrectangular_region():
    data = snapshot([
        "Row 1, column 1, freeform clue, in drawn region",
        "Row 1, column 2, in region with clue at row 1, column 1",
        "Row 2, column 1, in region with clue at row 1, column 1",
        "Row 2, column 2",
    ], 2, 2)
    with pytest.raises(ValueError, match="not rectangular"):
        board_from_json(data)
