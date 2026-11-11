"""Translate Mini Sudoku DOM snapshots into boards."""

from __future__ import annotations

import json
from typing import Any

from .model import BOARD_SIZE, Board


class InvalidDomSnapshot(ValueError):
    """The snapshot does not contain a recognizable Mini Sudoku board."""


def board_from_snapshot(snapshot: dict[str, Any]) -> Board:
    cells = snapshot.get("cells")
    if not isinstance(cells, list) or len(cells) != 36:
        raise InvalidDomSnapshot("snapshot must contain 36 cells")
    values = [0] * 36
    seen: set[int] = set()
    for cell in cells:
        if not isinstance(cell, dict):
            raise InvalidDomSnapshot("invalid cell entry")
        index, value = cell.get("index"), cell.get("value")
        if type(index) is not int or not 0 <= index < 36 or index in seen:
            raise InvalidDomSnapshot("cell index is invalid or duplicated")
        if not isinstance(value, str) or value not in ("", "1", "2", "3", "4", "5", "6"):
            raise InvalidDomSnapshot(f"unrecognized value in cell {index}")
        seen.add(index)
        values[index] = int(value) if value else 0
    return Board(tuple(tuple(values[i:i + BOARD_SIZE]) for i in range(0, 36, BOARD_SIZE)))


def board_from_json(value: str) -> Board:
    try:
        snapshot = json.loads(value)
    except (TypeError, json.JSONDecodeError) as error:
        raise InvalidDomSnapshot("snapshot is not valid JSON") from error
    if not isinstance(snapshot, dict):
        raise InvalidDomSnapshot("snapshot must be a JSON object")
    return board_from_snapshot(snapshot)


SNAPSHOT_SCRIPT = r"""
(() => {
  const grid = document.querySelector('[data-sudoku-grid="true"]');
  if (!grid) throw new Error('Mini Sudoku grid not found');
  const cells = [...grid.querySelectorAll('.sudoku-cell[data-cell-idx]')];
  return JSON.stringify({cells: cells.map(cell => {
    if (!/^(?:[0-9]|[12][0-9]|3[0-5])$/.test(cell.dataset.cellIdx))
      throw new Error('Invalid cell index');
    const index = Number(cell.dataset.cellIdx);
    const row = Math.floor(index / 6), col = index % 6;
    for (const [direction, expected] of [
      ['right', col === 2], ['left', col === 3],
      ['bottom', row === 1 || row === 3], ['top', row === 2 || row === 4]
    ]) {
      if (cell.classList.contains('sudoku-cell-wall-' + direction) !== expected)
        throw new Error('Unsupported Sudoku region layout');
    }
    const content = cell.querySelector('.sudoku-cell-content');
    if (!content) throw new Error('Cell content missing');
    const notes = content.querySelector('.sudoku-cell-notes');
    if (!notes && content.children.length) throw new Error('Unrecognized cell content');
    const value = notes ? '' : content.textContent.trim();
    return {index, value};
  })});
})()
"""
