"""Benchmark 200 seedów na każdym z pięciu poziomów po kalibracji 5.1."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from generator import build_puzzle

SEEDS = range(200)
LEVELS = range(1, 6)
OUT = Path(__file__).resolve().parent / "etap5_1_benchmark.json"


def median(values: list[float]) -> float:
    ordered = sorted(values)
    return ordered[len(ordered) // 2]


def quartile(values: list[float], part: float) -> float:
    ordered = sorted(values)
    index = min(len(ordered) - 1, int(round(part * (len(ordered) - 1))))
    return ordered[index]


def pack(rows: list[dict]) -> dict:
    summary = {}
    for key in (
        "arrows",
        "free",
        "free_ratio",
        "depth",
        "blocks",
        "joins",
        "join_ratio",
        "mean_choices",
        "first_share",
        "logic_difficulty",
        "visual_search",
        "spatial",
        "largest_empty",
        "fit",
        "deviation",
        "time",
        "core_arrows",
        "core_free",
        "core_depth",
        "core_joins",
    ):
        values = [row[key] for row in rows]
        summary[key] = {
            "min": min(values),
            "q25": quartile(values, 0.25),
            "median": median(values),
            "mean": sum(values) / len(values),
            "q75": quartile(values, 0.75),
            "max": max(values),
        }
    summary["profile_miss"] = sum(1 for row in rows if row["profile_miss"])
    summary["fallback"] = sum(1 for row in rows if row["fallback"])
    summary["solved"] = sum(1 for row in rows if row["solved"])
    summary["rejected_mean"] = sum(row["rejected"] for row in rows) / len(rows)
    summary["fill_arrows_mean"] = sum(row["arrows"] - row["core_arrows"] for row in rows) / len(rows)
    return summary


def main() -> None:
    grouped = {level: [] for level in LEVELS}
    records = []
    for level in LEVELS:
        for seed in SEEDS:
            puzzle = build_puzzle(seed, difficulty=level, report=False)
            stats = puzzle.final_stats
            core = puzzle.core_stats
            row = {
                "seed": seed,
                "level": level,
                "arrows": stats["arrows"],
                "free": stats["free"],
                "free_ratio": stats["free_ratio"],
                "depth": stats["depth"],
                "blocks": stats["blocks"],
                "joins": stats["joins"],
                "join_ratio": stats["join_ratio"],
                "mean_choices": stats["mean_choices"],
                "first_share": stats["first_share"],
                "logic_difficulty": stats["logic_difficulty"],
                "visual_search": stats["visual_search"],
                "spatial": stats["spatial"],
                "largest_empty": stats["largest_empty"],
                "fit": stats["fit"],
                "deviation": stats["deviation"],
                "time": stats["time"],
                "curve": stats["curve"],
                "profile_miss": stats["profile_miss"],
                "fallback": stats["fallback"],
                "solved": stats["solved"],
                "rejected": core["rejected"],
                "outside": stats["outside"],
                "core_arrows": core["arrows"],
                "core_free": core["free"],
                "core_depth": core["depth"],
                "core_joins": core["joins"],
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
            f"depth {stats['depth']['q25']:.0f}/{stats['depth']['median']:.0f}/{stats['depth']['q75']:.0f} "
            f"joins {stats['joins']['median']:.0f} "
            f"choices {stats['mean_choices']['median']:.2f} "
            f"ld {stats['logic_difficulty']['median']:.2f} "
            f"vs {stats['visual_search']['median']:.2f} "
            f"sp {stats['spatial']['median']:.2f} "
            f"empty {stats['largest_empty']['median']:.0f} "
            f"time {stats['time']['mean']:.3f}/{stats['time']['max']:.3f}s "
            f"miss {stats['profile_miss']} fb {stats['fallback']} "
            f"fill {stats['fill_arrows_mean']:.2f}"
        )


if __name__ == "__main__":
    main()
