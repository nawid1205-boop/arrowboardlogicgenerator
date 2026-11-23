"""Porównanie zapisanego generatora sprzed ETAP 4 z bieżącym kodem."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import Arrow, Board
from generator import build_puzzle
from quality_logic import analyze_logic
from quality_visual import analyze_visual

ROOT = Path(__file__).resolve().parent
OLD_PATH = ROOT / "pre_etap4.json"
OUT_PATH = ROOT / "etap4_compare.json"


def board_from(cells: list) -> Board:
    board = Board(12)
    for index, path in enumerate(cells, start=1):
        board.add(Arrow(index, tuple(tuple(cell) for cell in path)))
    return board


def pack(board: Board, seconds: float | None = None) -> dict:
    logic = analyze_logic(board)
    visual = analyze_visual(board)
    arrows = logic["arrows"] or 1
    curve = logic["curve"]
    return {
        "arrows": logic["arrows"],
        "filled": len(board.occupied),
        "free": logic["free"],
        "blocks": logic["blocks"],
        "depth": logic["depth"],
        "stages": logic["stages"],
        "curve": curve,
        "isolated": logic["isolated"],
        "splits": logic["splits"],
        "joins": logic["joins"],
        "logic": round(logic["score"], 5),
        "visual": round(visual["score"], 5),
        "logic_parts": {name: round(value, 5) for name, value in logic["parts"].items()},
        "visual_parts": {name: round(value, 5) for name, value in visual["parts"].items()},
        "curved": visual["curved"],
        "straight": visual["straight"],
        "solved": logic["solved"],
        "first_share": round(curve[0] / arrows, 5) if curve else None,
        "variety": round(len(set(curve)) / len(curve), 5) if curve else 0.0,
        "seconds": None if seconds is None else round(seconds, 4),
    }


def mean(rows: list[dict], key: str) -> float:
    return sum(row[key] for row in rows) / len(rows)


def span(rows: list[dict], key: str) -> str:
    values = [row[key] for row in rows]
    return f"{min(values)}-{max(values)} avg {mean(rows, key):.2f}"


def main() -> None:
    old_raw = json.loads(OLD_PATH.read_text(encoding="utf-8"))
    groups = {"old_core": [], "old_final": [], "new_core": [], "new_final": []}
    records = []
    mismatches = {"free": 0, "blocks": 0, "depth": 0, "stages": 0}
    fallbacks = 0
    time_capped = 0
    for item in old_raw:
        old_core_board = board_from(item["core"]["cells"])
        old_final_board = board_from(item["final"]["cells"])
        old_core = pack(old_core_board)
        old_final = pack(old_final_board, item["seconds"])
        for key in mismatches:
            if old_core[key] != item["core"][key]:
                mismatches[key] += 1
        puzzle = build_puzzle(item["seed"], report=False)
        new_core = pack(puzzle.core)
        new_final = pack(puzzle.final, puzzle.final_stats["time"])
        fallbacks += int(puzzle.core_stats["fallback"])
        time_capped += int(puzzle.fill_stats.get("time_capped", False))
        groups["old_core"].append(old_core)
        groups["old_final"].append(old_final)
        groups["new_core"].append(new_core)
        groups["new_final"].append(new_final)
        records.append(
            {
                "seed": item["seed"],
                "old_seconds": item["seconds"],
                "old_fill_added": item["fill_added"],
                "new_fill_added": puzzle.fill_stats["added"],
                "new_fallback": puzzle.core_stats["fallback"],
                "new_rejected": puzzle.core_stats["rejected"],
                "old_core": old_core,
                "old_final": old_final,
                "new_core": new_core,
                "new_final": new_final,
            }
        )

    summary = {"seeds": len(records), "fallbacks": fallbacks, "time_capped": time_capped, "stored_vs_rescored_mismatches": mismatches}
    fields = [
        "arrows",
        "filled",
        "free",
        "blocks",
        "depth",
        "stages",
        "isolated",
        "splits",
        "logic",
        "visual",
        "first_share",
        "variety",
        "curved",
        "straight",
    ]
    for name, rows in groups.items():
        summary[name] = {key: span(rows, key) for key in fields}
        summary[name]["seconds"] = span(rows, "seconds") if rows[0]["seconds"] is not None else "n/a"
        summary[name]["free_eq_1"] = sum(row["free"] <= 1 for row in rows)
        summary[name]["free_ge_6"] = sum(row["free"] >= 6 for row in rows)
        summary[name]["first_share_gt_050"] = sum((row["first_share"] or 0) > 0.50 for row in rows)
        summary[name]["unsolved"] = sum(not row["solved"] for row in rows)
        for part in rows[0]["logic_parts"]:
            summary[name][f"logic_{part}"] = f"{sum(row['logic_parts'][part] for row in rows) / len(rows):.3f}"
        for part in rows[0]["visual_parts"]:
            summary[name][f"visual_{part}"] = f"{sum(row['visual_parts'][part] for row in rows) / len(rows):.3f}"

    summary["new_fill_added"] = span(
        [{"added": record["new_fill_added"]} for record in records],
        "added",
    )
    summary["old_fill_added"] = span(
        [{"added": record["old_fill_added"]} for record in records],
        "added",
    )
    summary["new_fill_zero"] = sum(record["new_fill_added"] == 0 for record in records)
    summary["old_fill_zero"] = sum(record["old_fill_added"] == 0 for record in records)
    OUT_PATH.write_text(json.dumps({"summary": summary, "records": records}, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
