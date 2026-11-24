"""Beats einer ganzen Sequenz fuer das Sequenz-Detail (intern#164)."""
import csv
from pathlib import Path

import pytest

from caddy.beats import calc, sequence as seq

CSV_PATH = Path(__file__).resolve().parents[2] / "tools" / "beats" / "callerlab_timing.csv"


@pytest.fixture(scope="module")
def table():
    with open(CSV_PATH, encoding="utf-8-sig") as f:
        return calc.BeatTable(list(csv.DictReader(f, delimiter=";")))


FIG = {"Heads Square Thru 4": ["call_square_thru"],
       "Square Thru 4": ["call_square_thru"],
       "Right and Left Thru": ["call_right_and_left_thru"],
       "Allemande Left": ["call_allemande_left"],
       "Swing and Promenade": ["call_wrong_way_promenade"]}   # bekannter Mapping-Fehler


def test_erste_zeile_aus_dem_squared_set(table):
    fig = {"Heads Pass Thru": ["call_pass_thru"]}
    info = seq.sequence_info(table, ["Heads Pass Thru", "Heads Pass Thru"], fig)
    a, b = info.lines
    assert (a.beats.lo, b.beats.lo) == (4, 2)
    assert info.light is None and not info.singer


def test_startmarke_ohne_wert_und_ohne_squared_set(table):
    info = seq.sequence_info(table, ["(Zero Box)", "Square Thru 4"], FIG)
    assert info.lines[0] is None
    direct = seq.sequence_info(table, ["Square Thru 4"], FIG).lines[0].beats
    assert info.lines[1].beats == direct


def test_fuellwoerter_zaehlen_nicht(table):
    fig = dict(FIG, **{"(Keep Her)": ["filler_words"],
                       "Square Thru 4 (Keep Her)": ["call_square_thru", "filler_words"]})
    info = seq.sequence_info(table, ["(Keep Her)", "Square Thru 4 (Keep Her)"], fig)
    assert info.lines[0] is None
    assert info.lines[1].beats.flags == frozenset() and info.lines[1].beats.lo == 10


def test_bezeichner_zaehlen_nicht(table):
    fig = {"Beaus Run": ["dancer_beau", "call_run"], "Left Swing Thru": ["call_left_swing_thru"]}
    info = seq.sequence_info(table, ["Beaus Run", "Left Swing Thru"], fig)
    assert calc.UNKNOWN not in info.lines[0].beats.flags
    assert info.lines[1].beats.lo == 6 and not info.lines[1].beats.flags


def test_unbekannter_call_kennzeichnet_die_summe(table):
    info = seq.sequence_info(table, ["Square Thru 4", "Gibt es nicht"], FIG)
    assert calc.UNKNOWN in info.lines[1].beats.flags
    assert calc.fmt(info.total).startswith("≥")


def test_singer_schluss_zaehlt_als_swing_und_promenade(table):
    calls = ["Heads Square Thru 4", "Right and Left Thru", "Swing and Promenade"]
    info = seq.sequence_info(table, calls, FIG, seq_type="Singer (Corner Progression)")
    end = info.lines[2]
    assert end.dynamic and (end.beats.lo, end.beats.hi) == (8, 24)
    assert info.singer and info.light in (calc.GREEN, calc.YELLOW, calc.RED)


def test_singer_ohne_schluss_auf_der_karte_rechnet_ihn_dazu(table):
    calls = ["Heads Square Thru 4", "Right and Left Thru"]
    with_end = seq.sequence_info(table, calls, FIG, seq_type="Singer")
    patter = seq.sequence_info(table, calls, FIG, seq_type="Patter")
    assert with_end.total.lo == patter.total.lo + 8
    assert with_end.total.hi == patter.total.hi + 24
    assert patter.light is None


def test_square_flow_ersetzt_nur_dynamische_werte(table):
    calls = ["Heads Square Thru 4", "Right and Left Thru", "Swing and Promenade"]
    base = seq.sequence_info(table, calls, FIG, seq_type="Singer")
    sf = seq.sequence_info(table, calls, FIG, seq_type="Singer", tam_beats=[12, 6, 16])
    fixed = base.lines[0].beats.lo + base.lines[1].beats.lo
    assert sf.total.lo == sf.total.hi == fixed + 16
    assert sf.lines[2].tam == 16 and sf.lines[2].beats == base.lines[2].beats


def test_warnung_ab_zwei_beats_nur_bei_festen_calls(table):
    calls = ["Square Thru 4", "Swing and Promenade"]
    info = seq.sequence_info(table, calls, FIG, seq_type="Singer", tam_beats=[13, 30])
    assert info.lines[0].warn
    assert not info.lines[1].warn
    near = seq.sequence_info(table, ["Square Thru 4"], FIG, tam_beats=[11])
    assert not near.lines[0].warn


def test_ampel_nach_hoechstwert(table):
    calls = ["Square Thru 4"] * 6 + ["Swing and Promenade"]
    info = seq.sequence_info(table, calls, FIG, seq_type="Singer")
    assert info.total.hi == 60 + 24 and info.light == calc.RED


def test_ampel_neutral_statt_gruen_bei_unbekannter_zeile(table):
    """Review #194: '>= n + ?' darf nicht gruen zeigen; gelb/rot bleiben."""
    calls = ["Square Thru 4", "Gibt es nicht", "Swing and Promenade"]
    info = seq.sequence_info(table, calls, FIG, seq_type="Singer")
    assert calc.UNKNOWN in info.total.flags and info.light == calc.NEUTRAL
    long = seq.sequence_info(table, ["Square Thru 4"] * 6 + calls, FIG, seq_type="Singer")
    assert long.light == calc.RED


def test_keine_warnung_bei_not_timed(table):
    """Review #194: bei Not Timed ist der Tabellenwert nur eine Untergrenze."""
    fig = dict(FIG, **{"As Couples Square Thru 4": ["concept_as_couples", "call_square_thru"]})
    info = seq.sequence_info(table, ["As Couples Square Thru 4"], fig, tam_beats=[20])
    assert calc.NOT_TIMED in info.lines[0].beats.flags
    assert not info.lines[0].warn


def test_squared_set_ueberspringt_zeile_nur_aus_fuellwoertern(table):
    fig = {"(Keep Her)": ["filler_words"], "Heads Pass Thru": ["call_pass_thru"]}
    info = seq.sequence_info(table, ["(Keep Her)", "Heads Pass Thru", "Heads Pass Thru"], fig)
    assert info.lines[0] is None
    assert (info.lines[1].beats.lo, info.lines[2].beats.lo) == (4, 2)


def test_singer_schluss_mit_zeile_danach_zaehlt_einmal(table):
    """Review #194: Zeile nach dem Schluss -> Swing + Promenade nicht doppelt."""
    calls = ["Heads Square Thru 4", "Swing and Promenade", "Right and Left Thru"]
    info = seq.sequence_info(table, calls, FIG, seq_type="Singer")
    assert info.lines[1].dynamic and (info.lines[1].beats.lo, info.lines[1].beats.hi) == (8, 24)
    expected = sum(li.beats.lo for li in info.lines)
    assert info.total.lo == expected
