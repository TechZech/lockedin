"""Enumerate dictionary-based exact covers of the Wend grid."""

from __future__ import annotations

from collections import Counter
from functools import lru_cache
from typing import Callable, Iterable, Iterator

from wordfreq import iter_wordlist

from .model import Board


@lru_cache(maxsize=1)
def english_words() -> tuple[str, ...]:
    return tuple(word.upper() for word in iter_wordlist("en", wordlist="best")
                 if word.isascii() and word.isalpha())


class Solver:
    def __init__(self, words: Iterable[str] | None = None) -> None:
        self.words = words

    def solutions(
        self, board: Board, *, check: Callable[[], None] | None = None,
    ) -> Iterator[tuple[tuple[int, ...], ...]]:
        lengths = set(board.lengths)
        available = Counter(board.letters)
        trie: dict = {}
        ranks: dict[str, int] = {}
        for rank, word in enumerate(self.words if self.words is not None else english_words()):
            if check is not None and rank % 4096 == 0:
                check()
            if not isinstance(word, str) or not word.isascii() or not word.isalpha():
                continue
            word = word.upper()
            if len(word) not in lengths or Counter(word) - available:
                continue
            ranks.setdefault(word, rank)
            node = trie
            for letter in word:
                node = node.setdefault(letter, {})
            node[""] = True

        candidates: list[tuple[int, tuple[int, ...]]] = []
        by_cell: list[list[int]] = [[] for _ in board.letters]
        neighbors = tuple(board.neighbors(i) for i in range(len(board.letters)))
        visits = 0

        def find_paths(cell: int, mask: int, path: tuple[int, ...], node: dict) -> None:
            nonlocal visits
            visits += 1
            if check is not None and visits % 1024 == 0:
                check()
            node = node.get(board.letters[cell])
            if node is None:
                return
            mask |= 1 << cell
            path += (cell,)
            if "" in node:
                candidate = len(candidates)
                candidates.append((mask, path))
                for index in path:
                    by_cell[index].append(candidate)
            for other in neighbors[cell]:
                if not mask & (1 << other):
                    find_paths(other, mask, path, node)

        for index, letter in enumerate(board.letters):
            if letter:
                find_paths(index, 0, (), trie)
        for choices in by_cell:
            choices.sort(key=lambda i: ranks["".join(board.letters[c] for c in candidates[i][1])])

        all_cells = sum(1 << i for i, letter in enumerate(board.letters) if letter)
        remaining = Counter(board.lengths)
        failed: set[tuple[int, tuple[tuple[int, int], ...]]] = set()

        def search(mask: int, chosen: tuple[tuple[int, ...], ...]) -> Iterator[tuple[tuple[int, ...], ...]]:
            nonlocal visits
            visits += 1
            if check is not None and visits % 1024 == 0:
                check()
            if mask == all_cells:
                yield chosen
                return
            state = (mask, tuple(sorted((n, count) for n, count in remaining.items() if count)))
            if state in failed:
                return
            best: list[int] | None = None
            for cell, letter in enumerate(board.letters):
                if not letter or mask & (1 << cell):
                    continue
                options = [i for i in by_cell[cell]
                           if not candidates[i][0] & mask and remaining[len(candidates[i][1])]]
                if best is None or len(options) < len(best):
                    best = options
                    if not best:
                        break
            found = False
            for i in best or ():
                word_mask, path = candidates[i]
                remaining[len(path)] -= 1
                try:
                    for solution in search(mask | word_mask, chosen + (path,)):
                        found = True
                        yield solution
                finally:
                    remaining[len(path)] += 1
            if not found:
                failed.add(state)

        yield from search(0, ())

    def solve(self, board: Board) -> tuple[tuple[int, ...], ...]:
        solutions = self.solutions(board)
        first = next(solutions, None)
        if first is None:
            raise ValueError("Wend has no solution in the dictionary")
        if next(solutions, None) is not None:
            raise ValueError("Wend has multiple dictionary solutions; refusing to guess")
        return first
