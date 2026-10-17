"""Pausen-Uhr als Reducer (intern#220): Zustand und Uebergaenge ohne Qt."""
from caddy.breaks.break_clock import (
    BreakState, Pause, Reset, Restart, SetDuration, Start, Tick, reduce)


def test_start_laeuft_und_meldet_started():
    s, events = reduce(BreakState(total=60, remaining=60), Start())
    assert s.running
    assert events == ("started",)


def test_fortsetzen_nach_anhalten_meldet_nichts():
    s, events = reduce(BreakState(total=60, remaining=40), Start())
    assert s.running and s.remaining == 40
    assert events == ()


def test_tick_zieht_nur_bei_laufender_uhr_ab():
    laeuft = BreakState(total=60, remaining=60, running=True)
    assert reduce(laeuft, Tick(5)) == (BreakState(60, 55, running=True), ())
    angehalten = BreakState(total=60, remaining=40)
    assert reduce(angehalten, Tick(5)) == (angehalten, ())


def test_ablauf_auf_null_haelt_an_und_meldet_finished():
    s, events = reduce(BreakState(total=60, remaining=3, running=True), Tick(5))
    assert s == BreakState(total=60, remaining=0.0, running=False, finished=True)
    assert events == ("finished",)


def test_start_nach_ablauf_beginnt_von_vorn():
    abgelaufen = BreakState(total=60, remaining=0.0, finished=True)
    s, events = reduce(abgelaufen, Start())
    assert s == BreakState(total=60, remaining=60, running=True)
    assert events == ("started",)


def test_anhalten_behaelt_restzeit():
    s, events = reduce(BreakState(total=60, remaining=40, running=True), Pause())
    assert s == BreakState(total=60, remaining=40)
    assert events == ()


def test_reset_setzt_zurueck_ohne_finished():
    for vorher in (BreakState(total=120, remaining=37, running=True),
                   BreakState(total=120, remaining=0.0, finished=True)):
        s, events = reduce(vorher, Reset())
        assert s == BreakState(total=120, remaining=120)
        assert events == ()


def test_neue_dauer_bei_stehender_uhr_setzt_restzeit():
    abgelaufen = BreakState(total=60, remaining=0.0, finished=True)
    assert reduce(abgelaufen, SetDuration(300)) == (BreakState(300, 300), ())


def test_neue_dauer_aendert_laufenden_countdown_nicht():
    laeuft = BreakState(total=60, remaining=40, running=True)
    s, _ = reduce(laeuft, SetDuration(300))
    assert s == BreakState(total=300, remaining=40, running=True)


def test_ungueltige_dauer_aendert_nichts():
    s = BreakState(total=60, remaining=40)
    for dauer in (None, 0, -5):
        assert reduce(s, SetDuration(dauer)) == (s, ())
    assert reduce(s, SetDuration(0.4))[0].total == 1    # mindestens 1 s


def test_neustart_beginnt_frisch_auch_bei_laufender_uhr():
    laeuft = BreakState(total=60, remaining=40, running=True)
    assert reduce(laeuft, Restart()) == (
        BreakState(total=60, remaining=60, running=True), ("started",))
    assert reduce(laeuft, Restart(120)) == (
        BreakState(total=120, remaining=120, running=True), ("started",))
