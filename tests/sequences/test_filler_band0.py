"""Filler Words und Face schliessen keine Sequenz aus der Programmwahl aus (intern#206).

filler_words (0.001) und call_face (0.002) liegen in Band 0, vor allen
Programmen. Band 0 ist in keiner Tanzprogramm-Wahl enthalten. Bisher zaehlten
sie trotzdem als gebandete Figur, und jede Sequenz mit einem Filler-Text fiel
aus jeder Programmwahl heraus (Test-DB: 1.966 eingestufte Sequenzen).

Entity-IDs aus src/reference_calls.json.
"""
import pytest

from sequence_filter import filter_query_args

CIRCLE_LEFT = "call_circle_left"            # Basic 1, 10.0001
LOAD_THE_BOAT = "call_load_the_boat"        # Plus, 39.0007
BASIC_1 = {10}


@pytest.fixture
def db(tmp_path, keep):
    from song_db import SongDatabase

    d = keep(SongDatabase(str(tmp_path / "t.db")))
    d.set_call_text_figures("Circle Left", [CIRCLE_LEFT], mapped_by="manual")
    d.set_call_text_figures("Load The Boat", [LOAD_THE_BOAT], mapped_by="manual")
    d.set_call_text_figures("Heads Back Away", ["filler_words"], mapped_by="manual")
    d.set_call_text_figures("Face In", ["call_face"], mapped_by="manual")
    d.ids = {
        "basic": d.insert_sequence(["Circle Left"]),
        "basic_filler": d.insert_sequence(["Heads Back Away", "Circle Left"]),
        "basic_face": d.insert_sequence(["Face In", "Circle Left"]),
        "plus_filler": d.insert_sequence(["Heads Back Away", "Load The Boat"]),
        "nur_filler": d.insert_sequence(["Heads Back Away", "Face In"]),
    }
    d.recompute_sequence_max_to()
    return d


def _ids(db, **kw):
    return set(db.get_filtered_sequence_ids(**filter_query_args(**kw)))


def test_referenz_bringt_filler_und_face_in_band_0(db):
    rows = dict(db._conn.execute(
        "SELECT entity_id, teaching_order FROM call_programs "
        "WHERE entity_id IN ('filler_words', 'call_face')"))
    assert rows == {"filler_words": 0.001, "call_face": 0.002}


def test_filler_und_face_schliessen_basic_sequenz_nicht_aus(db):
    found = _ids(db, bands=BASIC_1)
    assert {db.ids["basic"], db.ids["basic_filler"], db.ids["basic_face"]} <= found


def test_plus_call_schliesst_trotz_filler_weiter_aus(db):
    assert db.ids["plus_filler"] not in _ids(db, bands=BASIC_1)


def test_sequenz_nur_aus_filler_braucht_eine_echte_figur(db):
    """Wie bisher: Ohne erkannte Figur passt eine Sequenz zu keinem Programm."""
    assert db.ids["nur_filler"] not in _ids(db, bands=BASIC_1)


def test_filler_hebt_das_limit_nicht(db):
    assert db.ids["basic_filler"] in _ids(db, limit=10.5)


def test_reseed_laesst_filler_und_face_stehen(db):
    db.reseed_reference_data(force=True)
    assert db.ids["basic_filler"] in _ids(db, bands=BASIC_1)


def test_alter_persistenter_cover_cache_gilt_nicht_mehr(db):
    """Ein Cache-Eintrag aus der alten Regel (ohne 'r'-Praefix) darf nicht
    wiederverwendet werden, sonst bliebe die Filler-Sequenz nach dem Update weg."""
    ver = db._band_data_version()
    db._conn.execute(
        "INSERT OR REPLACE INTO _band_cover (cache_key, ver, ids) VALUES (?, ?, ?)",
        (f"{sorted(BASIC_1)}|None", ver, str(db.ids["basic"])))
    db._band_cover_cache = {}
    assert db.ids["basic_filler"] in db._cover_ids(frozenset(BASIC_1))
