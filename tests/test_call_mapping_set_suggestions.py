"""Mengen-Vorschlag + Filter "Vorschlag weicht ab" im Call-Mapping-Dialog
(BL-210.8).

Baut auf suggest_figure_set()/canon_key() (BL-210.7, sequence_mapper.py) und
dem bestehenden CallMappingDialog (BL-210.4). Muster, Fixtures und Helfer aus
tests/test_call_figures_picker.py uebernommen und fuer diese eigene DB
dupliziert (bewusst keine gemeinsame Hilfsdatei). Wie dort: keine privaten
Attribute des Dialogs, nur seine sichtbaren Qt-Bausteine und Zellendaten.

Entity-IDs stammen aus src/reference_calls.json (verifiziert vor Testerstellung):
    call_pass_the_ocean          "Pass the Ocean"
    call_swing_thru               "Swing Thru"
    call_touch_a_quarter          "Touch a Quarter"
    concept_anything_and_spread   "(Anything) & Spread"
    concept_all_8                 "All 8 Concept"
"""
import time

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import (
    QApplication, QComboBox, QDialog, QLabel, QPushButton, QTableWidget,
)

from i18n import _t


PASS_THE_OCEAN = "call_pass_the_ocean"                 # Mainstream, 20.004/30.0035
SWING_THRU = "call_swing_thru"                          # Mainstream, 20.0038/30.0033
TOUCH_A_QUARTER = "call_touch_a_quarter"                # Mainstream, 20.0047/30.0042
ANYTHING_AND_SPREAD = "concept_anything_and_spread"     # Plus, 39.001/40.0032
ALL_8 = "concept_all_8"                                  # 60.003502

# Sequenz mit unmapptem Split-Fall: "Pass The Ocean" & "Swing Thru" loesen
# beide einzeln exakt auf -> suggest_split_figures().
SPLIT_TEXT = "Heads Pass The Ocean & Swing Thru"
# Bereits (falsch/veraltet) auf eine einzelne Figur gemappt -- der
# (Anything)-Vorlagen-Vorschlag weicht davon ab (Abnahmefall aus dem Issue).
MISMATCH_TEXT = "Heads Touch 1/4 & Spread"
# Fuellt NUR rest_lookup (eindeutige Zuordnung, len(figures) == 1); loest
# selbst keinen Mengen-Vorschlag aus (kein Trennzeichen, keine Vorlage).
TOUCH_QUARTER_TEXT = "Touch 1/4"
# Kontrolle fuer den Mengen- statt Listenvergleich im Mismatch-Filter: die
# (Anything)-Vorlage liefert [Zielfigur, Vorlagen-Konzept]
# (suggest_anything_figures), _figure_sets speichert dagegen rang-sortiert
# (hoechste teaching_order zuerst) -- concept_anything_and_spread (39.001)
# liegt hoeher als call_touch_a_quarter (20.0047), die gespeicherte
# Reihenfolge ist also GENAU umgekehrt zur Vorschlagsreihenfolge. Als MENGE
# gleich -> darf NICHT im Mismatch-Filter stehen; ein reiner Listenvergleich
# wuerde ihn faelschlich zeigen.
TOUCH_SPREAD_TEXT = "Touch 1/4 & Spread"
# Unvollstaendige Alt-Zuordnung OHNE Rollen-Praefix: suggest_figure_set()/
# _raw_exact_match() ueberspringt die Rollen-Praefix-Bereinigung fuer
# All-8/All-4-Couples-Texte bewusst (sonst waere "All Eight Circulate" vom
# blossen "Circulate" nicht unterscheidbar). Der volle Text
# "all 8 swing thru" bleibt darum als canon_key stehen -- GENAU derselbe
# Schluessel, den rest_lookup fuer diesen (einfigurig gemappten) Text auch
# benutzt. Nur so faellt eine versehentliche Vermischung von exact_lookup
# und rest_lookup (z. B. exact_lookup.update(rest_lookup)) hier ueberhaupt
# auf: der Text wuerde dann faelschlich als Volltreffer gelten und ganz aus
# set_cache verschwinden. Bei MISMATCH_TEXT ("Heads ...") verschluckt die
# Rollen-Praefix-Bereinigung denselben Fehler, weil sie dort VOR dem
# canon_key-Vergleich greift und den Unterschied unsichtbar macht.
ALL8_TEXT = "All 8 Swing Thru"


@pytest.fixture
def db(tmp_path):
    from song_db import SongDatabase

    d = SongDatabase(str(tmp_path / "t.db"))
    d.insert_sequence([SPLIT_TEXT, MISMATCH_TEXT, TOUCH_QUARTER_TEXT,
                       TOUCH_SPREAD_TEXT, ALL8_TEXT])
    d.set_call_text_figures(MISMATCH_TEXT, [ANYTHING_AND_SPREAD], mapped_by="manual")
    d.set_call_text_figures(TOUCH_QUARTER_TEXT, [TOUCH_A_QUARTER], mapped_by="manual")
    d.set_call_text_figures(TOUCH_SPREAD_TEXT, [TOUCH_A_QUARTER, ANYTHING_AND_SPREAD],
                            mapped_by="manual")
    # Unvollstaendig: das All-8-Konzept fehlt (siehe ALL8_TEXT oben).
    d.set_call_text_figures(ALL8_TEXT, [SWING_THRU], mapped_by="manual")
    yield d
    d.close()


def _warte_bis(bedingung, timeout_s=15.0):
    ende = time.monotonic() + timeout_s
    while not bedingung():
        assert time.monotonic() < ende, "Zeitueberschreitung"
        QApplication.processEvents()
        time.sleep(0.01)


def _zelle0(table, call_text):
    """Call-Text-Zelle (Spalte 0) zur Zeile des Call-Texts — ueber das Item,
    weil die sortierte Tabelle Zeilen verschiebt."""
    treffer = [it for it in table.findItems(call_text, Qt.MatchExactly)
               if it.column() == 0]
    return treffer[0] if treffer else None


def _zelle(table, call_text):
    """Figur-Zelle (Spalte 2) zur Zeile des Call-Texts."""
    item0 = _zelle0(table, call_text)
    return table.item(item0.row(), 2) if item0 else None


def _filter(dlg, wert):
    combo = dlg.findChild(QComboBox)
    combo.setCurrentIndex(combo.findData(wert))


def _doppelklick(table, item):
    # Wie beim Nutzer: erster Klick, dann der Doppelklick. Ein nacktes
    # mouseDClick ohne vorherigen Klick verwirft QAbstractItemView (kein
    # passender pressedIndex) -> doubleClicked kaeme nie.
    table.scrollToItem(item)
    pos = table.visualItemRect(item).center()
    QTest.mouseClick(table.viewport(), Qt.LeftButton, Qt.NoModifier, pos)
    QTest.mouseDClick(table.viewport(), Qt.LeftButton, Qt.NoModifier, pos)


def _klick(dlg, key):
    (knopf,) = [b for b in dlg.findChildren(QPushButton) if b.text() == _t(key)]
    knopf.click()


@pytest.fixture
def mapping(qapp, db, monkeypatch):
    import sequences_widget

    monkeypatch.setattr(sequences_widget.QMessageBox, "information",
                        lambda *a, **k: None)
    dlg = sequences_widget.CallMappingDialog(db)
    dlg.show()
    table = dlg.findChild(QTableWidget)
    # Default-Filter ist "Nicht gemappt" -- der Split-Text ist unmapped und
    # damit das Lade-Signal. Braucht genau EINEN Event-Loop-Durchlauf, weil
    # _load_table() synchron in _load_deferred() laeuft; die Hintergrund-
    # Fuzzy-Chunks haengen an einem WEITEREN QTimer.singleShot und stehen an
    # dieser Stelle darum typischerweise noch aus (siehe Test unten).
    _warte_bis(lambda: _zelle(table, SPLIT_TEXT) is not None)
    yield dlg, table
    dlg.close()
    dlg.deleteLater()


@pytest.fixture
def picker_double(monkeypatch):
    """Ersetzt den Picker; ``antwort`` legt fest, was der Nutzer waehlt."""
    import sequences_widget

    aufrufe = []
    antwort = {"ids": [], "split": False}

    class _Picker:
        def __init__(self, entities, selected=(), parent=None, allow_split=False,
                     unknown_ids=()):
            aufrufe.append({"entities": list(entities), "selected": list(selected),
                            "allow_split": allow_split,
                            "unknown_ids": set(unknown_ids)})

        def setWindowTitle(self, title):
            pass

        def exec(self):
            return QDialog.Accepted

        def selected_entity_ids(self):
            return list(antwort["ids"])

        def split_requested(self):
            return antwort["split"]

    monkeypatch.setattr(sequences_widget, "CallFiguresPickerDialog", _Picker)
    return aufrufe, antwort


# ------------------------------------------------------------------ Tests --

def test_unmapped_split_text_zeigt_menge_gelb_ohne_aenderung_beim_speichern(
        mapping, db):
    dlg, table = mapping

    zelle = _zelle(table, SPLIT_TEXT)
    zelle0 = _zelle0(table, SPLIT_TEXT)
    assert zelle is not None
    assert zelle0 is not None
    assert "+1" in zelle.text()
    assert zelle0.background().color().name() == "#fff3cd"
    assert set(zelle.data(Qt.UserRole)) == {PASS_THE_OCEAN, SWING_THRU}
    # Auto-Vorschlag zaehlt nicht als Aenderung: aktuelle Menge == Lademenge
    assert zelle.data(Qt.UserRole) == zelle.data(Qt.UserRole + 1)

    vor = db.get_all_call_text_figures()
    _klick(dlg, "call_mapping_save")
    nach = db.get_all_call_text_figures()

    assert nach == vor   # nichts geschrieben -- nicht nur SPLIT_TEXT geprueft


def test_filter_mismatch_zeigt_genau_die_abweichenden_zeilen(mapping):
    dlg, table = mapping
    _filter(dlg, "mismatch")

    zeilen = {table.item(r, 0).text() for r in range(table.rowCount())}
    # ALL8_TEXT: unvollstaendige Alt-Zuordnung, Vorschlag {concept_all_8,
    # call_swing_thru} weicht als Menge von [call_swing_thru] ab -> drin.
    assert zeilen == {SPLIT_TEXT, MISMATCH_TEXT, ALL8_TEXT}
    # TOUCH_SPREAD_TEXT: nur die Reihenfolge weicht ab, die Menge nicht.
    assert TOUCH_SPREAD_TEXT not in zeilen


def test_picker_haengt_mengen_vorschlag_bei_abweichender_zuordnung_vor(
        mapping, picker_double):
    dlg, table = mapping
    aufrufe, _antwort = picker_double
    _filter(dlg, "all")

    _doppelklick(table, _zelle(table, MISMATCH_TEXT))

    (aufruf,) = aufrufe
    assert set(aufruf["selected"]) == {TOUCH_A_QUARTER, ANYTHING_AND_SPREAD}


def test_split_zeile_behaelt_menge_nach_hintergrund_fuzzy_durchlauf(mapping):
    """Prueft das ERGEBNIS: die Menge in der Split-Zeile bleibt stehen,
    nachdem der Hintergrund-Fuzzy-Chunk-Lauf durchgelaufen ist. Der
    Split-Text hat selbst keinen Eintrag im Fuzzy-Cache (er ist unmapped und
    hat keinen einzelnen Vorschlag, nur die Menge) und wird darum bei jedem
    Chunk-Lauf erneut eingereiht -- ohne den Vorrang des Mengen-Vorschlags
    wuerde die Hintergrundschleife die Zelle auf einen Einzel-Fuzzy-Treffer
    zuruecksetzen (BL-210.8)."""
    dlg, table = mapping

    # Direkt nach dem Laden stehen die Chunks noch aus (siehe Kommentar in
    # der mapping-Fixture). Beobachtbar ohne privates Attribut: solange
    # Chunks ausstehen, zeigt ein QLabel im Dialog den "computing"-Text
    # (gesetzt beim Start der Hintergrundschleife, zurueckgesetzt erst wenn
    # der letzte Chunk durch ist).
    computing = _t("call_mapping_computing")
    assert any(l.text() == computing for l in dlg.findChildren(QLabel))

    _warte_bis(lambda: not any(l.text() == computing
                               for l in dlg.findChildren(QLabel)),
               timeout_s=3.0)

    zelle = _zelle(table, SPLIT_TEXT)
    assert "+1" in zelle.text()
    assert set(zelle.data(Qt.UserRole)) == {PASS_THE_OCEAN, SWING_THRU}


def test_speichern_nach_picker_entfernt_zeile_aus_dem_mismatch_filter(
        mapping, picker_double, db):
    import sequences_widget

    dlg, table = mapping
    _aufrufe, antwort = picker_double
    _filter(dlg, "all")
    antwort["ids"] = [TOUCH_A_QUARTER, ANYTHING_AND_SPREAD]

    _doppelklick(table, _zelle(table, MISMATCH_TEXT))
    _klick(dlg, "call_mapping_save")   # ruft dlg.accept()

    assert set(db.get_call_text_figures(MISMATCH_TEXT)) == {
        TOUCH_A_QUARTER, ANYTHING_AND_SPREAD}

    # Frischer Dialog auf derselben (jetzt aktualisierten) DB -- die
    # mapping-Fixture liefert nur einen Dialog, dieser wird von Hand gebaut.
    dlg2 = sequences_widget.CallMappingDialog(db)
    dlg2.show()
    table2 = dlg2.findChild(QTableWidget)
    try:
        _warte_bis(lambda: _zelle(table2, SPLIT_TEXT) is not None)
        _filter(dlg2, "mismatch")

        zeilen = {table2.item(r, 0).text() for r in range(table2.rowCount())}
        assert MISMATCH_TEXT not in zeilen
    finally:
        dlg2.close()
        dlg2.deleteLater()
