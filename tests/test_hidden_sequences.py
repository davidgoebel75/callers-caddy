"""Wo ist meine Sequenz? (intern#119)

Frisch importierte Sequenzen verschwinden, wenn ihre Call-Texte keine Zuordnung
haben: mit Tanzprogramm-Wahl fehlen Sequenzen ganz ohne gemappte Figur, mit Limit
jede Sequenz mit auch nur einem ungemappten Call-Text. Abhilfe:

- Rechtsklick "Auch ausgeblendete Sequenzen anzeigen": hebt Enthaelt, Limit und Nur-Filter
  auf, setzt die Tanzprogramm-Wahl NUR fuer die Liste aus (Typ, Schwierigkeit,
  Tags bleiben), laedt alles und springt ans Ende.
- Sequenzen mit Call-Texten ohne Zuordnung sind rot; Rechtsklick "Call-Mapping
  fuer diese Sequenz oeffnen" filtert es auf genau diese Call-Texte.

Nur oeffentliche Methoden und sichtbare Qt-Bausteine, keine privaten Attribute.
Entity-IDs aus src/reference_calls.json.
"""
import time

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QLabel, QMenu, QTableWidget,
)

from i18n import _t


SWING_THRU = "call_swing_thru"          # Mainstream, Teaching-Order 20.0038
MAPPED = "Swing Thru"
UNMAPPED_A = "Heads Frobnicate"         # bewusst ohne Zuordnung
UNMAPPED_B = "Sides Wiggle Around"      # bewusst ohne Zuordnung
SINGER = "Singer (Corner progression)"
PATTER = "Patter"
HARD = "Hard"


@pytest.fixture
def db(tmp_path):
    from song_db import SongDatabase

    d = SongDatabase(str(tmp_path / "t.db"))
    d.set_call_text_figures(MAPPED, [SWING_THRU], mapped_by="manual")
    ids = {
        # voll gemappt -> bei Tanzprogramm-Wahl Mainstream sichtbar
        "ok": d.insert_sequence([MAPPED, MAPPED], seq_type=SINGER),
        # teilweise gemappt -> rot
        "teil": d.insert_sequence([MAPPED, UNMAPPED_A, UNMAPPED_A],
                                  seq_type=SINGER),
        # "frisch importiert": gar nichts gemappt -> bei Tanzprogramm-Wahl weg
        "neu": d.insert_sequence([UNMAPPED_A, UNMAPPED_B], seq_type=SINGER),
        # anderer Typ -> vom Typ-Filter ausgeblendet, auch bei "Auch ausgeblendete Sequenzen anzeigen"
        "patter": d.insert_sequence([UNMAPPED_B], seq_type=PATTER,
                                    difficulty=HARD),
    }
    d.recompute_sequence_max_to()
    d.ids = ids
    yield d
    d.close()


def _warte_bis(bedingung, timeout_s=15.0):
    ende = time.monotonic() + timeout_s
    while not bedingung():
        assert time.monotonic() < ende, "Zeitueberschreitung"
        QApplication.processEvents()
        time.sleep(0.01)


def _ids(table):
    return [table.item(r, 0).data(Qt.UserRole) for r in range(table.rowCount())]


def _status(widget):
    texte = [lb.text() for lb in widget.findChildren(QLabel)]
    return next(t for t in texte if _t("sequences_program_selection_suspended") in t
                or "Sequen" in t or "sequen" in t)


@pytest.fixture
def widget(qapp, db):
    from sequences_widget import SequencesWidget

    w = SequencesWidget(db)
    w.set_type_filter(SINGER)
    w.set_program_bands({20})           # Tanzprogramm-Wahl: Mainstream
    yield w
    w.deleteLater()


# ------------------------------------------------------------------ DB --

def test_ungemappte_call_texte_einer_sequenz(db):
    assert db.get_unmapped_call_texts_of_sequence(db.ids["teil"]) == [UNMAPPED_A]
    assert db.get_unmapped_call_texts_of_sequence(db.ids["neu"]) == [
        UNMAPPED_A, UNMAPPED_B]
    assert db.get_unmapped_call_texts_of_sequence(db.ids["ok"]) == []
    assert db.get_unmapped_call_texts_of_sequence(999999) == []


# --------------------------------- Ausgeblendete zeigen --

def test_tanzprogramm_wahl_versteckt_frisch_importierte(widget, db):
    table = widget.findChild(QTableWidget)
    assert db.ids["neu"] not in _ids(table)


def test_ausgeblendete_zeigt_alle_und_springt_ans_ende(widget, db):
    table = widget.findChild(QTableWidget)
    widget.show_hidden_sequences()

    # Typ-Filter bleibt: Patter-Sequenz weiter ausgeblendet
    assert _ids(table) == [db.ids["ok"], db.ids["teil"], db.ids["neu"]]
    # neueste (hoechste id) unten und markiert
    assert table.currentRow() == table.rowCount() - 1
    assert _t("sequences_program_selection_suspended") in _status(widget)


def test_ausgeblendete_hebt_nur_zuordnungs_filter_auf(widget):
    only = widget.findChild(QCheckBox)
    only.setChecked(True)
    widget.show_hidden_sequences()
    assert not only.isChecked()
    assert widget.get_limit_filter_text() == ""
    assert widget.get_contains_filter_text() == ""


def test_filterwechsel_beendet_das_aussetzen(widget, db):
    table = widget.findChild(QTableWidget)
    widget.show_hidden_sequences()
    widget.set_type_filter("")          # Typ "Alle" -> normaler Filterwechsel
    assert db.ids["neu"] not in _ids(table)
    assert _t("sequences_program_selection_suspended") not in _status(widget)


def test_programmwechsel_beendet_das_aussetzen(widget, db):
    table = widget.findChild(QTableWidget)
    widget.show_hidden_sequences()
    widget.set_program_bands({20, 30})
    assert db.ids["neu"] not in _ids(table)


def test_kontextmenue_auch_in_leerer_liste(widget, monkeypatch):
    widget.set_type_filter("")
    widget.set_program_bands({90})      # Band ohne Figuren -> Liste leer
    table = widget.findChild(QTableWidget)
    assert table.rowCount() == 0
    import sequences_widget

    gesehen = []

    class _StummesMenue(QMenu):
        # Statt des blockierenden Popups nur die Eintraege merken
        def exec(self, *_a):
            gesehen.extend(act.text() for act in self.actions())

    monkeypatch.setattr(sequences_widget, "QMenu", _StummesMenue)
    table.customContextMenuRequested.emit(table.rect().center())
    assert _t("ctx_show_hidden_sequences") in gesehen


# ----------------------------------------------- Rot + Doppelklick --

def _zeile(table, seq_id):
    return next(r for r in range(table.rowCount())
                if table.item(r, 0).data(Qt.UserRole) == seq_id)


def test_ungemappte_sequenzen_sind_rot(widget, db):
    table = widget.findChild(QTableWidget)
    widget.show_hidden_sequences()
    rot = {r for r in range(table.rowCount())
           if table.item(r, 0).toolTip() == _t("sequences_unmapped_tooltip")}
    assert rot == {_zeile(table, db.ids["teil"]), _zeile(table, db.ids["neu"])}


def _rechtsklick(table, row, monkeypatch, waehle=None):
    """Kontextmenue auf einer Zeile oeffnen; liefert die Eintraege und loest
    optional den Eintrag mit Text `waehle` aus (statt blockierendem Popup)."""
    import sequences_widget

    gesehen = []

    class _StummesMenue(QMenu):
        def exec(self, *_a):
            for act in self.actions():
                gesehen.append(act.text())
                if waehle and act.text() == waehle:
                    act.trigger()

    monkeypatch.setattr(sequences_widget, "QMenu", _StummesMenue)
    item = table.item(row, 0)
    table.scrollToItem(item)
    table.customContextMenuRequested.emit(table.visualItemRect(item).center())
    return gesehen


def test_rechtsklick_auf_rot_oeffnet_call_mapping_mit_fokus(widget, db, monkeypatch):
    table = widget.findChild(QTableWidget)
    widget.resize(600, 400)
    widget.show()
    widget.show_hidden_sequences()
    aufrufe = []
    widget.on_open_call_mapping = aufrufe.append
    eintrag = _t("ctx_open_call_mapping_for_sequence")

    # nicht-rote Sequenz: kein Call-Mapping-Eintrag
    assert eintrag not in _rechtsklick(table, _zeile(table, db.ids["ok"]), monkeypatch)

    gesehen = _rechtsklick(table, _zeile(table, db.ids["neu"]), monkeypatch,
                           waehle=eintrag)
    assert eintrag in gesehen
    assert aufrufe == [[UNMAPPED_A, UNMAPPED_B]]
    # danach steht die Sequenz wieder markiert
    assert table.item(table.currentRow(), 0).data(Qt.UserRole) == db.ids["neu"]


def test_doppelklick_oeffnet_kein_call_mapping(widget, db):
    """Doppelklick bleibt beim bisherigen Verhalten (Sequenz-Detail)."""
    table = widget.findChild(QTableWidget)
    widget.resize(600, 400)
    widget.show()
    widget.show_hidden_sequences()
    aufrufe = []
    widget.on_open_call_mapping = aufrufe.append
    item = table.item(_zeile(table, db.ids["neu"]), 0)
    pos = table.visualItemRect(item).center()
    QTest.mouseClick(table.viewport(), Qt.LeftButton, Qt.NoModifier, pos)
    QTest.mouseDClick(table.viewport(), Qt.LeftButton, Qt.NoModifier, pos)
    assert aufrufe == []


def test_call_mapping_startet_gefiltert_auf_fokus(qapp, db):
    import sequences_widget

    dlg = sequences_widget.CallMappingDialog(db, focus_texts=[UNMAPPED_A, UNMAPPED_B])
    dlg.show()
    try:
        table = dlg.findChild(QTableWidget)
        _warte_bis(lambda: table.rowCount() > 0)
        texte = {table.item(r, 0).text() for r in range(table.rowCount())}
        assert texte == {UNMAPPED_A, UNMAPPED_B}
        combo = dlg.findChild(QComboBox)
        assert combo.currentText() == _t("call_mapping_f_focus", count=2)
        assert table.currentColumn() == 2
        # Fokus bleibt nur ein Filter: "Alle" zeigt wieder alles
        combo.setCurrentIndex(combo.findText(_t("call_mapping_f_all")))
        assert table.rowCount() == 3
    finally:
        dlg.close()


def test_call_mapping_ok_behaelt_typ_und_markierung(widget, db, monkeypatch):
    """intern#131: Nach "OK" im Call-Mapping (Remapping baut die Dropdowns
    neu) bleiben Typ und Schwierigkeit stehen, und dieselbe Sequenz ist
    wieder markiert. Bisher sprang der Typ auf "Singer" zurueck."""
    table = widget.findChild(QTableWidget)
    widget.resize(600, 400)
    widget.show()
    assert widget.set_type_filter(PATTER)
    diff = next(c for c in widget.findChildren(QComboBox) if c.findText(HARD) > 0)
    diff.setCurrentIndex(diff.findText(HARD))
    widget.show_hidden_sequences()
    # Wie P29MainWindow._open_call_mapping nach Accept
    widget.on_open_call_mapping = lambda _texts: widget._do_remapping()
    _rechtsklick(table, _zeile(table, db.ids["patter"]), monkeypatch,
                 waehle=_t("ctx_open_call_mapping_for_sequence"))
    texte = [c.currentText() for c in widget.findChildren(QComboBox)]
    assert PATTER in texte and HARD in texte
    assert table.item(table.currentRow(), 0).data(Qt.UserRole) == db.ids["patter"]
