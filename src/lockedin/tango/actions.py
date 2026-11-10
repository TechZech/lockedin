"""Translate Tango board state changes into cell click actions."""

from __future__ import annotations

from dataclasses import dataclass

from .model import BOARD_SIZE, Board, Cell


class InvalidActionPlan(ValueError):
    """Raised when a current board cannot safely become a solved board."""


@dataclass(frozen=True, slots=True)
class CellAction:
    """The number of clicks needed to set one cell to its target state."""

    index: int
    target: Cell
    clicks: int


@dataclass(frozen=True, slots=True)
class ActionPlan:
    """Keep the original board together with its solution and click actions."""

    current: Board
    solved: Board
    actions: tuple[CellAction, ...]


def create_action_plan(current: Board, solved: Board) -> ActionPlan:
    return ActionPlan(current, solved, plan_actions(current, solved))


def plan_actions(current: Board, solved: Board) -> tuple[CellAction, ...]:
    """Plan minimum clicks from the current board to a solved board.

    Tango cycles through blank -> sun -> moon -> blank. Known cells that do
    not match the solution are rejected instead of being changed blindly.
    """
    if current.constraints != solved.constraints:
        raise InvalidActionPlan("current and solved boards have different constraints")

    actions: list[CellAction] = []
    for row in range(BOARD_SIZE):
        for column in range(BOARD_SIZE):
            current_cell = current.cell((row, column))
            target = solved.cell((row, column))
            clicks = _click_count(current_cell, target)
            if clicks:
                actions.append(CellAction(row * BOARD_SIZE + column, target, clicks))
    return tuple(actions)


def apply_actions(current: Board, actions: tuple[CellAction, ...]) -> Board:
    """Simulate planned clicks and return the resulting logical board."""
    cells = [list(row) for row in current.cells]
    for action in actions:
        row, column = divmod(action.index, BOARD_SIZE)
        state = cells[row][column]
        for _ in range(action.clicks):
            state = {
                Cell.UNKNOWN: Cell.SUN,
                Cell.SUN: Cell.MOON,
                Cell.MOON: Cell.UNKNOWN,
            }[state]
        cells[row][column] = state
    return Board(tuple(tuple(row) for row in cells), current.constraints)


def _click_count(current: Cell, target: Cell) -> int:
    if target is Cell.UNKNOWN:
        raise InvalidActionPlan("solved board cannot contain unknown cells")
    if current is target:
        return 0
    if current is Cell.UNKNOWN:
        return 1 if target is Cell.SUN else 2
    raise InvalidActionPlan(
        f"known {current.value} cell does not match target {target.value}"
    )