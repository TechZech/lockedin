"""Deterministic constraint solver for Tango boards."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Callable, Iterable, Literal

from .model import BOARD_SIZE, Board, Cell, Constraint, Relation

SUN = 1
MOON = 2
BOTH = SUN | MOON
Position = tuple[int, int]
Unit = tuple[Literal["row", "column"], int]
Assign = Callable[[Position, int], None]


class UnsolvablePuzzle(ValueError):
    """Raised when no board satisfies the givens and Tango rules."""


class DeductionStalled(ValueError):
    """Raised when deduction cannot finish a board."""


@dataclass(frozen=True, slots=True)
class Solver:
    """Solve a Tango board without knowing anything about its UI."""

    def solve(self, board: Board) -> Board:
        domains = self._initial_domains(board)
        queue, queued = self._initial_queue(board)

        def schedule(unit: Unit) -> None:
            if unit not in queued:
                queue.appendleft(unit)
                queued.add(unit)

        def assign(position: Position, value: int) -> None:
            if self._assign(position, value, domains):
                self._schedule_dependencies(position, board.constraints, schedule)

        while queue:
            unit = queue.popleft()
            queued.remove(unit)
            self._process_unit(unit, board, domains, assign)

        self._validate_complete(domains, board)
        return self._board_from_domains(board, domains)

    def _process_unit(self, unit: Unit, board: Board, domains: dict[Position, int], assign: Assign) -> None:
        positions = self._unit_positions(unit)
        self._apply_line_rules(positions, domains, board.constraints, assign)
        for constraint in board.constraints:
            if constraint.first in positions or constraint.second in positions:
                self._apply_relation(constraint, domains, assign)

    @staticmethod
    def _initial_queue(board: Board) -> tuple[deque[Unit], set[Unit]]:
        units = [("row", index) for index in range(BOARD_SIZE)] + [("column", index) for index in range(BOARD_SIZE)]
        return deque(units), set(units)

    @staticmethod
    def _schedule_dependencies(position: Position, constraints: tuple[Constraint, ...], schedule: Callable[[Unit], None]) -> None:
        row, column = position
        schedule(("row", row))
        schedule(("column", column))
        for constraint in constraints:
            if position in (constraint.first, constraint.second):
                for endpoint in (constraint.first, constraint.second):
                    schedule(("row", endpoint[0]))
                    schedule(("column", endpoint[1]))

    @staticmethod
    def _unit_positions(unit: Unit) -> tuple[Position, ...]:
        kind, index = unit
        if kind == "row":
            return tuple((index, column) for column in range(BOARD_SIZE))
        return tuple((row, index) for row in range(BOARD_SIZE))

    def _initial_domains(self, board: Board) -> dict[tuple[int, int], int]:
        return {
            (row, column): self._domain_for_cell(board.cell((row, column)))
            for row in range(BOARD_SIZE)
            for column in range(BOARD_SIZE)
        }

    def _apply_line_rules(
        self,
        positions: tuple[Position, ...],
        domains: dict[Position, int],
        constraints: tuple[Constraint, ...],
        assign: Assign,
    ) -> None:
        self._apply_core_line_rules(positions, domains, constraints, assign)
        self._apply_candidate_elimination_rule(positions, domains, constraints, assign)

    def _apply_core_line_rules(
        self,
        positions: tuple[Position, ...],
        domains: dict[Position, int],
        constraints: tuple[Constraint, ...],
        assign: Assign,
    ) -> None:
        self._apply_count_rule(positions, domains, assign)
        self._apply_triple_rules(positions, domains, assign)
        self._apply_matching_endpoints_rule(positions, domains, assign)
        self._apply_terminal_pair_rule(positions, domains, assign)
        self._apply_equal_pair_endpoint_rule(positions, domains, constraints, assign)

    def _apply_candidate_elimination_rule(
        self,
        positions: tuple[Position, ...],
        domains: dict[Position, int],
        constraints: tuple[Constraint, ...],
        assign: Assign,
    ) -> None:
        for position in positions:
            if domains[position] != BOTH:
                continue
            candidates: list[int] = []
            for candidate in (SUN, MOON):
                tentative = domains.copy()
                tentative[position] = candidate
                try:
                    self._propagate_core_constraints(tentative, constraints)
                except (UnsolvablePuzzle, DeductionStalled):
                    continue
                candidates.append(candidate)
            if not candidates:
                raise UnsolvablePuzzle(f"cell {position} has no viable assignments")
            if len(candidates) == 1:
                assign(position, candidates[0])

    def _propagate_core_constraints(
        self,
        domains: dict[Position, int],
        constraints: tuple[Constraint, ...],
    ) -> None:
        queue, queued = self._initial_queue_for_domains(domains)

        def schedule(unit: Unit) -> None:
            if unit not in queued:
                queue.appendleft(unit)
                queued.add(unit)

        def assign(position: Position, value: int) -> None:
            if self._assign(position, value, domains):
                self._schedule_dependencies(position, constraints, schedule)

        while queue:
            unit = queue.popleft(); queued.remove(unit)
            positions = self._unit_positions(unit)
            self._apply_core_line_rules(positions, domains, constraints, assign)
            for constraint in constraints:
                if constraint.first in positions or constraint.second in positions:
                    self._apply_relation(constraint, domains, assign)

    @staticmethod
    def _initial_queue_for_domains(domains: dict[Position, int]) -> tuple[deque[Unit], set[Unit]]:
        rows = {
            ("row", row)
            for row, _ in domains
        }
        columns = {
            ("column", column)
            for _, column in domains
        }
        units = [*sorted(rows), *sorted(columns)]
        return deque(units), set(units)

    def _apply_count_rule(self, positions: tuple[Position, ...], domains: dict[Position, int], assign: Assign) -> None:
        half = len(positions) // 2
        sun_count = sum(domains[position] == SUN for position in positions)
        moon_count = sum(domains[position] == MOON for position in positions)
        if sun_count > half or moon_count > half:
            raise UnsolvablePuzzle("symbol count rule is violated")
        unknown = [position for position in positions if domains[position] == BOTH]
        if sun_count == half:
            for position in unknown:
                assign(position, MOON)
        elif moon_count == half:
            for position in unknown:
                assign(position, SUN)

    def _apply_triple_rules(self, positions: tuple[Position, ...], domains: dict[Position, int], assign: Assign) -> None:
        for start in range(len(positions) - 2):
            first, middle, last = positions[start : start + 3]
            values = (domains[first], domains[middle], domains[last])
            if values[0] != BOTH and values[0] == values[1] == values[2]:
                raise UnsolvablePuzzle("three identical adjacent symbols")
            if values[0] != BOTH and values[0] == values[1] and values[2] == BOTH:
                assign(last, self._opposite(values[0]))
            elif values[1] != BOTH and values[1] == values[2] and values[0] == BOTH:
                assign(first, self._opposite(values[1]))
            elif values[0] != BOTH and values[0] == values[2] and values[1] == BOTH:
                assign(middle, self._opposite(values[0]))

    def _apply_matching_endpoints_rule(
        self,
        positions: tuple[Position, ...],
        domains: dict[Position, int],
        assign: Assign,
    ) -> None:
        first, second, fifth, last = positions[0], positions[1], positions[-2], positions[-1]
        if domains[first] != BOTH and domains[first] == domains[last]:
            if domains[second] == BOTH:
                assign(second, self._opposite(domains[first]))
            if domains[fifth] == BOTH:
                assign(fifth, self._opposite(domains[first]))

    def _apply_terminal_pair_rule(
        self,
        positions: tuple[Position, ...],
        domains: dict[Position, int],
        assign: Assign,
    ) -> None:
        if len(positions) != 6:
            return

        left = tuple(domains[position] for position in positions[:3])
        right = tuple(domains[position] for position in positions[3:])

        if all(value == BOTH for value in left) and right[0] != BOTH and right[1] != BOTH and right[2] != BOTH:
            if right[0] != right[1] and right[1] == right[2]:
                assign(positions[0], right[0])

        if all(value == BOTH for value in right) and left[0] != BOTH and left[1] != BOTH and left[2] != BOTH:
            if left[0] == left[1] and left[0] != left[2]:
                assign(positions[-1], left[2])

    def _apply_equal_pair_endpoint_rule(
        self,
        positions: tuple[Position, ...],
        domains: dict[Position, int],
        constraints: tuple[Constraint, ...],
        assign: Assign,
    ) -> None:
        first, second, endpoint = positions[0], positions[1], positions[-1]
        if domains[endpoint] == BOTH:
            return
        if not self._has_relation(first, second, Relation.EQUAL, constraints):
            return
        assign(first, self._opposite(domains[endpoint]))
        assign(second, self._opposite(domains[endpoint]))

    @staticmethod
    def _has_relation(
        first: Position,
        second: Position,
        relation: Relation,
        constraints: tuple[Constraint, ...],
    ) -> bool:
        return any(
            constraint.relation is relation
            and {constraint.first, constraint.second} == {first, second}
            for constraint in constraints
        )

    def _apply_relation(
        self,
        constraint: Constraint,
        domains: dict[Position, int],
        assign: Assign,
    ) -> None:
        first, second = constraint.first, constraint.second
        first_domain, second_domain = domains[first], domains[second]
        allowed = self._allowed_pairs(constraint.relation)
        compatible = tuple(
            pair
            for pair in allowed
            if first_domain & pair[0]
            and second_domain & pair[1]
            and self._pair_is_locally_valid(first, second, pair, domains)
        )
        if not compatible:
            raise UnsolvablePuzzle("relation constraint is violated")
        assign(first, self._combine(pair[0] for pair in compatible))
        assign(second, self._combine(pair[1] for pair in compatible))

    def _pair_is_locally_valid(
        self,
        first: Position,
        second: Position,
        pair: tuple[int, int],
        domains: dict[Position, int],
    ) -> bool:
        candidate_domains = domains.copy()
        candidate_domains[first] = pair[0]
        candidate_domains[second] = pair[1]
        affected_units = {
            ("row", first[0]),
            ("column", first[1]),
            ("row", second[0]),
            ("column", second[1]),
        }
        return all(
            self._unit_is_locally_valid(self._unit_positions(unit), candidate_domains)
            for unit in affected_units
        )

    @staticmethod
    def _unit_is_locally_valid(positions: tuple[Position, ...], domains: dict[Position, int]) -> bool:
        half = len(positions) // 2
        sun_count = sum(domains[position] == SUN for position in positions)
        moon_count = sum(domains[position] == MOON for position in positions)
        unknown_count = sum(domains[position] == BOTH for position in positions)
        if sun_count > half or moon_count > half:
            return False
        if sun_count + unknown_count < half or moon_count + unknown_count < half:
            return False
        for start in range(len(positions) - 2):
            values = tuple(domains[position] for position in positions[start : start + 3])
            if values[0] != BOTH and values[0] == values[1] == values[2]:
                return False
        return True

    def _validate_complete(self, domains: dict[Position, int], board: Board) -> None:
        if any(domain == BOTH for domain in domains.values()):
            raise DeductionStalled("deduction stopped before the board was complete")
        for row in range(BOARD_SIZE):
            self._apply_line_rules(self._unit_positions(("row", row)), domains, board.constraints, self._no_assign)
        for column in range(BOARD_SIZE):
            self._apply_line_rules(self._unit_positions(("column", column)), domains, board.constraints, self._no_assign)
        for constraint in board.constraints:
            self._apply_relation(constraint, domains, self._no_assign)

    @staticmethod
    def _board_from_domains(board: Board, domains: dict[Position, int]) -> Board:
        rows = tuple(
            tuple(Cell.SUN if domains[(row, column)] == SUN else Cell.MOON for column in range(BOARD_SIZE))
            for row in range(BOARD_SIZE)
        )
        return Board(rows, board.constraints)

    @staticmethod
    def _domain_for_cell(cell: Cell) -> int:
        return {Cell.SUN: SUN, Cell.MOON: MOON, Cell.UNKNOWN: BOTH}[cell]

    @staticmethod
    def _combine(values: Iterable[int]) -> int:
        result = 0
        for value in values:
            result |= value
        return result

    @staticmethod
    def _allowed_pairs(relation: Relation) -> tuple[tuple[int, int], ...]:
        if relation is Relation.EQUAL:
            return ((SUN, SUN), (MOON, MOON))
        return ((SUN, MOON), (MOON, SUN))

    @staticmethod
    def _assign(position: Position, value: int, domains: dict[Position, int]) -> bool:
        restricted = domains[position] & value
        if not restricted:
            raise UnsolvablePuzzle(f"cell {position} has conflicting deductions")
        changed = restricted != domains[position]
        domains[position] = restricted
        return changed

    @staticmethod
    def _opposite(value: int) -> int:
        return MOON if value == SUN else SUN

    @staticmethod
    def _no_assign(position: Position, value: int) -> None:
        return None