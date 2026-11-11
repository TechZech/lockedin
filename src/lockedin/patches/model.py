"""Immutable Patches clues, rectangles, and board state."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Shape(str, Enum):
    SQUARE = "square"
    WIDE = "wide"
    TALL = "tall"
    FREEFORM = "freeform"


@dataclass(frozen=True, slots=True)
class Clue:
    index: int
    shape: Shape
    area: int | None = None


@dataclass(frozen=True, slots=True, order=True)
class Patch:
    top: int
    left: int
    bottom: int
    right: int

    def cells(self, columns: int) -> frozenset[int]:
        return frozenset(r * columns + c for r in range(self.top, self.bottom + 1)
                         for c in range(self.left, self.right + 1))


@dataclass(frozen=True, slots=True)
class Board:
    rows: int
    columns: int
    clues: tuple[Clue, ...]
    patches: tuple[Patch, ...] = ()

    def __post_init__(self) -> None:
        if type(self.rows) is not int or type(self.columns) is not int or self.rows < 1 or self.columns < 1:
            raise ValueError("grid dimensions must be positive integers")
        if not isinstance(self.clues, tuple) or not self.clues:
            raise ValueError("board must have clues")
        indices = set()
        for clue in self.clues:
            if (not isinstance(clue, Clue) or type(clue.index) is not int
                    or not 0 <= clue.index < self.rows * self.columns
                    or not isinstance(clue.shape, Shape)
                    or (clue.area is not None and
                        (type(clue.area) is not int or not 1 <= clue.area <= self.rows * self.columns))
                    or clue.index in indices):
                raise ValueError("invalid or duplicate clue")
            indices.add(clue.index)
        if not isinstance(self.patches, tuple):
            raise ValueError("patches must be a tuple")
        occupied: set[int] = set()
        for patch in self.patches:
            if not self.valid_patch(patch) or occupied.intersection(patch.cells(self.columns)):
                raise ValueError("existing patches are invalid or overlap")
            occupied.update(patch.cells(self.columns))

    def valid_patch(self, patch: Patch) -> bool:
        if (not isinstance(patch, Patch)
                or any(type(v) is not int for v in (patch.top, patch.left, patch.bottom, patch.right))
                or not (0 <= patch.top <= patch.bottom < self.rows)
                or not (0 <= patch.left <= patch.right < self.columns)):
            return False
        cells = patch.cells(self.columns)
        clues = [clue for clue in self.clues if clue.index in cells]
        if len(clues) != 1:
            return False
        clue = clues[0]
        height, width = patch.bottom - patch.top + 1, patch.right - patch.left + 1
        return ((clue.area is None or clue.area == height * width)
                and (clue.shape is Shape.FREEFORM
                     or clue.shape is Shape.SQUARE and width == height
                     or clue.shape is Shape.WIDE and width > height
                     or clue.shape is Shape.TALL and height > width))

    def with_patches(self, patches: tuple[Patch, ...]) -> Board:
        return Board(self.rows, self.columns, self.clues, tuple(sorted(patches)))
