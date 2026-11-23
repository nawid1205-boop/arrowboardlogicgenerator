"""Ocena logiczna planszy, niezależna od generatora.

Wynik jest ważoną sumą znormalizowanych składników. Służy do porównywania
kandydatów, ale nie zastępuje twardych warunków poprawności.
"""

from __future__ import annotations

from engine import Board, can_move, exit_cells, solve_board

# Składniki są w skali 0–1. Zmiana wag nie zmienia twardej walidacji.
LOGIC_WEIGHTS = {
    "opening": 0.22,
    "depth": 0.24,
    "structure": 0.28,
    "release": 0.18,
    "relevance": 0.08,
}


def analyze_logic(board: Board) -> dict:
    arrows = len(board.arrows)
    blockers, outgoing = _dependency_graph(board)
    free = sum(1 for arrow in board.arrows if can_move(arrow, board))
    edges = sum(len(items) for items in blockers.values())
    depth = _chain_depth(blockers)
    curve = release_curve(board)
    splits = sum(1 for targets in outgoing.values() if len(targets) >= 2)
    joins = sum(1 for sources in blockers.values() if len(sources) >= 2)
    isolated = sum(
        1
        for arrow in board.arrows
        if not blockers[arrow.id] and not outgoing[arrow.id]
    )
    order, error = solve_board(board)
    solved = error is None and len(order) == arrows
    parts = {
        "opening": _opening(free),
        "depth": _depth_score(depth),
        "structure": _structure(arrows, edges, splits, joins, isolated),
        "release": _release(curve, arrows),
        "relevance": _relevance(isolated, arrows),
    }
    return {
        "score": _weighted(parts, LOGIC_WEIGHTS),
        "parts": parts,
        "arrows": arrows,
        "free": free,
        "blocks": edges,
        "depth": depth,
        "splits": splits,
        "joins": joins,
        "isolated": isolated,
        "curve": curve,
        "stages": len(curve),
        "solved": solved,
        "blockers": blockers,
    }


def release_curve(board: Board) -> list[int]:
    """Ile strzałek schodzi w kolejnych rundach jednoczesnego usuwania."""
    work = board.copy()
    curve: list[int] = []
    guard = 0
    limit = len(board.arrows) + 1
    while work.arrows and guard < limit:
        movable = [arrow for arrow in work.arrows if can_move(arrow, work)]
        if not movable:
            break
        curve.append(len(movable))
        for arrow in movable:
            work.remove(arrow.id)
        guard += 1
    return curve


def _dependency_graph(
    board: Board,
) -> tuple[dict[int, list[int]], dict[int, list[int]]]:
    """Krawędź A <- B oznacza: B stoi na wyjeździe A i musi zniknąć wcześniej."""
    blockers = {arrow.id: [] for arrow in board.arrows}
    outgoing = {arrow.id: [] for arrow in board.arrows}
    for arrow in board.arrows:
        seen: set[int] = set()
        for cell in exit_cells(arrow, board.size):
            owner = board.occupied.get(cell)
            if owner is None or owner == arrow.id or owner in seen:
                continue
            seen.add(owner)
            blockers[arrow.id].append(owner)
            outgoing[owner].append(arrow.id)
    return blockers, outgoing


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
        for blocker_id in blockers.get(arrow_id, ()):
            best = max(best, 1 + depth(blocker_id))
        visiting.remove(arrow_id)
        memo[arrow_id] = best
        return best

    if not blockers:
        return 0
    return max(depth(arrow_id) for arrow_id in blockers)


def _opening(free: int) -> float:
    """Szczyt przy kilku ruchach na start, nie przy zerze i nie przy lawinie."""
    if free <= 0:
        return 0.0
    return _clamp(1.0 - abs(free - 3) / 5.0)


def _depth_score(depth: int) -> float:
    span = max(0, depth - 1)
    return _clamp(span / 8.0)


def _structure(arrows: int, edges: int, splits: int, joins: int, isolated: int) -> float:
    if arrows <= 0:
        return 0.0
    density = min(1.0, edges / arrows)
    split_ratio = splits / arrows
    join_ratio = joins / arrows
    isolated_ratio = isolated / arrows
    return _clamp(
        0.40 * density
        + 0.30 * split_ratio
        + 0.20 * join_ratio
        + 0.10 * (1.0 - isolated_ratio)
    )


def _release(curve: list[int], arrows: int) -> float:
    if arrows <= 0 or not curve or sum(curve) != arrows:
        return 0.0
    first = curve[0] / arrows
    opening = _clamp(1.0 - abs(first - 0.28) / 0.40)
    span = min(len(curve), 9) / 7.0
    variety = 0.0 if len(curve) == 1 else len(set(curve)) / len(curve)
    return _clamp(0.50 * opening + 0.30 * min(1.0, span) + 0.20 * variety)


def _relevance(isolated: int, arrows: int) -> float:
    if arrows <= 0:
        return 0.0
    return _clamp(1.0 - isolated / arrows)


def selection_key(logic_score: float, visual_score: float, filled: int) -> tuple:
    """Logika w pasmach 0,05, potem kompozycja, potem doprecyzowanie, pokrycie na końcu."""
    return (
        int(logic_score * 20),
        int(visual_score * 20),
        round(logic_score, 5),
        filled,
    )


def _weighted(parts: dict[str, float], weights: dict[str, float]) -> float:
    total = sum(weights.values())
    if total <= 0:
        return 0.0
    return sum(parts[name] * weight for name, weight in weights.items()) / total


def _clamp(value: float) -> float:
    if value < 0.0:
        return 0.0
    if value > 1.0:
        return 1.0
    return value
