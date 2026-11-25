"""Figuren-Uhr im Singing Call (Square Flow Phase 2, intern#247)."""
import pytest

from caddy.choreo import figure_clock as fc


def _res(**kw):
    r = {"stufe1": True, "urteil": "gruen", "anim_total": 16.0,
         "card_spans": [(0.0, 8.0), (8.0, 12.0), (12.0, 16.0)]}
    r.update(kw)
    return r


def test_anteile_nach_beats():
    assert fc.card_fractions(_res(), 3) == [0.0, 0.5, 0.75]


def test_gesamt_mit_aufloese_call_aus_der_animation():
    """Swing & Promenade ohne eigene Kartenzeile: Anteile beziehen sich auf die ganze Figur."""
    assert fc.card_fractions(_res(anim_total=32.0), 3) == [0.0, 0.25, 0.375]


def test_alter_cache_ohne_anim_total_nimmt_ende_der_letzten_karte():
    r = _res()
    del r["anim_total"]
    assert fc.figure_total(r) == 16.0


@pytest.mark.parametrize("kw", [{"stufe1": False}, {"urteil": "rot"}, {"card_spans": []}])
def test_abbruch_rot_oder_ohne_takte_gilt_nicht(kw):
    assert fc.card_fractions(_res(**kw), 3) is None


def test_andere_kartenzahl_gilt_nicht():
    assert fc.card_fractions(_res(), 4) is None


def test_karte_ohne_spanne_bekommt_keinen_anker():
    r = _res(card_spans=[(0.0, 8.0), None, (12.0, 16.0)])
    assert fc.card_fractions(r, 3) == [0.0, None, 0.75]
    assert fc.beat_anchors(10.0, 26.0, [0.0, None, 0.75], lambda i: 100 + i) == [(22.0, 102)]


def test_zwischenanker_ohne_ersten_call_und_streng_im_fenster():
    assert fc.beat_anchors(10.0, 26.0, [0.0, 0.5, 0.75], lambda i: i) == [(18.0, 1), (22.0, 2)]
    assert fc.beat_anchors(10.0, 26.0, [0.0, 1.0], lambda i: i) == []
    assert fc.beat_anchors(10.0, None, [0.0, 0.5], lambda i: i) == []


def test_beat_im_fenster_und_im_tempo():
    assert fc.beat_in_window(14.0, 10.0, 18.0, 16.0) == 8.0
    assert fc.beat_in_window(30.0, 10.0, 18.0, 16.0) == 16.0
    assert fc.beat_in_window(5.0, 10.0, 18.0, 16.0) == 0.0
    assert fc.beat_by_tempo(13.0, 10.0, 120) == 6.0


def test_fenster_aus_syncpoints():
    """Auto-Sync: je Teil Anfang (Ueberschrift) und Ende (letzte Blockzeile); ein gemeinsamer
    Block fuer alle Figuren. Teil 2 hat einen eigenen Zwischenanker des Callers."""
    block = (5, 9)
    anchors = [(1.0, 0), (10.0, 5), (26.0, 9), (40.0, 5), (48.0, 7), (56.0, 9), (70.0, 5)]
    w = fc.part_windows(anchors, {5}, lambda ln: block if 5 <= ln <= 9 else None)
    assert w == [(10.0, 26.0, True, block), (40.0, 56.0, False, block),
                 (70.0, None, False, block)]
