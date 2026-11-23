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
from difficulty import (
    analyze_difficulty,
    outside_targets,
    profile_fit,
    profile_for,
    selection_rank,
)
from fill import fill_board
from quality_logic import analyze_logic, extendable_tip
from quality_visual import analyze_visual

# Diagnostyka: False zostawia sam rdzeń, True pokazuje rdzeń i dopełnienie.
INCLUDE_FILL = True

MIN_ARROWS = 12
MAX_ARROWS = 16
MIN_LENGTH = 2
MAX_LENGTH = 8
TURN_PROBABILITY = 0.30

_MAX_TRIALS = 14
_MAX_STAGNANT = 28
_CANDIDATES = 7
_GROW_NODE_CAP = 500


def generate_board(seed: int, size: int = 12, difficulty: int = 3) -> Board:
    """Zwraca planszę pokazywaną w grze."""
    return build_puzzle(seed, size, difficulty=difficulty).final


def generate_core(seed: int, size: int = 12, difficulty: int = 3) -> Board:
    """Buduje kilka rdzeni i zostawia ten, którego pełna plansza pasuje do poziomu."""
    return build_puzzle(seed, size, report=False, difficulty=difficulty).core


def generate_core_report(
    seed: int,
    size: int = 12,
    trials: int | None = None,
    difficulty: int = 3,
) -> CoreReport:
    """Wybiera rdzeń tylko spośród kandydatów spełniających twarde warunki."""
    profile = profile_for(difficulty)
    pool, rejected, trial_count, emergency, hard_miss = _collect(seed, size, difficulty, trials)
    if emergency is not None:
        return CoreReport(emergency, True, trial_count, rejected, difficulty=profile.level)
    best = max(pool, key=lambda board: _rank(board, profile))
    fit, deviation, profile_miss = _fit_of(best, profile, hard_miss)
    return CoreReport(
        best,
        False,
        trial_count,
        rejected,
        fit=fit,
        deviation=deviation,
        profile_miss=profile_miss,
        difficulty=profile.level,
    )


def build_puzzle(seed: int, size: int = 12, *, report: bool = True, difficulty: int = 3):
    """Liczy rdzeń, dopełnienie zgodne z poziomem i wybiera planszę FINAL."""
    profile = profile_for(difficulty)
    started = time.perf_counter()
    pool, rejected, trial_count, emergency, hard_miss = _collect(seed, size, difficulty, None)
    fallback = emergency is not None
    if fallback:
        shortlist = [emergency]
        hard_miss = False
    else:
        shortlist = sorted(pool, key=lambda board: _rank(board, profile), reverse=True)
        shortlist = shortlist[: max(1, profile.finalists)]
    best: tuple | None = None
    for index, core in enumerate(shortlist):
        final, fill_stats = _apply_fill(core, seed, difficulty, index)
        if not _verified(final):
            continue
        key = _rank(final, profile)
        if best is None or key > best[0]:
            best = (key, core, final, fill_stats)
    if best is None:
        raise RuntimeError(f"Nie udało się zbudować planszy dla seed={seed}")
    _key, core, final, fill_stats = best
    core_stats = metrics(core)
    final_stats = metrics(final)
    core_stats["fallback"] = fallback
    core_stats["rejected"] = rejected
    core_stats["trials"] = trial_count
    _attach_difficulty(core_stats, core, profile, hard_miss)
    _attach_difficulty(final_stats, final, profile, hard_miss)
    final_stats["fallback"] = fallback
    final_stats["time"] = time.perf_counter() - started
    if report:
        _report(seed, core_stats, fill_stats, final_stats)
    return Puzzle(core, final, core_stats, fill_stats, final_stats)


def _collect(
    seed: int,
    size: int,
    difficulty: int,
    trials: int | None,
) -> tuple[list[Board], int, int, Board | None, bool]:
    profile = profile_for(difficulty)
    trial_count = profile.trials if trials is None else trials
    rng = random.Random(f"core-{difficulty}-{seed}")
    pool: list[Board] = []
    misses: list[Board] = []
    rejected = 0
    for _ in range(trial_count):
        low, high = profile.core_arrows
        target = rng.randint(low, high)
        board = _build_once(rng, size, target, profile)
        if not _verified(board):
            rejected += 1
            continue
        if not _acceptable(board, profile):
            misses.append(board)
            rejected += 1
            continue
        pool.append(board)
    if pool:
        return pool, rejected, trial_count, None, False
    if misses and not profile.strict_emergency:
        closest = max(misses, key=lambda board: _rank(board, profile))
        return [closest], rejected, trial_count, None, True
    if profile.strict_emergency:
        emergency = _emergency_board(size)
        if not _verified(emergency) or not _acceptable(emergency, profile):
            raise RuntimeError(f"Nie udało się zbudować planszy dla seed={seed}")
        return [], rejected, trial_count, emergency, False
    raise RuntimeError(f"Nie udało się zbudować planszy dla seed={seed}")


def _apply_fill(core: Board, seed: int, difficulty: int, salt: int) -> tuple[Board, dict]:
    if not INCLUDE_FILL:
        area = core.size * core.size
        filled = len(core.occupied)
        return core.copy(), {
            "added": 0,
            "extra_cells": 0,
            "cover": filled,
            "area": area,
            "empty": area - filled,
            "rejected": 0,
            "time_capped": False,
        }
    return fill_board(core, seed, difficulty=difficulty, variant_salt=salt)


def _fit_of(board: Board, profile, hard_miss: bool) -> tuple[float, float, bool]:
    report = analyze_difficulty(board)
    fit = profile_fit(report, profile)
    deviation = 1.0 - fit
    return fit, deviation, hard_miss or fit < 0.70


def _attach_difficulty(stats: dict, board: Board, profile, hard_miss: bool) -> None:
    report = analyze_difficulty(board)
    fit = profile_fit(report, profile)
    stats["difficulty"] = profile.level
    stats["label"] = profile.label
    stats["fit"] = fit
    stats["deviation"] = 1.0 - fit
    stats["profile_miss"] = hard_miss or fit < 0.58
    stats["outside"] = outside_targets(report, profile)
    stats["free_ratio"] = report["free_ratio"]
    stats["logic_difficulty"] = report["logic_difficulty"]
    stats["spatial"] = report["spatial"]
    stats["visual_search"] = report["visual_search"]
    stats["blocks_per_arrow"] = report["blocks_per_arrow"]
    stats["first_share"] = report["first_share"]
    stats["mean_choices"] = report["mean_choices"]
    stats["join_ratio"] = report["join_ratio"]
    stats["largest_empty"] = report["largest_empty"]
    stats["mean_bends"] = report["mean_bends"]
    stats["mean_length"] = report["mean_length"]


class CoreReport:
    def __init__(
        self,
        board: Board,
        fallback: bool,
        trials: int,
        rejected: int,
        fit: float = 0.0,
        deviation: float = 1.0,
        profile_miss: bool = False,
        difficulty: int = 3,
    ) -> None:
        self.board = board
        self.fallback = fallback
        self.trials = trials
        self.rejected = rejected
        self.fit = fit
        self.deviation = deviation
        self.profile_miss = profile_miss
        self.difficulty = difficulty


class Puzzle:
    def __init__(self, core: Board, final: Board, core_stats: dict, fill_stats: dict, final_stats: dict) -> None:
        self.core = core
        self.final = final
        self.core_stats = core_stats
        self.fill_stats = fill_stats
        self.final_stats = final_stats


def metrics(board: Board) -> dict:
    logic = analyze_logic(board)
    visual = analyze_visual(board)
    area = board.size * board.size
    filled = len(board.occupied)
    return {
        "arrows": logic["arrows"],
        "area": area,
        "filled": filled,
        "empty": area - filled,
        "blocks": logic["blocks"],
        "depth": logic["depth"],
        "free": logic["free"],
        "blocked": logic["arrows"] - logic["free"],
        "stages": logic["stages"],
        "curve": logic["curve"],
        "curved": visual["curved"],
        "straight": visual["straight"],
        "solved": logic["solved"],
        "logic": logic["score"],
        "visual": visual["score"],
        "logic_parts": logic["parts"],
        "visual_parts": visual["parts"],
        "isolated": logic["isolated"],
        "joins": logic["joins"],
        "splits": logic["splits"],
    }


def _report(seed: int, core_stats: dict, fill_stats: dict, final_stats: dict) -> None:
    print(
        f"[core] seed={seed} arrows={core_stats['arrows']} "
        f"cover={core_stats['filled']}/{core_stats['area']} "
        f"blocks={core_stats['blocks']} depth={core_stats['depth']} "
        f"free={core_stats['free']} logic={core_stats['logic']:.3f} "
        f"visual={core_stats['visual']:.3f} "
        f"fallback={'yes' if core_stats['fallback'] else 'no'} "
        f"rejected={core_stats['rejected']} "
        f"difficulty={core_stats['difficulty']} fit={core_stats['fit']:.2f}",
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
        f"stages={final_stats['stages']} free={final_stats['free']} "
        f"logic={final_stats['logic']:.3f} visual={final_stats['visual']:.3f} "
        f"fit={final_stats['fit']:.2f} deviation={final_stats['deviation']:.2f} "
        f"spatial={final_stats['spatial']:.2f} "
        f"logic_difficulty={final_stats['logic_difficulty']:.2f} "
        f"miss={'yes' if final_stats['profile_miss'] else 'no'}",
        flush=True,
    )


def _build_once(rng: random.Random, size: int, target: int, profile) -> Board:
    board = Board(size)
    next_id = 1
    stagnant = 0
    while len(board.arrows) < target and stagnant < profile.stagnant:
        chosen = _pick_candidate(rng, board, profile)
        if chosen is None:
            stagnant += 1
            continue
        placed = Arrow(next_id, chosen.cells)
        if not _placeable(placed, board):
            stagnant += 1
            continue
        if _new_blocks(placed, board) == 0 and _blocked_and_free(board)[1] >= profile.max_open:
            stagnant += 1
            continue
        board.add(placed)
        next_id += 1
        stagnant = 0
    return board


def _pick_candidate(rng: random.Random, board: Board, profile) -> Arrow | None:
    pool: list[Arrow] = []
    seen: set[tuple[tuple[int, int], ...]] = set()
    tip_id = extendable_tip(board) if board.arrows and profile.tip_weight >= 6 else None
    commit_tip = tip_id is not None and rng.random() < min(1.0, profile.tip_weight / 16)
    for _ in range(_CANDIDATES):
        if board.arrows and rng.random() < profile.blocking_bias:
            arrow = _blocking_candidate(rng, board, profile, tip_id)
        else:
            arrow = None
        if arrow is None:
            arrow = _random_candidate(rng, board, profile)
        if arrow is None or arrow.cells in seen:
            continue
        if commit_tip and _covers_target(arrow, board, tip_id):
            return arrow
        seen.add(arrow.cells)
        pool.append(arrow)
    if not pool:
        return None

    if board.arrows and rng.random() < profile.prefer_block:
        blockers = [arrow for arrow in pool if _new_blocks(arrow, board) > 0]
        if blockers:
            pool = blockers
    weights = [_weight(arrow, board, profile, tip_id) for arrow in pool]
    return rng.choices(pool, weights=weights, k=1)[0]


def _weight(arrow: Arrow, board: Board, profile, tip_id: int | None = None) -> int:
    fresh = _new_blocks(arrow, board)
    bends = bend_count(arrow.cells)
    existing_bends = sum(1 for other in board.arrows if bend_count(other.cells) > 0)
    diversity = 0
    if bends > 0 and existing_bends < 2:
        diversity += 2
    if bends == 0 and existing_bends >= 2:
        diversity += 1
    if bends >= 2 and profile.level >= 4:
        diversity += 1
    return (
        1
        + fresh * profile.block_weight
        + _block_count(arrow, board)
        + diversity
        + _spread_bonus(arrow, board, profile.spread_bonus)
        + (profile.tip_weight if tip_id is not None and _covers_target(arrow, board, tip_id) else 0)
    )


def _spread_bonus(arrow: Arrow, board: Board, bonus: int) -> int:
    if bonus <= 0 or not board.occupied:
        return 0
    counts = _quadrant_counts(board)
    row, col = arrow.head
    quadrant = _quadrant_index(row, col, board.size)
    if counts[quadrant] <= min(counts):
        return bonus
    return 0


def _quadrant_counts(board: Board) -> list[int]:
    counts = [0, 0, 0, 0]
    for row, col in board.occupied:
        counts[_quadrant_index(row, col, board.size)] += 1
    return counts


def _quadrant_index(row: int, col: int, size: int) -> int:
    mid = size / 2
    return (0 if row < mid else 2) + (0 if col < mid else 1)


def _quadrant_load(
    cell: tuple[int, int],
    direction: str,
    size: int,
    loads: list[int],
) -> int:
    d_row, d_col = DIRECTION_DELTA[direction]
    nxt = (cell[0] + d_row, cell[1] + d_col)
    if not _inside(nxt, size):
        return 99
    return loads[_quadrant_index(nxt[0], nxt[1], size)]


def _covers_target(arrow: Arrow, board: Board, target_id: int) -> bool:
    target = board.arrow_by_id(target_id)
    if target is None:
        return False
    covered = set(arrow.cells)
    return any(cell in covered for cell in exit_cells(target, board.size))


def _block_target(
    rng: random.Random,
    board: Board,
    target: Arrow,
    profile,
    prefer_room: bool,
) -> Arrow | None:
    free = [cell for cell in exit_cells(target, board.size) if cell not in board.occupied]
    if not free:
        return None
    if not prefer_room:
        rng.shuffle(free)
        pivots = free[:4]
    else:
        pivots = free
    for pivot in pivots:
        directions = list(DIRECTIONS)
        rng.shuffle(directions)
        if prefer_room:
            directions.sort(key=lambda name: _direction_rank(pivot, name, board))
        attempts = ((4, False, 0.0), (3, False, 0.0), (2, False, 0.0)) if prefer_room else (None,)
        for direction in directions:
            for forced in attempts:
                arrow = _arrow_from_head(rng, board, pivot, direction, profile, forced)
                if arrow is not None and _block_count(arrow, board) > 0:
                    return arrow
    return None


def _direction_rank(cell: tuple[int, int], direction: str, board: Board) -> tuple[int, int, int, int]:
    behind = 0 if _step_back_open(cell, direction, board) else 1
    room = len(ray_cells(cell[0], cell[1], direction, board.size))
    d_row, d_col = DIRECTION_DELTA[direction]
    nxt = (cell[0] + d_row, cell[1] + d_col)
    if not _inside(nxt, board.size):
        load = 99
    else:
        counts = _quadrant_counts(board)
        load = counts[_quadrant_index(nxt[0], nxt[1], board.size)]
    return (behind, 0 if room >= 2 else 1, load, -room)


def _step_back_open(cell: tuple[int, int], direction: str, board: Board) -> bool:
    d_row, d_col = DIRECTION_DELTA[OPPOSITE[direction]]
    behind = (cell[0] + d_row, cell[1] + d_col)
    return _inside(behind, board.size) and behind not in board.occupied


def _blocking_candidate(
    rng: random.Random,
    board: Board,
    profile,
    tip_id: int | None = None,
) -> Arrow | None:
    if tip_id is not None:
        tip = board.arrow_by_id(tip_id)
        if tip is not None:
            forced = _block_target(rng, board, tip, profile, True)
            if forced is not None:
                return forced
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
                arrow = _arrow_from_head(rng, board, pivot, direction, profile)
                if arrow is not None and _block_count(arrow, board) > 0:
                    return arrow
    return None


def _random_candidate(rng: random.Random, board: Board, profile) -> Arrow | None:
    for _ in range(10):
        direction = rng.choice(DIRECTIONS)
        head = _random_head(rng, board, direction, profile)
        if head is None:
            continue
        arrow = _arrow_from_head(rng, board, head, direction, profile)
        if arrow is not None:
            return arrow
    return None


def _arrow_from_head(
    rng: random.Random,
    board: Board,
    head: tuple[int, int],
    direction: str,
    profile,
    forced: tuple[int, bool, float] | None = None,
) -> Arrow | None:
    if not _step_back_inside(head, direction, board.size):
        return None
    if forced is None:
        length, want_bend, turn_p = _archetype(rng, profile)
    else:
        length, want_bend, turn_p = forced
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
        profile.tip_weight >= 8,
    )
    if cells is None:
        return None
    arrow = Arrow(-1, cells)
    if not _placeable(arrow, board):
        return None
    return arrow


def _archetype(rng: random.Random, profile) -> tuple[int, bool, float]:
    kind = rng.choices(
        ("short_straight", "long_straight", "short_bend", "long_bend"),
        weights=profile.archetype_weights,
        k=1,
    )[0]
    long_cap = max(4, min(MAX_LENGTH, profile.long_length))
    if kind == "short_straight":
        return rng.randint(2, 3), False, 0.0
    if kind == "long_straight":
        return rng.randint(4, long_cap), False, 0.0
    if kind == "short_bend":
        return rng.randint(3, 4), True, min(0.55, profile.turn_probability + 0.15)
    return rng.randint(min(5, long_cap), long_cap), True, profile.turn_probability


def _random_head(rng: random.Random, board: Board, direction: str, profile) -> tuple[int, int] | None:
    d_row, d_col = DIRECTION_DELTA[OPPOSITE[direction]]
    options = []
    for row in range(board.size):
        for col in range(board.size):
            behind = (row + d_row, col + d_col)
            if not _inside(behind, board.size):
                continue
            if (row, col) in board.occupied or behind in board.occupied:
                continue
            options.append((row, col))
    if not options:
        return None
    counts = _quadrant_counts(board)
    lightest = min(counts) if board.occupied else 0
    weights = []
    for row, col in options:
        bonus = profile.spread_bonus if counts[_quadrant_index(row, col, board.size)] <= lightest else 0
        weights.append(1 + bonus)
    return rng.choices(options, weights=weights, k=1)[0]


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
    spread: bool = False,
) -> tuple[tuple[int, int], ...] | None:
    """Buduje ciało wstecz od grotu i zwraca komórki od ogona do grotu."""
    path = [head]
    nodes = 0
    loads = [0, 0, 0, 0]
    if spread:
        for row, col in occupied:
            loads[_quadrant_index(row, col, size)] += 1

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
        if spread and turns:
            here = path[-1]
            turns.sort(key=lambda name: _quadrant_load(here, name, size, loads))
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


def _shape_mix(board: Board) -> tuple[int, int]:
    curved = sum(1 for arrow in board.arrows if bend_count(arrow.cells) > 0)
    straight = len(board.arrows) - curved
    return curved, straight


def _acceptable(board: Board, profile) -> bool:
    total = len(board.arrows)
    low, high = profile.hard_arrows
    if not (low <= total <= high):
        return False
    blocked, free = _blocked_and_free(board)
    if free < profile.hard_min_free or blocked < profile.hard_min_blocked:
        return False
    if profile.hard_free_le_blocked and free > blocked:
        return False
    curved, straight = _shape_mix(board)
    return curved >= profile.hard_min_curved and straight >= profile.hard_min_straight


def _rank(board: Board, profile) -> tuple:
    """Zgodność z poziomem, potem rozłożenie na planszy."""
    return selection_rank(board, profile)


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
