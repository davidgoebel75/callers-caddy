"""SyncPoint und Textzeile (intern#171).

Ein SyncPoint, der nicht am Zeilenanfang steht, gehoert trotzdem zu seiner
Textzeile: Der Rechtsklick findet ihn, ein Linksklick setzt neue Punkte an den
Anfang der Textzeile, auch auf einer umbrochenen Folgezeile.
"""
from types import SimpleNamespace

import pytest
from PySide6.QtCore import QPointF, QSettings, Qt
from PySide6.QtGui import QTextCursor

import sync_point_lines
from lyrics_widget import LyricsWidget

TEXT = "Circle left\nHeads promenade\nSwing"   # Zeilen ab 0, 12, 28


@pytest.mark.parametrize("pos, span", [
    (0, (0, 11)),
    (5, (0, 11)),
    (11, (0, 11)),    # genau auf dem Umbruch: Zeile davor
    (12, (12, 27)),
    (30, (28, 33)),
    (99, (28, 33)),   # hinter dem Text: letzte Zeile
])
def test_textzeile_zur_position(pos, span):
    assert sync_point_lines.line_span(TEXT, pos) == span


def test_punkte_der_zeile_auch_mitten_und_am_ende():
    anchors = [[1.0, 0], [2.0, 12], [3.0, 20], [4.0, 27], [5.0, 28]]
    assert sync_point_lines.indices_in_span(anchors, 12, 27) == [1, 2, 3]
    assert sync_point_lines.indices_in_span(anchors, 0, 11) == [0]


# ---------------------------------------------------------------------------
# Im Lyric-Fenster: Klick auf eine Zeile mit Markern
# ---------------------------------------------------------------------------

LONG = " ".join(["allemande left and weave the ring"] * 6)
HTML = f"<html><body><p>Circle left</p><p>{LONG}</p><p>Swing</p></body></html>"
LONG_START = len("Circle left") + 1
LONG_END = LONG_START + len(LONG)


@pytest.fixture
def widget(qapp, tmp_path):
    from path_manager import PathManager
    ini = QSettings(str(tmp_path / "w.ini"), QSettings.IniFormat)
    w = LyricsWidget(PathManager(ini))
    w.resize(400, 300)
    w.show()
    w._btn_auto_size.setChecked(False)
    w._btn_auto_width.setChecked(False)
    f = tmp_path / "song.htm"
    f.write_text(HTML, encoding="utf-8")
    w._load_file(str(f), f.name)
    w._sync_mode = True
    qapp.processEvents()
    yield w
    w.deleteLater()


def _click(w, pristine_pos, button=Qt.LeftButton):
    """Klick-Ereignis auf das Zeichen an der pristine-Position."""
    cursor = QTextCursor(w._browser.document())
    cursor.setPosition(w._pristine_to_display(pristine_pos))
    pt = QPointF(w._browser.cursorRect(cursor).center())
    return SimpleNamespace(position=lambda: pt, button=lambda: button)


def _second_screen_line(w):
    """Pristine-Position auf der zweiten Bildschirmzeile der langen Textzeile."""
    cursor = QTextCursor(w._browser.document())
    cursor.setPosition(LONG_START)
    cursor.movePosition(QTextCursor.Down)
    cursor.movePosition(QTextCursor.StartOfLine)
    assert cursor.position() > LONG_START, "lange Zeile bricht nicht um"
    return cursor.position() + 3


def test_verrutschter_punkt_wird_in_seiner_zeile_gefunden(widget):
    w = widget
    w._sync_anchors = [[10.0, 0], [20.0, LONG_START + 40], [30.0, LONG_END]]
    w._render_sync_markers()

    start, end = w._line_span_at(_click(w, LONG_START + 5))

    assert (start, end) == (LONG_START, LONG_END)
    assert sync_point_lines.indices_in_span(w._sync_anchors, start, end) == [1, 2]


def test_linksklick_auf_folgezeile_setzt_punkt_an_textzeilenanfang(widget):
    w = widget
    w._sync_last_pos = 42.0

    w._handle_sync_click(_click(w, _second_screen_line(w)))

    assert w._sync_anchors == [[42.0, LONG_START]]
