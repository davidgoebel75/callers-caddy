"""Abendplaner: Tage seit zuletzt gespielt zaehlen Kalendertage in Ortszeit.

last_played wird in Ortszeit geschrieben (datetime('now','localtime')). Frueher
rechnete get_planner_candidates gegen julianday('now') (UTC) und schnitt auf
volle 24 h: gestern 23:59 gespielt hiess bis zum naechsten Abend "0 Tage", und um
Mitternacht lag der Planer gegenueber der Songliste um einen Tag daneben.
"""
import contextlib
import io

import pytest

from song_db import SongDatabase, Song


@pytest.fixture
def db(tmp_path, keep):
    with contextlib.redirect_stdout(io.StringIO()):
        return keep(SongDatabase(str(tmp_path / "plan.db")))


def _days(db, last_played_sql):
    song = db.insert(Song(filename="a.mp3", title="A", quality=3, err=2))
    loc = db._conn.execute("SELECT id FROM locations LIMIT 1").fetchone()
    if loc is None:
        db._conn.execute("INSERT INTO locations (name) VALUES ('Hall')")
        loc = db._conn.execute("SELECT id FROM locations LIMIT 1").fetchone()
    db._conn.execute(
        "INSERT INTO song_location_stats (song_id, location_id, last_played, play_count) "
        f"VALUES (?, ?, {last_played_sql}, 1)", (song.id, loc[0]))
    db._conn.commit()
    rows = db.get_planner_candidates(2, loc[0], days_fallback=730)
    return [r[7] for r in rows if r[0] == song.id][0]


def test_gestern_spaet_gespielt_ist_ein_tag(db):
    assert _days(db, "date('now','localtime','-1 day') || ' 23:59:00'") == 1


def test_heute_gespielt_ist_null_tage(db):
    assert _days(db, "datetime('now','localtime')") == 0


def test_vor_zehn_tagen_ist_zehn_tage(db):
    assert _days(db, "datetime('now','localtime','-10 days')") == 10


def test_nie_gespielt_nimmt_fallback(db):
    song = db.insert(Song(filename="b.mp3", title="B", quality=3, err=2))
    rows = db.get_planner_candidates(2, None, days_fallback=730)
    assert [r[7] for r in rows if r[0] == song.id] == [730]
