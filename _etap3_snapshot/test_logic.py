"""Testy logiki Arrow Out. Minimum 100 pełnych plansz oraz przypadki ręczne."""

from __future__ import annotations

import random
import unittest

from engine import Arrow, Board, bend_count, can_move, solve_board
from generator import generate_board
from main import arrow_geometry, point_hits_body

SEED_COUNT = 100
DIRECTIONS = {
    "UP": (-1, 0),
    "DOWN": (1, 0),
    "LEFT": (0, -1),
    "RIGHT": (0, 1),
}
OPPOSITE = {"UP": "DOWN", "DOWN": "UP", "LEFT": "RIGHT", "RIGHT": "LEFT"}


def dump(board: Board):
    return tuple((arrow.id, arrow.direction, arrow.cells) for arrow in board.arrows)


def last_direction(arrow: Arrow) -> str:
    previous, head = arrow.cells[-2], arrow.cells[-1]
    delta = (head[0] - previous[0], head[1] - previous[1])
    for name, step in DIRECTIONS.items():
        if step == delta:
            return name
    raise AssertionError(delta)


def independent_exit(arrow: Arrow, size: int):
    d_row, d_col = DIRECTIONS[last_direction(arrow)]
    row, col = arrow.head
    cells = []
    row += d_row
    col += d_col
    while 0 <= row < size and 0 <= col < size:
        cells.append((row, col))
        row += d_row
        col += d_col
    return cells


def independently_blocked(arrow: Arrow, board: Board) -> bool:
    for cell in independent_exit(arrow, board.size):
        owner = board.occupied.get(cell)
        if owner is not None and owner != arrow.id:
            return True
    return False


def replay(board: Board, order: list[int]) -> bool:
    work = board.copy()
    for arrow_id in order:
        arrow = work.arrow_by_id(arrow_id)
        if arrow is None or independently_blocked(arrow, work):
            return False
        if can_move(arrow, work) == independently_blocked(arrow, work):
            return False
        work.remove(arrow_id)
    return not work.arrows


def greedy(board: Board, pick) -> tuple[list[int], bool]:
    work = board.copy()
    order = []
    while work.arrows:
        movable = [arrow for arrow in work.arrows if can_move(arrow, work)]
        if not movable:
            return order, False
        chosen = pick(movable)
        order.append(chosen.id)
        work.remove(chosen.id)
    return order, True


class HandCraftedTests(unittest.TestCase):
    def test_clear_right_arrow_can_leave(self):
        board = Board(12)
        arrow = Arrow(1, ((2, 1), (2, 2), (2, 3)))
        board.add(arrow)
        self.assertEqual(arrow.direction, "RIGHT")
        self.assertTrue(can_move(arrow, board))
        self.assertFalse(independently_blocked(arrow, board))

    def test_blocker_on_exit_stops_arrow(self):
        board = Board(12)
        blocked = Arrow(1, ((0, 0), (0, 1)))
        blocker = Arrow(2, ((0, 4), (1, 4), (2, 4)))
        board.add(blocked)
        board.add(blocker)
        self.assertFalse(can_move(blocked, board))
        self.assertTrue(can_move(blocker, board))
        board.remove(2)
        self.assertTrue(can_move(board.arrow_by_id(1), board))

    def test_own_cells_do_not_block(self):
        board = Board(12)
        arrow = Arrow(1, ((4, 6), (4, 5), (4, 4)))
        board.add(arrow)
        self.assertEqual(arrow.head, (4, 4))
        self.assertTrue(can_move(arrow, board))
        self.assertNotIn(arrow.head, independent_exit(arrow, 12))

    def test_bent_exit_follows_last_segment_only(self):
        board = Board(12)
        arrow = Arrow(1, ((1, 1), (1, 2), (1, 3), (2, 3), (3, 3)))
        board.add(arrow)
        self.assertEqual(arrow.direction, "DOWN")
        self.assertEqual(bend_count(arrow.cells), 1)
        self.assertEqual(independent_exit(arrow, 12)[0], (4, 3))
        side = Arrow(2, ((1, 5), (1, 6)))
        board.add(side)
        self.assertTrue(can_move(arrow, board))
        front = Arrow(3, ((6, 3), (7, 3)))
        board.add(front)
        self.assertFalse(can_move(board.arrow_by_id(1), board))

    def test_head_on_edge_is_free(self):
        board = Board(12)
        arrow = Arrow(1, ((2, 7), (1, 7), (0, 7)))
        other = Arrow(2, ((5, 0), (5, 1), (5, 2)))
        board.add(arrow)
        board.add(other)
        self.assertEqual(independent_exit(arrow, 12), [])
        self.assertTrue(can_move(arrow, board))

    def test_solver_removes_chain_from_the_exit_side(self):
        board = Board(12)
        board.add(Arrow(1, ((3, 0), (3, 1))))
        board.add(Arrow(2, ((3, 3), (3, 4))))
        board.add(Arrow(3, ((3, 7), (3, 8), (3, 9))))
        order, error = solve_board(board)
        self.assertIsNone(error)
        self.assertEqual(order, [3, 2, 1])
        self.assertEqual(len(board.arrows), 3)

    def test_solver_reports_deadlock(self):
        board = Board(12)
        board.add(Arrow(1, ((1, 0), (1, 1))))
        board.add(Arrow(2, ((1, 5), (1, 4), (1, 3))))
        order, error = solve_board(board)
        self.assertEqual(order, [])
        self.assertIsNotNone(error)
        self.assertFalse(can_move(board.arrows[0], board))
        self.assertFalse(can_move(board.arrows[1], board))

    def test_all_four_directions_have_correct_heads(self):
        samples = [
            Arrow(1, ((0, 0), (0, 1), (0, 2))),
            Arrow(2, ((1, 5), (1, 4))),
            Arrow(3, ((0, 8), (1, 8), (2, 8), (3, 8))),
            Arrow(4, ((6, 2), (5, 2), (4, 2))),
        ]
        for arrow in samples:
            d_row, d_col = DIRECTIONS[arrow.direction]
            for index in range(1, len(arrow.cells)):
                previous = arrow.cells[index - 1]
                current = arrow.cells[index]
                self.assertEqual(
                    (current[0] - previous[0], current[1] - previous[1]),
                    (d_row, d_col),
                )

    def test_rejects_reverse_and_skip(self):
        with self.assertRaises(ValueError):
            Arrow(1, ((0, 0), (0, 1), (0, 0)))
        with self.assertRaises(ValueError):
            Arrow(2, ((0, 0), (0, 2)))


class GeneratorTests(unittest.TestCase):
    def test_hundred_full_boards(self):
        seen = set()
        kinds = {"short_straight": 0, "long_straight": 0, "one_bend": 0, "multi_bend": 0}
        for seed in range(SEED_COUNT):
            with self.subTest(seed=seed):
                first = generate_board(seed)
                second = generate_board(seed)
                self.assertEqual(dump(first), dump(second))
                self.assert_board(first)
                seen.add(dump(first))
                for arrow in first.arrows:
                    bends = bend_count(arrow.cells)
                    if bends == 0 and len(arrow.cells) <= 3:
                        kinds["short_straight"] += 1
                    elif bends == 0:
                        kinds["long_straight"] += 1
                    elif bends == 1:
                        kinds["one_bend"] += 1
                    else:
                        kinds["multi_bend"] += 1
        self.assertEqual(len(seen), SEED_COUNT)
        for name, count in kinds.items():
            self.assertGreater(count, 0, name)

    def assert_board(self, board: Board):
        self.assertEqual(board.size, 12)
        self.assertGreaterEqual(len(board.arrows), 18)
        self.assertLessEqual(len(board.arrows), 72)
        self.assertEqual(len({arrow.id for arrow in board.arrows}), len(board.arrows))

        occupied = {}
        curved = 0
        straight = 0
        for arrow in board.arrows:
            self.assertGreaterEqual(len(arrow.cells), 2)
            self.assertLessEqual(len(arrow.cells), 8)
            self.assertEqual(arrow.direction, last_direction(arrow))
            self.assertEqual(len(set(arrow.cells)), len(arrow.cells))
            bends = bend_count(arrow.cells)
            if bends:
                curved += 1
            else:
                straight += 1
            previous_direction = None
            for index, cell in enumerate(arrow.cells):
                row, col = cell
                self.assertGreaterEqual(row, 0)
                self.assertLess(row, board.size)
                self.assertGreaterEqual(col, 0)
                self.assertLess(col, board.size)
                self.assertNotIn(cell, occupied)
                occupied[cell] = arrow.id
                if index:
                    previous = arrow.cells[index - 1]
                    delta = (row - previous[0], col - previous[1])
                    self.assertIn(delta, set(DIRECTIONS.values()))
                    direction = next(
                        name for name, step in DIRECTIONS.items() if step == delta
                    )
                    if previous_direction is not None:
                        self.assertNotEqual(direction, OPPOSITE[previous_direction])
                    previous_direction = direction
            own = set(arrow.cells)
            self.assertTrue(own.isdisjoint(independent_exit(arrow, board.size)))
            self.assertEqual(can_move(arrow, board), not independently_blocked(arrow, board))

        self.assertEqual(len(occupied), board.size * board.size)
        self.assertEqual(len(occupied), 144)
        self.assertGreaterEqual(curved, 1)
        self.assertGreaterEqual(straight, 1)
        self.assertTrue(any(len(arrow.cells) >= 5 for arrow in board.arrows))
        self.assertFalse(all(len(arrow.cells) == 2 for arrow in board.arrows))
        free = [arrow for arrow in board.arrows if not independently_blocked(arrow, board)]
        blocked = [arrow for arrow in board.arrows if independently_blocked(arrow, board)]
        self.assertGreaterEqual(len(free), 1)
        self.assertGreaterEqual(len(blocked), 1)
        self.assertLessEqual(len(free), len(blocked))

        order, error = solve_board(board)
        self.assertIsNone(error)
        self.assertEqual(len(order), len(board.arrows))
        self.assertTrue(replay(board, order))

        reverse_ids = [arrow.id for arrow in reversed(board.arrows)]
        self.assertTrue(replay(board, reverse_ids))

        for arrow in free:
            reduced = board.copy()
            self.assertTrue(can_move(arrow, reduced))
            reduced.remove(arrow.id)
            _rest, rest_error = solve_board(reduced)
            self.assertIsNone(rest_error)

        low_order, low_ok = greedy(board, lambda arrows: min(arrows, key=lambda arrow: arrow.id))
        high_order, high_ok = greedy(board, lambda arrows: max(arrows, key=lambda arrow: arrow.id))
        self.assertTrue(low_ok)
        self.assertTrue(high_ok)
        self.assertEqual(low_order, order)
        self.assertTrue(replay(board, high_order))

        shuffled = board.copy()
        random.Random(0).shuffle(shuffled.arrows)
        shuffled_order, shuffled_error = solve_board(shuffled)
        self.assertIsNone(shuffled_error)
        self.assertEqual(shuffled_order, order)


class HitTests(unittest.TestCase):
    def test_click_hits_every_cell_at_two_scales(self):
        arrow = Arrow(1, ((2, 1), (2, 2), (2, 3), (2, 4)))
        for cell in (22.0, 48.0, 71.5):
            origin_x, origin_y = 40.0, 55.0
            body = arrow_geometry(arrow, origin_x, origin_y, cell)
            for row, col in arrow.cells:
                x = origin_x + (col + 0.5) * cell
                y = origin_y + (row + 0.5) * cell
                self.assertTrue(point_hits_body(x, y, body))
            tip_x, tip_y = body["triangle"][0]
            self.assertTrue(point_hits_body(tip_x, tip_y, body))
            empty_x = origin_x + (6 + 0.5) * cell
            empty_y = origin_y + (2 + 0.5) * cell
            self.assertFalse(point_hits_body(empty_x, empty_y, body))

    def test_vertical_arrow_misses_neighbor_column(self):
        arrow = Arrow(3, ((8, 4), (7, 4), (6, 4)))
        cell = 36.0
        body = arrow_geometry(arrow, 10.0, 12.0, cell)
        for row, col in arrow.cells:
            x = 10.0 + (col + 0.5) * cell
            y = 12.0 + (row + 0.5) * cell
            self.assertTrue(point_hits_body(x, y, body))
        neighbor_x = 10.0 + (5 + 0.5) * cell
        neighbor_y = 12.0 + (7 + 0.5) * cell
        self.assertFalse(point_hits_body(neighbor_x, neighbor_y, body))

    def test_bent_arrow_hits_each_segment_not_the_gap(self):
        arrow = Arrow(4, ((2, 2), (2, 3), (2, 4), (3, 4), (4, 4)))
        cell = 40.0
        origin_x, origin_y = 8.0, 8.0
        body = arrow_geometry(arrow, origin_x, origin_y, cell)
        for row, col in arrow.cells:
            x = origin_x + (col + 0.5) * cell
            y = origin_y + (row + 0.5) * cell
            self.assertTrue(point_hits_body(x, y, body))
        gap_x = origin_x + (3 + 0.5) * cell
        gap_y = origin_y + (3 + 0.5) * cell
        self.assertFalse(point_hits_body(gap_x, gap_y, body))
        beside_x = origin_x + (2 + 0.5) * cell
        beside_y = origin_y + (1 + 0.5) * cell
        self.assertFalse(point_hits_body(beside_x, beside_y, body))


if __name__ == "__main__":
    unittest.main()
