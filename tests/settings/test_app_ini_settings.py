"""Einstellungen landen in der App-INI, nicht in einem nackten QSettings()
(intern#136). Ohne Organisation/Format zeigt QSettings() unter Windows in die
Registry: Werte aus der INI wirken dann nicht, gesetzte Werte gehen verloren.
"""
import pathlib
import re

from PySide6.QtCore import QSettings

SRC = pathlib.Path(__file__).resolve().parents[2] / "src"


def test_kein_nacktes_qsettings_im_code():
    treffer = []
    for py in SRC.glob("*.py"):
        for nr, zeile in enumerate(py.read_text(encoding="utf-8").splitlines(), 1):
            code = zeile.split("#", 1)[0]
            if re.search(r"\bQSettings\(\s*\)", code):
                treffer.append(f"{py.name}:{nr}")
    assert treffer == []


def test_lyrics_lesen_und_schreiben_die_app_ini(qapp, tmp_path):
    from path_manager import PathManager
    from lyrics_widget import LyricsWidget

    ini = QSettings(str(tmp_path / "t.ini"), QSettings.IniFormat)
    ini.setValue("lyrics/reading_position_pct", "40")  # intern#76
    w = LyricsWidget(PathManager(ini))
    assert w._SYNC_ANCHOR_VIEWPORT_FRAC == 0.4
    w._persist_dynamic_enabled(True)
    assert ini.value("lyrics/dynamic_enabled") in (True, "true")
    w.deleteLater()
