"""Immutable Wend board."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Board:
    rows: int
    columns: int
    letters: tuple[str, ...]
    lengths: tuple[int, ...]

    def __post_init__(self) -> None:
        if type(self.rows) is not int or type(self.columns) is not int or self.rows < 1 or self.columns < 1:
            raise ValueError("grid dimensions must be positive integers")
        if not isinstance(self.letters, tuple) or len(self.letters) != self.rows * self.columns:
            raise ValueError("letters must contain one entry per grid cell")
        if any(not isinstance(c, str) or (c and (len(c) != 1 or not c.isascii() or not c.isupper()))
               for c in self.letters):
            raise ValueError("cells must contain an uppercase ASCII letter or an empty wall")
        if (not isinstance(self.lengths, tuple) or not self.lengths
                or any(type(n) is not int or n < 2 for n in self.lengths)
                or sum(self.lengths) != sum(bool(c) for c in self.letters)):
            raise ValueError("word lengths must cover every letter exactly once")

    def neighbors(self, index: int) -> tuple[int, ...]:
        row, col = divmod(index, self.columns)
        return tuple(r * self.columns + c for r, c in
                     ((row - 1, col), (row, col - 1), (row, col + 1), (row + 1, col))
                     if 0 <= r < self.rows and 0 <= c < self.columns and self.letters[r * self.columns + c])
