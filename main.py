"""Okno gry Arrow Out. Czarne tło, białe strzałki, jeden przycisk."""

from __future__ import annotations

import random
import tkinter as tk

from difficulty import LABELS
from engine import Arrow, can_move
from generator import generate_board

BACKGROUND = "#050505"
ARROW_COLOR = "#ffffff"
BLOCKED_COLOR = "#ff3b30"
GRID_COLOR = "#222222"
COORD_COLOR = "#3a3a3a"
WINDOW_SIZE = "900x800"
SHOW_GRID = True


def arrow_geometry(
    arrow: Arrow,
    origin_x: float,
    origin_y: float,
    cell: float,
) -> dict:
    """Geometria ścieżki w pikselach. Ta sama funkcja rysuje i wykrywa kliknięcia."""
    centers = [
        (
            origin_x + (col + 0.5) * cell,
            origin_y + (row + 0.5) * cell,
        )
        for row, col in arrow.cells
    ]
    half = max(1.7, cell * 0.075)
    head_half = max(half + 2.0, cell * 0.22)
    head_len = max(head_half * 1.35, cell * 0.40)
    tail_unit = _unit(centers[0], centers[1])
    head_unit = _unit(centers[-2], centers[-1])
    start = (
        centers[0][0] - tail_unit[0] * cell * 0.34,
        centers[0][1] - tail_unit[1] * cell * 0.34,
    )
    tip = (
        centers[-1][0] + head_unit[0] * cell * 0.36,
        centers[-1][1] + head_unit[1] * cell * 0.36,
    )
    base = (
        tip[0] - head_unit[0] * head_len,
        tip[1] - head_unit[1] * head_len,
    )
    spine = [start, *centers[1:-1], base]
    if len(centers) == 2:
        spine = [start, base]
    perp = (-head_unit[1], head_unit[0])
    left_wing = (base[0] + perp[0] * head_half, base[1] + perp[1] * head_half)
    right_wing = (base[0] - perp[0] * head_half, base[1] - perp[1] * head_half)
    left, right = _side_offsets(spine, half)
    polygon: list[float] = []
    for point in left:
        polygon.extend(point)
    polygon.extend(left_wing)
    polygon.extend(tip)
    polygon.extend(right_wing)
    for point in reversed(right):
        polygon.extend(point)
    segments = [(start, centers[0])]
    segments.extend(zip(centers, centers[1:]))
    return {
        "polygon": tuple(polygon),
        "segments": tuple(segments),
        "half": half,
        "triangle": (tip, left_wing, right_wing),
        "pad": max(3.0, cell * 0.07),
    }


def _unit(start: tuple[float, float], end: tuple[float, float]) -> tuple[float, float]:
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    length = (dx * dx + dy * dy) ** 0.5
    return dx / length, dy / length


def _side_offsets(
    points: list[tuple[float, float]],
    half: float,
) -> tuple[list[tuple[float, float]], list[tuple[float, float]]]:
    normals: list[tuple[float, float]] = []
    for index in range(len(points) - 1):
        dx = points[index + 1][0] - points[index][0]
        dy = points[index + 1][1] - points[index][1]
        length = (dx * dx + dy * dy) ** 0.5
        normals.append((-dy / length, dx / length))

    left: list[tuple[float, float]] = []
    right: list[tuple[float, float]] = []

    def push(point: tuple[float, float], normal: tuple[float, float]) -> None:
        left.append((point[0] + normal[0] * half, point[1] + normal[1] * half))
        right.append((point[0] - normal[0] * half, point[1] - normal[1] * half))

    push(points[0], normals[0])
    for index in range(1, len(points) - 1):
        previous = normals[index - 1]
        nxt = normals[index]
        dot = previous[0] * nxt[0] + previous[1] * nxt[1]
        denom = 1.0 + dot
        if denom < 0.25:
            push(points[index], previous)
            push(points[index], nxt)
            continue
        scale = min(half * 2.5, half / denom)
        miter = ((previous[0] + nxt[0]) * scale, (previous[1] + nxt[1]) * scale)
        left.append((points[index][0] + miter[0], points[index][1] + miter[1]))
        right.append((points[index][0] - miter[0], points[index][1] - miter[1]))
    push(points[-1], normals[-1])
    return left, right


def draw_grid(
    canvas: tk.Canvas,
    origin_x: float,
    origin_y: float,
    cell: float,
    size: int,
) -> None:
    """Cienka siatka granic komórek. Wołać przed rysowaniem strzałek."""
    span = cell * size
    for index in range(size + 1):
        offset = index * cell
        canvas.create_line(
            origin_x + offset,
            origin_y,
            origin_x + offset,
            origin_y + span,
            fill=GRID_COLOR,
            width=1,
        )
        canvas.create_line(
            origin_x,
            origin_y + offset,
            origin_x + span,
            origin_y + offset,
            fill=GRID_COLOR,
            width=1,
        )
    _draw_coordinates(canvas, origin_x, origin_y, cell, size)


def _draw_coordinates(
    canvas: tk.Canvas,
    origin_x: float,
    origin_y: float,
    cell: float,
    size: int,
) -> None:
    if cell < 18 or origin_x < 14 or origin_y < 14:
        return
    font_size = max(7, min(9, int(cell * 0.16)))
    font = ("Segoe UI", font_size)
    gap = font_size + 3
    for col in range(size):
        canvas.create_text(
            origin_x + (col + 0.5) * cell,
            origin_y - gap,
            text=str(col),
            fill=COORD_COLOR,
            font=font,
        )
    for row in range(size):
        canvas.create_text(
            origin_x - gap,
            origin_y + (row + 0.5) * cell,
            text=str(row),
            fill=COORD_COLOR,
            font=font,
        )


def point_hits_body(x: float, y: float, body: dict) -> bool:
    limit = body["half"] + body["pad"]
    for (start_x, start_y), (end_x, end_y) in body["segments"]:
        if _segment_distance(x, y, start_x, start_y, end_x, end_y) <= limit:
            return True
    return _point_in_triangle((x, y), *body["triangle"])


def _segment_distance(
    px: float,
    py: float,
    ax: float,
    ay: float,
    bx: float,
    by: float,
) -> float:
    dx = bx - ax
    dy = by - ay
    length_sq = dx * dx + dy * dy
    if length_sq <= 1e-9:
        return ((px - ax) ** 2 + (py - ay) ** 2) ** 0.5
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / length_sq))
    qx = ax + t * dx
    qy = ay + t * dy
    return ((px - qx) ** 2 + (py - qy) ** 2) ** 0.5


def _point_in_triangle(
    point: tuple[float, float],
    a: tuple[float, float],
    b: tuple[float, float],
    c: tuple[float, float],
) -> bool:
    cross_ab = _cross(a, b, point)
    cross_bc = _cross(b, c, point)
    cross_ca = _cross(c, a, point)
    has_neg = cross_ab < 0 or cross_bc < 0 or cross_ca < 0
    has_pos = cross_ab > 0 or cross_bc > 0 or cross_ca > 0
    return not (has_neg and has_pos)


def _cross(
    origin: tuple[float, float],
    end: tuple[float, float],
    point: tuple[float, float],
) -> float:
    return (end[0] - origin[0]) * (point[1] - origin[1]) - (
        end[1] - origin[1]
    ) * (point[0] - origin[0])


class ArrowApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.board = None
        self.seed = 0
        self._error = None
        self._busy = False
        self._epoch = 0
        self._flashes: dict[int, int] = {}
        self._geom: tuple[float, float, float] | None = None
        self.show_grid = SHOW_GRID

        root.title("Arrow Puzzle")
        root.geometry(WINDOW_SIZE)
        root.minsize(520, 480)
        root.configure(bg=BACKGROUND)

        header = tk.Frame(root, bg=BACKGROUND)
        header.pack(side="top", fill="x", pady=(16, 6))

        controls = tk.Frame(header, bg=BACKGROUND)
        controls.pack()

        self.button = tk.Button(
            controls,
            text="Nowa plansza",
            command=self.new_board,
            bg="#161616",
            fg=ARROW_COLOR,
            activebackground="#2a2a2a",
            activeforeground=ARROW_COLOR,
            relief="flat",
            bd=0,
            padx=18,
            pady=8,
            font=("Segoe UI", 12),
            highlightthickness=0,
            cursor="hand2",
        )
        self.button.pack(side="left", padx=(0, 22))

        difficulty_box = tk.Frame(controls, bg=BACKGROUND)
        difficulty_box.pack(side="left")
        tk.Label(
            difficulty_box,
            text="Difficulty",
            bg=BACKGROUND,
            fg="#c8c8c8",
            font=("Segoe UI", 10),
        ).pack(anchor="w")
        self.difficulty = tk.IntVar(value=3)
        self.diff_caption = tk.Label(
            difficulty_box,
            text=f"3 — {LABELS[3]}",
            bg=BACKGROUND,
            fg="#8a8a8a",
            font=("Segoe UI", 9),
        )
        self.scale = tk.Scale(
            difficulty_box,
            from_=1,
            to=5,
            orient="horizontal",
            resolution=1,
            variable=self.difficulty,
            command=self._on_difficulty,
            bg=BACKGROUND,
            fg="#d0d0d0",
            troughcolor="#1a1a1a",
            activebackground="#3a3a3a",
            highlightthickness=0,
            bd=0,
            relief="flat",
            sliderrelief="flat",
            sliderlength=16,
            length=160,
            showvalue=False,
            font=("Segoe UI", 9),
        )
        self.scale.pack(anchor="w")
        self.diff_caption.pack(anchor="w")

        self.canvas = tk.Canvas(
            root,
            bg=BACKGROUND,
            highlightthickness=0,
            bd=0,
            cursor="arrow",
        )
        self.canvas.pack(side="top", fill="both", expand=True)
        self.canvas.bind("<Configure>", self._on_configure)
        self.canvas.bind("<Button-1>", self._on_click)
        root.bind_all("<KeyPress-g>", self._toggle_grid)
        root.bind_all("<KeyPress-G>", self._toggle_grid)

        self.new_board()

    def new_board(self, seed: int | None = None) -> None:
        if self._busy:
            return
        self._busy = True
        self.button.configure(state="disabled")
        try:
            if seed is None:
                seed = random.SystemRandom().randrange(0, 2**31)
            try:
                board = generate_board(seed, difficulty=int(self.difficulty.get()))
            except RuntimeError as error:
                print(error)
                self._error = "Nie udało się wygenerować planszy."
                if self.board is None:
                    self.redraw()
                return
            self._error = None
            self.seed = seed
            self._epoch += 1
            self._flashes.clear()
            self.board = board
            self.root.title(f"Arrow Puzzle - seed {seed}")
            self.redraw()
        finally:
            self._busy = False
            self.button.configure(state="normal")

    def _on_difficulty(self, _value: str | None = None) -> None:
        level = int(float(self.difficulty.get()))
        self.diff_caption.configure(text=f"{level} — {LABELS[level]}")

    def redraw(self) -> None:
        self.canvas.delete("all")
        width = self.canvas.winfo_width()
        height = self.canvas.winfo_height()
        if self.board is None:
            if self._error and width > 20 and height > 20:
                self.canvas.create_text(
                    width / 2,
                    height / 2,
                    text=self._error,
                    fill=ARROW_COLOR,
                    font=("Segoe UI", 16),
                )
            return
        if width < 20 or height < 20:
            return

        margin = 32
        cell = min(
            (width - 2 * margin) / self.board.size,
            (height - 2 * margin) / self.board.size,
        )
        if cell < 8:
            cell = min(width / self.board.size, height / self.board.size)
        board_px = cell * self.board.size
        origin_x = (width - board_px) / 2
        origin_y = (height - board_px) / 2
        self._geom = (origin_x, origin_y, cell)

        if self.show_grid:
            draw_grid(self.canvas, origin_x, origin_y, cell, self.board.size)

        for arrow in self.board.arrows:
            color = self._arrow_color(arrow.id)
            body = arrow_geometry(arrow, origin_x, origin_y, cell)
            self.canvas.create_polygon(
                *body["polygon"],
                fill=color,
                outline=color,
                joinstyle="round",
            )

        if not self.board.arrows:
            self.canvas.create_text(
                width / 2,
                height / 2,
                text="Rozwiązano!",
                fill=ARROW_COLOR,
                font=("Segoe UI", max(22, int(cell * 0.85))),
            )

    def _toggle_grid(self, _event: tk.Event | None = None) -> str:
        self.show_grid = not self.show_grid
        self.redraw()
        return "break"

    def _arrow_color(self, arrow_id: int) -> str:
        phase = self._flashes.get(arrow_id)
        if phase is not None and phase % 2 == 1:
            return BLOCKED_COLOR
        return ARROW_COLOR

    def _on_configure(self, event: tk.Event) -> None:
        if event.widget is self.canvas:
            self.redraw()

    def _on_click(self, event: tk.Event) -> None:
        if self._busy or self.board is None or self._geom is None:
            return
        origin_x, origin_y, cell = self._geom
        hit_id = None
        for arrow in reversed(self.board.arrows):
            body = arrow_geometry(arrow, origin_x, origin_y, cell)
            if point_hits_body(event.x, event.y, body):
                hit_id = arrow.id
                break
        if hit_id is None:
            return
        arrow = self.board.arrow_by_id(hit_id)
        if arrow is None:
            return
        if can_move(arrow, self.board):
            self._flashes.pop(arrow.id, None)
            self.board.remove(arrow.id)
            self.redraw()
            return
        self._start_flash(arrow.id)

    def _start_flash(self, arrow_id: int) -> None:
        epoch = self._epoch
        self._flashes[arrow_id] = 5
        self.redraw()
        self.root.after(120, lambda: self._flash_step(arrow_id, epoch))

    def _flash_step(self, arrow_id: int, epoch: int) -> None:
        if epoch != self._epoch or self.board is None:
            return
        if arrow_id not in self._flashes:
            return
        if self.board.arrow_by_id(arrow_id) is None:
            self._flashes.pop(arrow_id, None)
            self.redraw()
            return
        self._flashes[arrow_id] -= 1
        if self._flashes[arrow_id] <= 0:
            self._flashes.pop(arrow_id, None)
        self.redraw()
        if arrow_id in self._flashes:
            self.root.after(120, lambda: self._flash_step(arrow_id, epoch))


def main() -> None:
    root = tk.Tk()
    ArrowApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
