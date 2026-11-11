"""Exact-cover solver for Patches."""

from __future__ import annotations

from .model import Board, Patch


class UnsolvablePuzzle(ValueError):
    """No complete tiling respects the clues and existing patches."""


class AmbiguousPuzzle(ValueError):
    """More than one complete tiling is possible."""


class Solver:
    def solve(self, board: Board) -> Board:
        occupied = set().union(*(patch.cells(board.columns) for patch in board.patches))
        full_mask = (1 << (board.rows * board.columns)) - 1
        occupied_mask = sum(1 << cell for cell in occupied)
        options: list[list[tuple[Patch, int]]] = [[] for _ in range(board.rows * board.columns)]
        for clue in board.clues:
            if clue.index in occupied:
                continue
            row, col = divmod(clue.index, board.columns)
            for top in range(row + 1):
                for bottom in range(row, board.rows):
                    for left in range(col + 1):
                        for right in range(col, board.columns):
                            patch = Patch(top, left, bottom, right)
                            if not board.valid_patch(patch):
                                continue
                            cells = patch.cells(board.columns)
                            if cells & occupied:
                                continue
                            mask = sum(1 << cell for cell in cells)
                            for cell in cells:
                                options[cell].append((patch, mask))

        solutions: list[tuple[Patch, ...]] = []
        chosen: list[Patch] = []

        def search(mask: int) -> None:
            if len(solutions) >= 2:
                return
            if mask == full_mask:
                solutions.append(tuple(chosen))
                return
            best: list[tuple[Patch, int]] | None = None
            for cell, candidates in enumerate(options):
                if mask & (1 << cell):
                    continue
                available = [(patch, bits) for patch, bits in candidates if not bits & mask]
                if not available:
                    return
                if best is None or len(available) < len(best):
                    best = available
                    if len(best) == 1:
                        break
            assert best is not None
            for patch, bits in best:
                chosen.append(patch)
                search(mask | bits)
                chosen.pop()
                if len(solutions) >= 2:
                    return

        search(occupied_mask)
        if not solutions:
            raise UnsolvablePuzzle("board has no solution consistent with existing patches")
        if len(solutions) > 1:
            raise AmbiguousPuzzle("board has multiple solutions; refusing to guess")
        return board.with_patches(board.patches + solutions[0])
