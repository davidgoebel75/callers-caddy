"""Transport-Buttons: deaktivierte Icons in Skin-Farbe (intern#168).

Pause, Stop und Fade out sind deaktiviert, solange nichts laeuft. Ihr Icon
hatte dann ein Grau, das Qt selbst erzeugt und das in keiner skin.json steht.
Jetzt hat das deaktivierte Icon dieselbe Farbe wie der deaktivierte Text:
muted_text (skin.qss), bei Play text_dim (eigenes Stylesheet).
"""
import os

import pytest
from PySide6.QtCore import QSize
from PySide6.QtGui import QColor, QIcon

import player_widget
from skin_manager import SkinManager
from ui_helpers import _SVG_STOP, _make_icon

ROT = "#ff0000"
GRUEN = "#00ff00"


def _farben(icon, mode):
    """Alle deckenden Pixelfarben des Icons im angegebenen Zustand."""
    img = icon.pixmap(QSize(24, 24), mode).toImage()
    return {
        QColor(img.pixel(x, y)).name()
        for x in range(img.width()) for y in range(img.height())
        if QColor.fromRgba(img.pixel(x, y)).alpha() == 255
    }


def test_deaktiviertes_icon_in_eigener_farbe(qapp):
    icon = _make_icon(_SVG_STOP, ROT, GRUEN)
    assert _farben(icon, QIcon.Normal) == {ROT}
    assert _farben(icon, QIcon.Disabled) == {GRUEN}


def test_ohne_zweite_farbe_graut_qt_aus(qapp):
    # Ausgangslage des Fehlers: Qt erzeugt das Grau selbst.
    icon = _make_icon(_SVG_STOP, ROT)
    assert _farben(icon, QIcon.Disabled) - {ROT}


@pytest.fixture
def player(qapp):
    sm = SkinManager(os.path.dirname(player_widget.__file__))
    sm.load("default")
    sm._colors.update(button_text=ROT, muted_text=GRUEN, text_dim="#0000ff")
    w = player_widget.PlayerWidget(engine=None, paths=None, skin_mgr=sm)
    yield w
    w.close()
    w.deleteLater()


@pytest.mark.parametrize("name, farbe", [
    ("btn_pause", GRUEN), ("btn_stop", GRUEN), ("btn_fade", GRUEN),
    ("btn_play", "#0000ff"),
])
def test_transport_buttons_deaktiviert_in_skin_farbe(player, name, farbe):
    icon = getattr(player, name).icon()
    assert _farben(icon, QIcon.Normal) == {ROT}
    assert _farben(icon, QIcon.Disabled) == {farbe}
