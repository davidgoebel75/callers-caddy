"""Playlist-Datei lesen, parsen und schreiben (intern#140).

Eine Zeile je Eintrag: `MODUS ZAEHLER TITEL`, der Zaehler ist `N` oder `N:CUT`
(BL-164, Cut in Beats). Altformat ohne Zaehler: `MODUS TITEL`. Das Modul kennt
keine DB; den Titel nachschlagen die Aufrufer.
"""
import re
from dataclasses import dataclass
from typing import Iterable

QT_FREE = True

_COUNTER = re.compile(r"\d+(:\d+)?")


@dataclass(frozen=True)
class PlaylistLine:
    play_mode: str      # "P" oder "S"
    loop_count: int     # 0 = Altformat ohne Zaehler
    loop_cut: int       # Beats, 0 = kein Cut
    name: str           # Titel oder Dateiname zum Nachschlagen


def read_text_lines(path: str) -> list[str]:
    """utf-8, bei UnicodeDecodeError cp1252. OSError geht an den Aufrufer."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.readlines()
    except UnicodeDecodeError:
        with open(path, "r", encoding="cp1252") as f:
            return f.readlines()


def parse_lines(lines: Iterable[str], *, with_cut: bool = True) -> list[PlaylistLine]:
    """Zeilen zu Eintraegen. Leere und Einwort-Zeilen fallen weg.

    with_cut=False erkennt nur den Zaehler `N`; bei `N:CUT` bleibt der Token im
    Namen haengen. So las load_permanent_filters schon vorher (Verhalten bleibt,
    siehe issues/src-architektur-abschluss/abweichungen-fuer-david.md)."""
    out = []
    for line in lines:
        parts = line.strip().split(" ", 2)
        if len(parts) < 2:
            continue
        mode = parts[0].upper()
        if mode not in ("P", "S"):
            mode = "P"
        count = cut = 0
        if len(parts) == 3 and (_COUNTER.fullmatch(parts[1]) if with_cut
                                else parts[1].isdigit()):
            cnt = parts[1].split(":")
            count = int(cnt[0])
            cut = int(cnt[1]) if len(cnt) > 1 else 0
            name = parts[2]
        elif len(parts) == 3:
            name = parts[1] + " " + parts[2]
        else:
            name = parts[1]
        out.append(PlaylistLine(mode, count, cut, name))
    return out


def read(path: str, *, with_cut: bool = True) -> list[PlaylistLine]:
    return parse_lines(read_text_lines(path), with_cut=with_cut)


def write(path: str, entries: Iterable[PlaylistLine]) -> None:
    """utf-8; der Cut steht nur bei cut > 0 im Zaehler (altes Format bleibt gueltig)."""
    with open(path, "w", encoding="utf-8") as f:
        for e in entries:
            tok = f"{e.loop_count}:{e.loop_cut}" if e.loop_cut > 0 else f"{e.loop_count}"
            f.write(f"{e.play_mode} {tok} {e.name}\n")
