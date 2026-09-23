"""intern#106: Doppelgaenger von Unterordner-Songs erkennen und zusammenfuehren."""
import pytest

from song_db import Song, SongDatabase
from subfolder_duplicate_repair import find_pairs, repair_subfolder_duplicates


@pytest.fixture
def db(tmp_path):
    d = SongDatabase(str(tmp_path / "test.db"))
    d.seed_default_genres()
    yield d
    d.close()


def _finder(existing):
    """find_song_file-Ersatz: nur die genannten DB-Dateinamen sind auffindbar."""
    return lambda name: f"X:/music/{name}" if name in existing else None


def _make_pair(db):
    """Original per Import (nur Pattern) + Doppelgaenger wie bis v0.158."""
    a = db.insert(Song(filename="Patter/Get_Lucky.mp3", title="Get Lucky",
                       label="RYL 101", is_pattern=1, is_singing=0))
    b = db.get_or_create("Get_Lucky.mp3")   # Default: Pattern + Singing
    return a, b


def test_findet_doppelgaenger(db):
    a, b = _make_pair(db)
    pairs = find_pairs(db, _finder({"Patter/Get_Lucky.mp3"}))
    assert [(p.id, q.id) for p, q in pairs] == [(a.id, b.id)]


def test_legitimer_song_im_slot_stamm_bleibt(db):
    _make_pair(db)
    finder = _finder({"Patter/Get_Lucky.mp3", "Get_Lucky.mp3"})
    assert find_pairs(db, finder) == []


def test_offline_laufwerk_wird_nicht_angefasst(db):
    _make_pair(db)
    assert find_pairs(db, _finder(set())) == []


def test_mehrdeutiger_basename_wird_nicht_angefasst(db):
    _make_pair(db)
    db.insert(Song(filename="Singing/Get_Lucky.mp3", title="Get Lucky 2"))
    finder = _finder({"Patter/Get_Lucky.mp3", "Singing/Get_Lucky.mp3"})
    assert find_pairs(db, finder) == []


def test_zusammenfuehren_uebernimmt_aenderungen_des_doppelgaengers(db):
    a, b = _make_pair(db)
    # Nutzer hat am Doppelgaenger korrigiert und gespielt
    b.is_singing = 0
    b.base_bpm = 124.0
    db.update(b)
    db.set_property(b.id, "marker_1_time", "12.5")
    loc = db.insert_location("Club")
    db.log_play(b.id, loc.id)
    db.log_play(a.id, loc.id)

    n = repair_subfolder_duplicates(db, _finder({"Patter/Get_Lucky.mp3"}))

    assert n == 1
    assert db.get_by_id(b.id) is None
    merged = db.get_by_id(a.id)
    assert merged.filename == "Patter/Get_Lucky.mp3"
    assert (merged.is_pattern, merged.is_singing) == (1, 0)
    assert merged.base_bpm == 124.0
    # Unveraenderte Defaults am Doppelgaenger ueberschreiben das Original nicht
    assert merged.title == "Get Lucky"
    assert merged.label == "RYL 101"
    assert db.get_properties(a.id).get("marker_1_time") == "12.5"
    hist = db._conn.execute(
        "SELECT COUNT(*) FROM play_history WHERE song_id = ?", (a.id,)).fetchone()[0]
    assert hist == 2
    count = db._conn.execute(
        "SELECT play_count FROM song_location_stats WHERE song_id = ? AND location_id = ?",
        (a.id, loc.id)).fetchone()[0]
    assert count == 2
    assert len(db.get_all()) == 1


def test_default_pattern_singing_ueberschreibt_import_nicht(db):
    a, b = _make_pair(db)   # b unveraendert: P+S Default
    repair_subfolder_duplicates(db, _finder({"Patter/Get_Lucky.mp3"}))
    merged = db.get_by_id(a.id)
    assert (merged.is_pattern, merged.is_singing) == (1, 0)
