"""Schema-Abgleich zwischen _CREATE_* und _MIGRATIONS (intern#145).

Jede Spalte steht in song_db.py zweimal: in den _CREATE_*-Konstanten (fuer
eine frische DB) und in _MIGRATIONS (fuer bestehende DBs). Nichts vergleicht
die beiden, und _migrate() verschluckt OperationalError. Zwei Richtungen:

A. Eine Spalte nur in _MIGRATIONS fehlt bei jeder Neuinstallation: auf einer
   frischen DB laeuft _migrate() vor _create_tables(), die ALTERs gehen also
   ins Leere.
B. Eine Spalte nur in _CREATE_* fehlt bei jedem Update: eine bestehende
   Tabelle bekommt neue Spalten ausschliesslich ueber _MIGRATIONS.

Fuer B steht unten der Grundbestand je Tabelle: Spalten, die von Anfang an im
CREATE standen. Eingefroren am Stand 0.160; abgeglichen mit 0.150, seitdem
kam keine Spalte dazu. Eine neue Spalte gehoert nach _MIGRATIONS (und ins
CREATE), nie hierher. Eine neue Tabelle traegt man hier einmal komplett ein.
"""
import re
import sqlite3

import pytest

import song_db
from song_db import SongDatabase

_BASE_COLUMNS = {
    "_band_cache_ver": {"v"},
    "_band_cover": {"cache_key", "ver", "ids"},
    "app_meta": {"key", "value"},
    "call_programs": {"id", "entity_id", "teaching_order", "program"},
    "call_text_figures_extra": {"call_text", "entity_id"},
    "call_text_mappings": {"call_text", "entity_id", "mapped_by"},
    "calls": {"entity_id", "canonical_name"},
    "dance_programs": {"id", "code", "label", "sort_order",
                       "target_duration_min"},
    "genres": {"id", "name"},
    "location_programs": {"location_id", "dance_program_id"},
    "locations": {"id", "name"},
    "notes": {"id", "text", "status", "location_id", "sort_order",
              "note_type", "created_at", "done_at", "source", "source_ref"},
    "play_history": {"id", "song_id", "location_id", "played_at"},
    "potential_ignored": {"check_type", "entity_id", "ignored_at"},
    "sequence_calls": {"id", "sequence_id", "position", "call_text",
                       "entity_id", "teaching_order"},
    "sequences": {"id", *(f"field_{i}" for i in range(1, 16)),
                  "level_original", "max_teaching_order"},
    "song_genres": {"song_id", "genre_id"},
    "song_location_stats": {"song_id", "location_id", "last_played",
                            "play_count"},
    "song_properties": {"song_id", "key", "value"},
    "songs": {"id", "filename", "title", "label", "quality", "base_bpm",
              "standard_tempo", "pitch", "volume", "loop_in", "loop_out",
              "lyrics_file"},
}


def _migration_columns() -> set:
    """(Tabelle, Spalte) aller ALTER TABLE ... ADD COLUMN in _MIGRATIONS."""
    pattern = re.compile(r"\s*ALTER TABLE (\w+) ADD COLUMN (\w+)", re.I)
    return {m.groups() for sql in song_db._MIGRATIONS
            if (m := pattern.match(sql))}


@pytest.fixture(scope="module")
def fresh_columns(tmp_path_factory) -> dict:
    """Spalten je Tabelle einer frisch angelegten DB."""
    path = tmp_path_factory.mktemp("schema") / "fresh.db"
    SongDatabase(str(path))._conn.close()
    conn = sqlite3.connect(path)
    try:
        tables = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
        return {t: {r[1] for r in conn.execute(f"PRAGMA table_info({t})")}
                for t in tables}
    finally:
        conn.close()


def test_fresh_db_has_all_migration_columns(fresh_columns):
    missing = sorted(f"{t}.{c}" for t, c in _migration_columns()
                     if c not in fresh_columns.get(t, set()))
    assert not missing, (
        f"Nur in _MIGRATIONS, fehlt bei Neuinstallation: {missing}. "
        f"Spalte auch ins passende _CREATE_* schreiben.")


def test_every_create_column_reaches_existing_dbs(fresh_columns):
    migrated = _migration_columns()
    problems = []
    for table, cols in sorted(fresh_columns.items()):
        if table not in _BASE_COLUMNS:
            problems.append(f"neue Tabelle {table}: einmal komplett in "
                            f"_BASE_COLUMNS eintragen")
            continue
        extra = sorted(c for c in cols - _BASE_COLUMNS[table]
                       if (table, c) not in migrated)
        if extra:
            problems.append(f"{table}: {extra} nur im CREATE, fehlt bei "
                            f"Update. ALTER TABLE ... ADD COLUMN nach "
                            f"_MIGRATIONS")
    assert not problems, "\n".join(problems)
