"""Read, solve and report a Zip board."""

from __future__ import annotations

from typing import Protocol

from .actions import ActionPlan, create_action_plan
from .model import Board
from .solver import Solver


class BoardReader(Protocol):
    def snapshot_board(self) -> Board: ...


def plan_board(board: Board) -> ActionPlan:
    return create_action_plan(board, Solver().solve(board))


def solve_and_report(session: BoardReader) -> ActionPlan:
    board = session.snapshot_board()
    print(f"Zip board: {board.rows}x{board.columns}", flush=True)
    print(f"Waypoints: {board.waypoints}; walls: {sorted(board.walls)}", flush=True)
    plan = plan_board(board)
    print(f"Path: {plan.path}", flush=True)
    print(f"Moves: {plan.moves}", flush=True)
    return plan
