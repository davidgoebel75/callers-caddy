"""Tests fuer die Filter auf Figuren-Mengen (BL-210.3).

Geprueft wird ausschliesslich die oeffentliche ``SongDatabase``-API gegen eine
frische temporaere DB mit der gebuendelten Referenz. Figuren bewusst gewaehlt
(Teaching-Orders aus der Referenz):

  Allemande Right  call_allemande_right  30.000402              (nur MS 2026)
  Allemande Thar   call_allemande_thar   29.005301, 40.002601   (MS alt, Plus 2026)

Hoechste Figur der Menge ist Allemande Right (frueheste 30.0004 > 29.0053),
Allemande Thar steht in der Zusatztabelle. In der 2026er-Linie braucht eine
Sequenz mit beiden damit Plus (2026): bei Mainstream 2026 faellt sie heraus.
Jeder Test prueft zuerst den Stand mit nur einer Figur (wie vor den Mengen).
"""
import pytest


TEXT = "Allemande Right & Allemande Thar"
RIGHT = "call_allemande_right"
THAR = "call_allemande_thar"
MS2026 = {10, 20, 30}
PL2026 = {10, 20, 30, 40}


@pytest.fixture
def db(tmp_path):
    from song_db import SongDatabase

    d = SongDatabase(str(tmp_path / "test.db"))
    d.insert_sequence([TEXT])
    yield d
    d.close()


def test_band_filter_prueft_jede_figur_der_menge(db):
    db.set_call_text_mappings([(TEXT, RIGHT)])
    assert db.get_filtered_count(bands_filter=MS2026) == 1

    db.set_call_text_figures(TEXT, [RIGHT, THAR])

    # Allemande Thar liegt nicht in Band 30 -> raus; Plus 2026 deckt beide
    assert db.get_filtered_count(bands_filter=MS2026) == 0
    assert db.get_filtered_count(bands_filter=PL2026) == 1
    assert db.get_sequence_ids_for_bands(MS2026) == []
    assert len(db.get_sequence_ids_for_bands(PL2026)) == 1


def test_nur_filter_richtet_sich_nach_der_menge(db):
    db.set_call_text_mappings([(TEXT, RIGHT)])
    # "Nur Plus 2026": mit einer Figur schon bei MS 2026 tanzbar -> kein Treffer
    assert db.get_filtered_count(bands_filter=PL2026,
                                 bands_below_filter=MS2026) == 0

    db.set_call_text_figures(TEXT, [RIGHT, THAR])

    assert db.get_filtered_count(bands_filter=PL2026,
                                 bands_below_filter=MS2026) == 1


def test_enthaelt_filter_findet_sequenz_ueber_jede_figur(db):
    db.set_call_text_mappings([(TEXT, RIGHT)])
    assert db.get_filtered_count(entity_id_filter=THAR) == 0

    db.set_call_text_figures(TEXT, [RIGHT, THAR])

    assert db.get_filtered_count(entity_id_filter=RIGHT) == 1
    assert db.get_filtered_count(entity_id_filter=THAR) == 1


def test_max_teaching_order_nimmt_hoechste_figur_der_menge(db):
    db.set_call_text_mappings([(TEXT, RIGHT)])
    db.recompute_sequence_max_to()
    assert db.get_filtered_count(max_to_filter=31.0) == 1   # 30.000402

    db.set_call_text_figures(TEXT, [RIGHT, THAR])
    db.recompute_sequence_max_to()

    # Allemande Thar hebt die Sequenz auf 40.002601 (Plus 2026)
    assert db.get_filtered_count(max_to_filter=31.0) == 0
    assert db.get_filtered_count(max_to_filter=41.0) == 1
    assert db.get_filtered_count(min_to_filter=40.0) == 1


def test_detailansicht_bleibt_eine_zeile_je_call_text(db):
    db.set_call_text_figures(TEXT, [RIGHT, THAR])

    [sid] = db.get_filtered_sequence_ids()
    assert [(c[1], c[2]) for c in db.get_sequence_calls(sid)] == [(TEXT, RIGHT)]
    rows = [r for r in db.get_all_call_texts_with_mapping() if r[0] == TEXT]
    assert [(r[1], r[2]) for r in rows] == [(1, RIGHT)]
