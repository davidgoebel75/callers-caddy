"""Beats einer ganzen Sequenz fuer das Sequenz-Detail (intern#164), ohne Qt.

Verbindet die Kartenzeilen mit der Rechnung aus `calc`:
- Startmarken "(Zero Box)", "(Zero Line)", "(Rotated)" sind keine getanzte Zeile (kein Wert).
- Die erste getanzte Zeile beginnt im Squared Set, wenn keine Startmarke davor steht.
- Singer: Ist die letzte Zeile der Schluss (Swing and Promenade ...), zaehlt sie als
  Swing + Promenade, unabhaengig vom Mapping. Fehlt der Schluss auf der Karte, kommt er
  (wie bei Square Flow) unsichtbar zur Summe dazu.
- Square Flow (Taminations) liefert je Zeile Beats. Sie ersetzen nur dynamische Werte in
  der Summe; weicht ein Wert bei einem festen Call um >= 2 Beats ab, gibt es einen Hinweis.
"""
from dataclasses import dataclass

from caddy.beats import calc
from caddy.choreo.mapping import END_FORMATION, SINGER_SCHLUSS

QT_FREE = True

SINGER_END = ("call_swing", "call_couples_promenade")
# App-Calls ohne eigene Bewegung: zaehlen nicht und machen die Zeile nicht "unbekannt"
NO_BEATS = frozenset({"filler_words"})


@dataclass(frozen=True)
class LineInfo:
    beats: calc.Beats          # Tabellenwert (ohne Square Flow), fuer das Etikett
    tam: float | None = None   # Square-Flow-Wert der Zeile, wenn vorhanden
    dynamic: bool = False      # Wert haengt vom Weg ab (Etikett "SF n" zeigen)
    warn: bool = False         # Square Flow weicht >= 2 Beats ab


@dataclass(frozen=True)
class SequenceInfo:
    lines: tuple               # je Kartenzeile LineInfo oder None (Startmarke)
    total: calc.Beats
    singer: bool
    light: str | None          # Ampel nur bei Singern


def is_singer(seq_type):
    return (seq_type or "").strip().lower().startswith("singer")


def is_marker(text):
    return (text or "").strip().lower() in END_FORMATION


def is_singer_end(text):
    t = (text or "").strip()
    return bool(SINGER_SCHLUSS.search(t)) and "wrong way" not in t.lower()


def sequence_info(table, calls, figures, seq_type="", tam_beats=None):
    """calls: Kartentexte; figures: {Kartentext: App-Calls (Haupt-Call + weitere Figuren)};
    tam_beats: Beats je Kartenzeile aus Square Flow (oder None)."""
    singer = is_singer(seq_type)
    tam_beats = list(tam_beats or [])
    first = next((i for i, t in enumerate(calls) if not is_marker(t)), None)
    has_marker = first is not None and first > 0
    last = len(calls) - 1
    lines, sums = [], []
    for i, text in enumerate(calls):
        if is_marker(text):
            lines.append(None)
            continue
        mapped = figures.get(text) or ()
        ents = [e for e in mapped if e not in NO_BEATS]
        if mapped and not ents:          # nur Fuellwoerter: kein Wert, kein Etikett
            lines.append(None)
            continue
        if singer and i == last and is_singer_end(text):
            ents = SINGER_END
        ss = (i == first and not has_marker)
        base = calc.line_beats(table, ents, text, squared_set=ss)
        tam = tam_beats[i] if i < len(tam_beats) else None
        dynamic = calc.DYNAMIC in base.flags
        warn = (not dynamic and tam is not None and calc.UNKNOWN not in base.flags
                and calc.warn_deviation(base, tam))
        lines.append(LineInfo(base, tam, dynamic, warn))
        sums.append(calc.line_beats(table, ents, text, squared_set=ss, tam_beats=tam)
                    if dynamic and tam is not None else base)
    if singer and calls and not is_singer_end(calls[-1]):
        sums.append(calc.line_beats(table, SINGER_END, "Swing and Promenade"))
    total = calc.sequence_beats(sums)
    light = calc.traffic_light(total) if singer and sums else None
    return SequenceInfo(tuple(lines), total, singer, light)
