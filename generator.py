"""Rdzeń Arrow Out: randomized DFS i odwrotna konstrukcja.

Ścieżka rośnie wstecz od grotu. Nowa strzałka wchodzi na planszę tylko wtedy,
gdy jej prosty wyjazd jest wolny, więc odwrócona kolejność umieszczania jest
rozwiązaniem. Solver sprawdza planszę jeszcze raz.

Pokrycie siatki nie jest warunkiem rdzenia. Dopełnianie wolnych komórek robi
osobny moduł `fill`. Stała INCLUDE_FILL wybiera, czy gra pokazuje sam rdzeń,
czy rdzeń razem z dopełnieniem.

Kod rdzenia odtworzono z ostatniej wersji etapu 2 (brak repozytorium Git).
Jedyna świadoma różnica: wszystkie próby są oceniane i zostaje najlepsza
pod względem jakości logicznej, a nie pierwsza akceptowalna.
"""

from __future__ import annotations

import random
import time

from engine import (
    DIRECTION_DELTA,
    DIRECTIONS,
    OPPOSITE,
    Arrow,
    Board,
    bend_count,
    can_move,
    exit_cells,
    ray_cells,
    solve_board,
)
from fill import fill_board

# Diagnostyka: False zostawia sam rdzeń, True pokazuje rdzeń i dopełnienie.
INCLUDE_FILL = True

MIN_ARROWS = 12
MAX_ARROWS = 16
MIN_LENGTH = 2
MAX_LENGTH = 8
TURN_PROBABILITY = 0.30

_MAX_TRIALS = 10
_MAX_STAGNANT = 28
_CANDIDATES = 7
_GROW_NODE_CAP = 500


def generate_board(seed: int, size: int = 12) -> Board:
    """Zwraca planszę pokazywaną w grze."""
    return build_puzzle(seed, size).final


def generate_core(seed: int, size: int = 12) -> Board:
    """Buduje kilka rdzeni i zostawia najlepszy pod względem jakości."""
    rng = random.Random(seed)
    best: Board | None = None
    best_rank: tuple | None = None

    for _ in range(_MAX_TRIALS):
        target = rng.randint(MIN_ARROWS, MAX_ARROWS)
        board = _build_once(rng, size, target)
        if not _verified(board):
            continue
        rank = _rank(board)
        if best_rank is None or rank > best_rank:
            best = board
            best_rank = rank

    if best is not None and _has_opening(best):
        return best

    emergency = _emergency_board(size)
    if not _verified(emergency):
        raise RuntimeError(f"Nie udało się zbudować planszy dla seed={seed}")
    return emergency


def build_puzzle(seed: int, size: int = 12, *, report: bool = True):
    """Liczy rdzeń, opcjonalnie dopełnienie, i wypisuje metryki obu faz."""
    started = time.perf_counter()
    core = generate_core(seed, size)
    core_stats = metrics(core)
    if INCLUDE_FILL:
        final, fill_stats = fill_board(core, seed)
    else:
        final = core.copy()
        fill_stats = {
            "added": 0,
            "extra_cells": 0,
            "cover": core_stats["filled"],
            "area": core_stats["area"],
            "empty": core_stats["empty"],
            "rejected": 0,
        }
    final_stats = metrics(final)
    final_stats["time"] = time.perf_counter() - started
    if report:
        _report(seed, core_stats, fill_stats, final_stats)
    return Puzzle(core, final, core_stats, fill_stats, final_stats)


class Puzzle:
    def __init__(self, core: Board, final: Board, core_stats: dict, fill_stats: dict, final_stats: dict) -> None:
        self.core = core
        self.final = final
        self.core_stats = core_stats
        self.fill_stats = fill_stats
        self.final_stats = final_stats


def metrics(board: Board) -> dict:
    area = board.size * board.size
    filled = len(board.occupied)
    free = sum(1 for arrow in board.arrows if can_move(arrow, board))
    blockers = _blocker_map(board)
    curved = sum(1 for arrow in board.arrows if bend_count(arrow.cells) > 0)
    solved_order, error = solve_board(board)
    return {
        "arrows": len(board.arrows),
        "area": area,
        "filled": filled,
        "empty": area - filled,
        "blocks": sum(len(items) for items in blockers.values()),
        "depth": _chain_depth(blockers),
        "free": free,
        "blocked": len(board.arrows) - free,
        "stages": _stages(board),
        "curved": curved,
        "straight": len(board.arrows) - curved,
        "solved": error is None and len(solved_order) == len(board.arrows),
    }


def _report(seed: int, core_stats: dict, fill_stats: dict, final_stats: dict) -> None:
    print(
        f"[core] seed={seed} arrows={core_stats['arrows']} "
        f"cover={core_stats['filled']}/{core_stats['area']} "
        f"blocks={core_stats['blocks']} depth={core_stats['depth']} "
        f"free={core_stats['free']}",
        flush=True,
    )
    print(
        f"[fill] added={fill_stats['added']} "
        f"extra_cells={fill_stats['extra_cells']} "
        f"cover={fill_stats['cover']}/{fill_stats['area']} "
        f"empty={fill_stats['empty']} rejected={fill_stats['rejected']}",
        flush=True,
    )
    print(
        f"[final] solved={'yes' if final_stats['solved'] else 'no'} "
        f"time={final_stats['time']:.3f}s "
        f"stages={final_stats['stages']} free={final_stats['free']}",
        flush=True,
    )


def _build_once(rng: random.Random, size: int, target: int) -> Board:
    board = Board(size)
    next_id = 1
    stagnant = 0
    while len(board.arrows) < target and stagnant < _MAX_STAGNANT:
        chosen = _pick_candidate(rng, board)
        if chosen is None:
            stagnant += 1
            continue
        placed = Arrow(next_id, chosen.cells)
        if not _placeable(placed, board):
            stagnant += 1
            continue
        board.add(placed)
        next_id += 1
        stagnant = 0
    return board


def _pick_candidate(rng: random.Random, board: Board) -> Arrow | None:
    pool: list[Arrow] = []
    seen: set[tuple[tuple[int, int], ...]] = set()
    for _ in range(_CANDIDATES):
        if board.arrows and rng.random() < 0.78:
            arrow = _blocking_candidate(rng, board)
        else:
            arrow = None
        if arrow is None:
            arrow = _random_candidate(rng, board)
        if arrow is None or arrow.cells in seen:
            continue
        seen.add(arrow.cells)
        pool.append(arrow)
    if not pool:
        return None

    if board.arrows and rng.random() < 0.9:
        blockers = [arrow for arrow in pool if _new_blocks(arrow, board) > 0]
        if blockers:
            pool = blockers
    weights = [_weight(arrow, board) for arrow in pool]
    return rng.choices(pool, weights=weights, k=1)[0]


def _weight(arrow: Arrow, board: Board) -> int:
    fresh = _new_blocks(arrow, board)
    bends = bend_count(arrow.cells)
    existing_bends = sum(1 for other in board.arrows if bend_count(other.cells) > 0)
    diversity = 0
    if bends > 0 and existing_bends < 2:
        diversity += 2
    if bends == 0 and existing_bends >= 2:
        diversity += 1
    if bends >= 2:
        diversity += 1
    return 1 + fresh * 5 + _block_count(arrow, board) + diversity


def _blocking_candidate(rng: random.Random, board: Board) -> Arrow | None:
    targets = list(board.arrows)
    rng.shuffle(targets)
    for target in targets[:5]:
        free = [
            cell
            for cell in exit_cells(target, board.size)
            if cell not in board.occupied
        ]
        if not free:
            continue
        rng.shuffle(free)
        for pivot in free[:3]:
            directions = list(DIRECTIONS)
            rng.shuffle(directions)
            for direction in directions:
                arrow = _arrow_from_head(rng, board, pivot, direction)
                if arrow is not None and _block_count(arrow, board) > 0:
                    return arrow
    return None


def _random_candidate(rng: random.Random, board: Board) -> Arrow | None:
    for _ in range(10):
        direction = rng.choice(DIRECTIONS)
        head = _random_head(rng, board.size, direction, board.occupied)
        if head is None:
            continue
        arrow = _arrow_from_head(rng, board, head, direction)
        if arrow is not None:
            return arrow
    return None


def _arrow_from_head(
    rng: random.Random,
    board: Board,
    head: tuple[int, int],
    direction: str,
) -> Arrow | None:
    if not _step_back_inside(head, direction, board.size):
        return None
    length, want_bend, turn_p = _archetype(rng)
    forbidden = set(ray_cells(head[0], head[1], direction, board.size))
    cells = _grow_backward(
        rng,
        board.size,
        board.occupied,
        forbidden,
        head,
        direction,
        length,
        want_bend,
        turn_p,
    )
    if cells is None:
        return None
    arrow = Arrow(-1, cells)
    if not _placeable(arrow, board):
        return None
    return arrow


def _archetype(rng: random.Random) -> tuple[int, bool, float]:
    kind = rng.choices(
        ("short_straight", "long_straight", "short_bend", "long_bend"),
        weights=(3, 2, 3, 4),
        k=1,
    )[0]
    if kind == "short_straight":
        return rng.randint(2, 3), False, 0.0
    if kind == "long_straight":
        return rng.randint(4, MAX_LENGTH), False, 0.0
    if kind == "short_bend":
        return rng.randint(3, 4), True, 0.55
    return rng.randint(5, MAX_LENGTH), True, TURN_PROBABILITY


def _random_head(
    rng: random.Random,
    size: int,
    direction: str,
    occupied: dict[tuple[int, int], int],
) -> tuple[int, int] | None:
    d_row, d_col = DIRECTION_DELTA[OPPOSITE[direction]]
    options = []
    for row in range(size):
        for col in range(size):
            behind = (row + d_row, col + d_col)
            if not _inside(behind, size):
                continue
            if (row, col) in occupied or behind in occupied:
                continue
            options.append((row, col))
    if not options:
        return None
    return rng.choice(options)


def _grow_backward(
    rng: random.Random,
    size: int,
    occupied: dict[tuple[int, int], int],
    forbidden: set[tuple[int, int]],
    head: tuple[int, int],
    direction: str,
    length: int,
    want_bend: bool,
    turn_p: float,
) -> tuple[tuple[int, int], ...] | None:
    """Buduje ciało wstecz od grotu i zwraca komórki od ogona do grotu."""
    path = [head]
    nodes = 0

    def options() -> list[str]:
        if len(path) == 1:
            return [OPPOSITE[direction]]
        arrived = _step_name(path[-2], path[-1])
        turns = [
            name
            for name in DIRECTIONS
            if name != arrived and name != OPPOSITE[arrived]
        ]
        if not want_bend:
            return [arrived]
        rng.shuffle(turns)
        if turns and rng.random() < turn_p:
            return turns + [arrived]
        return [arrived] + turns

    def dfs() -> bool:
        nonlocal nodes
        nodes += 1
        if nodes > _GROW_NODE_CAP:
            return False
        if len(path) == length:
            return True
        for step in options():
            d_row, d_col = DIRECTION_DELTA[step]
            nxt = (path[-1][0] + d_row, path[-1][1] + d_col)
            if not _inside(nxt, size):
                continue
            if nxt in occupied or nxt in forbidden or nxt in path:
                continue
            path.append(nxt)
            if dfs():
                return True
            path.pop()
        return False

    if not dfs():
        return None
    if want_bend and bend_count(path) == 0:
        return None
    path.reverse()
    return tuple(path)


def _step_name(start: tuple[int, int], end: tuple[int, int]) -> str:
    delta = (end[0] - start[0], end[1] - start[1])
    for name, step in DIRECTION_DELTA.items():
        if step == delta:
            return name
    raise ValueError(f"Nieporawny krok {start} -> {end}")


def _step_back_inside(head: tuple[int, int], direction: str, size: int) -> bool:
    d_row, d_col = DIRECTION_DELTA[OPPOSITE[direction]]
    return _inside((head[0] + d_row, head[1] + d_col), size)


def _inside(cell: tuple[int, int], size: int) -> bool:
    row, col = cell
    return 0 <= row < size and 0 <= col < size


def _placeable(arrow: Arrow, board: Board) -> bool:
    seen: set[tuple[int, int]] = set()
    for cell in arrow.cells:
        if not _inside(cell, board.size):
            return False
        if cell in seen or cell in board.occupied:
            return False
        seen.add(cell)
    if seen & set(exit_cells(arrow, board.size)):
        return False
    return can_move(arrow, board)


def _block_count(arrow: Arrow, board: Board) -> int:
    covered = set(arrow.cells)
    blocked = 0
    for other in board.arrows:
        for cell in exit_cells(other, board.size):
            if cell in covered:
                blocked += 1
                break
    return blocked


def _new_blocks(arrow: Arrow, board: Board) -> int:
    """Ile obecnie wolnych strzałek zostanie zablokowanych."""
    covered = set(arrow.cells)
    blocked = 0
    for other in board.arrows:
        if not can_move(other, board):
            continue
        for cell in exit_cells(other, board.size):
            if cell in covered:
                blocked += 1
                break
    return blocked


def _verified(board: Board) -> bool:
    if len(board.arrows) < 2:
        return False
    order, error = solve_board(board)
    if error is not None or len(order) != len(board.arrows):
        return False
    return _reverse_works(board)


def _reverse_works(board: Board) -> bool:
    work = board.copy()
    for arrow_id in reversed([arrow.id for arrow in board.arrows]):
        arrow = work.arrow_by_id(arrow_id)
        if arrow is None or not can_move(arrow, work):
            return False
        work.remove(arrow_id)
    return not work.arrows


def _blocked_and_free(board: Board) -> tuple[int, int]:
    free = sum(1 for arrow in board.arrows if can_move(arrow, board))
    total = len(board.arrows)
    return total - free, free


def _has_opening(board: Board) -> bool:
    blocked, free = _blocked_and_free(board)
    return free >= 1 and blocked >= 1


def _shape_mix(board: Board) -> tuple[int, int]:
    curved = sum(1 for arrow in board.arrows if bend_count(arrow.cells) > 0)
    straight = len(board.arrows) - curved
    return curved, straight


def _acceptable(board: Board) -> bool:
    total = len(board.arrows)
    if not (MIN_ARROWS <= total <= MAX_ARROWS):
        return False
    blocked, free = _blocked_and_free(board)
    if blocked < 1 or free < 1 or free > blocked:
        return False
    curved, straight = _shape_mix(board)
    return curved >= 2 and straight >= 2


def _rank(board: Board) -> tuple:
    total = len(board.arrows)
    blocked, free = _blocked_and_free(board)
    curved, straight = _shape_mix(board)
    multi = sum(1 for arrow in board.arrows if bend_count(arrow.cells) >= 2)
    majority_blocked = 1 if free <= blocked else 0
    return (
        1 if _acceptable(board) else 0,
        majority_blocked,
        1 if curved >= 1 and straight >= 1 else 0,
        blocked,
        _chain_depth(_blocker_map(board)),
        curved,
        multi,
        total,
    )


def _blocker_map(board: Board) -> dict[int, list[int]]:
    blockers = {arrow.id: [] for arrow in board.arrows}
    for arrow in board.arrows:
        seen: set[int] = set()
        for cell in exit_cells(arrow, board.size):
            owner = board.occupied.get(cell)
            if owner is None or owner == arrow.id or owner in seen:
                continue
            seen.add(owner)
            blockers[arrow.id].append(owner)
    return blockers


def _chain_depth(blockers: dict[int, list[int]]) -> int:
    memo: dict[int, int] = {}
    visiting: set[int] = set()

    def depth(arrow_id: int) -> int:
        if arrow_id in memo:
            return memo[arrow_id]
        if arrow_id in visiting:
            return 1
        visiting.add(arrow_id)
        best = 1
        for blocker in blockers.get(arrow_id, ()):
            best = max(best, 1 + depth(blocker))
        visiting.remove(arrow_id)
        memo[arrow_id] = best
        return best

    if not blockers:
        return 0
    return max(depth(arrow_id) for arrow_id in blockers)


def _stages(board: Board) -> int:
    work = board.copy()
    stages = 0
    while work.arrows:
        movable = [arrow for arrow in work.arrows if can_move(arrow, work)]
        if not movable:
            break
        stages += 1
        for arrow in movable:
            work.remove(arrow.id)
    return stages


def _emergency_board(size: int = 12) -> Board:
    """Stała plansza z prostymi łańcuchami i dwoma zakrętami."""
    board = Board(size)
    next_id = 1

    def place(cells: tuple[tuple[int, int], ...]) -> None:
        nonlocal next_id
        board.add(Arrow(next_id, cells))
        next_id += 1

    for row in (0, 2, 4):
        place(tuple((row, col) for col in range(0, 2)))
        place(tuple((row, col) for col in range(4, 7)))
        place(tuple((row, col) for col in range(8, 11)))
    place(((8, 0), (8, 1)))
    place(((9, 4), (9, 5), (8, 5), (8, 6)))
    place(((10, 0), (10, 1), (10, 2)))
    place(((11, 5), (10, 5), (10, 6), (10, 7)))
    return board
