"""Plan the clicks needed to place Queens without changing existing marks."""

from __future__ import annotations

from dataclasses import dataclass

from .model import Board, Cell
from .solver import Solver


@dataclass(frozen=True, slots=True)
class CellAction:
    index: int
    clicks: int


@dataclass(frozen=True, slots=True)
class ActionPlan:
    current: Board
    solved: Board
    actions: tuple[CellAction, ...]


def create_action_plan(current: Board, solved: Board) -> ActionPlan:
    if current.regions != solved.regions or Solver().solve(current) != solved:
        raise ValueError("solution does not match the current board")
    actions = tuple(
        CellAction(row * current.size + column, 2)
        for row in range(current.size)
        for column in range(current.size)
        if current.cells[row][column] is Cell.EMPTY and solved.cells[row][column] is Cell.QUEEN
    )
    return ActionPlan(current, solved, actions)
