"""Read Wend's grid, word slots and locked tiles."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from .model import Board


@dataclass(frozen=True, slots=True)
class Snapshot:
    board: Board
    locked: frozenset[int]
    words: tuple[str, ...]


def snapshot_from_json(value: str) -> Snapshot:
    try:
        data: Any = json.loads(value)
    except (TypeError, json.JSONDecodeError) as error:
        raise ValueError("invalid Wend snapshot JSON") from error
    if not isinstance(data, dict):
        raise ValueError("Wend snapshot must be an object")
    rows, columns, cells, slots = (data.get(key) for key in ("rows", "columns", "cells", "slots"))
    if (type(rows) is not int or type(columns) is not int or rows < 1 or columns < 1
            or not isinstance(cells, list) or len(cells) != rows * columns
            or not isinstance(slots, list) or not slots):
        raise ValueError("invalid Wend grid or word slots")
    letters: list[str | None] = [None] * len(cells)
    locked: set[int] = set()
    for cell in cells:
        if not isinstance(cell, dict):
            raise ValueError("invalid Wend cell")
        index, letter, is_locked = cell.get("index"), cell.get("letter"), cell.get("locked")
        if type(index) is not int or not 0 <= index < len(cells) or letters[index] is not None:
            raise ValueError("invalid or duplicate Wend cell index")
        if not isinstance(letter, str) or type(is_locked) is not bool or (not letter and is_locked):
            raise ValueError("invalid Wend cell state")
        letters[index] = letter
        if is_locked:
            locked.add(index)
    words = []
    lengths = []
    for row in slots:
        if not isinstance(row, list) or any(
            not isinstance(letter, str) or (letter and (len(letter) != 1
                                                       or not letter.isascii() or not letter.isupper()))
            for letter in row
        ):
            raise ValueError("invalid Wend word slots")
        lengths.append(len(row))
        words.append("".join(row))
    if any(letter is None for letter in letters):
        raise ValueError("missing Wend cell")
    board = Board(rows, columns, tuple(letter for letter in letters if letter is not None), tuple(lengths))
    return Snapshot(board, frozenset(locked), tuple(words))


SNAPSHOT_SCRIPT = r"""
(() => {
  const grids = document.querySelectorAll('[data-testid="wend-game-board"] [data-testid="interactive-grid"][data-trail-grid]');
  const lists = document.querySelectorAll('[data-testid="wend-word-list"]');
  if (grids.length !== 1 || lists.length !== 1) throw new Error('Expected one Wend grid and word list');
  const grid = grids[0], cells = [...grid.querySelectorAll(':scope > [data-cell-idx]')];
  const columns = getComputedStyle(grid).gridTemplateColumns.split(/\s+/).length;
  if (!columns || !cells.length || cells.length % columns) throw new Error('Invalid Wend grid layout');
  const rows = [...lists[0].querySelectorAll('[data-testid^="wend-word-list-row-"]')]
    .filter(row => /^wend-word-list-row-\d+$/.test(row.dataset.testid));
  return JSON.stringify({
    columns, rows: cells.length / columns,
    cells: cells.map(cell => {
      if (!/^(0|[1-9]\d*)$/.test(cell.dataset.cellIdx)) throw new Error('Invalid cell index');
      const hole = cell.getAttribute('data-cell-is-hole') === 'true';
      const letters = [...cell.querySelectorAll('span')].map(e => e.textContent.trim())
        .filter(s => /^[A-Z]$/.test(s));
      if ((!hole && letters.length !== 1) || (hole && letters.length))
        throw new Error('Unsupported Wend cell layout');
      return {index: Number(cell.dataset.cellIdx), letter: hole ? '' : letters[0],
        locked: cell.getAttribute('data-cell-is-locked') === 'true'};
    }),
    slots: rows.map(row => [...row.querySelectorAll('[data-testid^="wend-word-list-slot-"]')]
      .map(slot => slot.textContent.trim()))
  });
})()
"""
