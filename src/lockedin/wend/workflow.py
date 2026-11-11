"""Read, solve and report a Wend board."""

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
    print(f"Wend board: {board.rows}x{board.columns}; word lengths: {board.lengths}", flush=True)
    plan = plan_board(board)
    print("Dictionary candidate (not verified against LinkedIn's hidden words):", flush=True)
    for path in plan.paths:
        print(f"{''.join(board.letters[i] for i in path)}: {path}", flush=True)
    return plan
