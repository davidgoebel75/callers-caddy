"""Mehrfach-Picker fuer Figuren-Mengen im Call-Mapping (BL-210.4).

Der Picker wird ausschliesslich ueber seine Seam getestet
(selected_entity_ids, split_requested, visible_entity_ids, set_search_text)
und ueber sichtbare Qt-Bausteine (Haken-Liste, Knoepfe) — keine privaten
Attribute.

Der Call-Mapping-Dialog laeuft gegen eine frische tmp-DB mit echter Referenz
(reference_calls.json). Dort wird der Picker durch ein Double gegen dieselbe
Seam ersetzt, weil exec() im Test blockieren wuerde.
"""
import time

import pytest
from PySide6.QtCore import QItemSelectionModel, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import (
    QApplication, QComboBox, QDialog, QListWidget, QPushButton, QTableWidget,
)

from i18n import _t


CHASE_RIGHT = "call_chase_right"                  # fruehestens 39.0029
ANYTHING_AND_ROLL = "concept_anything_and_roll"   # fruehestens 39.0012
ALLEMANDE_RIGHT = "call_allemande_right"          # fruehestens 30.000402
ALLEMANDE_THAR = "call_allemande_thar"            # fruehestens 29.005301

ENTITIES = [
    ("Allemande Thar  [Mainstream]", ALLEMANDE_THAR),
    ("Allemande Right  [Mainstream (2026)]", ALLEMANDE_RIGHT),
    ("(Anything) & Roll  [Plus]", ANYTHING_AND_ROLL),
    ("Chase Right  [Plus]", CHASE_RIGHT),
]


@pytest.fixture
def make_picker(qapp):
    dialogs = []

    def _make(entities=ENTITIES, selected=(), allow_split=False, unknown_ids=()):
        from sequences_widget import CallFiguresPickerDialog

        dlg = CallFiguresPickerDialog(entities, selected=selected,
                                      allow_split=allow_split,
                                      unknown_ids=unknown_ids)
        dialogs.append(dlg)
        return dlg

    yield _make
    for dlg in dialogs:
        dlg.close()
        dlg.deleteLater()


def _haken_umschalten(dlg, label):
    """Wie ein Nutzer: Eintrag in der Haken-Liste waehlen, Leertaste. Das
    Umsortieren laeuft deferred (QTimer.singleShot, intern#74) — einmal
    processEvents(), damit es vor der naechsten Assertion durchgelaufen ist."""
    lst = dlg.findChild(QListWidget)
    item = lst.findItems(label, Qt.MatchExactly)[0]
    lst.setCurrentItem(item)
    QTest.keyClick(lst, Qt.Key_Space)
    QApplication.processEvents()


def _knoepfe(dlg, text):
    return [b for b in dlg.findChildren(QPushButton) if b.text() == text]


# --------------------------------------------------------------- Picker ----

def test_startet_mit_der_bestehenden_menge_angehakt(make_picker):
    dlg = make_picker(selected=[CHASE_RIGHT, ALLEMANDE_THAR])

    # Listen-Reihenfolge, nicht die Reihenfolge der Vorauswahl
    assert dlg.selected_entity_ids() == [ALLEMANDE_THAR, CHASE_RIGHT]
    assert dlg.split_requested() is False


def test_haken_setzen_und_entfernen_liefert_die_menge(make_picker):
    dlg = make_picker(selected=[CHASE_RIGHT])

    _haken_umschalten(dlg, "(Anything) & Roll  [Plus]")
    assert dlg.selected_entity_ids() == [ANYTHING_AND_ROLL, CHASE_RIGHT]

    _haken_umschalten(dlg, "Chase Right  [Plus]")
    assert dlg.selected_entity_ids() == [ANYTHING_AND_ROLL]

    _haken_umschalten(dlg, "(Anything) & Roll  [Plus]")
    assert dlg.selected_entity_ids() == []   # leere Menge = keine Zuordnung


def test_split_knopf_liefert_den_split_weg_statt_einer_menge(make_picker):
    dlg = make_picker(selected=[CHASE_RIGHT], allow_split=True)
    (split,) = _knoepfe(dlg, _t("call_mapping_split"))

    split.click()

    assert dlg.result() == QDialog.Accepted
    assert dlg.split_requested() is True


def test_split_knopf_gibt_es_nur_mit_allow_split(make_picker):
    dlg = make_picker(selected=[CHASE_RIGHT])

    assert _knoepfe(dlg, _t("call_mapping_split")) == []


def test_suchfeld_filtert_und_haken_bleiben_erhalten(make_picker):
    dlg = make_picker(selected=[CHASE_RIGHT])

    dlg.set_search_text("allemande")   # Gross/klein egal, Teiltreffer
    assert dlg.visible_entity_ids() == [ALLEMANDE_THAR, ALLEMANDE_RIGHT]
    lst = dlg.findChild(QListWidget)
    assert lst.findItems("Chase Right  [Plus]", Qt.MatchExactly)[0].isHidden()

    _haken_umschalten(dlg, "Allemande Right  [Mainstream (2026)]")
    # Der ausgeblendete Haken bei Chase Right zaehlt weiter
    assert dlg.selected_entity_ids() == [ALLEMANDE_RIGHT, CHASE_RIGHT]

    dlg.set_search_text("& ROLL")
    assert dlg.visible_entity_ids() == [ANYTHING_AND_ROLL]

    dlg.set_search_text("")
    assert dlg.visible_entity_ids() == [
        ALLEMANDE_RIGHT, CHASE_RIGHT, ALLEMANDE_THAR, ANYTHING_AND_ROLL]
    assert dlg.selected_entity_ids() == [ALLEMANDE_RIGHT, CHASE_RIGHT]


def test_figur_aus_zwei_programmen_zaehlt_einmal(make_picker):
    # Die Referenz fuehrt eine Figur je Programm (Chase Right: Plus und
    # Plus (2026)) — beide Eintraege sind dieselbe Figur.
    entities = ENTITIES + [("Chase Right  [Plus (2026)]", CHASE_RIGHT)]
    dlg = make_picker(entities=entities)
    lst = dlg.findChild(QListWidget)

    _haken_umschalten(dlg, "Chase Right  [Plus (2026)]")
    assert dlg.selected_entity_ids() == [CHASE_RIGHT]
    assert lst.findItems("Chase Right  [Plus]", Qt.MatchExactly)[0] \
        .checkState() == Qt.Checked

    dlg.set_search_text("chase")
    assert dlg.visible_entity_ids() == [CHASE_RIGHT]

    _haken_umschalten(dlg, "Chase Right  [Plus]")
    assert dlg.selected_entity_ids() == []


def test_zugeordnete_figur_ausserhalb_der_liste_bleibt_angehakt(make_picker):
    # Figur ohne call_programs-Zeile: zugeordnet, aber nicht in der Liste.
    # Ohne eigenen Eintrag ginge sie beim OK stillschweigend verloren.
    legacy = "call_legacy_figure"
    dlg = make_picker(selected=[CHASE_RIGHT, legacy])
    lst = dlg.findChild(QListWidget)

    assert lst.item(0).text() == f"[{legacy}]"   # ganz oben
    assert dlg.selected_entity_ids() == [legacy, CHASE_RIGHT]

    dlg.set_search_text("legacy")
    assert dlg.visible_entity_ids() == [legacy]

    _haken_umschalten(dlg, f"[{legacy}]")   # bewusst abhaken
    assert dlg.selected_entity_ids() == [CHASE_RIGHT]


def test_figur_ohne_calls_zeile_ist_als_unbekannt_markiert(make_picker):
    dlg = make_picker(selected=[CHASE_RIGHT, "action_face_in"],
                      unknown_ids={"action_face_in"})
    lst = dlg.findChild(QListWidget)

    assert lst.item(0).text() == \
        f"[action_face_in] ({_t('call_mapping_picker_unknown')})"
    assert dlg.selected_entity_ids() == ["action_face_in", CHASE_RIGHT]


def test_verwaiste_figur_bleibt_immer_ganz_oben(make_picker):
    legacy = "call_legacy_figure"
    dlg = make_picker(selected=[legacy])
    lst = dlg.findChild(QListWidget)

    assert lst.item(0).text() == f"[{legacy}]"

    _haken_umschalten(dlg, "Chase Right  [Plus]")   # regulaer anhaken
    assert lst.item(0).text() == f"[{legacy}]"       # verwaiste bleibt oben

    _haken_umschalten(dlg, f"[{legacy}]")             # verwaiste abhaken
    assert lst.item(0).text() == f"[{legacy}]"        # bleibt trotzdem ganz oben (tier 0)
    assert dlg.selected_entity_ids() == [CHASE_RIGHT]


def test_resort_waehrend_suchfilter_aktiv_behaelt_ausgeblendete(make_picker):
    dlg = make_picker(selected=[CHASE_RIGHT])
    lst = dlg.findChild(QListWidget)

    dlg.set_search_text("allemande")
    _haken_umschalten(dlg, "Allemande Thar  [Mainstream]")

    # Chase Right bleibt ausgeblendet, obwohl sich die Reihenfolge geaendert hat
    assert lst.findItems("Chase Right  [Plus]", Qt.MatchExactly)[0].isHidden()
    assert lst.findItems("(Anything) & Roll  [Plus]", Qt.MatchExactly)[0].isHidden()
    assert dlg.visible_entity_ids() == [ALLEMANDE_THAR, ALLEMANDE_RIGHT]

    dlg.set_search_text("")
    assert dlg.visible_entity_ids() == [
        ALLEMANDE_THAR, CHASE_RIGHT, ALLEMANDE_RIGHT, ANYTHING_AND_ROLL]


def test_mehrere_haken_folgen_teaching_order_nicht_klick_reihenfolge(make_picker):
    dlg = make_picker()   # nichts vorausgewaehlt
    lst = dlg.findChild(QListWidget)

    # Absichtlich in "falscher" Reihenfolge anklicken: zuerst Chase Right,
    # dann Allemande Thar -> Block soll trotzdem Listen-/Teaching-Order zeigen
    _haken_umschalten(dlg, "Chase Right  [Plus]")
    _haken_umschalten(dlg, "Allemande Thar  [Mainstream]")

    assert [lst.item(i).text() for i in range(2)] == [
        "Allemande Thar  [Mainstream]", "Chase Right  [Plus]"]


def test_duplikat_ueber_zwei_programme_bleibt_beim_sortieren_benachbart(make_picker):
    entities = ENTITIES + [("Chase Right  [Plus (2026)]", CHASE_RIGHT)]
    dlg = make_picker(entities=entities)
    lst = dlg.findChild(QListWidget)

    _haken_umschalten(dlg, "Chase Right  [Plus (2026)]")

    assert [lst.item(i).text() for i in range(2)] == [
        "Chase Right  [Plus]", "Chase Right  [Plus (2026)]"]


# ---------------------------------------------------- Call-Mapping-Dialog ----

MENGE = "Chase Right & Roll"          # beim Oeffnen schon mit zwei Figuren
KOMMA = "Allemande Thar, Chase Right"  # Kandidat fuer den Split-Weg


@pytest.fixture
def db(tmp_path):
    from song_db import SongDatabase

    d = SongDatabase(str(tmp_path / "t.db"))
    d.insert_sequence([MENGE, "Allemande Thar", "Chase Right"])
    d.insert_sequence([KOMMA])
    d.set_call_text_figures(MENGE, [CHASE_RIGHT, ANYTHING_AND_ROLL])
    yield d
    d.close()


def _warte_bis(bedingung, timeout_s=15.0):
    ende = time.monotonic() + timeout_s
    while not bedingung():
        assert time.monotonic() < ende, "Zeitueberschreitung"
        QApplication.processEvents()
        time.sleep(0.01)


def _zelle(table, call_text):
    """Figur-Zelle (Spalte 2) zur Zeile des Call-Texts — ueber das Item, weil
    die sortierte Tabelle Zeilen verschiebt."""
    treffer = [it for it in table.findItems(call_text, Qt.MatchExactly)
               if it.column() == 0]
    return table.item(treffer[0].row(), 2) if treffer else None


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
    (knopf,) = _knoepfe(dlg, _t(key))
    knopf.click()


@pytest.fixture
def mapping(qapp, db, monkeypatch):
    import sequences_widget

    monkeypatch.setattr(sequences_widget.QMessageBox, "information",
                        lambda *a, **k: None)
    dlg = sequences_widget.CallMappingDialog(db)
    dlg.show()
    table = dlg.findChild(QTableWidget)
    # Geladen, und der Auto-Vorschlag fuer "Allemande Thar" steht in der Zelle
    _warte_bis(lambda: _zelle(table, "Allemande Thar") is not None
               and _zelle(table, "Allemande Thar").text().startswith("Allemande Thar"))
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


def test_mapping_zeigt_die_menge_mit_mehrfach_markierung(mapping):
    dlg, table = mapping
    _filter(dlg, "all")

    text = _zelle(table, MENGE).text()
    assert "+1" in text
    assert "Chase Right" in text
    assert "(Anything) & Roll" in text


def test_mapping_doppelklick_oeffnet_picker_und_speichert_die_menge(
        mapping, picker_double, db):
    dlg, table = mapping
    aufrufe, antwort = picker_double
    _filter(dlg, "all")
    antwort["ids"] = [ALLEMANDE_THAR, ANYTHING_AND_ROLL]

    _doppelklick(table, _zelle(table, MENGE))

    (aufruf,) = aufrufe
    assert aufruf["selected"] == [CHASE_RIGHT, ANYTHING_AND_ROLL]
    assert aufruf["allow_split"] is True
    ids = [eid for _label, eid in aufruf["entities"]]
    assert CHASE_RIGHT in ids
    assert None not in ids
    assert "__SPLIT_COMMA__" not in ids
    text = _zelle(table, MENGE).text()
    assert "+1" in text
    assert "Allemande Thar" in text

    _klick(dlg, "call_mapping_save")

    # 39.0012 (Anything & Roll) liegt hoeher als 29.005301 (Allemande Thar)
    assert db.get_call_text_figures(MENGE) == [ANYTHING_AND_ROLL, ALLEMANDE_THAR]


def test_mapping_ohne_haken_entfernt_die_zuordnung(mapping, picker_double, db):
    dlg, table = mapping
    _aufrufe, antwort = picker_double
    _filter(dlg, "all")
    antwort["ids"] = []

    _doppelklick(table, _zelle(table, MENGE))
    _klick(dlg, "call_mapping_save")

    assert db.get_call_text_figures(MENGE) == []


def test_mapping_split_im_picker_teilt_beim_speichern(mapping, picker_double, db):
    dlg, table = mapping
    _aufrufe, antwort = picker_double
    antwort["split"] = True

    _doppelklick(table, _zelle(table, KOMMA))
    assert _zelle(table, KOMMA).text() == _t("call_mapping_split")
    _klick(dlg, "call_mapping_save")

    assert db.get_sequence_ids_with_call_text(KOMMA) == []
    assert db.get_call_text_figures(KOMMA) == []


def test_mapping_auto_vorschlag_gilt_beim_speichern_nicht_als_aenderung(mapping, db):
    dlg, _table = mapping

    _klick(dlg, "call_mapping_save")

    assert db.get_call_text_figures("Allemande Thar") == []
    assert db.get_call_text_figures(MENGE) == [CHASE_RIGHT, ANYTHING_AND_ROLL]


def test_mapping_f2_auf_call_text_spalte_oeffnet_trotzdem_den_picker(
        mapping, picker_double):
    # Regression intern#73: Zeile per Klick auf Spalte 0 (Call-Text)
    # markieren, dann F2 -> currentIndex() behaelt Spalte 0, der Picker
    # muss trotzdem aufgehen (wie beim Doppelklick auf die Figur-Zelle).
    dlg, table = mapping
    aufrufe, antwort = picker_double
    _filter(dlg, "all")
    antwort["ids"] = [ALLEMANDE_THAR, ANYTHING_AND_ROLL]
    zelle0 = [it for it in table.findItems(MENGE, Qt.MatchExactly)
              if it.column() == 0][0]

    table.scrollToItem(zelle0)
    pos = table.visualItemRect(zelle0).center()
    QTest.mouseClick(table.viewport(), Qt.LeftButton, Qt.NoModifier, pos)
    table.setFocus()
    QTest.keyClick(table, Qt.Key_F2)

    (aufruf,) = aufrufe
    assert aufruf["selected"] == [CHASE_RIGHT, ANYTHING_AND_ROLL]


def test_mapping_bestaetigen_schreibt_die_auswahl_der_zeilen(
        mapping, picker_double, db):
    dlg, table = mapping
    _aufrufe, antwort = picker_double
    antwort["ids"] = [CHASE_RIGHT, ANYTHING_AND_ROLL]
    _doppelklick(table, _zelle(table, "Chase Right"))   # Menge statt Vorschlag

    table.clearSelection()
    for text in ("Allemande Thar", "Chase Right"):
        table.selectionModel().select(
            table.model().index(_zelle(table, text).row(), 0),
            QItemSelectionModel.Select | QItemSelectionModel.Rows)
    _klick(dlg, "call_mapping_confirm_selected")

    assert db.get_call_text_figures("Allemande Thar") == [ALLEMANDE_THAR]
    assert db.get_call_text_figures("Chase Right") == [CHASE_RIGHT, ANYTHING_AND_ROLL]
    # Filter "Nicht gemappt": bestaetigte Zeilen fallen ohne Voll-Reload weg
    assert _zelle(table, "Allemande Thar") is None
    assert _zelle(table, "Chase Right") is None
    assert _zelle(table, KOMMA) is not None


def test_mapping_entity_liste_hat_jede_figur_nur_einmal(mapping, picker_double):
    # intern#87: teaching_order_calls fuehrt eine entity_id je Band (Chase Right
    # in Plus UND Plus (2026)). Die an den Picker uebergebene Figuren-Liste muss
    # jede entity_id trotzdem nur EINMAL enthalten, Label ohne [Programm]-Suffix.
    dlg, table = mapping
    aufrufe, _antwort = picker_double
    _filter(dlg, "all")   # MENGE ist gemappt -> nur unter "Alle" sichtbar
    _doppelklick(table, _zelle(table, MENGE))

    (aufruf,) = aufrufe
    eids = [eid for _label, eid in aufruf["entities"]]
    assert eids.count(CHASE_RIGHT) == 1
    assert len(eids) == len(set(eids))                 # keine Dubletten
    labels = [label for label, _eid in aufruf["entities"]]
    assert all("[" not in label for label in labels)   # kein [Programm]-Label


def test_picker_entities_helper_dedupliziert_und_nimmt_niedrigstes_band():
    # intern#87: gemeinsame Dedup-Funktion beider Picker-Einstiege (Call-Mapping
    # UND Sequenz-Editor). to_calls kommt aufsteigend nach teaching_order; eine
    # entity_id in mehreren Baendern darf nur einmal erscheinen (niedrigstes Band),
    # Separatoren ("-- .. --") gehoeren nicht in die Figuren-Liste.
    from sequences_widget import picker_entities_from_to_calls

    to_calls = [
        ("call_recycle", "Recycle", 29.01, "Mainstream"),
        ("call_recycle", "Recycle", 30.01, "Mainstream (2026)"),  # weiteres Band
        ("--basic1", "-- Basic 1 --", 10.0, None),                # Separator
        ("call_chase_right", "Chase Right", 39.03, "Plus"),
    ]
    entity_list, eid_to_label, eid_min_to = picker_entities_from_to_calls(to_calls)

    assert entity_list == [("Recycle", "call_recycle"),
                           ("Chase Right", "call_chase_right")]   # Separator raus, dedup
    assert eid_min_to["call_recycle"] == 29.01                    # niedrigstes Band
    assert eid_to_label["--basic1"] == "-- Basic 1 --"           # Label inkl. Separator
