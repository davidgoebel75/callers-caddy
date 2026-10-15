"""Heilung beim Start: Zuordnungen aus dem alten Volltreffer (intern#89).

Bis intern#89 belegte "All Eight Circulate" den Schluessel des blanken
"Circulate", und "All 8 Spin The Top" landete auf "Spin the Top". Solche
Zuordnungen stehen in Bestands-DBs fest. Beim ersten Start mit dem neuen
Volltreffer werden sie einmal umgehaengt, wenn sie genau auf den alten
Volltreffer zeigen -- auch bestaetigte ('manual'), denn der Caller hat dann
nur den falschen gruenen Vorschlag uebernommen. Eine eigene Wahl des Callers
und Zuordnungen mit mehreren Figuren bleiben.

Entity-IDs aus src/reference_calls.json.
"""
from types import SimpleNamespace

import pytest

ALL_EIGHT = "call_all_eight_circulate"
NAMED = "call_named_dancers_circulate"
COUPLES = "call_couples_circulate"
SPIN = "call_spin_the_top"
ALL8_SPIN = "call_all_8_spin_the_top"
CENTERS_IN = "call_centers_in"
STEP_FLIP = "call_step_and_flip"

FLAG = "role_prefix_remapped"


def _zuordnung(db, text):
    return db.get_call_text_figures(text), db._conn.execute(
        "SELECT mapped_by FROM call_text_mappings WHERE call_text = ?",
        (text,)).fetchone()[0]


@pytest.fixture
def bestand(tmp_path, keep):
    """DB im Stand vor intern#89: falsche Zuordnungen, Heilung noch nicht gelaufen."""
    from song_db import SongDatabase

    path = str(tmp_path / "t.db")
    d = SongDatabase(path)
    for text, figs, by in [
        ("Circulate", [ALL_EIGHT], "auto"),
        ("Ends Circulate", [ALL_EIGHT], "manual"),
        ("Ladies Circulate", [COUPLES], "manual"),
        ("Centers Circulate", [ALL_EIGHT, SPIN], "auto"),
        ("All 8 Spin The Top", [SPIN], "auto"),
        ("In", [CENTERS_IN], "manual"),
    ]:
        d.set_call_text_figures(text, figs, mapped_by=by)
    seq = d.insert_sequence(["All 8 Spin The Top", "Circulate"])
    d.insert_sequence(["Step & Flip"])
    d.recompute_sequence_max_to()
    d._conn.execute("DELETE FROM app_meta WHERE key = ?", (FLAG,))
    d._conn.commit()
    max_to = d._conn.execute(
        "SELECT max_teaching_order FROM sequences WHERE id = ?", (seq,)).fetchone()[0]
    d.close()
    return SimpleNamespace(path=path, seq=seq, max_to=max_to,
                           open=lambda: keep(SongDatabase(path)))


def test_alte_volltreffer_werden_umgehaengt(bestand):
    db = bestand.open()
    assert _zuordnung(db, "Circulate") == ([NAMED], "auto")
    assert _zuordnung(db, "Ends Circulate") == ([NAMED], "auto")
    assert _zuordnung(db, "All 8 Spin The Top") == ([ALL8_SPIN], "auto")


def test_eigene_wahl_und_mengen_bleiben(bestand):
    db = bestand.open()
    assert _zuordnung(db, "Ladies Circulate") == ([COUPLES], "manual")
    assert sorted(_zuordnung(db, "Centers Circulate")[0]) == sorted([ALL_EIGHT, SPIN])
    assert _zuordnung(db, "In") == ([CENTERS_IN], "manual")   # kein neuer Volltreffer


def test_neue_volltreffer_werden_ergaenzt_und_eingestuft(bestand):
    db = bestand.open()
    assert _zuordnung(db, "Step & Flip") == ([STEP_FLIP], "auto")
    max_to = db._conn.execute(
        "SELECT max_teaching_order FROM sequences WHERE id = ?",
        (bestand.seq,)).fetchone()[0]
    assert bestand.max_to < 30 <= max_to   # Spin the Top: Mainstream, All 8 ...: Plus


def test_heilung_laeuft_nur_einmal(bestand):
    db = bestand.open()
    db.set_call_text_figures("Circulate", [ALL_EIGHT], mapped_by="auto")
    db.close()
    db = bestand.open()
    assert _zuordnung(db, "Circulate") == ([ALL_EIGHT], "auto")
