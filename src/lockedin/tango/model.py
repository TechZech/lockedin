"""UI-independent data types for a Tango puzzle."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable, Sequence

BOARD_SIZE = 6


class Cell(Enum):
    UNKNOWN = "?"
    SUN = "S"
    MOON = "M"

    def opposite(self) -> Cell:
        if self is Cell.SUN:
            return Cell.MOON
        if self is Cell.MOON:
            return Cell.SUN
        raise ValueError("UNKNOWN has no opposite")


class Relation(Enum):
    EQUAL = "="
    OPPOSITE = "x"


class InvalidBoard(ValueError):
    """Raised when a board or constraint set is malformed."""


@dataclass(frozen=True, slots=True)
class Constraint:
    first: tuple[int, int]
    second: tuple[int, int]
    relation: Relation


@dataclass(frozen=True, slots=True)
class Board:
    """A rectangular Tango board and its horizontal/vertical relations."""

    cells: tuple[tuple[Cell, ...], ...]
    constraints: tuple[Constraint, ...] = ()

    def __post_init__(self) -> None:
        if not self.cells or not self.cells[0]:
            raise InvalidBoard("board must contain at least one cell")
        width = len(self.cells[0])
        if any(len(row) != width for row in self.cells):
            raise InvalidBoard("board rows must have equal lengths")
        if self.height != BOARD_SIZE or width != BOARD_SIZE:
            raise InvalidBoard(f"Tango boards must be {BOARD_SIZE}x{BOARD_SIZE}")
        for constraint in self.constraints:
            self._check_position(constraint.first)
            self._check_position(constraint.second)
            if constraint.first == constraint.second:
                raise InvalidBoard("a constraint cannot reference one cell twice")
            row_distance = abs(constraint.first[0] - constraint.second[0])
            column_distance = abs(constraint.first[1] - constraint.second[1])
            if row_distance + column_distance != 1:
                raise InvalidBoard("constraint cells must be adjacent")

    @property
    def height(self) -> int:
        return len(self.cells)

    @property
    def width(self) -> int:
        return len(self.cells[0])

    def cell(self, position: tuple[int, int]) -> Cell:
        self._check_position(position)
        row, column = position
        return self.cells[row][column]

    def _check_position(self, position: tuple[int, int]) -> None:
        row, column = position
        if not (0 <= row < self.height and 0 <= column < self.width):
            raise InvalidBoard(f"position outside board: {position}")

    @classmethod
    def from_strings(
        cls,
        rows: Sequence[str],
        constraints: Iterable[Constraint] = (),
    ) -> Board:
        try:
            cells = tuple(tuple(Cell(character) for character in row) for row in rows)
        except ValueError as error:
            raise InvalidBoard("rows may only contain '?', 'S', or 'M'") from error
        return cls(cells, tuple(constraints))

    def as_strings(self) -> tuple[str, ...]:
        return tuple("".join(cell.value for cell in row) for row in self.cells)
