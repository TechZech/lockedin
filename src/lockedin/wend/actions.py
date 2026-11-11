"""Validate Wend word paths before browser execution."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from .model import Board


@dataclass(frozen=True, slots=True)
class ActionPlan:
    board: Board
    paths: tuple[tuple[int, ...], ...]


def create_action_plan(board: Board, paths: tuple[tuple[int, ...], ...]) -> ActionPlan:
    if not isinstance(paths, tuple) or any(not isinstance(path, tuple) for path in paths):
        raise ValueError("word paths must be tuples")
    if Counter(map(len, paths)) != Counter(board.lengths):
        raise ValueError("word paths do not match the required lengths")
    cells = tuple(cell for path in paths for cell in path)
    if (any(type(i) is not int or not 0 <= i < len(board.letters) or not board.letters[i] for i in cells)
            or len(set(cells)) != len(cells)
            or len(cells) != sum(bool(letter) for letter in board.letters)):
        raise ValueError("word paths must cover each letter exactly once")
    if any(b not in board.neighbors(a) for path in paths for a, b in zip(path, path[1:])):
        raise ValueError("word paths must connect adjacent letters")
    return ActionPlan(board, paths)
