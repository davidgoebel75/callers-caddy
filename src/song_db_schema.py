"""Datenbank-Schema und Update-Weg von SongDatabase (intern#145, intern#165).

Die _CREATE_*-Konstanten sind die einzige Stelle, an der Spalten stehen.
Fehlende Spalten alter DBs leitet _add_missing_columns() daraus ab.
Mixin: SongDatabase erbt die Methoden; __init__ ruft _migrate(),
_create_tables() und _apply_data_fixes().
"""
import sqlite3


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


# BL-094: Generische Song-Properties (Key/Value)
_CREATE_SONG_PROPERTIES_TABLE = """
CREATE TABLE IF NOT EXISTS song_properties (
    song_id INTEGER NOT NULL,
    key     TEXT    NOT NULL,
    value   TEXT    NOT NULL DEFAULT '',
    PRIMARY KEY (song_id, key),
    FOREIGN KEY (song_id) REFERENCES songs(id) ON DELETE CASCADE
);
"""


# intern#247: Ergebnis der Choreo-Engine je Sequenz (Square Flow): Urteil,
# Takte je Zeile, Hinweise (ohne Animation). Abgeleitet und jederzeit
# verwerfbar: passt input_hash (Zeilen, Typ, Mapping-Stand, App-Callnamen)
# oder engine_ver nicht mehr, wird neu gerechnet und ueberschrieben.
_CREATE_SEQUENCE_CHOREO_TABLE = """
CREATE TABLE IF NOT EXISTS sequence_choreo (
    sequence_id  INTEGER PRIMARY KEY,
    input_hash   TEXT NOT NULL DEFAULT '',
    engine_ver   TEXT NOT NULL DEFAULT '',
    result_json  TEXT NOT NULL DEFAULT ''
);
"""


# intern#164: Beats je Call nach den CALLERLAB-Timing-Charts. Reine Referenz aus
# src/callerlab_timing.json (erzeugt von tools/beats/build_callerlab_timing.py),
# beim Start komplett ersetzt, sobald sich dessen Version aendert (Marke
# callerlab_timing_version in app_meta; song_db_timing.py). Spalten wie die
# Pflegedatei; entity_ids bleibt Text ('a|b' = einer davon, 'a+b' = beide
# zusammen), id = Reihenfolge der Datei.
_CREATE_CALL_TIMING_TABLE = """
CREATE TABLE IF NOT EXISTS call_timing (
    id              INTEGER PRIMARY KEY,
    programm        TEXT NOT NULL DEFAULT '',
    call            TEXT NOT NULL DEFAULT '',
    entity_ids      TEXT NOT NULL DEFAULT '',
    variante        TEXT NOT NULL DEFAULT '',
    typ             TEXT NOT NULL DEFAULT '',
    beats           INTEGER,
    beats_bis       INTEGER,
    anything_ab     INTEGER,
    quelle          TEXT NOT NULL DEFAULT '',
    bemerkung       TEXT NOT NULL DEFAULT '',
    standard        INTEGER NOT NULL DEFAULT 0,
    variante_regel  TEXT NOT NULL DEFAULT ''
);
"""


# MS50-Umbau: kleiner Key/Value-Speicher fuer Referenzdaten-Version u.ae.
_CREATE_APP_META_TABLE = """
CREATE TABLE IF NOT EXISTS app_meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);
"""


# intern#145: Alle Tabellen mit Spalten-Deklaration. _add_missing_columns()
# gleicht bestehende DBs dagegen ab. Neue Tabelle -> hier eintragen.
# ponytail: die Cache-Tabellen _band_cache_ver/_band_cover fehlen bewusst, sie
# entstehen in _create_band_cache_triggers(); bekommen sie je eine neue Spalte,
# dort nachziehen.
_TABLE_SCHEMAS = (
    _CREATE_TABLE, _CREATE_LOCATIONS_TABLE, _CREATE_GENRES_TABLE,
    _CREATE_SONG_GENRES_TABLE, _CREATE_SONG_PROPERTIES_TABLE,
    _CREATE_PLAY_HISTORY_TABLE, _CREATE_SONG_LOCATION_STATS_TABLE,
    _CREATE_SEQUENCES_TABLE, _CREATE_CALLS_TABLE, _CREATE_CALL_PROGRAMS_TABLE,
    _CREATE_CALL_TEXT_MAPPINGS_TABLE, _CREATE_CALL_TEXT_FIGURES_EXTRA_TABLE,
    _CREATE_SEQUENCE_CALLS_TABLE, _CREATE_POTENTIAL_IGNORED_TABLE,
    _CREATE_NOTES_TABLE, _CREATE_DANCE_PROGRAMS_TABLE,
    _CREATE_LOCATION_PROGRAMS_TABLE, _CREATE_APP_META_TABLE,
    _CREATE_SEQUENCE_CHOREO_TABLE, _CREATE_CALL_TIMING_TABLE,
)


def _add_column_sql(ref: sqlite3.Connection, table: str, col: str) -> str:
    """ALTER TABLE ... ADD COLUMN fuer Spalte `col` aus der Referenz-DB `ref`
    (dort sind die _CREATE_*-Konstanten ausgefuehrt).

    ValueError, wenn SQLite die Spalte so nicht nachruesten kann. Dann braucht
    sie eine eigene Migration (intern#145). tests/db/test_schema.py prueft das
    fuer jede neue Spalte schon beim Entwickeln.
    """
    info = {r[1]: r for r in ref.execute(f"PRAGMA table_info({table})")}
    _cid, _name, ctype, notnull, dflt, pk = info[col]
    if pk:
        raise ValueError("PRIMARY KEY nicht per ADD COLUMN nachruestbar")
    for _seq, idx, unique, _origin, _partial in ref.execute(
            f"PRAGMA index_list({table})"):
        idx_cols = [r[2] for r in ref.execute(f"PRAGMA index_info({idx})")]
        if unique and col in idx_cols:
            raise ValueError("UNIQUE nicht per ADD COLUMN nachruestbar")
    if any(fk[3] == col for fk in ref.execute(f"PRAGMA foreign_key_list({table})")):
        raise ValueError("FOREIGN KEY ginge per ADD COLUMN verloren")
    if notnull and dflt is None:
        raise ValueError("NOT NULL ohne Standardwert nicht nachruestbar")
    if dflt is not None and "(" in dflt and not dflt.startswith("'"):
        raise ValueError(f"Standardwert {dflt} ist nicht konstant")
    sql = f"ALTER TABLE {table} ADD COLUMN {col} {ctype}"
    if notnull:
        sql += " NOT NULL"
    if dflt is not None:
        sql += f" DEFAULT {dflt}"
    return sql


# intern#145: Spalten stehen nur noch in den _CREATE_*-Konstanten. Fehlende
# Spalten einer bestehenden DB leitet _add_missing_columns() daraus ab. Hier
# bleiben nur Daten-Korrekturen, in fester Reihenfolge, bei jedem Start nach
# _create_tables(). Jede muss idempotent sein (WHERE-Klausel, die nach dem
# ersten Lauf nichts mehr trifft).
_DATA_FIXES = [
    # BL-XXX: quality-Spalte bereinigen (REAL/TEXT → INTEGER, behebt Crash bei str > int)
    "UPDATE songs SET quality = CAST(ROUND(quality) AS INTEGER) WHERE typeof(quality) != 'integer';",
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
]


class SchemaMixin:
    """Tabellen anlegen und alte DBs auf den aktuellen Stand bringen."""

    def _create_tables(self):
        self._conn.execute(_CREATE_TABLE)
        self._conn.execute(_CREATE_LOCATIONS_TABLE)
        self._conn.execute(_CREATE_GENRES_TABLE)
        self._conn.execute(_CREATE_SONG_GENRES_TABLE)
        self._conn.execute(_CREATE_SONG_PROPERTIES_TABLE)
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
        self._conn.execute(_CREATE_SEQUENCE_CHOREO_TABLE)
        self._conn.execute(_CREATE_CALL_TIMING_TABLE)
        self._create_band_cache_triggers()
        self._conn.commit()
        self._insert_default_dance_programs()

    def _create_band_cache_triggers(self):
        """MS50-Perf: Versions-Zaehler fuer den Band-Cache. Jede Aenderung an den
        Tabellen, die das "welche Sequenz ist mit diesen Baendern tanzbar"-Ergebnis
        beeinflussen (sequence_calls, call_text_mappings,
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
        # intern#111: `sequences` selbst zaehlt nicht — das Cover liest nur
        # sequence_calls, und jeder Einfuege-/Bearbeiten-/Loesch-Pfad schreibt dort.
        # Der Trigger auf sequences verwarf den Cache z.B. bei jedem
        # recompute_sequence_max_to (11k Zeilen -> 11k Zaehler-Updates).
        for op in ("ins", "upd", "del"):
            self._conn.execute(f"DROP TRIGGER IF EXISTS _bcv_sequences_{op}")
        for tbl in ("sequence_calls", "call_text_mappings",
                    "call_text_figures_extra", "call_programs"):
            for op, when in (("ins", "AFTER INSERT"),
                             ("upd", "AFTER UPDATE"),
                             ("del", "AFTER DELETE")):
                self._conn.execute(
                    f"CREATE TRIGGER IF NOT EXISTS _bcv_{tbl}_{op} "
                    f"{when} ON {tbl} BEGIN "
                    f"UPDATE _band_cache_ver SET v = v + 1; END;")

    def _has_table(self, name: str) -> bool:
        return self._conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (name,)).fetchone() is not None

    def _migrate(self):
        """Bringt bestehende Tabellen auf den Stand der _CREATE_*-Konstanten.

        Reihenfolge (intern#145): Umbenennung clubs -> locations, dann fehlende
        Spalten, dann die Struktur-Umbauten. Danach legt _create_tables()
        fehlende Tabellen an, und _apply_data_fixes() korrigiert Daten.
        Probleme landen in self.schema_problems statt verschluckt zu werden.
        """
        # P20: Clubs -> Locations umbenennen
        if self._has_table("clubs") and not self._has_table("locations"):
            self._conn.execute("ALTER TABLE clubs RENAME TO locations")
            self._conn.commit()
            print("[SongDB] Migration: clubs -> locations umbenannt")

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

        self._add_missing_columns()
        self._migrate_calls_split()
        self._migrate_location_programs()

    def _add_missing_columns(self):
        """Ergaenzt in bestehenden Tabellen die Spalten, die in _CREATE_*
        stehen, aber in der DB fehlen (intern#145).

        Die _CREATE_*-Konstanten laufen dazu in einer leeren In-Memory-DB;
        PRAGMA table_info liefert Typ, NOT NULL und Standardwert, daraus baut
        _add_column_sql() das ALTER. Fehlende Tabellen legt danach
        _create_tables() komplett an. Nicht nachruestbare Spalten werden nicht
        verschluckt: sie landen in self.schema_problems, main meldet sie.
        """
        from song_db import _safe_print  # zirkelfrei: erst zur Laufzeit
        ref = sqlite3.connect(":memory:")
        try:
            for create in _TABLE_SCHEMAS:
                ref.execute(create)
            tables = [r[0] for r in ref.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
            for table in tables:
                have = {r[1] for r in self._conn.execute(
                    f"PRAGMA table_info({table})")}
                if not have:
                    continue  # Tabelle fehlt ganz -> _create_tables()
                for r in ref.execute(f"PRAGMA table_info({table})").fetchall():
                    col = r[1]
                    if col in have:
                        continue
                    try:
                        self._conn.execute(_add_column_sql(ref, table, col))
                        _safe_print(f"[SongDB] Migration: Spalte {table}.{col} ergaenzt")
                    except (ValueError, sqlite3.Error) as e:
                        self.schema_problems.append(f"{table}.{col}: {e}")
            self._conn.commit()
        finally:
            ref.close()

    def _apply_data_fixes(self):
        """Daten-Korrekturen aus _DATA_FIXES, bei jedem Start (idempotent)."""
        from song_db import _safe_print  # zirkelfrei: erst zur Laufzeit
        for sql in _DATA_FIXES:
            try:
                n = self._conn.execute(sql).rowcount
            except sqlite3.Error as e:
                self.schema_problems.append(f"Datenkorrektur {sql.strip()[:50]}: {e}")
                continue
            if n > 0:
                _safe_print(f"[SongDB] Datenkorrektur ({n} Zeilen): {sql.strip()[:60]}...")
        self._conn.commit()

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
        # Ziel des Fremdschluessels muss existieren, sonst scheitert der INSERT
        # unten bei DBs aus der Zeit vor den Tanzprogrammen (intern#145, T5).
        self._conn.execute(_CREATE_DANCE_PROGRAMS_TABLE)
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
