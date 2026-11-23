"""Ocena kompozycji planszy prostymi miarami geometrycznymi.

Pokrycie siatki jest osobną miarą. Wynik wizualny opisuje rozłożenie,
a nie samą liczbę zajętych komórek.
"""

from __future__ import annotations

from engine import DIRECTION_DELTA, Board, bend_count, ray_cells

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
    return _clamp(1.0 - spread / 3.0)


def spatial_balance(board: Board) -> dict:
    """Rozproszenie po planszy. Pusta, ale rozłożona plansza może wypaść wysoko."""
    area = board.size * board.size
    if not board.occupied:
        parts = {
            "quadrants": 0.0,
            "heads": 0.0,
            "coverage": 0.0,
            "local": 1.0,
            "openness": 1.0,
        }
        return {"score": 0.0, "parts": parts, "largest_empty": area}
    mid = board.size / 2
    cells = [0, 0, 0, 0]
    heads = [0, 0, 0, 0]
    for row, col in board.occupied:
        cells[_quadrant(row, col, mid)] += 1
    for arrow in board.arrows:
        row, col = arrow.head
        heads[_quadrant(row, col, mid)] += 1
    used = sum(1 for count in cells if count) / 4
    even_cells = _evenness(cells)
    even_heads = _evenness(heads) if board.arrows else 0.0
    local = _clamp(1.0 - _clump_ratio(board))
    largest = _largest_empty(board)
    hole_share = largest / area
    void = hole_share * (1.0 - even_cells)
    openness = _clamp(1.0 - void / 0.50)
    spread = _head_spread(board)
    half = _half_balance(board)
    parts = {
        "quadrants": even_cells,
        "heads": even_heads,
        "coverage": used,
        "local": local,
        "openness": openness,
        "spread": spread,
        "half": half,
    }
    score = (
        0.22 * even_cells
        + 0.16 * even_heads
        + 0.12 * used
        + 0.12 * local
        + 0.12 * openness
        + 0.14 * spread
        + 0.12 * half
    )
    return {"score": _clamp(score), "parts": parts, "largest_empty": largest}


def _half_balance(board: Board) -> float:
    """0 gdy cała masa komórek leży w jednej połowie wierszy albo kolumn."""
    total = len(board.occupied)
    if total <= 0:
        return 1.0
    mid = board.size / 2
    top = sum(1 for row, _col in board.occupied if row < mid)
    left = sum(1 for _row, col in board.occupied if col < mid)
    return min(top, total - top, left, total - left) / total


def empty_runs(board: Board) -> tuple[int, int]:
    """Najdłuższy ciąg całkowicie pustych wierszy i kolumn."""
    return _empty_run(board, True), _empty_run(board, False)


def _empty_run(board: Board, rows: bool) -> int:
    best = 0
    current = 0
    for index in range(board.size):
        if rows:
            empty = all((index, col) not in board.occupied for col in range(board.size))
        else:
            empty = all((row, index) not in board.occupied for row in range(board.size))
        current = current + 1 if empty else 0
        best = max(best, current)
    return best


def fillability(board: Board) -> float:
    """Jaka część pustych komórek nadaje się na poprawną strzałkę."""
    components = _empty_components(board)
    if not components:
        return 1.0
    usable = 0
    trapped = 0
    for component in components:
        if len(component) >= 4 and _component_holds_arrow(component, board):
            usable += len(component)
        else:
            trapped += len(component)
    total = usable + trapped
    return usable / total if total else 1.0


def _empty_components(board: Board) -> list[list[tuple[int, int]]]:
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
                for d_row, d_col in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                    nxt = (cell[0] + d_row, cell[1] + d_col)
                    if (
                        not (0 <= nxt[0] < board.size and 0 <= nxt[1] < board.size)
                        or nxt in board.occupied
                        or nxt in seen
                    ):
                        continue
                    seen.add(nxt)
                    stack.append(nxt)
            components.append(component)
    components.sort(key=len, reverse=True)
    return components


def _component_holds_arrow(component: list[tuple[int, int]], board: Board) -> bool:
    area = set(component)
    for row, col in component:
        for name, (d_row, d_col) in DIRECTION_DELTA.items():
            behind = (row - d_row, col - d_col)
            if behind not in area:
                continue
            if all(cell not in board.occupied for cell in ray_cells(row, col, name, board.size)):
                return True
    return False


def _head_spread(board: Board) -> float:
    heads = [arrow.head for arrow in board.arrows]
    if len(heads) < 2:
        return 1.0
    total = 0.0
    pairs = 0
    for index, head in enumerate(heads):
        for other in heads[index + 1 :]:
            total += abs(head[0] - other[0]) + abs(head[1] - other[1])
            pairs += 1
    return _clamp((total / pairs) / (board.size * 0.75))


def _clump_ratio(board: Board) -> float:
    occupied = board.occupied
    if not occupied:
        return 0.0
    knots = 0
    for row, col in occupied:
        near = 0
        for d_row in (-1, 0, 1):
            for d_col in (-1, 0, 1):
                if d_row == 0 and d_col == 0:
                    continue
                if (row + d_row, col + d_col) in occupied:
                    near += 1
        if near >= 5:
            knots += 1
    return knots / len(occupied)


def _largest_empty(board: Board) -> int:
    empty = {
        (row, col)
        for row in range(board.size)
        for col in range(board.size)
        if (row, col) not in board.occupied
    }
    seen: set[tuple[int, int]] = set()
    largest = 0
    for start in empty:
        if start in seen:
            continue
        stack = [start]
        seen.add(start)
        size = 0
        while stack:
            row, col = stack.pop()
            size += 1
            for nxt in ((row - 1, col), (row + 1, col), (row, col - 1), (row, col + 1)):
                if nxt in empty and nxt not in seen:
                    seen.add(nxt)
                    stack.append(nxt)
        if size > largest:
            largest = size
    return largest


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
