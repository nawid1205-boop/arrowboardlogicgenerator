"""Profile trudności i pomiar rzeczywistej charakterystyki planszy.

Odległość od profilu służy do wyboru kandydata. Osobny wynik trudności
opisuje planszę niezależnie od tego, czy trafiła w założony poziom.
"""

from __future__ import annotations

from dataclasses import dataclass

from engine import Board, bend_count
from quality_logic import analyze_logic
from quality_visual import analyze_visual, spatial_balance

LABELS = {
    1: "Bardzo łatwa",
    2: "Łatwa",
    3: "Średnia",
    4: "Trudna",
    5: "Ekspercka",
}

FIT_WEIGHTS = {
    "free_ratio": 0.28,
    "depth": 0.24,
    "blocks_per_arrow": 0.16,
    "first_share": 0.12,
    "visual_search": 0.12,
    "arrows": 0.08,
}

LOGIC_DIFFICULTY_WEIGHTS = {
    "opening": 0.34,
    "depth": 0.30,
    "blocks": 0.22,
    "release": 0.14,
}


@dataclass(frozen=True)
class DifficultyProfile:
    level: int
    label: str
    core_arrows: tuple[int, int]
    total_arrows: tuple[int, int]
    free_ratio: tuple[float, float]
    depth: tuple[int, int]
    blocks_per_arrow: tuple[float, float]
    first_share: tuple[float, float]
    visual_search: tuple[float, float]
    min_spatial: float
    blocking_bias: float
    prefer_block: float
    block_weight: int
    max_open: int
    turn_probability: float
    archetype_weights: tuple[int, int, int, int]
    long_length: int
    spread_bonus: int
    stagnant: int
    fill_budget: int
    fill_variants: int
    free_slack: int
    trials: int
    finalists: int
    hard_arrows: tuple[int, int]
    hard_min_free: int
    hard_min_blocked: int
    hard_free_le_blocked: bool
    hard_min_curved: int
    hard_min_straight: int
    strict_emergency: bool


def _profile(**kwargs) -> DifficultyProfile:
    return DifficultyProfile(**kwargs)


PROFILES = {
    1: _profile(
        level=1,
        label=LABELS[1],
        core_arrows=(7, 9),
        total_arrows=(7, 10),
        free_ratio=(0.42, 0.72),
        depth=(2, 4),
        blocks_per_arrow=(0.20, 0.80),
        first_share=(0.42, 0.75),
        visual_search=(0.05, 0.30),
        min_spatial=0.40,
        blocking_bias=0.20,
        prefer_block=0.15,
        block_weight=1,
        max_open=9,
        turn_probability=0.10,
        archetype_weights=(8, 2, 2, 1),
        long_length=5,
        spread_bonus=3,
        stagnant=22,
        fill_budget=0,
        fill_variants=1,
        free_slack=2,
        trials=10,
        finalists=1,
        hard_arrows=(6, 12),
        hard_min_free=2,
        hard_min_blocked=1,
        hard_free_le_blocked=False,
        hard_min_curved=0,
        hard_min_straight=2,
        strict_emergency=False,
    ),
    2: _profile(
        level=2,
        label=LABELS[2],
        core_arrows=(9, 12),
        total_arrows=(10, 14),
        free_ratio=(0.30, 0.50),
        depth=(4, 7),
        blocks_per_arrow=(0.65, 1.25),
        first_share=(0.28, 0.50),
        visual_search=(0.15, 0.42),
        min_spatial=0.38,
        blocking_bias=0.48,
        prefer_block=0.50,
        block_weight=3,
        max_open=7,
        turn_probability=0.18,
        archetype_weights=(5, 2, 3, 2),
        long_length=6,
        spread_bonus=2,
        stagnant=26,
        fill_budget=2,
        fill_variants=3,
        free_slack=1,
        trials=12,
        finalists=2,
        hard_arrows=(8, 15),
        hard_min_free=2,
        hard_min_blocked=1,
        hard_free_le_blocked=False,
        hard_min_curved=1,
        hard_min_straight=2,
        strict_emergency=False,
    ),
    3: _profile(
        level=3,
        label=LABELS[3],
        core_arrows=(12, 16),
        total_arrows=(12, 18),
        free_ratio=(0.18, 0.38),
        depth=(6, 11),
        blocks_per_arrow=(1.05, 1.85),
        first_share=(0.16, 0.40),
        visual_search=(0.20, 0.55),
        min_spatial=0.30,
        blocking_bias=0.78,
        prefer_block=0.90,
        block_weight=5,
        max_open=12,
        turn_probability=0.30,
        archetype_weights=(3, 2, 3, 4),
        long_length=8,
        spread_bonus=1,
        stagnant=28,
        fill_budget=8,
        fill_variants=4,
        free_slack=1,
        trials=14,
        finalists=1,
        hard_arrows=(12, 16),
        hard_min_free=1,
        hard_min_blocked=1,
        hard_free_le_blocked=True,
        hard_min_curved=2,
        hard_min_straight=2,
        strict_emergency=True,
    ),
    4: _profile(
        level=4,
        label=LABELS[4],
        core_arrows=(13, 16),
        total_arrows=(14, 18),
        free_ratio=(0.18, 0.32),
        depth=(8, 11),
        blocks_per_arrow=(1.15, 1.80),
        first_share=(0.16, 0.32),
        visual_search=(0.28, 0.55),
        min_spatial=0.28,
        blocking_bias=0.76,
        prefer_block=0.86,
        block_weight=5,
        max_open=8,
        turn_probability=0.26,
        archetype_weights=(3, 2, 4, 3),
        long_length=8,
        spread_bonus=1,
        stagnant=28,
        fill_budget=2,
        fill_variants=2,
        free_slack=1,
        trials=8,
        finalists=1,
        hard_arrows=(12, 22),
        hard_min_free=1,
        hard_min_blocked=1,
        hard_free_le_blocked=True,
        hard_min_curved=2,
        hard_min_straight=2,
        strict_emergency=False,
    ),
    5: _profile(
        level=5,
        label=LABELS[5],
        core_arrows=(14, 17),
        total_arrows=(14, 19),
        free_ratio=(0.16, 0.28),
        depth=(8, 13),
        blocks_per_arrow=(1.25, 1.95),
        first_share=(0.12, 0.28),
        visual_search=(0.34, 0.64),
        min_spatial=0.28,
        blocking_bias=0.90,
        prefer_block=0.95,
        block_weight=7,
        max_open=8,
        turn_probability=0.34,
        archetype_weights=(2, 2, 4, 5),
        long_length=8,
        spread_bonus=1,
        stagnant=30,
        fill_budget=3,
        fill_variants=2,
        free_slack=0,
        trials=8,
        finalists=1,
        hard_arrows=(13, 20),
        hard_min_free=1,
        hard_min_blocked=1,
        hard_free_le_blocked=True,
        hard_min_curved=2,
        hard_min_straight=2,
        strict_emergency=False,
    ),
}


def profile_for(level: int) -> DifficultyProfile:
    try:
        return PROFILES[int(level)]
    except (KeyError, TypeError, ValueError):
        raise ValueError(f"Poziom trudności musi być od 1 do 5, otrzymano {level}") from None


def analyze_difficulty(board: Board) -> dict:
    """Charakterystyka gotowej planszy, liczona z grafu blokad i geometrii."""
    logic = analyze_logic(board)
    arrows = logic["arrows"]
    denom = arrows or 1
    spatial = spatial_balance(board)
    bends = [bend_count(arrow.cells) for arrow in board.arrows]
    lengths = [len(arrow.cells) for arrow in board.arrows]
    curve = logic["curve"]
    report = {
        "arrows": arrows,
        "free": logic["free"],
        "free_ratio": logic["free"] / denom,
        "depth": logic["depth"],
        "blocks": logic["blocks"],
        "blocks_per_arrow": logic["blocks"] / denom,
        "splits": logic["splits"],
        "joins": logic["joins"],
        "isolated": logic["isolated"],
        "curve": curve,
        "stages": logic["stages"],
        "first_share": (curve[0] / denom) if curve else 0.0,
        "curved": sum(1 for value in bends if value),
        "straight": arrows - sum(1 for value in bends if value),
        "mean_bends": (sum(bends) / denom) if arrows else 0.0,
        "mean_length": (sum(lengths) / denom) if arrows else 0.0,
        "visual_search": visual_search_complexity(board),
        "spatial": spatial["score"],
        "spatial_parts": spatial["parts"],
        "largest_empty": spatial["largest_empty"],
        "solved": logic["solved"],
    }
    report["logic_difficulty"] = logic_difficulty_score(report)
    return report


def visual_search_complexity(board: Board) -> float:
    """Geometryczna trudność wypatrzenia ruchu. Wyższa wartość znaczy trudniej."""
    arrows = board.arrows
    count = len(arrows)
    if count <= 0:
        return 0.0
    mean_length = sum(len(arrow.cells) for arrow in arrows) / count
    mean_bends = sum(bend_count(arrow.cells) for arrow in arrows) / count
    heads = [arrow.head for arrow in arrows]
    crowded = 0
    interior = 0
    margin = 2
    for index, head in enumerate(heads):
        near = 0
        for other_index, other in enumerate(heads):
            if other_index == index:
                continue
            if max(abs(head[0] - other[0]), abs(head[1] - other[1])) <= 2:
                near += 1
        if near >= 3:
            crowded += 1
        if margin <= head[0] < board.size - margin and margin <= head[1] < board.size - margin:
            interior += 1
    return _clamp(
        0.30 * (mean_length - 2.0) / 6.0
        + 0.25 * min(1.0, mean_bends / 1.5)
        + 0.25 * (crowded / count)
        + 0.20 * (interior / count)
    )


def logic_difficulty_score(report: dict) -> float:
    """0 to plansza luźna, 1 to długa sieć blokad. Bez oceny ładności."""
    parts = {
        "opening": _clamp(1.0 - report["free_ratio"] / 0.65),
        "depth": _clamp((report["depth"] - 1) / 14.0),
        "blocks": _clamp(report["blocks_per_arrow"] / 2.2),
        "release": _clamp(1.0 - report["first_share"] / 0.70),
    }
    return _weighted(parts, LOGIC_DIFFICULTY_WEIGHTS)


def profile_fit(report: dict, profile: DifficultyProfile) -> float:
    """1 oznacza trafienie we wszystkie pasma profilu."""
    parts = {
        "free_ratio": range_fit(report["free_ratio"], *profile.free_ratio),
        "depth": range_fit(report["depth"], *profile.depth),
        "blocks_per_arrow": range_fit(report["blocks_per_arrow"], *profile.blocks_per_arrow),
        "first_share": range_fit(report["first_share"], *profile.first_share),
        "visual_search": range_fit(report["visual_search"], *profile.visual_search),
        "arrows": range_fit(report["arrows"], *profile.total_arrows),
    }
    return _weighted(parts, FIT_WEIGHTS)


def outside_targets(report: dict, profile: DifficultyProfile) -> list[str]:
    checks = {
        "free_ratio": range_fit(report["free_ratio"], *profile.free_ratio),
        "depth": range_fit(report["depth"], *profile.depth),
        "blocks_per_arrow": range_fit(report["blocks_per_arrow"], *profile.blocks_per_arrow),
        "first_share": range_fit(report["first_share"], *profile.first_share),
        "visual_search": range_fit(report["visual_search"], *profile.visual_search),
        "arrows": range_fit(report["arrows"], *profile.total_arrows),
    }
    return [name for name, value in checks.items() if value < 1.0]


def selection_rank(board: Board, profile: DifficultyProfile | int | None = None) -> tuple:
    """Najpierw zgodność z poziomem, potem rozłożenie, potem czytelność kształtu."""
    if not isinstance(profile, DifficultyProfile):
        profile = profile_for(3 if profile is None else profile)
    report = analyze_difficulty(board)
    fit = profile_fit(report, profile)
    spatial = report["spatial"]
    adjusted = fit * (0.80 + 0.20 * spatial)
    readable = analyze_visual(board)["parts"]["shape"]
    if profile.level <= 2:
        cover = -len(board.occupied)
    elif profile.level >= 4:
        cover = len(board.occupied)
    else:
        cover = 0
    return (
        int(adjusted * 20),
        int(spatial * 20),
        int(readable * 20),
        round(adjusted, 5),
        cover,
    )


def range_fit(value: float, low: float, high: float) -> float:
    if low <= value <= high:
        return 1.0
    span = max(high - low, 1e-6)
    gap = (low - value) / span if value < low else (value - high) / span
    return _clamp(1.0 - gap)


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
