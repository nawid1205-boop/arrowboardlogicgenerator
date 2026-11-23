"""Generator pełnych plansz Arrow Out.

Każda komórka należy do dokładnie jednej strzałki. Ścieżka Hamiltona
pokrywa siatkę, potem jest cięta na odcinki o długości 2–8. Grot jest
tak ustawiony, żeby graf blokad był acykliczny: strzałka zależy od tych,
które stoją na jej prostym wyjeździe. Kolejność odwrotna do usuwania
jest wtedy poprawną konstrukcją, a solver potwierdza wynik.

Starszy generator kończył po 12–16 strzałkach i nie cofał decyzji, które
odcinały puste regiony. Tu puste pola nie powstają, bo podział ścieżki
zużywa całą planszę, a ślepe orientacje grotów są odrzucane.
"""

from __future__ import annotations

import random
import time

from engine import (
    DELTA_TO_DIRECTION,
    Arrow,
    Board,
    bend_count,
    can_move,
    ray_cells,
    solve_board,
)

MIN_LENGTH = 2
MAX_LENGTH = 8
_WEIGHTS = {2: 1, 3: 3, 4: 4, 5: 4, 6: 3, 7: 2, 8: 2}
_COMPOSITIONS = 3
_MAX_FLIPS = 250


def generate_board(seed: int, size: int = 12) -> Board:
    """Zwraca pełną, rozwiązywalną planszę odtwarzalną z podanego seeda."""
    started = time.perf_counter()
    rng = random.Random(seed)
    families = _families(size)
    order = list(range(len(families)))
    rng.shuffle(order)

    best: tuple[Board, dict] | None = None
    best_score: tuple | None = None
    failed = 0

    for index in order:
        family_best: tuple[Board, dict] | None = None
        family_score: tuple | None = None
        for _ in range(_COMPOSITIONS):
            parts = _compose(rng, size * size)
            if parts is None:
                failed += 1
                continue
            repaired = _repair(_split(families[index], parts), size, rng)
            if repaired is None:
                failed += 1
                continue
            board = _assemble(repaired, size)
            if board is None:
                failed += 1
                continue
            stats = _measure(board)
            if not _acceptable(stats):
                failed += 1
                continue
            score = _score(stats)
            if family_score is None or score > family_score:
                family_best = (board, stats)
                family_score = score
        if family_best is None or family_score is None:
            continue
        if best_score is None or family_score > best_score:
            best = family_best
            best_score = family_score
        if _quality(family_best[1]):
            break

    if best is None:
        raise RuntimeError(
            f"Nie udało się wygenerować pełnej planszy dla seed={seed}."
        )

    board, stats = best
    elapsed = time.perf_counter() - started
    print(
        f"[arrow] seed={seed} arrows={stats['arrows']} "
        f"fill={stats['filled']}/{stats['area']} curved={stats['curved']} "
        f"free={stats['free']} stages={stats['stages']} "
        f"time={elapsed:.3f}s failed_attempts={failed}"
    )
    return board


def _score(stats: dict) -> tuple:
    return (
        stats["stages"],
        -stats["free"],
        stats["curved"],
        stats["long_straight"],
        stats["max_length"],
    )


def _acceptable(stats: dict) -> bool:
    return (
        stats["filled"] == stats["area"]
        and stats["curved"] >= 1
        and stats["straight"] >= 1
        and stats["max_length"] >= 4
        and stats["free"] >= 1
        and stats["blocked"] >= 1
    )


def _quality(stats: dict) -> bool:
    return _acceptable(stats) and (
        stats["curved"] >= 3
        and stats["long_straight"] >= 1
        and stats["free"] <= stats["blocked"]
        and stats["stages"] >= 6
    )


def _measure(board: Board) -> dict:
    curved = straight = free = long_straight = max_length = 0
    for arrow in board.arrows:
        bends = bend_count(arrow.cells)
        max_length = max(max_length, len(arrow.cells))
        if bends:
            curved += 1
        else:
            straight += 1
            if len(arrow.cells) >= 5:
                long_straight += 1
        if can_move(arrow, board):
            free += 1
    work = board.copy()
    stages = 0
    while work.arrows:
        movable = [arrow for arrow in work.arrows if can_move(arrow, work)]
        if not movable:
            stages = 0
            break
        stages += 1
        for arrow in movable:
            work.remove(arrow.id)
    total = len(board.arrows)
    return {
        "arrows": total,
        "area": board.size * board.size,
        "filled": len(board.occupied),
        "curved": curved,
        "straight": straight,
        "long_straight": long_straight,
        "max_length": max_length,
        "free": free,
        "blocked": total - free,
        "stages": stages,
    }


def _compose(rng: random.Random, total: int) -> list[int] | None:
    parts: list[int] = []
    while total:
        if total <= MAX_LENGTH:
            if total < MIN_LENGTH:
                return None
            parts.append(total)
            break
        bag: list[int] = []
        for length, weight in _WEIGHTS.items():
            if total - length == 1:
                continue
            bag.extend([length] * weight)
        if not bag:
            return None
        length = rng.choice(bag)
        parts.append(length)
        total -= length
    return parts


def _split(path: list[tuple[int, int]], parts: list[int]) -> list[list[tuple[int, int]]]:
    segments: list[list[tuple[int, int]]] = []
    cursor = 0
    for length in parts:
        segments.append(path[cursor : cursor + length])
        cursor += length
    return segments


def _assemble(segments: list[list[tuple[int, int]]], size: int) -> Board | None:
    if _first_self_block(segments, size) is not None:
        return None
    blockers = _blockers(segments, size)
    if _find_cycle(blockers) is not None:
        return None
    order = _removal_order(blockers)
    if order is None:
        return None
    board = Board(size)
    try:
        for new_id, index in enumerate(reversed(order), start=1):
            arrow = Arrow(new_id, tuple(segments[index]))
            if not can_move(arrow, board):
                return None
            board.add(arrow)
    except ValueError:
        return None
    _solution, error = solve_board(board)
    if error is not None or len(board.occupied) != size * size:
        return None
    return board


def _repair(
    segments: list[list[tuple[int, int]]],
    size: int,
    rng: random.Random,
) -> list[list[tuple[int, int]]] | None:
    segments = [list(segment) for segment in segments]
    seen: set[tuple] = set()
    for _ in range(_MAX_FLIPS):
        key = tuple(tuple(segment) for segment in segments)
        if key in seen:
            return None
        seen.add(key)
        self_index = _first_self_block(segments, size)
        if self_index is not None:
            flipped = list(reversed(segments[self_index]))
            if _self_blocks(flipped, size):
                return None
            segments[self_index] = flipped
            continue
        blockers = _blockers(segments, size)
        cycle = _find_cycle(blockers)
        if cycle is None:
            return segments
        choice = rng.choice(cycle)
        segments[choice] = list(reversed(segments[choice]))
    return None


def _direction(cells: list[tuple[int, int]]) -> str:
    delta = (cells[-1][0] - cells[-2][0], cells[-1][1] - cells[-2][1])
    return DELTA_TO_DIRECTION[delta]


def _self_blocks(cells: list[tuple[int, int]], size: int) -> bool:
    own = set(cells)
    head = cells[-1]
    for cell in ray_cells(head[0], head[1], _direction(cells), size):
        if cell in own:
            return True
    return False


def _first_self_block(segments: list[list[tuple[int, int]]], size: int) -> int | None:
    for index, segment in enumerate(segments):
        if _self_blocks(segment, size):
            return index
    return None


def _blockers(segments: list[list[tuple[int, int]]], size: int) -> list[tuple[int, ...]]:
    owner: dict[tuple[int, int], int] = {}
    for index, segment in enumerate(segments):
        for cell in segment:
            owner[cell] = index
    blockers: list[tuple[int, ...]] = []
    for index, segment in enumerate(segments):
        head = segment[-1]
        hits: list[int] = []
        seen: set[int] = set()
        for cell in ray_cells(head[0], head[1], _direction(segment), size):
            other = owner.get(cell)
            if other is None or other == index or other in seen:
                continue
            seen.add(other)
            hits.append(other)
        blockers.append(tuple(sorted(hits)))
    return blockers


def _find_cycle(blockers: list[tuple[int, ...]]) -> list[int] | None:
    count = len(blockers)
    color = [0] * count
    parent = [-1] * count

    def walk(start: int) -> list[int] | None:
        stack = [(start, 0)]
        color[start] = 1
        while stack:
            node, next_index = stack[-1]
            neighbors = blockers[node]
            if next_index >= len(neighbors):
                color[node] = 2
                stack.pop()
                continue
            stack[-1] = (node, next_index + 1)
            nxt = neighbors[next_index]
            if color[nxt] == 1:
                cycle = [nxt]
                cursor = node
                while cursor != nxt and cursor != -1:
                    cycle.append(cursor)
                    cursor = parent[cursor]
                return cycle
            if color[nxt] == 0:
                parent[nxt] = node
                color[nxt] = 1
                stack.append((nxt, 0))
        return None

    for start in range(count):
        if color[start] == 0:
            found = walk(start)
            if found:
                return found
    return None


def _removal_order(blockers: list[tuple[int, ...]]) -> list[int] | None:
    remaining = set(range(len(blockers)))
    order: list[int] = []
    while remaining:
        free = [
            index
            for index in range(len(blockers))
            if index in remaining and all(item not in remaining for item in blockers[index])
        ]
        if not free:
            return None
        chosen = free[0]
        order.append(chosen)
        remaining.remove(chosen)
    return order


def _families(size: int) -> list[list[tuple[int, int]]]:
    bases = (
        _row_snake(size),
        _half_vertical(size),
        _spiral(size),
    )
    seen: set[tuple[tuple[int, int], ...]] = set()
    families: list[list[tuple[int, int]]] = []
    for base in bases:
        for path in (
            base,
            _rot90(base, size),
            _rot180(base, size),
            _rot270(base, size),
            _mirror_h(base, size),
            _mirror_v(base, size),
            list(reversed(base)),
            list(reversed(_rot90(base, size))),
        ):
            key = tuple(path)
            if key in seen or not _is_ham(path, size):
                continue
            seen.add(key)
            families.append(list(path))
    if not families:
        raise RuntimeError("Brak ścieżki pokrywającej planszę.")
    return families


def _is_ham(cells: list[tuple[int, int]], size: int) -> bool:
    if len(cells) != size * size or len(set(cells)) != len(cells):
        return False
    for previous, current in zip(cells, cells[1:]):
        if abs(previous[0] - current[0]) + abs(previous[1] - current[1]) != 1:
            return False
    return True


def _row_snake(size: int) -> list[tuple[int, int]]:
    cells: list[tuple[int, int]] = []
    for row in range(size):
        cols = range(size) if row % 2 == 0 else range(size - 1, -1, -1)
        cells.extend((row, col) for col in cols)
    return cells


def _half_vertical(size: int) -> list[tuple[int, int]]:
    """Dwa węże przedzielone pionowym szwem. Zakręty wchodzą w środek planszy."""
    mid = size // 2
    cells: list[tuple[int, int]] = []
    seam = mid - 1
    for row in range(size):
        if row % 2 == 0:
            cols = range(seam, -1, -1)
        else:
            cols = range(0, seam + 1)
        cells.extend((row, col) for col in cols)
    for offset, row in enumerate(range(size - 1, -1, -1)):
        if offset % 2 == 0:
            cols = range(mid, size)
        else:
            cols = range(size - 1, mid - 1, -1)
        cells.extend((row, col) for col in cols)
    return cells


def _spiral(size: int) -> list[tuple[int, int]]:
    cells: list[tuple[int, int]] = []
    top, bottom = 0, size - 1
    left, right = 0, size - 1
    while left <= right and top <= bottom:
        cells.extend((top, col) for col in range(left, right + 1))
        top += 1
        cells.extend((row, right) for row in range(top, bottom + 1))
        right -= 1
        if top <= bottom:
            cells.extend((bottom, col) for col in range(right, left - 1, -1))
            bottom -= 1
        if left <= right:
            cells.extend((row, left) for row in range(bottom, top - 1, -1))
            left += 1
    return cells


def _rot90(cells: list[tuple[int, int]], size: int) -> list[tuple[int, int]]:
    return [(col, size - 1 - row) for row, col in cells]


def _rot180(cells: list[tuple[int, int]], size: int) -> list[tuple[int, int]]:
    return _rot90(_rot90(cells, size), size)


def _rot270(cells: list[tuple[int, int]], size: int) -> list[tuple[int, int]]:
    return _rot90(_rot180(cells, size), size)


def _mirror_h(cells: list[tuple[int, int]], size: int) -> list[tuple[int, int]]:
    return [(row, size - 1 - col) for row, col in cells]


def _mirror_v(cells: list[tuple[int, int]], size: int) -> list[tuple[int, int]]:
    return [(size - 1 - row, col) for row, col in cells]
