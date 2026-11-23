"""Benchmark 100 seedów na każdym z pięciu poziomów."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from generator import build_puzzle

SEEDS = range(100)
LEVELS = range(1, 6)
OUT = Path(__file__).resolve().parent / "etap5_benchmark.json"


def median(values: list[float]) -> float:
    ordered = sorted(values)
    return ordered[len(ordered) // 2]


def pack(rows: list[dict]) -> dict:
    def column(key: str) -> list[float]:
        return [row[key] for row in rows]

    summary = {}
    for key in (
        "arrows",
        "free",
        "free_ratio",
        "depth",
        "blocks",
        "logic_difficulty",
        "visual_search",
        "spatial",
        "fit",
        "deviation",
        "time",
        "first_share",
        "blocks_per_arrow",
    ):
        values = column(key)
        summary[key] = {
            "min": min(values),
            "median": median(values),
            "mean": sum(values) / len(values),
            "max": max(values),
        }
    summary["profile_miss"] = sum(1 for row in rows if row["profile_miss"])
    summary["fallback"] = sum(1 for row in rows if row["fallback"])
    summary["rejected_mean"] = sum(row["rejected"] for row in rows) / len(rows)
    curves = [tuple(row["curve"]) for row in rows]
    summary["curve_median_length"] = median([len(curve) for curve in curves])
    return summary


def main() -> None:
    grouped = {level: [] for level in LEVELS}
    records = []
    for level in LEVELS:
        for seed in SEEDS:
            puzzle = build_puzzle(seed, difficulty=level, report=False)
            stats = puzzle.final_stats
            row = {
                "seed": seed,
                "level": level,
                "arrows": stats["arrows"],
                "free": stats["free"],
                "free_ratio": stats["free_ratio"],
                "depth": stats["depth"],
                "blocks": stats["blocks"],
                "logic_difficulty": stats["logic_difficulty"],
                "visual_search": stats["visual_search"],
                "spatial": stats["spatial"],
                "fit": stats["fit"],
                "deviation": stats["deviation"],
                "time": stats["time"],
                "first_share": stats["first_share"],
                "blocks_per_arrow": stats["blocks_per_arrow"],
                "curve": stats["curve"],
                "profile_miss": stats["profile_miss"],
                "fallback": stats["fallback"],
                "rejected": puzzle.core_stats["rejected"],
                "outside": stats["outside"],
            }
            grouped[level].append(row)
            records.append(row)
        print(f"level {level} done", flush=True)
    summary = {str(level): pack(grouped[level]) for level in LEVELS}
    OUT.write_text(json.dumps({"summary": summary, "records": records}, ensure_ascii=False), encoding="utf-8")
    for level, stats in summary.items():
        print(
            f"L{level} arrows {stats['arrows']['median']:.0f} "
            f"free {stats['free']['median']:.0f} "
            f"ratio {stats['free_ratio']['median']:.2f} "
            f"depth {stats['depth']['median']:.0f} "
            f"blocks {stats['blocks']['median']:.0f} "
            f"ld {stats['logic_difficulty']['median']:.2f} "
            f"vs {stats['visual_search']['median']:.2f} "
            f"sp {stats['spatial']['median']:.2f} "
            f"time {stats['time']['mean']:.3f}s "
            f"miss {stats['profile_miss']} "
            f"rejected {stats['rejected_mean']:.1f}"
        )


if __name__ == "__main__":
    main()
