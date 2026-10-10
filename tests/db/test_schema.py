"""Update-Weg der Datenbank von jedem bekannten Altstand (intern#145).

Spalten stehen nur noch in den _CREATE_*-Konstanten von song_db_schema.py. Fehlende
Spalten einer bestehenden DB leitet _add_missing_columns() daraus ab.

Geprueft wird gegen Schema-Abbilder in schemas/: nur CREATE-Statements, keine
Daten. Die alten Staende stammen aus Davids Test- und Nutzer-DBs
(callers-caddy-intern, testdaten/alte-dbs), benannt nach Datum; die Release-
Staende nach Version. Jedes Abbild wird zu einer leeren DB, SongDatabase
oeffnet sie, danach muss sie genau die Spalten einer frischen DB haben.

Das neueste Release-Abbild faengt auch neue Spalten ab: Laesst sich eine
Spalte nicht per ADD COLUMN nachruesten (PRIMARY KEY, UNIQUE, FOREIGN KEY,
NOT NULL ohne Standardwert, Funktion als Standardwert), wird der Test rot,
lange bevor ein Caller das Update bekommt.

Neues Release -> neues Abbild, vom Repo-Stamm aus:
    python tests/db/test_schema.py 0.XX
"""
import contextlib
import io
import pathlib
import re
import sqlite3
import sys
import tempfile

import pytest

if __name__ == "__main__":  # als Skript (Abbild schreiben): src/ selbst holen
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "src"))

import song_db_schema  # noqa: E402
from song_db import SongDatabase  # noqa: E402

_SCHEMAS = pathlib.Path(__file__).resolve().parent / "schemas"


def _open(path) -> SongDatabase:
    with contextlib.redirect_stdout(io.StringIO()):
        return SongDatabase(str(path))


def _columns(path) -> dict[str, set[str]]:
    conn = sqlite3.connect(path)
    try:
        tables = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
        return {t: {r[1] for r in conn.execute(f"PRAGMA table_info({t})")}
                for t in tables}
    finally:
        conn.close()


def _db_from_schema(schema: pathlib.Path, path: pathlib.Path) -> pathlib.Path:
    conn = sqlite3.connect(path)
    conn.executescript(schema.read_text(encoding="utf-8"))
    conn.close()
    return path


@pytest.fixture(scope="module")
def fresh_columns(tmp_path_factory) -> dict[str, set[str]]:
    path = tmp_path_factory.mktemp("schema") / "fresh.db"
    _open(path).close()
    return _columns(path)


@pytest.mark.parametrize("schema", sorted(_SCHEMAS.glob("*.sql")),
                         ids=lambda p: p.stem)
def test_update_from_old_schema(schema, tmp_path, fresh_columns):
    db = _open(_db_from_schema(schema, tmp_path / "old.db"))
    problems = db.schema_problems
    db.close()
    assert problems == [], f"Update von {schema.stem} unvollstaendig: {problems}"
    after = _columns(tmp_path / "old.db")
    missing = sorted(f"{t}.{c}" for t, cols in fresh_columns.items()
                     for c in cols - after.get(t, set()))
    assert not missing, f"Nach Update von {schema.stem} fehlen: {missing}"


def test_unaddable_column_is_reported_not_raised(tmp_path, monkeypatch):
    """Geht beim Nutzer doch etwas schief, startet die App weiter und meldet
    es ueber schema_problems (main zeigt einen Dialog)."""
    broken = song_db_schema._CREATE_TABLE.replace(
        "err             INTEGER NOT NULL DEFAULT 0",
        "err             INTEGER NOT NULL DEFAULT 0,\n    _unaddable_probe TEXT NOT NULL")
    assert broken != song_db_schema._CREATE_TABLE
    monkeypatch.setattr(song_db_schema, "_TABLE_SCHEMAS",
                        (broken,) + song_db_schema._TABLE_SCHEMAS[1:])
    db = _open(_db_from_schema(_SCHEMAS / "0.160.sql", tmp_path / "old.db"))
    problems = db.schema_problems
    db.close()
    assert len(problems) == 1, problems
    assert problems[0].startswith("songs._unaddable_probe:"), problems


def test_every_create_table_is_registered():
    """Eine Tabelle, die nicht in _TABLE_SCHEMAS steht, bekaeme in alten DBs
    nie neue Spalten."""
    created = {re.search(r"CREATE TABLE IF NOT EXISTS (\w+)", v)[1]
               for k, v in vars(song_db_schema).items()
               if k.startswith("_CREATE_") and isinstance(v, str)
               and "CREATE TABLE" in v}
    registered = {re.search(r"CREATE TABLE IF NOT EXISTS (\w+)", v)[1]
                  for v in song_db_schema._TABLE_SCHEMAS}
    assert created == registered, f"fehlt in _TABLE_SCHEMAS: {created - registered}"


def _write_snapshot(version: str) -> pathlib.Path:
    """Schema-Abbild einer frischen DB, ohne Daten."""
    path = pathlib.Path(tempfile.mkdtemp()) / "fresh.db"
    _open(path).close()
    conn = sqlite3.connect(path)
    rows = conn.execute(
        "SELECT sql FROM sqlite_master "
        "WHERE sql IS NOT NULL AND name NOT LIKE 'sqlite_%' "
        "ORDER BY CASE type WHEN 'table' THEN 0 WHEN 'index' THEN 1 "
        "WHEN 'view' THEN 2 ELSE 3 END, name").fetchall()
    conn.close()
    out = _SCHEMAS / f"{version}.sql"
    out.write_text("".join(f"{sql.strip()};\n\n" for (sql,) in rows),
                   encoding="utf-8", newline="\n")
    return out


if __name__ == "__main__":
    print(_write_snapshot(sys.argv[1]))
