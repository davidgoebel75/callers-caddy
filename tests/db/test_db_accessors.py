"""Abfragen, die frueher per db._conn in den Widgets standen (intern#138)."""
import contextlib
import io

import pytest

from song_db import SongDatabase


@pytest.fixture
def db(tmp_path):
    with contextlib.redirect_stdout(io.StringIO()):
        db = SongDatabase(str(tmp_path / "acc.db"))
    yield db
    db.close()


def test_get_location_name(db):
    loc = db.insert_location("Club A")
    assert db.get_location_name(loc.id) == "Club A"
    assert db.get_location_name(loc.id + 99) is None


def test_next_note_order_ignores_deleted(db):
    loc = db.insert_location("A").id
    assert db.next_note_order(loc) == 1
    db.add_note("eins", loc, sort_order=3)
    gone = db.add_note("weg", loc, sort_order=9)
    db.set_note_status(gone, "deleted")
    assert db.next_note_order(loc) == 4


def test_get_real_calls_skips_separators(db):
    names = [name for _eid, name in db.get_real_calls()]
    assert names, "Referenzdaten ohne Calls"
    assert not any(n.startswith("--") for n in names)


def test_get_all_calls_json(db):
    with contextlib.redirect_stdout(io.StringIO()):
        db.insert_sequence(["Heads Square Thru 4", "Dosado"])
    found = db.get_all_calls_json()
    assert any("Dosado" in cj for cj in found)
    assert None not in found and "" not in found
