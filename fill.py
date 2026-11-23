"""Dopełnianie wolnych komórek bez ruszania strzałek rdzenia.

Każda nowa strzałka wchodzi tylko wtedy, gdy jej wyjazd jest wolny względem
planszy już ułożonej. Dzięki temu odwrotna kolejność strzałek FILL, a potem
rozwiązanie rdzenia, czyści całą planszę. Wybór wariantu idzie za jakością
logiczną i kompozycją. Pokrycie nie decyduje, a dopełnienie psujące otwarcie
jest odrzucane.
"""

from __future__ import annotations

import random

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
from difficulty import profile_for, selection_rank

_MAX_FILL = 8
_NODE_LIMIT = 8
_GROW_CAP = 48
_NEIGHBORS = ((-1, 0), (0, 1), (1, 0), (0, -1))


def fill_board(
    core: Board,
    seed: int,
    *,
    node_limit: int = _NODE_LIMIT,
    difficulty: int = 3,
    variant_salt: int = 0,
) -> tuple[Board, dict]:
    """Buduje kilka dopełnień i zostawia to, które trzyma poziom trudności."""
    profile = profile_for(difficulty)
    budget = max(0, min(profile.fill_budget, _MAX_FILL, node_limit))
    rng = random.Random(f"fill-{difficulty}-{seed}-{variant_salt}")
    core_free = sum(1 for arrow in core.arrows if can_move(arrow, core))
    variants = [core.copy()]
    rejected = 0
    for _ in range(profile.fill_variants):
        local = random.Random(rng.randrange(1 << 30))
        board = core.copy()
        placed = 0
        while placed < budget:
            candidates = _candidates(local, board, profile)
            if not candidates:
                break
            chosen = _chain_candidate(board, candidates, core_free, profile.free_slack)
            if chosen is None:
                rejected += len(candidates)
                break
            board.add(chosen)
            placed += 1
            rejected += max(0, len(candidates) - 1)
        variants.append(board)
    best, dropped = select_variant(core, variants, difficulty)
    rejected += dropped
    extra = len(best.occupied) - len(core.occupied)
    area = core.size * core.size
    return best, {
        "added": len(best.arrows) - len(core.arrows),
        "extra_cells": extra,
        "cover": len(best.occupied),
        "area": area,
        "empty": area - len(best.occupied),
        "rejected": rejected,
        "time_capped": False,
    }


def select_variant(core: Board, variants: list[Board], difficulty: int = 3) -> tuple[Board, int]:
    """Wybiera wariant zgodny z poziomem. Pokrycie nie jest pierwszym kryterium."""
    profile = profile_for(difficulty)
    core_free = sum(1 for arrow in core.arrows if can_move(arrow, core))
    accepted: list[Board] = []
    dropped = 0
    for board in variants:
        if _accept(core, board, core_free):
            accepted.append(board)
        else:
            dropped += 1
    if not accepted:
        return core.copy(), dropped
    return max(accepted, key=lambda board: _fill_key(board, profile, core)), dropped


def _fill_key(board: Board, profile, core: Board) -> tuple:
    rank = selection_rank(board, profile)
    if _open_rows(core) < 3:
        return rank
    extra = len(board.occupied) - len(core.occupied)
    band = round(rank[3] * 20)
    return (band, extra, *rank[1:])


def _open_rows(board: Board) -> int:
    count = 0
    for row in range(board.size):
        if all((row, col) not in board.occupied for col in range(board.size)):
            count += 1
    return count


def _chain_candidate(
    board: Board,
    candidates: list[Arrow],
    core_free: int,
    free_slack: int = 1,
) -> Arrow | None:
    """Dokłada strzałkę, która przedłuża blokadę, zamiast otwierać nowy luźny ruch."""
    current_free = sum(1 for arrow in board.arrows if can_move(arrow, board))
    for arrow in candidates:
        if _blocks_now(arrow, board) == 0 and current_free >= core_free + free_slack:
            continue
        return arrow
    return None


def _blocks_now(arrow: Arrow, board: Board) -> int:
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


def _accept(core: Board, board: Board, core_free: int) -> bool:
    if not _same_core(core, board):
        return False
    order, error = solve_board(board)
    if error is not None or len(order) != len(board.arrows):
        return False
    free = sum(1 for arrow in board.arrows if can_move(arrow, board))
    if free < 1:
        return False
    fill = board.arrows[len(core.arrows) :]
    if not fill:
        return True
    if free > core_free + 2:
        return False
    if len(fill) >= 6:
        short = sum(1 for arrow in fill if len(arrow.cells) == 2)
        if short * 10 > len(fill) * 7:
            return False
    return True


def _same_core(core: Board, board: Board) -> bool:
    if len(board.arrows) < len(core.arrows):
        return False
    for original, current in zip(core.arrows, board.arrows):
        if original.id != current.id or original.cells != current.cells:
            return False
    return True


def _candidates(rng: random.Random, board: Board, profile=None) -> list[Arrow]:
    found: list[Arrow] = []
    seen: set[tuple[tuple[int, int], ...]] = set()
    next_id = 1 + max((arrow.id for arrow in board.arrows), default=0)

    def take(cells: tuple[tuple[int, int], ...] | None) -> None:
        nonlocal next_id
        if cells is None or cells in seen:
            return
        arrow = Arrow(next_id, cells)
        if not _placeable(arrow, board):
            return
        seen.add(cells)
        found.append(arrow)
        next_id += 1

    free_arrows = [arrow for arrow in board.arrows if can_move(arrow, board)]
    rng.shuffle(free_arrows)
    for target in free_arrows[:4]:
        pivots = [cell for cell in exit_cells(target, board.size) if cell not in board.occupied]
        rng.shuffle(pivots)
        for pivot in pivots[:2]:
            directions = list(DIRECTIONS)
            rng.shuffle(directions)
            for direction in directions[:2]:
                take(_grow(rng, board, pivot, direction))
                if len(found) >= 8:
                    return _ranked(found, board, profile)

    heads = _chainable_heads(board)
    rng.shuffle(heads)
    for head, direction in heads[:6]:
        take(_grow(rng, board, head, direction))
        if len(found) >= 8:
            break
    return _ranked(found, board, profile)


def _ranked(arrows: list[Arrow], board: Board, profile=None) -> list[Arrow]:
    base_holes = _singletons(board, ())
    scored = [(_score(arrow, board, base_holes, profile), arrow.cells, arrow) for arrow in arrows]
    scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return [arrow for _score_value, _cells, arrow in scored]


def _score(arrow: Arrow, board: Board, base_holes: int, profile=None) -> int:
    covered = set(arrow.cells)
    fresh = 0
    for other in board.arrows:
        if not can_move(other, board):
            continue
        for cell in exit_cells(other, board.size):
            if cell in covered:
                fresh += 1
                break
    holes = _singletons(board, arrow.cells) - base_holes
    room = 0
    for cell in exit_cells(arrow, board.size):
        if cell not in board.occupied and cell not in covered:
            room += 1
            if room >= 3:
                break
    bends = bend_count(arrow.cells)
    length = len(arrow.cells)
    length_fit = 2 if 4 <= length <= 6 else (1 if length >= 3 else 0)
    bend_fit = 1 if bends == 1 else 0
    twist_penalty = 3 if bends >= 3 else 0
    score = fresh * 8 + length_fit * 2 + bend_fit - twist_penalty - max(0, holes) * 4
    if profile is not None and profile.tip_weight >= 6 and board.occupied:
        counts = [0, 0, 0, 0]
        mid = board.size / 2
        for row, col in board.occupied:
            counts[(0 if row < mid else 2) + (0 if col < mid else 1)] += 1
        head_row, head_col = arrow.head
        quadrant = (0 if head_row < mid else 2) + (0 if head_col < mid else 1)
        if counts[quadrant] <= min(counts):
            score += 2
    if length == 2 and fresh == 0:
        score -= 4
    if room == 0 and fresh == 0:
        score -= 6
    return score


def _chainable_heads(board: Board) -> list[tuple[tuple[int, int], str]]:
    heads: list[tuple[tuple[int, int], str]] = []
    for component in _components(board)[:2]:
        if len(component) < 4:
            continue
        area = set(component)
        for cell in component:
            row, col = cell
            for direction, (d_row, d_col) in DIRECTION_DELTA.items():
                hit = 0
                next_row = row + d_row
                next_col = col + d_col
                while (next_row, next_col) in area and hit < 3:
                    hit += 1
                    next_row += d_row
                    next_col += d_col
                if hit >= 2 and _step_inside((row, col), OPPOSITE[direction], board, area):
                    heads.append(((row, col), direction))
    return heads


def _step_inside(
    head: tuple[int, int],
    direction: str,
    board: Board,
    area: set[tuple[int, int]],
) -> bool:
    d_row, d_col = DIRECTION_DELTA[direction]
    behind = (head[0] + d_row, head[1] + d_col)
    return behind in area and behind not in board.occupied


def _grow(
    rng: random.Random,
    board: Board,
    head: tuple[int, int],
    direction: str,
) -> tuple[tuple[int, int], ...] | None:
    if head in board.occupied or not _inside(head, board.size):
        return None
    if not _step_inside(head, OPPOSITE[direction], board, _all_cells(board.size)):
        return None
    local = random.Random(rng.randrange(1 << 30))
    want_bend = local.random() < 0.42
    lengths = [8, 7, 6, 5, 4, 3, 2]
    local.shuffle(lengths)
    forbidden = set(ray_cells(head[0], head[1], direction, board.size))
    for length in lengths:
        cells = _grow_exact(local, board, head, direction, length, want_bend, forbidden)
        if cells is None and want_bend:
            cells = _grow_exact(local, board, head, direction, length, False, forbidden)
        if cells is not None:
            return cells
    return None


def _grow_exact(
    rng: random.Random,
    board: Board,
    head: tuple[int, int],
    direction: str,
    length: int,
    want_bend: bool,
    forbidden: set[tuple[int, int]],
) -> tuple[tuple[int, int], ...] | None:
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
        if turns and rng.random() < 0.5:
            return turns + [arrived]
        return [arrived] + turns

    def dfs() -> bool:
        nonlocal nodes
        nodes += 1
        if nodes > _GROW_CAP:
            return False
        if len(path) == length:
            return True
        for step in options():
            d_row, d_col = DIRECTION_DELTA[step]
            nxt = (path[-1][0] + d_row, path[-1][1] + d_col)
            if not _inside(nxt, board.size):
                continue
            if nxt in board.occupied or nxt in forbidden or nxt in path:
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


def _placeable(arrow: Arrow, board: Board) -> bool:
    seen: set[tuple[int, int]] = set()
    for cell in arrow.cells:
        if not _inside(cell, board.size) or cell in seen or cell in board.occupied:
            return False
        seen.add(cell)
    if len(arrow.cells) < 2 or len(arrow.cells) > 8:
        return False
    if seen & set(exit_cells(arrow, board.size)):
        return False
    return can_move(arrow, board)


def _components(board: Board) -> list[list[tuple[int, int]]]:
    seen: set[tuple[int, int]] = set()
    components: list[list[tuple[int, int]]] = []
    for row in range(board.size):
        for col in range(board.size):
            start = (row, col)
            if start in board.occupied or start in seen:
                continue
            stack = [start]
            seen.add(start)
            component: list[tuple[int, int]] = []
            while stack:
                cell = stack.pop()
                component.append(cell)
                for d_row, d_col in _NEIGHBORS:
                    nxt = (cell[0] + d_row, cell[1] + d_col)
                    if not _inside(nxt, board.size) or nxt in board.occupied or nxt in seen:
                        continue
                    seen.add(nxt)
                    stack.append(nxt)
            components.append(component)
    components.sort(key=len, reverse=True)
    return components


def _singletons(board: Board, extra: tuple[tuple[int, int], ...] | set[tuple[int, int]]) -> int:
    blocked = set(extra)
    seen: set[tuple[int, int]] = set()
    singles = 0
    for row in range(board.size):
        for col in range(board.size):
            start = (row, col)
            if start in seen or start in board.occupied or start in blocked:
                continue
            stack = [start]
            seen.add(start)
            count = 0
            while stack:
                count += 1
                cell = stack.pop()
                for d_row, d_col in _NEIGHBORS:
                    nxt = (cell[0] + d_row, cell[1] + d_col)
                    if (
                        not _inside(nxt, board.size)
                        or nxt in seen
                        or nxt in board.occupied
                        or nxt in blocked
                    ):
                        continue
                    seen.add(nxt)
                    stack.append(nxt)
            if count == 1:
                singles += 1
    return singles


def _all_cells(size: int) -> set[tuple[int, int]]:
    return {(row, col) for row in range(size) for col in range(size)}


def _inside(cell: tuple[int, int], size: int) -> bool:
    row, col = cell
    return 0 <= row < size and 0 <= col < size


def _step_name(start: tuple[int, int], end: tuple[int, int]) -> str:
    delta = (end[0] - start[0], end[1] - start[1])
    for name, step in DIRECTION_DELTA.items():
        if step == delta:
            return name
    raise ValueError(delta)
