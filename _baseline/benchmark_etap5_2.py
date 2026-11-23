"""Benchmark 200 seedów na każdym z pięciu poziomów po zagęszczeniu 5.2."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from generator import build_puzzle

SEEDS = range(200)
LEVELS = range(1, 6)
OUT = Path(__file__).resolve().parent / "etap5_2_benchmark.json"


def pick(values: list[float], part: float) -> float:
    ordered = sorted(values)
    index = min(len(ordered) - 1, int(round(part * (len(ordered) - 1))))
    return ordered[index]


def pack(rows: list[dict]) -> dict:
    summary = {}
    for key in (
        "coverage",
        "arrows",
        "mean_length",
        "curved_ratio",
        "depth",
        "joins",
        "free",
        "free_ratio",
        "mean_choices",
        "largest_empty",
        "empty_row_run",
        "empty_col_run",
        "spatial",
        "logic_difficulty",
        "time",
        "core_coverage",
    ):
        values = [row[key] for row in rows]
        summary[key] = {
            "min": min(values),
            "p10": pick(values, 0.10),
            "p25": pick(values, 0.25),
            "median": pick(values, 0.50),
            "mean": sum(values) / len(values),
            "p75": pick(values, 0.75),
            "max": max(values),
        }
    summary["profile_miss"] = sum(1 for row in rows if row["profile_miss"])
    summary["fallback"] = sum(1 for row in rows if row["fallback"])
    summary["solved"] = sum(1 for row in rows if row["solved"])
    summary["rejected_mean"] = sum(row["rejected"] for row in rows) / len(rows)
    summary["fill_arrows_mean"] = sum(row["fill_arrows"] for row in rows) / len(rows)
    return summary


def main() -> None:
    grouped = {level: [] for level in LEVELS}
    records = []
    for level in LEVELS:
        for seed in SEEDS:
            puzzle = build_puzzle(seed, difficulty=level, report=False)
            stats = puzzle.final_stats
            core = puzzle.core_stats
            arrows = stats["arrows"] or 1
            row = {
                "seed": seed,
                "level": level,
                "coverage": stats["coverage"],
                "arrows": stats["arrows"],
                "mean_length": stats["mean_length"],
                "curved_ratio": stats["curved"] / arrows,
                "depth": stats["depth"],
                "joins": stats["joins"],
                "free": stats["free"],
                "free_ratio": stats["free_ratio"],
                "mean_choices": stats["mean_choices"],
                "largest_empty": stats["largest_empty"],
                "empty_row_run": stats["empty_row_run"],
                "empty_col_run": stats["empty_col_run"],
                "spatial": stats["spatial"],
                "logic_difficulty": stats["logic_difficulty"],
                "time": stats["time"],
                "core_coverage": len(puzzle.core.occupied) / (puzzle.core.size ** 2),
                "fill_arrows": stats["arrows"] - core["arrows"],
                "profile_miss": stats["profile_miss"],
                "fallback": stats["fallback"],
                "solved": stats["solved"],
                "rejected": core["rejected"],
                "outside": stats["outside"],
            }
            grouped[level].append(row)
            records.append(row)
        print(f"level {level} done", flush=True)
    summary = {str(level): pack(grouped[level]) for level in LEVELS}
    OUT.write_text(json.dumps({"summary": summary, "records": records}, ensure_ascii=False), encoding="utf-8")
    for level, stats in summary.items():
        print(
            f"L{level} cov {stats['coverage']['p10']:.2f}/{stats['coverage']['median']:.2f}/{stats['coverage']['p75']:.2f} "
            f"arrows {stats['arrows']['median']:.0f} "
            f"len {stats['mean_length']['median']:.2f} "
            f"curved {stats['curved_ratio']['median']:.2f} "
            f"free {stats['free']['median']:.0f} "
            f"depth {stats['depth']['p25']:.0f}/{stats['depth']['median']:.0f}/{stats['depth']['p75']:.0f} "
            f"joins {stats['joins']['median']:.0f} "
            f"empty {stats['largest_empty']['median']:.0f} "
            f"rows {stats['empty_row_run']['median']:.0f} "
            f"sp {stats['spatial']['median']:.2f} "
            f"time {stats['time']['mean']:.3f}/{stats['time']['max']:.3f}s "
            f"miss {stats['profile_miss']} fb {stats['fallback']} "
            f"rej {stats['rejected_mean']:.1f} "
            f"fill {stats['fill_arrows_mean']:.2f}"
        )


if __name__ == "__main__":
    main()
