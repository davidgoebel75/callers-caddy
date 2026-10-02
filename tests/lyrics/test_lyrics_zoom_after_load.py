"""Zoom direkt nach dem Laden (intern#152).

Auch mit Auto-Breite/Auto-Size muss das frisch geladene Dokument SOFORT zum
aktuellen Zoom passen, nicht erst nach dem verzoegerten Auto-Fit. Sonst rechnet
Dynamic Lyrics (wird direkt nach dem Laden wieder eingeschaltet) einen falschen
Zoom-Faktor heraus: Der Fliesstext schrumpft, Ueberschriften ohne eigene
Schriftgroesse wirken riesig.
"""
import pytest
from PySide6.QtCore import QSettings

from lyrics_widget import LyricsWidget

HTML = ("<html><body><h1>OPENER</h1>"
        "<p><span style='font-size:10pt'>Circle left</span></p></body></html>")


@pytest.fixture
def widget(qapp, tmp_path):
    from path_manager import PathManager
    ini = QSettings(str(tmp_path / "w.ini"), QSettings.IniFormat)
    w = LyricsWidget(PathManager(ini))
    w.resize(400, 300)
    w.show()
    qapp.processEvents()
    yield w
    w.deleteLater()


def _inline_pt(w):
    doc = w._browser.document()
    block = doc.begin()
    while block.isValid():
        it = block.begin()
        while not it.atEnd():
            pt = it.fragment().charFormat().fontPointSize()
            if pt > 0:
                return pt
            it += 1
        block = block.next()
    return None


@pytest.mark.parametrize("auto_width", [True, False])
def test_dokument_passt_sofort_zum_aktuellen_zoom(widget, tmp_path, auto_width):
    w = widget
    w._btn_auto_size.setChecked(False)
    w._btn_auto_width.setChecked(auto_width)
    w._current_font_size = w._base_font_size * 2
    f = tmp_path / "song.htm"
    f.write_text(HTML, encoding="utf-8")

    w._load_file(str(f), f.name)

    # Vor jedem Auto-Fit: Inline-Groesse = Original x aktueller Faktor
    assert _inline_pt(w) == pytest.approx(20.0)


# ---------------------------------------------------------------------------
# Edit-Modus: Words Stylesheet in <!-- --> muss wirken (intern#152)
# ---------------------------------------------------------------------------

def test_word_stylesheet_in_kommentar_wirkt(qapp):
    from PySide6.QtGui import QTextDocument
    raw = ("<html><head><style>\n<!--\nh1\n\t{font-size:10.0pt;color:brown;}\n-->\n"
           "</style></head><body><h1>OPENER</h1></body></html>")
    doc = QTextDocument()
    doc.setHtml(LyricsWidget._unwrap_style_comments(raw))
    fmt = doc.begin().begin().fragment().charFormat()
    assert fmt.fontPointSize() == pytest.approx(10.0)


def test_kommentare_ausserhalb_von_style_bleiben():
    html = "<!-- Kopf --><style><!-- p{} --></style><p><!-- x -->a</p>"
    out = LyricsWidget._unwrap_style_comments(html)
    assert out == "<!-- Kopf --><style> p{} </style><p><!-- x -->a</p>"


def test_ueberschrift_ohne_eigene_groesse_wie_text(widget, tmp_path):
    """h1-h6 ohne Groessenangabe: so gross wie der Text (Default-Stylesheet)."""
    w = widget
    w._btn_auto_size.setChecked(False)
    w._btn_auto_width.setChecked(False)
    f = tmp_path / "song.htm"
    f.write_text("<html><body><h1>OPENER</h1><p>Circle left</p></body></html>",
                 encoding="utf-8")
    w._load_file(str(f), f.name)
    doc = w._browser.document()
    h1, p = doc.begin(), doc.begin().next()
    assert h1.charFormat().font().pointSizeF() == pytest.approx(
        p.charFormat().font().pointSizeF())


def test_bearbeiten_zeigt_100_prozent_und_sperrt_zoom(widget, tmp_path):
    w = widget
    w._btn_auto_size.setChecked(False)
    w._btn_auto_width.setChecked(False)
    w._current_font_size = w._base_font_size * 2
    f = tmp_path / "song.htm"
    f.write_text(HTML, encoding="utf-8")
    w._load_file(str(f), f.name)
    w._current_path = str(f)  # setzt sonst load_song

    w._enter_edit_mode()
    assert w._edit_mode
    assert w._label_zoom.text() == "100%"
    assert _inline_pt(w) == pytest.approx(10.0)
    assert not w._btn_zoom_in.isEnabled()
    assert not w._btn_auto_width.isEnabled()
    w._on_zoom_in()  # gesperrt per Button; direkt aufgerufen bleibt es 100 %
    assert w._label_zoom.text() == "100%"

    w._leave_edit_mode_silent()
    assert not w._edit_mode
    assert w._label_zoom.text() == f"{round(w._current_font_size / w._base_font_size * 100)}%"
    assert w._btn_zoom_in.isEnabled()
    assert w._btn_auto_width.isEnabled()
