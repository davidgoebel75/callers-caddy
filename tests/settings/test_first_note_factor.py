"""Erste-Notiz-Faktor aus dem Einstellungsdialog (intern#198).

Wer den Faktor im Dialog aendert, will ihn sofort sehen - und nach dem
Neustart wiederfinden. Bisher kam der neue Wert nicht im Notizen-Widget an,
und beim Beenden schrieb _save_layout() den alten Wert des Widgets zurueck.
"""
from types import SimpleNamespace

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QMainWindow

import main
from notes_widget import NotesWidget


class _FakeDB:
    def get_notes(self, *args, **kwargs):
        return []


def _window(tmp_path):
    win = QMainWindow()
    win._settings = QSettings(str(tmp_path / "t.ini"), QSettings.IniFormat)
    win.notes_widget = NotesWidget(_FakeDB())
    return win


def test_neuer_faktor_wirkt_sofort(qapp, tmp_path):
    win = _window(tmp_path)
    win._settings.setValue("notes/first_note_factor", "2.5")
    main.P29MainWindow._on_settings_applied(win, ["notes/first_note_factor"])
    assert win.notes_widget._first_note_factor == 2.5


def test_beenden_ueberschreibt_den_faktor_nicht(qapp, tmp_path):
    """Die INI kennt den Faktor nur aus dem Dialog; das Widget hat keine
    eigene Bedienung dafuer. _save_layout() darf ihn nicht zurueckschreiben."""
    win = _window(tmp_path)
    win._settings.setValue("notes/first_note_factor", "2.5")   # Widget noch 4.0
    win.sequences_widget = SimpleNamespace(_zoom_pct=100)
    win.lyrics_widget = SimpleNamespace(
        _current_font_size=20, _base_font_size=20,
        _auto_size_enabled=True, _auto_width_enabled=False)
    win._raised_tab_docknames = lambda: []
    win._save_float_geoms = lambda settings: None
    main.P29MainWindow._save_layout(win)
    assert win._settings.value("notes/first_note_factor") == "2.5"
