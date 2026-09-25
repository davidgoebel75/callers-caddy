"""
Geteilte Button-Raster-Logik fuer Callers Caddy.

Verteilt n gleichartige Kacheln moeglichst gleichmaessig ueber eine Flaeche mit
dynamischem Zeilenumbruch: so viele Spalten wie moeglich (Kacheln bis zur
Mindestbreite schmaler), damit die Zeilenzahl minimal wird; danach fuellt jede
Zeile die volle Breite gleichmaessig aus. Die Kachelhoehe wird gedeckelt und die
Matrix vertikal zentriert.

Genutzt vom Jump-Markers-Widget (BL-185) und vom To-Call-Widget (BL-199), damit
beide dieselbe Anordnung teilen (geteilter Code statt Duplikat).
"""

import math


def distribute(n: int, rows: int) -> list:
    """Verteilt n Elemente moeglichst gleichmaessig auf rows Zeilen.

    Vollere Zeilen zuerst (7 auf 2 -> [4, 3]).
    """
    if rows <= 0:
        return [n]
    base, rem = divmod(n, rows)
    return [base + 1 if i < rem else base for i in range(rows)]


def _max_cols(inner_w: float, min_w: int, gap: int) -> int:
    """Hoechstens so viele Spalten, dass jede Kachel min_w breit bleibt."""
    return max(1, int((inner_w + gap) // (min_w + gap)))


def min_matrix_height(n: int, avail_w: int, *, margin: int = 8, gap: int = 6,
                      min_w: int = 78, min_h: int = 30) -> int:
    """Hoehe (inkl. Rand), die n Kacheln mindestens brauchen: maximal viele
    Spalten, jede Kachel auf min_h. Passt die Flaeche nicht, muss der
    Aufrufer scrollen (intern#114)."""
    if n <= 0:
        return 0
    inner_w = max(1, avail_w - 2 * margin)
    cols = min(n, _max_cols(inner_w, min_w, gap))
    rows = math.ceil(n / cols)
    return rows * min_h + (rows - 1) * gap + 2 * margin


def compute_cells(n: int, avail_w: int, avail_h: int, *,
                  margin: int = 8, gap: int = 6,
                  min_w: int = 78, min_h: int = 30, max_h: int = 54,
                  target_ratio: float = None):
    """Berechnet die Kachel-Geometrien.

    Args:
        n: Anzahl Kacheln.
        avail_w/avail_h: verfuegbare Widget-Flaeche (inkl. spaeterem Rand).
        margin: Rand um die Matrix.
        gap: Abstand zwischen Kacheln.
        min_w: Mindestbreite (steuert die maximale Spaltenzahl).
        min_h/max_h: Grenzen der Kachelhoehe.
        target_ratio: angestrebtes Seitenverhaeltnis Breite:Hoehe (z. B. 2.0).
            Ist es gesetzt, wird die Spaltenzahl so gewaehlt, dass die Kacheln
            diesem Verhaeltnis am naechsten kommen (und ihre Hoehe wird auf
            breite/ratio gedeckelt -> nie hochkantiger als das Verhaeltnis).
            Ohne target_ratio: maximal viele Spalten (minimale Zeilenzahl).

    Returns:
        (cols, rows, cells) — cells ist eine Liste von (x, y, w, h) in
        Widget-Koordinaten, ein Eintrag je Element in Reihenfolge.
    """
    if n <= 0:
        return 0, 0, []

    inner_w = max(1, avail_w - 2 * margin)
    inner_h = max(1, avail_h - 2 * margin)

    def _cell_w(cols):
        return (inner_w - (cols - 1) * gap) / cols

    def _cell_h(rows):
        return (inner_h - (rows - 1) * gap) / rows

    cols_max = _max_cols(inner_w, min_w, gap)

    if target_ratio and target_ratio > 0:
        # Spaltenzahl so waehlen, dass Breite:Hoehe dem Zielverhaeltnis am
        # naechsten kommt (Gleichstand -> weniger leere Zellen, dann groesser).
        # Nur Spaltenzahlen, bei denen die Kacheln min_h erreichen -- sonst
        # wuerde die Hoehe unten geklemmt und die Matrix liefe ueber avail_h
        # hinaus, obwohl mehr Spalten gepasst haetten (intern#114).
        best = None
        for c in range(1, n + 1):
            r = math.ceil(n / c)
            cw = _cell_w(c)
            if cw < min_w and c > 1:
                continue
            ch = _cell_h(r)
            if ch < min_h:
                continue
            score = (abs(cw / ch - target_ratio), c * r - n, -cw)
            if best is None or score < best[0]:
                best = (score, c, r, cw, ch)
        if best is None:
            # Passt bei keiner Spaltenzahl: maximal viele Spalten, Kacheln auf
            # min_h. Die Matrix wird dann hoeher als avail_h, der Aufrufer
            # scrollt (frueher: TypeError beim Entpacken von None).
            cols = min(n, cols_max)
            rows = math.ceil(n / cols)
            best = (None, cols, rows, _cell_w(cols), _cell_h(rows))
        _, cols, rows, cw, ch = best
        # Hoehe auf breite/ratio deckeln -> Kacheln bleiben "quer" (>= Ratio).
        btn_h = int(max(min_h, min(max_h, ch, cw / target_ratio)))
    else:
        # So viele Spalten wie moeglich (Kacheln bis Mindestbreite schmaler) ->
        # minimale Zeilenzahl.
        cols = min(n, cols_max)
        rows = math.ceil(n / cols)
        btn_h = int(max(min_h, min(max_h, _cell_h(rows))))

    row_counts = distribute(n, rows)
    matrix_h = rows * btn_h + (rows - 1) * gap
    origin_y = margin + max(0, (inner_h - matrix_h) // 2)

    cells = []
    for r in range(rows):
        count = row_counts[r]
        # Jede Zeile fuellt die volle Breite gleichmaessig aus.
        btn_w = int((inner_w - (count - 1) * gap) / count)
        y = origin_y + r * (btn_h + gap)
        for c in range(count):
            x = margin + c * (btn_w + gap)
            cells.append((x, y, btn_w, btn_h))
    return cols, rows, cells
