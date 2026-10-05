"""Statistik bei geteilter Historie (intern#137).

Teilt Lokation B die Historie von A, landen Plays an B unter A (log_play loest
auf die Senke auf). Die Statistik fuer B muss sie trotzdem zeigen.
"""
import contextlib
import io

import pytest

from song_db import Song, SongDatabase


@pytest.fixture
def db(tmp_path):
    with contextlib.redirect_stdout(io.StringIO()):
        db = SongDatabase(str(tmp_path / "stats.db"))
    yield db
    db.close()


def _song(db, title, **flags):
    return db.insert(Song(filename=f"{title}.mp3", title=title, **flags)).id


def test_shared_history_counts_for_both_locations(db):
    a = db.insert_location("A").id
    b = db.insert_location("B").id
    db.set_shared_history(b, a)
    sid = _song(db, "Patter", is_singing=0)
    with contextlib.redirect_stdout(io.StringIO()):
        db.log_play(sid, b)
        db.log_play(sid, b)

    for loc in (a, b, None):
        assert [(r[0], r[3]) for r in db.play_counts(loc, None, None)] == [(sid, 2)]
    assert db.play_counts(b, None, "singing") == []
    assert db.play_counts(b, "2999-01-01 00:00:00", None) == []


def test_songs_by_type(db):
    p = _song(db, "Patter", is_singing=0)
    s = _song(db, "Singing", is_pattern=0)
    assert {r[0] for r in db.songs_by_type(None)} == {p, s}
    assert [r[0] for r in db.songs_by_type("pattern")] == [p]
    assert [r[0] for r in db.songs_by_type("singing")] == [s]
