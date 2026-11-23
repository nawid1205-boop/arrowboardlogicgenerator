"""Testy logiki Arrow Out. Rdzeń, dopełnienie i przypadki ręczne."""

from __future__ import annotations

import random
import time
import tkinter as tk
import unittest

import generator
from engine import Arrow, Board, bend_count, can_move, solve_board
from fill import fill_board, select_variant
from generator import build_puzzle, generate_board, generate_core, generate_core_report
from difficulty import LABELS, analyze_difficulty, profile_for
from quality_logic import LOGIC_WEIGHTS, analyze_logic, release_curve, selection_key
from quality_visual import VISUAL_WEIGHTS, analyze_visual, spatial_balance
import main
from main import ArrowApp, arrow_geometry, point_hits_body

SEED_COUNT = 200
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
    def test_two_hundred_seeds(self):
        seen = set()
        kinds = {"short_straight": 0, "long_straight": 0, "one_bend": 0, "multi_bend": 0}
        fill_arrows = 0
        fill_curved = 0
        core_cover = []
        final_cover = []
        core_free = []
        final_free = []
        core_depth = []
        final_stages = []
        fallbacks = []
        core_logic = []
        final_logic = []
        core_visual = []
        final_visual = []
        for seed in range(SEED_COUNT):
            with self.subTest(seed=seed):
                first = build_puzzle(seed, report=seed < 3)
                second = build_puzzle(seed, report=False)
                self.assertEqual(dump(first.core), dump(second.core))
                self.assertEqual(dump(first.final), dump(second.final))
                self.assert_core(first.core)
                self.assert_final(first)
                seen.add(dump(first.final))
                fill_arrows += first.fill_stats["added"]
                final_only = first.final.arrows[len(first.core.arrows) :]
                fill_curved += sum(1 for arrow in final_only if bend_count(arrow.cells))
                core_cover.append(first.core_stats["filled"])
                final_cover.append(first.fill_stats["cover"])
                core_free.append(first.core_stats["free"])
                final_free.append(first.final_stats["free"])
                core_depth.append(first.core_stats["depth"])
                final_stages.append(first.final_stats["stages"])
                fallbacks.append(first.core_stats["fallback"])
                core_logic.append(first.core_stats["logic"])
                final_logic.append(first.final_stats["logic"])
                core_visual.append(first.core_stats["visual"])
                final_visual.append(first.final_stats["visual"])
                self.assertFalse(first.fill_stats["time_capped"])
                for arrow in first.core.arrows:
                    bends = bend_count(arrow.cells)
                    if bends == 0 and len(arrow.cells) <= 3:
                        kinds["short_straight"] += 1
                    elif bends == 0:
                        kinds["long_straight"] += 1
                    elif bends == 1:
                        kinds["one_bend"] += 1
                    else:
                        kinds["multi_bend"] += 1
        self.assertGreaterEqual(len(seen), SEED_COUNT - 5)
        for name, count in kinds.items():
            self.assertGreater(count, 0, name)
        self.assertGreater(fill_arrows, 0)
        self.assertGreater(fill_curved, 0)
        self.assertEqual(sum(1 for seed_fallback in fallbacks if seed_fallback), 0)
        print(
            f"[summary] seeds={SEED_COUNT} "
            f"core_cover={min(core_cover)}-{max(core_cover)} "
            f"final_cover={min(final_cover)}-{max(final_cover)} "
            f"fill_arrows={fill_arrows} fill_curved={fill_curved} "
            f"core_free={min(core_free)}-{max(core_free)} "
            f"final_free={min(final_free)}-{max(final_free)} "
            f"core_depth={min(core_depth)}-{max(core_depth)} "
            f"stages={min(final_stages)}-{max(final_stages)} "
            f"core_logic={min(core_logic):.3f}-{max(core_logic):.3f} "
            f"final_logic={min(final_logic):.3f}-{max(final_logic):.3f} "
            f"core_visual={min(core_visual):.3f}-{max(core_visual):.3f} "
            f"final_visual={min(final_visual):.3f}-{max(final_visual):.3f}",
            flush=True,
        )

    def test_generate_board_matches_fill_when_enabled(self):
        puzzle = build_puzzle(7, report=False)
        shown = generate_board(7)
        self.assertEqual(dump(shown), dump(puzzle.final))
        core = generate_core(7)
        self.assertEqual(dump(core), dump(puzzle.core))

    def test_include_fill_flag_keeps_core_only(self):
        previous = generator.INCLUDE_FILL
        generator.INCLUDE_FILL = False
        try:
            puzzle = build_puzzle(4, report=False)
            self.assertEqual(dump(puzzle.final), dump(puzzle.core))
            self.assertEqual(puzzle.fill_stats["added"], 0)
        finally:
            generator.INCLUDE_FILL = previous

    def test_isolated_holes_are_left_empty(self):
        board = _isolated_holes()
        before = dump(board)
        started = time.perf_counter()
        filled, stats = fill_board(board, 1)
        self.assertLess(time.perf_counter() - started, 1.0)
        self.assertEqual(dump(board), before)
        self.assertEqual(len(filled.arrows), len(board.arrows))
        self.assertEqual(stats["added"], 0)
        self.assertGreater(stats["empty"], 0)

    def test_corridor_can_be_filled_without_touching_core(self):
        board = _corridor_board()
        before = dump(board)
        order, error = solve_board(board)
        self.assertIsNone(error)
        self.assertEqual(len(order), len(board.arrows))
        filled, stats = fill_board(board, 2)
        self.assertEqual(dump(board), before)
        self.assertGreaterEqual(stats["added"], 1)
        self.assertGreater(stats["extra_cells"], 1)
        self.assert_prefix_and_peel(board, filled)

    def test_large_region_fills_without_requiring_full_cover(self):
        board = _open_region_board()
        filled, stats = fill_board(board, 3)
        self.assertGreaterEqual(stats["added"], 2)
        self.assertGreaterEqual(stats["extra_cells"], 8)
        self.assertGreater(stats["empty"], 0)
        solved, error = solve_board(filled)
        self.assertIsNone(error)
        self.assertEqual(len(solved), len(filled.arrows))
        self.assert_prefix_and_peel(board, filled)

    def test_node_limit_stops(self):
        board = _open_region_board()
        started = time.perf_counter()
        filled, stats = fill_board(board, 5, node_limit=2)
        self.assertLess(time.perf_counter() - started, 1.0)
        self.assertLessEqual(stats["added"], 2)
        self.assert_prefix_and_peel(board, filled)
        solved, error = solve_board(filled)
        self.assertIsNone(error)

    def assert_core(self, board: Board):
        self.assertEqual(board.size, 12)
        self.assertGreaterEqual(len(board.arrows), 12)
        self.assertLessEqual(len(board.arrows), 16)
        self.assert_geometry(board)
        curved = sum(1 for arrow in board.arrows if bend_count(arrow.cells))
        straight = len(board.arrows) - curved
        self.assertGreaterEqual(curved, 2)
        self.assertGreaterEqual(straight, 2)
        free = [arrow for arrow in board.arrows if can_move(arrow, board)]
        blocked = [arrow for arrow in board.arrows if not can_move(arrow, board)]
        self.assertGreaterEqual(len(free), 1)
        self.assertGreaterEqual(len(blocked), 1)
        self.assertLessEqual(len(free), len(blocked))
        self.assertLess(len(board.occupied), board.size * board.size)
        order, error = solve_board(board)
        self.assertIsNone(error)
        self.assertTrue(replay(board, order))
        reverse_ids = [arrow.id for arrow in reversed(board.arrows)]
        self.assertTrue(replay(board, reverse_ids))
        for arrow in free:
            reduced = board.copy()
            reduced.remove(arrow.id)
            _rest, rest_error = solve_board(reduced)
            self.assertIsNone(rest_error)

    def assert_final(self, puzzle):
        self.assertTrue(puzzle.core_stats["solved"])
        self.assertTrue(puzzle.final_stats["solved"])
        self.assertLessEqual(puzzle.final_stats["free"], puzzle.core_stats["free"] + 2)
        self.assertEqual(puzzle.fill_stats["cover"], len(puzzle.final.occupied))
        self.assertEqual(
            puzzle.fill_stats["extra_cells"],
            len(puzzle.final.occupied) - len(puzzle.core.occupied),
        )
        self.assert_geometry(puzzle.final)
        self.assert_prefix_and_peel(puzzle.core, puzzle.final)
        low_order, low_ok = greedy(
            puzzle.final, lambda arrows: min(arrows, key=lambda arrow: arrow.id)
        )
        self.assertTrue(low_ok)
        solved, error = solve_board(puzzle.final)
        self.assertIsNone(error)
        self.assertEqual(low_order, solved)
        shuffled = puzzle.final.copy()
        random.Random(0).shuffle(shuffled.arrows)
        shuffled_order, shuffled_error = solve_board(shuffled)
        self.assertIsNone(shuffled_error)
        self.assertEqual(shuffled_order, solved)

    def assert_prefix_and_peel(self, core: Board, final: Board):
        self.assertGreaterEqual(len(final.arrows), len(core.arrows))
        for original, current in zip(core.arrows, final.arrows):
            self.assertEqual(original.id, current.id)
            self.assertEqual(original.cells, current.cells)
            self.assertEqual(original.direction, current.direction)
        work = final.copy()
        for arrow in reversed(final.arrows[len(core.arrows) :]):
            current = work.arrow_by_id(arrow.id)
            self.assertIsNotNone(current)
            self.assertTrue(can_move(current, work))
            work.remove(arrow.id)
        self.assertEqual(dump(work), dump(core))

    def assert_geometry(self, board: Board):
        self.assertEqual(len({arrow.id for arrow in board.arrows}), len(board.arrows))
        occupied = {}
        for arrow in board.arrows:
            self.assertGreaterEqual(len(arrow.cells), 2)
            self.assertLessEqual(len(arrow.cells), 8)
            self.assertEqual(arrow.direction, last_direction(arrow))
            self.assertEqual(len(set(arrow.cells)), len(arrow.cells))
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
                    direction = next(name for name, step in DIRECTIONS.items() if step == delta)
                    if previous_direction is not None:
                        self.assertNotEqual(direction, OPPOSITE[previous_direction])
                    previous_direction = direction
            own = set(arrow.cells)
            self.assertTrue(own.isdisjoint(independent_exit(arrow, board.size)))
            self.assertEqual(can_move(arrow, board), not independently_blocked(arrow, board))


class QualityTests(unittest.TestCase):
    def test_dependency_edge_follows_the_exit(self):
        board = Board(12)
        board.add(Arrow(1, ((0, 0), (0, 1))))
        board.add(Arrow(2, ((0, 4), (0, 5))))
        report = analyze_logic(board)
        self.assertEqual(report["blockers"][1], [2])
        self.assertEqual(report["blockers"][2], [])
        self.assertGreaterEqual(report["depth"], 2)
        self.assertEqual(report["splits"], 0)
        self.assertEqual(report["isolated"], 0)

    def test_release_curve_accounts_for_every_arrow(self):
        board = Board(12)
        board.add(Arrow(1, ((1, 0), (1, 1), (1, 2))))
        board.add(Arrow(2, ((1, 5), (1, 6))))
        board.add(Arrow(3, ((1, 9), (1, 10))))
        curve = release_curve(board)
        self.assertEqual(sum(curve), len(board.arrows))
        self.assertGreaterEqual(curve[0], 1)
        report = analyze_logic(board)
        self.assertEqual(report["curve"], curve)
        self.assertEqual(report["stages"], len(curve))
        self.assertTrue(report["solved"])

    def test_chain_has_more_depth_than_independent_arrows(self):
        chain = Board(12)
        chain.add(Arrow(1, ((2, 0), (2, 1))))
        chain.add(Arrow(2, ((2, 4), (2, 5))))
        chain.add(Arrow(3, ((2, 8), (2, 9))))
        loose = Board(12)
        loose.add(Arrow(1, ((0, 10), (0, 11))))
        loose.add(Arrow(2, ((4, 10), (4, 11))))
        loose.add(Arrow(3, ((8, 10), (8, 11))))
        chain_report = analyze_logic(chain)
        loose_report = analyze_logic(loose)
        self.assertGreater(chain_report["depth"], loose_report["depth"])
        self.assertGreater(chain_report["parts"]["depth"], loose_report["parts"]["depth"])
        self.assertEqual(loose_report["isolated"], 3)
        self.assertGreater(chain_report["parts"]["relevance"], loose_report["parts"]["relevance"])

    def test_scores_stay_inside_zero_and_one_and_follow_weights(self):
        board = build_puzzle(11, report=False).core
        logic = analyze_logic(board)
        visual = analyze_visual(board)
        for value in (*logic["parts"].values(), logic["score"]):
            self.assertGreaterEqual(value, 0.0)
            self.assertLessEqual(value, 1.0)
        for value in (*visual["parts"].values(), visual["score"]):
            self.assertGreaterEqual(value, 0.0)
            self.assertLessEqual(value, 1.0)
        saved = dict(LOGIC_WEIGHTS)
        LOGIC_WEIGHTS.update({name: 0.0 for name in saved})
        LOGIC_WEIGHTS["opening"] = 1.0
        try:
            only_opening = analyze_logic(board)["score"]
        finally:
            LOGIC_WEIGHTS.update(saved)
        self.assertAlmostEqual(only_opening, logic["parts"]["opening"])
        again = analyze_logic(board)
        self.assertEqual(again["score"], logic["score"])
        self.assertEqual(again["curve"], logic["curve"])
        self.assertEqual(analyze_visual(board)["score"], visual["score"])
        self.assertGreater(sum(VISUAL_WEIGHTS.values()), 0)

    def test_spread_board_is_more_balanced_than_a_corner_cluster(self):
        packed = Board(12)
        packed.add(Arrow(1, ((0, 0), (0, 1))))
        packed.add(Arrow(2, ((1, 0), (1, 1))))
        spread = Board(12)
        spread.add(Arrow(1, ((0, 0), (0, 1))))
        spread.add(Arrow(2, ((10, 10), (10, 11))))
        self.assertGreater(
            analyze_visual(spread)["parts"]["balance"],
            analyze_visual(packed)["parts"]["balance"],
        )

    def test_fill_rejects_extra_free_arrows_even_when_they_cover_more(self):
        core = Board(12)
        core.add(Arrow(1, ((0, 0), (0, 1))))
        fuller = core.copy()
        fuller.add(Arrow(2, ((3, 0), (3, 1))))
        fuller.add(Arrow(3, ((5, 0), (5, 1))))
        fuller.add(Arrow(4, ((7, 0), (7, 1))))
        chosen, dropped = select_variant(core, [core.copy(), fuller])
        self.assertEqual(dump(chosen), dump(core))
        self.assertGreaterEqual(dropped, 1)
        self.assertGreater(selection_key(0.90, 0.40, 20), selection_key(0.70, 0.95, 100))
        self.assertGreater(selection_key(0.80, 0.70, 30), selection_key(0.81, 0.40, 90))
        self.assertLess(selection_key(0.80, 0.60, 30), selection_key(0.80, 0.60, 90))

    def test_missing_candidates_report_the_fallback_board(self):
        report = generate_core_report(3, trials=0)
        self.assertTrue(report.fallback)
        self.assertEqual(report.trials, 0)
        self.assertGreaterEqual(len(report.board.arrows), 12)
        order, error = solve_board(report.board)
        self.assertIsNone(error)
        self.assertEqual(len(order), len(report.board.arrows))
        curved = sum(1 for arrow in report.board.arrows if bend_count(arrow.cells))
        straight = len(report.board.arrows) - curved
        free = sum(1 for arrow in report.board.arrows if can_move(arrow, report.board))
        self.assertGreaterEqual(curved, 2)
        self.assertGreaterEqual(straight, 2)
        self.assertGreaterEqual(free, 1)
        self.assertLessEqual(free, len(report.board.arrows) - free)


def _leftward(row: int, tail_col: int, head_col: int):
    return tuple((row, col) for col in range(tail_col, head_col - 1, -1))


def _place(board: Board, cells) -> None:
    board.add(Arrow(len(board.arrows) + 1, cells))


def _isolated_holes() -> Board:
    board = Board(12)
    for row in range(12):
        pairs = ((1, 0), (4, 3), (7, 6), (10, 9)) if row % 2 == 0 else ((2, 1), (5, 4), (8, 7), (11, 10))
        for tail, head in pairs:
            _place(board, _leftward(row, tail, head))
    return board


def _corridor_board() -> Board:
    board = Board(12)
    for row in range(12):
        if row == 6:
            _place(board, _leftward(row, 11, 8))
            continue
        _place(board, _leftward(row, 11, 6))
        _place(board, _leftward(row, 5, 0))
    return board


def _open_region_board() -> Board:
    board = Board(12)
    for row in range(12):
        if 3 <= row <= 7:
            continue
        _place(board, _leftward(row, 11, 6))
        _place(board, _leftward(row, 5, 0))
    return board


class DifficultyTests(unittest.TestCase):
    def test_every_level_is_solvable_and_keeps_the_core(self):
        rows = {level: [] for level in range(1, 6)}
        for seed in range(8):
            for level in range(1, 6):
                first = build_puzzle(seed, difficulty=level, report=False)
                second = build_puzzle(seed, difficulty=level, report=False)
                self.assertEqual(dump(first.final), dump(second.final))
                self.assertEqual(dump(first.core), dump(second.core))
                self.assertTrue(first.final_stats["solved"])
                self.assertFalse(first.final_stats["fallback"])
                self.assertLess(first.final_stats["time"], 2.0)
                self.assertGreaterEqual(first.core_stats["trials"], 1)
                self.assertLessEqual(first.core_stats["trials"], 14)
                self.assertIn("deviation", first.final_stats)
                self.assertIn("logic_difficulty", first.final_stats)
                self.assertIn("spatial", first.final_stats)
                GeneratorTests.assert_geometry(self, first.final)
                GeneratorTests.assert_prefix_and_peel(self, first.core, first.final)
                rows[level].append(first.final_stats)
        depths = [self._median(rows[level], "depth") for level in range(1, 6)]
        ratios = [self._median(rows[level], "free_ratio") for level in range(1, 6)]
        scores = [self._median(rows[level], "logic_difficulty") for level in range(1, 6)]
        self.assertLess(depths[0], depths[2])
        self.assertLess(depths[2], depths[4])
        self.assertGreater(ratios[0], ratios[2])
        self.assertGreater(ratios[2], ratios[4])
        self.assertLess(scores[0], scores[1])
        self.assertLess(scores[1], scores[4])
        self.assertGreaterEqual(depths[4], depths[3])
        self.assertGreater(self._median(rows[1], "spatial"), 0.7)

    def test_same_seed_changes_with_difficulty(self):
        easy = build_puzzle(9, difficulty=1, report=False)
        expert = build_puzzle(9, difficulty=5, report=False)
        self.assertNotEqual(dump(easy.final), dump(expert.final))
        self.assertGreater(easy.final_stats["free_ratio"], expert.final_stats["free_ratio"])
        self.assertLess(easy.final_stats["logic_difficulty"], expert.final_stats["logic_difficulty"])

    def test_unknown_difficulty_is_rejected(self):
        with self.assertRaises(ValueError):
            profile_for(0)
        with self.assertRaises(ValueError):
            build_puzzle(1, difficulty=6, report=False)

    def test_difficulty_report_matches_the_dependency_graph(self):
        board = build_puzzle(4, difficulty=2, report=False).final
        logic = analyze_logic(board)
        report = analyze_difficulty(board)
        self.assertEqual(report["blocks"], logic["blocks"])
        self.assertEqual(report["depth"], logic["depth"])
        self.assertEqual(report["curve"], logic["curve"])
        self.assertEqual(sum(report["curve"]), report["arrows"])
        self.assertGreaterEqual(report["logic_difficulty"], 0.0)
        self.assertLessEqual(report["logic_difficulty"], 1.0)
        self.assertGreaterEqual(report["spatial"], 0.0)
        self.assertLessEqual(report["spatial"], 1.0)

    def test_spatial_balance_accepts_airy_spread(self):
        packed = Board(12)
        packed.add(Arrow(1, ((0, 0), (0, 1))))
        packed.add(Arrow(2, ((0, 2), (1, 2))))
        packed.add(Arrow(3, ((1, 0), (1, 1))))
        spread = Board(12)
        spread.add(Arrow(1, ((0, 0), (0, 1))))
        spread.add(Arrow(2, ((0, 10), (0, 11))))
        spread.add(Arrow(3, ((11, 0), (11, 1))))
        spread.add(Arrow(4, ((11, 10), (11, 11))))
        self.assertGreater(spatial_balance(spread)["score"], spatial_balance(packed)["score"])
        self.assertGreater(spatial_balance(spread)["largest_empty"], 100)

    def test_slider_does_not_replace_the_board(self):
        root = tk.Tk()
        root.withdraw()
        try:
            app = ArrowApp(root)
            root.update_idletasks()
            before = dump(app.board)
            seed = app.seed
            app.difficulty.set(1)
            app._on_difficulty("1")
            self.assertEqual(seed, app.seed)
            self.assertEqual(before, dump(app.board))
            self.assertEqual(app.diff_caption.cget("text"), f"1 — {LABELS[1]}")
            self.assertEqual(int(app.difficulty.get()), 1)
        finally:
            root.destroy()

    def test_new_board_reads_the_slider(self):
        root = tk.Tk()
        root.withdraw()
        calls = []
        original = main.generate_board

        def wrapped(seed, size=12, difficulty=3):
            calls.append(difficulty)
            return original(seed, size=size, difficulty=difficulty)

        main.generate_board = wrapped
        try:
            app = ArrowApp(root)
            self.assertEqual(calls[0], 3)
            app.difficulty.set(5)
            app.new_board(seed=21)
            self.assertEqual(calls[-1], 5)
            self.assertEqual(dump(app.board), dump(original(21, difficulty=5)))
            self.assertEqual(app.seed, 21)
        finally:
            main.generate_board = original
            root.destroy()

    def _median(self, rows: list[dict], key: str) -> float:
        values = sorted(row[key] for row in rows)
        return values[len(values) // 2]


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
