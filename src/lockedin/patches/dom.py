"""Parse Patches' English accessible cell labels."""

from __future__ import annotations

import json
import re
from typing import Any

from .model import Board, Clue, Patch, Shape

CELL_LABEL = re.compile(
    r"Row (\d+), column (\d+)"
    r"(?:, (square|wide rectangle|tall rectangle|freeform) clue(?:, (\d+) cells?)?)?"
    r"(?:, (in drawn region|in region with clue at row \d+, column \d+))?"
)
REGION_LABEL = re.compile(r"in region with clue at row (\d+), column (\d+)")
SHAPES = {"square": Shape.SQUARE, "wide rectangle": Shape.WIDE,
          "tall rectangle": Shape.TALL, "freeform": Shape.FREEFORM}


def board_from_json(value: str) -> Board:
    try:
        data: Any = json.loads(value)
    except (TypeError, json.JSONDecodeError) as error:
        raise ValueError("invalid Patches snapshot JSON") from error
    if not isinstance(data, dict):
        raise ValueError("Patches snapshot must be an object")
    rows, columns, cells = data.get("rows"), data.get("columns"), data.get("cells")
    if (type(rows) is not int or type(columns) is not int or rows < 1 or columns < 1
            or not isinstance(cells, list) or len(cells) != rows * columns):
        raise ValueError("invalid Patches grid dimensions or cells")
    clues: list[Clue] = []
    regions: dict[int, set[int]] = {}
    seen: set[int] = set()
    for cell in cells:
        if not isinstance(cell, dict):
            raise ValueError("invalid Patches cell")
        index, label = cell.get("index"), cell.get("label")
        if type(index) is not int or not 0 <= index < rows * columns or index in seen:
            raise ValueError("invalid or duplicate Patches cell index")
        seen.add(index)
        match = CELL_LABEL.fullmatch(label) if isinstance(label, str) else None
        if match is None or (int(match[1]) - 1, int(match[2]) - 1) != divmod(index, columns):
            raise ValueError(f"unrecognized Patches cell label at {index}: {label!r}")
        shape, area, region = match[3], match[4], match[5]
        if shape:
            clues.append(Clue(index, SHAPES[shape], int(area) if area else None))
        if region == "in drawn region":
            if not shape:
                raise ValueError("drawn region anchor is not a clue")
            regions.setdefault(index, set()).add(index)
        elif region:
            owner = REGION_LABEL.fullmatch(region)
            assert owner is not None
            r, c = int(owner[1]) - 1, int(owner[2]) - 1
            if not (0 <= r < rows and 0 <= c < columns):
                raise ValueError("drawn region clue is outside the grid")
            regions.setdefault(r * columns + c, set()).add(index)
    clue_indices = {clue.index for clue in clues}
    patches = []
    for owner, members in regions.items():
        if owner not in clue_indices or owner not in members:
            raise ValueError("drawn region has no marked clue")
        positions = [divmod(index, columns) for index in members]
        patch = Patch(min(r for r, _ in positions), min(c for _, c in positions),
                      max(r for r, _ in positions), max(c for _, c in positions))
        if patch.cells(columns) != members:
            raise ValueError("drawn region is not rectangular")
        patches.append(patch)
    return Board(rows, columns, tuple(sorted(clues, key=lambda clue: clue.index)), tuple(sorted(patches)))


SNAPSHOT_SCRIPT = r"""
(() => {
  const grids = document.querySelectorAll('[data-testid="interactive-grid"][data-trail-grid]');
  if (grids.length !== 1) throw new Error('Expected one Patches grid');
  const grid = grids[0], cells = [...grid.querySelectorAll(':scope > [data-cell-idx]')];
  const columns = getComputedStyle(grid).gridTemplateColumns.split(/\s+/).length;
  if (!columns || !cells.length || cells.length % columns) throw new Error('Invalid grid layout');
  return JSON.stringify({columns, rows: cells.length / columns, cells: cells.map(cell => {
    if (!/^(0|[1-9]\d*)$/.test(cell.dataset.cellIdx)) throw new Error('Invalid cell index');
    return {index: Number(cell.dataset.cellIdx), label: cell.getAttribute('aria-label')};
  })});
})()
"""
