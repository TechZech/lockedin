"""Plan cell and keypad actions for Mini Sudoku."""

from __future__ import annotations

from dataclasses import dataclass

from .model import BOARD_SIZE, Board
from .solver import Solver


@dataclass(frozen=True, slots=True)
class CellAction:
    index: int
    target: int


@dataclass(frozen=True, slots=True)
class ActionPlan:
    current: Board
    solved: Board
    actions: tuple[CellAction, ...]


def create_action_plan(current: Board, solved: Board) -> ActionPlan:
    if any(value == 0 for row in solved.cells for value in row) or Solver().solve(solved) != solved:
        raise ValueError("solution must be a complete valid board")
    actions = []
    for row in range(BOARD_SIZE):
        for column in range(BOARD_SIZE):
            existing, target = current.cells[row][column], solved.cells[row][column]
            if existing and existing != target:
                raise ValueError(f"existing cell {row * BOARD_SIZE + column} differs from solution")
            if not existing:
                actions.append(CellAction(row * BOARD_SIZE + column, target))
    return ActionPlan(current, solved, tuple(actions))
