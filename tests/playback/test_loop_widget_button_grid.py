"""New-Songs-Widget: die Kanten der beiden Button-Reihen fluchten (intern#158).

Reihe 1: Set In, Clear Loop, Set Out, Test. Reihe 2: Find Loop ueber zwei
Spalten, Snap, Set Marker. Geprueft bei mehreren Breiten und mit einem
ueberlangen Button-Text (steht fuer die unterschiedlich langen Texte in
de/en/ja).
"""
import pytest

from player_widget import LoopWidget


def _edges(w, name):
    g = getattr(w, name).geometry()
    return g.left(), g.right()


def _assert_aligned(w):
    set_in, clear, set_out, test = (
        _edges(w, n) for n in
        ("btn_set_in", "btn_clear_loop", "btn_set_out", "btn_test"))
    find, snap, marker = (
        _edges(w, n) for n in ("btn_find_loop", "btn_snap", "btn_set_marker"))
    assert find == (set_in[0], clear[1])     # Find Loop deckt Spalte 1 und 2
    assert snap == set_out
    assert marker == test


@pytest.fixture
def loop_widget(qapp):
    w = LoopWidget(engine=None)
    yield w
    w.close()
    w.deleteLater()


@pytest.mark.parametrize("extra", [0, 60, 250])
def test_kanten_fluchten_bei_jeder_breite(qapp, loop_widget, extra):
    w = loop_widget
    w.resize(w.minimumSizeHint().width() + extra, w.sizeHint().height())
    w.show()
    qapp.processEvents()
    _assert_aligned(w)


def test_kanten_fluchten_auch_mit_langem_text(qapp, loop_widget):
    w = loop_widget
    w.btn_clear_loop.setText("Ein sehr langer Button-Text\nin einer Sprache")
    w.resize(w.minimumSizeHint().width() + 60, w.sizeHint().height())
    w.show()
    qapp.processEvents()
    _assert_aligned(w)
    widths = {getattr(w, n).width() for n in
              ("btn_set_in", "btn_clear_loop", "btn_set_out", "btn_test")}
    assert max(widths) - min(widths) <= 1    # Rundung auf ganze Pixel


def test_loop_widget_liest_song_aus_sitzung(keep):
    """intern#142: LoopWidget braucht die Sitzung, sonst AttributeError beim Loop-Speichern."""
    from types import SimpleNamespace
    song = SimpleNamespace(id=7)
    w = keep(LoopWidget(engine=None, session=SimpleNamespace(song=song)))
    assert w._current_song() is song
    assert keep(LoopWidget(engine=None))._current_song() is None
