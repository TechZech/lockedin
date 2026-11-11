"""Find a Hamiltonian path through the grid and ordered waypoints."""

from __future__ import annotations

from .model import Board


class Solver:
    def solve(self, board: Board) -> tuple[int, ...]:
        size = board.rows * board.columns
        neighbors = tuple(board.neighbors(i) for i in range(size))
        waypoint_numbers = {cell: number for number, cell in enumerate(board.waypoints)}
        all_cells = (1 << size) - 1
        failed: set[tuple[int, int, int]] = set()
        path = [board.waypoints[0]]

        def search(current: int, visited: int, next_waypoint: int) -> bool:
            if visited == all_cells:
                return next_waypoint == len(board.waypoints)
            state = (current, visited, next_waypoint)
            if state in failed:
                return False

            remaining = all_cells ^ visited
            reachable = 1 << current
            frontier = [current]
            while frontier:
                node = frontier.pop()
                for other in neighbors[node]:
                    bit = 1 << other
                    if (remaining & bit) and not (reachable & bit):
                        reachable |= bit
                        frontier.append(other)
            if reachable != remaining | (1 << current):
                failed.add(state)
                return False

            # Only one unvisited cell can be the eventual endpoint.
            leaves = 0
            for node in range(size):
                if remaining & (1 << node):
                    degree = sum(bool((remaining | (1 << current)) & (1 << n)) for n in neighbors[node])
                    if degree == 0:
                        failed.add(state)
                        return False
                    leaves += degree == 1
            if leaves > 1:
                failed.add(state)
                return False

            candidates = []
            for other in neighbors[current]:
                if visited & (1 << other):
                    continue
                number = waypoint_numbers.get(other)
                if number is not None and number != next_waypoint:
                    continue
                degree = sum(not (visited & (1 << n)) for n in neighbors[other])
                candidates.append((degree, other, number is not None))
            for _, other, is_waypoint in sorted(candidates):
                path.append(other)
                if search(other, visited | (1 << other), next_waypoint + is_waypoint):
                    return True
                path.pop()
            failed.add(state)
            return False

        if not search(path[0], 1 << path[0], 1):
            raise ValueError("Zip board has no solution")
        return tuple(path)
