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


def test_aus_der_referenz_gefallenes_programm_bleibt_als_eigenes(db, monkeypatch):
    """Ein mitgeliefertes Programm, das die Referenz nicht mehr fuehrt (hier:
    C3B aus der Referenz genommen), bleibt als eigenes stehen, samt Zuordnung -
    geloescht wird beim Reseed nichts."""
    import json

    import song_db

    gone = _ids(db)["C3B"]
    loc = db.insert_location("Club")
    db.set_location_program_ids(loc.id, [gone, _ids(db)["MS2026"]])
    real_load = json.load

    def without_c3b(fh, *a, **k):
        data = real_load(fh, *a, **k)
        if isinstance(data, dict) and "dance_programs" in data:
            data["dance_programs"] = [p for p in data["dance_programs"]
                                      if p["code"] != "C3B"]
        return data
    monkeypatch.setattr(json, "load", without_c3b)
    assert "C3B" not in [c for c, *_ in song_db._DEFAULT_DANCE_PROGRAMS]

    db.reseed_reference_data(force=True)

    assert _ids(db)["C3B"] == gone
    assert db._conn.execute(
        "SELECT origin FROM dance_programs WHERE id=?", (gone,)).fetchone()[0] == "user"
    assert sorted(db.get_location_program_ids(loc.id)) == sorted([gone, _ids(db)["MS2026"]])


def test_reseed_laesst_eigenes_programm_stehen(db):
    db._conn.execute(
        "INSERT INTO dance_programs (code, label, origin) VALUES ('MEIN', 'Mein', 'user')")
    pid = _ids(db)["MEIN"]
    db.reseed_reference_data(force=True)
    assert _ids(db)["MEIN"] == pid


def test_im_manager_angelegtes_programm_ueberlebt_den_reseed(db):
    """Review Thomas zu #128: insert_dance_program() schrieb kein origin, der
    DEFAULT 'builtin' liess den Reseed das Programm samt Zuordnung loeschen."""
    pid = db.insert_dance_program("MEIN", "Mein Programm", 99, 8.0, 30.999999)
    loc = db.insert_location("Club")
    db.set_location_program_ids(loc.id, [pid])

    db.reseed_reference_data(force=True)

    assert _ids(db)["MEIN"] == pid
    assert db.get_location_program_ids(loc.id) == [pid]


def test_bestandsprogramm_mit_builtin_wird_geheilt_statt_geloescht(db):
    """Altbestand: vor dem Fix angelegt, steht als 'builtin' in der DB."""
    pid = db._conn.execute(
        "INSERT INTO dance_programs (code, label) VALUES ('ALTEIGEN', 'Alt eigen')"
    ).lastrowid
    loc = db.insert_location("Club")
    db.set_location_program_ids(loc.id, [pid])

    db.reseed_reference_data(force=True)

    assert _ids(db)["ALTEIGEN"] == pid
    assert db._conn.execute(
        "SELECT origin FROM dance_programs WHERE id=?", (pid,)).fetchone()[0] == "user"
    assert db.get_location_program_ids(loc.id) == [pid]


def test_im_manager_umbenanntes_mitgeliefertes_programm_bleibt(db):
    pid = _ids(db)["MS2026"]
    db.update_dance_program(pid, "MS2026-Club", "Mein MS", 40, 7.0, 30.999999)

    db.reseed_reference_data(force=True)

    assert _ids(db)["MS2026-Club"] == pid
    assert "MS2026" in _ids(db)     # das mitgelieferte kommt neu dazu
