"""Rauchtest: jede Potential-Abfrage laeuft auf einer frischen DB (intern#165).

Die Checks stehen im Mixin song_db_potential; der Test faengt kaputtes SQL und
Import-Fehler ab (z. B. den Lazy-Import von CHECK_BEATSNAP_GENRE_NAME).
"""
import contextlib
import inspect
import io

from song_db import SongDatabase, Song
from song_db_potential import PotentialMixin


def test_every_potential_query_runs(tmp_path):
    with contextlib.redirect_stdout(io.StringIO()):
        db = SongDatabase(str(tmp_path / "pot.db"))
    try:
        no_args = [name for name, fn in vars(PotentialMixin).items()
                   if inspect.isfunction(fn) and not name.startswith("_")
                   and len(inspect.signature(fn).parameters) == 1]
        assert len(no_args) > 15, no_args
        for name in no_args:
            with contextlib.redirect_stdout(io.StringIO()):
                getattr(db, name)()
    finally:
        db.close()


def test_potential_queries_with_parameters(tmp_path):
    with contextlib.redirect_stdout(io.StringIO()):
        db = SongDatabase(str(tmp_path / "pot.db"))
    try:
        song = db.insert(Song(filename="ohne_lyrics.mp3", title="Ohne Lyrics"))
        before = db.potential_count("singing_no_lyrics")
        assert before >= 1
        db.potential_ignore("singing_no_lyrics", song.id)
        assert db.potential_count("singing_no_lyrics") == before - 1
        db.potential_unignore("singing_no_lyrics", song.id)
        assert db.potential_count("singing_no_lyrics") == before
        assert db.potential_count("unbekannt") == 0
        assert db.songs_with_sync_anchors([song.id]) == set()
    finally:
        db.close()
