"""Review #194: _ensure_band_scope darf keine offene Transaktion hinterlassen.

Ohne commit() blieb die Haupt-Verbindung nach dem Fuellen von seq_scope in einer
Transaktion mit altem Lese-Stand. Schrieb danach eine zweite Verbindung (Square-Flow-
Cache), schlug jeder Schreibzugriff der Haupt-Verbindung mit "database is locked" fehl.
"""
import contextlib
import io
import sqlite3

from song_db import SongDatabase


def test_band_scope_laesst_keine_transaktion_offen(tmp_path, keep):
    path = str(tmp_path / "scope.db")
    with contextlib.redirect_stdout(io.StringIO()):
        db = keep(SongDatabase(path))
    db._ensure_band_scope({1}, None)
    assert not db._conn.in_transaction
    other = sqlite3.connect(path, timeout=0.2)
    other.execute("CREATE TABLE zweiter_schreiber (a)")
    other.commit()
    other.close()
    db._conn.execute("CREATE TABLE haupt_schreibt (a)")
    db._conn.commit()
