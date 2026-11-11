"""Validate and plan rectangle placements."""

from __future__ import annotations

from dataclasses import dataclass

from .model import Board, Patch


@dataclass(frozen=True, slots=True)
class ActionPlan:
    current: Board
    solved: Board
    actions: tuple[Patch, ...]


def create_action_plan(current: Board, solved: Board) -> ActionPlan:
    if (current.rows != solved.rows or current.columns != solved.columns
            or current.clues != solved.clues or not set(current.patches) <= set(solved.patches)):
        raise ValueError("solution does not preserve the current board")
    covered = set().union(*(patch.cells(solved.columns) for patch in solved.patches))
    if len(covered) != solved.rows * solved.columns:
        raise ValueError("solution does not cover the board")
    return ActionPlan(current, solved, tuple(p for p in solved.patches if p not in current.patches))
