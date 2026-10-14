"""Startwert fuer "Auch ausgeblendete Sequenzen anzeigen" (intern#205).

Die Funktion selbst bleibt wie in intern#119/#156. Neu ist nur der Schluessel
sequences/show_hidden_on_start: an -> die App startet mit eingeblendeten roten
Sequenzen. Umschalten in der Sitzung aendert den Startwert nicht.
"""
import types

import pytest
from PySide6.QtCore import QSettings, Qt

SWING_THRU = "call_swing_thru"
MAPPED = "Swing Thru"
UNMAPPED = "Heads Frobnicate"           # bewusst ohne Zuordnung
KEY = "sequences/show_hidden_on_start"


@pytest.fixture
def db(tmp_path, keep):
    from song_db import SongDatabase

    d = keep(SongDatabase(str(tmp_path / "t.db")))
    d.set_call_text_figures(MAPPED, [SWING_THRU], mapped_by="manual")
    d.ids = {"ok": d.insert_sequence([MAPPED]),
             "rot": d.insert_sequence([MAPPED, UNMAPPED])}
    d.recompute_sequence_max_to()
    return d


def _start(db, keep, tmp_path, value=None):
    """Startpfad wie main(): Widget mit Tanzprogramm-Wahl, dann _init_sequences."""
    import main
    from sequences_widget import SequencesWidget

    settings = QSettings(str(tmp_path / "t.ini"), QSettings.IniFormat)
    if value is not None:
        settings.setValue(KEY, value)
    w = keep(SequencesWidget(db, settings=settings))
    w.set_program_bands({20}, defer_load=True)
    win = types.SimpleNamespace(
        db=db, sequences_widget=w, _settings=settings,
        sequence_view_widget=types.SimpleNamespace(set_sequence=lambda *a: None))
    win._show_hidden_on_start = lambda: main.P29MainWindow._show_hidden_on_start(win)
    main.P29MainWindow._init_sequences(win)
    return w, settings, win


def _ids(w):
    t = w._table
    return {t.item(r, 0).data(Qt.UserRole) for r in range(t.rowCount())}


def test_standard_aus_rote_sequenz_bleibt_ausgeblendet(db, keep, tmp_path):
    w, _, _ = _start(db, keep, tmp_path)
    assert db.ids["ok"] in _ids(w)
    assert db.ids["rot"] not in _ids(w)


def test_startwert_an_zeigt_rote_sequenz(db, keep, tmp_path):
    w, _, _ = _start(db, keep, tmp_path, value=True)
    assert {db.ids["ok"], db.ids["rot"]} <= _ids(w)


def test_umschalten_in_der_sitzung_aendert_den_startwert_nicht(db, keep, tmp_path):
    w, settings, _ = _start(db, keep, tmp_path, value=True)
    w.hide_unmapped_sequences()
    assert db.ids["rot"] not in _ids(w)
    assert settings.value(KEY, type=bool) is True


def test_einstellung_im_dialog_standard_aus(qapp, tmp_path):
    from settings_dialog import SETTINGS_META, _RESTART_KEYS

    assert SETTINGS_META[KEY]["default"] is False
    assert KEY in _RESTART_KEYS


@pytest.mark.parametrize("value, sichtbar", [(True, True), (False, False)])
def test_bestaetigte_lokation_beim_start_behaelt_den_startwert(
        db, keep, tmp_path, monkeypatch, value, sichtbar):
    """Die Lokation bringt eine andere Tanzprogramm-Wahl mit. Das beendet das
    Einblenden wie jeder Programmwechsel - die Bestaetigung beim Start gehoert
    aber noch zum Start, also gilt danach wieder der Startwert."""
    import main
    from PySide6.QtWidgets import QMessageBox

    w, _, win = _start(db, keep, tmp_path, value=value)
    loc = types.SimpleNamespace(name="Club", schedule_list=[])
    win.session = types.SimpleNamespace(location=None)
    win.db = types.SimpleNamespace(find_locations_for_datetime=lambda _dt: [(loc, 1.0)])
    win._set_current_location = lambda _loc: w.set_program_bands({10, 20})
    win._confirm_startup_location = (
        lambda l: main.P29MainWindow._confirm_startup_location(win, l))
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Yes)

    main.P29MainWindow._auto_detect_location_on_startup(win)

    assert (db.ids["rot"] in _ids(w)) is sichtbar
    assert db.ids["ok"] in _ids(w)
