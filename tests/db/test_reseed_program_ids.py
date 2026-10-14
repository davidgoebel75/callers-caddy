"""Ein Referenz-Update laesst die ids der Tanzprogramme stehen (intern#206).

reseed_reference_data() loeschte alle mitgelieferten dance_programs und legte
sie neu an - mit neuen ids. location_programs, locations.dance_program_id und
die INI (sequences/dance_programs) speichern ids und zeigten danach ins Leere:
Jede Lokation verlor beim naechsten REFERENCE_DATA_VERSION-Bump ihr Programm.
"""
import pytest


@pytest.fixture
def db(tmp_path, keep):
    from song_db import SongDatabase

    return keep(SongDatabase(str(tmp_path / "t.db")))


def _ids(db):
    return {code: pid for pid, code, *_ in db.get_all_dance_programs()}


def test_reseed_behaelt_ids_und_lokations_programme(db):
    before = _ids(db)
    loc = db.insert_location("Club")
    progs = [before["MS2026"], before["PL2026"]]
    db.set_location_program_ids(loc.id, progs)

    db.reseed_reference_data(force=True)

    assert _ids(db) == before
    assert sorted(db.get_location_program_ids(loc.id)) == sorted(progs)


def test_reseed_behaelt_eingestellte_ziel_dauer(db):
    db._conn.execute(
        "UPDATE dance_programs SET target_duration_min=9.5 WHERE code='MS2026'")
    db.reseed_reference_data(force=True)
    assert db._conn.execute(
        "SELECT target_duration_min FROM dance_programs WHERE code='MS2026'"
    ).fetchone()[0] == 9.5


def test_reseed_entfernt_weggefallenes_programm_samt_zuordnung(db):
    cur = db._conn.execute(
        "INSERT INTO dance_programs (code, label, origin) VALUES ('ALT', 'Alt', 'builtin')")
    old = cur.lastrowid
    loc = db.insert_location("Club")
    db.set_location_program_ids(loc.id, [old, _ids(db)["MS2026"]])

    db.reseed_reference_data(force=True)

    assert "ALT" not in _ids(db)
    assert db.get_location_program_ids(loc.id) == [_ids(db)["MS2026"]]


def test_reseed_laesst_eigenes_programm_stehen(db):
    db._conn.execute(
        "INSERT INTO dance_programs (code, label, origin) VALUES ('MEIN', 'Mein', 'user')")
    pid = _ids(db)["MEIN"]
    db.reseed_reference_data(force=True)
    assert _ids(db)["MEIN"] == pid
