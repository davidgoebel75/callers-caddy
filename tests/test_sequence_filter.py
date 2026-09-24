"""Tests fuer die Sequenz-Filter-Regel (sequence_filter.py, intern#113).

Qt-frei: Filter-Werte rein, Abfrage-Parameter fuer SongDatabase raus.
"""
from sequence_filter import filter_query_args as fqa


def test_ohne_filter_alles_none():
    assert fqa() == dict(
        entity_id_filter=None, type_filter=None, difficulty_filter=None,
        tags_filter=None, max_to_filter=None, min_to_filter=None,
        bands_filter=None, bands_below_filter=None, cover_max_to=None)


def test_einfache_filter_werden_durchgereicht():
    args = fqa(contains="swing_thru", seq_type="Singing break",
               difficulty="Easy", tags="Party", bands={10, 20})
    assert args["entity_id_filter"] == "swing_thru"
    assert args["type_filter"] == "Singing break"
    assert args["difficulty_filter"] == "Easy"
    assert args["tags_filter"] == "Party"


# ---- Alt-Pfad (ohne Tanzprogramm-Wahl) ----

def test_alt_limit_wird_max_to():
    args = fqa(limit=52.3)
    assert args["max_to_filter"] == 52.3
    assert args["min_to_filter"] is None
    assert args["cover_max_to"] is None


def test_alt_nur_filter_ist_programm_start_des_limits():
    # A1-Limit 50.7 -> Untergrenze 50.0 (Ganzzahlteil)
    assert fqa(limit=50.7, only=True)["min_to_filter"] == 50.0


def test_alt_nur_filter_ohne_limit_wirkungslos():
    assert fqa(only=True)["min_to_filter"] is None


# ---- Baender-Pfad (mit Tanzprogramm-Wahl) ----

def test_baender_limit_wird_cover_max_to():
    args = fqa(limit=42.5, bands={10, 20, 30, 40})
    assert args["bands_filter"] == {10, 20, 30, 40}
    assert args["cover_max_to"] == 42.5
    assert args["max_to_filter"] is None
    assert args["min_to_filter"] is None
    assert args["bands_below_filter"] is None


def test_baender_nur_filter_setzt_baender_unter_dem_obersten():
    args = fqa(only=True, limit=42.5, bands={10, 20, 30, 40})
    assert args["bands_below_filter"] == {10, 20, 30}
    assert args["min_to_filter"] is None


def test_baender_nur_filter_mit_einem_band_wirkungslos():
    assert fqa(only=True, bands={40})["bands_below_filter"] is None


def test_leere_band_menge_ist_alt_pfad():
    args = fqa(limit=52.3, bands=set())
    assert args["bands_filter"] is None
    assert args["max_to_filter"] == 52.3
