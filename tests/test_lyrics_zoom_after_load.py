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
