# Arrow Puzzle

Prosty generator zagadek Arrow Out dla Windows 10/11. Program działa lokalnie, bez internetu i bez dodatkowych bibliotek.

## Uruchomienie

Dwuklik `start.bat` albo w terminalu:

```
py -3 main.py
```

Potrzebny jest Python 3.11 lub nowszy z Tkinter (standardowa instalacja z python.org).

## Jak grać

Kliknij strzałkę. Jeśli komórki od grotu do krawędzi planszy są puste, strzałka znika. Jeśli coś stoi na drodze, miga na czerwono. Usuń wszystkie strzałki.

**Nowa plansza** losuje kolejną rozwiązywalną zagadkę. Seed jest w tytule okna. Ten sam seed odtwarza ten sam układ:

```
py -3 -c "from generator import generate_board; print(generate_board(12345).arrows)"
```

## Testy

```
py -3 test_logic.py
```
