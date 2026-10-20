"""Sync-Anker-Abfragen der Potential-Checks (intern#140, Charakterisierung)."""
import contextlib
import io

from song_db import SongDatabase, Song


def _db(tmp_path):
    with contextlib.redirect_stdout(io.StringIO()):
        return SongDatabase(str(tmp_path / "sync.db"))


def test_songs_with_sync_anchors_nur_slot_m1_l1(tmp_path, keep):
    db = keep(_db(tmp_path))
    a = db.insert(Song(filename="a.mp3", title="A"))
    b = db.insert(Song(filename="b.mp3", title="B"))
    c = db.insert(Song(filename="c.mp3", title="C"))
    db.set_property(a.id, "lyric_sync_m1_l1_1", "1.00|0")
    db.set_property(b.id, "lyric_sync_m2_l1_1", "1.00|0")
    assert db.songs_with_sync_anchors([a.id, b.id, c.id]) == {a.id}


def test_potential_singing_no_sync_points(tmp_path, keep):
    db = keep(_db(tmp_path))
    mit = db.insert(Song(filename="mit.mp3", title="Mit", is_singing=True,
                         lyrics_file="mit.htm"))
    ohne = db.insert(Song(filename="ohne.mp3", title="Ohne", is_singing=True,
                          lyrics_file="ohne.htm"))
    db.set_property(mit.id, "lyric_sync_m3_l2_1", "1.00|0")
    ids = [r[0] for r in db.potential_singing_no_sync_points()]
    assert ids == [ohne.id]
