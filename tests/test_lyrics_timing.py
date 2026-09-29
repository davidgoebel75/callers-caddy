"""Timing-Parameter fuer Lyrics (intern#115).

"Textsprung timen" (lyrics/text_jump_offset) verschiebt, wann der Auto-Scroll
eine SyncPoint-Zeile erreicht. "Texttausch timen" (lyrics/dynamic_swap_offset)
verschiebt die Figuren-Grenzen von Dynamic Lyrics (Sequenzwechsel und
Heads/Sides-Tausch). Negative Werte = frueher. Die gespeicherten SyncPoints
bleiben unveraendert.
"""
import pytest
from PySide6.QtCore import QSettings

from lyrics_widget import LyricsWidget

L = LyricsWidget


class _Stub:
    _dynamic_current_part = L._dynamic_current_part
    reload_timing_settings = L.reload_timing_settings
    _TIMING_OFFSET_LIMIT = L._TIMING_OFFSET_LIMIT

    def __init__(self, settings=None):
        self._settings = settings
        self._dyn_part_starts = [0.0, 30.0, 60.0, 90.0]
        self._dynamic_swap_offset = 0
        self._text_jump_offset = 0


def test_ohne_offset_wechselt_der_teil_am_syncpoint():
    s = _Stub()
    assert s._dynamic_current_part(29.0) == 0
    assert s._dynamic_current_part(30.0) == 1


def test_negativer_tausch_offset_wechselt_frueher():
    s = _Stub()
    s._dynamic_swap_offset = -2
    assert s._dynamic_current_part(27.9) == 0
    assert s._dynamic_current_part(28.0) == 1


def test_positiver_tausch_offset_wechselt_spaeter():
    s = _Stub()
    s._dynamic_swap_offset = 3
    assert s._dynamic_current_part(32.9) == 0
    assert s._dynamic_current_part(33.0) == 1


def test_einstellungen_werden_gelesen_und_begrenzt(tmp_path):
    ini = QSettings(str(tmp_path / "t.ini"), QSettings.IniFormat)
    ini.setValue("lyrics/text_jump_offset", "-2")
    ini.setValue("lyrics/dynamic_swap_offset", "99")
    s = _Stub(ini)
    s.reload_timing_settings()
    assert s._text_jump_offset == -2
    assert s._dynamic_swap_offset == 10


def test_kaputter_wert_gilt_als_null(tmp_path):
    ini = QSettings(str(tmp_path / "t.ini"), QSettings.IniFormat)
    ini.setValue("lyrics/text_jump_offset", "abc")
    s = _Stub(ini)
    s._text_jump_offset = 5
    s.reload_timing_settings()
    assert s._text_jump_offset == 0


# ---------------------------------------------------------------------------
# Auto-Scroll: SyncPoint-Zeile wird um den Offset frueher/spaeter erreicht
# ---------------------------------------------------------------------------

@pytest.fixture
def widget(qapp, tmp_path):
    from path_manager import PathManager
    ini = QSettings(str(tmp_path / "w.ini"), QSettings.IniFormat)
    w = LyricsWidget(PathManager(ini))
    w.resize(400, 300)
    w._browser.setPlainText("\n".join(f"Zeile {i}" for i in range(200)))
    w._lyrics_loaded = True
    w.show()
    qapp.processEvents()
    assert w._browser.verticalScrollBar().maximum() > 0
    yield w
    w.deleteLater()


def _ziel(w, pos, anker_zeile=100, anker_sek=60.0, dur=180.0):
    """Scroll-Ziel bei pos mit einem SyncPoint auf anker_zeile."""
    block = w._browser.document().findBlockByNumber(anker_zeile)
    w._active_anchors = lambda: [(anker_sek, block.position())]
    max_val = w._browser.verticalScrollBar().maximum()
    return w._sync_scroll_target(pos, dur, max_val)


def test_textsprung_offset_erreicht_syncpoint_frueher(widget):
    am_syncpoint = _ziel(widget, 60.0)
    widget._text_jump_offset = -2
    assert _ziel(widget, 58.0) == am_syncpoint
    assert _ziel(widget, 60.0) > am_syncpoint


def test_textsprung_offset_vor_songanfang_wird_begrenzt(widget):
    widget._text_jump_offset = -10
    # Anker bei 3 s rutscht auf 0 s, nicht davor: kein Absturz, Ziel >= 0
    assert _ziel(widget, 1.0, anker_sek=3.0) >= 0
