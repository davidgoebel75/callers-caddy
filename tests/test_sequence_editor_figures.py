"""Figuren-Picker im Sequenz-Editor (BL-210.5).

Der Doppelklick geht wie beim Nutzer in das Call-Eingabefeld des Editors
(QTest auf den Viewport). Der Picker wird durch ein Double gegen seine Seam
ersetzt, weil exec() im Test blockieren wuerde. Ob eine Zeile gruen ist, liest
der Test an den Formaten ab, die der Highlighter auf die Zeile legt.

tmp-DB mit echter Referenz (reference_calls.json).
"""
import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QTextCursor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QDialog, QPlainTextEdit


CHASE_RIGHT = "call_chase_right"                  # fruehestens 39.0029
ANYTHING_AND_ROLL = "concept_anything_and_roll"   # fruehestens 39.0012
ALLEMANDE_THAR = "call_allemande_thar"            # fruehestens 29.005301

MENGE = "Chase Right & Roll"   # kein exakter Treffer -> gruen nur mit Zuordnung
UNSCHARF = "Chase Rite"        # Matcher schlaegt Chase Right vor (nicht exakt)


@pytest.fixture
def db(tmp_path):
    from song_db import SongDatabase

    d = SongDatabase(str(tmp_path / "t.db"))
    yield d
    d.close()


@pytest.fixture
def picker_double(monkeypatch):
    """Ersetzt den Picker; ``antwort`` legt fest, was der Nutzer tut."""
    import sequences_widget

    aufrufe = []
    antwort = {"ids": [], "ergebnis": QDialog.Accepted}

    class _Picker:
        def __init__(self, entities, selected=(), parent=None, allow_split=False):
            aufrufe.append({"entities": list(entities), "selected": list(selected),
                            "allow_split": allow_split})

        def setWindowTitle(self, title):
            pass

        def exec(self):
            return antwort["ergebnis"]

        def selected_entity_ids(self):
            return list(antwort["ids"])

        def split_requested(self):
            return False

    monkeypatch.setattr(sequences_widget, "CallFiguresPickerDialog", _Picker)
    return aufrufe, antwort


@pytest.fixture
def editor(qapp, db):
    """Editor mit den Zeilen ``zeilen``; liefert das Call-Eingabefeld."""
    import sequences_widget

    dialogs = []

    def _make(zeilen):
        dlg = sequences_widget.SequenceEditorDialog(db)
        dialogs.append(dlg)
        edit = dlg.findChild(QPlainTextEdit)
        edit.setPlainText("\n".join(zeilen))
        dlg.show()
        QTest.qWaitForWindowExposed(dlg)
        return edit

    yield _make
    for dlg in dialogs:
        dlg.close()
        dlg.deleteLater()


def _doppelklick(edit, zeile):
    # Wie beim Nutzer: erster Klick, dann der Doppelklick auf die Zeile
    block = edit.document().findBlockByNumber(zeile)
    pos = edit.cursorRect(QTextCursor(block)).center()
    pos.setX(pos.x() + 2)
    QTest.mouseClick(edit.viewport(), Qt.LeftButton, Qt.NoModifier, pos)
    QTest.mouseDClick(edit.viewport(), Qt.LeftButton, Qt.NoModifier, pos)


def _ist_gruen(edit, zeile):
    """Der Highlighter legt nur auf erkannte Zeilen ein Format."""
    return bool(edit.document().findBlockByNumber(zeile).layout().formats())


def test_doppelklick_auf_zugeordnete_zeile_oeffnet_picker_mit_der_menge(
        editor, picker_double, db):
    aufrufe, antwort = picker_double
    db.set_call_text_figures(MENGE, [CHASE_RIGHT, ANYTHING_AND_ROLL])
    antwort["ergebnis"] = QDialog.Rejected
    edit = editor(["Allemande Thar", MENGE])

    _doppelklick(edit, 1)

    (aufruf,) = aufrufe
    assert aufruf["selected"] == [CHASE_RIGHT, ANYTHING_AND_ROLL]
    assert aufruf["allow_split"] is False
    ids = [eid for _label, eid in aufruf["entities"]]
    assert CHASE_RIGHT in ids
    assert all(not label.startswith("--") for label, _eid in aufruf["entities"])


def test_geaenderte_menge_wird_uebernommen(editor, picker_double, db):
    _aufrufe, antwort = picker_double
    db.set_call_text_figures(MENGE, [CHASE_RIGHT, ANYTHING_AND_ROLL])
    antwort["ids"] = [ALLEMANDE_THAR, CHASE_RIGHT]
    edit = editor([MENGE])

    _doppelklick(edit, 0)

    # 39.0029 (Chase Right) liegt hoeher als 29.005301 (Allemande Thar)
    assert db.get_call_text_figures(MENGE) == [CHASE_RIGHT, ALLEMANDE_THAR]


def test_zeile_faerbt_nach_dem_picker_neu(editor, picker_double):
    _aufrufe, antwort = picker_double
    antwort["ids"] = [CHASE_RIGHT, ANYTHING_AND_ROLL]
    edit = editor([MENGE])
    assert not _ist_gruen(edit, 0)   # ungemappt, kein exakter Treffer

    _doppelklick(edit, 0)

    assert _ist_gruen(edit, 0)


def test_abbrechen_schreibt_nichts(editor, picker_double, db):
    _aufrufe, antwort = picker_double
    db.set_call_text_figures(MENGE, [CHASE_RIGHT, ANYTHING_AND_ROLL])
    antwort["ids"] = [ALLEMANDE_THAR]
    antwort["ergebnis"] = QDialog.Rejected
    edit = editor([MENGE])

    _doppelklick(edit, 0)

    assert db.get_call_text_figures(MENGE) == [CHASE_RIGHT, ANYTHING_AND_ROLL]


def test_ungemappte_zeile_startet_mit_dem_matcher_vorschlag(editor, picker_double):
    aufrufe, antwort = picker_double
    antwort["ergebnis"] = QDialog.Rejected
    edit = editor([UNSCHARF, "Zzqx Blorp"])

    _doppelklick(edit, 0)
    _doppelklick(edit, 1)   # ohne Vorschlag bleibt die Liste leer

    assert [a["selected"] for a in aufrufe] == [[CHASE_RIGHT], []]


def test_leere_auswahl_entfernt_die_zuordnung(editor, picker_double, db):
    _aufrufe, antwort = picker_double
    db.set_call_text_figures(MENGE, [CHASE_RIGHT, ANYTHING_AND_ROLL])
    antwort["ids"] = []
    edit = editor([MENGE])
    assert _ist_gruen(edit, 0)

    _doppelklick(edit, 0)

    assert db.get_call_text_figures(MENGE) == []
    assert not _ist_gruen(edit, 0)


def test_leere_zeile_oeffnet_keinen_picker(editor, picker_double):
    aufrufe, antwort = picker_double
    antwort["ergebnis"] = QDialog.Rejected
    edit = editor(["Allemande Thar", "", "   ", MENGE])

    _doppelklick(edit, 1)
    _doppelklick(edit, 2)
    assert aufrufe == []

    _doppelklick(edit, 3)   # Gegenprobe: gefuellte Zeile oeffnet ihn
    assert len(aufrufe) == 1


def test_unveraenderte_menge_wird_nicht_neu_geschrieben(editor, picker_double, db):
    # Neu schreiben machte aus 'auto' ein 'manual' und verwuerfe den Cover-Cache
    _aufrufe, antwort = picker_double
    db.set_call_text_figures(MENGE, [CHASE_RIGHT, ANYTHING_AND_ROLL],
                             mapped_by="auto")
    antwort["ids"] = [ANYTHING_AND_ROLL, CHASE_RIGHT]   # andere Reihenfolge
    edit = editor([MENGE])

    _doppelklick(edit, 0)

    zeilen = {(m["entity_id"], m["mapped_by"])
              for m in db.get_all_call_text_mappings() if m["call_text"] == MENGE}
    assert zeilen == {(CHASE_RIGHT, "auto"), (ANYTHING_AND_ROLL, "auto")}


def test_figur_ohne_programm_bleibt_beim_ok_erhalten(editor, db, monkeypatch):
    import sequences_widget

    # Altbestand wie in test_call_text_figures: steht in calls, hat nach dem
    # Referenz-Update aber keine call_programs-Zeile -> fehlt in der Figurenliste
    legacy = "call_legacy_figure"
    db.bulk_insert_teaching_order_calls([(legacy, "Legacy Figure", 10.5, "")])
    db.reseed_reference_data(force=True)
    db.set_call_text_figures(MENGE, [CHASE_RIGHT, legacy])
    # Echter Picker (ein Double saehe den Fehler nicht), nur exec() blockiert
    # nicht: OK ohne jede Aenderung
    monkeypatch.setattr(sequences_widget.CallFiguresPickerDialog, "exec",
                        lambda self: QDialog.Accepted)
    edit = editor([MENGE])

    _doppelklick(edit, 0)

    assert db.get_call_text_figures(MENGE) == [CHASE_RIGHT, legacy]
