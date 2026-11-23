"""Ocena kompozycji planszy prostymi miarami geometrycznymi.

Pokrycie siatki nie wchodzi do wyniku. Jest osobnym, niskim priorytetem
przy wyborze między kandydatami o zbliżonej jakości.
"""

from __future__ import annotations

from engine import Board, bend_count

VISUAL_WEIGHTS = {
    "balance": 0.28,
    "diversity": 0.30,
    "congestion": 0.22,
    "shape": 0.20,
}


def analyze_visual(board: Board) -> dict:
    arrows = board.arrows
    count = len(arrows)
    bends = [bend_count(arrow.cells) for arrow in arrows]
    curved = sum(1 for value in bends if value)
    parts = {
        "balance": _balance(board),
        "diversity": _diversity(arrows, bends),
        "congestion": _congestion(arrows),
        "shape": _shape(bends),
    }
    return {
        "score": _weighted(parts, VISUAL_WEIGHTS),
        "parts": parts,
        "curved": curved,
        "straight": count - curved,
        "filled": len(board.occupied),
    }


def _balance(board: Board) -> float:
    if not board.occupied:
        return 0.0
    mid = board.size / 2
    cells = [0, 0, 0, 0]
    heads = [0, 0, 0, 0]
    for row, col in board.occupied:
        cells[_quadrant(row, col, mid)] += 1
    for arrow in board.arrows:
        row, col = arrow.head
        heads[_quadrant(row, col, mid)] += 1
    return _clamp(0.65 * _evenness(cells) + 0.35 * _evenness(heads))


def _quadrant(row: int, col: int, mid: float) -> int:
    return (0 if row < mid else 2) + (0 if col < mid else 1)


def _evenness(counts: list[int]) -> float:
    total = sum(counts)
    if total <= 0:
        return 0.0
    mean = total / 4
    spread = (max(counts) - min(counts)) / mean
    return _clamp(1.0 - spread / 4.0)


def _diversity(arrows, bends: list[int]) -> float:
    count = len(arrows)
    if count <= 0:
        return 0.0
    lengths = [len(arrow.cells) for arrow in arrows]
    length_buckets = (
        any(2 <= length <= 3 for length in lengths),
        any(4 <= length <= 5 for length in lengths),
        any(length >= 6 for length in lengths),
    )
    bend_buckets = (
        any(value == 0 for value in bends),
        any(value == 1 for value in bends),
        any(value >= 2 for value in bends),
    )
    directions = {arrow.direction for arrow in arrows}
    dominant = max(sum(1 for arrow in arrows if arrow.direction == name) for name in directions)
    score = (
        0.40 * (sum(length_buckets) / 3)
        + 0.30 * (sum(bend_buckets) / 3)
        + 0.30 * (len(directions) / 4)
    )
    if dominant / count > 0.70:
        score *= 0.75
    return _clamp(score)


def _congestion(arrows) -> float:
    count = len(arrows)
    if count <= 0:
        return 0.0
    heads = [arrow.head for arrow in arrows]
    short = {
        arrow.head
        for arrow in arrows
        if len(arrow.cells) <= 3
    }
    hot = 0
    for index, head in enumerate(heads):
        near = 0
        short_near = 0
        for other_index, other in enumerate(heads):
            if other_index == index:
                continue
            if max(abs(head[0] - other[0]), abs(head[1] - other[1])) <= 1:
                near += 1
                if other in short and head in short:
                    short_near += 1
        if near >= 3 or short_near >= 2:
            hot += 1
    return _clamp(1.0 - hot / count)


def _shape(bends: list[int]) -> float:
    count = len(bends)
    if count <= 0:
        return 0.0
    twisty = sum(1 for value in bends if value >= 3) / count
    mean = sum(bends) / count
    extra = max(0.0, mean - 1.4) / 2.0
    return _clamp((1.0 - twisty) * (1.0 - min(1.0, extra)))


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
