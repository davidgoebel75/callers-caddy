"""Knopf "Optimieren" im Call-Mapping-Dialog (intern#97).

Uebernimmt die Mengen-Vorschlaege auf einen Schlag -- genau die Zeilen, die
der Filter "Vorschlag weicht ab" zeigt --, getrennt nach drei Gruppen:
neu zuordnen (bisher ungemappt), ergaenzen (Vorschlag ist echte Obermenge der
Zuordnung) und aendern (Vorschlag weicht anders ab). Geschrieben wird mit
mapped_by='inferred'.

Muster, Fixtures und Helfer aus tests/test_call_mapping_set_suggestions.py
uebernommen und hier dupliziert (bewusst keine gemeinsame Hilfsdatei). Keine
privaten Attribute des Dialogs: nur sichtbare Qt-Bausteine, das ersetzbare
Bestaetigungsfenster und oeffentliche DB-Methoden.

Entity-IDs aus src/reference_calls.json; die Vorschlaege je Text vor der
Testerstellung mit suggest_figure_set() gegen diese Fixture verifiziert:
    SPLIT_TEXT         (ungemappt)              -> {pass_the_ocean, swing_thru}
    MISMATCH_TEXT      [anything_and_spread]    -> {touch_a_quarter, anything_and_spread}
    ALL8_TEXT          [swing_thru]             -> {all_8, swing_thru}
    CHANGE_TEXT        [pass_the_ocean]         -> {swing_thru, anything_and_spread}
    TOUCH_SPREAD_TEXT  gleiche Menge            -> keine Abweichung
    TOUCH_QUARTER_TEXT                          -> kein Mengen-Vorschlag
"""
import time

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import (
    QApplication, QComboBox, QDialog, QMessageBox, QPushButton, QTableWidget,
)

from i18n import _t


PASS_THE_OCEAN = "call_pass_the_ocean"
SWING_THRU = "call_swing_thru"                          # Mainstream, 20.0038
TOUCH_A_QUARTER = "call_touch_a_quarter"
ANYTHING_AND_SPREAD = "concept_anything_and_spread"
ALL_8 = "concept_all_8"                                  # 60.003502

SPLIT_TEXT = "Heads Pass The Ocean & Swing Thru"        # neu zuordnen
MISMATCH_TEXT = "Heads Touch 1/4 & Spread"              # ergaenzen
ALL8_TEXT = "All 8 Swing Thru"                          # ergaenzen
CHANGE_TEXT = "Swing Thru & Spread"                     # aendern
TOUCH_QUARTER_TEXT = "Touch 1/4"
TOUCH_SPREAD_TEXT = "Touch 1/4 & Spread"


@pytest.fixture
def db(tmp_path):
    from song_db import SongDatabase

    d = SongDatabase(str(tmp_path / "t.db"))
    d.insert_sequence([SPLIT_TEXT, MISMATCH_TEXT, TOUCH_QUARTER_TEXT,
                       TOUCH_SPREAD_TEXT, ALL8_TEXT, CHANGE_TEXT])
    # Eigene Sequenz nur aus ALL8_TEXT: voll gemappt, hat also ein Band.
    d.insert_sequence([ALL8_TEXT])
    d.set_call_text_figures(MISMATCH_TEXT, [ANYTHING_AND_SPREAD], mapped_by="manual")
    d.set_call_text_figures(TOUCH_QUARTER_TEXT, [TOUCH_A_QUARTER], mapped_by="manual")
    d.set_call_text_figures(TOUCH_SPREAD_TEXT, [TOUCH_A_QUARTER, ANYTHING_AND_SPREAD],
                            mapped_by="manual")
    d.set_call_text_figures(ALL8_TEXT, [SWING_THRU], mapped_by="manual")
    d.set_call_text_figures(CHANGE_TEXT, [PASS_THE_OCEAN], mapped_by="manual")
    d.recompute_sequence_max_to()
    yield d
    d.close()


def _warte_bis(bedingung, timeout_s=15.0):
    ende = time.monotonic() + timeout_s
    while not bedingung():
        assert time.monotonic() < ende, "Zeitueberschreitung"
        QApplication.processEvents()
        time.sleep(0.01)


def _zelle(table, call_text):
    treffer = [it for it in table.findItems(call_text, Qt.MatchExactly)
               if it.column() == 0]
    return table.item(treffer[0].row(), 2) if treffer else None


def _klick(dlg, key):
    (knopf,) = [b for b in dlg.findChildren(QPushButton) if b.text() == _t(key)]
    knopf.click()


def _doppelklick(table, item):
    # Wie beim Nutzer: erst Klick, dann Doppelklick (sonst verwirft
    # QAbstractItemView den Doppelklick ohne pressedIndex).
    table.scrollToItem(item)
    pos = table.visualItemRect(item).center()
    QTest.mouseClick(table.viewport(), Qt.LeftButton, Qt.NoModifier, pos)
    QTest.mouseDClick(table.viewport(), Qt.LeftButton, Qt.NoModifier, pos)


def _filter(dlg, wert):
    combo = dlg.findChild(QComboBox)
    combo.setCurrentIndex(combo.findData(wert))


def _zuordnungen(db):
    """{call_text: (mapped_by, {figuren})} ueber die oeffentliche Export-Sicht."""
    out = {}
    for row in db.get_all_call_text_mappings():
        mb, figs = out.setdefault(row["call_text"], (row["mapped_by"], set()))
        figs.add(row["entity_id"])
    return out


def _max_to(db, erster_call):
    """max_teaching_order der Sequenz mit diesem ersten Call (field_1) --
    ueber die oeffentliche Listen-Abfrage (Index 1 = field_1, 17 = max_to)."""
    (wert,) = [r[17] for r in db.get_filtered_sequences(limit=100)
               if r[1] == erster_call]
    return wert


@pytest.fixture
def infos(monkeypatch):
    import sequences_widget

    meldungen = []
    monkeypatch.setattr(sequences_widget.QMessageBox, "information",
                        lambda *a, **k: meldungen.append(a))
    return meldungen


@pytest.fixture
def mapping(qapp, db, infos):
    import sequences_widget

    dlg = sequences_widget.CallMappingDialog(db)
    dlg.show()
    table = dlg.findChild(QTableWidget)
    _warte_bis(lambda: _zelle(table, SPLIT_TEXT) is not None)
    yield dlg
    dlg.close()
    dlg.deleteLater()


@pytest.fixture
def bestaetigung(monkeypatch):
    """Ersetzt das Bestaetigungsfenster; ``antwort`` legt die Wahl fest."""
    import sequences_widget

    aufrufe = []
    antwort = {"ok": True, "gruppen": {"new", "extend", "change"}}

    class _Bestaetigung:
        def __init__(self, counts, parent=None):
            aufrufe.append(dict(counts))

        def exec(self):
            return QDialog.Accepted if antwort["ok"] else QDialog.Rejected

        def chosen_groups(self):
            return set(antwort["gruppen"])

    monkeypatch.setattr(sequences_widget, "CallMappingOptimizeDialog",
                        _Bestaetigung)
    return aufrufe, antwort


@pytest.fixture
def picker_double(monkeypatch):
    """Ersetzt den Figuren-Picker; ``antwort`` legt die Wahl des Nutzers fest."""
    import sequences_widget

    antwort = {"ids": []}

    class _Picker:
        def __init__(self, entities, selected=(), parent=None, allow_split=False,
                     unknown_ids=()):
            pass

        def setWindowTitle(self, title):
            pass

        def exec(self):
            return QDialog.Accepted

        def selected_entity_ids(self):
            return list(antwort["ids"])

        def split_requested(self):
            return False

    monkeypatch.setattr(sequences_widget, "CallFiguresPickerDialog", _Picker)
    return antwort


@pytest.fixture
def rueckfrage(monkeypatch):
    """Ersetzt QMessageBox.question; ``antwort["knopf"]`` ist die Antwort."""
    import sequences_widget

    fragen = []
    antwort = {"knopf": QMessageBox.No}

    def _frage(*a, **k):
        fragen.append(a)
        return antwort["knopf"]

    monkeypatch.setattr(sequences_widget.QMessageBox, "question", _frage)
    return fragen, antwort


# ------------------------------------------------------------------ Tests --

def test_optimieren_zeigt_die_drei_gruppen_getrennt(mapping, bestaetigung):
    aufrufe, _antwort = bestaetigung

    _klick(mapping, "call_mapping_optimize")

    assert aufrufe == [{"new": 1, "extend": 2, "change": 1}]


def test_optimieren_schreibt_vorschlaege_als_inferred(mapping, bestaetigung, db):
    _klick(mapping, "call_mapping_optimize")

    z = _zuordnungen(db)
    # Abnahmefall aus dem Issue
    assert z[MISMATCH_TEXT] == ("inferred", {TOUCH_A_QUARTER, ANYTHING_AND_SPREAD})
    assert z[SPLIT_TEXT] == ("inferred", {PASS_THE_OCEAN, SWING_THRU})
    assert z[ALL8_TEXT] == ("inferred", {ALL_8, SWING_THRU})
    assert z[CHANGE_TEXT] == ("inferred", {SWING_THRU, ANYTHING_AND_SPREAD})
    # Nicht abweichende Zeilen bleiben unberuehrt
    assert z[TOUCH_SPREAD_TEXT] == ("manual", {TOUCH_A_QUARTER, ANYTHING_AND_SPREAD})
    assert z[TOUCH_QUARTER_TEXT] == ("manual", {TOUCH_A_QUARTER})


def test_abgewaehlte_gruppe_bleibt_unberuehrt(mapping, bestaetigung, db):
    _aufrufe, antwort = bestaetigung
    antwort["gruppen"] = {"new", "extend"}   # "aendern" abgehakt

    _klick(mapping, "call_mapping_optimize")

    z = _zuordnungen(db)
    assert z[CHANGE_TEXT] == ("manual", {PASS_THE_OCEAN})
    assert z[MISMATCH_TEXT] == ("inferred", {TOUCH_A_QUARTER, ANYTHING_AND_SPREAD})
    assert z[SPLIT_TEXT] == ("inferred", {PASS_THE_OCEAN, SWING_THRU})


def test_abbrechen_schreibt_nichts(mapping, bestaetigung, db):
    _aufrufe, antwort = bestaetigung
    antwort["ok"] = False
    vor = _zuordnungen(db)

    _klick(mapping, "call_mapping_optimize")

    assert _zuordnungen(db) == vor
    assert SPLIT_TEXT not in vor


def test_nichts_angehakt_schreibt_nichts(mapping, bestaetigung, db):
    _aufrufe, antwort = bestaetigung
    antwort["gruppen"] = set()
    vor = _zuordnungen(db)

    _klick(mapping, "call_mapping_optimize")

    assert _zuordnungen(db) == vor


def test_optimieren_rechnet_die_baender_nach(mapping, bestaetigung, db):
    # Vorher: nur Swing Thru (Mainstream) -> fruehestes Band 20.0038
    assert _max_to(db, ALL8_TEXT) == pytest.approx(20.0038)
    # Sequenz mit ungemapptem SPLIT_TEXT hat noch kein Band
    assert _max_to(db, SPLIT_TEXT) is None

    _klick(mapping, "call_mapping_optimize")

    # Das ergaenzte All-8-Konzept hebt die Sequenz auf 60.003502
    assert _max_to(db, ALL8_TEXT) == pytest.approx(60.003502)
    assert _max_to(db, SPLIT_TEXT) == pytest.approx(60.003502)


def test_nach_optimieren_ist_der_abweichungsfilter_leer_und_meldet_anzahl(
        mapping, bestaetigung, infos):
    _filter(mapping, "mismatch")
    table = mapping.findChild(QTableWidget)
    assert table.rowCount() == 4

    _klick(mapping, "call_mapping_optimize")

    assert table.rowCount() == 0
    assert any(_t("call_mapping_optimize_done", count=4) in a for a in infos)
    assert mapping.wrote_assignments is True


def test_ohne_abweichung_nur_hinweis_keine_rueckfrage(mapping, bestaetigung, infos):
    aufrufe, _antwort = bestaetigung
    _klick(mapping, "call_mapping_optimize")
    del infos[:]

    _klick(mapping, "call_mapping_optimize")

    assert len(aufrufe) == 1   # nur der erste Klick fragte nach
    assert any(_t("call_mapping_optimize_nothing") in a for a in infos)


def test_abbrechen_setzt_kein_optimiert_kennzeichen(mapping, bestaetigung):
    _aufrufe, antwort = bestaetigung
    antwort["ok"] = False

    _klick(mapping, "call_mapping_optimize")

    assert mapping.wrote_assignments is False


# ---------------------------------------------------------- SongDatabase --

def test_mapping_stats_zaehlt_inferred(db):
    db.set_call_text_figures_bulk(
        [(SPLIT_TEXT, [PASS_THE_OCEAN, SWING_THRU]),
         (ALL8_TEXT, [ALL_8, SWING_THRU])], mapped_by="inferred")

    stats = db.get_mapping_stats()

    assert stats["inferred"] == 2
    assert stats["manual"] == 4
    assert stats["auto"] == 0


def test_clear_inferred_entfernt_nur_inferred_samt_zusatzfiguren(db):
    db.set_call_text_figures_bulk(
        [(SPLIT_TEXT, [PASS_THE_OCEAN, SWING_THRU]),
         (ALL8_TEXT, [ALL_8, SWING_THRU])], mapped_by="inferred")

    db.clear_call_text_mappings("inferred")

    z = _zuordnungen(db)
    assert SPLIT_TEXT not in z
    assert ALL8_TEXT not in z
    assert db.get_call_text_figures(ALL8_TEXT) == []
    assert z == {
        MISMATCH_TEXT: ("manual", {ANYTHING_AND_SPREAD}),
        TOUCH_QUARTER_TEXT: ("manual", {TOUCH_A_QUARTER}),
        TOUCH_SPREAD_TEXT: ("manual", {TOUCH_A_QUARTER, ANYTHING_AND_SPREAD}),
        CHANGE_TEXT: ("manual", {PASS_THE_OCEAN}),
    }


# ------------------------------------------- ungespeicherte Picker-Aenderung --

def test_ungespeicherte_aenderung_nein_verwirft_nichts_und_schreibt_nichts(
        mapping, bestaetigung, picker_double, rueckfrage, db):
    aufrufe, _antwort = bestaetigung
    fragen, _ = rueckfrage
    _filter(mapping, "all")
    table = mapping.findChild(QTableWidget)
    picker_double["ids"] = [TOUCH_A_QUARTER]
    _doppelklick(table, _zelle(table, CHANGE_TEXT))   # ungespeichert
    vor = _zuordnungen(db)

    _klick(mapping, "call_mapping_optimize")

    assert len(fragen) == 1
    assert aufrufe == []            # abgebrochen vor der Gruppen-Rueckfrage
    assert _zuordnungen(db) == vor
    # Die ungespeicherte Wahl steht noch in der Zelle
    assert _zelle(table, CHANGE_TEXT).text() == "Touch a Quarter"


def test_ungespeicherte_aenderung_ja_optimiert(
        mapping, bestaetigung, picker_double, rueckfrage, db):
    fragen, antwort = rueckfrage
    antwort["knopf"] = QMessageBox.Yes
    _filter(mapping, "all")
    table = mapping.findChild(QTableWidget)
    picker_double["ids"] = [TOUCH_A_QUARTER]
    _doppelklick(table, _zelle(table, CHANGE_TEXT))

    _klick(mapping, "call_mapping_optimize")

    assert len(fragen) == 1
    assert _zuordnungen(db)[CHANGE_TEXT] == (
        "inferred", {SWING_THRU, ANYTHING_AND_SPREAD})


def test_ohne_ungespeicherte_aenderung_keine_rueckfrage(
        mapping, bestaetigung, rueckfrage):
    fragen, _ = rueckfrage

    _klick(mapping, "call_mapping_optimize")

    assert fragen == []


def test_nach_optimieren_zeigt_die_tabelle_den_neuen_stand(mapping, bestaetigung):
    table = mapping.findChild(QTableWidget)

    _klick(mapping, "call_mapping_optimize")

    _filter(mapping, "unmapped")
    assert _zelle(table, SPLIT_TEXT) is None
    _filter(mapping, "mapped")
    zeile = _zelle(table, SPLIT_TEXT).row()
    assert table.item(zeile, 3).text() == "inferred"
    assert set(table.item(zeile, 2).data(Qt.UserRole)) == {PASS_THE_OCEAN, SWING_THRU}


# ------------------------------------------------ echtes Bestaetigungsfenster --

def test_bestaetigungsfenster_zeigt_anzahlen_und_hakt_alle_gruppen_an(qapp):
    from PySide6.QtWidgets import QCheckBox
    import sequences_widget

    dlg = sequences_widget.CallMappingOptimizeDialog(
        {"new": 1, "extend": 2, "change": 3})
    try:
        texte = [cb.text() for cb in dlg.findChildren(QCheckBox)]
        assert texte == [_t("call_mapping_optimize_new", count=1),
                         _t("call_mapping_optimize_extend", count=2),
                         _t("call_mapping_optimize_change", count=3)]
        assert dlg.chosen_groups() == {"new", "extend", "change"}
    finally:
        dlg.deleteLater()
