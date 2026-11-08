"""Sync-Marken behalten beim Zoomen eine einheitliche Groesse (intern#197).

Die Zoom-Skalierung merkt sich die Inline-Schriftgroessen der Datei in
Positionen OHNE Marken (_cache_original_sizes nach setHtml). Im Sync-Modus
stehen aber Marken im Dokument, die alle Folgepositionen verschieben. Ohne
Umrechnung trafen die gemerkten Bereiche deshalb teils Marken-Zeichen (die
eine fremde Groesse bekamen) und teils den falschen Liedtext - je weiter
hinten im Song, desto staerker verrutscht.
"""
import pytest
from PySide6.QtCore import QSettings

from lyrics_widget import LyricsWidget

ZEILEN = ["Heads square thru four", "Swing thru boys run",
          "Ferris wheel centers pass thru", "Allemande left your corner",
          "Do sa do and swing", "Promenade her home"]
HTML = ("<html><body><h1>OPENER, BREAK, ENDING</h1>"
        + "".join(f"<p><span style='font-size:{10 + i % 3 * 2}pt'>{z}</span></p>"
                  for i, z in enumerate(ZEILEN))
        + "</body></html>")


@pytest.fixture
def widget(qapp, tmp_path, keep):
    from path_manager import PathManager
    ini = QSettings(str(tmp_path / "w.ini"), QSettings.IniFormat)
    w = keep(LyricsWidget(PathManager(ini)))
    w.resize(500, 400)
    w.show()
    qapp.processEvents()
    w._btn_auto_size.setChecked(False)
    w._btn_auto_width.setChecked(False)
    f = tmp_path / "song.htm"
    f.write_text(HTML, encoding="utf-8")
    w._load_file(str(f), f.name)
    return w


def _zeichen(w):
    """[(zeichen, ist_marke, pointSize)] fuer das ganze Dokument."""
    doc = w._browser.document()
    out = []
    block = doc.begin()
    while block.isValid():
        it = block.begin()
        while not it.atEnd():
            frag = it.fragment()
            fmt = frag.charFormat()
            marke = fmt.background().color().name() == w._SYNC_MARKER_BG.lower()
            for ch in frag.text():
                out.append((ch, marke, fmt.fontPointSize()))
            it += 1
        block = block.next()
    return out


def _sync_an(w):
    doc = w._browser.document()
    # Anker an jedem Zeilenanfang (pristine-Positionen, wie aus der DB)
    positions = [doc.findBlockByNumber(n).position() for n in range(1, len(ZEILEN) + 1)]
    w._sync_anchors = [[4.0 + 10 * i, p] for i, p in enumerate(positions)]
    w._sync_mode = True
    w._render_sync_markers()


def _groessen_ohne_marken(w):
    return [(ch, pt) for ch, marke, pt in _zeichen(w) if not marke]


@pytest.mark.parametrize("zoom", [68, 100, 191])
def test_marken_einheitlich_nach_zoom(widget, zoom):
    w = widget
    _sync_an(w)
    w.set_zoom(zoom)
    marken_pt = {pt for _ch, marke, pt in _zeichen(w) if marke}
    assert len(marken_pt) == 1, f"Marken in verschiedenen Groessen: {marken_pt}"


@pytest.mark.parametrize("zoom", [68, 191])
def test_liedtext_groessen_wie_ohne_marken(widget, zoom):
    """Der Liedtext hat mit Marken genau die Groessen wie ohne Marken."""
    w = widget
    w.set_zoom(zoom)
    ohne = _groessen_ohne_marken(w)
    w.set_zoom(100)
    _sync_an(w)
    w.set_zoom(zoom)
    assert _groessen_ohne_marken(w) == ohne


def test_marken_weg_text_unveraendert(widget):
    """Nach Zoom mit Marken und Verlassen des Sync-Modus: wie nie markiert."""
    w = widget
    w.set_zoom(68)
    vorher = _groessen_ohne_marken(w)
    _sync_an(w)
    w.set_zoom(150)
    w.set_zoom(68)
    w._sync_mode = False
    w._clear_sync_markers()
    assert not any(marke for _c, marke, _p in _zeichen(w))
    assert _groessen_ohne_marken(w) == vorher


def test_groessen_einsammeln_mit_marken(widget):
    """Wird die Groessen-Basis neu eingesammelt, waehrend Marken stehen (z. B.
    Dynamic-Lyrics-Neuaufbau), bleiben Positionen ohne Marken die Basis."""
    w = widget
    ohne = list(w._original_sizes)
    _sync_an(w)
    w._cache_original_sizes()
    assert w._original_sizes == ohne
    w.set_zoom(68)
    assert len({pt for _c, marke, pt in _zeichen(w) if marke}) == 1
