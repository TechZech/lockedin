"""Constraint solver that rejects invalid and ambiguous puzzles."""

from __future__ import annotations

from .model import BOARD_SIZE, Board

DIGITS = frozenset(range(1, 7))


class UnsolvablePuzzle(ValueError):
    """The board violates Sudoku rules or has no solution."""


class AmbiguousPuzzle(ValueError):
    """More than one solution fits the current board."""


class Solver:
    def solve(self, board: Board) -> Board:
        cells = [list(row) for row in board.cells]
        solutions: list[Board] = []

        def candidates(row: int, column: int) -> set[int]:
            used = set(cells[row])
            used.update(cells[r][column] for r in range(BOARD_SIZE))
            used.update(
                cells[r][c]
                for r in range(row // 2 * 2, row // 2 * 2 + 2)
                for c in range(column // 3 * 3, column // 3 * 3 + 3)
            )
            return set(DIGITS - used)

        for r in range(BOARD_SIZE):
            for c in range(BOARD_SIZE):
                value = cells[r][c]
                if value:
                    cells[r][c] = 0
                    valid = value in candidates(r, c)
                    cells[r][c] = value
                    if not valid:
                        raise UnsolvablePuzzle(f"duplicate digit at cell ({r}, {c})")

        def search() -> None:
            if len(solutions) >= 2:
                return
            best: tuple[int, int, set[int]] | None = None
            for r in range(BOARD_SIZE):
                for c in range(BOARD_SIZE):
                    if cells[r][c] == 0:
                        options = candidates(r, c)
                        if not options:
                            return
                        if best is None or len(options) < len(best[2]):
                            best = (r, c, options)
            if best is None:
                solutions.append(Board(tuple(tuple(row) for row in cells)))
                return
            r, c, options = best
            for value in sorted(options):
                cells[r][c] = value
                search()
                cells[r][c] = 0
                if len(solutions) >= 2:
                    break

        search()
        if not solutions:
            raise UnsolvablePuzzle("board has no solution")
        if len(solutions) > 1:
            raise AmbiguousPuzzle("board has multiple solutions; refusing to guess")
        return solutions[0]
