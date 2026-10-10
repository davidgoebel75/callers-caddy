"""Einfuegeposition neuer Notizen: Oben/Unten (intern#96).

Der knifflige Teil ist die Reihenfolge bei Mehrfach-Anlage: add_notes() dreht
die Liste bei "top" um, weil _append_note() dort jeweils oben einfuegt. Genau
dieses doppelte Umdrehen war der Bug aus dem Abendplaner — deshalb prueft der
Test die sichtbare Reihenfolge in der offenen Liste, nicht die Interna.
"""
import pytest

from notes_widget import NotesWidget, _NoteRow


class _FakeDB:
    """Minimal-DB — nur die Aufrufe, die beim Anlegen von Notizen fallen."""

    def __init__(self):
        self._next_id = 1
        self.saved_order = None

    def add_note(self, text, location_id, note_type="normal", sort_order=0):
        note_id = self._next_id
        self._next_id += 1
        return note_id

    def update_notes_order(self, orders):
        self.saved_order = list(orders)

    def get_notes(self, *args, **kwargs):
        return []


@pytest.fixture
def notes(qapp):
    widget = NotesWidget(_FakeDB())
    widget._location_id = 1   # sonst steigt add_note()/add_notes() sofort aus
    return widget


def _open_texts(widget) -> list:
    """Sichtbare Reihenfolge der offenen Notizen, oben -> unten."""
    return [r._text for r in widget._open_list.rows() if isinstance(r, _NoteRow)]


# ---- add_notes: Reihenfolge bleibt, egal wohin eingefuegt wird ------------

def test_add_notes_top_keeps_order(notes):
    notes.set_insert_position("top")
    notes.add_notes(["Tip 1", "Tip 2", "Tip 3"])
    assert _open_texts(notes) == ["Tip 1", "Tip 2", "Tip 3"]


def test_add_notes_bottom_keeps_order(notes):
    notes.set_insert_position("bottom")
    notes.add_notes(["Tip 1", "Tip 2", "Tip 3"])
    assert _open_texts(notes) == ["Tip 1", "Tip 2", "Tip 3"]


def test_add_notes_top_lands_above_existing(notes):
    notes.set_insert_position("top")
    notes.add_notes(["alt"])
    notes.add_notes(["neu 1", "neu 2"])
    assert _open_texts(notes) == ["neu 1", "neu 2", "alt"]


def test_add_notes_bottom_lands_below_existing(notes):
    notes.set_insert_position("bottom")
    notes.add_notes(["alt"])
    notes.add_notes(["neu 1", "neu 2"])
    assert _open_texts(notes) == ["alt", "neu 1", "neu 2"]


def test_add_notes_skips_empty_texts(notes):
    notes.add_notes(["a", "", None, "b"])
    assert _open_texts(notes) == ["a", "b"]


def test_add_notes_without_location_does_nothing(qapp):
    widget = NotesWidget(_FakeDB())
    widget.add_notes(["a", "b"])
    assert _open_texts(widget) == []


# ---- add_note: Einzelanlage folgt demselben Toggle ------------------------

def test_add_note_top_prepends(notes):
    notes.set_insert_position("top")
    notes.add_note("erste")
    notes.add_note("zweite")
    assert _open_texts(notes) == ["zweite", "erste"]


def test_add_note_bottom_appends(notes):
    notes.set_insert_position("bottom")
    notes.add_note("erste")
    notes.add_note("zweite")
    assert _open_texts(notes) == ["erste", "zweite"]


# ---- Mitte: ueber der obersten Trennzeile --------------------------------

def _type(widget, text):
    """Tippt einen Eintrag ins Eingabefeld (so entstehen auch Trennzeilen)."""
    widget._input.setText(text)
    widget._on_add_note()


def _open_layout(widget) -> list:
    """Offene Liste mit Trennzeilen als '---Text', oben -> unten."""
    return [("---" + r._label_text) if r.note_type == "separator" else r._text
            for r in widget._open_list.rows()]


def test_middle_inserts_above_topmost_separator(notes):
    notes.set_insert_position("bottom")
    for t in ("heute 1", "---Tag 2", "gestern", "---Tag 1", "vorgestern"):
        _type(notes, t)
    notes.set_insert_position("middle")
    notes.add_note("neu")
    assert _open_layout(notes) == [
        "heute 1", "neu", "---Tag 2", "gestern", "---Tag 1", "vorgestern"]


def test_middle_add_notes_keeps_order(notes):
    notes.set_insert_position("bottom")
    for t in ("oben", "---Linie", "unten"):
        _type(notes, t)
    notes.set_insert_position("middle")
    notes.add_notes(["Tip 1", "Tip 2", "Tip 3"])
    assert _open_layout(notes) == [
        "oben", "Tip 1", "Tip 2", "Tip 3", "---Linie", "unten"]


def test_middle_with_separator_on_top_inserts_at_top(notes):
    notes.set_insert_position("bottom")
    for t in ("---Linie", "unten"):
        _type(notes, t)
    notes.set_insert_position("middle")
    notes.add_note("neu")
    assert _open_layout(notes) == ["neu", "---Linie", "unten"]


def test_middle_without_separator_appends(notes):
    notes.set_insert_position("middle")
    notes.add_notes(["a", "b"])
    notes.add_note("c")
    assert _open_texts(notes) == ["a", "b", "c"]


# ---- Toggle-Zustand ------------------------------------------------------

def test_default_position_is_top(notes):
    assert notes._insert_position == "top"


def test_unknown_position_falls_back_to_default(notes):
    notes.set_insert_position("irgendwas")
    assert notes._insert_position == "top"


def test_toggle_cycles_top_middle_bottom(notes):
    notes.set_insert_position("top")
    notes._on_toggle_insert_position()
    assert notes._insert_position == "middle"
    notes._on_toggle_insert_position()
    assert notes._insert_position == "bottom"
    notes._on_toggle_insert_position()
    assert notes._insert_position == "top"


def test_toggle_gives_focus_to_input(notes):
    notes.show()
    notes.activateWindow()
    notes._btn_insert_pos.setFocus()
    notes._btn_insert_pos.click()
    assert notes.focusWidget() is notes._input


def test_toggle_updates_button_label(notes):
    notes.set_insert_position("top")
    top_label = notes._btn_insert_pos.text()
    notes._on_toggle_insert_position()
    assert notes._btn_insert_pos.text() != top_label


# ---- Kopplung Einstellungen <-> Widget -----------------------------------

def test_settings_dialog_offers_exactly_the_accepted_values(notes):
    """Der Dialog darf nur Werte anbieten, die set_insert_position auch annimmt.

    Der Dialog listet ausserdem nur INI-Keys (childKeys) — main.py saet den
    Default deshalb einmalig, sonst waere die Zeile unsichtbar.
    """
    from settings_dialog import SETTINGS_META, _SettingRow

    meta = SETTINGS_META["notes/insert_position"]
    # Die Auswahl baut _build_widget zur Laufzeit (i18n) — also die echte
    # Combobox fragen, nicht SETTINGS_META["choices"].
    combo = _SettingRow("notes", "insert_position", meta["default"]).widget
    offered = [combo.itemData(i) for i in range(combo.count())]
    assert offered
    assert meta["default"] in offered

    for value in offered:
        notes.set_insert_position(value)
        assert notes._insert_position == value
