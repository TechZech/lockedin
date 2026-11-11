import json
from itertools import permutations

import pytest

from lockedin.queens.actions import create_action_plan
from lockedin.queens.dom import InvalidDomSnapshot, board_from_json, board_from_snapshot
from lockedin.queens.model import Board, Cell, InvalidBoard
from lockedin.queens.solver import AmbiguousPuzzle, Solver, UnsolvablePuzzle


REGIONS = tuple(tuple(str(row) for _ in range(4)) for row in range(4))


def board(*marks):
    cells = [[Cell.EMPTY] * 4 for _ in range(4)]
    for row, column, value in marks:
        cells[row][column] = value
    return Board(REGIONS, tuple(tuple(row) for row in cells))


def test_unique_solution_preserves_marks_and_allows_distant_diagonal_queens():
    current = board((0, 2, Cell.CROSS))
    solution = Solver().solve(current)
    assert solution.as_strings() == (".QX.", "...Q", "Q...", "..Q.")
    assert create_action_plan(current, solution).actions[0].index == 1
    assert all(action.clicks == 2 for action in create_action_plan(current, solution).actions)
    assert Solver().solve(solution) == solution


def test_existing_queen_is_preserved_and_already_solved_has_no_actions():
    current = board((0, 1, Cell.QUEEN))
    solved = Solver().solve(current)
    assert solved.as_strings() == (".Q..", "...Q", "Q...", "..Q.")
    assert len(create_action_plan(current, solved).actions) == 3
    assert not create_action_plan(solved, solved).actions


def test_ambiguous_invalid_and_conflicting_marks_are_rejected():
    with pytest.raises(AmbiguousPuzzle):
        Solver().solve(board())
    with pytest.raises(UnsolvablePuzzle):
        Solver().solve(board((0, 1, Cell.QUEEN), (1, 2, Cell.QUEEN)))
    with pytest.raises(UnsolvablePuzzle):
        Solver().solve(board(*[(0, c, Cell.CROSS) for c in range(4)]))
    with pytest.raises(InvalidBoard):
        Board((("one", "one"), ("one", "one")), ((Cell.EMPTY,) * 2,) * 2)


def test_plan_rejects_solution_and_regions_not_matching_current():
    current = board((0, 2, Cell.CROSS))
    with pytest.raises(ValueError):
        create_action_plan(current, board((0, 1, Cell.QUEEN)))
    other = Board(tuple(tuple(f"region{row}" for _ in range(4)) for row in range(4)), current.cells)
    with pytest.raises(ValueError):
        create_action_plan(current, other)


@pytest.mark.parametrize("region_rows", [
    ("AABC", "AABC", "DDBC", "DDBC"),
    ("ABCD", "ABCD", "ABCD", "ABCD"),
    ("AAAB", "CCAB", "CCBB", "DDDD"),
])
def test_solver_matches_exhaustive_search_for_region_layouts(region_rows):
    regions = tuple(tuple(row) for row in region_rows)
    current = Board(regions, ((Cell.EMPTY,) * 4,) * 4)
    solutions = [
        columns for columns in permutations(range(4))
        if all(abs(columns[row] - columns[row + 1]) > 1 for row in range(3))
        and len({regions[row][column] for row, column in enumerate(columns)}) == 4
    ]
    if not solutions:
        with pytest.raises(UnsolvablePuzzle):
            Solver().solve(current)
    elif len(solutions) > 1:
        with pytest.raises(AmbiguousPuzzle):
            Solver().solve(current)
    else:
        solved = Solver().solve(current)
        assert tuple(row.index(Cell.QUEEN) for row in solved.cells) == solutions[0]


def snapshot():
    return {"cells": [
        {"index": row * 4 + column,
         "label": f"Empty cell of color {row}, row {row + 1}, column {column + 1}"}
        for row in range(4) for column in range(4)
    ]}


def test_snapshot_accepts_unordered_cells_and_all_states():
    data = snapshot()
    data["cells"][2]["label"] = "Cross of color 0, row 1, column 3"
    data["cells"][1]["label"] = "Queen of color 0, row 1, column 2"
    data["cells"].reverse()
    assert board_from_json(json.dumps(data)) == board((0, 1, Cell.QUEEN), (0, 2, Cell.CROSS))


@pytest.mark.parametrize("change", ["duplicate", "bad-label", "bad-coordinates", "not-square"])
def test_snapshot_rejects_bad_data(change):
    data = snapshot()
    if change == "duplicate":
        data["cells"][1]["index"] = 0
    elif change == "bad-label":
        data["cells"][0]["label"] = "unknown"
    elif change == "bad-coordinates":
        data["cells"][0]["label"] = "Empty cell of color 0, row 2, column 1"
    else:
        data["cells"].pop()
    with pytest.raises(InvalidDomSnapshot):
        board_from_snapshot(data)
