"""UI-independent Queens board."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class InvalidBoard(ValueError):
    """A board has invalid dimensions, regions, or cell states."""


class Cell(Enum):
    EMPTY = "empty"
    CROSS = "cross"
    QUEEN = "queen"


@dataclass(frozen=True, slots=True)
class Board:
    regions: tuple[tuple[str, ...], ...]
    cells: tuple[tuple[Cell, ...], ...]

    def __post_init__(self) -> None:
        size = len(self.regions)
        if not 1 <= size <= 16 or len(self.cells) != size:
            raise InvalidBoard("Queens boards must be square with a size from 1 to 16")
        if any(len(row) != size for row in self.regions + self.cells):
            raise InvalidBoard("Queens boards must be square")
        if any(not isinstance(region, str) or not region.strip()
               for row in self.regions for region in row):
            raise InvalidBoard("each cell must have a region")
        if len({region for row in self.regions for region in row}) != size:
            raise InvalidBoard("the number of regions must equal the board size")
        if any(not isinstance(cell, Cell) for row in self.cells for cell in row):
            raise InvalidBoard("unrecognized cell state")

    @property
    def size(self) -> int:
        return len(self.regions)

    def with_cell(self, index: int, state: Cell) -> Board:
        if type(index) is not int or not 0 <= index < self.size ** 2:
            raise InvalidBoard("cell index is outside the board")
        rows = [list(row) for row in self.cells]
        row, column = divmod(index, self.size)
        rows[row][column] = state
        return Board(self.regions, tuple(tuple(values) for values in rows))

    def as_strings(self) -> tuple[str, ...]:
        symbols = {Cell.EMPTY: ".", Cell.CROSS: "X", Cell.QUEEN: "Q"}
        return tuple("".join(symbols[cell] for cell in row) for row in self.cells)
