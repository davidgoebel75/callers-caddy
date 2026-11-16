"""Zeilenabstand der Notizen (intern#246).

Bisher war der Zeilenvorschub fest 90 % der Schrift-Pixelgroesse; Unterlaengen
und Akzente ragten in die Nachbarzeile. Jetzt ist 100 % die echte Zeilenhoehe
der Schrift (ascent + descent), einstellbar 100-200 % ueber
notes/line_spacing_pct.
"""
import pytest
from PySide6.QtCore import QSettings
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QMainWindow

import main
from notes_widget import NotesWidget, _TightLabel
from settings_dialog import SettingsDialog


class _FakeDB:
    def get_notes(self, *args, **kwargs):
        return []


@pytest.fixture(autouse=True)
def _reset_spacing():
    yield
    _TightLabel.line_spacing_pct = 100


def _label(keep, px):
    lbl = keep(_TightLabel("x"))
    f = QFont()
    f.setPixelSize(px)
    lbl.setFont(f)
    return lbl


@pytest.mark.parametrize("px", [14, 28, 56])
def test_zeilen_ueberlappen_nicht(keep, px):
    lbl = _label(keep, px)
    fm = lbl.fontMetrics()
    assert lbl._tight_line_height() >= fm.ascent() + fm.descent()


def test_zeilenabstand_vergroessert_die_zeile(keep):
    lbl = _label(keep, 28)
    normal = lbl._tight_line_height()
    _TightLabel.line_spacing_pct = 150
    assert lbl._tight_line_height() == round(normal * 1.5)


@pytest.mark.parametrize("pct, expected", [(50, 100), (150, 150), (500, 200), ("110.0", 110),
                                           ("kaputt", 100)])
def test_set_line_spacing_begrenzt(keep, pct, expected):
    keep(NotesWidget(_FakeDB())).set_line_spacing(pct)
    assert _TightLabel.line_spacing_pct == expected


def test_dialog_wert_wirkt_sofort(keep, tmp_path):
    win = keep(QMainWindow())
    win._settings = QSettings(str(tmp_path / "t.ini"), QSettings.IniFormat)
    win.notes_widget = keep(NotesWidget(_FakeDB()))
    dlg = keep(SettingsDialog(None, win._settings, on_apply=lambda keys:
                         main.P29MainWindow._on_settings_applied(win, keys)))
    dlg._populate_groups_deferred()
    row = next(r for r in dlg._rows if r.full_key == "notes/line_spacing_pct")
    row.widget.setValue(130)
    dlg._on_apply_btn()
    assert _TightLabel.line_spacing_pct == 130
