"""Read, solve and report a Mini Sudoku board."""

from __future__ import annotations

from typing import Protocol

from .actions import ActionPlan, create_action_plan
from .model import Board
from .solver import Solver


class BoardReader(Protocol):
    def snapshot_board(self) -> Board: ...


def plan_board(current: Board) -> ActionPlan:
    return create_action_plan(current, Solver().solve(current))


def solve_and_report(session: BoardReader) -> ActionPlan:
    current = session.snapshot_board()
    print("Current board:", *current.as_strings(), sep="\n", flush=True)
    plan = plan_board(current)
    print("\nSolved board:", *plan.solved.as_strings(), sep="\n", flush=True)
    print("\nAction plan:", flush=True)
    for action in plan.actions:
        print(f"cell {action.index} -> {action.target}", flush=True)
    if not plan.actions:
        print("No actions needed; board is already solved.", flush=True)
    return plan
