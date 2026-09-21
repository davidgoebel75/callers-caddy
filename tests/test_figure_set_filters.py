"""Tests fuer die Filter auf Figuren-Mengen (BL-210.3).

Geprueft wird im Kern die oeffentliche ``SongDatabase``-API gegen eine frische
temporaere DB mit der gebuendelten Referenz. Ausnahme: der Determinismus-Test
zum Programm-Badge greift bewusst per ``_conn`` in ``call_programs`` ein, um die
Band-Reihenfolge zu kontrollieren (dort begruendet). Figuren bewusst gewaehlt
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


def test_sequenz_anzeige_zeigt_deterministisch_das_niedrigste_band(db):
    # intern#87: Allemande Thar steht in zwei Baendern (Mainstream 29.005301 und
    # Plus 2026 40.002601). get_sequence_calls joint auf die Mehrfach-View; ohne
    # ORDER BY waere das Programm-Badge willkuerlich. Erwartet: immer das
    # niedrigste Band -> teaching_order 29.005301, Programm "Mainstream".
    #
    # Ohne Vorkehrung liefert schon der ALTE Code (fetchone ohne ORDER BY)
    # "Mainstream", weil die View die Baender in Einfuege-Reihenfolge (call_programs.id
    # aufsteigend) ausgibt und Mainstream zuerst eingefuegt wurde. Damit der Test
    # den Fix wirklich absichert, wird die Mainstream-Zeile ans Ende geschoben
    # (neue, hoehere id) -> alter Code liefert dann Plus (2026), neuer weiter Mainstream.
    # Bewusst ueber _conn (privat), wie in anderen Tests; die reine-API-Zusage im
    # Modul-Docstring gilt fuer die uebrigen Tests.
    db._conn.execute(
        "DELETE FROM call_programs WHERE entity_id = ? AND teaching_order = ?",
        (THAR, 29.005301))
    db._conn.execute(
        "INSERT INTO call_programs (entity_id, teaching_order, program) "
        "VALUES (?, ?, ?)", (THAR, 29.005301, "Mainstream"))

    db.set_call_text_mappings([(TEXT, THAR)])
    [sid] = db.get_filtered_sequence_ids()

    (row,) = db.get_sequence_calls(sid)
    # (position, call_text, entity_id, teaching_order, canonical_name, program)
    assert row[2] == THAR
    assert row[3] == 29.005301
    assert row[5] == "Mainstream"
