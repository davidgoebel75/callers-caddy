"""Zeitachse (intern#247): Beats je Kartenzeile, Interpolation, Beat/Sekunde."""
from caddy.choreo import timeline


def test_card_beats_summiert_und_ende():
    # Kartenzeilen: Pass Thru | Tag The Line Right (2 Zeilen) | Ferris Wheel | L.A.
    res = timeline.card_beats(4, [None, 0, 1, 1, 2], [6, 2, 4, 2, 4], end_src=3, beats_end=4)
    assert res == [2, 6, 4, 4]


def test_card_beats_nach_abbruch_ohne_wert():
    res = timeline.card_beats(3, [0, 1, 2], [4, 6], end_src=None, beats_end=None)
    assert res == [4, 6, None]


def test_beat_sekunde():
    assert timeline.beats_to_seconds(64, 128) == 30.0
    assert timeline.seconds_to_beats(30.0, 128) == 64
    assert timeline.beats_to_seconds(8, 0) == 0.0


def _anim():
    return {"dancers": [{"n": 1, "couple": 1, "boy": True}],
            "call_starts": [0, 4], "total_beats": 8,
            "frames": [[0, [[0.0, 0.0, 350.0]]], [4, [[2.0, 0.0, 10.0]]], [8, [[2.0, 2.0, 10.0]]]]}


def test_pose_interpoliert_mit_kuerzestem_winkel():
    tl = timeline.Timeline(_anim())
    x, y, w = tl.pose_at(2)[0]
    assert (x, y) == (1.0, 0.0)
    assert abs(w - 360.0) < 1e-9            # 350 -> 10 ueber 0, nicht rueckwaerts
    assert tl.pose_at(-1) == [[0.0, 0.0, 350.0]]
    assert tl.pose_at(99) == [[2.0, 2.0, 10.0]]


def test_zeile_zum_beat():
    tl = timeline.Timeline(_anim())
    assert tl.line_at(-0.5) == -1
    assert tl.line_at(0) == 0
    assert tl.line_at(5) == 1
    assert tl.line_span(1) == (4, 8)


def test_leere_animation():
    tl = timeline.Timeline(None)
    assert tl.empty() and tl.pose_at(3) == []
