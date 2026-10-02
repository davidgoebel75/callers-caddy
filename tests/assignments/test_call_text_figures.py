"""Tests fuer Figuren-Mengen je Call-Text (BL-210.2).

Geprueft wird ausschliesslich die oeffentliche ``SongDatabase``-API gegen eine
frische temporaere DB. Beim Oeffnen spielt ``SongDatabase`` die gebuendelte
Referenz ein (reference_calls.json, 775 call_programs) — die Figuren und ihre
Teaching-Orders unten sind also echt.

"Hoechste Figur" = Figur, deren frueheste Teaching-Order am hoechsten ist.
Die erwarteten Reihenfolgen stehen als Literale im Test und kommen aus der
Referenz (Werte in den Kommentaren), nicht aus der Rechnung des Codes.
"""
import pytest


# Figuren der Referenz: (frueheste, weitere Teaching-Orders)
CHASE_RIGHT = "call_chase_right"                  # 39.0029, 40.0045
ANYTHING_AND_ROLL = "concept_anything_and_roll"   # 39.0012, 40.002
CLOVER_AND_ANYTHING = "concept_clover_and_anything"  # 40.0046, 49.0016
PARTNER_TAG = "call_partner_tag"                  # 40.0035, 49.0019


@pytest.fixture
def db(tmp_path):
    from song_db import SongDatabase

    d = SongDatabase(str(tmp_path / "test.db"))
    yield d
    d.close()


def test_menge_setzen_und_lesen_hoechste_zuerst(db):
    db.set_call_text_figures("Chase Right & Roll", [ANYTHING_AND_ROLL, CHASE_RIGHT])

    assert db.get_call_text_figures("Chase Right & Roll") == [
        CHASE_RIGHT, ANYTHING_AND_ROLL]
    assert db.get_call_text_figures("Unbekannter Call-Text") == []


def test_hoechste_figur_nach_fruehester_teaching_order(db):
    # Beide Figuren liegen in Plus (2026) und A1. Nach der SPAETESTEN
    # Teaching-Order waere Partner Tag hoeher (49.0019 > 49.0016), nach der
    # FRUEHESTEN ist es Clover and (Anything) (40.0046 > 40.0035).
    db.set_call_text_figures("Clover and Partner Tag",
                             [PARTNER_TAG, CLOVER_AND_ANYTHING])

    assert db.get_call_text_figures("Clover and Partner Tag") == [
        CLOVER_AND_ANYTHING, PARTNER_TAG]
    # Die hoechste Figur steht als Hauptzuordnung (sehen auch aeltere Versionen)
    assert db.get_entity_for_call_text("Clover and Partner Tag") == CLOVER_AND_ANYTHING


def test_gleichstand_entscheidet_entity_id_aufsteigend(db):
    # Echter Gleichstand in der Referenz: beide fruehestens bei 30.003203.
    db.set_call_text_figures("Right & Left Hand Trade",
                             ["call_right_hand_trade", "call_left_hand_trade"])

    assert db.get_call_text_figures("Right & Left Hand Trade") == [
        "call_left_hand_trade", "call_right_hand_trade"]


def test_figur_ohne_programm_kommt_zuletzt(db):
    # Altbestand: eine Figur, die eine fruehere Referenz noch kannte. Nach dem
    # Referenz-Update steht sie weiter in calls, hat aber keine call_programs-
    # Zeile mehr. Sie kommt zuletzt: Eine aeltere Version sieht nur die
    # Hauptfigur und muss dort eine Figur mit Programm pruefen koennen.
    db.bulk_insert_teaching_order_calls(
        [("call_legacy_figure", "Legacy Figure", 10.5, "")])
    db.reseed_reference_data(force=True)

    db.set_call_text_figures("Legacy & Chase Right",
                             ["call_legacy_figure", CHASE_RIGHT])

    assert db.get_call_text_figures("Legacy & Chase Right") == [
        CHASE_RIGHT, "call_legacy_figure"]
    assert db.get_entity_for_call_text("Legacy & Chase Right") == CHASE_RIGHT


def test_menge_auf_eine_figur_reduzieren(db):
    db.set_call_text_figures("Chase Right & Roll", [CHASE_RIGHT, ANYTHING_AND_ROLL])
    db.set_call_text_figures("Chase Right & Roll", [ANYTHING_AND_ROLL])

    assert db.get_call_text_figures("Chase Right & Roll") == [ANYTHING_AND_ROLL]
    assert db.get_entity_for_call_text("Chase Right & Roll") == ANYTHING_AND_ROLL


def test_leere_menge_entfernt_zuordnung(db):
    db.set_call_text_figures("Chase Right & Roll", [CHASE_RIGHT, ANYTHING_AND_ROLL])
    db.set_call_text_figures("Chase Right & Roll", [])

    assert db.get_call_text_figures("Chase Right & Roll") == []
    assert db.get_entity_for_call_text("Chase Right & Roll") is None


def test_einzelfigur_setzen_raeumt_alte_menge_ab(db):
    db.set_call_text_figures("Chase Right & Roll", [CHASE_RIGHT, ANYTHING_AND_ROLL])
    db.set_call_text_figures("Clover and Partner Tag",
                             [CLOVER_AND_ANYTHING, PARTNER_TAG])

    db.set_call_text_mapping("Chase Right & Roll", "call_swing_thru")
    db.set_call_text_mappings([("Clover and Partner Tag", "call_swing_thru")])

    assert db.get_call_text_figures("Chase Right & Roll") == ["call_swing_thru"]
    assert db.get_call_text_figures("Clover and Partner Tag") == ["call_swing_thru"]


def test_zuordnung_loeschen_raeumt_menge_ab(db):
    db.set_call_text_figures("Chase Right & Roll", [CHASE_RIGHT, ANYTHING_AND_ROLL])

    db.delete_call_text_mapping("Chase Right & Roll")

    assert db.get_call_text_figures("Chase Right & Roll") == []


def test_mappings_leeren_raeumt_mengen_der_quelle_ab(db):
    db.set_call_text_figures("Chase Right & Roll",
                             [CHASE_RIGHT, ANYTHING_AND_ROLL], mapped_by="manual")
    db.set_call_text_figures("Clover and Partner Tag",
                             [CLOVER_AND_ANYTHING, PARTNER_TAG], mapped_by="auto")

    db.clear_call_text_mappings("manual")
    assert db.get_call_text_figures("Chase Right & Roll") == []
    assert db.get_call_text_figures("Clover and Partner Tag") == [
        CLOVER_AND_ANYTHING, PARTNER_TAG]

    db.clear_call_text_mappings()
    assert db.get_call_text_figures("Clover and Partner Tag") == []


def test_fehlgeschlagenes_setzen_laesst_alte_menge_stehen(db):
    import sqlite3

    db.set_call_text_figures("Chase Right & Roll", [CHASE_RIGHT, ANYTHING_AND_ROLL])

    # Ausnahme vom Nur-API-Grundsatz: Schreibfehler mitten in der Menge, per
    # TEMP-Trigger erzwungen (Hauptzeile ist schon ersetzt) -> ganz oder gar nicht
    db._conn.execute(
        "CREATE TEMP TRIGGER test_abbruch BEFORE INSERT ON call_text_figures_extra "
        "BEGIN SELECT RAISE(ABORT, 'Testabbruch'); END")
    with pytest.raises(sqlite3.DatabaseError):
        db.set_call_text_figures("Chase Right & Roll",
                                 [CHASE_RIGHT, CLOVER_AND_ANYTHING])

    assert db.get_call_text_figures("Chase Right & Roll") == [
        CHASE_RIGHT, ANYTHING_AND_ROLL]


def _verwaiste_zuordnung(db, call_text, entity_id):
    """Altbestand wie auf der Prod-DB: auto-Zuordnung auf eine ID ohne
    calls-Zeile, geschrieben ohne Fremdschluessel. Ausnahme vom
    Nur-API-Grundsatz, ueber die API entsteht dieser Zustand nicht mehr."""
    db._conn.execute("PRAGMA foreign_keys=OFF")
    db._conn.execute(
        "INSERT INTO call_text_mappings (call_text, entity_id, mapped_by) "
        "VALUES (?, ?, 'auto')", (call_text, entity_id))
    db._conn.commit()
    db._conn.execute("PRAGMA foreign_keys=ON")


def test_figur_ohne_calls_zeile_faellt_beim_schreiben_weg(db):
    _verwaiste_zuordnung(db, "Girls Face In & Chase Right", "action_face_in")

    assert db.unknown_figures(["action_face_in", CHASE_RIGHT]) == {"action_face_in"}

    # Frueher: IntegrityError "FOREIGN KEY constraint failed"
    db.set_call_text_figures("Girls Face In & Chase Right",
                             ["action_face_in", CHASE_RIGHT])

    assert db.get_call_text_figures("Girls Face In & Chase Right") == [CHASE_RIGHT]


def test_bulk_setzen_und_alle_mengen_lesen(db):
    db.set_call_text_mapping("Swing Thru", "call_swing_thru")

    written = db.set_call_text_figures_bulk([
        ("Chase Right & Roll", [ANYTHING_AND_ROLL, CHASE_RIGHT]),
        ("Clover and Partner Tag", [PARTNER_TAG, CLOVER_AND_ANYTHING]),
    ])

    assert written == 2
    assert db.get_all_call_text_figures() == {
        "Swing Thru": ["call_swing_thru"],
        "Chase Right & Roll": [CHASE_RIGHT, ANYTHING_AND_ROLL],
        "Clover and Partner Tag": [CLOVER_AND_ANYTHING, PARTNER_TAG],
    }


def test_merge_beim_referenz_update_zieht_weitere_figur_mit(db):
    # Echter Merge-Eintrag aus reference_calls.json:
    #   call_walk_around_the_corner -> call_walk_around (fruehestens 10.0028)
    # Altbestand: die fruehere Referenz kannte "Walk Around the Corner" noch.
    db.bulk_insert_teaching_order_calls(
        [("call_walk_around_the_corner", "Walk Around the Corner", 10.0029, "")])
    db.set_call_text_figures("Chase Right & Walk Around the Corner",
                             ["call_walk_around_the_corner", CHASE_RIGHT])

    db.reseed_reference_data(force=True)

    assert db.get_call_text_figures("Chase Right & Walk Around the Corner") == [
        CHASE_RIGHT, "call_walk_around"]


def test_merge_bestimmt_hoechste_figur_neu(db):
    # Altbestand nach einem frueheren Referenz-Update: "Walk Around the Corner"
    # steht noch in calls, hat aber keine call_programs-Zeile mehr und kommt
    # damit hinter Circle Left (10.0001).
    db.bulk_insert_teaching_order_calls(
        [("call_walk_around_the_corner", "Walk Around the Corner", 10.0029, "")])
    db.reseed_reference_data(force=True)
    db.set_call_text_figures("Circle Left & Walk Around the Corner",
                             ["call_walk_around_the_corner", "call_circle_left"])
    assert db.get_entity_for_call_text(
        "Circle Left & Walk Around the Corner") == "call_circle_left"

    # Der echte Merge macht daraus Walk Around (10.0028) — die liegt ueber
    # Circle Left und muss die Hauptzuordnung werden.
    db.reseed_reference_data(force=True)

    assert db.get_entity_for_call_text(
        "Circle Left & Walk Around the Corner") == "call_walk_around"
    assert db.get_call_text_figures("Circle Left & Walk Around the Corner") == [
        "call_walk_around", "call_circle_left"]


def test_export_eine_zeile_je_figur_hoechste_zuerst(db):
    db.set_call_text_figures("Chase Right & Roll",
                             [ANYTHING_AND_ROLL, CHASE_RIGHT], mapped_by="manual")
    db.set_call_text_mapping("Swing Thru", "call_swing_thru", mapped_by="auto")
    # bewusst "keine Figur" (entity_id NULL) bleibt eine Zeile wie bisher
    db.bulk_insert_call_text_mappings([("Bla Bla", None, "manual")])

    assert db.get_all_call_text_mappings() == [
        {"call_text": "Bla Bla", "entity_id": None, "mapped_by": "manual"},
        {"call_text": "Chase Right & Roll", "entity_id": CHASE_RIGHT,
         "mapped_by": "manual"},
        {"call_text": "Chase Right & Roll", "entity_id": ANYTHING_AND_ROLL,
         "mapped_by": "manual"},
        {"call_text": "Swing Thru", "entity_id": "call_swing_thru",
         "mapped_by": "auto"},
    ]


def test_schreiben_weiterer_figuren_erhoeht_cache_zaehler(db):
    # Ausnahme vom Nur-API-Grundsatz: _band_cache_ver ist der Vertrag zwischen
    # Schreibern und Cover-Cache. Der Verhaltens-Test ueber Trefferzahlen folgt
    # mit dem Filter-Umbau (BL-210.3).
    def ver():
        return db._conn.execute("SELECT v FROM _band_cache_ver").fetchone()[0]

    v0 = ver()
    db.set_call_text_figures("Swing Thru", ["call_swing_thru"])
    einzeln = ver() - v0

    v1 = ver()
    db.set_call_text_figures("Chase Right & Roll", [CHASE_RIGHT, ANYTHING_AND_ROLL])
    mit_zusatzfigur = ver() - v1

    # Die Zeile in call_text_figures_extra muss den Zaehler zusaetzlich erhoehen
    assert mit_zusatzfigur > einzeln


def test_reste_einer_aelteren_version_werden_beim_start_aufgeraeumt(tmp_path):
    from song_db import SongDatabase

    path = str(tmp_path / "gemischt.db")
    db = SongDatabase(path)
    db.set_call_text_figures("Chase Right & Roll", [CHASE_RIGHT, ANYTHING_AND_ROLL])
    db.set_call_text_figures("Clover and Partner Tag",
                             [CLOVER_AND_ANYTHING, PARTNER_TAG])
    # Ausnahme vom Nur-API-Grundsatz: So schreibt eine aeltere Version, die die
    # Zusatztabelle nicht kennt. Sie loescht nur die Hauptzeile bzw. ordnet sie
    # auf eine andere Figur um.
    db._conn.execute(
        "DELETE FROM call_text_mappings WHERE call_text = 'Chase Right & Roll'")
    db._conn.execute(
        "UPDATE call_text_mappings SET entity_id = 'call_swing_thru' "
        "WHERE call_text = 'Clover and Partner Tag'")
    db._conn.commit()
    db.close()

    db = SongDatabase(path)   # kein Referenz-Update, nur ein normaler Start
    try:
        # geloescht: die verwaiste weitere Figur ist weg
        assert db.get_call_text_figures("Chase Right & Roll") == []
        # umgeordnet: neue Figur bleibt, die hoechste steht wieder vorn
        assert db.get_entity_for_call_text("Clover and Partner Tag") == PARTNER_TAG
        assert db.get_call_text_figures("Clover and Partner Tag") == [
            PARTNER_TAG, "call_swing_thru"]
    finally:
        db.close()
