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
import json
import re
from dataclasses import dataclass
from typing import Optional, List


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

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS songs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    filename        TEXT    NOT NULL UNIQUE,
    title           TEXT    NOT NULL DEFAULT '',
    artist          TEXT    NOT NULL DEFAULT '',
    label           TEXT    NOT NULL DEFAULT '',
    quality         INTEGER NOT NULL DEFAULT 0,
    base_bpm        REAL    NOT NULL DEFAULT 0.0,
    standard_tempo  REAL    NOT NULL DEFAULT 1.0,
    pitch           REAL    NOT NULL DEFAULT 0.0,
    volume          REAL    NOT NULL DEFAULT 1.0,
    loop_in         REAL    NOT NULL DEFAULT 0.0,
    loop_out        REAL    NOT NULL DEFAULT 0.0,
    loop_offset_ms  REAL    NOT NULL DEFAULT 0.0,
    lyrics_file     TEXT    NOT NULL DEFAULT '',
    is_pattern      INTEGER NOT NULL DEFAULT 1,
    is_singing      INTEGER NOT NULL DEFAULT 1,
    date_added      TEXT    NOT NULL DEFAULT '',
    err             INTEGER NOT NULL DEFAULT 0
);
"""

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

_CREATE_LOCATIONS_TABLE = """
CREATE TABLE IF NOT EXISTS locations (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    name              TEXT    NOT NULL UNIQUE,
    dance_program_id  INTEGER,
    temp_tempo        REAL,
    target_bpm        REAL,
    tempo_mode        TEXT,
    planned_tips      INTEGER,
    break_minutes     INTEGER,
    weekdays          TEXT,
    time_from         TEXT,
    time_to           TEXT,
    schedules         TEXT,
    shared_history_with INTEGER
);
"""

_INSERT_LOCATION = "INSERT INTO locations (name) VALUES (:name);"
_UPDATE_LOCATION = "UPDATE locations SET name = :name WHERE id = :id;"
_SELECT_ALL_LOCATIONS = "SELECT * FROM locations ORDER BY name;"
_DELETE_LOCATION = "DELETE FROM locations WHERE id = :id;"

# ---- SQL-Statements: Genres (M:N mit Songs) ----

_CREATE_GENRES_TABLE = """
CREATE TABLE IF NOT EXISTS genres (
    id   INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT    NOT NULL UNIQUE
);
"""

_CREATE_SONG_GENRES_TABLE = """
CREATE TABLE IF NOT EXISTS song_genres (
    song_id  INTEGER NOT NULL,
    genre_id INTEGER NOT NULL,
    PRIMARY KEY (song_id, genre_id),
    FOREIGN KEY (song_id)  REFERENCES songs(id),
    FOREIGN KEY (genre_id) REFERENCES genres(id)
);
"""

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

# ---- SQL-Statements: Sequenzen (Cached Live-Mapping) ----

_CREATE_SEQUENCES_TABLE = """
CREATE TABLE IF NOT EXISTS sequences (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    field_1             TEXT,
    field_2             TEXT,
    field_3             TEXT,
    field_4             TEXT,
    field_5             TEXT,
    field_6             TEXT,
    field_7             TEXT,
    field_8             TEXT,
    field_9             TEXT,
    field_10            TEXT,
    field_11            TEXT,
    field_12            TEXT,
    field_13            TEXT,
    field_14            TEXT,
    field_15            TEXT,
    level_original      TEXT,
    max_teaching_order  REAL,
    type                TEXT NOT NULL DEFAULT '',
    difficulty          TEXT NOT NULL DEFAULT '',
    -- Volle Callliste als JSON-Array (Source of Truth, hebt die 15-Grenze auf).
    -- field_1..15 bleiben als Rueckwaerts-Mirror der ersten 15 Calls befuellt,
    -- damit AELTERE App-Versionen die DB weiter lesen koennen (calls_json ist
    -- fuer sie eine unbekannte, ignorierte Spalte). Siehe docs/seq_calls_json_umbau.md.
    calls_json          TEXT,
    -- Herkunft: '' = User-eigen/Alt, 'ceder' = ausgelieferter Referenz-Satz.
    -- Erlaubt, den Referenz-Satz sauber zu ersetzen, ohne User-Sequenzen anzufassen.
    source              TEXT NOT NULL DEFAULT '',
    -- BL-191: frei vergebbarer Tag/Kategorie je Sequenz (z.B. "Once and a half",
    -- "Asymmetrische Choreo"). Freitext mit Auto-Vervollstaendigung im Editor,
    -- exakter Filter im Sequences-Widget.
    tags                TEXT NOT NULL DEFAULT ''
);
"""

# MS50-Umbau (2026): Call-Identität von Programm-Zugehörigkeit getrennt, damit ein
# Call in MEHREREN Programmen (Bändern) stehen kann (alt+neu parallel).
#   calls          = stabile Identität (FK-Ziel für call_text_mappings)
#   call_programs  = Zugehörigkeiten, beliebig viele je Call
#   teaching_order_calls = VIEW über beide -> alle bestehenden Leser laufen unverändert
# Konvertierung bestehender DBs: _migrate_calls_split().
_CREATE_CALLS_TABLE = """
CREATE TABLE IF NOT EXISTS calls (
    entity_id       TEXT PRIMARY KEY,
    canonical_name  TEXT NOT NULL
);
"""

_CREATE_CALL_PROGRAMS_TABLE = """
CREATE TABLE IF NOT EXISTS call_programs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_id       TEXT NOT NULL,
    teaching_order  REAL,
    program         TEXT,
    UNIQUE(entity_id, teaching_order),
    FOREIGN KEY (entity_id) REFERENCES calls(entity_id)
);
"""

_CREATE_TOC_VIEW = """
CREATE VIEW IF NOT EXISTS teaching_order_calls AS
    SELECT cp.entity_id, c.canonical_name, cp.teaching_order, cp.program
    FROM call_programs cp
    JOIN calls c ON c.entity_id = cp.entity_id;
"""

_CREATE_CALL_TEXT_MAPPINGS_TABLE = """
CREATE TABLE IF NOT EXISTS call_text_mappings (
    call_text   TEXT PRIMARY KEY,
    entity_id   TEXT,
    mapped_by   TEXT NOT NULL DEFAULT 'auto',
    FOREIGN KEY (entity_id) REFERENCES calls(entity_id)
);
"""

_CREATE_CTM_ENTITY_IDX = """
CREATE INDEX IF NOT EXISTS idx_ctm_entity
    ON call_text_mappings (entity_id);
"""

# BL-210: Ein Call-Text kann einer MENGE von Figuren zugeordnet sein
# ("Chase Right & Roll" = Chase Right + (Anything) & Roll). call_text_mappings
# bleibt 1:1 und haelt die hoechste Figur (aeltere Versionen sehen genau diese
# und liegen beim Limit auf der sicheren Seite); die weiteren Figuren stehen in
# call_text_figures_extra. Die VIEW call_text_figures vereint beide.
# UNION ALL statt UNION: der Dedup-Sort wuerde den grossen Cover-Join treffen;
# disjunkt haelt die Schreibseite (nie Zusatzzeile ohne Hauptzeile, nie
# Zusatzzeile gleich Hauptfigur). Bei leerer Zusatztabelle liefert die VIEW
# zeilen- und reihenfolgengleich dasselbe wie call_text_mappings.
_CREATE_CALL_TEXT_FIGURES_EXTRA_TABLE = """
CREATE TABLE IF NOT EXISTS call_text_figures_extra (
    call_text  TEXT NOT NULL,
    entity_id  TEXT NOT NULL,
    PRIMARY KEY (call_text, entity_id),
    FOREIGN KEY (entity_id) REFERENCES calls(entity_id)
);
"""

_CREATE_CTFE_ENTITY_IDX = """
CREATE INDEX IF NOT EXISTS idx_ctfe_entity
    ON call_text_figures_extra (entity_id);
"""

_CREATE_CALL_TEXT_FIGURES_VIEW = """
CREATE VIEW IF NOT EXISTS call_text_figures AS
    SELECT call_text, entity_id FROM call_text_mappings WHERE entity_id IS NOT NULL
    UNION ALL
    SELECT call_text, entity_id FROM call_text_figures_extra;
"""

# Figuren je Call-Text mit ihrer fruehesten Teaching-Order (NULL = Figur ohne
# call_programs-Zeile). Grundlage fuer die Rangfolge "hoechste Figur zuerst".
_SELECT_CALL_TEXT_FIGURES_RANKED = (
    "SELECT f.call_text, f.entity_id, r.min_to "
    "FROM call_text_figures f "
    "LEFT JOIN (SELECT entity_id, MIN(teaching_order) AS min_to "
    "           FROM call_programs GROUP BY entity_id) r "
    "ON r.entity_id = f.entity_id"
)

_CREATE_SEQ_MAX_TO_IDX = """
CREATE INDEX IF NOT EXISTS idx_sequences_max_to
    ON sequences (max_teaching_order);
"""

# sequence_calls = indizierter enthält-Filter-Index (eine Zeile je Call). Bisher
# nur vom externen Remap-Tool angelegt — jetzt von der App selbst, damit der
# Filter auf jeder DB funktioniert. Wir speichern bewusst NUR (sequence_id,
# position, call_text): kein entity_id, weil das von call_text_mappings abhaengt
# und den Index bei jeder Mapping-Aenderung veralten liesse. Der enthält-Filter
# joint call_text zur Query-Zeit. Damit haengt der Index nur am Sequenz-Inhalt.
_CREATE_SEQUENCE_CALLS_TABLE = """
CREATE TABLE IF NOT EXISTS sequence_calls (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    sequence_id     INTEGER NOT NULL,
    position        INTEGER NOT NULL,
    call_text       TEXT    NOT NULL,
    entity_id       TEXT,
    teaching_order  REAL,
    FOREIGN KEY (sequence_id) REFERENCES sequences(id)
);
"""

_CREATE_SEQCALLS_CALLTEXT_IDX = """
CREATE INDEX IF NOT EXISTS idx_seqcalls_calltext
    ON sequence_calls (call_text);
"""

_INSERT_SEQUENCE = """
INSERT INTO sequences (field_1, field_2, field_3, field_4, field_5,
                       field_6, field_7, field_8, field_9, field_10,
                       field_11, field_12, field_13, field_14, field_15,
                       level_original, max_teaching_order,
                       type, difficulty, calls_json, source, tags)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
"""

_COUNT_SEQUENCES = "SELECT COUNT(*) FROM sequences;"

# ---- SQL-Statements: Abspielhistorie (Drei-Schichten-Architektur) ----

# Schicht 1: Unveraenderliches Protokoll (nur INSERTs)
_CREATE_PLAY_HISTORY_TABLE = """
CREATE TABLE IF NOT EXISTS play_history (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    song_id     INTEGER NOT NULL,
    location_id INTEGER,
    played_at   TEXT    NOT NULL DEFAULT (datetime('now', 'localtime')),
    FOREIGN KEY (song_id)     REFERENCES songs(id),
    FOREIGN KEY (location_id) REFERENCES locations(id)
);
"""

_CREATE_PLAY_HISTORY_INDEX = """
CREATE INDEX IF NOT EXISTS idx_play_history_loc_song
    ON play_history (location_id, song_id, played_at DESC);
"""

# Schicht 2: Materialisierter Cache
_CREATE_SONG_LOCATION_STATS_TABLE = """
CREATE TABLE IF NOT EXISTS song_location_stats (
    song_id     INTEGER NOT NULL,
    location_id INTEGER NOT NULL,
    last_played TEXT    NOT NULL,
    play_count  INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (song_id, location_id),
    FOREIGN KEY (song_id)     REFERENCES songs(id),
    FOREIGN KEY (location_id) REFERENCES locations(id)
);
"""

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

# ---- SQL-Statements: Potential (Datenqualitaets-Checks) ----

_CREATE_POTENTIAL_IGNORED_TABLE = """
CREATE TABLE IF NOT EXISTS potential_ignored (
    check_type  TEXT    NOT NULL,
    entity_id   INTEGER NOT NULL,
    ignored_at  TEXT    NOT NULL DEFAULT (datetime('now', 'localtime')),
    PRIMARY KEY (check_type, entity_id)
);
"""

# BL-008: Notizen
_CREATE_NOTES_TABLE = """
CREATE TABLE IF NOT EXISTS notes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    text        TEXT    NOT NULL DEFAULT '',
    status      TEXT    NOT NULL DEFAULT 'open',
    location_id INTEGER,
    sort_order  INTEGER NOT NULL DEFAULT 0,
    note_type   TEXT    NOT NULL DEFAULT 'normal',
    created_at  TEXT    NOT NULL DEFAULT (datetime('now', 'localtime')),
    done_at     TEXT,
    source      TEXT    NOT NULL DEFAULT 'manual',
    source_ref  TEXT,
    FOREIGN KEY (location_id) REFERENCES locations(id)
);
"""

# BL-083: Tanzprogramm-Levels (MS, PL, A1, A2, C1, C2, C3A)
_CREATE_DANCE_PROGRAMS_TABLE = """
CREATE TABLE IF NOT EXISTS dance_programs (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    code                TEXT    NOT NULL UNIQUE,
    label               TEXT    NOT NULL DEFAULT '',
    sort_order          INTEGER NOT NULL DEFAULT 0,
    target_duration_min REAL    NOT NULL DEFAULT 7.0,
    sequence_limit_to   REAL,
    origin              TEXT    NOT NULL DEFAULT 'builtin'
);
"""

# MS50-Umbau (2026): Eine Lokation kann MEHRERE Tanzprogramme haben (alt+neu
# parallel; wer Plus 2026 tanzt, tanzt MS50 included). Junction-Tabelle statt der
# einen locations.dance_program_id. Die Alt-Spalte bleibt vorerst als Kompatibilitaet
# bestehen; Backfill via _migrate_location_programs().
_CREATE_LOCATION_PROGRAMS_TABLE = """
CREATE TABLE IF NOT EXISTS location_programs (
    location_id       INTEGER NOT NULL,
    dance_program_id  INTEGER NOT NULL,
    PRIMARY KEY (location_id, dance_program_id),
    FOREIGN KEY (location_id) REFERENCES locations(id) ON DELETE CASCADE,
    FOREIGN KEY (dance_program_id) REFERENCES dance_programs(id)
);
"""

# MS50-Umbau: kleiner Key/Value-Speicher fuer Referenzdaten-Version u.ae.
_CREATE_APP_META_TABLE = """
CREATE TABLE IF NOT EXISTS app_meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);
"""

# Version der gebuendelten Referenzdaten (reference_calls.json). Hochzaehlen, wenn
# eine neue Referenz an Bestandsnutzer verteilt werden soll -> Reseed laeuft erneut.
REFERENCE_DATA_VERSION = 3

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

# ---- Migration ----

_MIGRATIONS = [
    # BL-084: Tanzprogramm-Zuweisung pro Lokation
    "ALTER TABLE locations ADD COLUMN dance_program_id INTEGER;",
    # BL-086: Temporaeres Tempo pro Lokation
    "ALTER TABLE locations ADD COLUMN temp_tempo REAL;",
    # BL-144: Ziel-BPM pro Lokation (Zwilling zu temp_tempo)
    "ALTER TABLE locations ADD COLUMN target_bpm REAL;",
    # BL-144: Welcher der beiden Werte gilt ('percent'|'bpm'; NULL = percent)
    "ALTER TABLE locations ADD COLUMN tempo_mode TEXT;",
    # Geplante Anzahl Tips pro Lokation
    "ALTER TABLE locations ADD COLUMN planned_tips INTEGER;",
    # Standard-Pausendauer pro Lokation (Minuten)
    "ALTER TABLE locations ADD COLUMN break_minutes INTEGER;",
    # BL-178 Paket 1: Termin-Angaben pro Lokation (fuer Start-Auto-Erkennung)
    # weekdays: CSV der Wochentage (1=Mo..7=So), z.B. "2,4"; NULL/'' = keine
    "ALTER TABLE locations ADD COLUMN weekdays TEXT;",
    # time_from/time_to: "HH:MM"; NULL = keine Zeitangabe
    "ALTER TABLE locations ADD COLUMN time_from TEXT;",
    "ALTER TABLE locations ADD COLUMN time_to TEXT;",
    # BL-178: Mehrere Termine pro Lokation als JSON-Liste von Tripeln
    # [{"wd":2,"from":"19:30","to":"22:00"}, ...]. Loest die drei Einzelspalten
    # oben ab (die bleiben als Lese-Fallback fuer Altbestand bestehen).
    "ALTER TABLE locations ADD COLUMN schedules TEXT;",
    # BL-178 Paket 2: Shared History. Zeigt (falls gesetzt) auf die "Senke" —
    # die Lokation, die die geteilte Abspielhistorie fuehrt. NULL = eigene History.
    "ALTER TABLE locations ADD COLUMN shared_history_with INTEGER;",
    # P18: Pattern/Singing
    "ALTER TABLE songs ADD COLUMN is_pattern INTEGER NOT NULL DEFAULT 1;",
    "ALTER TABLE songs ADD COLUMN is_singing INTEGER NOT NULL DEFAULT 1;",
    # P20: Clubs -> Locations umbenennen
    "ALTER TABLE clubs RENAME TO locations;",
    # Migration-Tool: Artist-Spalte
    "ALTER TABLE songs ADD COLUMN artist TEXT NOT NULL DEFAULT '';",
    # Loop-Offset: Automatisch gemessener Versatz pro Song (Millisekunden)
    "ALTER TABLE songs ADD COLUMN loop_offset_ms REAL NOT NULL DEFAULT 0.0;",
    # P37: Eintragungsdatum
    "ALTER TABLE songs ADD COLUMN date_added TEXT NOT NULL DEFAULT '';",
    # Ceder-Import: Sequenz-Typ und Schwierigkeitsgrad
    "ALTER TABLE sequences ADD COLUMN type TEXT NOT NULL DEFAULT '';",
    "ALTER TABLE sequences ADD COLUMN difficulty TEXT NOT NULL DEFAULT '';",
    # BL-111: Emotional Response Rate (1=Höhepunkt, 2=Vorbereitung, 3=Baseline, 4=Beruhigung)
    "ALTER TABLE songs ADD COLUMN err INTEGER NOT NULL DEFAULT 0;",
    # BL-XXX: quality-Spalte bereinigen (REAL/TEXT → INTEGER, behebt Crash bei str > int)
    "UPDATE songs SET quality = CAST(ROUND(quality) AS INTEGER) WHERE typeof(quality) != 'integer';",
    # BL-132: Sequenz-Limit pro Tanzprogramm
    "ALTER TABLE dance_programs ADD COLUMN sequence_limit_to REAL;",
    # BL-094: Generische Song-Properties (Key/Value)
    """CREATE TABLE IF NOT EXISTS song_properties (
        song_id INTEGER NOT NULL,
        key     TEXT    NOT NULL,
        value   TEXT    NOT NULL DEFAULT '',
        PRIMARY KEY (song_id, key),
        FOREIGN KEY (song_id) REFERENCES songs(id) ON DELETE CASCADE
    );""",
    # BL-147: Relative Pfade kanonisch mit '/' speichern. Aeltere Versionen
    # haben relative Unterpfade mit Windows-Backslash abgelegt (z.B.
    # 'Sub\\song.mp3'). Das bricht den exakten String-Vergleich in
    # get_by_filename()/UNIQUE. Einmal auf Forward-Slashes normalisieren.
    r"UPDATE songs SET filename = REPLACE(filename, '\', '/') WHERE filename LIKE '%\%';",
    r"UPDATE songs SET lyrics_file = REPLACE(lyrics_file, '\', '/') WHERE lyrics_file LIKE '%\%';",
    # Auch Varianten-Dateipfade (music_2_file, lyric_3_file, ...) normalisieren.
    r"UPDATE song_properties SET value = REPLACE(value, '\', '/') WHERE value LIKE '%\%' AND key LIKE '%file';",
    # Sequenz-Typ-Konsolidierung: zwei/mehr Labels fuer denselben Typ zusammenfuehren.
    # Ursache: der CSDS-/Ceder-Nummern-Import (_SEQTYPE_NAMES in main.py) schrieb
    # abweichende Schreibweisen ("Singing call ..." statt nativ "Singer ...",
    # Bindestrich statt Pfeil). Die UPDATEs sind idempotent — nach dem ersten Lauf
    # matcht ihre WHERE-Klausel nichts mehr. Neuzugaenge werden zusaetzlich am
    # Schreib-Flaschenhals (canonicalize_seq_type in insert/update_sequence)
    # normalisiert; diese Migration raeumt nur den Altbestand auf.
    "UPDATE sequences SET type = 'Singer (Corner progression)' "
    "WHERE type = 'Singing call (Corner progression)';",
    "UPDATE sequences SET type = 'Singer (R-H Lady progression)' "
    "WHERE type = 'Singing call (R-H Lady progression)';",
    "UPDATE sequences SET type = 'Static Set ➔ Resolve' "
    "WHERE type = 'Static Set ➔ Resolve - Complete Dance Routine';",
    # Bindestrich- auf native Pfeil-Form ziehen (Static Set / Zero Line / Zero Box).
    "UPDATE sequences SET type = REPLACE(type, ' - ', ' ➔ ') "
    "WHERE type LIKE 'Static Set - %' OR type LIKE 'Zero Line - %' "
    "OR type LIKE 'Zero Box - %';",
    # Option C: volle Callliste als JSON. field_1..15 bleiben als Mirror.
    # Der Backfill fuer Alt-Zeilen (calls_json IS NULL) laeuft in Python
    # (_backfill_calls_json), weil das Filtern leerer/'-'-Felder in SQL umstaendlich ist.
    "ALTER TABLE sequences ADD COLUMN calls_json TEXT;",
    # Herkunfts-Marke fuer den ausgelieferten Referenz-Satz (siehe CREATE TABLE).
    "ALTER TABLE sequences ADD COLUMN source TEXT NOT NULL DEFAULT '';",
    # BL-191: frei vergebbarer Tag/Kategorie je Sequenz.
    "ALTER TABLE sequences ADD COLUMN tags TEXT NOT NULL DEFAULT '';",
    # MS50-Umbau: Herkunft eines Tanzprogramms (builtin -> vom Reseed pflegbar,
    # user -> vom Nutzer angelegt, bleibt erhalten).
    "ALTER TABLE dance_programs ADD COLUMN origin TEXT NOT NULL DEFAULT 'builtin';",
]

# ---------------------------------------------------------------------------
# Sequenz-Typ-Kanonisierung
# ---------------------------------------------------------------------------
# Ein Sequenz-Typ darf nur EINE Schreibweise haben, sonst zerfaellt der
# Typ-Filter im SequenzView in scheinbar verschiedene Kategorien. Kanonisch ist
# die native Ceder-Konvention: "Singer (...)" (nicht "Singing call (...)") und
# Pfeil "➔" als Trenner (nicht Bindestrich). Diese Tabelle bildet bekannte
# Alt-/Import-Schreibweisen auf die kanonische Form ab; unbekannte Werte bleiben
# unveraendert (nur um Pfeil-Trenner normalisiert).
_SEQ_TYPE_ALIASES = {
    "Singing call (Corner progression)": "Singer (Corner progression)",
    "Singing call (R-H Lady progression)": "Singer (R-H Lady progression)",
    "Static Set ➔ Resolve - Complete Dance Routine": "Static Set ➔ Resolve",
}


def canonicalize_seq_type(raw: str) -> str:
    """Fuehrt einen Sequenz-Typ auf seine kanonische Schreibweise zurueck.

    Anwenden an JEDER Schreibstelle (Import, Editor), damit nie zwei Labels fuer
    denselben Typ entstehen. Idempotent: canonicalize(canonicalize(x)) == canonicalize(x).
    """
    if not raw:
        return ""
    value = raw.strip()
    # "- Complete Dance Routine" ist ein Special-Tag (Ceder special=15), kein
    # eigener Typ — an jeden Basistyp anhaengbar (Static Set, Six Couples ...).
    # Generisch abstreifen, damit keine Schatten-Kategorien entstehen.
    _CDR = " - Complete Dance Routine"
    if value.endswith(_CDR):
        value = value[:-len(_CDR)]
    # Bindestrich-Trenner der "X - Y"-Resolve-Typen auf native Pfeil-Form ziehen.
    if value.startswith(("Static Set - ", "Zero Line - ", "Zero Box - ")):
        value = value.replace(" - ", " ➔ ", 1)
    return _SEQ_TYPE_ALIASES.get(value, value)


# ---------------------------------------------------------------------------
# Sequenz-Calllisten: JSON <-> Liste, Mirror-Felder
# ---------------------------------------------------------------------------
# calls_json ist die Source of Truth (beliebig viele Calls). field_1..15 werden
# als Mirror der ersten 15 mitgefuehrt (Rueckwaerts-Kompatibilitaet fuer aeltere
# App-Versionen). Beide entstehen aus DERSELBEN bereinigten Liste, damit nichts
# auseinanderlaeuft. Bereinigung = strip + leere/'-'-Platzhalter raus (identisch
# zur bisherigen get_sequence_calls-Logik, damit der Alt-Bestand bitgleich bleibt).

def clean_calls(calls) -> list:
    """Bereinigt eine rohe Callliste: strip, leere und '-'-Platzhalter entfernen."""
    out = []
    for c in (calls or []):
        if c is None:
            continue
        s = str(c).strip()
        if s and s != "-":
            out.append(s)
    return out


def calls_to_json(calls) -> str:
    """Bereinigte Callliste als JSON-Array-String (UTF-8, keine ASCII-Escapes)."""
    return json.dumps(clean_calls(calls), ensure_ascii=False)


def calls_from_json(raw) -> list:
    """JSON-Array-String -> Liste. Leer/ungueltig -> []."""
    if not raw:
        return []
    try:
        val = json.loads(raw)
        return val if isinstance(val, list) else []
    except (ValueError, TypeError):
        return []


def calls_to_mirror_fields(calls) -> list:
    """Erste 15 bereinigte Calls, auf genau 15 mit None aufgefuellt (Mirror)."""
    cleaned = clean_calls(calls)[:15]
    return cleaned + [None] * (15 - len(cleaned))

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


class SongDatabase:
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
        self._migrate()         # Zuerst: bestehende Tabellen umbenennen/erweitern
        self._create_tables()   # Dann: fehlende Tabellen anlegen (IF NOT EXISTS)
        self._backfill_calls_json()  # Option C: calls_json aus field_1..15 fuellen
        self._ensure_sequence_calls_index()  # enthält-Filter-Index sicherstellen
        self.reseed_reference_data()  # MS50: gebuendelte Referenz einspielen (einmalig)
        self._backfill_auto_mappings_once()  # heilt ungemappte Massenimporte (einmalig)
        print(f"[SongDB] Datenbank geoeffnet: {db_path}")

    def _backfill_calls_json(self):
        """Fuellt calls_json fuer Alt-Zeilen aus field_1..15 (Option C).

        Selbst-abgesichert: verarbeitet nur Zeilen mit calls_json IS NULL. Nach
        dem ersten Lauf sind das keine mehr -> die Pruefung ist danach ein
        billiger Count. Neu eingefuegte Zeilen setzen calls_json ohnehin direkt.
        Baut die Liste bitgleich zur get_sequence_calls-Logik (strip, '-'/leer raus).
        """
        # Spalte vorhanden? (falls Migration auf einer Uralt-DB scheiterte)
        cols = [r[1] for r in self._conn.execute("PRAGMA table_info(sequences)")]
        if "calls_json" not in cols:
            return
        rows = self._conn.execute(
            "SELECT id, field_1, field_2, field_3, field_4, field_5, "
            "field_6, field_7, field_8, field_9, field_10, "
            "field_11, field_12, field_13, field_14, field_15 "
            "FROM sequences WHERE calls_json IS NULL"
        ).fetchall()
        if not rows:
            return
        updates = [(calls_to_json(row[1:16]), row[0]) for row in rows]
        self._conn.executemany(
            "UPDATE sequences SET calls_json = ? WHERE id = ?", updates)
        self._conn.commit()
        print(f"[SongDB] calls_json-Backfill: {len(updates)} Sequenzen gefuellt")

    # ---- enthält-Filter-Index (sequence_calls) ----

    def _sync_sequence_calls_for(self, seq_id: int, calls) -> None:
        """Aktualisiert die Index-Zeilen EINER Sequenz (kein commit hier).

        Loescht die alten Zeilen und legt je Call eine neue an (nur sequence_id,
        position, call_text). Aufrufer committet."""
        self._conn.execute(
            "DELETE FROM sequence_calls WHERE sequence_id = ?", (seq_id,))
        cleaned = clean_calls(calls)
        if cleaned:
            self._conn.executemany(
                "INSERT INTO sequence_calls (sequence_id, position, call_text) "
                "VALUES (?, ?, ?)",
                [(seq_id, i + 1, t) for i, t in enumerate(cleaned)])

    def rebuild_sequence_calls_index(self) -> int:
        """Baut den kompletten enthält-Filter-Index aus calls_json neu auf.

        Aufrufen nach Massen-Importen (Roh-INSERTs, die insert_sequence umgehen)
        oder wenn der Index veraltet ist. Gibt die Zeilenzahl zurueck."""
        self._conn.execute("DELETE FROM sequence_calls")
        ins = []
        for sid, cj in self._conn.execute("SELECT id, calls_json FROM sequences"):
            for pos, text in enumerate(calls_from_json(cj), start=1):
                ins.append((sid, pos, text))
        if ins:
            self._conn.executemany(
                "INSERT INTO sequence_calls (sequence_id, position, call_text) "
                "VALUES (?, ?, ?)", ins)
        self._conn.commit()
        print(f"[SongDB] sequence_calls-Index neu gebaut: {len(ins)} Zeilen")
        return len(ins)

    def _ensure_sequence_calls_index(self) -> None:
        """Baut den Index beim Oeffnen neu, falls er fehlt oder veraltet ist.

        Vergleicht die Zahl der indizierten Sequenzen mit der Zahl der Sequenzen
        mit mind. einem Call. Stimmt sie nicht (leer, teilbefuellt, Altbestand vom
        externen Remap-Tool), wird neu gebaut. Im Normalfall (synchron) passiert
        nichts."""
        try:
            want = self._conn.execute(
                "SELECT COUNT(*) FROM sequences "
                "WHERE calls_json IS NOT NULL AND calls_json != '[]'"
            ).fetchone()[0]
            have = self._conn.execute(
                "SELECT COUNT(DISTINCT sequence_id) FROM sequence_calls"
            ).fetchone()[0]
        except sqlite3.OperationalError:
            return  # Tabelle fehlt (Uralt-DB) — _create_tables legt sie noch an
        if have != want:
            self.rebuild_sequence_calls_index()

    def _create_tables(self):
        self._conn.execute(_CREATE_TABLE)
        self._conn.execute(_CREATE_LOCATIONS_TABLE)
        self._conn.execute(_CREATE_GENRES_TABLE)
        self._conn.execute(_CREATE_SONG_GENRES_TABLE)
        self._conn.execute(_CREATE_PLAY_HISTORY_TABLE)
        self._conn.execute(_CREATE_PLAY_HISTORY_INDEX)
        self._conn.execute(_CREATE_SONG_LOCATION_STATS_TABLE)
        self._conn.execute(_CREATE_SEQUENCES_TABLE)
        self._conn.execute(_CREATE_CALLS_TABLE)
        self._conn.execute(_CREATE_CALL_PROGRAMS_TABLE)
        self._conn.execute(_CREATE_TOC_VIEW)
        self._conn.execute(_CREATE_CALL_TEXT_MAPPINGS_TABLE)
        self._conn.execute(_CREATE_CTM_ENTITY_IDX)
        self._conn.execute(_CREATE_CALL_TEXT_FIGURES_EXTRA_TABLE)
        self._conn.execute(_CREATE_CTFE_ENTITY_IDX)
        self._conn.execute(_CREATE_CALL_TEXT_FIGURES_VIEW)
        self._conn.execute(_CREATE_SEQ_MAX_TO_IDX)
        self._conn.execute(_CREATE_SEQUENCE_CALLS_TABLE)
        self._conn.execute(_CREATE_SEQCALLS_CALLTEXT_IDX)
        self._conn.execute(_CREATE_POTENTIAL_IGNORED_TABLE)
        self._conn.execute(_CREATE_NOTES_TABLE)
        self._conn.execute(_CREATE_DANCE_PROGRAMS_TABLE)
        self._conn.execute(_CREATE_LOCATION_PROGRAMS_TABLE)
        self._conn.execute(_CREATE_APP_META_TABLE)
        self._create_band_cache_triggers()
        self._conn.commit()
        self._insert_default_dance_programs()

    def _create_band_cache_triggers(self):
        """MS50-Perf: Versions-Zaehler fuer den Band-Cache. Jede Aenderung an den
        Tabellen, die das "welche Sequenz ist mit diesen Baendern tanzbar"-Ergebnis
        beeinflussen (sequences, sequence_calls, call_text_mappings,
        call_text_figures_extra, call_programs), erhoeht `v`. Der Band-Cache
        vergleicht `v` und verwirft sich bei Aenderung selbst — so kann kein
        einzelner Writer vergessen werden."""
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS _band_cache_ver (v INTEGER NOT NULL)")
        self._conn.execute(
            "INSERT INTO _band_cache_ver (v) SELECT 0 "
            "WHERE NOT EXISTS (SELECT 1 FROM _band_cache_ver)")
        # Persistenter Cover-Cache (B): das teure _cover_ids-Ergebnis pro
        # Band-Auswahl EINMAL rechnen und ueber Neustarts hinweg halten. Gestempelt
        # mit dem `v`, bei dem es galt -> bei Datenaenderung (Trigger erhoeht v)
        # verfehlt der Lookup und rechnet einmal neu. cache_key ist PRIMARY KEY ->
        # genau eine (aktuelle) Zeile je Auswahl. ids als CSV der Sequenz-IDs.
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS _band_cover ("
            "cache_key TEXT PRIMARY KEY, ver INTEGER NOT NULL, ids TEXT NOT NULL)")
        for tbl in ("sequences", "sequence_calls", "call_text_mappings",
                    "call_text_figures_extra", "call_programs"):
            for op, when in (("ins", "AFTER INSERT"),
                             ("upd", "AFTER UPDATE"),
                             ("del", "AFTER DELETE")):
                self._conn.execute(
                    f"CREATE TRIGGER IF NOT EXISTS _bcv_{tbl}_{op} "
                    f"{when} ON {tbl} BEGIN "
                    f"UPDATE _band_cache_ver SET v = v + 1; END;")

    def _migrate(self):
        """Fuehrt DB-Migrationen aus (neue Spalten, Tabellen-Umbenennungen).

        Jede Migration ist idempotent-sicher:
        Falls die Aenderung schon existiert, wirft SQLite einen Fehler,
        den wir einfach ignorieren.
        """
        for sql in _MIGRATIONS:
            try:
                self._conn.execute(sql)
                self._conn.commit()
                _safe_print(f"[SongDB] Migration: {sql.strip()[:60]}...")
            except sqlite3.OperationalError:
                pass  # Spalte/Tabelle existiert bereits bzw. Quell-Tabelle fehlt

        # Sonderfall: Falls clubs UND locations beide existieren (z.B. nach
        # abgebrochenem erstem Start), Daten aus clubs nach locations kopieren
        # und clubs-Tabelle loeschen.
        cur = self._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='clubs'"
        )
        if cur.fetchone():
            cur2 = self._conn.execute("SELECT id, name FROM clubs")
            for row in cur2.fetchall():
                try:
                    self._conn.execute(
                        "INSERT INTO locations (id, name) VALUES (?, ?)",
                        (row[0], row[1])
                    )
                except sqlite3.IntegrityError:
                    pass  # Lokation mit gleicher ID oder Name existiert bereits
            self._conn.execute("DROP TABLE clubs")
            self._conn.commit()
            print("[SongDB] Migration: clubs-Reste nach locations uebernommen")

        self._migrate_calls_split()
        self._migrate_location_programs()

    def _migrate_location_programs(self):
        """MS50-Umbau: Backfill der Junction-Tabelle location_programs.

        Einmalig: nur wenn die Tabelle noch nicht existiert. Danach uebernimmt sie
        die Wahrheit; ein Nutzer, der spaeter alle Programme einer Lokation
        entfernt, bekommt sie NICHT wieder aufgezwungen.
        """
        exists = self._conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='location_programs'"
        ).fetchone()
        if exists:
            return
        self._conn.execute(_CREATE_LOCATION_PROGRAMS_TABLE)
        # locations-Tabelle da? (frische DB: noch nicht -> _create_tables macht sie)
        has_loc = self._conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='locations'"
        ).fetchone()
        if has_loc:
            n = self._conn.execute(
                "INSERT OR IGNORE INTO location_programs (location_id, dance_program_id) "
                "SELECT id, dance_program_id FROM locations WHERE dance_program_id IS NOT NULL"
            ).rowcount
            self._conn.commit()
            if n:
                print(f"[SongDB] Migration MS50: {n} Lokations-Programme nach location_programs uebernommen")

    def _migrate_calls_split(self):
        """MS50-Umbau: teaching_order_calls (Tabelle) -> calls + call_programs + View.

        Einmalig und idempotent: laeuft nur, solange teaching_order_calls noch eine
        TABELLE ist. Nach der Konvertierung ist es eine VIEW (type='view'), der
        Detektor greift nicht mehr. Ein Call kann danach in mehreren Programmen
        (Baendern) stehen. call_text_mappings.entity_id zeigt danach auf calls().
        """
        row = self._conn.execute(
            "SELECT type FROM sqlite_master WHERE name='teaching_order_calls'"
        ).fetchone()
        if not row or row[0] != 'table':
            return  # bereits konvertiert (View) oder frische DB (kommt aus _create_tables)

        print("[SongDB] Migration MS50: splitte teaching_order_calls -> calls + call_programs ...")
        # FK-Enforcement kurz aus, damit Tabellen-Umbau (DROP/RENAME) sauber laeuft.
        self._conn.execute("PRAGMA foreign_keys=OFF;")
        try:
            self._conn.execute(_CREATE_CALLS_TABLE)
            self._conn.execute(_CREATE_CALL_PROGRAMS_TABLE)
            # Identitaeten (entity_id war PK -> je Call genau eine Zeile)
            self._conn.execute(
                "INSERT OR IGNORE INTO calls (entity_id, canonical_name) "
                "SELECT entity_id, canonical_name FROM teaching_order_calls"
            )
            # Zugehoerigkeiten (aktuell genau eine je Call)
            self._conn.execute(
                "INSERT OR IGNORE INTO call_programs (entity_id, teaching_order, program) "
                "SELECT entity_id, teaching_order, program FROM teaching_order_calls"
            )
            self._conn.execute("DROP TABLE teaching_order_calls")
            self._conn.execute(_CREATE_TOC_VIEW)

            # call_text_mappings: FK zeigte auf teaching_order_calls (jetzt View) ->
            # Tabelle mit FK auf calls() neu aufbauen, Daten uebernehmen.
            self._conn.execute("ALTER TABLE call_text_mappings RENAME TO _ctm_old")
            self._conn.execute(_CREATE_CALL_TEXT_MAPPINGS_TABLE)
            self._conn.execute(
                "INSERT INTO call_text_mappings (call_text, entity_id, mapped_by) "
                "SELECT call_text, entity_id, mapped_by FROM _ctm_old"
            )
            self._conn.execute("DROP TABLE _ctm_old")
            self._conn.execute(_CREATE_CTM_ENTITY_IDX)
            self._conn.commit()
        finally:
            self._conn.execute("PRAGMA foreign_keys=ON;")
        # Sanity: nur die Invariante DIESER Migration pruefen — jede
        # call_programs.entity_id muss in calls existieren. (Vorbestehende
        # verwaiste call_text_mappings/song_properties absichtlich NICHT pruefen;
        # die gab es schon vorher und die App lebt seit jeher damit.)
        orphan = self._conn.execute(
            "SELECT COUNT(*) FROM call_programs WHERE entity_id NOT IN "
            "(SELECT entity_id FROM calls)"
        ).fetchone()[0]
        if orphan:
            print(f"[SongDB] WARNUNG MS50-Migration: {orphan} call_programs ohne calls-Identitaet")
        n_calls = self._conn.execute("SELECT COUNT(*) FROM calls").fetchone()[0]
        n_prog = self._conn.execute("SELECT COUNT(*) FROM call_programs").fetchone()[0]
        print(f"[SongDB] Migration MS50 fertig: {n_calls} calls, {n_prog} call_programs")

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

    # ---- Calls eines Tanzprogramms (BL-199) ----

    def get_calls_for_program(self, program_label: str) -> list:
        """Alle echten Calls eines Programms, nach Teaching-Order sortiert.

        program_label ist das in call_programs.program gespeicherte Programm-
        Label (z. B. "Mainstream (2026)"), NICHT der dance_programs.code.
        Trenner-Eintraege ("-- ... --") werden herausgefiltert, Duplikate
        (mehrere teaching_order-Zeilen je Call) zusammengefasst.

        Returns:
            Liste von (entity_id, canonical_name).
        """
        if not program_label:
            return []
        cur = self._conn.execute(
            "SELECT c.entity_id, c.canonical_name "
            "FROM call_programs cp JOIN calls c ON c.entity_id = cp.entity_id "
            "WHERE cp.program = ? AND c.canonical_name NOT LIKE '--%' "
            "ORDER BY cp.teaching_order, c.canonical_name;",
            (program_label,)
        )
        seen = set()
        out = []
        for eid, name in cur.fetchall():
            if eid in seen:
                continue
            seen.add(eid)
            out.append((eid, name))
        return out

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

        # Neuer Song: Titel = Dateiname ohne Endung, beide Typen aktiv
        title = os.path.splitext(filename)[0]
        song = Song(filename=filename, title=title,
                    is_pattern=1, is_singing=1)
        return self.insert(song)

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

    # ---- Sequenzen-CRUD ----

    def insert_sequence(self, fields: list, level_original: str = "",
                        max_teaching_order: float = None,
                        seq_type: str = "", difficulty: str = "",
                        source: str = "", tags: str = "") -> int:
        """Fuegt eine Sequenz ein und gibt die ID zurueck.

        Args:
            fields: Liste von Call-Texten (wird auf 15 Felder aufgefuellt)
            level_original: Original-Level-Text (z.B. "Mainstream - SSD Week 9")
            max_teaching_order: Vorberechnete hoechste Teaching-Order
            seq_type: Sequenz-Typ (z.B. "Singer (Corner progression)")
            difficulty: Schwierigkeitsgrad (z.B. "Easy", "Medium", "Hard")
        """
        # calls_json = volle Liste (Source of Truth); field_1..15 = Mirror der
        # ersten 15 (Rueckwaerts-Kompatibilitaet). Beide aus derselben Liste.
        mirror = calls_to_mirror_fields(fields)
        params = mirror + [level_original, max_teaching_order,
                           canonicalize_seq_type(seq_type), difficulty or "",
                           calls_to_json(fields), source or "", tags or ""]
        cur = self._conn.execute(_INSERT_SEQUENCE, params)
        seq_id = cur.lastrowid
        self._sync_sequence_calls_for(seq_id, fields)
        self._conn.commit()
        return seq_id

    def bulk_import_sequences(self, seqs, source: str = "",
                              replace_source: bool = False,
                              dedup_against_existing: bool = True) -> tuple:
        """Fuegt VIELE Sequenzen effizient ein — eine Transaktion, Index +
        max_teaching_order werden EINMAL am Ende aufgebaut (nicht pro Zeile).
        Ersetzt das langsame Schleifen-insert_sequence fuer Massen-Importe.

        Args:
            seqs: iterable von dicts {calls, level, seq_type, difficulty}.
            source: Herkunfts-Marke der neuen Zeilen ('' = User, 'ceder' = Referenz).
            replace_source: True -> vorher ALLE Zeilen mit genau diesem source
                loeschen (sauberes Ersetzen des Referenz-Satzes; User-Sequenzen
                mit anderem source bleiben unberuehrt).
            dedup_against_existing: True -> Sequenzen ueberspringen, deren calls_json
                schon in der DB existiert (nach evtl. replace_source) oder im Batch
                doppelt ist. Verhindert Doppelungen gegen User-eigene Sequenzen.

        Returns:
            (inserted, skipped)
        """
        if replace_source:
            self._conn.execute(
                "DELETE FROM sequence_calls WHERE sequence_id IN "
                "(SELECT id FROM sequences WHERE source = ?)", (source or "",))
            self._conn.execute("DELETE FROM sequences WHERE source = ?",
                               (source or "",))

        existing = set()
        if dedup_against_existing:
            existing = {r[0] for r in self._conn.execute(
                "SELECT calls_json FROM sequences WHERE calls_json IS NOT NULL")}

        rows = []
        skipped = 0
        batch_seen = set()
        for s in seqs:
            meta = s if isinstance(s, dict) else {}
            calls = meta.get("calls") if isinstance(s, dict) else s
            cleaned = clean_calls(calls)
            if not cleaned:
                skipped += 1
                continue
            cj = calls_to_json(cleaned)
            if dedup_against_existing and (cj in existing or cj in batch_seen):
                skipped += 1
                continue
            batch_seen.add(cj)
            mirror = calls_to_mirror_fields(cleaned)
            rows.append(tuple(mirror) + (
                meta.get("level", "") or "", None,
                canonicalize_seq_type(meta.get("seq_type", "") or ""),
                meta.get("difficulty", "") or "", cj, source or ""))

        if rows:
            self._conn.executemany(
                "INSERT INTO sequences (field_1, field_2, field_3, field_4, "
                "field_5, field_6, field_7, field_8, field_9, field_10, "
                "field_11, field_12, field_13, field_14, field_15, "
                "level_original, max_teaching_order, type, difficulty, "
                "calls_json, source) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
        self._conn.commit()
        # Index + Cache einmal aufbauen (Bulk-INSERT umging insert_sequence).
        self.rebuild_sequence_calls_index()
        # Auto-Mappings fuer die neuen Call-Texte anlegen — sonst bliebe der Import
        # voellig ungemappt und der Band-Filter (Programmwahl) zeigte 0 Sequenzen.
        self.backfill_auto_mappings()
        self.recompute_sequence_max_to()
        return (len(rows), skipped)

    def get_sequence_count(self) -> int:
        """Anzahl aller Sequenzen in der Datenbank."""
        cur = self._conn.execute(_COUNT_SEQUENCES)
        return cur.fetchone()[0]

    def get_all_sequences_for_export(self) -> list[dict]:
        """Gibt alle Sequenzen im JSON-Import-Format zurueck (calls, level, seq_type, difficulty)."""
        cur = self._conn.execute(
            "SELECT id, calls_json, field_1, field_2, field_3, field_4, field_5, "
            "field_6, field_7, field_8, field_9, field_10, "
            "field_11, field_12, field_13, field_14, field_15, "
            "level_original, type, difficulty "
            "FROM sequences ORDER BY id"
        )
        result = []
        for row in cur.fetchall():
            seq_id = row[0]
            # Volle Liste aus calls_json (Fallback: Mirror-Felder row[2:17]).
            calls = calls_from_json(row[1]) if row[1] else clean_calls(row[2:17])
            result.append({
                "id": str(seq_id),
                "calls": calls,
                "level": row[17] or "",
                "seq_type": row[18] or "",
                "difficulty": row[19] or "",
            })
        return result

    # ---- MS50-Perf: Band-Cover-Cache + Scope-Materialisierung ----

    def _band_data_version(self) -> int:
        """Aktueller Wert des Trigger-Zaehlers (0 falls Tabelle fehlt)."""
        try:
            row = self._conn.execute("SELECT v FROM _band_cache_ver").fetchone()
            return int(row[0]) if row else 0
        except Exception:
            return 0

    def _check_band_cache_version(self):
        """Verwirft den Band-Cache, sobald sich relevante Daten geaendert haben
        (sequences/sequence_calls/call_text_mappings/call_programs -> Trigger)."""
        ver = self._band_data_version()
        if ver != self._band_cache_ver_seen:
            self._band_cover_cache = {}
            self._scope_key = None
            self._band_cache_ver_seen = ver

    def _cover_ids(self, bandset: frozenset, max_to: float = None) -> frozenset:
        """Menge der Sequenz-IDs, deren gemappte Figuren ALLE in mindestens einem der
        Baender liegen (aggregiert pro Figur -> Mehrfachnennung korrekt). Optional
        begrenzt max_to die Figuren zusaetzlich auf Teaching-Position <= max_to (feiner
        Limit-Filter). Ergebnis je (Band-Menge, max_to) gecacht — der eine teure
        Durchlauf, der frueher 3-6x pro Wechsel lief."""
        if not bandset:
            return frozenset()
        key = (bandset, max_to)
        cached = self._band_cover_cache.get(key)
        if cached is not None:
            return cached
        bands = sorted(bandset)
        # Persistenter Cover-Cache (B): erst in _band_cover nachschlagen. Der
        # Eintrag ist mit dem `v` gestempelt, bei dem er galt; passt es zum
        # aktuellen `v`, koennen wir den teuren 97k-Zeilen-Join komplett sparen —
        # auch ueber Neustarts hinweg. cache_key ist stabil aus Band-Menge + Limit.
        ck = f"{bands}|{max_to}"
        ver = self._band_data_version()
        try:
            prow = self._conn.execute(
                "SELECT ids FROM _band_cover WHERE cache_key=? AND ver=?",
                (ck, ver)).fetchone()
        except sqlite3.OperationalError:
            prow = None   # Tabelle (noch) nicht vorhanden (alte DB vor Migration)
        if prow is not None:
            ids = (frozenset(int(x) for x in prow[0].split(","))
                   if prow[0] else frozenset())
            self._band_cover_cache[key] = ids
            return ids
        ph = ",".join("?" for _ in bands)
        # Eine Figur "zaehlt" nur, wenn sie eine Band-Zeile im gewaehlten Band hat
        # UND (bei gesetztem Limit) an einer Teaching-Position <= max_to liegt. So
        # wirkt der Limit feingranular INNERHALB eines Bandes (z.B. Spin Chain Thru
        # vor Recycle, obwohl beide in Band 29).
        if max_to is None:
            cond = f"CAST(cp.teaching_order AS INTEGER) IN ({ph})"
            params = bands
        else:
            cond = (f"CAST(cp.teaching_order AS INTEGER) IN ({ph}) "
                    f"AND cp.teaching_order <= ?")
            params = bands + [max_to]
        sql = f"""SELECT sid FROM (
                    SELECT sc.sequence_id AS sid, m.entity_id AS eid,
                           MAX(CASE WHEN {cond}
                                    THEN 1 ELSE 0 END) AS covered
                    FROM sequence_calls sc
                    JOIN call_text_figures m
                         ON m.call_text = sc.call_text
                    JOIN call_programs cp ON cp.entity_id = m.entity_id
                    GROUP BY sc.sequence_id, m.entity_id
                  )
                  GROUP BY sid HAVING MIN(covered) = 1"""
        ids = frozenset(r[0] for r in self._conn.execute(sql, params))
        self._band_cover_cache[key] = ids
        # Ergebnis persistieren (B): einmal rechnen, ueber Neustarts halten. Bei
        # Datenaenderung erhoeht der Trigger `v` -> dieser Eintrag passt nicht mehr
        # und wird beim naechsten Miss durch INSERT OR REPLACE aktualisiert.
        try:
            self._conn.execute(
                "INSERT OR REPLACE INTO _band_cover (cache_key, ver, ids) "
                "VALUES (?, ?, ?)",
                (ck, ver, ",".join(str(i) for i in sorted(ids))))
            self._conn.commit()
        except sqlite3.OperationalError:
            pass   # Tabelle fehlt (alte DB) -> nur In-Memory-Cache, kein Persist
        return ids

    def _ensure_band_scope(self, bands_filter, bands_below_filter, cover_max_to=None):
        """Materialisiert die aktuell gefilterte Band-ID-Menge (Baender minus 'below'
        fuer "Only", optional mit feiner Limit-Obergrenze cover_max_to) in der TEMP-
        Tabelle seq_scope. Rechnet nur neu, wenn sich Band-Menge, Limit oder Daten
        aenderten. Danach lesen count/page/ids alle billig aus seq_scope."""
        self._check_band_cache_version()
        bkey = frozenset(int(b) for b in bands_filter) if bands_filter else frozenset()
        lkey = (frozenset(int(b) for b in bands_below_filter)
                if bands_below_filter else frozenset())
        key = (bkey, lkey, cover_max_to)
        if key == self._scope_key:
            return
        cover = set(self._cover_ids(bkey, cover_max_to))
        if lkey:
            cover -= set(self._cover_ids(lkey, cover_max_to))
        self._conn.execute(
            "CREATE TEMP TABLE IF NOT EXISTS seq_scope (id INTEGER PRIMARY KEY)")
        self._conn.execute("DELETE FROM seq_scope")
        self._conn.executemany(
            "INSERT INTO seq_scope (id) VALUES (?)", [(i,) for i in cover])
        self._scope_key = key

    def invalidate_band_cache(self):
        """Verwirft den Band-Cache manuell. Die Trigger-Version macht das i.d.R.
        selbst; diese Methode ist ein expliziter Reset (z.B. fuer Tests)."""
        self._band_cover_cache = {}
        self._scope_key = None
        self._band_cache_ver_seen = -1

    def _build_sequence_where(self,
                              entity_id_filter: str = None,
                              max_to_filter: float = None,
                              type_filter: str = None,
                              difficulty_filter: str = None,
                              min_to_filter: float = None,
                              tags_filter: str = None,
                              bands_filter=None,
                              bands_below_filter=None,
                              cover_max_to: float = None) -> tuple:
        """Hilfsmethode: baut WHERE-Clause + params fuer Sequenz-Abfragen.

        bands_filter: iterable von Programm-Baendern (Ganzzahlen). Wenn gesetzt,
        greift der MS50-Mengen-Filter (statt/zusaetzlich zu max_to_filter): nur
        Sequenzen, deren gemappte Figuren ALLE in einem der Baender liegen und die
        mind. eine erkannte Figur haben. Aggregiert pro Figur (Mehrfachnennung).

        Returns:
            (where_sql, params)
        """
        where_clauses = []
        params = []

        # MS50-Perf: Der teure "welche Sequenz ist mit diesen Baendern tanzbar"-Join
        # wird NICHT mehr je Query neu gerechnet. Stattdessen materialisiert
        # _ensure_band_scope die (gecachte) Menge tanzbarer IDs einmal in der TEMP-
        # Tabelle seq_scope (inkl. 'below' fuer "Only" bereits herausgerechnet) und
        # wir referenzieren sie nur. Neu-Berechnung nur bei Band-Wechsel oder
        # Datenaenderung (Trigger-Version). Siehe _cover_ids / _ensure_band_scope.
        if bands_filter:
            self._ensure_band_scope(bands_filter, bands_below_filter, cover_max_to)
            where_clauses.append("id IN (SELECT id FROM seq_scope)")

        if entity_id_filter:
            # enthält-Filter ueber den indizierten sequence_calls-Index: von der
            # entity_id ueber call_text_figures (idx_ctm_entity/idx_ctfe_entity) auf die
            # call_texts, von dort ueber idx_seqcalls_calltext auf die
            # sequence_ids. Index-Seek statt Full-Scan; deckt auch Calls >15 ab.
            where_clauses.append("""id IN (
                SELECT sc.sequence_id
                FROM call_text_figures m
                JOIN sequence_calls sc ON sc.call_text = m.call_text
                WHERE m.entity_id = ?
            )""")
            params.append(entity_id_filter)

        if max_to_filter is not None:
            where_clauses.append(
                "max_teaching_order IS NOT NULL AND max_teaching_order <= ?"
            )
            params.append(max_to_filter)

        # "Nur"-Filter: hoechster Call muss im Ziel-Programm liegen
        # (Untergrenze = Programm-Start, z.B. 50.0 fuer A1)
        if min_to_filter is not None:
            where_clauses.append(
                "max_teaching_order IS NOT NULL AND max_teaching_order >= ?"
            )
            params.append(min_to_filter)

        if type_filter:
            where_clauses.append("type = ?")
            params.append(type_filter)

        if difficulty_filter:
            where_clauses.append("difficulty = ?")
            params.append(difficulty_filter)

        # BL-191: Tag-Filter — exakter Match auf den gewaehlten Tag.
        if tags_filter:
            where_clauses.append("tags = ?")
            params.append(tags_filter)

        where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""
        return where_sql, params

    def get_filtered_sequences(self, entity_id_filter: str = None,
                               max_to_filter: float = None,
                               limit: int = 50, offset: int = 0,
                               type_filter: str = None,
                               difficulty_filter: str = None,
                               min_to_filter: float = None,
                               tags_filter: str = None,
                               bands_filter=None,
                               bands_below_filter=None,
                               cover_max_to: float = None) -> list[tuple]:
        """Gibt gefilterte Sequenzen zurueck (Lazy Loading).

        Returns:
            [(id, field_1..15, level_original, max_teaching_order, type, difficulty), ...]
            Indizes: 0=id, 1-15=fields, 16=level_original, 17=max_to, 18=type, 19=difficulty
        """
        where_sql, params = self._build_sequence_where(
            entity_id_filter, max_to_filter, type_filter, difficulty_filter,
            min_to_filter, tags_filter, bands_filter, bands_below_filter,
            cover_max_to=cover_max_to)

        sql = f"""SELECT id, field_1, field_2, field_3, field_4, field_5,
                         field_6, field_7, field_8, field_9, field_10,
                         field_11, field_12, field_13, field_14, field_15,
                         level_original, max_teaching_order,
                         type, difficulty
                  FROM sequences {where_sql}
                  ORDER BY id LIMIT ? OFFSET ?"""
        params.extend([limit, offset])
        cur = self._conn.execute(sql, params)
        return cur.fetchall()

    def get_filtered_count(self, entity_id_filter: str = None,
                           max_to_filter: float = None,
                           type_filter: str = None,
                           difficulty_filter: str = None,
                           min_to_filter: float = None,
                           tags_filter: str = None,
                           bands_filter=None,
                           bands_below_filter=None,
                           cover_max_to: float = None) -> int:
        """Gibt die Anzahl gefilterter Sequenzen zurueck."""
        where_sql, params = self._build_sequence_where(
            entity_id_filter, max_to_filter, type_filter, difficulty_filter,
            min_to_filter, tags_filter, bands_filter, bands_below_filter,
            cover_max_to=cover_max_to)
        sql = f"SELECT COUNT(*) FROM sequences {where_sql}"
        cur = self._conn.execute(sql, params)
        return cur.fetchone()[0]

    def get_filtered_sequence_ids(self, entity_id_filter: str = None,
                                   max_to_filter: float = None,
                                   type_filter: str = None,
                                   difficulty_filter: str = None,
                                   min_to_filter: float = None,
                                   tags_filter: str = None,
                                   bands_filter=None,
                                   bands_below_filter=None,
                                   cover_max_to: float = None) -> list:
        """Gibt alle IDs gefilterter Sequenzen zurueck (fuer Navigation im Detail-Dialog)."""
        where_sql, params = self._build_sequence_where(
            entity_id_filter, max_to_filter, type_filter, difficulty_filter,
            min_to_filter, tags_filter, bands_filter, bands_below_filter,
            cover_max_to=cover_max_to)
        sql = f"SELECT id FROM sequences {where_sql} ORDER BY id"
        cur = self._conn.execute(sql, params)
        return [row[0] for row in cur.fetchall()]

    def get_sequence_ids_for_bands(self, allowed_bands) -> list:
        """MS50-Umbau: Mengen-Filter statt Schwellwert.

        Gibt alle Sequenz-IDs zurueck, deren *gemappte* Calls ALLE in mindestens
        einem der erlaubten Programm-Baender (Ganzzahl von teaching_order) liegen.
        Nicht gemappte Call-Texte werden — wie bei der alten max_teaching_order-
        Logik — ignoriert (sie schliessen eine Sequenz nicht aus).

        Args:
            allowed_bands: iterable von Band-Ganzzahlen, z.B. {10,20,30} fuer
                           "bis Mainstream 2026" oder {10,20,29,39,49} fuer altes A1.

        Ersetzt konzeptionell den ``max_teaching_order <= limit``-Filter, sobald
        ein Call in mehreren Programmen stehen kann und der Maximalwert nicht mehr
        eindeutig ist.
        """
        bands = sorted({int(b) for b in (allowed_bands or [])})
        if not bands:
            return []
        placeholders = ",".join("?" for _ in bands)
        # WICHTIG bei Mehrfachnennung: pro FIGUR (entity) aggregieren, nicht pro
        # call_programs-Zeile. Eine Figur ist "abgedeckt", wenn IRGENDEINE ihrer
        # Band-Mitgliedschaften erlaubt ist (z.B. Dosado in Band 10 UND 30 -> bei
        # Auswahl {30} abgedeckt). Innere GROUP BY (sequence, entity) -> covered;
        # aeussere: Sequenz passt, wenn ALLE ihre gemappten & gebandeten Figuren
        # abgedeckt sind (MIN(covered)=1). Nicht gemappte / bandlose Calls
        # (z.B. action_*-Styling) erzeugen keine Join-Zeile -> ignoriert.
        # Existiert die Gruppe ueberhaupt, gibt es >=1 gebandete Figur.
        sql = f"""
            SELECT sid FROM (
                SELECT sc.sequence_id AS sid, m.entity_id AS eid,
                       MAX(CASE WHEN CAST(cp.teaching_order AS INTEGER) IN ({placeholders})
                                THEN 1 ELSE 0 END) AS covered
                FROM sequence_calls sc
                JOIN call_text_figures m
                     ON m.call_text = sc.call_text
                JOIN call_programs cp ON cp.entity_id = m.entity_id
                GROUP BY sc.sequence_id, m.entity_id
            )
            GROUP BY sid
            HAVING MIN(covered) = 1
            ORDER BY sid
        """
        cur = self._conn.execute(sql, bands)
        return [row[0] for row in cur.fetchall()]

    def get_sequence_type_values(self) -> list[str]:
        """Gibt alle vorhandenen (nicht-leeren) type-Werte sortiert zurueck."""
        cur = self._conn.execute(
            "SELECT DISTINCT type FROM sequences WHERE type != '' ORDER BY type"
        )
        return [row[0] for row in cur.fetchall()]

    def get_sequence_difficulty_values(self) -> list[str]:
        """Gibt alle vorhandenen (nicht-leeren) difficulty-Werte zurueck (Easy→Medium→Hard)."""
        cur = self._conn.execute(
            "SELECT DISTINCT difficulty FROM sequences WHERE difficulty != '' ORDER BY difficulty"
        )
        raw = [row[0] for row in cur.fetchall()]
        # Sinnvolle Reihenfolge: Easy vor Medium vor Hard
        order = ["Easy", "Medium", "Hard"]
        sorted_vals = [v for v in order if v in raw]
        sorted_vals += [v for v in raw if v not in order]
        return sorted_vals

    def get_sequence_tags_values(self) -> list[str]:
        """BL-191: Gibt alle vorhandenen (nicht-leeren) Tag-Werte alphabetisch
        zurueck. Basis fuer die Auto-Vervollstaendigung im Editor und die
        Filter-Vorschlaege im Sequences-Widget."""
        cur = self._conn.execute(
            "SELECT DISTINCT tags FROM sequences WHERE tags != '' "
            "ORDER BY tags COLLATE NOCASE"
        )
        return [row[0] for row in cur.fetchall()]

    def get_sequence_calls(self, sequence_id: int) -> list[tuple]:
        """Gibt alle Calls einer Sequenz zurueck (via call_text_mappings).

        Liest die volle Callliste aus calls_json (Fallback field_1..15) und joined
        mit call_text_mappings + teaching_order_calls.

        Returns:
            [(position, call_text, entity_id, teaching_order, canonical_name, program), ...]
        """
        cur = self._conn.execute(
            "SELECT calls_json, field_1, field_2, field_3, field_4, field_5, "
            "field_6, field_7, field_8, field_9, field_10, "
            "field_11, field_12, field_13, field_14, field_15 "
            "FROM sequences WHERE id = ?",
            (sequence_id,)
        )
        row = cur.fetchone()
        if not row:
            return []

        # calls_json ist die Quelle; falls (noch) NULL -> aus den Mirror-Feldern.
        calls = calls_from_json(row[0]) if row[0] else clean_calls(row[1:16])

        results = []
        for i, text in enumerate(calls):
            cur2 = self._conn.execute(
                "SELECT m.entity_id, t.teaching_order, t.canonical_name, t.program "
                "FROM call_text_mappings m "
                "LEFT JOIN teaching_order_calls t ON t.entity_id = m.entity_id "
                "WHERE m.call_text = ?",
                (text,)
            )
            mapping = cur2.fetchone()
            if mapping:
                results.append((i + 1, text, mapping[0], mapping[1],
                                mapping[2], mapping[3]))
            else:
                results.append((i + 1, text, None, None, None, None))
        return results

    def get_sequence_raw(self, sequence_id: int) -> dict | None:
        """Gibt die Rohdaten einer Sequenz zurueck (fuer den Editor).

        Returns:
            {"fields": [15 Strings/None], "level_original": str,
             "seq_type": str, "difficulty": str, "tags": str}  oder None.
        """
        cur = self._conn.execute(
            "SELECT calls_json, field_1, field_2, field_3, field_4, field_5, "
            "field_6, field_7, field_8, field_9, field_10, "
            "field_11, field_12, field_13, field_14, field_15, "
            "level_original, type, difficulty, tags "
            "FROM sequences WHERE id = ?",
            (sequence_id,)
        )
        row = cur.fetchone()
        if not row:
            return None
        # Volle Liste aus calls_json (Fallback: Mirror-Felder). Nicht mehr auf 15
        # begrenzt — der Editor bekommt alle Calls.
        fields = calls_from_json(row[0]) if row[0] else clean_calls(row[1:16])
        return {
            "fields": fields,
            "level_original": row[16] or "",
            "seq_type": row[17] or "",
            "difficulty": row[18] or "",
            "tags": row[19] or "",
        }

    def update_sequence(self, sequence_id: int, fields: list,
                        level_original: str = "", seq_type: str = "",
                        difficulty: str = "", tags: str = "") -> None:
        """Aktualisiert eine bestehende Sequenz (Editor).

        max_teaching_order wird auf NULL gesetzt — der Aufrufer sollte
        anschliessend recompute_sequence_max_to() ausfuehren.
        """
        mirror = calls_to_mirror_fields(fields)
        set_fields = ", ".join(f"field_{i} = ?" for i in range(1, 16))
        params = mirror + [level_original or "", canonicalize_seq_type(seq_type),
                           difficulty or "", calls_to_json(fields), tags or "",
                           sequence_id]
        self._conn.execute(
            f"UPDATE sequences SET {set_fields}, level_original = ?, "
            f"type = ?, difficulty = ?, calls_json = ?, tags = ?, "
            f"max_teaching_order = NULL "
            f"WHERE id = ?",
            params
        )
        self._sync_sequence_calls_for(sequence_id, fields)
        self._conn.commit()

    def find_sequence_by_fields(self, fields: list,
                                exclude_id: int = None) -> int | None:
        """Sucht eine Sequenz mit identischen 15 Feldern (exakte Dublette).

        Args:
            fields: Liste von Call-Texten (wird auf 15 aufgefuellt)
            exclude_id: Diese ID bei der Suche ignorieren (eigene beim Editieren)

        Returns:
            id der ersten gefundenen identischen Sequenz, sonst None.
        """
        # Vergleich ueber die volle Callliste (calls_json). Erkennt auch
        # >15-Call-Dubletten und ist unabhaengig von NULL/''/'-'-Feinheiten,
        # weil calls_json bereits bereinigt ist.
        params = [calls_to_json(fields)]
        sql = "SELECT id FROM sequences WHERE calls_json = ?"
        if exclude_id is not None:
            sql += " AND id != ?"
            params.append(exclude_id)
        sql += " ORDER BY id LIMIT 1"
        cur = self._conn.execute(sql, params)
        row = cur.fetchone()
        return row[0] if row else None

    # ---- Teaching-Order-Calls (Referenztabelle) ----

    def clear_teaching_order_calls(self):
        """Loescht alle Programm-Zugehoerigkeiten (vor Neuimport).

        teaching_order_calls ist seit dem MS50-Umbau eine VIEW ueber
        calls + call_programs. Geleert werden die Zugehoerigkeiten
        (call_programs); die Identitaeten (calls) bleiben als FK-Ziel fuer
        call_text_mappings erhalten und werden beim Insert per OR IGNORE
        aktualisiert.
        """
        self._conn.execute("DELETE FROM call_programs;")
        self._conn.commit()

    def bulk_insert_teaching_order_calls(self, rows: list[tuple]):
        """Fuegt Teaching-Order-Eintraege ein (Identitaet + Zugehoerigkeit).

        Args:
            rows: [(entity_id, canonical_name, teaching_order, program), ...]

        Eine entity_id darf mehrfach vorkommen (mehrere Programme/Baender);
        eindeutig ist (entity_id, teaching_order).
        """
        self._conn.executemany(
            "INSERT OR IGNORE INTO calls (entity_id, canonical_name) VALUES (?, ?)",
            [(r[0], r[1]) for r in rows]
        )
        self._conn.executemany(
            "INSERT OR REPLACE INTO call_programs "
            "(entity_id, teaching_order, program) VALUES (?, ?, ?)",
            [(r[0], r[2], r[3]) for r in rows]
        )
        self._conn.commit()

    def get_teaching_order_calls(self) -> list[tuple]:
        """Alle Teaching-Order-Calls sortiert nach teaching_order.

        Returns:
            [(entity_id, canonical_name, teaching_order, program), ...]
        """
        cur = self._conn.execute(
            "SELECT entity_id, canonical_name, teaching_order, program "
            "FROM teaching_order_calls ORDER BY teaching_order"
        )
        return cur.fetchall()

    def get_teaching_order_count(self) -> int:
        """Anzahl der Teaching-Order-Eintraege."""
        cur = self._conn.execute("SELECT COUNT(*) FROM teaching_order_calls")
        return cur.fetchone()[0]

    # ---- Call-Text-Mappings (Zuordnungstabelle) ----

    def clear_call_text_mappings(self, mapped_by: str = None):
        """Loescht Mappings. Ohne Parameter: alle. Mit: nur die angegebene Quelle.

        Args:
            mapped_by: 'auto' oder 'manual' — None loescht alle
        """
        # BL-210: weitere Figuren zuerst, solange die Hauptzeilen noch sagen,
        # zu welcher Quelle sie gehoeren (nie Zusatzzeile ohne Hauptzeile).
        if mapped_by:
            self._conn.execute(
                "DELETE FROM call_text_figures_extra WHERE call_text IN "
                "(SELECT call_text FROM call_text_mappings WHERE mapped_by = ?)",
                (mapped_by,))
            self._conn.execute(
                "DELETE FROM call_text_mappings WHERE mapped_by = ?",
                (mapped_by,))
        else:
            self._conn.execute("DELETE FROM call_text_figures_extra;")
            self._conn.execute("DELETE FROM call_text_mappings;")
        self._conn.commit()

    def bulk_insert_call_text_mappings(self, rows: list[tuple]):
        """Fuegt Call-Text-Mappings ein.

        Args:
            rows: [(call_text, entity_id, mapped_by), ...]
        """
        self._conn.executemany(
            "INSERT OR IGNORE INTO call_text_mappings "
            "(call_text, entity_id, mapped_by) VALUES (?, ?, ?)",
            rows
        )
        self._conn.commit()

    def get_entity_for_call_text(self, call_text: str) -> str | None:
        """Gibt die gemappte entity_id fuer einen Call-Text zurueck.

        Returns None, wenn kein Mapping existiert ODER das Mapping auf NULL
        zeigt (z.B. bewusst nicht zugeordnet). Wird vom Editor fuer die
        Gruen-Markierung gemappter Zeilen genutzt.
        """
        if not call_text or not call_text.strip():
            return None
        cur = self._conn.execute(
            "SELECT entity_id FROM call_text_mappings WHERE call_text = ?",
            (call_text.strip(),)
        )
        row = cur.fetchone()
        if not row:
            return None
        return row[0]

    def set_call_text_mapping(self, call_text: str, entity_id: str,
                              mapped_by: str = "manual"):
        """Setzt oder aktualisiert ein einzelnes Mapping (fuer manuelle Zuordnung).

        BL-210: Einzel-Figur-Weg — eine bisherige Figuren-Menge des Texts wird
        dabei abgeraeumt, damit nie eine alte Menge halb stehen bleibt.
        """
        self._conn.execute(
            "DELETE FROM call_text_figures_extra WHERE call_text = ?",
            (call_text,))
        self._conn.execute(
            "INSERT OR REPLACE INTO call_text_mappings "
            "(call_text, entity_id, mapped_by) VALUES (?, ?, ?)",
            (call_text, entity_id, mapped_by)
        )
        self._conn.commit()

    def set_call_text_mappings(self, pairs: list, mapped_by: str = "manual") -> int:
        """Setzt viele Mappings in EINER Transaktion (ein einziges commit).

        pairs: [(call_text, entity_id), ...]

        Perf: das einzelne set_call_text_mapping committet je Aufruf (ein Fsync
        pro Zeile). Beim Bestaetigen vieler markierter Zeilen summiert sich das
        auf hunderte ms — als Batch sind es wenige ms. Gibt die Zahl der
        geschriebenen Zeilen zurueck.

        BL-210: Einzel-Figur-Weg — bisherige Figuren-Mengen der Texte werden
        abgeraeumt (siehe set_call_text_mapping).
        """
        rows = [(ct, eid, mapped_by) for ct, eid in pairs if ct and eid]
        if not rows:
            return 0
        self._conn.executemany(
            "DELETE FROM call_text_figures_extra WHERE call_text = ?",
            [(ct,) for ct, _eid, _mb in rows]
        )
        self._conn.executemany(
            "INSERT OR REPLACE INTO call_text_mappings "
            "(call_text, entity_id, mapped_by) VALUES (?, ?, ?)",
            rows
        )
        self._conn.commit()
        return len(rows)

    # ---- BL-210: Figuren-Mengen je Call-Text ----

    @staticmethod
    def _figure_rank_key(entity_id: str, min_to):
        """Sortierschluessel "hoechste Figur zuerst".

        Hoechste Figur = Figur, deren FRUEHESTE Teaching-Order am hoechsten ist
        (der Band-Filter wertet eine Figur als abgedeckt, sobald eine ihrer
        Programm-Zugehoerigkeiten erlaubt ist). Figur ohne call_programs-Zeile
        (min_to None) kommt zuletzt. Fuer die Filter dieser Version ist ihr
        Platz egal (Band-Filter uebergeht sie, Limit wertet den Text als
        ungemappt). Eine aeltere Version sieht aber nur die Hauptfigur und
        muss dort eine Figur MIT Programm finden, sonst uebergeht ihr
        Band-Filter den ganzen Call-Text.
        Gleichstand: entity_id aufsteigend.
        """
        if min_to is None:
            return (1, 0.0, entity_id)
        return (0, -min_to, entity_id)

    def _rank_figures(self, entity_ids) -> list[str]:
        """Entfernt Duplikate/Leere und sortiert hoechste Figur zuerst."""
        ids = list(dict.fromkeys(e for e in entity_ids if e))
        if len(ids) < 2:
            return ids
        placeholders = ",".join("?" * len(ids))
        min_to = dict(self._conn.execute(
            "SELECT entity_id, MIN(teaching_order) FROM call_programs "
            f"WHERE entity_id IN ({placeholders}) GROUP BY entity_id", ids))
        return sorted(ids, key=lambda e: self._figure_rank_key(e, min_to.get(e)))

    @classmethod
    def _collect_ranked_figures(cls, rows) -> dict[str, list[str]]:
        """(call_text, entity_id, min_to)-Zeilen -> {call_text: [hoechste, ...]}."""
        groups: dict[str, dict[str, object]] = {}
        for call_text, entity_id, min_to in rows:
            groups.setdefault(call_text, {})[entity_id] = min_to
        return {
            ct: sorted(figs, key=lambda e: cls._figure_rank_key(e, figs[e]))
            for ct, figs in groups.items()
        }

    def _write_call_text_figures(self, call_text: str, entity_ids,
                                 mapped_by: str):
        """Schreibt die Figuren-Menge eines Call-Texts OHNE commit.

        Hoechste Figur nach call_text_mappings, Rest nach
        call_text_figures_extra, alte Zusatzzeilen weg. Leere Menge entfernt
        die Zuordnung.
        """
        ranked = self._rank_figures(entity_ids)
        self._conn.execute(
            "DELETE FROM call_text_figures_extra WHERE call_text = ?",
            (call_text,))
        if not ranked:
            self._conn.execute(
                "DELETE FROM call_text_mappings WHERE call_text = ?",
                (call_text,))
            return
        self._conn.execute(
            "INSERT OR REPLACE INTO call_text_mappings "
            "(call_text, entity_id, mapped_by) VALUES (?, ?, ?)",
            (call_text, ranked[0], mapped_by))
        self._conn.executemany(
            "INSERT INTO call_text_figures_extra (call_text, entity_id) "
            "VALUES (?, ?)",
            [(call_text, e) for e in ranked[1:]])

    def set_call_text_figures(self, call_text: str, entity_ids,
                              mapped_by: str = "manual"):
        """Setzt die Figuren-Menge eines Call-Texts (ersetzt die bisherige).

        Leere Liste entfernt die Zuordnung (wie delete_call_text_mapping).
        Eine Transaktion: schlaegt ein Schreibschritt fehl (z.B. unbekannte
        Figur), bleibt die bisherige Menge vollstaendig stehen.
        """
        try:
            self._write_call_text_figures(call_text, entity_ids, mapped_by)
        except Exception:
            self._conn.rollback()
            raise
        self._conn.commit()

    def get_call_text_figures(self, call_text: str) -> list[str]:
        """Figuren eines Call-Texts, hoechste zuerst. Ohne Zuordnung: []."""
        rows = self._conn.execute(
            _SELECT_CALL_TEXT_FIGURES_RANKED + " WHERE f.call_text = ?",
            (call_text,))
        return self._collect_ranked_figures(rows).get(call_text, [])

    def set_call_text_figures_bulk(self, pairs, mapped_by: str = "manual") -> int:
        """Setzt viele Figuren-Mengen in EINER Transaktion (ein commit).

        pairs: Iterable von (call_text, entity_ids). Je Text wie
        set_call_text_figures (leere Menge entfernt die Zuordnung); Paare ohne
        Call-Text werden uebersprungen. Gibt die Zahl der geschriebenen
        Call-Texte zurueck (analog set_call_text_mappings).
        """
        written = 0
        try:
            for call_text, entity_ids in pairs:
                if not call_text:
                    continue
                self._write_call_text_figures(call_text, entity_ids, mapped_by)
                written += 1
        except Exception:
            self._conn.rollback()
            raise
        self._conn.commit()
        return written

    def _normalize_call_text_figures(self):
        """Stellt die Invariante der Figuren-Mengen wieder her, OHNE commit.

        Fuer Referenz-Updates (Merges, geaenderte Teaching-Orders) und fuer
        Zustaende, die eine aeltere Version hinterlassen hat:
        - Zusatzzeilen ohne Hauptfigur oder gleich der Hauptfigur fallen weg
        - die hoechste Figur steht (wieder) in call_text_mappings
        Betrifft nur Texte mit Zusatzzeilen; mapped_by bleibt erhalten.
        """
        self._conn.execute(
            "DELETE FROM call_text_figures_extra WHERE NOT EXISTS ("
            "SELECT 1 FROM call_text_mappings m "
            "WHERE m.call_text = call_text_figures_extra.call_text "
            "AND m.entity_id IS NOT NULL "
            "AND m.entity_id <> call_text_figures_extra.entity_id)")
        sets = self._collect_ranked_figures(self._conn.execute(
            _SELECT_CALL_TEXT_FIGURES_RANKED + " WHERE f.call_text IN "
            "(SELECT call_text FROM call_text_figures_extra)"))
        main = {ct: (eid, mb) for ct, eid, mb in self._conn.execute(
            "SELECT call_text, entity_id, mapped_by FROM call_text_mappings "
            "WHERE call_text IN (SELECT call_text FROM call_text_figures_extra)")}
        for call_text, ranked in sets.items():
            entity_id, mapped_by = main[call_text]
            if ranked[0] != entity_id:
                self._write_call_text_figures(call_text, ranked, mapped_by)

    def get_all_call_text_figures(self) -> dict[str, list[str]]:
        """Alle Figuren-Mengen in einem Query-Durchlauf:
        {call_text: [hoechste, ...]} — gleiche Reihenfolge wie
        get_call_text_figures. Texte ohne Figur fehlen."""
        rows = self._conn.execute(_SELECT_CALL_TEXT_FIGURES_RANKED)
        return self._collect_ranked_figures(rows)

    def get_sequence_ids_with_call_text(self, call_text: str) -> list[int]:
        """Sequenz-IDs, die den gegebenen (exakten) Call-Text enthalten.

        Nutzt den indizierten sequence_calls-Index (idx_seqcalls_calltext) —
        Index-Seek statt Full-Scan. Reihenfolge: kleinste ID zuerst (stabil zum
        Durchblaettern). Fuer "Beispiel zeigen" im Call-Mapping-Dialog.
        """
        ct = (call_text or "").strip()
        if not ct:
            return []
        cur = self._conn.execute(
            "SELECT DISTINCT sequence_id FROM sequence_calls "
            "WHERE call_text = ? ORDER BY sequence_id",
            (ct,)
        )
        return [row[0] for row in cur.fetchall()]

    def get_unmapped_call_texts(self) -> list[str]:
        """Gibt alle Sequenz-Call-Texte zurueck die noch kein Mapping haben.

        Sammelt alle einzigartigen Texte aus den 15 Feldern und filtert
        die ohne Eintrag in call_text_mappings.
        """
        return [text for text, _cnt in self.get_unmapped_call_texts_by_frequency()]

    def get_unmapped_call_texts_by_frequency(self) -> list[tuple]:
        """Gibt ungemappte Call-Texte sortiert nach Haeufigkeit zurueck.

        Returns:
            [(call_text, count), ...] — haeufigste zuerst, bei Gleichstand alphabetisch
        """
        cur = self._conn.execute("""
            SELECT je.value AS val, COUNT(*) AS cnt
            FROM sequences, json_each(sequences.calls_json) je
            WHERE je.value NOT IN (SELECT call_text FROM call_text_mappings)
            GROUP BY val
            ORDER BY cnt DESC, val ASC
        """)
        return cur.fetchall()

    def count_duplicate_sequences(self) -> tuple:
        """Zaehlt exakte Sequenz-Duplikate (alle 15 Felder identisch).

        Returns:
            (total, dup_groups, to_delete)
            total:      Gesamtzahl Sequenzen
            dup_groups: Anzahl Gruppen mit mind. einem Duplikat
            to_delete:  Anzahl zu loeschender Zeilen (Duplikate ohne den aeltesten Eintrag)
        """
        # Dubletten = identische volle Callliste (calls_json). Ersetzt das
        # GROUP BY ueber field_1..15 und erkennt auch >15-Call-Dubletten.
        cur = self._conn.execute("SELECT COUNT(*) FROM sequences")
        total = cur.fetchone()[0]

        cur = self._conn.execute("""
            SELECT COUNT(*) FROM (
                SELECT MIN(id) FROM sequences
                GROUP BY calls_json
                HAVING COUNT(*) > 1
            )
        """)
        dup_groups = cur.fetchone()[0]

        cur = self._conn.execute("""
            SELECT COUNT(*) FROM sequences
            WHERE id NOT IN (
                SELECT MIN(id) FROM sequences GROUP BY calls_json
            )
        """)
        to_delete = cur.fetchone()[0]

        return (total, dup_groups, to_delete)

    def delete_sequences(self, seq_ids: list) -> int:
        """Loescht eine oder mehrere Sequenzen anhand der IDs.

        Sequenzen werden von keiner anderen Tabelle ueber Foreign Key
        referenziert — DELETE ist daher harmlos und endgueltig (kein
        Papierkorb wie bei Songs).

        Args:
            seq_ids: Liste der zu loeschenden Sequenz-IDs.

        Returns:
            Anzahl tatsaechlich geloeschter Zeilen.
        """
        if not seq_ids:
            return 0
        placeholders = ",".join("?" * len(seq_ids))
        # Index-Kinder zuerst (FK NO ACTION wuerde den Sequenz-Delete sonst blocken)
        self._conn.execute(
            f"DELETE FROM sequence_calls WHERE sequence_id IN ({placeholders})",
            list(seq_ids)
        )
        cur = self._conn.execute(
            f"DELETE FROM sequences WHERE id IN ({placeholders})",
            list(seq_ids)
        )
        deleted = cur.rowcount
        self._conn.commit()
        return deleted

    def remove_duplicate_sequences(self) -> int:
        """Loescht exakte Sequenz-Duplikate, behaelt den aeltesten Eintrag (MIN id).

        Fuehrt anschliessend VACUUM aus um den Speicherplatz freizugeben.

        Returns:
            Anzahl geloeschter Zeilen
        """
        # Index-Kinder der zu loeschenden Sequenzen zuerst entfernen (FK).
        self._conn.execute("""
            DELETE FROM sequence_calls
            WHERE sequence_id NOT IN (
                SELECT MIN(id) FROM sequences GROUP BY calls_json
            )
        """)
        cur = self._conn.execute("""
            DELETE FROM sequences
            WHERE id NOT IN (
                SELECT MIN(id) FROM sequences GROUP BY calls_json
            )
        """)
        deleted = cur.rowcount
        self._conn.commit()
        self._conn.execute("VACUUM")
        return deleted

    def get_all_call_texts_with_mapping(self) -> list[tuple]:
        """Gibt alle Call-Texte aus Sequenzen mit Haeufigkeit und aktuellem Mapping.

        Returns:
            [(call_text, count, entity_id, canonical_name, program, mapped_by), ...]
            entity_id/canonical_name/program/mapped_by sind None wenn kein Mapping.
            Sortiert: count DESC, call_text ASC.
        """
        cur = self._conn.execute("""
            SELECT
                je.value AS val,
                COUNT(*) AS cnt,
                m.entity_id,
                t.canonical_name,
                t.program,
                m.mapped_by
            FROM sequences, json_each(sequences.calls_json) je
            LEFT JOIN call_text_mappings m ON m.call_text = je.value
            LEFT JOIN teaching_order_calls t ON t.entity_id = m.entity_id
            GROUP BY val
            ORDER BY cnt DESC, val ASC
        """)
        return cur.fetchall()

    def get_all_call_text_mappings(self) -> list[dict]:
        """Gibt alle Zuordnungen als Liste von Dicts zurueck (Export).

        BL-210: eine Zeile je Figur, hoechste Figur zuerst; weitere Figuren
        tragen das mapped_by der Hauptzeile. Aeltere Versionen importieren per
        INSERT OR IGNORE und uebernehmen so genau die hoechste Figur.
        """
        figures = self.get_all_call_text_figures()
        cur = self._conn.execute(
            "SELECT call_text, entity_id, mapped_by FROM call_text_mappings ORDER BY call_text"
        )
        return [
            {"call_text": call_text, "entity_id": fig, "mapped_by": mapped_by}
            for call_text, entity_id, mapped_by in cur.fetchall()
            for fig in (figures.get(call_text) or [entity_id])
        ]

    def import_call_text_mappings(self, rows: list[dict]) -> tuple[int, int]:
        """Importiert Zuordnungen; vorhandene Call-Texte werden uebersprungen
        (Semantik wie INSERT OR IGNORE).

        BL-210: Zeilen werden je Call-Text gesammelt (eine Zeile je Figur) und
        als Menge geschrieben — die hoechste Figur wird neu bestimmt, nicht der
        Dateireihenfolge entnommen. mapped_by kommt aus der ersten Zeile des
        Texts. Eine Transaktion.

        Returns:
            (neu_eingefuegt, bereits_vorhanden) — gezaehlt in Call-Texten
            (Zuordnungen), nicht in Figuren-Zeilen
        """
        groups: dict[str, tuple[str, list]] = {}
        for r in rows:
            _mb, ids = groups.setdefault(r["call_text"], (r["mapped_by"], []))
            if r["entity_id"]:
                ids.append(r["entity_id"])
        existing = {ct for (ct,) in self._conn.execute(
            "SELECT call_text FROM call_text_mappings")}
        neu = 0
        try:
            for call_text, (mapped_by, ids) in groups.items():
                if call_text in existing:
                    continue
                if ids:
                    self._write_call_text_figures(call_text, ids, mapped_by)
                else:
                    # bewusst "keine Figur" (entity_id NULL) wie bisher uebernehmen
                    self._conn.execute(
                        "INSERT INTO call_text_mappings (call_text, entity_id, mapped_by) "
                        "VALUES (?, NULL, ?)", (call_text, mapped_by))
                neu += 1
        except Exception:
            self._conn.rollback()
            raise
        self._conn.commit()
        return neu, len(groups) - neu

    def delete_call_text_mapping(self, call_text: str):
        """Loescht ein bestehendes Mapping fuer den gegebenen Call-Text
        (BL-210: samt der weiteren Figuren seiner Menge)."""
        self._conn.execute(
            "DELETE FROM call_text_figures_extra WHERE call_text = ?", (call_text,)
        )
        self._conn.execute(
            "DELETE FROM call_text_mappings WHERE call_text = ?", (call_text,)
        )
        self._conn.commit()

    def ensure_filler_words_entity(self):
        """Stellt sicher dass der 'Filler Words'-Eintrag in teaching_order_calls existiert.

        teaching_order=0.001 → erscheint ganz oben in der sortierten Liste,
        beeinflusst max_teaching_order einer Sequenz nicht nennenswert.
        """
        self._conn.execute(
            "INSERT OR IGNORE INTO calls (entity_id, canonical_name) "
            "VALUES ('filler_words', 'Filler Words')"
        )
        self._conn.execute(
            "INSERT OR IGNORE INTO call_programs (entity_id, teaching_order, program) "
            "VALUES ('filler_words', 0.001, '')"
        )
        self._conn.commit()

    def split_sequence_call_at_comma(self, call_text: str) -> tuple:
        """Splittet einen Call-Text am ersten Komma in allen betroffenen Sequenzen.

        Findet alle Sequenzen die diesen Text in einem Feld enthalten,
        teilt ihn am ersten Komma auf und schiebt nachfolgende Felder
        um eine Position nach rechts. Ueberlauf bei Feld 15 wird abgeschnitten.

        Returns:
            (seq_count, split_count) — Anzahl Sequenzen + Einzelvorkommen
        """
        comma_idx = call_text.find(',')
        if comma_idx < 0:
            return (0, 0)
        part1 = call_text[:comma_idx].strip()
        part2 = call_text[comma_idx + 1:].strip()
        if not part1 or not part2:
            return (0, 0)

        target = call_text.strip()
        rows = self._conn.execute("""
            SELECT id, calls_json FROM sequences
            WHERE EXISTS (
                SELECT 1 FROM json_each(sequences.calls_json) je WHERE je.value = ?
            )
        """, (target,)).fetchall()

        seq_count = 0
        split_count = 0
        set_clause = ", ".join(f"field_{i}=?" for i in range(1, 16))

        for seq_id, cj in rows:
            calls = calls_from_json(cj)
            new_calls = []
            changed = False
            for c in calls:
                if c == target:
                    new_calls.extend([part1, part2])
                    split_count += 1
                    changed = True
                else:
                    new_calls.append(c)
            if not changed:
                continue
            # calls_json + Mirror aktualisieren. Kein Ueberlauf-Abschnitt mehr —
            # die Liste darf ueber 15 hinaus wachsen.
            mirror = calls_to_mirror_fields(new_calls)
            self._conn.execute(
                f"UPDATE sequences SET {set_clause}, calls_json=? WHERE id=?",
                tuple(mirror) + (calls_to_json(new_calls), seq_id)
            )
            self._sync_sequence_calls_for(seq_id, new_calls)
            seq_count += 1

        self._conn.commit()
        return (seq_count, split_count)

    def get_mapping_stats(self) -> dict:
        """Statistik ueber den Mapping-Stand."""
        # Alle einzigartigen Texte aus Sequenzen (volle Callliste via json_each)
        all_texts = set()
        cur = self._conn.execute(
            "SELECT DISTINCT je.value FROM sequences, "
            "json_each(sequences.calls_json) je"
        )
        for (val,) in cur.fetchall():
            if val and val.strip() and val.strip() != '-':
                all_texts.add(val.strip())

        cur = self._conn.execute("SELECT COUNT(*) FROM call_text_mappings WHERE entity_id IS NOT NULL")
        mapped_count = cur.fetchone()[0]

        cur = self._conn.execute("SELECT COUNT(*) FROM call_text_mappings WHERE mapped_by = 'auto'")
        auto_count = cur.fetchone()[0]

        cur = self._conn.execute("SELECT COUNT(*) FROM call_text_mappings WHERE mapped_by = 'manual'")
        manual_count = cur.fetchone()[0]

        return {
            "total_unique_texts": len(all_texts),
            "mapped": mapped_count,
            "unmapped": len(all_texts) - mapped_count,
            "auto": auto_count,
            "manual": manual_count,
        }

    def backfill_auto_mappings(self) -> int:
        """Legt fuer alle noch ungemappten Call-Texte, die EXAKT (Score 1.0) zu
        einem bekannten Call passen, ein 'auto'-Mapping an.

        Gemeinsame Basis fuer Startup-Backfill-Migration, Bulk-Import und den
        Remapping-Knopf — damit die drei Pfade nicht auseinanderlaufen. Ohne
        diesen Schritt bleibt ein Massenimport voellig ungemappt: der Band-Filter
        (Programmwahl) liefert dann 0 Sequenzen, obwohl welche da sind.

        Idempotent und risikoarm: fuegt nur exakte Treffer via INSERT OR IGNORE
        hinzu, fasst manuelle Mappings nie an und loescht nichts. Gibt die Anzahl
        neu angelegter Mappings zurueck.
        """
        toc = self.get_teaching_order_calls()
        if not toc:
            return 0
        from sequence_mapper import CallMatcher
        matcher = CallMatcher(toc)
        # Nur Texte OHNE bestehendes Mapping betrachten (manuelle bleiben unberuehrt).
        texts = [r[0] for r in self._conn.execute(
            "SELECT DISTINCT sc.call_text FROM sequence_calls sc "
            "LEFT JOIN call_text_mappings m ON m.call_text = sc.call_text "
            "WHERE m.call_text IS NULL"
        )]
        rows = []
        for t in texts:
            eid = matcher.exact_entity(t)
            if eid is not None:
                rows.append((t, eid, "auto"))
        if rows:
            self._conn.executemany(
                "INSERT OR IGNORE INTO call_text_mappings "
                "(call_text, entity_id, mapped_by) VALUES (?, ?, ?)", rows)
            self._conn.commit()
        return len(rows)

    def _backfill_auto_mappings_once(self):
        """Startup-Heilung (einmalig, per Flag in app_meta): baut fehlende Auto-
        Mappings fuer Bestands-DBs nach, die per Massenimport ungemappt blieben.

        Laeuft nach reseed_reference_data(), damit calls/call_programs aktuell
        sind. Bei frischen oder bereits gehealten DBs ein billiger No-Op.
        """
        done = self._conn.execute(
            "SELECT value FROM app_meta WHERE key='auto_mappings_backfilled'"
        ).fetchone()
        if done:
            return
        try:
            n = self.backfill_auto_mappings()
            if n:
                self.recompute_sequence_max_to()
                print(f"[SongDB] Auto-Mapping-Backfill: {n} fehlende Mappings ergaenzt")
        except Exception as e:
            # Backfill darf den Start nie verhindern — Flag NICHT setzen, damit es
            # beim naechsten Start erneut versucht wird.
            print(f"[SongDB] Auto-Mapping-Backfill uebersprungen: {e}")
            return
        self._conn.execute(
            "INSERT OR REPLACE INTO app_meta (key, value) "
            "VALUES ('auto_mappings_backfilled', '1')")
        self._conn.commit()

    def recompute_sequence_max_to(self):
        """Berechnet max_teaching_order fuer alle Sequenzen neu.

        Basiert auf call_text_mappings + call_text_figures_extra + teaching_order_calls.
        Konservativ: NULL wenn mindestens ein Feld unmapped ist.
        """
        cur = self._conn.execute(
            "SELECT id, calls_json, field_1, field_2, field_3, field_4, field_5, "
            "field_6, field_7, field_8, field_9, field_10, "
            "field_11, field_12, field_13, field_14, field_15 "
            "FROM sequences"
        )
        sequences = cur.fetchall()

        # Mapping-Cache laden
        cur2 = self._conn.execute(
            "SELECT m.call_text, t.teaching_order "
            "FROM call_text_mappings m "
            "LEFT JOIN teaching_order_calls t ON t.entity_id = m.entity_id"
        )
        text_to_to = {row[0]: row[1] for row in cur2.fetchall()}
        # BL-210: weitere Figuren eines Textes -> hoechste Teaching-Order zaehlt.
        # Ohne Zusatzzeilen bleibt text_to_to bitgleich; fehlt einer Figur die
        # Teaching-Order, gilt der Text wie bisher als ungemappt.
        for text, to in self._conn.execute(
                "SELECT e.call_text, t.teaching_order "
                "FROM call_text_figures_extra e "
                "LEFT JOIN teaching_order_calls t ON t.entity_id = e.entity_id"):
            prev = text_to_to.get(text)
            text_to_to[text] = None if prev is None or to is None else max(prev, to)

        updates = []
        for seq in sequences:
            seq_id = seq[0]
            # Volle Callliste (calls_json), Fallback Mirror-Felder seq[2:17].
            calls = calls_from_json(seq[1]) if seq[1] else clean_calls(seq[2:17])
            max_to = None
            has_unmapped = False

            for text in calls:
                to = text_to_to.get(text)
                if to is not None:
                    max_to = max(max_to or 0.0, to)
                else:
                    has_unmapped = True

            # Konservativ: NULL wenn Felder unmapped
            if has_unmapped:
                max_to = None

            updates.append((max_to, seq_id))

        self._conn.executemany(
            "UPDATE sequences SET max_teaching_order = ? WHERE id = ?",
            updates
        )
        self._conn.commit()

    def get_all_sequences_raw(self) -> list[tuple]:
        """Gibt alle Sequenzen mit Rohdaten zurueck (fuer Remapping).

        Returns:
            [(id, field_1..field_15), ...]
        """
        cur = self._conn.execute(
            "SELECT id, field_1, field_2, field_3, field_4, field_5, "
            "field_6, field_7, field_8, field_9, field_10, "
            "field_11, field_12, field_13, field_14, field_15 "
            "FROM sequences ORDER BY id"
        )
        return cur.fetchall()

    # ---- Potential (Datenqualitaets-Checks) ----

    def potential_singing_no_lyrics(self) -> list:
        """Singing Calls ohne verknuepfte Lyrics-Datei."""
        cur = self._conn.execute("""
            SELECT s.id, s.title, s.filename
            FROM songs s
            LEFT JOIN potential_ignored pi
                ON pi.check_type = 'singing_no_lyrics' AND pi.entity_id = s.id
            WHERE s.is_singing = 1
              AND (s.lyrics_file IS NULL OR s.lyrics_file = '')
              AND pi.entity_id IS NULL
            ORDER BY s.title;
        """)
        return cur.fetchall()

    def potential_singing_no_lyrics_full(self) -> list:
        """Wie potential_singing_no_lyrics, aber mit Label.

        Rueckgabe: (id, title, label, filename). Die Krabbelkiste-Suche
        vergleicht Titel + Label + Plattennummer und braucht deshalb das
        Label-Feld zusaetzlich zum Titel.
        """
        cur = self._conn.execute("""
            SELECT s.id, s.title, s.label, s.filename
            FROM songs s
            LEFT JOIN potential_ignored pi
                ON pi.check_type = 'singing_no_lyrics' AND pi.entity_id = s.id
            WHERE s.is_singing = 1
              AND (s.lyrics_file IS NULL OR s.lyrics_file = '')
              AND pi.entity_id IS NULL
            ORDER BY s.title;
        """)
        return cur.fetchall()

    def potential_singing_no_song_points(self) -> list:
        """Singing Calls mit Lyrics, aber ohne gesetzten Liedstart UND -ende.

        Start/Ende liegen als song_properties 'singing_start_m<slot>' /
        'singing_end_m<slot>' vor (pro Musik-Variante). Ein Song gilt als versorgt,
        wenn er fuer irgendeine Variante BEIDE Werte hat. Ohne Lyrics ist das Setzen
        nicht moeglich — solche Songs stehen bereits unter 'Ohne Lyrics'.
        """
        cur = self._conn.execute("""
            SELECT s.id, s.title, s.filename
            FROM songs s
            LEFT JOIN potential_ignored pi
                ON pi.check_type = 'singing_no_song_points' AND pi.entity_id = s.id
            WHERE s.is_singing = 1
              AND s.lyrics_file IS NOT NULL AND s.lyrics_file != ''
              AND pi.entity_id IS NULL
              AND s.id NOT IN (
                  SELECT sp1.song_id FROM song_properties sp1
                  WHERE sp1.key LIKE 'singing_start_m%' AND sp1.value != ''
                  INTERSECT
                  SELECT sp2.song_id FROM song_properties sp2
                  WHERE sp2.key LIKE 'singing_end_m%' AND sp2.value != ''
              )
            ORDER BY s.title;
        """)
        return cur.fetchall()

    def potential_singing_no_sync_points(self) -> list:
        """Singing Calls mit Lyrics, aber ohne einen einzigen Sync-Punkt.

        Sync-Anker liegen als song_properties mit Prefix 'lyric_sync_' vor
        (Schluessel 'lyric_sync_m<musik>_l<lyric>_<index>'). Ohne Lyrics nicht
        moeglich — solche Songs stehen bereits unter 'Ohne Lyrics'.
        """
        cur = self._conn.execute("""
            SELECT s.id, s.title, s.filename
            FROM songs s
            LEFT JOIN potential_ignored pi
                ON pi.check_type = 'singing_no_sync_points' AND pi.entity_id = s.id
            WHERE s.is_singing = 1
              AND s.lyrics_file IS NOT NULL AND s.lyrics_file != ''
              AND pi.entity_id IS NULL
              AND s.id NOT IN (
                  SELECT sp.song_id FROM song_properties sp
                  WHERE sp.key LIKE 'lyric_sync_%'
              )
            ORDER BY s.title;
        """)
        return cur.fetchall()

    def singing_with_lyrics(self) -> list:
        """ALLE Singing Calls mit Lyrics — auch die, die schon Sync-Punkte haben.

        Gegenstueck zu potential_singing_no_sync_points(): dort geht es um die
        offene Arbeitsliste, hier um einen bewussten Komplettlauf ueber den
        ganzen Bestand. Deshalb auch ohne potential_ignored-Filter: "ignorieren"
        heisst "nicht mehr anmahnen", nicht "nie wieder anfassen".
        """
        cur = self._conn.execute("""
            SELECT s.id, s.title, s.filename
            FROM songs s
            WHERE s.is_singing = 1
              AND s.lyrics_file IS NOT NULL AND s.lyrics_file != ''
            ORDER BY s.title;
        """)
        return cur.fetchall()

    def songs_with_sync_anchors(self, song_ids) -> set:
        """Teilmenge von song_ids, die bereits Sync-Anker hat (Slot m1/l1).

        Grundlage fuer die Rueckfrage vor einem Komplettlauf: nur so laesst sich
        beziffern, wie viel bestehende Arbeit ueberschrieben wuerde.
        """
        ids = [int(i) for i in song_ids]
        if not ids:
            return set()
        out = set()
        CHUNK = 500   # SQLite-Grenze fuer Platzhalter nicht ausreizen
        for i in range(0, len(ids), CHUNK):
            part = ids[i:i + CHUNK]
            q = ",".join("?" * len(part))
            rows = self._conn.execute(
                f"SELECT DISTINCT song_id FROM song_properties "
                f"WHERE key LIKE 'lyric_sync_m1_l1_%' AND song_id IN ({q});",
                part).fetchall()
            out.update(r[0] for r in rows)
        return out

    def potential_pattern_no_loop(self) -> list:
        """Pattern ohne gesetzte Loop-Marken (beide auf Default 0.0)."""
        cur = self._conn.execute("""
            SELECT s.id, s.title, s.filename
            FROM songs s
            LEFT JOIN potential_ignored pi
                ON pi.check_type = 'pattern_no_loop' AND pi.entity_id = s.id
            WHERE s.is_pattern = 1
              AND s.loop_in = 0.0 AND s.loop_out = 0.0
              AND pi.entity_id IS NULL
            ORDER BY s.title;
        """)
        return cur.fetchall()

    def potential_no_bpm(self) -> list:
        """Songs mit fehlender oder unplausibler BPM: base_bpm < 100 oder > 150.
        base_bpm = 0 (nie gesetzt) faellt unter < 100 → ebenfalls Kandidat.
        Liefert (id, title, filename, base_bpm) — die BPM wird fuer die
        Problem-Spalte gebraucht; Aufrufer nutzen sonst nur row[0..2]."""
        cur = self._conn.execute("""
            SELECT s.id, s.title, s.filename, s.base_bpm
            FROM songs s
            WHERE s.base_bpm < 100 OR s.base_bpm > 150
            ORDER BY s.title;
        """)
        return cur.fetchall()

    def songs_bpm_empty(self) -> list:
        """Songs ganz ohne BPM (base_bpm <= 0) — fuer 'Alle leere ermitteln'."""
        cur = self._conn.execute("""
            SELECT s.id, s.title, s.filename
            FROM songs s
            WHERE s.base_bpm <= 0
            ORDER BY s.title;
        """)
        return cur.fetchall()

    def songs_all_for_bpm(self) -> list:
        """Alle Songs (id, title, filename) — fuer 'ALLE ermitteln'."""
        cur = self._conn.execute("""
            SELECT s.id, s.title, s.filename
            FROM songs s
            ORDER BY s.title;
        """)
        return cur.fetchall()

    def singing_no_start(self) -> list:
        """Singing Calls ohne gesetzten Musik-Startpunkt (kein
        'singing_start_m<slot>' fuer irgendeine Variante).

        Die Auto-Erkennung (detect_singing_body) arbeitet rein auf Audio und
        braucht KEINE Lyrics — daher werden hier bewusst ALLE is_singing-Songs
        ohne Start gelistet (auch solche ohne Lyrics), anders als
        potential_singing_no_song_points. base_bpm dient als Tempo-Anker fuer
        den Detektor und als Info-Spalte.
        """
        cur = self._conn.execute("""
            SELECT s.id, s.title, s.filename, s.base_bpm
            FROM songs s
            WHERE s.is_singing = 1
              AND s.id NOT IN (
                  SELECT sp.song_id FROM song_properties sp
                  WHERE sp.key LIKE 'singing_start_m%' AND sp.value != ''
              )
            ORDER BY s.title;
        """)
        return cur.fetchall()

    def singing_all_for_start(self) -> list:
        """Alle Singing Calls (id, title, filename, base_bpm) — fuer 'ALLE
        analysieren' (ueberschreibt ggf. bereits gesetzte Startpunkte)."""
        cur = self._conn.execute("""
            SELECT s.id, s.title, s.filename, s.base_bpm
            FROM songs s
            WHERE s.is_singing = 1
            ORDER BY s.title;
        """)
        return cur.fetchall()

    def potential_loop_no_beatsnap(self) -> list:
        """Songs mit Loop-Marken aber ohne Beat Snap Optimierung (Offset = 0).

        Songs mit dem Marker-Genre 'CHECK: BEATSNAP' (Bulk-Beat-Snap konnte
        keinen Offset finden) sind ausgeschlossen — sonst taeten sie mit
        loop_offset_ms=0.0 endlos wieder auftauchen."""
        cur = self._conn.execute(f"""
            SELECT s.id, s.title, s.filename
            FROM songs s
            LEFT JOIN potential_ignored pi
                ON pi.check_type = 'loop_no_beatsnap' AND pi.entity_id = s.id
            WHERE (s.loop_in > 0.0 OR s.loop_out > 0.0)
              AND s.loop_offset_ms = 0.0
              AND pi.entity_id IS NULL
              AND NOT EXISTS (
                  SELECT 1 FROM song_genres sg
                  JOIN genres g ON g.id = sg.genre_id
                  WHERE sg.song_id = s.id
                    AND g.name = '{CHECK_BEATSNAP_GENRE_NAME}')
            ORDER BY s.title;
        """)
        return cur.fetchall()

    def patter_with_loop(self) -> list:
        """Patter-Songs mit gesetzter Sprungmarke — Basis fuer die Loop-Optimierung.

        Nur Songs mit gueltigem Loop (loop_out > loop_in, loop_out > 0); ohne
        vorhandene Marken gibt es nichts zu optimieren.
        """
        cur = self._conn.execute("""
            SELECT s.id, s.title, s.filename
            FROM songs s
            WHERE s.is_pattern = 1
              AND s.loop_out > 0.0
              AND s.loop_out > s.loop_in
            ORDER BY s.title;
        """)
        return cur.fetchall()

    def potential_location_no_history(self) -> list:
        """Lokationen ohne Abspielhistorie."""
        cur = self._conn.execute("""
            SELECT l.id, l.name
            FROM locations l
            LEFT JOIN play_history ph ON ph.location_id = l.id
            LEFT JOIN potential_ignored pi
                ON pi.check_type = 'location_no_history' AND pi.entity_id = l.id
            WHERE ph.id IS NULL
              AND pi.entity_id IS NULL
            ORDER BY l.name;
        """)
        return cur.fetchall()

    def potential_history_orphaned(self) -> list:
        """Historieneintraege mit geloeschten Lokationen."""
        cur = self._conn.execute("""
            SELECT DISTINCT ph.location_id,
                   COUNT(*) as cnt
            FROM play_history ph
            LEFT JOIN locations l ON l.id = ph.location_id
            WHERE ph.location_id IS NOT NULL
              AND l.id IS NULL
            GROUP BY ph.location_id
            ORDER BY cnt DESC;
        """)
        return cur.fetchall()

    def potential_no_quality(self) -> list:
        """Songs ohne Qualitaetsbewertung (quality = 0 = Default = nicht gesetzt)."""
        cur = self._conn.execute("""
            SELECT s.id, s.title, s.filename
            FROM songs s
            LEFT JOIN potential_ignored pi
                ON pi.check_type = 'no_quality' AND pi.entity_id = s.id
            WHERE s.quality = 0
              AND pi.entity_id IS NULL
            ORDER BY s.title;
        """)
        return cur.fetchall()

    def potential_no_genre(self) -> list:
        """Songs ohne Genre-Zuweisung."""
        cur = self._conn.execute("""
            SELECT s.id, s.title, s.filename
            FROM songs s
            LEFT JOIN song_genres sg ON sg.song_id = s.id
            LEFT JOIN potential_ignored pi
                ON pi.check_type = 'no_genre' AND pi.entity_id = s.id
            WHERE sg.song_id IS NULL
              AND pi.entity_id IS NULL
            ORDER BY s.title;
        """)
        return cur.fetchall()

    def potential_no_err(self) -> list:
        """Songs ohne ERR-Bewertung (err = 0 = Default = nicht gesetzt)."""
        cur = self._conn.execute("""
            SELECT s.id, s.title, s.filename
            FROM songs s
            LEFT JOIN potential_ignored pi
                ON pi.check_type = 'no_err' AND pi.entity_id = s.id
            WHERE s.err = 0
              AND pi.entity_id IS NULL
            ORDER BY s.title;
        """)
        return cur.fetchall()

    def get_songs_for_qe_filler(self) -> list:
        """Songs wo Quality=0 ODER ERR=0.
        Gibt (id, title, filename, quality, err, is_pattern, is_singing) zurueck."""
        cur = self._conn.execute("""
            SELECT s.id, s.title, s.filename, s.quality, s.err, s.is_pattern, s.is_singing
            FROM songs s
            WHERE s.quality = 0 OR s.err = 0
            ORDER BY s.title;
        """)
        return cur.fetchall()

    def potential_no_mp3_candidates(self) -> list:
        """Alle Songs (nicht ignorierte) als Kandidaten fuer den MP3-Datei-Check.

        Der eigentliche Datei-Check (os.path.isfile) erfolgt im Widget via PathManager.
        """
        cur = self._conn.execute("""
            SELECT s.id, s.title, s.filename
            FROM songs s
            LEFT JOIN potential_ignored pi
                ON pi.check_type = 'no_mp3' AND pi.entity_id = s.id
            WHERE pi.entity_id IS NULL
            ORDER BY s.title;
        """)
        return cur.fetchall()

    def potential_bad_mp3_candidates(self) -> list:
        """Alle Songs (nicht ignorierte) als Kandidaten fuer den Kompatibilitaets-Check.

        Prueft ob soundfile/libsndfile die Datei lesen kann. Erfordert PathManager im Widget.
        """
        cur = self._conn.execute("""
            SELECT s.id, s.title, s.filename
            FROM songs s
            LEFT JOIN potential_ignored pi
                ON pi.check_type = 'bad_mp3' AND pi.entity_id = s.id
            WHERE pi.entity_id IS NULL
            ORDER BY s.title;
        """)
        return cur.fetchall()

    def potential_cleanup_orphaned_history(self) -> int:
        """Loescht alle Historieneintraege mit geloeschten Lokationen.

        Returns: Anzahl geloeschter Eintraege.
        """
        cur = self._conn.execute("""
            DELETE FROM play_history
            WHERE location_id IS NOT NULL
              AND location_id NOT IN (SELECT id FROM locations);
        """)
        self._conn.commit()
        deleted = cur.rowcount
        if deleted > 0:
            print(f"[SongDB] Verwaiste Historie bereinigt: {deleted} Eintraege")
        return deleted

    def potential_ignore(self, check_type: str, entity_id: int):
        """Markiert einen Eintrag als ignoriert."""
        self._conn.execute("""
            INSERT OR IGNORE INTO potential_ignored (check_type, entity_id)
            VALUES (?, ?);
        """, (check_type, entity_id))
        self._conn.commit()

    def potential_unignore(self, check_type: str, entity_id: int):
        """Entfernt die Ignorieren-Markierung."""
        self._conn.execute("""
            DELETE FROM potential_ignored
            WHERE check_type = ? AND entity_id = ?;
        """, (check_type, entity_id))
        self._conn.commit()

    def potential_count(self, check_type: str) -> int:
        """Zaehlt die Eintraege fuer einen Check-Typ (ohne ignorierte)."""
        method_map = {
            'singing_no_lyrics': self.potential_singing_no_lyrics,
            # Cue-Sheet-Suche arbeitet auf derselben Grundmenge wie "ohne Lyrics"
            'singing_no_lyrics_fill': self.potential_singing_no_lyrics,
            'singing_no_song_points': self.potential_singing_no_song_points,
            'singing_no_sync_points': self.potential_singing_no_sync_points,
            'pattern_no_loop': self.potential_pattern_no_loop,
            'no_bpm': self.potential_no_bpm,
            'loop_no_beatsnap': self.potential_loop_no_beatsnap,
            'location_no_history': self.potential_location_no_history,
            'history_orphaned': self.potential_history_orphaned,
            'no_quality': self.potential_no_quality,
            'no_genre': self.potential_no_genre,
            'no_err': self.potential_no_err,
            # 'no_mp3' fehlt absichtlich — Datei-Check braucht PathManager (Widget)
        }
        fn = method_map.get(check_type)
        if fn:
            return len(fn())
        return 0

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

    def _backup_before_reseed(self):
        """Pflicht-Backup der DB vor dem Reseed (Wiederherstellungspunkt)."""
        import shutil, datetime
        if not self.db_path or not os.path.exists(self.db_path):
            return
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        dst = f"{self.db_path}.bak_pre_ms50_{ts}"
        try:
            self._conn.execute("PRAGMA wal_checkpoint(FULL);")
            shutil.copy(self.db_path, dst)
            print(f"[SongDB] Pflicht-Backup vor Reseed: {os.path.basename(dst)}")
        except Exception as e:
            print(f"[SongDB] WARNUNG: Backup vor Reseed fehlgeschlagen: {e}")

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
            # 5) Builtin-dance_programs ersetzen (origin='user' bleibt erhalten)
            self._conn.execute(
                "DELETE FROM dance_programs WHERE origin IS NULL OR origin='builtin';")
            band_to_pid = {}
            for dp in ref["dance_programs"]:
                band = int(dp["band"])
                cur = self._conn.execute(
                    "INSERT INTO dance_programs "
                    "(code, label, sort_order, target_duration_min, sequence_limit_to, origin) "
                    "VALUES (?, ?, ?, ?, ?, 'builtin');",
                    (dp["code"], dp["label"], dp.get("sort_order", band),
                     7.0, band + 0.999999))
                # Class-Varianten teilen sich das Band ihres 2026-/Basis-Programms
                # (= gleiche Calls). Fuer die Band->Programm-Zuordnung der Lokations-
                # Migration zaehlt nur das Primaer-Programm, sonst zeigte eine Lokation
                # auf die Class-Variante statt aufs regulaere Programm.
                if not dp.get("is_class"):
                    band_to_pid[band] = cur.lastrowid
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
        cur = self._conn.execute(
            "INSERT INTO dance_programs (code, label, sort_order, target_duration_min, sequence_limit_to) "
            "VALUES (?, ?, ?, ?, ?);",
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

