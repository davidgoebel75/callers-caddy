"""To-Call-Widget bei Platzmangel (intern#114).

Frueher liefen die offenen Kacheln ueber ihre Zone hinaus in die Erledigt-Zone
(Ueberlappen) oder wurden unten abgeschnitten; bei wenig Hoehe warf
compute_cells einen TypeError. Jetzt: Erledigte stehen standardmaessig
eingeklappt als Leiste unter den offenen, offene Kacheln schrumpfen bis
_MIN_H, danach scrollt die Flaeche.
"""
import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

from button_grid import compute_cells, min_matrix_height
from to_call_widget import ToCallWidget


@pytest.fixture
def widget(qapp):
    def _make(n, erledigt, w, h):
        tc = ToCallWidget()
        tc.resize(w, h)
        tc.show()                      # sonst hat der Viewport keine Groesse
        erzeugt.append(tc)
        tc.fill([(f"e{i}", f"Call Nummer {i}") for i in range(n)])
        for tile in tc._tiles[:erledigt]:
            QTest.mouseClick(tile, Qt.LeftButton)
        qapp.processEvents()
        return tc
    erzeugt = []
    yield _make
    for tc in erzeugt:
        tc.close()
        tc.deleteLater()


def _sichtbar(tc):
    return [t for t in tc._tiles if t.isVisibleTo(tc._canvas)]


def _ueberlappungen(tc):
    rects = [t.geometry() for t in _sichtbar(tc)]
    if tc._done_bar.isVisibleTo(tc._canvas):
        rects.append(tc._done_bar.geometry())
    return sum(1 for i in range(len(rects)) for j in range(i + 1, len(rects))
               if rects[i].intersects(rects[j]))


def _ausserhalb(tc):
    h = tc._canvas.height()
    return [t for t in _sichtbar(tc) if t.geometry().bottom() >= h]


def test_ohne_erledigte_keine_leiste_und_kein_scrollen(widget):
    tc = widget(40, 0, 460, 1000)
    assert not tc._done_bar.isVisibleTo(tc._canvas)
    assert len(_sichtbar(tc)) == 40
    assert tc._canvas.height() == tc._scroll.viewport().height()
    assert _ueberlappungen(tc) == 0


def test_erledigte_sind_standardmaessig_eingeklappt(widget):
    # auch wenn genug Platz waere: die offenen sollen hervorstechen
    tc = widget(40, 10, 460, 1000)
    assert tc._done_bar.isVisibleTo(tc._canvas)
    assert tc._done_bar.text() == "10 erledigt ▸"
    assert len(_sichtbar(tc)) == 30
    assert tc._canvas.height() == tc._scroll.viewport().height()
    assert _ueberlappungen(tc) == 0


def test_viele_calls_eingeklappt_ohne_ueberlappen(widget):
    # Fall aus dem Screenshot: 80 Calls, 36 erledigt, zu wenig Hoehe
    tc = widget(80, 36, 460, 700)
    assert tc._done_bar.isVisibleTo(tc._canvas)
    assert tc._done_bar.text().startswith("36")
    assert len(_sichtbar(tc)) == 44          # nur die offenen
    assert _ueberlappungen(tc) == 0
    assert _ausserhalb(tc) == []


def test_klick_auf_leiste_klappt_auf_und_scrollt(widget):
    tc = widget(80, 36, 460, 700)
    QTest.mouseClick(tc._done_bar, Qt.LeftButton)

    assert len(_sichtbar(tc)) == 80
    assert tc._canvas.height() > tc._scroll.viewport().height()   # scrollt
    assert _ueberlappungen(tc) == 0
    assert _ausserhalb(tc) == []

    QTest.mouseClick(tc._done_bar, Qt.LeftButton)                 # wieder zu
    assert len(_sichtbar(tc)) == 44


def test_zu_viele_offene_scrollen_statt_abgeschnitten(widget):
    tc = widget(120, 0, 460, 700)
    assert len(_sichtbar(tc)) == 120
    assert all(t.height() >= ToCallWidget._MIN_H for t in tc._tiles)
    assert tc._canvas.height() > tc._scroll.viewport().height()
    assert _ueberlappungen(tc) == 0
    assert _ausserhalb(tc) == []


def test_fuellen_setzt_die_handwahl_zurueck(widget):
    tc = widget(80, 36, 460, 700)
    QTest.mouseClick(tc._done_bar, Qt.LeftButton)
    assert tc._done_expanded is True
    tc.fill([("a", "Dosado")])
    assert tc._done_expanded is False


def test_wenig_hoehe_wirft_keinen_fehler(widget):
    # frueher: TypeError in compute_cells (best = None)
    tc = widget(80, 60, 460, 300)
    assert _ueberlappungen(tc) == 0


def test_compute_cells_ratio_ohne_passende_spaltenzahl():
    cols, rows, cells = compute_cells(40, 500, 50, min_w=90, min_h=34,
                                      max_h=160, target_ratio=2.0)
    assert (cols, rows) == (5, 8)                 # maximal viele Spalten
    assert all(h == 34 for _x, _y, _w, h in cells)


def test_compute_cells_ratio_bevorzugt_spaltenzahl_mit_min_h():
    # Mehr Spalten passen in die Hoehe -> nie eine Wahl, die unter min_h klemmt
    n, w, h = 40, 460, 500
    _c, _r, cells = compute_cells(n, w, h, min_w=90, min_h=34, max_h=160,
                                  target_ratio=2.0)
    assert max(y + hh for _x, y, _w, hh in cells) <= h
    assert min_matrix_height(n, w, min_w=90, min_h=34) <= h
