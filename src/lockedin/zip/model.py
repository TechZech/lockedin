"""Immutable representation of a Zip grid."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Board:
    rows: int
    columns: int
    waypoints: tuple[int, ...]
    walls: frozenset[tuple[int, int]] = frozenset()

    def __post_init__(self) -> None:
        if type(self.rows) is not int or type(self.columns) is not int or self.rows < 1 or self.columns < 1:
            raise ValueError("grid dimensions must be positive integers")
        size = self.rows * self.columns
        if not isinstance(self.waypoints, tuple) or not self.waypoints:
            raise ValueError("at least waypoint 1 is required")
        if any(type(i) is not int or not 0 <= i < size for i in self.waypoints):
            raise ValueError("waypoint outside the grid")
        if len(set(self.waypoints)) != len(self.waypoints):
            raise ValueError("waypoints must occupy different cells")
        if not isinstance(self.walls, frozenset):
            raise ValueError("walls must be a frozenset")
        for wall in self.walls:
            if (not isinstance(wall, tuple) or len(wall) != 2
                    or any(type(i) is not int or not 0 <= i < size for i in wall)):
                raise ValueError("invalid wall")
            a, b = wall
            if a >= b or not self.adjacent(a, b):
                raise ValueError("walls must contain ordered adjacent cell indices")

    def adjacent(self, a: int, b: int) -> bool:
        ar, ac = divmod(a, self.columns)
        br, bc = divmod(b, self.columns)
        return abs(ar - br) + abs(ac - bc) == 1

    def neighbors(self, cell: int) -> tuple[int, ...]:
        row, col = divmod(cell, self.columns)
        result = []
        for r, c in ((row - 1, col), (row, col - 1), (row, col + 1), (row + 1, col)):
            other = r * self.columns + c
            if (0 <= r < self.rows and 0 <= c < self.columns
                    and (min(cell, other), max(cell, other)) not in self.walls):
                result.append(other)
        return tuple(result)
