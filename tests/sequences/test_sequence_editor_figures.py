"""Figuren-Picker im Sequenz-Editor (BL-210.5).

Der Doppelklick geht wie beim Nutzer in das Call-Eingabefeld des Editors
(QTest auf den Viewport). Der Picker wird durch ein Double gegen seine Seam
ersetzt, weil exec() im Test blockieren wuerde. Ob eine Zeile gruen ist, liest
der Test an den Formaten ab, die der Highlighter auf die Zeile legt.

tmp-DB mit echter Referenz (reference_calls.json).
"""
import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QTextCursor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QDialog, QPlainTextEdit


CHASE_RIGHT = "call_chase_right"                  # fruehestens 39.0029
ANYTHING_AND_ROLL = "concept_anything_and_roll"   # fruehestens 39.0012
ALLEMANDE_THAR = "call_allemande_thar"            # fruehestens 29.005301
TOUCH_A_QUARTER = "call_touch_a_quarter"
ANYTHING_AND_SPREAD = "concept_anything_and_spread"
ALL_EIGHT_CIRCULATE = "call_all_eight_circulate"  # K1: eigene Figur, kein Konzept

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
        def __init__(self, entities, selected=(), parent=None, allow_split=False,
                     unknown_ids=()):
            aufrufe.append({"entities": list(entities), "selected": list(selected),
                            "allow_split": allow_split,
                            "unknown_ids": set(unknown_ids)})

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


def _zustand(edit, zeile):
    """'gruen' / 'gelb' / None -- am Hintergrund, den der Highlighter legt."""
    formats = edit.document().findBlockByNumber(zeile).layout().formats()
    if not formats:
        return None
    farbe = formats[0].format.background().color().name()
    return {QColor(46, 94, 46).name(): "gruen",
            QColor(110, 90, 20).name(): "gelb"}[farbe]


def _ist_gruen(edit, zeile):
    return _zustand(edit, zeile) == "gruen"


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

    # OK nimmt auch den vorangehakten Mengen-Vorschlag mit (BL-210.12)
    assert db.get_call_text_figures(MENGE) == [CHASE_RIGHT, ANYTHING_AND_ROLL,
                                               legacy]


def test_verwaiste_figur_ist_markiert_und_stoert_das_speichern_nicht(
        editor, picker_double, db):
    aufrufe, antwort = picker_double
    # Altbestand wie auf der Prod-DB: auto-Zuordnung auf eine ID ohne calls-Zeile
    db._conn.execute("PRAGMA foreign_keys=OFF")
    db._conn.execute(
        "INSERT INTO call_text_mappings (call_text, entity_id, mapped_by) "
        "VALUES (?, 'action_face_in', 'auto')", (MENGE,))
    db._conn.commit()
    db._conn.execute("PRAGMA foreign_keys=ON")
    antwort["ids"] = ["action_face_in", CHASE_RIGHT]   # Haken bleibt, Figur dazu
    edit = editor([MENGE])

    _doppelklick(edit, 0)   # frueher: IntegrityError aus dem Qt-Slot

    assert aufrufe[0]["unknown_ids"] == {"action_face_in"}
    assert db.get_call_text_figures(MENGE) == [CHASE_RIGHT]


# --- BL-210.12: Mustererkennung im Sequenz-Editor ---------------------------

HALB_ROLL = "Heads Touch 1/4 & Roll"      # zugeordnet nur auf die Zielfigur
HALB_SPREAD = "Heads Touch 1/4 & Spread"  # zugeordnet nur auf die Vorlage


def _halbe_zuordnungen(db):
    # 'Touch 1/4' ist kein kanonischer Name (die Figur heisst 'Touch a
    # Quarter'), steht aber schon als Zuordnung -> rest_lookup loest ihn auf
    db.set_call_text_figures("Touch 1/4", [TOUCH_A_QUARTER])
    db.set_call_text_figures(HALB_ROLL, [TOUCH_A_QUARTER], mapped_by="auto")
    db.set_call_text_figures(HALB_SPREAD, [ANYTHING_AND_SPREAD])


def test_halbe_zuordnung_bekommt_den_mustervorschlag_dazu(
        editor, picker_double, db):
    aufrufe, antwort = picker_double
    _halbe_zuordnungen(db)
    antwort["ergebnis"] = QDialog.Rejected
    edit = editor([HALB_ROLL, HALB_SPREAD])
    assert [_zustand(edit, 0), _zustand(edit, 1)] == ["gelb", "gelb"]

    _doppelklick(edit, 0)
    _doppelklick(edit, 1)

    # Vereinigung in beide Richtungen; Reihenfolge ist kein Vertrag
    assert [set(a["selected"]) for a in aufrufe] == [
        {TOUCH_A_QUARTER, ANYTHING_AND_ROLL},
        {TOUCH_A_QUARTER, ANYTHING_AND_SPREAD}]
    # Abbrechen schreibt nichts, auch nicht die vorangehakte Ergaenzung
    zeilen = {(m["entity_id"], m["mapped_by"])
              for m in db.get_all_call_text_mappings() if m["call_text"] == HALB_ROLL}
    assert zeilen == {(TOUCH_A_QUARTER, "auto")}
    assert db.get_call_text_figures(HALB_SPREAD) == [ANYTHING_AND_SPREAD]


def test_ok_uebernimmt_die_ergaenzte_menge(editor, picker_double, db):
    _aufrufe, antwort = picker_double
    _halbe_zuordnungen(db)
    antwort["ids"] = [TOUCH_A_QUARTER, ANYTHING_AND_ROLL]
    edit = editor([HALB_ROLL])

    _doppelklick(edit, 0)

    assert set(db.get_call_text_figures(HALB_ROLL)) == {
        TOUCH_A_QUARTER, ANYTHING_AND_ROLL}
    assert _zustand(edit, 0) == "gruen"


def test_all8_figur_bekommt_kein_konzept_vorangehakt(editor, picker_double, db):
    aufrufe, antwort = picker_double
    db.set_call_text_figures("All Eight Circulate", [ALL_EIGHT_CIRCULATE])
    antwort["ergebnis"] = QDialog.Rejected
    edit = editor(["All Eight Circulate"])
    assert _zustand(edit, 0) == "gruen"

    _doppelklick(edit, 0)

    assert aufrufe[0]["selected"] == [ALL_EIGHT_CIRCULATE]


def test_neue_zuordnung_faerbt_andere_zeilen_neu(editor, picker_double, db):
    # 'Touch 1/4' ist noch nirgends zugeordnet -> fuer HALB_ROLL kein Vorschlag
    _aufrufe, antwort = picker_double
    antwort["ids"] = [TOUCH_A_QUARTER]
    edit = editor([HALB_ROLL, "Touch 1/4"])
    assert _zustand(edit, 0) is None

    _doppelklick(edit, 1)

    # die neue Zuordnung loest den Rest auf, der Vorschlag erscheint sofort
    assert _zustand(edit, 0) == "gelb"


# --- intern#88: Rueckfrage beim Speichern -----------------------------------

@pytest.fixture
def speichern(monkeypatch):
    """Ersetzt Rueckfrage und Erfolgsmeldung; ``antwort["knopf"]`` ist die
    Antwort auf die Rueckfrage. Liefert eine Funktion, die wie der Nutzer
    einen Typ waehlt und auf Speichern klickt."""
    import sequences_widget
    from PySide6.QtWidgets import QComboBox, QMessageBox, QPushButton
    from i18n import _t

    fragen = []
    antwort = {"knopf": QMessageBox.Yes}

    # Aufgezeichnet wird, was der Nutzer liest -- "woertlich": die Box zeigt
    # den Text als Klartext, nicht als Rich Text (dort verschwaenden <...>)
    def _exec(box):
        fragen.append({"text": box.text(), "details": box.detailedText(),
                       "woertlich": box.textFormat() == Qt.PlainText})
        return antwort["knopf"]

    monkeypatch.setattr(sequences_widget.QMessageBox, "exec", _exec)
    monkeypatch.setattr(sequences_widget.QMessageBox, "information",
                        lambda *a, **k: None)

    def _klick(edit):
        dlg = edit.window()
        dlg.findChild(QComboBox).setCurrentText("Singing Call")   # Typ
        (knopf,) = [b for b in dlg.findChildren(QPushButton)
                    if b.text() == _t("seq_editor_btn_save")]
        knopf.click()

    return _klick, fragen, antwort


def _max_to(db, erster_call):
    """max_teaching_order der Sequenz mit diesem ersten Call (field_1) --
    ueber die oeffentliche Listen-Abfrage (Index 1 = field_1, 17 = max_to)."""
    (wert,) = [r[17] for r in db.get_filtered_sequences(limit=100)
               if r[1] == erster_call]
    return wert


def test_ja_beim_speichern_uebernimmt_die_vorgeschlagene_menge(
        editor, speichern, db):
    klick, fragen, _antwort = speichern
    _halbe_zuordnungen(db)
    edit = editor([HALB_ROLL, "Allemande Thar"])

    klick(edit)

    assert len(fragen) == 1
    zeilen = {(m["entity_id"], m["mapped_by"])
              for m in db.get_all_call_text_mappings() if m["call_text"] == HALB_ROLL}
    assert zeilen == {(TOUCH_A_QUARTER, "inferred"), (ANYTHING_AND_ROLL, "inferred")}
    # Level wie nach dem Speichern in der App (main._after_save rechnet die
    # Baender nach): (Anything) & Roll ist Plus
    db.recompute_sequence_max_to()
    assert _max_to(db, HALB_ROLL) == pytest.approx(39.0012)


def test_nein_beim_speichern_laesst_die_zuordnung_und_speichert(
        editor, speichern, db):
    from PySide6.QtWidgets import QMessageBox

    klick, fragen, antwort = speichern
    antwort["knopf"] = QMessageBox.No
    _halbe_zuordnungen(db)
    edit = editor([HALB_ROLL, "Allemande Thar"])

    klick(edit)

    assert len(fragen) == 1
    zeilen = {(m["entity_id"], m["mapped_by"])
              for m in db.get_all_call_text_mappings() if m["call_text"] == HALB_ROLL}
    assert zeilen == {(TOUCH_A_QUARTER, "auto")}
    db.recompute_sequence_max_to()
    # ohne (Anything) & Roll bleibt Allemande Thar die hoechste Figur
    assert _max_to(db, HALB_ROLL) == pytest.approx(29.005301)


def test_ohne_gelbe_zeile_kommt_keine_rueckfrage(editor, speichern, db):
    klick, fragen, _antwort = speichern
    # K1: eigene Figur, kein Mengen-Vorschlag; dazu eine unbekannte Zeile
    db.set_call_text_figures("All Eight Circulate", [ALL_EIGHT_CIRCULATE])
    edit = editor(["All Eight Circulate", "Zzqx Blorp"])

    klick(edit)

    assert fragen == []
    assert [r[1] for r in db.get_filtered_sequences(limit=100)] == [
        "All Eight Circulate"]   # trotzdem gespeichert
    assert db.get_call_text_figures("All Eight Circulate") == [ALL_EIGHT_CIRCULATE]


def test_rueckfrage_listet_call_texte_mit_den_dazukommenden_figuren(
        editor, speichern, db):
    klick, fragen, _antwort = speichern
    _halbe_zuordnungen(db)
    edit = editor([HALB_ROLL, "Allemande Thar", HALB_ROLL, HALB_SPREAD])

    klick(edit)

    # je Call-Text einmal, nur die Figuren, die zur bisherigen Menge dazukommen
    (frage,) = fragen
    assert frage["text"] == (
        "2 Call-Texte haben Vorschläge mit noch fehlenden Figuren – "
        "jetzt übernehmen?\n\n"
        "Heads Touch 1/4 & Roll  →  + (Anything) & Roll\n"
        "Heads Touch 1/4 & Spread  →  + Touch a Quarter")


def test_rueckfrage_zu_einem_call_text_im_singular(editor, speichern, db):
    klick, fragen, _antwort = speichern
    _halbe_zuordnungen(db)
    edit = editor([HALB_ROLL, "Allemande Thar"])

    klick(edit)

    (frage,) = fragen
    assert frage["text"] == (
        "Ein Call-Text hat einen Vorschlag mit noch fehlenden Figuren – "
        "jetzt übernehmen?\n\n"
        "Heads Touch 1/4 & Roll  →  + (Anything) & Roll")
    assert frage["details"] == ""


# elf ungemappte Texte, alle mit Mengen-Vorschlag (Figur + Konzept)
ELF_TEXTE = ["Swing Thru & Roll", "Scoot Back & Roll", "Zoom & Roll",
             "Swing Thru & Spread", "Trade & Roll", "Partner Trade & Roll",
             "Dosado & Roll", "Ferris Wheel & Roll", "Wheel Around & Roll",
             "Zoom & Spread", "Dosado & Spread"]


def test_rueckfrage_zeigt_elf_call_texte_ungekuerzt(editor, speichern, db):
    # "... und 1 weitere" spart keine Zeile -- gekuerzt wird erst ab zwei
    klick, fragen, _antwort = speichern
    edit = editor(ELF_TEXTE)

    klick(edit)

    (frage,) = fragen
    zeilen = frage["text"].split("\n")
    assert len(zeilen) == 2 + 11   # Frage, Leerzeile, elf Texte
    assert zeilen[-1] == "Dosado & Spread  →  + Dosado, (Anything) & Spread"
    assert frage["details"] == ""


def test_rueckfrage_kuerzt_ab_zwoelf_call_texten(editor, speichern, db):
    klick, fragen, _antwort = speichern
    edit = editor(ELF_TEXTE + ["Scoot Back & Spread"])

    klick(edit)

    (frage,) = fragen
    zeilen = frage["text"].split("\n")
    assert len(zeilen) == 2 + 10 + 1   # Frage, Leerzeile, zehn Texte, Rest
    assert zeilen[-2:] == ["Zoom & Spread  →  + Zoom, (Anything) & Spread",
                           "… und 2 weitere"]
    assert "Dosado & Spread" not in frage["text"]
    # die komplette Liste steht im Detailbereich
    details = frage["details"].split("\n")
    assert len(details) == 12
    assert details[0] == "Swing Thru & Roll  →  + Swing Thru, (Anything) & Roll"
    assert details[-1] == ("Scoot Back & Spread  →  + Scoot Back, "
                           "(Anything) & Spread")


def test_rueckfrage_zeigt_spitze_klammern_woertlich(editor, speichern, db):
    klick, fragen, _antwort = speichern
    db.set_call_text_figures("<Zoom>", ["call_zoom"])
    edit = editor(["<Zoom> & Roll"])

    klick(edit)

    (frage,) = fragen
    assert frage["text"].split("\n")[-1] == (
        "<Zoom> & Roll  →  + Zoom, (Anything) & Roll")
    assert frage["woertlich"]


def test_rueckfrage_zeigt_figur_ohne_namen_mit_ihrer_id(editor, speichern, db):
    klick, fragen, _antwort = speichern
    # Altbestand wie in test_figur_ohne_programm_bleibt_beim_ok_erhalten: steht
    # in calls, hat aber keine call_programs-Zeile -> kein Name im Katalog
    legacy = "call_legacy_figure"
    db.bulk_insert_teaching_order_calls([(legacy, "Legacy Figure", 10.5, "")])
    db.reseed_reference_data(force=True)
    db.set_call_text_figures("Legacy Thing", [legacy])
    edit = editor(["Legacy Thing & Roll"])

    klick(edit)

    (frage,) = fragen
    assert frage["text"].split("\n")[-1] == (
        "Legacy Thing & Roll  →  + call_legacy_figure, (Anything) & Roll")
