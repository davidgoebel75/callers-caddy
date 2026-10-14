"""Lyrics-Zoom, Auto-Size und Auto-Breite aus dem Einstellungsdialog (intern#204).

main.py rief lyrics_widget.set_zoom() auf, das LyricsWidget hatte die Methode
nicht; ein except Exception verschluckte den Fehler. Auto-Size und Auto-Breite
wurden gar nicht uebernommen. Beim Beenden ueberschrieb _save_layout() alle
drei mit dem Zustand des Fensters.
"""
import pytest
from PySide6.QtCore import QSettings

from lyrics_widget import LyricsWidget


@pytest.fixture
def widget(qapp, tmp_path, keep):
    from path_manager import PathManager
    ini = QSettings(str(tmp_path / "w.ini"), QSettings.IniFormat)
    return keep(LyricsWidget(PathManager(ini)))


@pytest.fixture
def ini(tmp_path):
    return QSettings(str(tmp_path / "t.ini"), QSettings.IniFormat)


def _pct(w):
    return round(w._current_font_size / w._base_font_size * 100)


def test_zoom_aus_dem_dialog_wirkt_wie_die_zoom_knoepfe(widget, ini):
    w = widget
    assert w._btn_auto_size.isChecked()
    ini.setValue("lyrics/zoom_pct", 150)

    w.apply_size_settings(ini, ["lyrics/zoom_pct"])

    assert _pct(w) == 150
    assert w._label_zoom.text() == "150%"
    assert not w._auto_size_enabled and not w._btn_auto_size.isChecked()
    assert ini.value("lyrics/auto_size", type=bool) is False


def test_auto_haken_im_selben_dialog_gewinnt_ueber_den_zoom(widget, ini):
    w = widget
    w._btn_auto_size.setChecked(False)
    ini.setValue("lyrics/zoom_pct", 150)
    ini.setValue("lyrics/auto_size", True)

    # Reihenfolge in changed_keys darf keine Rolle spielen
    w.apply_size_settings(ini, ["lyrics/auto_size", "lyrics/zoom_pct"])

    assert w._auto_size_enabled and w._btn_auto_size.isChecked()


def test_auto_breite_aus_dem_dialog_schaltet_auto_size_ab(widget, ini):
    w = widget
    ini.setValue("lyrics/auto_width", True)

    w.apply_size_settings(ini, ["lyrics/auto_width"])

    assert w._auto_width_enabled and w._btn_auto_width.isChecked()
    assert not w._auto_size_enabled
    assert ini.value("lyrics/auto_size", type=bool) is False
    assert ini.value("lyrics/auto_width", type=bool) is True


def test_beide_auto_haken_an_auto_breite_gewinnt(widget, ini):
    w = widget
    ini.setValue("lyrics/auto_size", True)
    ini.setValue("lyrics/auto_width", True)

    w.apply_size_settings(ini, ["lyrics/auto_width", "lyrics/auto_size"])

    assert w._auto_width_enabled and not w._auto_size_enabled


def test_andere_schluessel_aendern_nichts(widget, ini):
    w = widget
    before = w._current_font_size

    w.apply_size_settings(ini, ["lyrics/dynamic_enabled"])

    assert w._current_font_size == before and w._auto_size_enabled
    assert ini.allKeys() == []


def test_start_stellt_zoom_wieder_her_ohne_auto_abzuschalten(widget):
    w = widget
    w.apply_zoom_pct(130)
    assert _pct(w) == 130
    assert w._auto_size_enabled


def test_main_reicht_dialog_aenderungen_an_das_lyrics_fenster(widget, tmp_path):
    """Der Weg ueber _on_settings_applied, den der Dialog nimmt."""
    import main
    from PySide6.QtWidgets import QMainWindow

    win = QMainWindow()
    win._settings = QSettings(str(tmp_path / "m.ini"), QSettings.IniFormat)
    win.lyrics_widget = widget
    win._settings.setValue("lyrics/zoom_pct", 120)

    main.P29MainWindow._on_settings_applied(win, ["lyrics/zoom_pct"])

    assert _pct(widget) == 120
    win.deleteLater()
