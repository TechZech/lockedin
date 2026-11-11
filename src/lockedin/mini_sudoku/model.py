"""UI-independent Mini Sudoku board."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

BOARD_SIZE = 6


class InvalidBoard(ValueError):
    """A board has invalid dimensions or values."""


@dataclass(frozen=True, slots=True)
class Board:
    cells: tuple[tuple[int, ...], ...]

    def __post_init__(self) -> None:
        if len(self.cells) != BOARD_SIZE or any(len(row) != BOARD_SIZE for row in self.cells):
            raise InvalidBoard("Mini Sudoku boards must be 6x6")
        if any(type(value) is not int or not 0 <= value <= 6 for row in self.cells for value in row):
            raise InvalidBoard("cells must be integers from 0 to 6")

    def cell(self, position: tuple[int, int]) -> int:
        row, column = position
        if not (0 <= row < BOARD_SIZE and 0 <= column < BOARD_SIZE):
            raise InvalidBoard(f"position outside board: {position}")
        return self.cells[row][column]

    @classmethod
    def from_strings(cls, rows: Sequence[str]) -> Board:
        if len(rows) != BOARD_SIZE or any(len(row) != BOARD_SIZE for row in rows):
            raise InvalidBoard("Mini Sudoku boards must be 6x6")
        if any(character not in "0123456?." for row in rows for character in row):
            raise InvalidBoard("rows may only contain digits 1-6 and 0, ? or . for blanks")
        return cls(tuple(tuple(int(c) if c in "123456" else 0 for c in row) for row in rows))

    def as_strings(self) -> tuple[str, ...]:
        return tuple("".join(str(value) if value else "?" for value in row) for row in self.cells)
