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
def uhr(keep):
    """Pausen-Uhr mit mitgeschriebenen Callbacks. Die Logik dahinter pruefen die
    Reducer-Tests in test_break_clock.py, hier nur die Verdrahtung."""
    from caddy.playback.break_widget import BreakWidget
    w = keep(BreakWidget())
    w.events = []
    w.on_break_started = lambda with_music: w.events.append(("started", with_music))
    w.on_break_finished = lambda: w.events.append(("finished",))
    return w


def test_start_knopf_meldet_frischen_start(uhr):
    uhr._btn_start.click()
    assert uhr.state.running
    assert uhr.events == [("started", False)]


@pytest.fixture
def takt(uhr, monkeypatch):
    """Gestellte Uhrzeit: takt(t) setzt die Zeit und loest einen Timer-Tick aus."""
    import caddy.playback.break_widget as modul
    jetzt = [0.0]
    monkeypatch.setattr(modul.time, "monotonic", lambda: jetzt[0])

    def _takt(t):
        jetzt[0] = t
        uhr._timer.timeout.emit()
    return _takt


def test_ablauf_meldet_finished_und_haelt_an(uhr, takt):
    uhr.start_break(60)
    takt(100.0)                                 # erster Tick: nur Zeitmarke
    takt(161.0)                                 # 61 s spaeter: abgelaufen
    assert uhr.state.finished and not uhr.state.running
    assert uhr.events == [("started", False), ("finished",)]


def test_neustart_laufender_uhr_misst_die_zeit_neu(uhr, takt):
    uhr.start_break(60)
    takt(100.0)
    takt(110.0)
    assert uhr.state.remaining == 50
    uhr.start_break(60)                         # Rule-Aktion bei laufender Uhr
    takt(110.2)                                 # erster Tick danach: nur Zeitmarke
    assert uhr.state.remaining == 60


def test_reset_knopf_meldet_kein_finished(uhr):
    uhr.start_break(60)
    uhr._btn_reset.click()
    assert not uhr.state.running
    assert uhr.events == [("started", False)]


def test_start_mit_wartemusik(uhr):
    uhr.on_play_last_song = lambda secs: True
    uhr.start_break_with_last_song(60)
    assert uhr.events == [("started", True)]


# --- Rule-Ton (play_sound) auch ohne laufende Musik hoerbar -----------------

def _leerlauf_engine():
    """AudioEngine ohne __init__ (kein Geraet, kein Feeder-Thread) im Zustand
    'Stream offen, keine Musik'."""
    import numpy as np
    from audio_engine import AudioEngine
    eng = AudioEngine.__new__(AudioEngine)
    eng._frame_samples_done = True
    eng.playing = False
    eng.paused = False
    eng.stretcher = None
    eng.channels = 2
    eng._alert_data = None
    eng._alert_pos = 0
    eng._alert_volume = 1.0
    eng.stream = object()        # Stream schon offen (es wurde schon gespielt)
    eng.sample_rate = 44100
    return eng, np


def test_alert_im_leerlauf_wird_ausgegeben_und_verbraucht():
    eng, np = _leerlauf_engine()
    eng.play_alert(np.full(300, 0.5, dtype=np.float32), volume=1.0)
    out = np.zeros((256, 2), dtype=np.float32)
    eng._callback(out, 256, None, None)
    assert np.allclose(out, 0.5)                 # hoerbar statt Stille
    out2 = np.zeros((256, 2), dtype=np.float32)
    eng._callback(out2, 256, None, None)
    assert np.allclose(out2[:44], 0.5) and np.allclose(out2[44:], 0.0)
    assert eng._alert_data is None               # nicht fuer den naechsten Song aufgehoben


def test_leerlauf_ohne_alert_bleibt_still():
    eng, np = _leerlauf_engine()
    out = np.ones((128, 2), dtype=np.float32)
    eng._callback(out, 128, None, None)
    assert not out.any()


def test_kaltstart_oeffnet_stream_fuer_alert():
    """Noch nie gespielt, kein Song geladen: play_alert oeffnet den Stream
    selbst im Alert-Standardformat, statt bis zum naechsten Play zu warten."""
    from audio_engine import ALERT_IDLE_SR
    eng, np = _leerlauf_engine()
    eng.stream = None
    eng.sample_rate = None
    eng.channels = None
    geoeffnet = []
    eng._ensure_stream = lambda: geoeffnet.append((eng.sample_rate, eng.channels))
    eng.play_alert(np.full(10, 0.5, dtype=np.float32))
    assert geoeffnet == [(ALERT_IDLE_SR, 2)]
    assert eng._alert_data.shape == (10, 2)


def test_kaltstart_mit_geladenem_song_behaelt_songformat():
    eng, np = _leerlauf_engine()
    eng.stream = None
    eng.sample_rate = 48000
    eng.channels = 2
    geoeffnet = []
    eng._ensure_stream = lambda: geoeffnet.append((eng.sample_rate, eng.channels))
    eng.play_alert(np.full(10, 0.5, dtype=np.float32))
    assert geoeffnet == [(48000, 2)]
