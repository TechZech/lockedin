"""Translate accessible Queens cell labels into a board."""

from __future__ import annotations

import json
import re
from math import isqrt
from typing import Any

from .model import Board, Cell


class InvalidDomSnapshot(ValueError):
    """The snapshot does not contain a recognizable Queens board."""


LABEL = re.compile(r"(Empty cell|Cross|Queen) of color (.+), row (\d+), column (\d+)")
STATES = {"Empty cell": Cell.EMPTY, "Cross": Cell.CROSS, "Queen": Cell.QUEEN}


def board_from_snapshot(snapshot: dict[str, Any]) -> Board:
    entries = snapshot.get("cells")
    if not isinstance(entries, list):
        raise InvalidDomSnapshot("snapshot must contain cells")
    size = isqrt(len(entries))
    if not 1 <= size <= 16 or size * size != len(entries):
        raise InvalidDomSnapshot("Queens grid must be square")
    cells: list[Cell | None] = [None] * len(entries)
    regions: list[str] = [""] * len(entries)
    for entry in entries:
        if not isinstance(entry, dict):
            raise InvalidDomSnapshot("invalid cell entry")
        index, label = entry.get("index"), entry.get("label")
        if type(index) is not int or not 0 <= index < len(entries) or cells[index] is not None:
            raise InvalidDomSnapshot("cell index is invalid or duplicated")
        match = LABEL.fullmatch(label) if isinstance(label, str) else None
        if not match:
            raise InvalidDomSnapshot(f"unrecognized label in cell {index}")
        state, color, row, column = match.groups()
        if (int(row) - 1, int(column) - 1) != divmod(index, size):
            raise InvalidDomSnapshot(f"cell {index} has inconsistent coordinates")
        cells[index], regions[index] = STATES[state], color
    if any(cell is None for cell in cells):
        raise InvalidDomSnapshot("missing cell")
    values = [cell for cell in cells if cell is not None]
    return Board(
        tuple(tuple(regions[i:i + size]) for i in range(0, len(entries), size)),
        tuple(tuple(values[i:i + size]) for i in range(0, len(entries), size)),
    )


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
  const grids = document.querySelectorAll('#queens-game-board [data-testid="interactive-grid"]');
  if (grids.length !== 1) throw new Error('Queens grid not found or ambiguous');
  return JSON.stringify({cells: [...grids[0].querySelectorAll('[data-cell-idx]')].map(cell => {
    const raw = cell.getAttribute('data-cell-idx');
    if (!/^(0|[1-9]\d*)$/.test(raw)) throw new Error('Invalid cell index');
    return {index: Number(raw), label: cell.getAttribute('aria-label')};
  })});
})()
"""
