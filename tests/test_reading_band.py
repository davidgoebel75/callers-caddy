"""Lesebalken und Leseposition (intern#76).

Der Lesebalken liegt auf dem Text, der gerade zu singen ist. "Textsprung timen"
(intern#115) verschiebt nur den Scroll, nicht den Balken. Die Leseposition
(lyrics/reading_position_pct, 0 % = oben, 100 % = unten) gilt mit und ohne
SyncPoints. Werte stehen im Abschnitt [lyrics] der INI.
"""
import pytest
from PySide6.QtCore import QSettings, Qt

from lyrics_widget import LyricsWidget

DUR = 180.0
ANCHOR_SEC = 60.0
ANCHOR_LINE = 100


@pytest.fixture
def ini(tmp_path):
    return QSettings(str(tmp_path / "w.ini"), QSettings.IniFormat)


@pytest.fixture
def widget(qapp, ini):
    from path_manager import PathManager
    w = LyricsWidget(PathManager(ini))
    w.resize(400, 300)
    w._browser.setPlainText("\n".join(f"Zeile {i}" for i in range(200)))
    w._lyrics_loaded = True
    w.show()
    qapp.processEvents()
    assert w._browser.verticalScrollBar().maximum() > 0
    yield w
    w.deleteLater()


def _with_anchor(w):
    block = w._browser.document().findBlockByNumber(ANCHOR_LINE)
    w._active_anchors = lambda: [(ANCHOR_SEC, block.position())]
    return w._anchor_doc_points()[0][1]      # Dokument-Y der Ankerzeile


def _band_center_on_screen(w):
    rect = w._reading_band.band_rect()
    assert rect is not None
    return rect.center().y()


def test_standardwerte(widget):
    assert widget._SYNC_ANCHOR_VIEWPORT_FRAC == pytest.approx(0.30)
    assert widget._reading_band_enabled is True
    assert widget._reading_band_height_pct == 12
    assert widget._reading_band_opacity_pct == 30


def test_einstellungen_werden_gelesen_und_begrenzt(widget, ini):
    ini.setValue("lyrics/reading_position_pct", "250")
    ini.setValue("lyrics/reading_band_enabled", "false")
    ini.setValue("lyrics/reading_band_height", "abc")
    ini.setValue("lyrics/reading_band_opacity", "55")
    widget.reload_reading_settings()
    assert widget._SYNC_ANCHOR_VIEWPORT_FRAC == 1.0
    assert widget._reading_band_enabled is False
    assert widget._reading_band_height_pct == 12      # unlesbar -> Standard
    assert widget._reading_band_opacity_pct == 55


def test_am_syncpoint_steht_der_balken_auf_der_leseposition(widget):
    y_anchor = _with_anchor(widget)
    widget._text_jump_offset = 0
    widget.update_scroll(ANCHOR_SEC, DUR)
    assert widget._band_doc_y == y_anchor
    assert abs(_band_center_on_screen(widget) - widget._read_offset()) <= 2


def test_textsprung_verschiebt_nur_den_scroll_nicht_den_balken(widget):
    y_anchor = _with_anchor(widget)
    widget._text_jump_offset = -4
    widget.update_scroll(ANCHOR_SEC, DUR)
    # Balken liegt weiter auf dem gesungenen Text ...
    assert widget._band_doc_y == y_anchor
    # ... der Scroll ist schon weiter, also steht der Balken ueber der Leseposition
    assert _band_center_on_screen(widget) < widget._read_offset() - 2


def test_ohne_syncpoints_steht_der_gesungene_text_auf_der_leseposition(widget):
    widget._active_anchors = lambda: []
    widget.update_scroll(DUR / 2, DUR)
    doc_h = widget._browser.document().size().height()
    assert widget._band_doc_y == int(doc_h / 2)
    assert abs(_band_center_on_screen(widget) - widget._read_offset()) <= 2


def test_leseposition_wirkt_auf_den_scroll(widget, ini):
    y_anchor = _with_anchor(widget)
    widget._text_jump_offset = 0
    ini.setValue("lyrics/reading_position_pct", "50")
    widget.reload_reading_settings()
    widget.update_scroll(ANCHOR_SEC, DUR)
    bar = widget._browser.verticalScrollBar()
    half = widget._browser.viewport().height() // 2
    assert abs((y_anchor - bar.value()) - half) <= 2


def test_ausgeschaltet_im_syncpoint_und_edit_modus_kein_balken(widget):
    _with_anchor(widget)
    widget.update_scroll(ANCHOR_SEC, DUR)
    assert widget._reading_band.band_rect() is not None
    widget._sync_mode = True
    assert widget._reading_band.band_rect() is None
    widget._sync_mode = False
    widget._edit_mode = True
    assert widget._reading_band.band_rect() is None
    widget._edit_mode = False
    widget._reading_band_enabled = False
    assert widget._reading_band.band_rect() is None


def test_balken_laesst_mausereignisse_durch(widget):
    assert widget._reading_band.testAttribute(
        Qt.WidgetAttribute.WA_TransparentForMouseEvents)


def test_balkenhoehe_in_prozent_der_fensterhoehe(widget):
    _with_anchor(widget)
    widget.update_scroll(ANCHOR_SEC, DUR)
    widget._reading_band_height_pct = 20
    h = widget._reading_band.height()
    assert widget._reading_band.band_rect().height() == int(h * 0.20)
