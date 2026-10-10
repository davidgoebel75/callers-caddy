"""Tests fuer den Band-Filter (Programmwahl) ueber die oeffentliche
``SongDatabase``-API, als Absicherung fuer intern#111 (Cover-Berechnung).

Frische temporaere DB mit der gebuendelten Referenz. Figuren bewusst gewaehlt
(Teaching-Orders aus der Referenz):

  Circle Left      call_circle_left      30.000101
  Allemande Right  call_allemande_right  30.000402
  Recycle          call_recycle          29.0067, 30.005

Erwartete Trefferzahlen sind aus diesen Werten von Hand abgeleitet.
"""
import pytest


EASY = ["Circle Left", "Allemande Right"]
LATE = ["Circle Left", "Recycle"]
MAPPINGS = [
    ("Circle Left", "call_circle_left"),
    ("Allemande Right", "call_allemande_right"),
    ("Recycle", "call_recycle"),
]
MS2026 = {10, 20, 30}


@pytest.fixture
def db(tmp_path):
    from song_db import SongDatabase

    d = SongDatabase(str(tmp_path / "test.db"))
    d.insert_sequence(EASY)
    d.insert_sequence(LATE)
    d.set_call_text_mappings(MAPPINGS)
    yield d
    d.close()


def test_limit_schneidet_innerhalb_eines_bandes(db):
    assert db.get_filtered_count(bands_filter=MS2026) == 2
    # Limit hinter Allemande Right, vor Recycle (beide Band 30)
    assert db.get_filtered_count(bands_filter=MS2026, cover_max_to=30.001) == 1
    assert db.get_filtered_count(bands_filter=MS2026, cover_max_to=30.0001) == 0


def test_nur_filter_mit_limit(db):
    # Circle Left (10, 30) + Recycle (29, 30) ist schon mit {10, 29} tanzbar
    # -> bei "Nur 30" raus; Allemande Right gibt es nur in 30
    below = {10, 29}
    assert db.get_filtered_count(bands_filter={30},
                                 bands_below_filter=below) == 1
    assert db.get_filtered_count(bands_filter={10, 29, 30},
                                 bands_below_filter=below,
                                 cover_max_to=30.001) == 1
    assert db.get_filtered_count(bands_filter={10, 29, 30},
                                 bands_below_filter=below,
                                 cover_max_to=30.0001) == 0


def test_ungemappte_texte_schliessen_nicht_aus(db):
    db.insert_sequence(["Circle Left", "Voellig Unbekannt"])
    db.insert_sequence(["Voellig Unbekannt"])
    # erste zaehlt (einzige erkannte Figur passt), zweite hat keine Figur
    assert db.get_filtered_count(bands_filter=MS2026) == 3


def test_filter_folgt_mapping_aenderung_nach_vorheriger_abfrage(db):
    assert db.get_filtered_count(bands_filter={30}, cover_max_to=30.001) == 1
    db.set_call_text_mappings([("Allemande Right", "call_recycle")])
    assert db.get_filtered_count(bands_filter={30}, cover_max_to=30.001) == 0
    assert db.get_filtered_count(bands_filter={30}) == 2


def test_filter_folgt_neuer_sequenz(db):
    assert db.get_filtered_count(bands_filter={30}, cover_max_to=30.001) == 1
    db.insert_sequence(["Allemande Right"])
    assert db.get_filtered_count(bands_filter={30}, cover_max_to=30.001) == 2


def test_filter_folgt_bearbeiteter_sequenz(db):
    [_easy_id, late_id] = db.get_filtered_sequence_ids(bands_filter={30})
    assert db.get_filtered_count(bands_filter={30}, cover_max_to=30.001) == 1
    db.update_sequence(late_id, EASY)
    assert db.get_filtered_count(bands_filter={30}, cover_max_to=30.001) == 2


def test_filter_folgt_geloeschter_sequenz(db):
    [easy_id, _late_id] = db.get_filtered_sequence_ids(bands_filter={30})
    assert db.get_filtered_count(bands_filter={30}, cover_max_to=30.001) == 1
    db.delete_sequences([easy_id])
    assert db.get_filtered_count(bands_filter={30}) == 1
    assert db.get_filtered_count(bands_filter={30}, cover_max_to=30.001) == 0
