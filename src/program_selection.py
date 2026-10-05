"""Tanzprogramm-Wahl: Programm-Band, Programm-Reihe und Figuren-Auswahl (intern#143).

Qt-frei. Hauptfenster, Programm-Auswahldialog und Sequenzen-Widget holen sich
hier dieselbe Regel, statt sie je selbst zu rechnen.

`programs` ist immer die Liste aus SongDatabase.get_all_dance_programs():
[(id, code, label, sort_order, target_duration_min, sequence_limit_to)].
Das Band eines Programms ist der Ganzzahlteil von sequence_limit_to
(z. B. 30.999999 -> 30); Programme ohne Limit haben kein Band.
"""


def band_of(limit_to):
    """Band zu einem sequence_limit_to-Wert, None ohne Limit."""
    return int(limit_to) if limit_to is not None else None


def bands_for(programs, pids):
    """Band-Menge der gewaehlten Programme. Leer/None -> None (= kein
    Programm-Filter, alle Sequenzen)."""
    if not pids:
        return None
    limits = {r[0]: r[5] for r in programs}
    bands = {band_of(limits[p]) for p in pids if limits.get(p) is not None}
    return bands or None


def top_program(programs, pids):
    """Oberstes (hoechstes Band) der gewaehlten Programme -> (program_id, code).
    Liefert die Basis fuer die Ziel-Tanzdauer. Leer -> (None, '')."""
    rows = {r[0]: r for r in programs}
    best = None  # (band, id, code)
    for p in pids or []:
        r = rows.get(p)
        if r is None:
            continue
        band = r[5] if r[5] is not None else -1
        if best is None or band > best[0]:
            best = (band, p, r[1])
    if best is None:
        return None, ""
    return best[1], best[2]


def limit_for_code(programs, code):
    """sequence_limit_to des Programms mit diesem Code, sonst None."""
    for r in programs:
        if r[1] == code:
            return r[5]
    return None


def primary_program_by_band(programs):
    """Band -> ID des regulaeren Programms (kleinster sort_order im Band), damit
    die Kaskade nicht versehentlich eine Class-Variante anhakt."""
    best = {}  # band -> (pid, sort_order)
    for r in programs:
        band = band_of(r[5])
        if band is not None and (band not in best or r[3] < best[band][1]):
            best[band] = (r[0], r[3])
    return {band: pid for band, (pid, _so) in best.items()}


def predecessor_bands(all_bands, band):
    """Baender unterhalb von `band` in derselben Programm-Reihe (Issue #64).

    Alte Reihe (Basics 10/20 + krumme Baender 29/39/49) und 2026er/obere Reihe
    (runde Baender ab 30) sind getrennt. Die 2026er-Reihe zieht KEINE Basics und
    kein altes MS/PL/A1 mit — Mainstream 2026 (Band 30) hat die uebrig
    gebliebenen Basic-Calls bereits absorbiert.
    """
    if band is None:
        return []
    old_line = [b for b in all_bands if b < 30 or b % 10 != 0]
    new_line = [b for b in all_bands if b >= 30 and b % 10 == 0]
    line = old_line if (band < 30 or band % 10 != 0) else new_line
    return sorted(b for b in line if b < band)


def calls_in_bands(all_calls, bands):
    """Figuren passend zu den gewaehlten Baendern. Nur Zeilen, deren Band
    gewaehlt ist; eine Figur erscheint genau EINMAL, im NIEDRIGSTEN gewaehlten
    Band. Ohne Programmwahl -> alle Figuren.

    all_calls = [(name, entity_id, to), ...] nach Teaching-Order sortiert,
    Rueckgabe ebenso.
    """
    if not bands:
        return list(all_calls)
    best = {}  # entity_id -> (name, eid, to) im niedrigsten gewaehlten Band
    for name, eid, to in all_calls:
        if to is None or band_of(to) not in bands:
            continue
        if eid not in best or to < best[eid][2]:
            best[eid] = (name, eid, to)
    return sorted(best.values(), key=lambda r: r[2])
