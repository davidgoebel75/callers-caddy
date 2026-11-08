"""Grenzfaelle zu intern#197: Zoom mit Sync-Marken.

Eine Pruefregel fuer alle Faelle: Nach jedem Zoom-Weg haben
  (a) alle Marken-Zeichen keine eigene Schriftgroesse (sie folgen der
      Dokument-Schrift und sind damit einheitlich gross),
  (b) alle Textzeichen genau Originalgroesse x aktueller Zoom-Faktor
      (bzw. keine eigene Groesse, wenn die Datei dort keine hat).
Die Originalgroesse je Zeichen wird nach dem Laden OHNE Marken gemessen.
"""
import pytest
from PySide6.QtCore import QSettings

from lyrics_widget import LyricsWidget

# ---- Dokumentformen -------------------------------------------------------

ZEILEN_JE_SPAN = (
    "<html><body><h1 style='font-size:16pt'>OPENER, BREAK, ENDING</h1>"
    "<p><span style='font-size:10pt'>Heads square thru four</span></p>"
    "<p><span style='font-size:12pt'>Swing thru boys run</span></p>"
    "<p class='comment'><span style='font-size:9pt'>(repeat)</span></p>"
    "<h1 style='font-size:16pt'>FIGURE</h1>"
    "<p><span style='font-size:14pt'>Allemande left your corner</span></p>"
    "<p><span style='font-size:10pt'>Promenade her home</span></p>"
    "</body></html>")

# RTF-artig: EIN Block, EIN Span, Zeilen nur per <br> (Marken mitten im Span)
EIN_BLOCK = ("<html><body><p><span style='font-size:11pt'>"
             "Heads square thru<br>Swing thru<br>Boys run<br>Bend the line<br>"
             "Promenade</span></p></body></html>")

# Mehrere Spans in einer Zeile, Groessenwechsel mitten im Wort
GEMISCHT = ("<html><body><p><span style='font-size:10pt'>Sq</span>"
            "<span style='font-size:20pt'>uare</span> thru "
            "<span style='font-size:8pt'>four</span></p>"
            "<p>ohne eigene Groesse</p>"
            "<p><span style='font-size:13pt'>X</span></p></body></html>")

# Gar keine eigenen Groessen (_original_sizes leer)
OHNE_GROESSEN = ("<html><body><p>Heads square thru</p><p>Swing thru</p>"
                 "<p>Promenade</p></body></html>")

DOKUMENTE = {"zeilen_je_span": ZEILEN_JE_SPAN, "ein_block": EIN_BLOCK,
             "gemischt": GEMISCHT, "ohne_groessen": OHNE_GROESSEN}


# ---- Hilfen ----------------------------------------------------------------

def _laden(qapp, tmp_path, html, w_px=500, h_px=400):
    from path_manager import PathManager
    ini = QSettings(str(tmp_path / "w.ini"), QSettings.IniFormat)
    w = LyricsWidget(PathManager(ini))
    w.resize(w_px, h_px)
    w.show()
    qapp.processEvents()
    w._btn_auto_size.setChecked(False)
    w._btn_auto_width.setChecked(False)
    f = tmp_path / "song.htm"
    f.write_text(html, encoding="utf-8")
    w._load_file(str(f), f.name)
    w.set_zoom(100)
    qapp.processEvents()
    return w


def _zeichen(w):
    doc = w._browser.document()
    out = []
    bg = w._SYNC_MARKER_BG.lower()
    block = doc.begin()
    while block.isValid():
        it = block.begin()
        while not it.atEnd():
            frag = it.fragment()
            fmt = frag.charFormat()
            marke = fmt.background().color().name() == bg
            out.extend((ch, marke, fmt.fontPointSize()) for ch in frag.text())
            it += 1
        # Blocktrenner zaehlt als ein Zeichen in Dokument-Positionen
        out.append(("\n", False, None))
        block = block.next()
    return out


def _original_je_zeichen(w):
    """Originalgroesse je pristine-Zeichen (aus der Basis nach dem Laden)."""
    n = w._browser.document().characterCount()
    orig = [0.0] * (n + 1)
    for pos, length, pt in w._original_sizes:
        for i in range(pos, pos + length):
            orig[i] = pt
    return orig


def _faktor(w):
    return w._current_font_size / w._base_font_size


def _pruefen(w, orig):
    """Pruefregel (a) + (b)."""
    f = _faktor(w)
    pristine = 0
    fehler = []
    for ch, marke, pt in _zeichen(w):
        if pt is None:          # Blocktrenner
            pristine += 1
            continue
        if marke:
            if pt != 0:
                fehler.append(f"Marke {ch!r} hat eigene Groesse {pt}")
            continue
        soll = orig[pristine] * f
        if abs(pt - soll) > 1e-6:
            fehler.append(f"Text {ch!r}@{pristine}: {pt} statt {soll}")
        pristine += 1
    assert not fehler, "\n".join(fehler[:10])


def _anker(w, positionen):
    w._sync_anchors = [[3.0 + 7 * i, p] for i, p in enumerate(positionen)]
    w._sync_mode = True
    w._render_sync_markers()


def _alle_zeilenanfaenge(w):
    text = w._browser.document().toPlainText()
    pos = [0] + [i + 1 for i, c in enumerate(text) if c in "\n "]
    return [p for p in pos if p < len(text)]


ANKER_LAGEN = {
    "zeilenanfaenge": _alle_zeilenanfaenge,
    "nur_anfang": lambda w: [0],
    "letztes_zeichen": lambda w: [w._browser.document().characterCount() - 2],
    "jenseits_ende": lambda w: [0, w._browser.document().characterCount() + 50],
    "mitten_im_wort": lambda w: [1, 2, 5, 9],
    "dicht_an_dicht": lambda w: list(range(0, 12)),
    "doppelt": lambda w: [3, 3, 3, 0, 0],
}


@pytest.fixture(params=sorted(DOKUMENTE))
def dok(request):
    return DOKUMENTE[request.param]


@pytest.mark.parametrize("lage", sorted(ANKER_LAGEN))
@pytest.mark.parametrize("zoom", [25, 68, 100, 191, 400])
def test_pruefregel_direkter_zoom(qapp, tmp_path, keep, dok, lage, zoom):
    w = keep(_laden(qapp, tmp_path, dok))
    orig = _original_je_zeichen(w)
    _anker(w, ANKER_LAGEN[lage](w))
    w.set_zoom(zoom)
    _pruefen(w, orig)


@pytest.mark.parametrize("lage", ["zeilenanfaenge", "mitten_im_wort", "dicht_an_dicht"])
def test_pruefregel_zoom_zickzack(qapp, tmp_path, keep, dok, lage):
    """Viele Zoom-Schritte hintereinander: kein Aufschaukeln."""
    w = keep(_laden(qapp, tmp_path, dok))
    orig = _original_je_zeichen(w)
    _anker(w, ANKER_LAGEN[lage](w))
    for z in (68, 191, 30, 150, 68, 400, 68):
        w.set_zoom(z)
        _pruefen(w, orig)


def test_marken_neu_zeichnen_im_zoom(qapp, tmp_path, keep, dok):
    """Marken werden bei schon gezoomtem Dokument neu gezeichnet (z. B. neuer
    Sync Point gesetzt) und danach weiter gezoomt."""
    w = keep(_laden(qapp, tmp_path, dok))
    orig = _original_je_zeichen(w)
    w.set_zoom(68)
    _anker(w, _alle_zeilenanfaenge(w))
    _pruefen(w, orig)
    _anker(w, _alle_zeilenanfaenge(w)[::2])   # andere Anker, neu gezeichnet
    _pruefen(w, orig)
    w.set_zoom(191)
    _pruefen(w, orig)


def test_sync_aus_und_wieder_an(qapp, tmp_path, keep, dok):
    w = keep(_laden(qapp, tmp_path, dok))
    orig = _original_je_zeichen(w)
    _anker(w, _alle_zeilenanfaenge(w))
    w.set_zoom(68)
    w._sync_mode = False
    w._clear_sync_markers()
    _pruefen(w, orig)
    w.set_zoom(150)
    _pruefen(w, orig)
    w._sync_mode = True
    w._render_sync_markers()
    w.set_zoom(68)
    _pruefen(w, orig)


@pytest.mark.parametrize("modus", ["auto_size", "auto_width"])
@pytest.mark.parametrize("groesse", [(250, 150), (900, 900)])
def test_pruefregel_auto_fit(qapp, tmp_path, keep, dok, modus, groesse):
    """Auto-Size/Auto-Breite: die Fit-Schleife setzt viele Zwischengroessen,
    waehrend die Marken im Dokument stehen."""
    w = keep(_laden(qapp, tmp_path, dok, *groesse))
    orig = _original_je_zeichen(w)
    _anker(w, _alle_zeilenanfaenge(w))
    if modus == "auto_size":
        w._auto_size_enabled = True
        w._auto_fit_font_size()
    else:
        w._auto_width_enabled = True
        w.auto_fit_width()
    qapp.processEvents()
    _pruefen(w, orig)
    w.resize(groesse[0] // 2 + 100, groesse[1] // 2 + 100)  # Fenster aendern
    qapp.processEvents()
    if modus == "auto_size":
        w._auto_fit_font_size()
    else:
        w.auto_fit_width()
    _pruefen(w, orig)


def test_basis_neu_einsammeln_bei_zoom_mit_marken(qapp, tmp_path, keep, dok):
    """_recache_original_sizes_scaled bei gezoomtem Dokument MIT Marken
    (Dynamic-Lyrics-Weg) liefert dieselbe Basis wie nach dem Laden."""
    # Zeichen fuer Zeichen vergleichen: Marken mitten in einem Span teilen
    # ihn beim Einsammeln in Stuecke, die dieselben Zeichen abdecken.
    w = keep(_laden(qapp, tmp_path, dok))
    basis = _original_je_zeichen(w)
    _anker(w, _alle_zeilenanfaenge(w))
    w.set_zoom(68)
    w._recache_original_sizes_scaled(_faktor(w))
    neu = _original_je_zeichen(w)
    assert all(abs(a - b) < 1e-6 for a, b in zip(neu, basis))
    orig = basis
    w.set_zoom(191)                     # mit der neuen Basis weiterzoomen
    _pruefen(w, orig)
    w._sync_mode = False
    w._clear_sync_markers()
    w.set_zoom(68)
    _pruefen(w, orig)


def test_marken_text_bleibt_lesbar(qapp, tmp_path, keep):
    """Die Marken selbst (Zeittext) sind nach dem Zoom vollstaendig und
    unveraendert - kein Zeichen geht beim Teilen der Bereiche verloren."""
    w = keep(_laden(qapp, tmp_path, EIN_BLOCK))
    vor = w._browser.document().toPlainText()
    _anker(w, _alle_zeilenanfaenge(w))
    mit = w._browser.document().toPlainText()
    w.set_zoom(68)
    w.set_zoom(191)
    assert w._browser.document().toPlainText() == mit
    w._sync_mode = False
    w._clear_sync_markers()
    assert w._browser.document().toPlainText() == vor
