"""Constraint solver for Queens, rejecting inconsistent and ambiguous boards."""

from __future__ import annotations

from .model import Board, Cell


class UnsolvablePuzzle(ValueError):
    """The board has no solution consistent with its markings."""


class AmbiguousPuzzle(ValueError):
    """More than one solution fits the current board."""


class Solver:
    def solve(self, board: Board) -> Board:
        size = board.size
        regions = {name: index for index, name in enumerate(
            sorted({region for row in board.regions for region in row})
        )}
        placed: dict[int, int] = {}
        columns = 0
        used_regions = 0

        for row in range(size):
            for column in range(size):
                if board.cells[row][column] is not Cell.QUEEN:
                    continue
                col_bit = 1 << column
                region_bit = 1 << regions[board.regions[row][column]]
                if (row in placed or columns & col_bit or used_regions & region_bit
                        or any(abs(row - r) == 1 and abs(column - c) <= 1
                               for r, c in placed.items())):
                    raise UnsolvablePuzzle("existing queens violate the rules")
                placed[row] = column
                columns |= col_bit
                used_regions |= region_bit

        solutions: list[tuple[int, ...]] = []

        def options(row: int, occupied_columns: int, occupied_regions: int) -> list[int]:
            return [
                column for column in range(size)
                if board.cells[row][column] is Cell.EMPTY
                and not occupied_columns & (1 << column)
                and not occupied_regions & (1 << regions[board.regions[row][column]])
                and all(abs(row - r) != 1 or abs(column - c) > 1 for r, c in placed.items())
            ]

        def search(occupied_columns: int, occupied_regions: int) -> None:
            if len(solutions) >= 2:
                return
            if len(placed) == size:
                solutions.append(tuple(placed[row] for row in range(size)))
                return
            candidates = [(row, options(row, occupied_columns, occupied_regions))
                          for row in range(size) if row not in placed]
            row, choices = min(candidates, key=lambda item: len(item[1]))
            for column in choices:
                placed[row] = column
                search(occupied_columns | (1 << column),
                       occupied_regions | (1 << regions[board.regions[row][column]]))
                del placed[row]
                if len(solutions) >= 2:
                    return

        search(columns, used_regions)
        if not solutions:
            raise UnsolvablePuzzle("board has no solution consistent with its queens and X marks")
        if len(solutions) > 1:
            raise AmbiguousPuzzle("board has multiple solutions; refusing to guess")
        solved = board
        for row, column in enumerate(solutions[0]):
            solved = solved.with_cell(row * size + column, Cell.QUEEN)
        return solved
