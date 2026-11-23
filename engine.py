"""Logiczny model planszy Arrow Out oraz solver.

Strzałka jest ścieżką od ogona do grotu. Segmenty są prostopadłe.
Kierunek wyjazdu wynika wyłącznie z ostatniego segmentu i jest prostą
do krawędzi planszy. Renderer nie należy do tego modułu.
"""

from __future__ import annotations

from dataclasses import dataclass

DIRECTIONS = ("UP", "DOWN", "LEFT", "RIGHT")

DIRECTION_DELTA = {
    "UP": (-1, 0),
    "DOWN": (1, 0),
    "LEFT": (0, -1),
    "RIGHT": (0, 1),
}

OPPOSITE = {
    "UP": "DOWN",
    "DOWN": "UP",
    "LEFT": "RIGHT",
    "RIGHT": "LEFT",
}

DELTA_TO_DIRECTION = {step: name for name, step in DIRECTION_DELTA.items()}

DEFAULT_SIZE = 12


@dataclass(frozen=True)
class Arrow:
    id: int
    cells: tuple[tuple[int, int], ...]

    def __post_init__(self) -> None:
        if len(self.cells) < 2:
            raise ValueError("Strzałka musi zajmować co najmniej 2 komórki")
        if len(set(self.cells)) != len(self.cells):
            raise ValueError("Strzałka przecina samą siebie")
        previous: str | None = None
        for index in range(1, len(self.cells)):
            delta = (
                self.cells[index][0] - self.cells[index - 1][0],
                self.cells[index][1] - self.cells[index - 1][1],
            )
            direction = DELTA_TO_DIRECTION.get(delta)
            if direction is None:
                raise ValueError("Segment nie jest krokiem o jedną komórkę")
            if previous is not None and direction == OPPOSITE[previous]:
                raise ValueError("Natychmiastowy zawrót")
            previous = direction

    @property
    def head(self) -> tuple[int, int]:
        return self.cells[-1]

    @property
    def tail(self) -> tuple[int, int]:
        return self.cells[0]

    @property
    def direction(self) -> str:
        """Kierunek grotu, zgodny z ostatnim segmentem."""
        delta = (
            self.cells[-1][0] - self.cells[-2][0],
            self.cells[-1][1] - self.cells[-2][1],
        )
        return DELTA_TO_DIRECTION[delta]


class Board:
    """Plansza. Lista `arrows` jest w kolejności umieszczania."""

    def __init__(self, size: int = DEFAULT_SIZE) -> None:
        if size < 2:
            raise ValueError("Plansza jest za mała")
        self.size = size
        self.arrows: list[Arrow] = []
        self.occupied: dict[tuple[int, int], int] = {}

    def copy(self) -> Board:
        clone = Board(self.size)
        clone.arrows = list(self.arrows)
        clone.occupied = dict(self.occupied)
        return clone

    def arrow_by_id(self, arrow_id: int) -> Arrow | None:
        for arrow in self.arrows:
            if arrow.id == arrow_id:
                return arrow
        return None

    def arrow_at(self, cell: tuple[int, int]) -> Arrow | None:
        arrow_id = self.occupied.get(cell)
        if arrow_id is None:
            return None
        return self.arrow_by_id(arrow_id)

    def add(self, arrow: Arrow) -> None:
        for cell in arrow.cells:
            row, col = cell
            if not (0 <= row < self.size and 0 <= col < self.size):
                raise ValueError(f"Komórka poza planszą: {cell}")
            if cell in self.occupied:
                raise ValueError(f"Nakładanie w komórce {cell}")
        for cell in arrow.cells:
            self.occupied[cell] = arrow.id
        self.arrows.append(arrow)

    def remove(self, arrow_id: int) -> Arrow | None:
        arrow = self.arrow_by_id(arrow_id)
        if arrow is None:
            return None
        self.arrows = [item for item in self.arrows if item.id != arrow_id]
        for cell in arrow.cells:
            self.occupied.pop(cell, None)
        return arrow


def bend_count(cells: tuple[tuple[int, int], ...] | list[tuple[int, int]]) -> int:
    bends = 0
    previous: str | None = None
    for index in range(1, len(cells)):
        delta = (
            cells[index][0] - cells[index - 1][0],
            cells[index][1] - cells[index - 1][1],
        )
        direction = DELTA_TO_DIRECTION[delta]
        if previous is not None and direction != previous:
            bends += 1
        previous = direction
    return bends


def ray_cells(row: int, col: int, direction: str, size: int) -> list[tuple[int, int]]:
    """Komórki za punktem, w linii prostej, aż do krawędzi."""
    d_row, d_col = DIRECTION_DELTA[direction]
    cells: list[tuple[int, int]] = []
    row += d_row
    col += d_col
    while 0 <= row < size and 0 <= col < size:
        cells.append((row, col))
        row += d_row
        col += d_col
    return cells


def exit_cells(arrow: Arrow, size: int) -> list[tuple[int, int]]:
    """Droga wyjazdu: prosta od grotu do krawędzi, bez komórki grotu."""
    row, col = arrow.head
    return ray_cells(row, col, arrow.direction, size)


def can_move(arrow: Arrow, board: Board) -> bool:
    """Czy droga od grotu do krawędzi jest wolna od innych strzałek.

    Komórki samej strzałki nie blokują jej wyjazdu.
    """
    for cell in exit_cells(arrow, board.size):
        owner = board.occupied.get(cell)
        if owner is not None and owner != arrow.id:
            return False
    return True


def solve_board(board: Board) -> tuple[list[int], str | None]:
    """Usuwa kolejne dostępne strzałki i zwraca kolejność oraz błąd.

    Wybór przy kilku ruchach to najmniejszy identyfikator, więc wynik jest
    powtarzalny. Usunięcie strzałki nigdy nie dodaje nowej blokady, więc
    zachłanny wybór znajduje rozwiązanie, jeżeli ono istnieje.
    """
    work = board.copy()
    order: list[int] = []
    while work.arrows:
        movable = [arrow for arrow in work.arrows if can_move(arrow, work)]
        if not movable:
            return order, "Nie można usunąć wszystkich strzałek."
        chosen = min(movable, key=lambda arrow: arrow.id)
        order.append(chosen.id)
        work.remove(chosen.id)
    return order, None
