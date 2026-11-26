"""Song-Katalog: Square-Dance-Songs aus einer externen Quelldatei als Referenz (intern#126).

Der Katalog (ca. 9.000 Songs) liegt als CSV unter
`music-extended-data/music_extended_data.csv` und liefert zu Titel, Label und
Plattennummer die kanonische Schreibweise plus Metadaten (Typ, Caller, Genre,
Original Artist, Erscheinungsjahr).

Er ist eine weitere Datenquelle fuer den vorhandenen Abgleich — die Bewertung
selbst kommt unveraendert aus song_match.score_match ('record'-Profil). Wer
Katalogdaten automatisch uebernimmt (Einzelimport), tut das nur ab der Stufe
"sicher" (IMPORT_MIN_SCORE); alles darunter bleibt Vorschlag (Potential).

Aktualisiert wird die CSV von aussen: tools/update_song_catalog.py (aufgerufen
nach jedem Update der Quelldatei) schiebt sie per PR ins Repo.

GUI-frei (wie song_match), damit eigenstaendig testbar. Geladen wird lazy und
einmal pro Datei-Stand (Pfad + mtime), die Indexe liegen im Speicher.
"""

from __future__ import annotations

import csv
import difflib
import os
import re
from dataclasses import dataclass, field
from typing import Optional

import song_match

CATALOG_DIR = "music-extended-data"
CATALOG_FILE = "music_extended_data.csv"
COLUMNS = ["Song Title", "Label", "Label Code", "Number", "Type", "Caller",
           "Genre", "Original Artist", "Released"]

# Ab hier gilt ein Katalogtreffer als "sicher" (= song_match.confidence_word) und
# darf beim Import ohne Rueckfrage uebernommen werden. Im 'record'-Profil
# erreicht das praktisch nur ein Treffer mit passendem Label UND Nummer.
IMPORT_MIN_SCORE = 90

# Fuzzy-Stufe fuer Titel ohne exakten Treffer (wie bisher im Potential-Import)
FUZZY_CUTOFF = 0.80

_YEAR = re.compile(r"\b(\d{4})\b")


@dataclass(frozen=True)
class CatalogEntry:
    title: str
    label_name: str = ""
    label_code: str = ""
    number: str = ""
    type: str = ""
    caller: str = ""
    genre: str = ""
    original_artist: str = ""
    release_year: str = ""

    @property
    def label_field(self) -> str:
        """Labeltext in App-Form (songs.label): 'Kuerzel Nummer'."""
        code = self.label_code or self.label_name
        return f"{code} {self.number}".strip() if self.number else code

    @property
    def genres(self) -> list:
        return [g.strip() for g in self.genre.split(",") if g.strip()]

    @property
    def is_singing(self) -> bool:
        return "singing" in self.type.lower()

    @property
    def is_patter(self) -> bool:
        t = self.type.lower()
        return "patter" in t or "hoedown" in t


@dataclass
class CatalogMatch:
    entry: CatalogEntry
    score: int
    reasons: list = field(default_factory=list)

    @property
    def is_sure(self) -> bool:
        return self.score >= IMPORT_MIN_SCORE


def _fix_mojibake(s: str) -> str:
    """Repariert doppelt kodiertes UTF-8 aus der Quelldatei ('Weâ€™re' -> 'We’re').
    Nur wenn typische Muster auftauchen und die Rueckwandlung sauber klappt."""
    if not s or ("â" not in s and "Ã" not in s):
        return s
    try:
        return s.encode("cp1252").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return s


def _number_key(number: str) -> str:
    return str(number or "").strip().lstrip("0").lower()


class SongCatalog:
    """Katalog im Speicher mit Indexen nach Titel und Plattennummer."""

    def __init__(self, entries: list, path: str = ""):
        self.path = path
        self.entries = list(entries)
        self._by_title: dict = {}
        self._by_number: dict = {}
        for e in self.entries:
            self._by_title.setdefault(song_match.catalog_title_key(e.title), []).append(e)
            if e.number:
                self._by_number.setdefault(_number_key(e.number), []).append(e)
        self._title_keys = list(self._by_title)

    def __len__(self) -> int:
        return len(self.entries)

    # ---- Laden ----

    @classmethod
    def from_csv(cls, path: str) -> "SongCatalog":
        """Liest eine Katalog-CSV (Spalten wie COLUMNS). Zeilen ohne Titel
        werden uebersprungen; das Jahr wird aus 'Released' gezogen."""
        entries = []
        with open(path, newline="", encoding="utf-8", errors="replace") as f:
            for raw in csv.DictReader(f):
                row = {k: _fix_mojibake(v or "") for k, v in raw.items() if k}
                title = (row.get("Song Title") or "").strip()
                if not title:
                    continue
                year = _YEAR.search((row.get("Released") or "").strip())
                entries.append(CatalogEntry(
                    title=title,
                    label_name=(row.get("Label") or "").strip(),
                    label_code=(row.get("Label Code") or "").strip(),
                    number=(row.get("Number") or "").strip(),
                    type=(row.get("Type") or "").strip(),
                    caller=(row.get("Caller") or "").strip(),
                    genre=(row.get("Genre") or "").strip(),
                    original_artist=(row.get("Original Artist") or "").strip(),
                    release_year=year.group(1) if year else "",
                ))
        return cls(entries, path)

    # ---- Abfragen ----

    def by_title(self, title: str) -> list:
        """Exakte Titeltreffer (nach catalog_title_key)."""
        return list(self._by_title.get(song_match.catalog_title_key(title), []))

    def by_title_fuzzy(self, title: str, n: int = 3,
                       cutoff: float = FUZZY_CUTOFF) -> tuple:
        """Fuzzy-Titeltreffer: (Eintraege, Aehnlichkeit des besten)."""
        key = song_match.catalog_title_key(title)
        close = difflib.get_close_matches(key, self._title_keys, n=n, cutoff=cutoff)
        if not close:
            return ([], 0.0)
        hits = [e for k in close for e in self._by_title[k]]
        return (hits, difflib.SequenceMatcher(None, key, close[0]).ratio())

    def by_label_number(self, label_field: str) -> list:
        """Eintraege, deren Label (Name ODER Kuerzel) UND Nummer zum Labeltext
        eines Songs passen (song_match.label_number_matches, intern#108)."""
        _name, num = song_match.split_label_number(label_field)
        if not num:
            return []
        return [e for e in self._by_number.get(_number_key(num), [])
                if song_match.label_number_matches(
                    label_field, e.label_name, e.label_code, e.number)]

    def unique_label_for_title(self, title: str) -> str:
        """Labeltext ('Kuerzel Nummer') eines Titels, wenn der Katalog ihn
        GENAU EINER Aufnahme zuordnet, sonst ''. Fuer Suchen ohne Song-Label
        (Ceder, Krabbelkiste): bei mehreren Aufnahmen desselben Titels waere
        jede Wahl geraten — und eine falsche Nummer wertet Treffer ab."""
        labels = {e.label_field for e in self.by_title(title) if e.number}
        return labels.pop() if len(labels) == 1 else ""

    def identify(self, title: str, label_field: str = "") -> Optional[CatalogMatch]:
        """Bester Katalogeintrag fuer (Titel, Labeltext) mit Score/Begruendung.

        Kandidaten: Label+Nummer, exakter Titel, Fuzzy-Titel. Bewertet wird mit
        song_match.score_match ('record'), Label gegen Kuerzel UND Namen (der
        bessere zaehlt). None, wenn nichts ueber song_match.MIN_SCORE liegt.
        """
        cands, seen = [], set()
        fuzzy, _sim = self.by_title_fuzzy(title) if title else ([], 0.0)
        for e in (self.by_label_number(label_field) + self.by_title(title) + fuzzy):
            if id(e) not in seen:
                seen.add(id(e))
                cands.append(e)
        want_name, want_num = song_match.split_label_number(label_field)
        best = None
        for e in cands:
            scored = max(
                (song_match.score_match(title, want_name, want_num,
                                        e.title, lbl, e.number, profile="record")
                 for lbl in {e.label_code, e.label_name} if lbl),
                default=song_match.score_match(title, want_name, want_num,
                                               e.title, "", e.number, profile="record"),
                key=lambda sw: sw[0])
            if best is None or scored[0] > best.score:
                best = CatalogMatch(entry=e, score=max(0, min(100, scored[0])),
                                    reasons=scored[1])
        if best is None or best.score < song_match.MIN_SCORE:
            return None
        return best


_BRACKET_PART = re.compile(r"[\(\[][^\)\]]*[\)\]]")


def canonical_title(parsed_title: str, entry_title: str) -> str:
    """Katalog-Schreibweise, aber Klammer-Zusaetze aus dem Dateinamen bleiben
    ('... (Vocal)'): sonst haetten Haupt- und Vocal-Spur denselben Titel."""
    have = {song_match.compact_title(b) for b in _BRACKET_PART.findall(entry_title or "")}
    extra = [b for b in _BRACKET_PART.findall(parsed_title or "")
             if song_match.compact_title(b) not in have]
    return " ".join([entry_title, *extra]).strip()


# ---------------------------------------------------------------------------
# Fundort + Cache
# ---------------------------------------------------------------------------

def catalog_path(app_dir: str = "") -> str:
    """Pfad der Katalog-CSV oder '' wenn keine da ist.

    Zuerst der App-Ordner (Release: neben der EXE), dann der Repo-Ordner neben
    src/ (Dev-Start aus 2_Test ohne eigene Kopie)."""
    candidates = []
    if app_dir:
        candidates.append(os.path.join(app_dir, CATALOG_DIR, CATALOG_FILE))
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    candidates.append(os.path.join(repo_root, CATALOG_DIR, CATALOG_FILE))
    for c in candidates:
        if os.path.isfile(c):
            return c
    return ""


_cache: dict = {}   # path -> (mtime, SongCatalog)


def get_catalog(app_dir: str = "") -> Optional[SongCatalog]:
    """Der Katalog (lazy geladen, neu nur bei geaenderter Datei) oder None."""
    path = catalog_path(app_dir)
    if not path:
        return None
    try:
        mtime = os.path.getmtime(path)
        cached = _cache.get(path)
        if cached and cached[0] == mtime:
            return cached[1]
        cat = SongCatalog.from_csv(path)
    except (OSError, csv.Error, UnicodeError) as e:
        print(f"[SongCatalog] Katalog nicht lesbar ({path}): {e}")
        return None
    _cache[path] = (mtime, cat)
    return cat


def label_hint(title: str, label_field: str, app_dir: str = "") -> str:
    """Labeltext fuer eine Suche: das eigene Label, sonst das eindeutige Label
    aus dem Katalog, sonst ''. Nie eine Ausnahme (Suche geht ohne weiter)."""
    if (label_field or "").strip():
        return label_field
    try:
        catalog = get_catalog(app_dir)
        return catalog.unique_label_for_title(title) if catalog and title else ""
    except Exception:  # noqa: BLE001
        return ""
