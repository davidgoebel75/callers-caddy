"""intern#164: Beat-Rechnung (caddy.beats.calc) gegen die echte Pflegedatei."""
import csv
from pathlib import Path

import pytest

from caddy.beats import calc

CSV_PATH = Path(__file__).resolve().parents[2] / "tools" / "beats" / "callerlab_timing.csv"


@pytest.fixture(scope="module")
def table():
    with open(CSV_PATH, encoding="utf-8-sig", newline="") as f:
        return calc.BeatTable(list(csv.DictReader(f, delimiter=";")))


def lb(table, ents, text, **kw):
    b = calc.line_beats(table, ents, text, **kw)
    return b.lo, b.hi, set(b.flags)


@pytest.mark.parametrize("ents, text, lo, hi", [
    (["call_pass_thru"], "Pass Thru", 2, 2),
    (["call_square_thru"], "Square Thru", 10, 10),            # Standard FC 4
    (["call_square_thru"], "Square Thru 2", 5, 5),
    (["call_square_thru"], "Square Thru 3", 7, 8),            # bereich
    (["call_square_thru"], "Heads Square Thru 4", 10, 10),    # gerade: kein SS-Zuschlag
    (["call_couples_promenade"], "Promenade 1/2", 8, 8),
    (["call_eight_chain_thru"], "Eight Chain Thru", 20, 20),
    (["call_eight_chain_thru"], "Eight Chain 4", 10, 10),     # 2 + 3 + 2 + 3
    (["call_eight_chain_thru"], "Eight Chain 3", 7, 7),       # 2 + 3 + 2
])
def test_einzelne_calls(table, ents, text, lo, hi):
    assert lb(table, ents, text)[:2] == (lo, hi)


def test_ss_zeile_nur_aus_dem_squared_set(table):
    assert lb(table, ["call_pass_thru"], "Heads Pass Thru", squared_set=True)[:2] == (4, 4)
    assert lb(table, ["call_pass_thru"], "Heads Pass Thru", squared_set=False)[:2] == (2, 2)


def test_ss_ungerade_square_thru_plus_zwei(table):
    # SS odd numbers: add 2 to previous count -> FC 3 (7-8) + 2
    assert lb(table, ["call_square_thru"], "Heads Square Thru 3", squared_set=True)[:2] == (9, 10)


def test_separate_around_ohne_pass_thru_zieht_zwei_ab(table):
    e = ["call_separate_around_to_a_line"]
    assert lb(table, e, "Separate Around 1 to a Line")[:2] == (6, 6)
    assert lb(table, e, "Separate Around 2 to a Line")[:2] == (8, 8)
    assert lb(table, e, "Pass Thru, Separate Around 1 to a Line")[:2] == (8, 8)


def test_supercalls(table):
    # Explode and (Anything): 2 + Call
    assert lb(table, ["concept_explode_and_anything", "call_square_thru"],
              "Explode And 1/2 Square Thru")[:2] == (7, 7)     # 2 + Square Thru 2 (5)
    assert lb(table, ["concept_explode_and_anything", "call_pass_thru"],
              "Explode And Pass Thru")[:2] == (4, 4)
    # Clover and (Anything): max(4, Call)
    assert lb(table, ["concept_clover_and_anything", "call_pass_thru"],
              "Clover And Pass Thru")[:2] == (4, 4)
    assert lb(table, ["concept_clover_and_anything", "call_square_thru"],
              "Clover And Square Thru 4")[:2] == (10, 10)
    # (Anything) and Cross: Call + 2
    assert lb(table, ["call_anything_and_cross", "call_named_dancers_trade"],
              "Centers Trade And Cross")[:2] == (5, 5)


def test_transfer_and_anything_beginnt_auf_beat_fuenf(table):
    e = ["concept_transfer_and_anything"]
    assert lb(table, e + ["call_pass_thru"], "Transfer And Pass Thru")[:2] == (8, 8)
    assert lb(table, e + ["call_square_thru"], "Transfer And Square Thru 4")[:2] == (14, 14)


def test_kombination_all_4_couples(table):
    lo, hi, flags = lb(table, ["concept_all_4_couples", "call_pass_thru"], "All 4 Couples Pass Thru")
    assert (lo, hi) == (8, 8) and not flags


def test_not_timed_und_unbekannt(table):
    lo, hi, flags = lb(table, ["concept_any_hand", "call_pass_thru"], "Any Hand Pass Thru")
    assert (lo, hi) == (2, 2) and calc.NOT_TIMED in flags
    assert calc.UNKNOWN in lb(table, ["call_gibt_es_nicht"], "Foo")[2]
    assert calc.UNKNOWN in lb(table, [], "Foo")[2]


def test_dynamisch_mit_und_ohne_taminations(table):
    e = ["call_swing", "call_couples_promenade"]
    lo, hi, flags = lb(table, e, "Swing & Promenade")
    assert calc.DYNAMIC in flags
    lo, hi, flags = lb(table, e, "Swing & Promenade", tam_beats=22)
    assert (lo, hi) == (22, 22) and flags == {calc.TAMINATIONS}
    # fester Call: Taminations ersetzt nichts
    assert lb(table, ["call_pass_thru"], "Pass Thru", tam_beats=5)[:2] == (2, 2)


def test_summe_ampel_und_anzeige():
    B = calc.Beats
    total = calc.sequence_beats([B(10, 10), B(7, 8), B(40, 46)])
    assert (total.lo, total.hi) == (57, 64)
    assert calc.traffic_light(total) == calc.GREEN
    assert calc.traffic_light(B(60, 66)) == calc.YELLOW
    assert calc.traffic_light(B(60, 69)) == calc.RED
    assert calc.fmt(B(7, 8)) == "7–8"
    assert calc.fmt(B(58, 58, frozenset({calc.NOT_TIMED}))) == "≥ 58 + ?"


def test_abweichung_ab_zwei_beats():
    b = calc.Beats(6, 8)
    assert calc.deviation(b, 7) == 0
    assert calc.deviation(b, 4) == -2 and calc.warn_deviation(b, 4)
    assert not calc.warn_deviation(b, 9)


@pytest.mark.parametrize("text, factor", [
    ("Split Circulate Twice", 2), ("Swing Thru Double", 2), ("Double Pass Thru", 1),
    ("Circulate 1 & 1/2", 1.5), ("Circulate One and a Half", 1.5), ("Pass Thru", 1),
])
def test_wiederholung(text, factor):
    assert calc.repeat_factor(text) == factor


def test_wiederholung_in_der_rechnung(table):
    assert lb(table, ["call_split_circulate"], "Split Circulate Twice")[:2] == (8, 8)


def test_cloverleaf_mit_gruppe_vier_aktive(table):
    assert lb(table, ["call_cloverleaf"], "Cloverleaf")[:2] == (8, 8)
    assert lb(table, ["call_cloverleaf"], "Outsides Cloverleaf")[:2] == (6, 6)
