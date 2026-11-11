"""Read, solve and report a Patches board."""

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
    print("Patches board:", current, flush=True)
    plan = plan_board(current)
    print("Patches solution:", plan.solved.patches, flush=True)
    print("Patches to draw:", plan.actions, flush=True)
    return plan
