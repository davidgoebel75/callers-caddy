"""Pausen-Trigger break_started / break_finished (intern#110).

Prueft die GUI-freien Teile (Registry, Suspend-Bypass der Engine) und die
Callbacks der Pausen-Uhr. Die Verdrahtung in main.py (deferred fire_trigger,
Wartemusik vor break_finished stoppen) laeuft ueber genau diese Callbacks.
"""
import pytest

from rule_definitions import register_v1_definitions
from rule_engine import ActionDef, Rule, RuleEngine


def _engine(tmp_path):
    eng = RuleEngine(str(tmp_path))
    register_v1_definitions(eng)
    return eng


def test_trigger_und_condition_registriert(tmp_path):
    reg = _engine(tmp_path).registry
    assert "break_started" in reg.triggers
    assert "break_finished" in reg.triggers
    cond = reg.conditions.get("break_type")
    assert cond is not None
    kind = cond.params_schema["kind"]
    assert kind["choices"] == ["all", "without_music", "with_music"]
    assert kind["default"] == "all"


def _engine_mit_rule(tmp_path, trigger):
    eng = _engine(tmp_path)
    calls = []
    eng.register_action("play", lambda p: calls.append("play"))
    eng.set_context_provider(lambda: {})
    eng._rules_user.append(Rule(id="usr_t", name="t", active=True, trigger=trigger,
                                conditions=[], actions=[ActionDef("play")]))
    return eng, calls


def test_break_music_sperre_laesst_pausen_trigger_durch(tmp_path):
    eng, calls = _engine_mit_rule(tmp_path, "break_started")
    eng.suspend("break_music")
    eng.fire_trigger("break_started")                      # ohne Bypass: geschluckt
    assert calls == []
    eng.fire_trigger("break_started", bypass_suspend=("break_music",))
    assert calls == ["play"]


def test_andere_sperren_gelten_weiter(tmp_path):
    eng, calls = _engine_mit_rule(tmp_path, "break_finished")
    eng.suspend("break_music")
    eng.suspend("loop_finder")
    eng.fire_trigger("break_finished", bypass_suspend=("break_music",))
    assert calls == []
    eng.resume("loop_finder")
    eng.fire_trigger("break_finished", bypass_suspend=("break_music",))
    assert calls == ["play"]


def test_sperre_ohne_grund_laesst_sich_nicht_umgehen(tmp_path):
    eng, calls = _engine_mit_rule(tmp_path, "break_started")
    eng.suspend()
    eng.fire_trigger("break_started", bypass_suspend=("break_music",))
    assert calls == []


@pytest.fixture
def uhr(qapp):
    from break_photo_widget import BreakWidget
    w = BreakWidget()
    w.events = []
    w.on_break_started = lambda with_music: w.events.append(("started", with_music))
    w.on_break_finished = lambda: w.events.append(("finished",))
    yield w
    w._timer.stop()
    w.deleteLater()


def _ablaufen(w):
    w._last_mono = 0.0          # naechster _tick zieht die ganze Restzeit ab
    w._remaining = 0.001
    w._tick()


def test_frischer_start_feuert_fortsetzen_nicht(uhr):
    uhr._toggle_start()                         # Start
    assert uhr.events == [("started", False)]
    uhr._remaining -= 5                         # etwas gelaufen
    uhr._toggle_start()                         # anhalten
    uhr._toggle_start()                         # fortsetzen
    assert uhr.events == [("started", False)]


def test_ablauf_feuert_finished_zuruecksetzen_nicht(uhr):
    uhr.start_break(60)
    uhr._remaining -= 5
    uhr._reset()
    assert ("finished",) not in uhr.events
    uhr.start_break(60)
    _ablaufen(uhr)
    assert uhr.events == [("started", False), ("started", False), ("finished",)]


def test_start_nach_ablauf_ist_frisch(uhr):
    uhr.start_break(60)
    _ablaufen(uhr)
    uhr._toggle_start()
    assert uhr.events == [("started", False), ("finished",), ("started", False)]


def test_start_mit_wartemusik(uhr):
    uhr.on_play_last_song = lambda secs: True
    uhr.start_break_with_last_song(60)
    assert uhr.events == [("started", True)]
