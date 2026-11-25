"""SongDatabase.open_worker_connection und write_base_bpm (intern#139)."""
import contextlib
import io
import threading

import pytest

from song_db import SongDatabase
from song_db_potential import PotentialMixin


@pytest.fixture
def db(tmp_path, keep):
    with contextlib.redirect_stdout(io.StringIO()):
        d = keep(SongDatabase(str(tmp_path / "w.db")))
    return d


def _add_song(db):
    db._conn.execute(
        "INSERT INTO songs (filename, title) VALUES ('a.mp3', 'A')")
    db._conn.commit()
    return db._conn.execute("SELECT id FROM songs").fetchone()[0]


def _bpm(db, sid):
    return db._conn.execute(
        "SELECT base_bpm FROM songs WHERE id=?", (sid,)).fetchone()[0]


def test_worker_connection_is_separate_with_pragmas(db):
    conn = db.open_worker_connection()
    try:
        assert conn is not db._conn
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert conn.execute("PRAGMA busy_timeout").fetchone()[0] == 30000
    finally:
        conn.close()


def test_write_from_foreign_thread_visible_after_commit(db):
    sid = _add_song(db)
    errors = []

    def work():
        try:
            conn = db.open_worker_connection()
            PotentialMixin.write_base_bpm(conn, sid, 128.0)
            conn.commit()
            conn.close()
        except Exception as e:  # pragma: no cover
            errors.append(e)
    t = threading.Thread(target=work)
    t.start()
    t.join()
    assert not errors
    assert _bpm(db, sid) == 128.0


def test_write_base_bpm_does_not_commit(db):
    sid = _add_song(db)
    conn = db.open_worker_connection()
    try:
        PotentialMixin.write_base_bpm(conn, sid, 120.0)
        assert _bpm(db, sid) in (None, 0, 0.0)   # Main sieht es noch nicht
        conn.commit()
        assert _bpm(db, sid) == 120.0
    finally:
        conn.close()
