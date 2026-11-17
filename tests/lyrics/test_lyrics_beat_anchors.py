"""Lesebalken nach Beats und Figuren-Fenster fuer Square Flow (intern#247 Phase 2)."""
import pytest


def _result(**kw):
    r = {"stufe1": True, "urteil": "gruen", "anim_total": 16.0,
         "card_spans": [(0.0, 8.0), (8.0, 12.0), (12.0, 16.0)]}
    r.update(kw)
    return r


CALLS = ["Heads Square Thru 4", "Right And Left Thru", "Allemande Left"]


@pytest.fixture
def make(qapp, tmp_path):
    from PySide6.QtCore import QSettings
    from path_manager import PathManager
    from lyrics_widget import LyricsWidget

    def _make(result):
        ini = QSettings(str(tmp_path / "t.ini"), QSettings.IniFormat)
        w = LyricsWidget(PathManager(ini))
        w._settings = ini
        w._browser.setHtml("<p>OPENER</p><p>FIGURE</p><p>old call</p><p>old 2</p>"
                           "<p>CLOSER</p>")
        w._lyrics_loaded = True
        w._rebuild_line_offsets()
        w._cache_original_sizes()
        w._lyric_sections = {n: (1, 3) for n in
                             ("figure1", "figure2", "figure3", "figure4")}
        off = w._line_offsets
        # Auto-Sync: Teil-Anfang auf der Ueberschrift, Ende auf der letzten Blockzeile
        w._sync_anchors = [[1.0, off[0]], [10.0, off[1]], [26.0, off[3]],
                           [40.0, off[1]], [56.0, off[3]], [70.0, off[4]]]
        w.get_current_sequence_calls = lambda: list(CALLS)
        w.get_flow_result = lambda calls: result if calls == CALLS else None
        w._dynamic_enabled = True
        w._apply_dynamic()
        return w
    return _make


def _anchor_lines(w):
    return sorted((round(sec, 2), w._char_to_line_in(w._line_offsets, p))
                  for sec, p in w._dynamic_anchors)


def test_zwischenanker_je_call_nach_beats(make):
    w = make(_result())
    lines = _anchor_lines(w)
    # Calls stehen in den Zeilen 2..4; Anteile 0 / 0.5 / 0.75 im Fenster 10..26
    assert (18.0, 3) in lines and (22.0, 4) in lines
    assert (48.0, 3) in lines and (52.0, 4) in lines   # Teil 2: 40..56
    assert w._dyn_beat_times == {18.0, 22.0, 48.0, 52.0}


def test_lesebalken_laeuft_von_call_zu_call(make):
    w = make(_result())
    ys = dict(w._reading_geometry()["anchors"])
    assert ys[10.0] < ys[18.0] < ys[22.0] <= ys[26.0]


def test_kurze_calls_beenden_keinen_abschnitt(make):
    """Zwischenanker binnen 2 s zeigen auf die Zeilenmitte, nicht auf die Unterkante."""
    w = make(_result())
    w._dynamic_anchors = [a for a in w._dynamic_anchors if a[0] != 22.0]
    w._dynamic_anchors += [[25.0, w._line_offsets[4]]]        # 1 s vor dem Ende-Anker
    w._dyn_beat_times = frozenset({18.0, 25.0})
    mid = dict(w._reading_geometry()["anchors"])[25.0]
    w._dyn_beat_times = frozenset({18.0})                     # Gegenprobe: echter Anker
    w._geom_cache = None
    bottom = dict(w._reading_geometry()["anchors"])[25.0]
    assert mid < bottom


@pytest.mark.parametrize("res", [None, _result(urteil="rot"), _result(stufe1=False)])
def test_ohne_takte_rot_oder_abbruch_wie_bisher(make, res):
    w = make(res)
    assert w._dyn_beat_times == frozenset()
    assert len(w._dynamic_anchors) == len(w._sync_anchors)


def test_figuren_fenster(make):
    w = make(_result())
    assert w.figure_window(5.0) == (-1, -1, None, None)        # Opener
    assert w.figure_window(12.0) == (0, 0, 10.0, 26.0)
    assert w.figure_window(30.0) == (-1, 0, None, None)        # zwischen den Figuren
    assert w.figure_window(41.0) == (1, 1, 40.0, 56.0)
    w._revert_dynamic()
    assert w.figure_window(12.0) is None                       # Dynamic aus -> manuell
