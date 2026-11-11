"""Validate a path and turn it into keyboard moves."""

from __future__ import annotations

from dataclasses import dataclass

from .model import Board


@dataclass(frozen=True, slots=True)
class ActionPlan:
    board: Board
    path: tuple[int, ...]
    moves: tuple[str, ...]


def create_action_plan(board: Board, path: tuple[int, ...]) -> ActionPlan:
    size = board.rows * board.columns
    if (len(path) != size or any(type(i) is not int or not 0 <= i < size for i in path)
            or len(set(path)) != size or path[0] != board.waypoints[0]):
        raise ValueError("path must visit every cell exactly once, starting at waypoint 1")
    if tuple(i for i in path if i in board.waypoints) != board.waypoints:
        raise ValueError("path must visit the waypoints in order")
    moves = []
    for a, b in zip(path, path[1:]):
        if b not in board.neighbors(a):
            raise ValueError("path crosses a wall or moves between non-adjacent cells")
        ar, ac = divmod(a, board.columns)
        br, bc = divmod(b, board.columns)
        moves.append({(-1, 0): "ArrowUp", (1, 0): "ArrowDown",
                      (0, -1): "ArrowLeft", (0, 1): "ArrowRight"}[(br - ar, bc - ac)])
    return ActionPlan(board, path, tuple(moves))
