"""Lesebalken-Kurve und In-Lesebalken Countdown als reine Rechnung
(intern#172, intern#148). Y-Werte sind Dokument-Pixel, Zeiten Song-Sekunden.
"""
import pytest

import reading_band_path as rbp

DUR = 200.0
DOC_H = 1000.0


def _y(pos, anchors, start_y=None, end_ys=None):
    return rbp.position(pos, rbp.build_path(anchors, DUR, DOC_H, start_y, end_ys))[0]


# ---- vor dem ersten Anker ----

def test_balken_wartet_und_laeuft_im_tempo_des_folgestuecks_an():
    anchors = [(28.0, 500.0), (48.0, 700.0)]        # danach 10 px/s
    # 200 px Anlauf bei 10 px/s -> Start bei 8 s
    assert _y(0.0, anchors, start_y=300.0) == 300.0
    assert _y(8.0, anchors, start_y=300.0) == 300.0
    assert _y(18.0, anchors, start_y=300.0) == pytest.approx(400.0)
    assert _y(28.0, anchors, start_y=300.0) == 500.0


def test_ohne_folgestueck_gleitet_er_in_vier_sekunden_hin():
    anchors = [(28.0, 500.0)]
    assert _y(24.0, anchors, start_y=300.0) == 300.0
    assert _y(26.0, anchors, start_y=300.0) == pytest.approx(400.0)


def test_anlauf_beginnt_fruehestens_bei_null():
    anchors = [(5.0, 500.0), (25.0, 520.0)]         # 1 px/s -> 200 s Anlauf
    assert _y(0.0, anchors, start_y=300.0) == 300.0
    assert _y(2.5, anchors, start_y=300.0) == pytest.approx(400.0)


def test_anker_auf_der_ersten_zeile_haelt_die_position():
    anchors = [(28.0, 300.0), (48.0, 500.0)]
    assert _y(0.0, anchors, start_y=300.0) == 300.0
    assert _y(20.0, anchors, start_y=300.0) == 300.0


def test_unbekannter_abschnittsanfang_laeuft_vom_dokumentanfang():
    assert _y(14.0, [(28.0, 500.0)]) == pytest.approx(250.0)


# ---- vor einem Ruecksprung ----

BACK = [(10.0, 100.0), (30.0, 300.0), (50.0, 100.0)]     # 10 px/s, dann zurueck


def test_laeuft_im_bisherigen_tempo_bis_zum_abschnittsende_und_wartet():
    ends = [None, 400.0, None]
    assert _y(35.0, BACK, end_ys=ends) == pytest.approx(350.0)
    assert _y(40.0, BACK, end_ys=ends) == pytest.approx(400.0)
    assert _y(45.0, BACK, end_ys=ends) == pytest.approx(400.0)   # wartet
    assert _y(50.0, BACK, end_ys=ends) == 100.0


def test_ruecksprung_gleitet_kurz_vor_dem_ziel():
    path = rbp.build_path(BACK, DUR, DOC_H, None, [None, 400.0, None])
    assert rbp.position(48.0, path)[1] is False
    y, snapping = rbp.position(49.25, path)
    assert snapping is True
    assert y == pytest.approx(250.0)


def test_wird_nicht_schneller_wenn_die_zeit_nicht_reicht():
    ends = [None, 900.0, None]                      # 60 s noetig, 18,5 s da
    assert _y(48.5, BACK, end_ys=ends) == pytest.approx(485.0)


def test_ohne_abschnittsende_bleibt_er_stehen_wie_bisher():
    assert _y(40.0, BACK) == 300.0


def test_abschnittsende_anker_laeuft_nicht_weiter():
    anchors = [(10.0, 100.0), (30.0, 300.0), (31.0, 100.0)]
    assert _y(30.0, anchors, end_ys=[None, 900.0, None]) == 300.0


def test_ohne_stueck_davor_gilt_das_mittlere_tempo():
    anchors = [(10.0, 300.0), (40.0, 100.0), (60.0, 300.0)]   # Mittel 10 px/s
    assert _y(20.0, anchors, end_ys=[500.0, None, None]) == pytest.approx(400.0)


def test_nach_dem_letzten_anker_bis_zum_dokumentende():
    assert _y(DUR, BACK) == DOC_H


def test_ohne_anker_proportional():
    assert _y(50.0, []) == pytest.approx(250.0)


# ---- In-Lesebalken Countdown ----

def test_abschnittswechsel_bei_neuem_abschnitt_oder_ruecksprung():
    anchors = [(8.0, 10.0), (36.0, 50.0), (37.0, 70.0), (60.0, 90.0), (90.0, 70.0)]
    ids = ["opener", "opener", "figure", "figure", "figure"]
    assert rbp.section_change_times(anchors, ids) == [37.0, 90.0]


@pytest.mark.parametrize("pos, expected", [
    (5.9, None),        # 9 Beats entfernt
    (6.1, 8),
    (9.9, 1),
    (10.0, None),       # Wechsel erreicht, kein weiterer
])
def test_beats_bis_zum_wechsel(pos, expected):
    assert rbp.beats_until_change(pos, [10.0], 120.0, 8) == expected


def test_ohne_bpm_kein_countdown():
    assert rbp.beats_until_change(9.0, [10.0], 0.0, 8) is None
