"""Galeria diagnostyczna pięciu poziomów. Nie jest częścią okna gry."""

from __future__ import annotations

from pathlib import Path

from difficulty import LABELS
from engine import bend_count
from generator import build_puzzle

CELL = 18
PAD = 16
SEEDS = (1, 2, 3, 4, 5)


def _points(cells: tuple[tuple[int, int], ...]) -> str:
    coords = []
    for row, col in cells:
        x = PAD + (col + 0.5) * CELL
        y = PAD + (row + 0.5) * CELL
        coords.append(f"{x:.1f},{y:.1f}")
    return " ".join(coords)


def _arrow(arrow) -> str:
    points = _points(arrow.cells)
    row, col = arrow.head
    previous = arrow.cells[-2]
    dx = col - previous[1]
    dy = row - previous[0]
    tip_x = PAD + (col + 0.5) * CELL + dx * CELL * 0.28
    tip_y = PAD + (row + 0.5) * CELL + dy * CELL * 0.28
    base_x = tip_x - dx * CELL * 0.42
    base_y = tip_y - dy * CELL * 0.42
    px, py = -dy, dx
    wing = CELL * 0.22
    left = f"{base_x + px * wing:.1f},{base_y + py * wing:.1f}"
    right = f"{base_x - px * wing:.1f},{base_y - py * wing:.1f}"
    tip = f"{tip_x:.1f},{tip_y:.1f}"
    bends = bend_count(arrow.cells)
    width = 2.2 if bends else 1.8
    return (
        f'<polyline points="{points}" fill="none" stroke="#ffffff" '
        f'stroke-width="{width}" stroke-linecap="round" stroke-linejoin="round"/>'
        f'<polygon points="{left} {tip} {right}" fill="#ffffff"/>'
    )


def _board(puzzle, level: int, seed: int) -> str:
    stats = puzzle.final_stats
    size = PAD * 2 + 12 * CELL
    arrows = "".join(_arrow(arrow) for arrow in puzzle.final.arrows)
    caption = (
        f"Difficulty {level} — {LABELS[level]}<br>"
        f"seed {seed}<br>"
        f"strzałki {stats['arrows']}<br>"
        f"ruchy {stats['free']}<br>"
        f"głębokość {stats['depth']}<br>"
        f"logic {stats['logic_difficulty']:.2f}<br>"
        f"spatial {stats['spatial']:.2f}"
    )
    return (
        '<figure>'
        f'<svg width="{size}" height="{size}" viewBox="0 0 {size} {size}">'
        f'<rect width="100%" height="100%" fill="#050505"/>{arrows}</svg>'
        f"<figcaption>{caption}</figcaption></figure>"
    )


def build_gallery(path: Path) -> None:
    sections = []
    for level in range(1, 6):
        cards = []
        for seed in SEEDS:
            puzzle = build_puzzle(seed, difficulty=level, report=False)
            cards.append(_board(puzzle, level, seed))
        sections.append(f"<section><h2>{level} — {LABELS[level]}</h2>{''.join(cards)}</section>")
    html = f"""<!DOCTYPE html>
<html lang="pl">
<head>
<meta charset="utf-8">
<title>Arrow Puzzle — poziomy trudności</title>
<style>
body {{ margin: 0; background: #050505; color: #d0d0d0; font: 14px Segoe UI, sans-serif; }}
h1, h2 {{ font-weight: 500; }}
h1 {{ padding: 28px 32px 0; }}
section {{ padding: 8px 32px 24px; }}
figure {{ display: inline-block; margin: 0 18px 18px 0; vertical-align: top; }}
figcaption {{ margin-top: 8px; color: #9a9a9a; line-height: 1.45; }}
</style>
</head>
<body>
<h1>Galeria poziomów 1–5</h1>
{''.join(sections)}
</body>
</html>
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, encoding="utf-8")


if __name__ == "__main__":
    destination = Path(__file__).resolve().parent / "gallery" / "difficulty.html"
    build_gallery(destination)
    print(destination)
