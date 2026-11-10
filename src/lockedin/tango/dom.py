"""Convert a Tango DOM snapshot into the UI-independent board model."""

from __future__ import annotations

import json
from typing import Any

from .model import BOARD_SIZE, Board, Constraint, Relation


class InvalidDomSnapshot(ValueError):
    """Raised when a browser snapshot does not describe a Tango board."""


def board_from_snapshot(snapshot: dict[str, Any]) -> Board:
    cells = snapshot.get("cells")
    relations = snapshot.get("relations", [])
    if not isinstance(cells, list) or len(cells) != BOARD_SIZE * BOARD_SIZE:
        raise InvalidDomSnapshot("snapshot must contain 36 cells")

    rows = ["?"] * (BOARD_SIZE * BOARD_SIZE)
    seen = set()
    for cell in cells:
        try:
            index = int(cell["index"])
            state = cell.get("state", "?")
        except (KeyError, TypeError, ValueError) as error:
            raise InvalidDomSnapshot("cell entries need an index and state") from error
        if not 0 <= index < len(rows) or index in seen or state not in {"S", "M", "?"}:
            raise InvalidDomSnapshot("cell index or state is invalid")
        seen.add(index)
        rows[index] = state

    constraints = []
    for relation in relations:
        try:
            first = _position(relation["first"])
            second = _position(relation["second"])
            kind = {"Equal": Relation.EQUAL, "Cross": Relation.OPPOSITE}[relation["type"]]
        except (KeyError, TypeError, ValueError) as error:
            raise InvalidDomSnapshot("relation entries are invalid") from error
        constraints.append(Constraint(first, second, kind))

    return Board.from_strings(
        tuple("".join(rows[row * BOARD_SIZE : (row + 1) * BOARD_SIZE]) for row in range(BOARD_SIZE)),
        constraints,
    )


def board_from_json(value: str) -> Board:
    try:
        snapshot = json.loads(value)
    except json.JSONDecodeError as error:
        raise InvalidDomSnapshot("snapshot is not valid JSON") from error
    if not isinstance(snapshot, dict):
        raise InvalidDomSnapshot("snapshot must be a JSON object")
    return board_from_snapshot(snapshot)


def _position(value: Any) -> tuple[int, int]:
    index = int(value)
    if not 0 <= index < BOARD_SIZE * BOARD_SIZE:
        raise ValueError("cell index outside board")
    return divmod(index, BOARD_SIZE)


SNAPSHOT_SCRIPT = r"""
(() => {
  const grid = document.querySelector('[data-testid="interactive-grid"]');
  const cells = [...grid.querySelectorAll('[data-testid^="cell-"][data-cell-idx]')];
  const bounds = element => {
    const rect = element.getBoundingClientRect();
    return {
      x: rect.left + rect.width / 2,
      y: rect.top + rect.height / 2
    };
  };
  const result = {
    cells: cells.map(cell => ({
      index: Number(cell.dataset.cellIdx),
      state: cell.querySelector('svg[aria-label="Sun"]') ? 'S'
        : cell.querySelector('svg[aria-label="Moon"]') ? 'M' : '?'
    })),
    relations: []
  };
  for (const cell of cells) {
    for (const marker of cell.querySelectorAll('[data-testid="edge-equal"], [data-testid="edge-cross"]')) {
      const source = bounds(cell);
      const markerPoint = bounds(marker);
      const offset = { x: markerPoint.x - source.x, y: markerPoint.y - source.y };
      const direction = Math.abs(offset.x) > Math.abs(offset.y)
        ? (offset.x < 0 ? 'left' : 'right')
        : (offset.y < 0 ? 'up' : 'down');
      const first = Number(cell.dataset.cellIdx);
      const second = direction === 'left' ? first - 1
        : direction === 'right' ? first + 1
        : direction === 'up' ? first - 6
        : first + 6;
      const validNeighbor = direction === 'left' ? first % 6 > 0
        : direction === 'right' ? first % 6 < 5 : true;
      if (!validNeighbor || second < 0 || second >= 36) {
        throw new Error('Relation marker points outside the board');
      }
      result.relations.push({
        first,
        second,
        type: marker.getAttribute('aria-label')
      });
    }
  }
  return JSON.stringify(result);
})()
"""