"""Read the observed LinkedIn Zip grid, including rendered wall segments."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from .model import Board


@dataclass(frozen=True, slots=True)
class Snapshot:
    board: Board
    filled: frozenset[int]


def snapshot_from_json(value: str) -> Snapshot:
    try:
        data: Any = json.loads(value)
    except (TypeError, json.JSONDecodeError) as error:
        raise ValueError("invalid Zip snapshot JSON") from error
    if not isinstance(data, dict):
        raise ValueError("Zip snapshot must be an object")
    rows, columns, cells = data.get("rows"), data.get("columns"), data.get("cells")
    if (type(rows) is not int or type(columns) is not int or rows < 1 or columns < 1
            or not isinstance(cells, list) or len(cells) != rows * columns):
        raise ValueError("invalid Zip grid dimensions or cells")
    clues: dict[int, int] = {}
    walls: set[tuple[int, int]] = set()
    filled: set[int] = set()
    seen: set[int] = set()
    for cell in cells:
        if not isinstance(cell, dict):
            raise ValueError("invalid Zip cell")
        index, clue = cell.get("index"), cell.get("clue")
        if type(index) is not int or not 0 <= index < rows * columns or index in seen:
            raise ValueError("invalid or duplicate Zip cell index")
        seen.add(index)
        if not isinstance(clue, str) or (clue and (not clue.isascii() or not clue.isdigit() or int(clue) < 1)):
            raise ValueError("invalid Zip waypoint")
        if clue:
            number = int(clue)
            if number in clues:
                raise ValueError("duplicate Zip waypoint")
            clues[number] = index
        if type(cell.get("filled")) is not bool:
            raise ValueError("invalid Zip path state")
        if cell["filled"]:
            filled.add(index)
        for direction, offset in (("right", 1), ("down", columns)):
            wall = cell.get(direction)
            if type(wall) is not bool:
                raise ValueError("invalid Zip wall state")
            if wall:
                if (direction == "right" and index % columns == columns - 1
                        or direction == "down" and index // columns == rows - 1):
                    raise ValueError("Zip wall lies outside the grid")
                walls.add((index, index + offset))
    if set(clues) != set(range(1, len(clues) + 1)):
        raise ValueError("Zip waypoints must be consecutive starting at 1")
    return Snapshot(Board(rows, columns, tuple(clues[i] for i in range(1, len(clues) + 1)),
                          frozenset(walls)), frozenset(filled))


SNAPSHOT_SCRIPT = r"""
(() => {
  const grid = document.querySelector('[data-testid="interactive-grid"][data-trail-grid]');
  if (!grid) throw new Error('Zip grid not found');
  const cells = [...grid.querySelectorAll(':scope > [data-cell-idx]')];
  const columns = getComputedStyle(grid).gridTemplateColumns.split(/\s+/).length;
  if (!columns || !cells.length || cells.length % columns) throw new Error('Invalid grid layout');
  const observed = cells.map(cell => {
    if (!/^(0|[1-9]\d*)$/.test(cell.dataset.cellIdx)) throw new Error('Invalid cell index');
    const face = cell.firstElementChild;
    const bounds = cell.getBoundingClientRect();
    const faceBounds = face?.getBoundingClientRect();
    const faceStyle = face && getComputedStyle(face);
    if (!faceStyle || faceStyle.position !== 'absolute' ||
        Math.abs(faceBounds.width - bounds.width) > 3 ||
        Math.abs(faceBounds.height - bounds.height) > 3 ||
        parseFloat(faceStyle.borderTopWidth) <= 0)
      throw new Error('Unsupported Zip cell layout; wall detection unavailable');
    let left = false, right = false, down = false;
    for (const child of [...cell.children].slice(1)) {
      if (child.hasAttribute('data-cell-content') ||
          child.matches('[data-testid="filled-cell"], [data-cell-hint-arrow]')) continue;
      const before = getComputedStyle(child, '::before');
      const after = getComputedStyle(child, '::after');
      if (before.content !== 'none' && before.content !== 'normal')
        throw new Error('Unsupported Zip wall or cell decoration');
      if (after.content === 'none' || after.content === 'normal') {
        const rect = child.getBoundingClientRect();
        if (getComputedStyle(child).position !== 'absolute' ||
            rect.width <= 0 || rect.height <= 0 ||
            rect.width >= bounds.width || rect.height >= bounds.height)
          throw new Error('Unsupported Zip wall or cell decoration');
        continue;
      }
      const sides = ['Top', 'Right', 'Bottom', 'Left'].filter(side =>
        parseFloat(after[`border${side}Width`]) > 0);
      if (after.content !== '""' || after.position !== 'absolute' || sides.length !== 1 ||
          sides[0] === 'Top' || after[`border${sides[0]}Style`] !== 'solid' ||
          parseFloat(after[`border${sides[0]}Width`]) <= parseFloat(faceStyle.borderTopWidth))
        throw new Error('Unsupported Zip wall or cell decoration');
      right ||= sides[0] === 'Right';
      down ||= sides[0] === 'Bottom';
      left ||= sides[0] === 'Left';
    }
    const clues = cell.querySelectorAll('[data-cell-content]');
    if (clues.length > 1) throw new Error('Multiple waypoints in cell');
    return {
      index: Number(cell.dataset.cellIdx),
      clue: clues.length ? clues[0].textContent.trim() : '',
      left,
      right,
      down,
      filled: cell.querySelectorAll('[data-testid="filled-cell"]').length > 0
    };
  });
  const byIndex = new Map(observed.map(cell => [cell.index, cell]));
  for (const cell of observed) {
    if (cell.left) {
      if (cell.index % columns === 0 || !byIndex.has(cell.index - 1))
        throw new Error('Zip wall lies outside the grid');
      byIndex.get(cell.index - 1).right = true;
    }
    delete cell.left;
  }
  return JSON.stringify({columns, rows: cells.length / columns, cells: observed});
})()
"""
