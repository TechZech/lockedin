"""Shared board-solving and reporting workflow for Tango entry points."""

from __future__ import annotations

import sys
from typing import Protocol

from .actions import ActionPlan, CellAction, create_action_plan
from .model import Board
from .solver import DeductionStalled, Solver


class BoardReader(Protocol):
    def snapshot_board(self) -> Board: ...


def plan_board(current: Board) -> ActionPlan:
    """Solve a board and produce its click plan without browser access."""
    return create_action_plan(current, Solver().solve(current))


def solve_and_report(session: BoardReader) -> ActionPlan:
    """Read, solve and print a board without interacting with its cells."""
    current = session.snapshot_board()
    print("Current board:", flush=True)
    print("\n".join(current.as_strings()), flush=True)
    try:
        plan = plan_board(current)
    except DeductionStalled:
        print("\nSolver status: deduction stalled.", file=sys.stderr)
        print("Check that all relation markers were extracted from the board.", file=sys.stderr)
        raise
    print("\nSolved board:", flush=True)
    print("\n".join(plan.solved.as_strings()), flush=True)
    print("\nClick plan:", flush=True)
    if plan.actions:
        for action in plan.actions:
            print(_format_action(action), flush=True)
    else:
        print("No clicks needed; board is already solved.", flush=True)
    return plan


def _format_action(action: CellAction) -> str:
    target = "SUN" if action.target.value == "S" else "MOON"
    return f"cell {action.index} -> {target} ({action.clicks} click{'s' if action.clicks != 1 else ''})"
