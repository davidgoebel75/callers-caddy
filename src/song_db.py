"""
Song- und Lokation-Datenbank (SQLite)
======================================
Zentrale Persistenzschicht fuer Song-, Lokation- und Historie-Modell.

Song-Schema gemaess Lastenheft (docs/02_songverwaltung.md + docs/07_datenmodell.md):
  - filename      TEXT  NOT NULL UNIQUE  (technisch, unveraenderlich)
  - title         TEXT                   (editierbar, Import-Default = Dateiname)
  - label         TEXT                   (Plattenlabel)
  - quality       INTEGER                (Qualitaetsskala 0-10)
  - base_bpm      REAL                   (Basis-BPM, manuell oder Auto)
  - standard_tempo REAL                  (Song-Tempo-Faktor, Default 1.0 = 100%)
  - pitch         REAL                   (Halbtoene, Default 0.0)
  - volume        REAL                   (Lautstaerke-Faktor, Default 1.0)
  - loop_in       REAL                   (Loop-In in Sekunden, Default 0.0)
  - loop_out      REAL                   (Loop-Out in Sekunden, 0.0 = Songende)
  - lyrics_file   TEXT                   (Dateiname der zugehoerigen Lyrics)
  - is_pattern    INTEGER                (1 = als Pattern nutzbar, Default 1)
  - is_singing    INTEGER                (1 = als Singing Call nutzbar, Default 1)

Lokation-Schema (generalisiert aus Club):
  - id            INTEGER PRIMARY KEY
  - name          TEXT NOT NULL UNIQUE   (z.B. "SquareBreakers", "Sommer-Special 2026")

Abspielhistorie (Drei-Schichten-Architektur):
  Schicht 1 — play_history: Unveraenderliches Protokoll (nur INSERTs)
  Schicht 2 — song_location_stats: Materialisierter Cache (last_played, play_count)
  Schicht 3 — On-the-Fly: julianday('now') - julianday(last_played) fuer Empfehlungen

Design-Entscheidungen:
  - Nur Dateiname gespeichert, KEINE absoluten Pfade (portabel)
  - Gemeinsame DB-Datei fuer alle Entitaeten (callers_caddy.db)
  - Alle Methoden sind synchron (SQLite ist fuer diesen Anwendungsfall schnell genug)
  - get_or_create() fuer den Import-Workflow: existiert ein Song schon, wird er geladen
  - is_pattern/is_singing als getrennte Booleans: performant filterbar (WHERE is_pattern = 1)
  - Lokationen sind generalisierte Kontexte (Club oder Special — Unterscheidung nur per Name)
  - Cache-Update bei jedem Play: INSERT play_history + UPSERT song_location_stats
  - Cache kann jederzeit aus play_history regeneriert werden (Datenintegritaet)
"""

import sqlite3
import os
import sys
import re
from dataclasses import dataclass
from typing import Optional, List

from song_db_potential import PotentialMixin
from song_db_schema import SchemaMixin
from song_db_sequences import SequencesMixin
import song_types


def _chunked(seq, size: int = 900):
    """Teilt eine Sequenz in Bloecke <= size (SQLite-Variablengrenze)."""
    seq = list(seq)
    for i in range(0, len(seq), size):
        yield seq[i:i + size]


def _safe_print(text: str):
    """Wie print(), aber bricht nie an Zeichen ab, die das Konsolen-Encoding
    nicht darstellen kann (z.B. '➔' auf einer cp1252-Windows-Konsole).

    Hintergrund: Migrations-SQL kann Unicode-Zeichen enthalten. Auf einer
    nicht-UTF-8-Konsole wirft print() sonst UnicodeEncodeError und liess
    frueher den Build (clean_db.py) abbrechen. Unkodierbare Zeichen werden
    hier durch '?' ersetzt statt zu crashen.
    """
    enc = getattr(sys.stdout, "encoding", None) or "utf-8"
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode(enc, errors="replace").decode(enc, errors="replace"))


@dataclass
class Song:
    """Fachliches Song-Objekt."""
    id: Optional[int] = None
    filename: str = ""
    title: str = ""
    artist: str = ""
    label: str = ""
    quality: int = 0
    base_bpm: float = 0.0
    standard_tempo: float = 1.0
    pitch: float = 0.0
    volume: float = 1.0
    loop_in: float = 0.0
    loop_out: float = 0.0
    loop_offset_ms: float = 0.0
    lyrics_file: str = ""
    is_pattern: int = 1
    is_singing: int = 1
    date_added: str = ""
    err: int = 0


@dataclass
class Location:
    """Fachliches Lokation-Objekt (Club oder Special).

    Typ-Unterscheidung erfolgt nur ueber den Namen:
      - "SquareBreakers" = dauerhafter Club
      - "Sommer-Special 2026-03-08" = einmaliges Event (Datum im Namen)
    """
    id: Optional[int] = None
    name: str = ""
    dance_program_id: Optional[int] = None    # BL-084
    temp_tempo: Optional[float] = None        # BL-086  (Prozent, 100 = neutral)
    target_bpm: Optional[float] = None        # BL-144  (Ziel-BPM, None/0 = leer)
    tempo_mode: Optional[str] = None          # BL-144  ('percent'|'bpm', None = percent)
    planned_tips: Optional[int] = None        # Geplante Anzahl Tips pro Abend
    break_minutes: Optional[int] = None       # Standard-Pausendauer (Min., None = 5)
    schedules: Optional[str] = None           # BL-178: JSON-Liste von Termin-Tripeln
    shared_history_with: Optional[int] = None # BL-178 P2: Senke der geteilten History (NULL=eigene)
    weekdays: Optional[str] = None            # BL-178 (alt): CSV der Wochentage — Lese-Fallback
    time_from: Optional[str] = None           # BL-178 (alt): "HH:MM" — Lese-Fallback
    time_to: Optional[str] = None             # BL-178 (alt): "HH:MM" — Lese-Fallback

    # Standard-Pausendauer, wenn nichts gesetzt ist (Minuten)
    DEFAULT_BREAK_MINUTES = 5

    # BL-144: Tempo-Modi
    TEMPO_MODE_PERCENT = "percent"
    TEMPO_MODE_BPM = "bpm"

    @property
    def effective_tempo_mode(self) -> str:
        """Aktiver Tempo-Modus — Altbestand (NULL) zaehlt als Prozent."""
        return (self.TEMPO_MODE_BPM
                if self.tempo_mode == self.TEMPO_MODE_BPM
                else self.TEMPO_MODE_PERCENT)

    @property
    def has_target_bpm(self) -> bool:
        """BL-144: Laeuft diese Lokation auf Ziel-BPM?

        Beide Werte duerfen gespeichert sein — entscheidend ist der Modus.
        Ohne brauchbare BPM-Zahl faellt die Lokation auf Prozent zurueck.
        """
        return (self.effective_tempo_mode == self.TEMPO_MODE_BPM
                and bool(self.target_bpm) and self.target_bpm > 0)

    @property
    def effective_break_minutes(self) -> int:
        """Pausendauer in Minuten — Fallback auf DEFAULT_BREAK_MINUTES."""
        return self.break_minutes if self.break_minutes else self.DEFAULT_BREAK_MINUTES

    @property
    def schedule_list(self) -> list:
        """BL-178: Termine als Liste von (weekday, time_from, time_to)-Tripeln
        (weekday 1=Mo..7=So; time_to darf None sein).

        Primaerquelle ist die JSON-Spalte `schedules`. Als Fallback fuer
        Altbestand aus der ersten Paket-1-Fassung werden die Einzelspalten
        weekdays-CSV + eine gemeinsame Zeit in Tripel je Wochentag konvertiert.
        Robust gegen kaputte Werte — liefert im Zweifel eine leere Liste.
        """
        import json
        if self.schedules:
            try:
                raw = json.loads(self.schedules)
            except (ValueError, TypeError):
                raw = []
            out = []
            for item in raw if isinstance(raw, list) else []:
                if not isinstance(item, dict):
                    continue
                wd_raw = item.get("wd")
                try:
                    wd = int(wd_raw)
                except (TypeError, ValueError):
                    continue
                tf = str(item.get("from") or "").strip()
                tt = str(item.get("to") or "").strip()
                if 1 <= wd <= 7 and tf:
                    out.append((wd, tf, tt or None))
            return out
        # Fallback: alte Einzel-Felder (weekdays-CSV + gemeinsame Zeit)
        if self.weekdays and self.time_from:
            out = []
            for part in str(self.weekdays).split(","):
                part = part.strip()
                if part.isdigit() and 1 <= int(part) <= 7:
                    out.append((int(part), self.time_from, self.time_to or None))
            return out
        return []

    @property
    def has_schedule(self) -> bool:
        """BL-178: Hat die Lokation mindestens einen nutzbaren Termin?"""
        return bool(self.schedule_list)


# ---- SQL-Statements: Songs ----


_INSERT = """
INSERT INTO songs (filename, title, artist, label, quality, base_bpm,
                   standard_tempo, pitch, volume, loop_in, loop_out,
                   loop_offset_ms, lyrics_file, is_pattern, is_singing,
                   date_added, err)
VALUES (:filename, :title, :artist, :label, :quality, :base_bpm,
        :standard_tempo, :pitch, :volume, :loop_in, :loop_out,
        :loop_offset_ms, :lyrics_file, :is_pattern, :is_singing,
        :date_added, :err);
"""

_UPDATE = """
UPDATE songs SET
    title = :title,
    artist = :artist,
    label = :label,
    quality = :quality,
    base_bpm = :base_bpm,
    standard_tempo = :standard_tempo,
    pitch = :pitch,
    volume = :volume,
    loop_in = :loop_in,
    loop_out = :loop_out,
    loop_offset_ms = :loop_offset_ms,
    lyrics_file = :lyrics_file,
    is_pattern = :is_pattern,
    is_singing = :is_singing,
    err = :err
WHERE id = :id;
"""

_SONG_COLS = ("id, filename, title, artist, label, quality, base_bpm, "
              "standard_tempo, pitch, volume, loop_in, loop_out, "
              "loop_offset_ms, lyrics_file, is_pattern, is_singing, "
              "date_added, err")

_SELECT_BY_FILENAME = f"SELECT {_SONG_COLS} FROM songs WHERE filename = :filename;"
_SELECT_BY_TITLE = f"SELECT {_SONG_COLS} FROM songs WHERE title = :title LIMIT 1;"
_SELECT_BY_ID = f"SELECT {_SONG_COLS} FROM songs WHERE id = :id;"
_SELECT_ALL = f"SELECT {_SONG_COLS} FROM songs ORDER BY title;"
_DELETE = "DELETE FROM songs WHERE id = :id;"
_COUNT = "SELECT COUNT(*) FROM songs;"

# ---- SQL-Statements: Lokationen ----


_INSERT_LOCATION = "INSERT INTO locations (name) VALUES (:name);"
_UPDATE_LOCATION = "UPDATE locations SET name = :name WHERE id = :id;"
_SELECT_ALL_LOCATIONS = "SELECT * FROM locations ORDER BY name;"
_DELETE_LOCATION = "DELETE FROM locations WHERE id = :id;"

# ---- SQL-Statements: Genres (M:N mit Songs) ----


# BL-040: Name des speziellen "NEW"-Genres, das jeder neu angelegte Song
# automatisch erhaelt (Import / manuelles Anlegen). Caller entfernen es,
# sobald der Song eingearbeitet ist.
_NEW_GENRE_NAME = "NEW"

# Konvention "CHECK: <Thema>": System-Genres, die als To-Do-Marker fuer den
# Caller dienen (nach Songliste filterbar) — analog zum "NEW"-Genre, aber
# themenbezogen und wiederverwendbar. Eine Auto-Analyse setzt den Marker, wenn
# ihr Ergebnis unsicher war; beim manuellen Korrigieren wird er wieder entfernt.
# Erstes Thema: unsicher erkannter Musik-Startpunkt (Singing-Body).
CHECK_START_GENRE_NAME = "CHECK: START"

# Beat-Snap-Marker: Songs, deren Loop-Marken der Bulk-Beat-Snap NICHT sinnvoll
# auf den Beat legen konnte (Offset bleibt 0.0 — zu schwache Korrelation, Datei
# nicht dekodierbar, oder Loop liegt bereits exakt auf dem Beat). Ohne diesen
# Marker taeten sie mit loop_offset_ms=0.0 immer wieder als "ohne BeatSnap"
# auftauchen. Der Marker nimmt sie aus der Kandidatenliste; findet ein spaeterer
# Lauf doch einen Offset, wird er wieder abgeraeumt.
CHECK_BEATSNAP_GENRE_NAME = "CHECK: BEATSNAP"

_INSERT_GENRE = "INSERT OR IGNORE INTO genres (name) VALUES (:name);"
_SELECT_ALL_GENRES = "SELECT id, name FROM genres ORDER BY name;"
_RENAME_GENRE = "UPDATE genres SET name = :name WHERE id = :id;"
_DELETE_GENRE = "DELETE FROM genres WHERE id = :id;"
_REASSIGN_SONG_GENRES = "UPDATE song_genres SET genre_id = :new_id WHERE genre_id = :old_id;"
_DELETE_SONG_GENRE_BY_GENRE = "DELETE FROM song_genres WHERE genre_id = :genre_id;"
_SELECT_GENRE_COUNTS = """
SELECT genre_id, COUNT(*) as cnt FROM song_genres GROUP BY genre_id;
"""
_SELECT_GENRE_BY_NAME = "SELECT id FROM genres WHERE name = :name;"
_SELECT_GENRES_FOR_SONG = """
SELECT g.id, g.name FROM genres g
JOIN song_genres sg ON g.id = sg.genre_id
WHERE sg.song_id = :song_id
ORDER BY g.name;
"""
_DELETE_SONG_GENRES = "DELETE FROM song_genres WHERE song_id = :song_id;"
_INSERT_SONG_GENRE = "INSERT OR IGNORE INTO song_genres (song_id, genre_id) VALUES (?, ?);"
_SELECT_SONG_GENRE_MAP = """
SELECT sg.song_id, sg.genre_id, g.name
FROM song_genres sg
JOIN genres g ON g.id = sg.genre_id;
"""

# ---- SQL-Statements: Abspielhistorie (Drei-Schichten-Architektur) ----


_INSERT_PLAY_HISTORY = """
INSERT INTO play_history (song_id, location_id, played_at)
VALUES (:song_id, :location_id, datetime('now', 'localtime'));
"""

_UPSERT_SONG_LOCATION_STATS = """
INSERT INTO song_location_stats (song_id, location_id, last_played, play_count)
VALUES (:song_id, :location_id, datetime('now', 'localtime'), 1)
ON CONFLICT(song_id, location_id) DO UPDATE SET
    last_played = datetime('now', 'localtime'),
    play_count = play_count + 1;
"""

_SELECT_LAST_PLAYED_FOR_LOCATION = """
SELECT s.id, sls.last_played
FROM songs s
LEFT JOIN song_location_stats sls
    ON s.id = sls.song_id AND sls.location_id = :location_id;
"""

# ---- Referenzdaten und Default-Tanzprogramme ----


# Version der gebuendelten Referenzdaten (reference_calls.json). Hochzaehlen, wenn
# eine neue Referenz an Bestandsnutzer verteilt werden soll -> Reseed laeuft erneut.
REFERENCE_DATA_VERSION = 4

# Default-Programme inkl. Figuren-Limit (sequence_limit_to, BL-132). Das Limit
# ist die Programm-Obergrenze aus sequence_mapper._PROGRAMS als ".999999", damit
# alle Calls des Programms (teaching_order N.xxxx) eingeschlossen werden:
# MS=30, PL=40, A1=50, A2=60, C1=70, C2=80, C3A=90. Class-Varianten erben das
# Limit ihres Programms. Ohne dieses Limit bewirkt der Sequenz-Filter beim
# Programmwechsel nichts (siehe _insert_default_dance_programs, Backfill).
_DEFAULT_DANCE_PROGRAMS = [
    ("MS",        "Mainstream",           10, 7.0, 30.999999),
    ("MS Class",  "Mainstream (Class)",   15, 7.0, 30.999999),
    ("PL",        "Plus",                 20, 7.0, 40.999999),
    ("PL Class",  "Plus (Class)",         25, 7.0, 40.999999),
    ("A1",        "Advanced 1",           30, 7.0, 50.999999),
    ("A1 Class",  "Advanced 1 (Class)",   35, 7.0, 50.999999),
    ("A2",        "Advanced 2",           40, 7.0, 60.999999),
    ("A2 Class",  "Advanced 2 (Class)",   45, 7.0, 60.999999),
    ("C1",        "Challenge 1",          50, 7.0, 70.999999),
    ("C1 Class",  "Challenge 1 (Class)",  55, 7.0, 70.999999),
    ("C2",        "Challenge 2",          60, 7.0, 80.999999),
    ("C2 Class",  "Challenge 2 (Class)",  65, 7.0, 80.999999),
    ("C3A",       "Challenge 3A",         70, 7.0, 90.999999),
    ("C3A Class", "Challenge 3A (Class)", 75, 7.0, 90.999999),
]

# user_version-Marke fuer den einmaligen Figuren-Limit-Backfill (siehe
# _insert_default_dance_programs). Hochzaehlen, falls spaeter ein weiterer
# einmaliger Datenabgleich noetig wird.
_DP_LIMIT_BACKFILL_VERSION = 1


# Vordefinierte Property-Keys (key → (DE-Label, EN-Label))
# Nur diese Keys werden im Dialog als bekannte Felder angezeigt.
# Neue Keys hier ergänzen, niemals umbenennen (sonst gehen gespeicherte Werte verloren).
SONG_PROPERTY_KEYS: dict[str, tuple[str, str]] = {
    "original_artist": ("Original Artist", "Original Artist"),
    "release_year":    ("Erscheinungsjahr", "Release Year"),
}


# BL-178: Parameter der Start-Auto-Erkennung (Paket 1)
_SCHEDULE_TOLERANCE_BEFORE_MIN = 60    # so lange VOR time_from gilt der Vorschlag
_SCHEDULE_DEFAULT_DURATION_MIN = 240   # Fallback-Fensterlaenge, wenn time_to fehlt


def _parse_hhmm(value: Optional[str]) -> Optional[int]:
    """BL-178: Wandelt 'HH:MM' in Minuten seit Mitternacht; None bei ungueltig."""
    if not value:
        return None
    try:
        h_str, m_str = str(value).split(":")
        h, m = int(h_str), int(m_str)
    except (ValueError, AttributeError):
        return None
    if 0 <= h <= 23 and 0 <= m <= 59:
        return h * 60 + m
    return None


def _row_to_song(row: tuple) -> Song:
    """Wandelt eine DB-Zeile in ein Song-Objekt um."""
    return Song(
        id=row[0],
        filename=row[1],
        title=row[2],
        artist=row[3],
        label=row[4],
        quality=int(round(float(row[5] or 0))),
        base_bpm=row[6],
        standard_tempo=row[7],
        pitch=row[8],
        volume=row[9],
        loop_in=row[10],
        loop_out=row[11],
        loop_offset_ms=row[12] if len(row) > 12 else 0.0,
        lyrics_file=row[13] if len(row) > 13 else "",
        is_pattern=row[14] if len(row) > 14 else 1,
        is_singing=row[15] if len(row) > 15 else 1,
        date_added=row[16] if len(row) > 16 else "",
        err=row[17] if len(row) > 17 else 0,
    )


class SongDatabase(SchemaMixin, PotentialMixin, SequencesMixin):
    """SQLite-Datenbankzugriff fuer Songs, Lokationen und Abspielhistorie."""

    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            # PyInstaller: DB liegt neben der EXE, nicht in _internal
            if getattr(sys, 'frozen', False):
                base = os.path.dirname(sys.executable)
            else:
                base = os.path.dirname(__file__)
            db_path = os.path.join(base, "callers_caddy.db")
        self.db_path = db_path
        # timeout=30: bei gehaltener Schreibsperre (z.B. laufende Bulk-Worker)
        # bis zu 30s warten statt sofort "database is locked" zu werfen.
        self._conn = sqlite3.connect(db_path, timeout=30)
        self._conn.execute("PRAGMA journal_mode=WAL;")
        self._conn.execute("PRAGMA busy_timeout=30000;")
        self._conn.execute("PRAGMA foreign_keys=ON;")
        self._new_genre_id = None   # BL-040: gecachte ID des "NEW"-Genres
        # MS50-Perf (Band-Cache): Die teure "welche Sequenzen sind mit diesen Baendern
        # tanzbar?"-Auswertung haengt nur an stabilen Daten (Figuren je Sequenz, Baender
        # je Figur) + der gewaehlten Band-Menge (ueber den Abend stabil). Deshalb 1x
        # rechnen und merken; nur an Datenaenderungen verwerfen (invalidate_band_cache).
        self._band_cover_cache = {}   # frozenset(bands) -> frozenset(sequence_ids)
        self._scope_key = None        # (frozenset bands, frozenset below), aktuell in TEMP seq_scope
        self._band_cache_ver_seen = -1  # zuletzt gesehener _band_cache_ver.v (Auto-Invalidierung)
        self._seq_figures = None      # intern#111: sequence_id -> frozenset gebandeter Figuren
        # intern#145: Was beim Update nicht klappte. main zeigt es beim Start an.
        self.schema_problems: list[str] = []
        self._migrate()         # Zuerst: bestehende Tabellen umbenennen/erweitern
        self._create_tables()   # Dann: fehlende Tabellen anlegen (IF NOT EXISTS)
        self._apply_data_fixes()
        for problem in self.schema_problems:
            _safe_print(f"[SongDB] Update-Problem: {problem}")
        self._backfill_calls_json()  # Option C: calls_json aus field_1..15 fuellen
        self._ensure_sequence_calls_index()  # enthält-Filter-Index sicherstellen
        self.reseed_reference_data()  # MS50: gebuendelte Referenz einspielen (einmalig)
        # BL-210: Reste aelterer Versionen (kennen call_text_figures_extra nicht)
        # bei jedem Start aufraeumen, nicht erst beim naechsten Referenz-Update
        self._normalize_call_text_figures()
        self._conn.commit()
        self._backfill_auto_mappings_once()  # heilt ungemappte Massenimporte (einmalig)
        self._recompute_max_to_once()  # intern#95: Band-Regel geaendert (einmalig)
        print(f"[SongDB] Datenbank geoeffnet: {db_path}")

    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None
            print("[SongDB] Datenbank geschlossen")

    def is_open(self) -> bool:
        """True wenn die DB-Verbindung noch aktiv ist."""
        return self._conn is not None

    # ---- Song-CRUD ----

    def insert(self, song: Song) -> Song:
        """Fuegt einen neuen Song ein und gibt ihn mit ID zurueck."""
        from datetime import date
        from dataclasses import asdict
        if not song.date_added:
            song.date_added = date.today().isoformat()
        # asdict() spiegelt alle Felder des Dataclass automatisch —
        # neue Felder muessen hier nicht manuell ergaenzt werden.
        # Ueberzaehlige Keys (z.B. 'id') werden von sqlite3 stillschweigend ignoriert.
        cur = self._conn.execute(_INSERT, asdict(song))
        song.id = cur.lastrowid
        # BL-040: Jeder neu angelegte Song bekommt automatisch das Genre "NEW".
        # Additiv (INSERT OR IGNORE) — ueberschreibt keine spaeter gesetzten Genres.
        # Migration umgeht insert() (eigener Bulk-INSERT in migration/db_writer.py),
        # damit migrierter Altbestand NICHT als "NEW" markiert wird.
        self._conn.execute(_INSERT_SONG_GENRE, (song.id, self._ensure_new_genre_id()))
        self._conn.commit()
        print(f"[SongDB] Song eingefuegt: #{song.id} '{song.filename}'")
        return song

    def update(self, song: Song) -> Song:
        """Aktualisiert einen bestehenden Song (nach ID).

        Sicherheit: Loop-Werte werden geschuetzt gegen:
        1. Ueberschreiben mit 0.0 (typisch bei Song-Wechsel)
        2. Ueberschreiben mit Song-Dauer (typisch wenn Engine-Loops
           auf (0, Songlaenge) zurueckgesetzt wurden und der Guard
           nur loop_in=0 abfaengt, aber loop_out=Dauer durchlaesst)
        """
        # Safety-Guard: Loop-Werte schuetzen
        loop_in = song.loop_in
        loop_out = song.loop_out
        existing = self.get_by_id(song.id)
        if existing:
            # Guard 1: Nullen verhindern
            if loop_in == 0.0 and existing.loop_in > 0.0:
                loop_in = existing.loop_in
                print(f"[SongDB] GUARD: loop_in=0 verhindert "
                      f"(DB hat {existing.loop_in:.2f})")
            if loop_out == 0.0 and existing.loop_out > 0.0:
                loop_out = existing.loop_out
                print(f"[SongDB] GUARD: loop_out=0 verhindert "
                      f"(DB hat {existing.loop_out:.2f})")
            # Guard 2: Song-Dauer ueberschreibt echten Loop-Out nicht.
            # Wenn DB einen Loop-Out hat der KLEINER ist als der neue Wert
            # UND loop_in auf 0 zurueckgesetzt wurde (= Engine-Reset-Muster),
            # dann alten Wert beibehalten.
            if (loop_in == 0.0 and existing.loop_in > 0.0
                    and loop_out > existing.loop_out
                    and existing.loop_out > 0.0):
                loop_out = existing.loop_out
                print(f"[SongDB] GUARD: loop_out=Dauer verhindert "
                      f"(DB hat {existing.loop_out:.2f}, "
                      f"neu waere {song.loop_out:.2f})")
        from dataclasses import asdict
        params = asdict(song)
        # Loop-Guard-Werte einsetzen (koennen vom Guard abweichen)
        params["loop_in"] = loop_in
        params["loop_out"] = loop_out
        self._conn.execute(_UPDATE, params)
        self._conn.commit()
        print(f"[SongDB] Song aktualisiert: #{song.id} '{song.filename}'")
        return song

    def update_filename(self, song_id: int, new_filename: str) -> str:
        """Aendert den Dateinamen eines Songs.

        Returns:
            "" bei Erfolg, Fehlermeldung bei Konflikt.
        """
        # Pruefen ob Filename schon vergeben ist
        existing = self.get_by_filename(new_filename)
        if existing and existing.id != song_id:
            return (f"Datei '{new_filename}' ist bereits Song "
                    f"#{existing.id} '{existing.title}' zugeordnet.")
        self._conn.execute(
            "UPDATE songs SET filename = :filename WHERE id = :id;",
            {"id": song_id, "filename": new_filename}
        )
        self._conn.commit()
        print(f"[SongDB] Filename geaendert: #{song_id} -> '{new_filename}'")
        return ""

    def get_by_filename(self, filename: str) -> Optional[Song]:
        """Sucht einen Song anhand des Dateinamens."""
        cur = self._conn.execute(_SELECT_BY_FILENAME, {"filename": filename})
        row = cur.fetchone()
        return _row_to_song(row) if row else None

    def get_by_title(self, title: str) -> Optional[Song]:
        """Sucht einen Song anhand des Titels (Fallback fuer V1-Playlisten)."""
        cur = self._conn.execute(_SELECT_BY_TITLE, {"title": title})
        row = cur.fetchone()
        return _row_to_song(row) if row else None

    # ---- Song-Properties (BL-094) ----

    def get_properties(self, song_id: int) -> dict:
        """Alle Properties eines Songs als dict {key: value} laden."""
        cur = self._conn.execute(
            "SELECT key, value FROM song_properties WHERE song_id = ?", (song_id,)
        )
        return dict(cur.fetchall())

    def set_property(self, song_id: int, key: str, value: str):
        """Property setzen (upsert). Leerer value → Eintrag loeschen."""
        if value.strip():
            self._conn.execute(
                "INSERT OR REPLACE INTO song_properties (song_id, key, value) VALUES (?, ?, ?)",
                (song_id, key, value.strip()),
            )
        else:
            self._conn.execute(
                "DELETE FROM song_properties WHERE song_id = ? AND key = ?",
                (song_id, key),
            )
        self._conn.commit()

    def set_properties(self, song_id: int, props: dict):
        """Mehrere Properties auf einmal setzen (Batch-Upsert)."""
        for key, value in props.items():
            self.set_property(song_id, key, value)

    # ---- Song-Varianten (BL-XXX: Music- und Lyric-Varianten) ----

    def get_variants(self, song_id: int, kind: str) -> list:
        """Alle Varianten eines Songs zurückgeben (Index 2+).

        Args:
            kind: 'music' oder 'lyric'
        Returns:
            Liste von (index, name, filename) — index beginnt bei 2.
        """
        props = self.get_properties(song_id)
        variants = []
        idx = 2
        while True:
            name_key = f"{kind}_{idx}_name"
            file_key = f"{kind}_{idx}_file"
            if name_key not in props and file_key not in props:
                break
            variants.append((idx, props.get(name_key, ""), props.get(file_key, "")))
            idx += 1
        return variants

    def get_variant_owner(self, filename: str, kind: str = "music") -> Optional[Song]:
        """Song, bei dem filename als Variante (Index 2+) eingetragen ist, sonst None.

        Vergleich ohne Gross-/Kleinschreibung wie die Varianten-Pruefung des
        ZIP-Imports (intern#132).
        """
        row = self._conn.execute(
            "SELECT song_id FROM song_properties "
            "WHERE key LIKE ? ESCAPE '\\' AND lower(value) = lower(?) "
            "ORDER BY song_id LIMIT 1",
            (f"{kind}\\_%\\_file", filename)).fetchone()
        return self.get_by_id(row[0]) if row else None

    def add_variant(self, song_id: int, kind: str, name: str, filename: str):
        """Neue Variante anlegen (naechster freier Index ab 2).

        Args:
            kind: 'music' oder 'lyric'
        """
        props = self.get_properties(song_id)
        idx = 2
        while f"{kind}_{idx}_name" in props or f"{kind}_{idx}_file" in props:
            idx += 1
        self.set_property(song_id, f"{kind}_{idx}_name", name)
        self.set_property(song_id, f"{kind}_{idx}_file", filename)

    def delete_variant(self, song_id: int, kind: str, idx: int):
        """Variante loeschen und hoehere Indizes nachruecken lassen."""
        props = self.get_properties(song_id)
        self._conn.execute(
            "DELETE FROM song_properties WHERE song_id=? AND key IN (?, ?)",
            (song_id, f"{kind}_{idx}_name", f"{kind}_{idx}_file"),
        )
        # Hoehere Indizes um eins heruntersetzen
        cur = idx + 1
        new = idx
        while True:
            name_key = f"{kind}_{cur}_name"
            file_key = f"{kind}_{cur}_file"
            if name_key not in props and file_key not in props:
                break
            self._conn.execute(
                "DELETE FROM song_properties WHERE song_id=? AND key IN (?, ?)",
                (song_id, name_key, file_key),
            )
            if name_key in props:
                self._conn.execute(
                    "INSERT OR REPLACE INTO song_properties (song_id, key, value) VALUES (?, ?, ?)",
                    (song_id, f"{kind}_{new}_name", props[name_key]),
                )
            if file_key in props:
                self._conn.execute(
                    "INSERT OR REPLACE INTO song_properties (song_id, key, value) VALUES (?, ?, ?)",
                    (song_id, f"{kind}_{new}_file", props[file_key]),
                )
            cur += 1
            new += 1
        self._conn.commit()

    # ---- Custom-Jump-Marker (BL-185) ----
    # Speicherort: song_properties (Extended Data), Keys marker_<idx>_time und
    # marker_<idx>_caption. Nur Songs mit Markern belegen Zeilen — kein neues
    # Song-Feld, keine leeren Spalten. idx ist eine stabile ID (max+1, keine
    # Wiederverwendung, Luecken erlaubt). time ist Original-Zeit in Sekunden
    # (tempo-/WSOLA-unabhaengig, wie loop_in/out).

    @staticmethod
    def _marker_idx_from_key(key: str):
        m = re.match(r'^marker_(\d+)_time$', key)
        return int(m.group(1)) if m else None

    def get_markers(self, song_id: int) -> list:
        """Alle Custom-Marker eines Songs, nach Zeit sortiert.

        Returns:
            Liste von (idx, time_seconds, caption). idx = stabile ID.
        """
        props = self.get_properties(song_id)
        markers = []
        for key, val in props.items():
            idx = self._marker_idx_from_key(key)
            if idx is None:
                continue
            try:
                t = float(val)
            except (ValueError, TypeError):
                continue
            caption = props.get(f"marker_{idx}_caption", "")
            markers.append((idx, t, caption))
        markers.sort(key=lambda x: x[1])
        return markers

    def add_marker(self, song_id: int, time_seconds: float, caption: str = "") -> int:
        """Neuen Marker anlegen (naechste freie ID = hoechste + 1). Gibt idx zurueck."""
        props = self.get_properties(song_id)
        max_idx = 0
        for key in props:
            idx = self._marker_idx_from_key(key)
            if idx is not None:
                max_idx = max(max_idx, idx)
        idx = max_idx + 1
        self.set_property(song_id, f"marker_{idx}_time", f"{float(time_seconds):.3f}")
        # set_property loescht leere Werte — leere Caption bleibt also unbelegt.
        self.set_property(song_id, f"marker_{idx}_caption", caption or "")
        return idx

    def update_marker(self, song_id: int, idx: int,
                      time_seconds: float = None, caption: str = None):
        """Zeit und/oder Beschriftung eines bestehenden Markers aendern."""
        if time_seconds is not None:
            self.set_property(song_id, f"marker_{idx}_time",
                              f"{float(time_seconds):.3f}")
        if caption is not None:
            self.set_property(song_id, f"marker_{idx}_caption", caption or "")

    def delete_marker(self, song_id: int, idx: int):
        """Marker loeschen (Zeit + Caption). Keine Neuvergabe der IDs."""
        self._conn.execute(
            "DELETE FROM song_properties WHERE song_id=? AND key IN (?, ?)",
            (song_id, f"marker_{idx}_time", f"marker_{idx}_caption"),
        )
        self._conn.commit()

    # ---- Metadaten-Export/Import (BL-114) ----

    _UPDATABLE_SONG_FIELDS = {'artist', 'label', 'quality', 'err'}

    def update_song_simple_field(self, song_id: int, field: str, value: str):
        """Aktualisiert artist oder label in der songs-Tabelle."""
        if field not in self._UPDATABLE_SONG_FIELDS:
            raise ValueError(f"Feld '{field}' nicht erlaubt")
        self._conn.execute(f"UPDATE songs SET {field} = ? WHERE id = ?", (value, song_id))
        self._conn.commit()

    def update_lyrics_file(self, song_id: int, filename: str) -> None:
        """Setzt den lyrics_file-Eintrag eines Songs (Dateiname ohne Pfad).

        Wird vom Lyrics-Editor benutzt, wenn beim Bearbeiten eine RTF/TXT-Datei
        nach HTML konvertiert wurde — der Song zeigt dann auf die neue Datei.
        """
        self._conn.execute(
            "UPDATE songs SET lyrics_file = ? WHERE id = ?",
            (filename or "", int(song_id))
        )
        self._conn.commit()

    # ---- BL-206: Universeller Spalten-Zugriff fuer Songdaten-Export/Import ----

    def list_song_columns(self) -> list:
        """Alle Spalten der songs-Tabelle in Schema-Reihenfolge.

        Dynamisch per PRAGMA: neue Spalten erscheinen automatisch, ohne dass
        Export/Import angepasst werden muss (BL-206 — universelle Feldliste).
        Rueckgabe: [(name, affinity), ...] mit affinity z.B. 'INTEGER', 'REAL',
        'TEXT' (Gross geschrieben).
        """
        cur = self._conn.execute("PRAGMA table_info(songs)")
        # Spalten je Zeile: cid, name, type, notnull, dflt_value, pk
        return [(row[1], (row[2] or "").upper()) for row in cur.fetchall()]

    def get_song_row(self, song_id: int) -> dict:
        """Eine songs-Zeile als {spalte: wert} (alle Spalten, universell).

        Liest direkt aus dem Schema statt aus dem Song-Dataclass, damit auch
        kuenftige Spalten ohne Code-Aenderung mitgelesen werden (BL-206).
        """
        cols = [name for name, _ in self.list_song_columns()]
        cur = self._conn.execute(
            f"SELECT {', '.join(cols)} FROM songs WHERE id = ?", (int(song_id),))
        row = cur.fetchone()
        return dict(zip(cols, row)) if row else {}

    def apply_import_fields(self, song_id: int, col_values: dict) -> None:
        """Schreibt GENAU die uebergebenen songs-Spalten (BL-206-Import).

        Bewusst OHNE den Loop-Guard aus update(): ein importierter loop_in/
        loop_out/loop_offset_ms soll exakt uebernommen werden (auch 0.0).
        Spaltennamen werden gegen das echte Schema geprueft (kein Einschleusen
        ueber Feldnamen); 'id' ist nie beschreibbar.
        """
        valid = {name for name, _ in self.list_song_columns()} - {"id"}
        sets, params = [], []
        for col, val in col_values.items():
            if col not in valid:
                raise ValueError(f"Spalte '{col}' nicht beschreibbar")
            sets.append(f"{col} = ?")
            params.append(val)
        if not sets:
            return
        params.append(int(song_id))
        self._conn.execute(
            f"UPDATE songs SET {', '.join(sets)} WHERE id = ?", params)
        self._conn.commit()

    def get_all_property_keys(self, song_ids=None) -> list:
        """Alle vorkommenden song_properties-Keys (Extended Data), sortiert.

        Mit song_ids: nur Keys, die bei diesen Songs vorkommen (fuer die
        Feld-Auswahl beim Export der gefilterten Liste). Ohne: alle Keys der DB.
        """
        if song_ids:
            ids = [int(s) for s in song_ids]
            marks = ",".join("?" * len(ids))
            cur = self._conn.execute(
                f"SELECT DISTINCT key FROM song_properties WHERE song_id IN ({marks})",
                ids)
        else:
            cur = self._conn.execute("SELECT DISTINCT key FROM song_properties")
        return sorted(row[0] for row in cur.fetchall())

    def get_install_id(self) -> str:
        """Stabile, pro-Datenbank eindeutige Installations-ID (lazy erzeugt).

        Dient dem Songdaten-Import (BL-206): nur wenn eine Export-JSON von
        DIESER Installation stammt, darf ueber die stabile lokale Song-id
        zugeordnet werden (das erlaubt Titel-Umbenennen). Fremde JSONs
        (Caller-Austausch) tragen eine andere/keine install_id -> dort greift
        weiter der Titel-Abgleich, damit keine id auf einen fremden Song zeigt.
        """
        row = self._conn.execute(
            "SELECT value FROM app_meta WHERE key='install_id'").fetchone()
        if row and row[0]:
            return row[0]
        import uuid
        iid = uuid.uuid4().hex
        self._conn.execute(
            "INSERT OR REPLACE INTO app_meta (key, value) VALUES ('install_id', ?)",
            (iid,))
        self._conn.commit()
        return iid

    def get_songs_missing_song_field(self, field: str) -> list:
        """Songs bei denen artist oder label leer ist. Gibt [(id, title, filename)] zurueck."""
        cur = self._conn.execute(
            f"SELECT id, title, filename FROM songs WHERE {field} = '' OR {field} IS NULL"
        )
        return cur.fetchall()

    def get_songs_missing_property(self, key: str) -> list:
        """Songs ohne gesetzten song_property-Key. Gibt [(id, title, filename)] zurueck."""
        cur = self._conn.execute("""
            SELECT s.id, s.title, s.filename
            FROM songs s
            LEFT JOIN song_properties sp ON sp.song_id = s.id AND sp.key = ?
            WHERE sp.value IS NULL OR sp.value = ''
        """, (key,))
        return cur.fetchall()

    def get_songs_missing_rating(self, field: str) -> list:
        """Songs bei denen quality oder err noch auf 0 (unbewertet) steht."""
        cur = self._conn.execute(
            f"SELECT id, title, filename FROM songs WHERE {field} = 0"
        )
        return cur.fetchall()

    def get_songs_missing_genre(self) -> list:
        """Songs ohne Genre-Zuweisung. Gibt [(id, title, filename)] zurueck."""
        cur = self._conn.execute("""
            SELECT s.id, s.title, s.filename
            FROM songs s
            WHERE NOT EXISTS (SELECT 1 FROM song_genres sg WHERE sg.song_id = s.id)
        """)
        return cur.fetchall()

    def get_by_id(self, song_id: int) -> Optional[Song]:
        """Sucht einen Song anhand der ID."""
        cur = self._conn.execute(_SELECT_BY_ID, {"id": song_id})
        row = cur.fetchone()
        return _row_to_song(row) if row else None

    def get_all(self) -> List[Song]:
        """Gibt alle Songs sortiert nach Titel zurueck."""
        cur = self._conn.execute(_SELECT_ALL)
        return [_row_to_song(row) for row in cur.fetchall()]

    def delete(self, song_id: int):
        """Loescht einen Song anhand der ID.

        Entfernt auch abhaengige Eintraege:
        - song_genres (Genre-Verknuepfungen)
        - play_history (Abspiel-Historie)
        - song_location_stats (Statistik-Cache)
        - potential_ignored (Datenqualitaets-Flags)
        Dateien (MP3, Lyrics) werden NICHT geloescht.
        """
        # Abhaengige Tabellen aufraeumen
        cur_g = self._conn.execute(
            "DELETE FROM song_genres WHERE song_id = ?", (song_id,))
        cur_h = self._conn.execute(
            "DELETE FROM play_history WHERE song_id = ?", (song_id,))
        cur_s = self._conn.execute(
            "DELETE FROM song_location_stats WHERE song_id = ?", (song_id,))
        self._conn.execute(
            "DELETE FROM potential_ignored WHERE entity_id = ?", (song_id,))
        # Song selbst loeschen
        self._conn.execute(_DELETE, {"id": song_id})
        self._conn.commit()
        print(f"[SongDB] Song geloescht: #{song_id} "
              f"({cur_g.rowcount} Genres, {cur_h.rowcount} History, "
              f"{cur_s.rowcount} Stats)")

    def get_all_songs_for_bulk(self) -> list:
        """Schlanke Liste aller Songs fuer den Massen-Loesch-Reiter (BL-148).

        Laedt nur die fuer die Tabelle benoetigten Spalten — KEINE vollen
        Song-Objekte (Performance bei grossen Bibliotheken).
        Rueckgabe: [(id, is_pattern, is_singing, date_added, title, label,
                    quality, err), ...]
        """
        cur = self._conn.execute(
            "SELECT id, is_pattern, is_singing, date_added, title, label, "
            "quality, err FROM songs")
        return cur.fetchall()

    def count_songs_with_history(self, song_ids: list) -> int:
        """Anzahl der Songs aus song_ids, zu denen Historiendaten existieren.

        Zaehlt Songs, die in play_history ODER song_location_stats vorkommen.
        Fuer die Rueckfrage im Massen-Loeschen (BL-148).
        """
        if not song_ids:
            return 0
        found = set()
        for chunk in _chunked(song_ids):
            ph = ",".join("?" * len(chunk))
            cur = self._conn.execute(
                f"SELECT song_id FROM play_history WHERE song_id IN ({ph}) "
                f"UNION SELECT song_id FROM song_location_stats "
                f"WHERE song_id IN ({ph})", list(chunk) + list(chunk))
            found.update(r[0] for r in cur.fetchall())
        return len(found)

    @staticmethod
    def bulk_delete_on_connection(conn, song_ids: list,
                                  delete_history: bool = False) -> int:
        """Loescht mehrere Songs in EINER Transaktion auf der gegebenen
        Connection (BL-148). Als staticmethod, damit ein Hintergrund-Worker
        mit eigener Connection dieselbe Logik nutzen kann (Eiserne Regel:
        Massen-DELETE nicht auf dem Main-Thread).

        song_genres und potential_ignored werden immer mit entfernt.
        delete_history=True: play_history + song_location_stats werden ebenfalls
        geloescht. delete_history=False: Historie bleibt als verwaiste Eintraege
        erhalten (per 'Verwaiste Historie' spaeter bereinigbar) — dafuer wird der
        FK-Check waehrend des Song-Loeschens kurz deaktiviert (wie delete_location).

        IDs werden gechunkt (SQLite-Variablengrenze), aber als EINE Transaktion
        committet (Commit erst am Ende).

        Rueckgabe: Anzahl tatsaechlich geloeschter Songs.
        """
        if not song_ids:
            return 0
        deleted = 0
        # FK nur im Behalten-Modus deaktivieren (verwaiste Historie zulassen)
        if not delete_history:
            conn.execute("PRAGMA foreign_keys = OFF;")
        try:
            for chunk in _chunked(song_ids):
                ids = list(chunk)
                ph = ",".join("?" * len(ids))
                # Genre-Verknuepfungen und Datenqualitaets-Flags immer aufraeumen
                conn.execute(f"DELETE FROM song_genres WHERE song_id IN ({ph})", ids)
                conn.execute(
                    f"DELETE FROM potential_ignored WHERE entity_id IN ({ph})", ids)
                if delete_history:
                    conn.execute(
                        f"DELETE FROM play_history WHERE song_id IN ({ph})", ids)
                    conn.execute(
                        f"DELETE FROM song_location_stats WHERE song_id IN ({ph})", ids)
                cur = conn.execute(f"DELETE FROM songs WHERE id IN ({ph})", ids)
                deleted += cur.rowcount
            conn.commit()
        finally:
            if not delete_history:
                conn.execute("PRAGMA foreign_keys = ON;")
        print(f"[SongDB] Massen-Loeschung: {deleted} Songs "
              f"(Historie {'mit' if delete_history else 'behalten'})")
        return deleted

    def bulk_delete_songs(self, song_ids: list, delete_history: bool = False) -> int:
        """Main-Thread-Variante (kleine Mengen). Delegiert an
        bulk_delete_on_connection mit der eigenen Connection."""
        return self.bulk_delete_on_connection(self._conn, song_ids, delete_history)

    def count(self) -> int:
        """Anzahl aller Songs in der Datenbank."""
        cur = self._conn.execute(_COUNT)
        return cur.fetchone()[0]

    # ---- Song-Convenience ----

    def get_or_create(self, filename: str) -> Song:
        """Gibt einen bestehenden Song zurueck oder legt einen neuen an.

        Import-Workflow: Beim Laden einer MP3 wird der Dateiname gesucht.
        Existiert er bereits, werden die gespeicherten Einstellungen geladen.
        Andernfalls wird ein neuer Eintrag mit Default-Werten angelegt.
        Neue Songs: is_pattern=1 und is_singing=1 (beide angehakt).
        """
        existing = self.get_by_filename(filename)
        if existing:
            print(f"[SongDB] Song gefunden: #{existing.id} '{filename}'")
            return existing
        return self.insert(self.new_song(filename))

    @staticmethod
    def new_song(filename: str) -> Song:
        """Anlage-Defaults eines neuen Songs: Titel = Dateiname ohne Endung,
        beide Typen aktiv. Einzige Quelle dafuer — auch die Doppelgaenger-
        Reparatur (intern#106) vergleicht dagegen."""
        return Song(filename=filename, title=os.path.splitext(filename)[0],
                    is_pattern=1, is_singing=1)

    def get_or_create_for_file(self, rel_filename: str) -> Song:
        """Song zu einer geladenen Datei finden oder anlegen (intern#106).

        rel_filename ist der Pfad relativ zum Musik-Slot ('Sub/song.mp3' bzw.
        'song.mp3' im Slot-Stamm). Erst exakt danach suchen, dann ueber den
        Basename — nur so findet ein Song aus einem Unterordner seinen
        Eintrag, statt einen Doppelgaenger mit Defaults anzulegen."""
        song = self.get_by_filename(rel_filename)
        if song is None:
            song = self.get_or_create(os.path.basename(rel_filename))
        return song

    def merge_songs(self, keep: Song, drop_id: int, properties: dict,
                    skip_genre_id: int = -1):
        """Fuehrt Song drop_id in keep zusammen — in EINER Transaktion (intern#106).

        keep:        bereits fertig zusammengefuehrte Song-Felder (wird 1:1
                     geschrieben, ohne Loop-Guard: der Aufrufer hat entschieden)
        properties:  vollstaendige song_properties fuer keep (ersetzt die alten)
        skip_genre_id: Genre, das von drop NICHT uebernommen wird (z.B. "NEW")
        play_history wird umgehaengt, song_location_stats addiert, danach wird
        drop samt Abhaengigkeiten geloescht. Bricht etwas ab, bleibt alles
        wie vorher (Rollback)."""
        from dataclasses import asdict
        with self._conn:
            self._conn.execute(_UPDATE, asdict(keep))
            self._conn.execute("DELETE FROM song_properties WHERE song_id IN (?, ?)",
                               (keep.id, drop_id))
            self._conn.executemany(
                "INSERT INTO song_properties (song_id, key, value) VALUES (?, ?, ?)",
                [(keep.id, k, v) for k, v in properties.items()])
            self._conn.execute(
                "INSERT OR IGNORE INTO song_genres (song_id, genre_id) "
                "SELECT ?, genre_id FROM song_genres WHERE song_id = ? AND genre_id != ?",
                (keep.id, drop_id, skip_genre_id))
            self._conn.execute("UPDATE play_history SET song_id = ? WHERE song_id = ?",
                               (keep.id, drop_id))
            self._conn.execute(
                "INSERT INTO song_location_stats (song_id, location_id, last_played, play_count) "
                "SELECT ?, location_id, last_played, play_count "
                "FROM song_location_stats WHERE song_id = ? "
                "ON CONFLICT(song_id, location_id) DO UPDATE SET "
                "  last_played = MAX(last_played, excluded.last_played), "
                "  play_count = play_count + excluded.play_count",
                (keep.id, drop_id))
            for sql in ("DELETE FROM song_genres WHERE song_id = ?",
                        "DELETE FROM song_location_stats WHERE song_id = ?",
                        "DELETE FROM potential_ignored WHERE entity_id = ?",
                        "DELETE FROM songs WHERE id = ?"):
                self._conn.execute(sql, (drop_id,))
        print(f"[SongDB] Song #{drop_id} in #{keep.id} '{keep.filename}' zusammengefuehrt")

    def clear_loop(self, song_id: int):
        """Loescht Loop-Marker fuer einen Song (umgeht Safety-Guard)."""
        self._conn.execute(
            "UPDATE songs SET loop_in = 0.0, loop_out = 0.0 WHERE id = :id",
            {"id": song_id})
        self._conn.commit()
        print(f"[SongDB] Loop geloescht fuer Song #{song_id}")

    def save_playback_settings(self, song_id: int, *,
                                tempo: float = None,
                                pitch: float = None,
                                volume: float = None,
                                loop_in: float = None,
                                loop_out: float = None,
                                loop_offset_ms: float = None):
        """Speichert einzelne Wiedergabe-Einstellungen (Partial Update).

        Nur die uebergebenen Werte werden geaendert (Keyword-Only).
        """
        song = self.get_by_id(song_id)
        if not song:
            return

        if tempo is not None:
            song.standard_tempo = tempo
        if pitch is not None:
            song.pitch = pitch
        if volume is not None:
            song.volume = volume
        if loop_in is not None:
            song.loop_in = loop_in
        if loop_out is not None:
            song.loop_out = loop_out
        if loop_offset_ms is not None:
            song.loop_offset_ms = loop_offset_ms

        self.update(song)

    # ---- Lokation-CRUD ----

    def insert_location(self, name: str) -> Location:
        """Fuegt eine neue Lokation ein."""
        cur = self._conn.execute(_INSERT_LOCATION, {"name": name})
        self._conn.commit()
        location = Location(id=cur.lastrowid, name=name)
        print(f"[SongDB] Lokation eingefuegt: #{location.id} '{location.name}'")
        return location

    def update_location(self, location: Location):
        """Aktualisiert den Lokation-Namen."""
        self._conn.execute(_UPDATE_LOCATION, {"id": location.id, "name": location.name})
        self._conn.commit()
        print(f"[SongDB] Lokation aktualisiert: #{location.id} '{location.name}'")

    def delete_location(self, location_id: int, delete_history: bool = False):
        """Loescht eine Lokation.

        Args:
            location_id: ID der zu loeschenden Lokation.
            delete_history: Wenn True, werden auch play_history und
                song_location_stats fuer diese Lokation geloescht.
                Wenn False, wird location_id in play_history auf NULL gesetzt.
        """
        if delete_history:
            cur = self._conn.execute(
                "DELETE FROM play_history WHERE location_id = ?", (location_id,))
            hist_count = cur.rowcount
            cur2 = self._conn.execute(
                "DELETE FROM song_location_stats WHERE location_id = ?",
                (location_id,))
            stats_count = cur2.rowcount
            print(f"[SongDB] Historie geloescht: {hist_count} History, "
                  f"{stats_count} Stats fuer Lokation #{location_id}")
        else:
            # History behalten — location_id bleibt stehen (wird verwaist)
            # Nur Stats bereinigen (Cache, kann regeneriert werden)
            self._conn.execute(
                "DELETE FROM song_location_stats WHERE location_id = ?",
                (location_id,))
        # Ignorieren-Eintraege fuer diese Lokation bereinigen
        self._conn.execute(
            "DELETE FROM potential_ignored "
            "WHERE check_type = 'location_no_history' AND entity_id = ?",
            (location_id,))
        # BL-178 P2: Lokationen, die ihre Historie mit DIESER teilten, wieder
        # eigenstaendig machen (verwaisten Senken-Verweis aufloesen).
        self._conn.execute(
            "UPDATE locations SET shared_history_with=NULL WHERE shared_history_with=?",
            (location_id,))
        # FK kurz deaktivieren: play_history darf auf geloeschte Lokation zeigen
        self._conn.commit()
        self._conn.execute("PRAGMA foreign_keys=OFF;")
        self._conn.execute(_DELETE_LOCATION, {"id": location_id})
        self._conn.commit()
        self._conn.execute("PRAGMA foreign_keys=ON;")
        print(f"[SongDB] Lokation geloescht: #{location_id} "
              f"(Historie {'geloescht' if delete_history else 'behalten'})")

    def get_all_locations(self) -> List[Location]:
        """Gibt alle Lokationen sortiert nach Name zurueck."""
        cur = self._conn.execute(
            "SELECT id, name, dance_program_id, temp_tempo, target_bpm, "
            "tempo_mode, planned_tips, break_minutes, weekdays, time_from, time_to, "
            "schedules, shared_history_with "
            "FROM locations ORDER BY name;"
        )
        return [
            Location(
                id=row[0], name=row[1],
                dance_program_id=row[2] if len(row) > 2 else None,
                temp_tempo=row[3] if len(row) > 3 else None,
                target_bpm=row[4] if len(row) > 4 else None,
                tempo_mode=row[5] if len(row) > 5 else None,
                planned_tips=row[6] if len(row) > 6 else None,
                break_minutes=row[7] if len(row) > 7 else None,
                weekdays=row[8] if len(row) > 8 else None,
                time_from=row[9] if len(row) > 9 else None,
                time_to=row[10] if len(row) > 10 else None,
                schedules=row[11] if len(row) > 11 else None,
                shared_history_with=row[12] if len(row) > 12 else None,
            )
            for row in cur.fetchall()
        ]

    def find_locations_for_datetime(self, dt) -> list:
        """BL-178: Lokationen, deren Termin auf den Zeitpunkt dt passt —
        beste Uebereinstimmung zuerst.

        Match-Regeln:
          - Wochentag von dt (Mo=1..So=7) muss in weekdays der Lokation liegen.
          - Die Uhrzeit von dt muss im Fenster
              [time_from - Toleranz .. time_to]
            liegen (fehlt/ungueltig time_to, gilt time_from + Standard-Dauer).

        Rueckgabe: Liste von (Location, score); kleinerer score = besser
        (zeitlich naeher am geplanten Start). Leere Liste = kein Treffer.
        """
        weekday = dt.isoweekday()          # Mo=1..So=7
        now_min = dt.hour * 60 + dt.minute
        matches = []
        for loc in self.get_all_locations():
            best = None
            for (wd, tf, tt) in loc.schedule_list:
                if wd != weekday:
                    continue
                start = _parse_hhmm(tf)
                if start is None:
                    continue
                end = _parse_hhmm(tt)
                if end is None or end <= start:
                    end = start + _SCHEDULE_DEFAULT_DURATION_MIN
                win_start = start - _SCHEDULE_TOLERANCE_BEFORE_MIN
                if win_start <= now_min <= end:
                    score = abs(now_min - start)
                    if best is None or score < best:
                        best = score
            if best is not None:
                matches.append((loc, best))
        matches.sort(key=lambda t: t[1])
        return matches

    def get_location_name(self, location_id: int) -> str | None:
        row = self._conn.execute(
            "SELECT name FROM locations WHERE id = ?", (location_id,)).fetchone()
        return row[0] if row else None

    # ---- BL-178 Paket 2: Shared History ----

    def _effective_history_id(self, location_id):
        """BL-178 P2: Loest eine Lokations-ID auf die History-fuehrende 'Senke'
        auf. shared_history_with zeigt (per set_shared_history) immer direkt auf
        die Senke, daher genuegt EIN Lookup (keine Ketten-Aufloesung noetig)."""
        if location_id is None:
            return None
        row = self._conn.execute(
            "SELECT shared_history_with FROM locations WHERE id=?",
            (location_id,)).fetchone()
        if row and row[0]:
            return row[0]
        return location_id

    def count_history_entries(self, location_id) -> int:
        """BL-178 P2: Anzahl play_history-Eintraege, die UNTER dieser ID stehen
        (fuer die Rueckfrage vor dem Historie-Umzug)."""
        if location_id is None:
            return 0
        row = self._conn.execute(
            "SELECT COUNT(*) FROM play_history WHERE location_id=?",
            (location_id,)).fetchone()
        return row[0] if row else 0

    def set_shared_history(self, location_id: int, target_id, migrate: bool = True) -> int:
        """BL-178 P2: Verknuepft die Historie von location_id mit einer Ziel-Senke
        (target_id) oder loest die Verknuepfung (target_id=None).

        - Ziel wird transitiv auf dessen Senke aufgeloest (keine Ketten).
        - Selbst-/Zyklus-Verweis wird verhindert.
        - migrate=True: bereits vorhandene play_history-Eintraege von location_id
          werden auf die Senke umgeschrieben und der Statistik-Cache neu gebaut.

        Rueckgabe: Anzahl umgezogener History-Eintraege (0 bei Trennen/ohne Migration).
        """
        moved = 0
        if target_id is None:
            self._conn.execute(
                "UPDATE locations SET shared_history_with=NULL WHERE id=?",
                (location_id,))
            self._conn.commit()
            return 0
        sink = self._effective_history_id(target_id)
        if sink == location_id:
            # Zielsenke ist die Lokation selbst -> keine sinnvolle Verknuepfung.
            self._conn.execute(
                "UPDATE locations SET shared_history_with=NULL WHERE id=?",
                (location_id,))
            self._conn.commit()
            return 0
        if migrate:
            moved = self.count_history_entries(location_id)
            if moved:
                self._conn.execute(
                    "UPDATE play_history SET location_id=? WHERE location_id=?",
                    (sink, location_id))
        self._conn.execute(
            "UPDATE locations SET shared_history_with=? WHERE id=?",
            (sink, location_id))
        self._conn.commit()
        if migrate and moved:
            self.rebuild_stats_cache()
        print(f"[SongDB] Shared History: #{location_id} -> Senke #{sink} "
              f"({moved} Eintraege umgezogen)")
        return moved

    def get_history_group(self, location_id):
        """BL-178 P2: Gibt (sink_id, [(id, name), ...]) fuer die History-Gruppe
        zurueck — alle Lokationen, die dieselbe Senke teilen (inkl. Senke selbst).
        Bei einer eigenstaendigen Lokation ist die Gruppe nur sie selbst."""
        sink = self._effective_history_id(location_id)
        rows = self._conn.execute(
            "SELECT id, name FROM locations "
            "WHERE id=? OR shared_history_with=? ORDER BY name",
            (sink, sink)).fetchall()
        return sink, rows

    def create_sub_location(self, source_id: int, name: str) -> "Location":
        """BL-178 P2: Legt eine neue Lokation an, die ALLE Einstellungen der
        Quell-Lokation (inkl. Termine) uebernimmt und ihre Historie automatisch
        mit deren Senke teilt. Rueckgabe: die neue Location."""
        src = None
        for loc in self.get_all_locations():
            if loc.id == source_id:
                src = loc
                break
        new_loc = self.insert_location(name)
        if src is not None:
            # Termine normalisieren (auch Alt-Fallback wird als JSON uebernommen).
            import json as _json
            sched = src.schedules
            if not sched and src.schedule_list:
                sched = _json.dumps([{"wd": wd, "from": tf, "to": (tt or "")}
                                     for (wd, tf, tt) in src.schedule_list])
            self.update_location_settings(
                new_loc.id, src.dance_program_id, src.temp_tempo,
                planned_tips=src.planned_tips, break_minutes=src.break_minutes,
                target_bpm=src.target_bpm, tempo_mode=src.tempo_mode,
                schedules=sched)
            # Historie mit der Senke der Quelle teilen (kein Umzug — neu, leer).
            self.set_shared_history(new_loc.id, source_id, migrate=False)
        # Objekt mit aktuellen Werten zurueckgeben.
        for loc in self.get_all_locations():
            if loc.id == new_loc.id:
                return loc
        return new_loc

    def update_location_settings(self, location_id: int,
                                  dance_program_id: Optional[int],
                                  temp_tempo: Optional[float],
                                  planned_tips: Optional[int] = None,
                                  break_minutes: Optional[int] = None,
                                  target_bpm: Optional[float] = None,
                                  tempo_mode: Optional[str] = None,
                                  schedules: Optional[str] = None):
        """Speichert Tanzprogramm, Tempo, Ziel-BPM, Modus, Tips und Pausendauer.

        BL-144: temp_tempo und target_bpm werden BEIDE gespeichert — welcher
        Wert gilt, entscheidet tempo_mode ('percent'|'bpm'). So bleibt die
        prozentuale Vorgabe erhalten, wenn der Caller auf Ziel-BPM umschaltet.

        BL-178: schedules ist eine JSON-Liste von Termin-Tripeln
        [{"wd":2,"from":"19:30","to":"22:00"}, ...] fuer die Start-Auto-Erkennung.
        Leerer Wert -> NULL. Die alten Einzelspalten (weekdays/time_from/time_to)
        werden beim Speichern geleert, damit der Lese-Fallback nicht mehr greift.
        """
        if tempo_mode not in (Location.TEMPO_MODE_PERCENT, Location.TEMPO_MODE_BPM):
            tempo_mode = Location.TEMPO_MODE_PERCENT
        self._conn.execute(
            "UPDATE locations SET dance_program_id=?, temp_tempo=?, target_bpm=?, "
            "tempo_mode=?, planned_tips=?, break_minutes=?, "
            "schedules=?, weekdays=NULL, time_from=NULL, time_to=NULL WHERE id=?;",
            (dance_program_id, temp_tempo, target_bpm, tempo_mode, planned_tips,
             break_minutes, (schedules or None), location_id),
        )
        self._conn.commit()

    # ---- Abspielhistorie ----

    def log_play(self, song_id: int, location_id: Optional[int]):
        """Protokolliert einen Abspielvorgang.

        Drei-Schichten-Update:
          Schicht 1: INSERT in play_history (unveraenderliches Protokoll)
          Schicht 2: UPSERT in song_location_stats (Cache aktualisieren)

        Wird einmal pro frischem Play aufgerufen (nicht bei Resume aus Pause).

        BL-178 P2: Teilt die Lokation ihre Historie, wird unter der Senke
        protokolliert — so sehen alle verknuepften Lokationen dieselben Plays.
        """
        # BL-178 P2: auf die History-fuehrende Senke aufloesen
        location_id = self._effective_history_id(location_id)
        # Schicht 1: Unveraenderliches Protokoll
        self._conn.execute(_INSERT_PLAY_HISTORY, {
            "song_id": song_id,
            "location_id": location_id,
        })

        # Schicht 2: Cache aktualisieren (nur wenn Lokation gesetzt)
        if location_id is not None:
            self._conn.execute(_UPSERT_SONG_LOCATION_STATS, {
                "song_id": song_id,
                "location_id": location_id,
            })

        self._conn.commit()
        print(f"[SongDB] Play protokolliert: Song #{song_id}, Lokation #{location_id}")

    def get_last_played_map(self, location_id: Optional[int]) -> dict:
        """Gibt {song_id: last_played_iso_str} fuer eine Lokation zurueck.

        Nutzt den song_location_stats-Cache (Schicht 2) fuer schnellen Zugriff.
        Gibt leeres Dict zurueck wenn keine Lokation gesetzt ist.
        """
        if location_id is None:
            return {}
        location_id = self._effective_history_id(location_id)  # BL-178 P2
        cur = self._conn.execute(_SELECT_LAST_PLAYED_FOR_LOCATION, {
            "location_id": location_id,
        })
        result = {}
        for row in cur.fetchall():
            song_id = row[0]
            last_played = row[1]  # None wenn nie an dieser Lokation gespielt
            if last_played:
                result[song_id] = last_played
        return result

    # ---- Statistik (BL-019) ----

    @staticmethod
    def _song_type_filter(type_key) -> str:
        return song_types.SQL_FILTER.get(type_key, "")

    def play_counts(self, location_id, since, type_key) -> list:
        """Gespielte Songs als [(song_id, title, label, count)], meistgespielt
        zuerst. location_id=None = alle Lokationen; since = 'YYYY-MM-DD HH:MM:SS'
        oder None; type_key = 'pattern' | 'singing' | 'other' | None.

        Geteilte Historie: Plays stehen unter der Senke (log_play), daher hier
        genauso aufloesen (intern#137)."""
        parts, params = [], {}
        if location_id is not None:
            parts.append("ph.location_id = :loc_id")
            params["loc_id"] = self._effective_history_id(location_id)
        if since is not None:
            parts.append("ph.played_at >= :since")
            params["since"] = since
        if type_filter := self._song_type_filter(type_key):
            parts.append(type_filter)
        where = ("WHERE " + " AND ".join(parts)) if parts else ""
        return self._conn.execute(f"""
            SELECT s.id, s.title, s.label, COUNT(*) AS cnt
            FROM play_history ph
            JOIN songs s ON s.id = ph.song_id
            {where}
            GROUP BY s.id
            ORDER BY cnt DESC
        """, params).fetchall()

    def songs_by_type(self, type_key) -> list:
        """Alle Songs als [(song_id, title, label)], sortiert nach Label/Titel;
        type_key wie bei play_counts."""
        type_filter = self._song_type_filter(type_key)
        where = f"WHERE {type_filter}" if type_filter else ""
        return self._conn.execute(
            f"SELECT s.id, s.title, s.label FROM songs s {where} "
            "ORDER BY s.label, s.title").fetchall()

    def get_planner_candidates(self, target_err: int, location_id,
                               days_fallback: int = 730) -> list:
        """Gibt Songkandidaten fuer den Evening Planner zurueck.

        Liefert alle Songs mit quality > 0, zusammen mit der Anzahl Tage
        seit dem letzten Abspielen an der angegebenen Lokation.
        ERR-Matching und Scoring erfolgen in SongScorer (evening_planner_widget.py).
        Songs mit err=0 (nicht bewertet) erhalten einen niedrigeren Score.

        days_fallback: Tage fuer Songs, die an dieser Lokation noch nie gespielt wurden.
                       Sollte (heute - start_date).days sein.

        Rueckgabe: Liste von Tuples (id, title, label, err, quality,
                                     is_pattern, is_singing, days_since)
        """
        location_id = self._effective_history_id(location_id)  # BL-178 P2
        return self._conn.execute("""
            SELECT s.id, s.title, s.label, s.err, s.quality,
                   s.is_pattern, s.is_singing,
                   COALESCE(
                       CAST(julianday('now') - julianday(sls.last_played) AS INTEGER),
                       ?
                   ) AS days_since,
                   GROUP_CONCAT(g.name, ',') AS genres
            FROM songs s
            LEFT JOIN song_location_stats sls
                   ON s.id = sls.song_id AND sls.location_id = ?
            LEFT JOIN song_genres sg ON s.id = sg.song_id
            LEFT JOIN genres g ON sg.genre_id = g.id
            WHERE s.quality > 0
            GROUP BY s.id
        """, (days_fallback, location_id)).fetchall()

    def get_genres(self) -> list:
        """Gibt alle Genre-Namen aus der genres-Tabelle zurueck, alphabetisch sortiert."""
        rows = self._conn.execute(
            "SELECT name FROM genres ORDER BY name COLLATE NOCASE"
        ).fetchall()
        return [r[0] for r in rows]

    def rebuild_stats_cache(self):
        """Baut song_location_stats aus play_history neu auf.

        Sicherheitsnetz fuer den Fall, dass der Cache inkonsistent wird.
        Im Normalbetrieb nicht noetig.
        """
        self._conn.execute("DELETE FROM song_location_stats;")
        self._conn.execute("""
            INSERT INTO song_location_stats (song_id, location_id, last_played, play_count)
            SELECT song_id, location_id, MAX(played_at), COUNT(*)
            FROM play_history
            WHERE location_id IS NOT NULL
            GROUP BY song_id, location_id;
        """)
        self._conn.commit()
        print("[SongDB] song_location_stats Cache aus play_history neu aufgebaut")

    # ---- Setlist / Reports ----

    def get_setlist(self, location_id: int, date_str: Optional[str] = None) -> list:
        """Chronologische Setlist fuer eine Lokation, optional auf einen Tag gefiltert.

        Returns: [(title, label, played_at), ...] — Duplikate pro Tag entfernt (erster Play).
        """
        location_id = self._effective_history_id(location_id)  # BL-178 P2
        if date_str:
            cur = self._conn.execute("""
                SELECT s.title, s.label, MIN(ph.played_at) AS first_play
                FROM play_history ph
                JOIN songs s ON s.id = ph.song_id
                WHERE ph.location_id = :loc_id
                  AND DATE(ph.played_at) = :date_str
                GROUP BY ph.song_id
                ORDER BY first_play
            """, {"loc_id": location_id, "date_str": date_str})
        else:
            cur = self._conn.execute("""
                SELECT s.title, s.label, MIN(ph.played_at) AS first_play
                FROM play_history ph
                JOIN songs s ON s.id = ph.song_id
                WHERE ph.location_id = :loc_id
                GROUP BY DATE(ph.played_at), ph.song_id
                ORDER BY first_play
            """, {"loc_id": location_id})
        return cur.fetchall()

    def get_setlist_dates(self, location_id: Optional[int] = None) -> list:
        """Alle Tage mit History-Eintraegen, optional gefiltert nach Location.

        Returns: ['2026-03-13', ...] absteigend sortiert (neueste zuerst).
        """
        location_id = self._effective_history_id(location_id)  # BL-178 P2
        if location_id is not None:
            cur = self._conn.execute("""
                SELECT DISTINCT DATE(played_at) AS d
                FROM play_history
                WHERE location_id = :loc_id
                ORDER BY d DESC
            """, {"loc_id": location_id})
        else:
            cur = self._conn.execute("""
                SELECT DISTINCT DATE(played_at) AS d
                FROM play_history
                WHERE location_id IS NOT NULL
                ORDER BY d DESC
            """)
        return [row[0] for row in cur.fetchall()]

    def get_setlist_locations(self, date_str: Optional[str] = None) -> list:
        """Alle Locations mit History-Eintraegen, optional gefiltert nach Datum.

        Returns: [(id, name), ...] alphabetisch sortiert.
        """
        if date_str is not None:
            cur = self._conn.execute("""
                SELECT DISTINCT l.id, l.name
                FROM play_history ph
                JOIN locations l ON l.id = ph.location_id
                WHERE DATE(ph.played_at) = :date_str
                ORDER BY l.name
            """, {"date_str": date_str})
        else:
            cur = self._conn.execute("""
                SELECT DISTINCT l.id, l.name
                FROM play_history ph
                JOIN locations l ON l.id = ph.location_id
                ORDER BY l.name
            """)
        return cur.fetchall()

    # ---- Genre-CRUD ----

    def insert_genre(self, name: str) -> int:
        """Fuegt ein Genre ein (INSERT OR IGNORE) und gibt die ID zurueck."""
        self._conn.execute(_INSERT_GENRE, {"name": name})
        self._conn.commit()
        cur = self._conn.execute("SELECT id FROM genres WHERE name = ?", (name,))
        row = cur.fetchone()
        return row[0] if row else -1

    def get_all_genres(self) -> List[tuple]:
        """Gibt alle Genres als [(id, name), ...] zurueck."""
        cur = self._conn.execute(_SELECT_ALL_GENRES)
        return cur.fetchall()

    def get_genres_for_song(self, song_id: int) -> List[tuple]:
        """Gibt [(genre_id, genre_name), ...] fuer einen Song zurueck."""
        cur = self._conn.execute(_SELECT_GENRES_FOR_SONG, {"song_id": song_id})
        return cur.fetchall()

    def set_genres_for_song(self, song_id: int, genre_ids: List[int]):
        """Setzt die Genres fuer einen Song (ersetzt vorhandene)."""
        self._conn.execute(_DELETE_SONG_GENRES, {"song_id": song_id})
        for gid in genre_ids:
            self._conn.execute(_INSERT_SONG_GENRE, (song_id, gid))
        self._conn.commit()

    def add_song_genre(self, song_id: int, genre_id: int):
        """Fuegt einem Song ein Genre additiv hinzu, ohne bestehende zu loeschen.

        Im Gegensatz zu set_genres_for_song() (DELETE + INSERT) bleibt z.B. das
        automatisch gesetzte "NEW"-Genre (BL-040) erhalten.
        """
        self._conn.execute(_INSERT_SONG_GENRE, (song_id, genre_id))
        self._conn.commit()

    def remove_song_genre(self, song_id: int, genre_id: int):
        """Entfernt EIN Genre von einem Song, ohne die uebrigen anzutasten.
        Gegenstueck zu add_song_genre() — z.B. zum Abraeumen eines
        'CHECK: <Thema>'-Markers, wenn der Caller den Wert korrigiert hat."""
        self._conn.execute(
            "DELETE FROM song_genres WHERE song_id = ? AND genre_id = ?",
            (song_id, genre_id))
        self._conn.commit()

    def _ensure_new_genre_id(self) -> int:
        """Gibt die ID des speziellen "NEW"-Genres zurueck (lazy, gecacht).

        Legt das Genre an, falls es noch fehlt (z.B. in Alt-DBs, die vor BL-040
        ohne erneutes Seeding angelegt wurden).
        """
        if self._new_genre_id is None:
            gid = self.get_genre_id_by_name(_NEW_GENRE_NAME)
            if gid <= 0:
                gid = self.insert_genre(_NEW_GENRE_NAME)
            self._new_genre_id = gid
        return self._new_genre_id

    def get_genre_song_ids(self) -> dict:
        """Gibt {genre_id: set(song_id, ...)} zurueck fuer Filterung.

        Einmal laden, dann in Python filtern — performant bei 500 Songs.
        """
        cur = self._conn.execute(_SELECT_SONG_GENRE_MAP)
        result = {}  # {genre_id: set(song_ids)}
        for song_id, genre_id, _ in cur.fetchall():
            if genre_id not in result:
                result[genre_id] = set()
            result[genre_id].add(song_id)
        return result

    def get_song_genre_names(self) -> dict:
        """Gibt {song_id: [genre_name, ...]} zurueck fuer Anzeige."""
        cur = self._conn.execute(_SELECT_SONG_GENRE_MAP)
        result = {}  # {song_id: [names]}
        for song_id, _, name in cur.fetchall():
            if song_id not in result:
                result[song_id] = []
            result[song_id].append(name)
        return result

    def rename_genre(self, genre_id: int, new_name: str):
        """Benennt ein Genre um."""
        self._conn.execute(_RENAME_GENRE, {"id": genre_id, "name": new_name})
        self._conn.commit()

    def delete_genre(self, genre_id: int, reassign_to_id: int = None):
        """Loescht ein Genre. Optional: Songs auf anderes Genre umbiegen."""
        if reassign_to_id is not None:
            # Duplikate verhindern: nur Songs umbiegen, die das neue Genre noch nicht haben
            self._conn.execute(
                "DELETE FROM song_genres WHERE genre_id = :new_id AND song_id IN "
                "(SELECT song_id FROM song_genres WHERE genre_id = :old_id);",
                {"old_id": genre_id, "new_id": reassign_to_id}
            )
            self._conn.execute(_REASSIGN_SONG_GENRES,
                               {"new_id": reassign_to_id, "old_id": genre_id})
        else:
            self._conn.execute(_DELETE_SONG_GENRE_BY_GENRE, {"genre_id": genre_id})
        self._conn.execute(_DELETE_GENRE, {"id": genre_id})
        self._conn.commit()

    def get_genre_counts(self) -> dict:
        """Gibt {genre_id: song_count} zurueck."""
        cur = self._conn.execute(_SELECT_GENRE_COUNTS)
        return {row[0]: row[1] for row in cur.fetchall()}

    def get_genre_id_by_name(self, name: str) -> int:
        """Gibt die ID eines Genres anhand des Namens zurueck, oder -1."""
        cur = self._conn.execute(_SELECT_GENRE_BY_NAME, {"name": name})
        row = cur.fetchone()
        return row[0] if row else -1

    def seed_default_genres(self):
        """Sorgt fuer das System-Genre 'NEW' (bei JEDEM Start) und saet die
        uebrigen Standard-Genres GENAU EINMAL aus (Flag in app_meta).

        Hintergrund: Frueher lief das komplette Seeding bei jedem Start per
        INSERT OR IGNORE. Vom Nutzer geloeschte Default-Genres (z.B. 'Blues')
        tauchten dadurch beim naechsten Start wieder auf. Jetzt:
        - 'NEW' ist System und wird IMMER sichergestellt (Import-Marker).
        - Alle anderen Defaults kommen nur bei der Erstbefuellung; danach
          respektieren wir Loeschungen des Nutzers.
        """
        # 1) Systemgenre 'NEW' IMMER sicherstellen (Import-Marker, nie geloescht)
        self._conn.execute(_INSERT_GENRE, {"name": "NEW"})

        # 2) Uebrige Defaults nur ein einziges Mal aussaeen
        done = self._conn.execute(
            "SELECT value FROM app_meta WHERE key='default_genres_seeded'"
        ).fetchone()
        if done:
            self._conn.commit()
            return

        # Bestands-DB erkennen: gibt es bereits Genres ausser 'NEW' oder schon
        # Songs? Dann NICHT nachsaeen — sonst kaemen bereits geloeschte
        # Default-Genres zurueck. Nur die Marke setzen und fertig.
        other_genres = self._conn.execute(
            "SELECT 1 FROM genres WHERE name <> 'NEW' LIMIT 1").fetchone()
        has_songs = self._conn.execute("SELECT 1 FROM songs LIMIT 1").fetchone()
        if other_genres or has_songs:
            self._conn.execute(
                "INSERT OR REPLACE INTO app_meta (key, value) "
                "VALUES ('default_genres_seeded', '1')")
            self._conn.commit()
            return

        # Frische DB → volle Default-Liste einmalig aussaeen ('NEW' bereits oben)
        defaults = [
            # Dekaden
            "30s", "40s", "50s", "60s", "70s", "80s", "90s", "2000s and Later",
            # Stilrichtungen
            "Big Band", "Bluegrass", "Blues", "British Invasion", "Broadway",
            "Cajun", "Calypso", "Caribbean", "Country Classic", "Country Modern",
            "Dance", "Disco", "Easy Listening", "Electronic", "Folk", "Gospel",
            "Irish", "Jazz", "Latin", "Motown", "Pop", "R&B / Soul", "Rock",
            "Spanish", "Traditional", "Yodeling",
            # Kuenstler
            "ABBA", "Beatles", "Carpenters", "Elton John", "Elvis Presley",
            "Frank Sinatra", "Garth Brooks", "Jimmy Buffett", "John Denver",
            "Johnny Cash", "Michael Jackson", "Patsy Cline",
            # Themen / Anlaesse
            "Christmas", "Disney", "Halloween", "Holiday", "Love / Valentine",
            "Movies", "Patriotic", "Soundtracks", "Summer", "TV Themes", "Winter",
            # Square Dance spezifisch
            "Called MS", "Called Plus", "Called A1", "Called A2",
            "Female Range", "Line Dance", "Multiple Caller Friendly",
        ]
        for name in defaults:
            self._conn.execute(_INSERT_GENRE, {"name": name})
        # Erstbefuellung erledigt → Marke setzen, damit spaetere Starts nicht
        # erneut aussaeen (geloeschte Genres bleiben geloescht).
        self._conn.execute(
            "INSERT OR REPLACE INTO app_meta (key, value) "
            "VALUES ('default_genres_seeded', '1')")
        self._conn.commit()

    # ── Notizen (BL-008) ──────────────────────────────────────────────────────

    def get_notes(self, location_id: int) -> list:
        """Gibt alle nicht-geloeschten Notizen einer Lokation zurueck,
        sortiert nach sort_order."""
        rows = self._conn.execute("""
            SELECT id, text, status, sort_order, note_type, created_at, done_at
            FROM notes
            WHERE location_id = ? AND status != 'deleted'
            ORDER BY sort_order ASC, id ASC;
        """, (location_id,)).fetchall()
        return [
            {
                "id":         r[0],
                "text":       r[1],
                "status":     r[2],
                "sort_order": r[3],
                "note_type":  r[4],
                "created_at": r[5],
                "done_at":    r[6],
            }
            for r in rows
        ]

    def add_note(self, text: str, location_id: int, *,
                 note_type: str = "normal",
                 sort_order: int = 0,
                 source: str = "manual",
                 source_ref: str = None) -> int:
        """Fuegt eine neue Notiz ein und gibt die neue ID zurueck."""
        cur = self._conn.execute("""
            INSERT INTO notes (text, status, location_id, sort_order,
                               note_type, source, source_ref)
            VALUES (?, 'open', ?, ?, ?, ?, ?);
        """, (text, location_id, sort_order, note_type, source, source_ref))
        self._conn.commit()
        return cur.lastrowid

    def next_note_order(self, location_id: int) -> int:
        """sort_order fuer eine neue Notiz ganz unten (geloeschte zaehlen nicht)."""
        row = self._conn.execute(
            "SELECT MAX(sort_order) FROM notes "
            "WHERE location_id = ? AND status != 'deleted'", (location_id,)).fetchone()
        return (row[0] or 0) + 1

    def set_note_status(self, note_id: int, status: str,
                        done_at: str = None):
        """Setzt den Status einer Notiz (open/done/deleted)."""
        self._conn.execute("""
            UPDATE notes SET status = ?, done_at = ? WHERE id = ?;
        """, (status, done_at, note_id))
        self._conn.commit()

    def update_note_text(self, note_id: int, text: str):
        """Aktualisiert den Text einer bestehenden Notiz."""
        self._conn.execute(
            "UPDATE notes SET text = ? WHERE id = ?;", (text, note_id))
        self._conn.commit()

    def update_notes_order(self, orders: list):
        """Aktualisiert sort_order fuer eine Liste von (note_id, sort_order)."""
        self._conn.executemany(
            "UPDATE notes SET sort_order = ? WHERE id = ?;",
            [(order, note_id) for note_id, order in orders])
        self._conn.commit()

    def delete_notes(self, note_ids: list):
        """Loescht Notizen endgueltig (Papierkorb)."""
        if not note_ids:
            return
        placeholders = ",".join("?" * len(note_ids))
        self._conn.execute(
            f"DELETE FROM notes WHERE id IN ({placeholders});", note_ids)
        self._conn.commit()

    # ---- BL-083: Tanzprogramme ----

    def _insert_default_dance_programs(self):
        """Legt fehlende Default-Programme an und traegt fehlende Figuren-Limits
        einmalig nach.

        - INSERT OR IGNORE ist idempotent: vorhandene Programme (auch vom Nutzer
          bearbeitete) bleiben unangetastet, nur fehlende Codes kommen hinzu —
          jetzt inklusive sequence_limit_to.
        - Backfill: aeltere Nutzer-DBs haben die Programme OHNE sequence_limit_to
          angelegt (das Feld kam erst mit BL-132), weshalb der Sequenz-Limit-
          Filter beim Programmwechsel nichts bewirkte. Die fehlenden Limits
          werden EINMALIG nachgetragen — ueber einen user_version-Waechter, damit
          ein spaeter bewusst auf "kein Limit" (NULL) gesetztes Programm nicht bei
          jedem Start wieder ueberschrieben wird. Nur Zeilen mit NULL werden
          angefasst; selbst gesetzte Limits bleiben unberuehrt.
        """
        self._conn.executemany(
            "INSERT OR IGNORE INTO dance_programs "
            "(code, label, sort_order, target_duration_min, sequence_limit_to) "
            "VALUES (?, ?, ?, ?, ?);",
            _DEFAULT_DANCE_PROGRAMS,
        )
        self._conn.commit()

        ver = self._conn.execute("PRAGMA user_version").fetchone()[0]
        if ver < _DP_LIMIT_BACKFILL_VERSION:
            self._conn.executemany(
                "UPDATE dance_programs SET sequence_limit_to = ? "
                "WHERE code = ? AND sequence_limit_to IS NULL;",
                [(slt, code) for (code, _lbl, _so, _tm, slt)
                 in _DEFAULT_DANCE_PROGRAMS],
            )
            # PRAGMA erlaubt keine Parameter-Bindung; der Wert ist eine eigene
            # Integer-Konstante, daher unbedenklich.
            self._conn.execute(
                f"PRAGMA user_version = {int(_DP_LIMIT_BACKFILL_VERSION)};")
            self._conn.commit()

    # ---- MS50-Reseed: gebuendelte Referenzdaten an Bestandsnutzer verteilen ----

    def backup_copy(self, tag: str) -> str:
        """Kopie der DB-Datei als Wiederherstellungspunkt vor einem riskanten
        Eingriff: '<db>.bak_<tag>_<Zeitstempel>'. Gibt den Pfad zurueck,
        '' wenn keine Datei da ist oder das Kopieren scheitert."""
        import shutil, datetime
        if not self.db_path or not os.path.exists(self.db_path):
            return ""
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        dst = f"{self.db_path}.bak_{tag}_{ts}"
        try:
            self._conn.execute("PRAGMA wal_checkpoint(FULL);")
            shutil.copy(self.db_path, dst)
            print(f"[SongDB] Backup: {os.path.basename(dst)}")
            return dst
        except Exception as e:
            print(f"[SongDB] WARNUNG: Backup '{tag}' fehlgeschlagen: {e}")
            return ""

    def _backup_before_reseed(self):
        """Pflicht-Backup der DB vor dem Reseed (Wiederherstellungspunkt)."""
        self.backup_copy("pre_ms50")

    def reseed_reference_data(self, force: bool = False):
        """MS50-Umbau: verteilt die gebuendelte Referenz (reference_calls.json).

        Laeuft einmal pro REFERENCE_DATA_VERSION (Marke in app_meta). Ersetzt nur
        Referenzdaten; Nutzerdaten bleiben erhalten (eigene Sequenzen, manuelle
        Mappings, dance_programs mit origin='user'). Bestehende Lokationen werden
        auf das 2026-Programmset ihres bisherigen Levels gestellt (Default NEU; die
        alten Listen bleiben waehlbar, der Nutzer kann selbst zurueckstellen).
        """
        import json
        row = self._conn.execute(
            "SELECT value FROM app_meta WHERE key='reference_data_version'").fetchone()
        cur_ver = int(row[0]) if row else 0
        if not force and cur_ver >= REFERENCE_DATA_VERSION:
            return False

        ref_path = os.path.join(os.path.dirname(__file__), "reference_calls.json")
        if not os.path.exists(ref_path):
            print("[SongDB] Reseed uebersprungen: reference_calls.json nicht gefunden")
            return False
        ref = json.load(open(ref_path, encoding="utf-8"))

        # 1) Pflicht-Backup
        self._backup_before_reseed()

        # 2) Alt-Level je Lokation ERFASSEN, bevor dance_programs umgebaut wird.
        old_band = {}
        for lid, slt in self._conn.execute(
            "SELECT l.id, dp.sequence_limit_to FROM locations l "
            "JOIN dance_programs dp ON dp.id = l.dance_program_id "
            "WHERE l.dance_program_id IS NOT NULL").fetchall():
            if slt is not None:
                old_band[lid] = int(slt)

        self._conn.execute("PRAGMA foreign_keys=OFF;")
        try:
            # 3) Merges (Identitaets-Zusammenfuehrungen) auf Mappings
            for frm, into in ref.get("merges", []):
                self._conn.execute(
                    "UPDATE OR IGNORE call_text_mappings SET entity_id=? WHERE entity_id=?",
                    (into, frm))
                self._conn.execute(
                    "DELETE FROM call_text_mappings WHERE entity_id=?", (frm,))
                # BL-210: weitere Figuren der Mengen ziehen mit (bestehende
                # Ziel-Zeile -> OR IGNORE, Rest der Quelle danach weg)
                self._conn.execute(
                    "UPDATE OR IGNORE call_text_figures_extra SET entity_id=? "
                    "WHERE entity_id=?", (into, frm))
                self._conn.execute(
                    "DELETE FROM call_text_figures_extra WHERE entity_id=?", (frm,))
            # 4) call_programs komplett aus Referenz
            self._conn.execute("DELETE FROM call_programs;")
            name_by = {e: n for e, n in
                       self._conn.execute("SELECT entity_id, canonical_name FROM calls")}
            for r in ref["call_programs"]:
                e = r["entity_id"]
                cname = r.get("canonical_name") or name_by.get(e, e)
                # Namen aktuell halten (z.B. Trenner, Forward and Back)
                self._conn.execute(
                    "INSERT INTO calls (entity_id, canonical_name) VALUES (?, ?) "
                    "ON CONFLICT(entity_id) DO UPDATE SET canonical_name=excluded.canonical_name",
                    (e, cname))
                self._conn.execute(
                    "INSERT OR IGNORE INTO call_programs (entity_id, teaching_order, program) "
                    "VALUES (?, ?, ?)", (e, r["teaching_order"], r.get("program", "")))
            # BL-210: nach Merges und neuen Teaching-Orders die hoechste Figur je
            # Menge neu bestimmen, Dubletten Haupt/Zusatz aufloesen
            self._normalize_call_text_figures()
            # 5) Builtin-dance_programs abgleichen (origin='user' bleibt erhalten).
            #    intern#206: per code aktualisieren statt loeschen + neu anlegen. Die
            #    id bleibt so stabil - location_programs, locations.dance_program_id
            #    und die INI (sequences/dance_programs) speichern ids, ein Neuanlegen
            #    liess sie ins Leere zeigen. target_duration_min bleibt, wie der
            #    Nutzer es eingestellt hat.
            #    Geloescht wird nichts mehr: Ein Programm, das die Referenz nicht
            #    mehr fuehrt, bleibt nach der Heilung als eigenes stehen, samt
            #    Lokations-Zuordnung.
            ref_codes = [dp["code"] for dp in ref["dance_programs"]]
            # Heilung: Bis intern#206 schrieb insert_dance_program() kein origin,
            # die Spalte steht auf DEFAULT 'builtin'. Im Tanzprogramm-Manager
            # angelegte (oder dort umbenannte) Programme sahen also aus wie
            # mitgelieferte; das alte DELETE hat sie geloescht (seit 0.139 bei
            # jedem Kunden mit eigenen Programmen). Was weder in der Referenz
            # noch in den Default-Programmen steht, gehoert dem Nutzer.
            known = ref_codes + [code for code, *_ in _DEFAULT_DANCE_PROGRAMS]
            self._conn.execute(
                "UPDATE dance_programs SET origin='user' "
                "WHERE (origin IS NULL OR origin='builtin') "
                f"AND code NOT IN ({','.join('?' * len(known))})", known)
            band_to_pid = {}
            for dp in ref["dance_programs"]:
                band = int(dp["band"])
                self._conn.execute(
                    "INSERT INTO dance_programs "
                    "(code, label, sort_order, target_duration_min, sequence_limit_to, origin) "
                    "VALUES (?, ?, ?, 7.0, ?, 'builtin') "
                    "ON CONFLICT(code) DO UPDATE SET label=excluded.label, "
                    "sort_order=excluded.sort_order, "
                    "sequence_limit_to=excluded.sequence_limit_to, origin='builtin' "
                    "WHERE origin IS NULL OR origin='builtin';",
                    (dp["code"], dp["label"], dp.get("sort_order", band),
                     band + 0.999999))
                # Class-Varianten teilen sich das Band ihres 2026-/Basis-Programms
                # (= gleiche Calls). Fuer die Band->Programm-Zuordnung der Lokations-
                # Migration zaehlt nur das Primaer-Programm, sonst zeigte eine Lokation
                # auf die Class-Variante statt aufs regulaere Programm.
                if not dp.get("is_class"):
                    band_to_pid[band] = self._conn.execute(
                        "SELECT id FROM dance_programs WHERE code=?",
                        (dp["code"],)).fetchone()[0]
            # 6) Lokationen EINMALIG auf das 2026-Set migrieren (Default NEU). Basic 10/20
            #    sind in MS50 (Band 30) absorbiert -> 2026-Baender = 30..100. Nur beim
            #    allerersten Reseed (Flag in app_meta), damit spaetere Referenz-Bumps die
            #    manuell gewaehlte Programm-Zuordnung der Lokationen NICHT zuruecksetzen.
            migrated = self._conn.execute(
                "SELECT value FROM app_meta WHERE key='ms50_locations_migrated'").fetchone()
            if not migrated:
                SET2026 = [30, 40, 50, 60, 70, 80, 90, 100]
                self._conn.execute("DELETE FROM location_programs;")
                for lid, ob in old_band.items():
                    bands = [b for b in SET2026 if b <= ob] or [30]
                    for b in bands:
                        pid = band_to_pid.get(b)
                        if pid:
                            self._conn.execute(
                                "INSERT OR IGNORE INTO location_programs "
                                "(location_id, dance_program_id) VALUES (?, ?)", (lid, pid))
                    top = band_to_pid.get(bands[-1])
                    self._conn.execute(
                        "UPDATE locations SET dance_program_id=? WHERE id=?", (top, lid))
                self._conn.execute(
                    "INSERT OR REPLACE INTO app_meta (key, value) "
                    "VALUES ('ms50_locations_migrated', '1')")
            self._conn.commit()
        finally:
            self._conn.execute("PRAGMA foreign_keys=ON;")

        self._conn.execute(
            "INSERT OR REPLACE INTO app_meta (key, value) VALUES ('reference_data_version', ?)",
            (str(REFERENCE_DATA_VERSION),))
        self._conn.commit()
        print(f"[SongDB] Reseed MS50 fertig: Referenz v{REFERENCE_DATA_VERSION} "
              f"({len(ref['call_programs'])} call_programs, {len(ref['dance_programs'])} Programme, "
              f"{len(old_band)} Lokationen auf 2026 migriert)")
        return True

    def get_all_dance_programs(self) -> list:
        """Gibt alle Tanzprogramme sortiert zurueck: [(id, code, label, sort_order, target_duration_min, sequence_limit_to)]."""
        cur = self._conn.execute(
            "SELECT id, code, label, sort_order, target_duration_min, sequence_limit_to "
            "FROM dance_programs ORDER BY sort_order, code;"
        )
        return cur.fetchall()

    # ---- Lokation -> mehrere Programme (MS50-Umbau, location_programs) ----

    def get_location_program_ids(self, location_id: int) -> list:
        """Gibt die dance_program_id-Liste einer Lokation zurueck (sortiert nach sort_order)."""
        cur = self._conn.execute(
            "SELECT lp.dance_program_id FROM location_programs lp "
            "JOIN dance_programs dp ON dp.id = lp.dance_program_id "
            "WHERE lp.location_id = ? ORDER BY dp.sort_order, dp.code;",
            (location_id,)
        )
        return [r[0] for r in cur.fetchall()]

    def set_location_program_ids(self, location_id: int, program_ids: list):
        """Ersetzt die Programm-Zuordnung einer Lokation (komplett).

        Haelt die Alt-Spalte locations.dance_program_id spiegelnd aktuell
        (erstes Programm oder NULL), damit noch nicht umgestellte Leser weiter
        funktionieren.
        """
        ids = [int(p) for p in (program_ids or [])]
        self._conn.execute(
            "DELETE FROM location_programs WHERE location_id = ?", (location_id,))
        self._conn.executemany(
            "INSERT OR IGNORE INTO location_programs (location_id, dance_program_id) "
            "VALUES (?, ?)", [(location_id, pid) for pid in ids])
        # Kompat-Spiegel
        self._conn.execute(
            "UPDATE locations SET dance_program_id = ? WHERE id = ?",
            (ids[0] if ids else None, location_id))
        self._conn.commit()

    def insert_dance_program(self, code: str, label: str, sort_order: int,
                              target_duration_min: float,
                              sequence_limit_to: float = None) -> int:
        # intern#206: origin='user', sonst greift DEFAULT 'builtin' und ein
        # Referenz-Update haelt das Programm fuer ein mitgeliefertes.
        cur = self._conn.execute(
            "INSERT INTO dance_programs "
            "(code, label, sort_order, target_duration_min, sequence_limit_to, origin) "
            "VALUES (?, ?, ?, ?, ?, 'user');",
            (code.strip(), label.strip(), sort_order, target_duration_min, sequence_limit_to),
        )
        self._conn.commit()
        return cur.lastrowid

    def update_dance_program(self, program_id: int, code: str, label: str,
                              sort_order: int, target_duration_min: float,
                              sequence_limit_to: float = None):
        self._conn.execute(
            "UPDATE dance_programs SET code=?, label=?, sort_order=?, "
            "target_duration_min=?, sequence_limit_to=? WHERE id=?;",
            (code.strip(), label.strip(), sort_order, target_duration_min,
             sequence_limit_to, program_id),
        )
        self._conn.commit()

    def delete_dance_program(self, program_id: int):
        self._conn.execute("DELETE FROM dance_programs WHERE id=?;", (program_id,))
        self._conn.commit()

