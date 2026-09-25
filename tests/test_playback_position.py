"""Positionsuhr der Engine und Jump-Marker-Tooltip (intern#100).

Die Uhr (_estimate_playback_pos -> Anzeige, Loop-In/-Out setzen) zog den
vorberechneten Stretcher-Output-Buffer nicht ab und lief ~1 s vor dem Ton.
Geprueft ohne Audiogeraet: Feeder-Durchlauf und Callback werden von Hand
abwechselnd aufgerufen, die Ausgabe per Kreuzkorrelation dem Original
zugeordnet. Weisses Rauschen wiederholt sich nie -> eindeutige Zuordnung.
"""
import numpy as np
import pytest
import soundfile as sf

import audio_engine as ae
from jump_markers_widget import JumpMarkersWidget

SR = 22050
FRAMES = 1024


@pytest.fixture
def engine(tmp_path):
    rng = np.random.default_rng(7)
    noise = rng.uniform(-0.5, 0.5, (SR * 40, 2)).astype(np.float32)
    path = tmp_path / "rauschen.wav"
    sf.write(str(path), noise, SR)
    e = ae.AudioEngine()
    e.load(str(path))
    e.playing = True
    e.paused = False
    yield e, noise.mean(axis=1)
    e.playing = False


def _spielen(e, sekunden):
    """Wie _feeder_loop + Audio-Callback im Wechsel."""
    outs = []
    for _ in range(int(sekunden * SR / FRAMES)):
        with e._lock:
            e._feed_stretcher()
        e.stretcher.preprocess(int(ae.PREPROCESS_OUTPUT_SECONDS * SR))
        out = np.zeros((FRAMES, 2), np.float32)
        e._callback(out, FRAMES, None, None)
        outs.append(out)
    return np.concatenate(outs).mean(axis=1)


def _gehoert_bis(ref, ausgabe, schaetzung):
    """Sekunde im Original, bis zu der die Ausgabe tatsaechlich gespielt hat."""
    seg = ausgabe[-int(0.05 * SR):]
    lo = max(0, int((schaetzung - 3) * SR))
    hi = min(len(ref) - len(seg), int((schaetzung + 3) * SR))
    win = ref[lo:hi + len(seg)]
    k = int(np.argmax(np.correlate(win, seg, "valid")))
    return (lo + k + len(seg)) / SR


@pytest.mark.parametrize("tempo", [1.0, 1.1, 0.9])
def test_anzeige_folgt_dem_ton(engine, tempo):
    e, ref = engine
    e.set_tempo(tempo)
    e.seek(10.0)
    ausgabe = _spielen(e, 3.0)
    gehoert = _gehoert_bis(ref, ausgabe, 10.0 + 3.0 * tempo)
    # frueher: ~ +1 s (Output-Buffer), jetzt auf wenige ms
    assert e.get_position_seconds() == pytest.approx(gehoert, abs=0.03)


def test_sprung_landet_exakt_und_anzeige_stimmt(engine):
    e, ref = engine
    _spielen(e, 2.0)
    e.seek_with_crossfade(29.54, 46)
    ausgabe = _spielen(e, 1.0)
    gehoert = _gehoert_bis(ref, ausgabe, 30.5)
    assert gehoert == pytest.approx(29.54 + len(ausgabe) / SR, abs=0.03)
    assert e.get_position_seconds() == pytest.approx(gehoert, abs=0.03)


def test_loop_in_setzen_trifft_den_gehoerten_moment(engine):
    e, ref = engine
    e.seek(5.0)
    ausgabe = _spielen(e, 3.0)
    gehoert = _gehoert_bis(ref, ausgabe, 8.0)
    e.set_loop_in_at_current()
    assert e.loop_in_seconds == pytest.approx(gehoert, abs=0.03)


@pytest.mark.parametrize("label, t, erwartet", [
    ("00:29", 29.54, "00:29.54"),          # Vorbelegung aus "Marker setzen"
    ("", 29.54, "00:29.54"),
    ("Refrain", 29.54, "Refrain · 00:29.54"),
    ("Start", 0.0, "Start · 00:00.00"),
])
def test_tooltip_ohne_scheinbare_zeitspanne(label, t, erwartet):
    assert JumpMarkersWidget._tooltip(label, t) == erwartet


# --- Doppelklick auf Sprung-Button: hinspringen und abspielen (intern#100) ---

import types

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest


def _jump_widget(sprung, play):
    engine = types.SimpleNamespace(get_original_duration=lambda: 180.0,
                                   loop_in_seconds=0.0, loop_out_seconds=0.0)
    db = types.SimpleNamespace(get_markers=lambda _sid: [(1, 29.54, "Refrain")])
    w = JumpMarkersWidget(engine, db, jump_callback=sprung, play_callback=play,
                          song_provider=lambda: types.SimpleNamespace(id=1))
    w.resize(300, 120)
    w.refresh()
    return w


def test_klick_springt_doppelklick_spielt(qapp):
    spruenge, plays = [], []
    w = _jump_widget(spruenge.append, plays.append)
    refrain = [b for b in w._buttons if b.text() == "Refrain"][0]
    assert "\n" in refrain.toolTip()                      # Doppelklick-Hinweis

    QTest.mouseClick(refrain, Qt.LeftButton)
    assert spruenge == [29.54] and plays == []

    QTest.mouseDClick(refrain, Qt.LeftButton)
    assert plays == [29.54]


def _fenster(playing, paused=False):
    import main
    eng = types.SimpleNamespace(
        is_loaded=lambda: True,
        is_playing=lambda: playing and not paused)
    aufrufe = []
    fake = types.SimpleNamespace(
        player=types.SimpleNamespace(engine=eng,
                                     _on_play=lambda: aufrufe.append("play")),
        _jump_to_time=lambda t: aufrufe.append(("sprung", t)))
    main.P29MainWindow._jump_and_play(fake, 29.54)
    return aufrufe


def test_doppelklick_gestoppt_springt_und_startet():
    assert _fenster(playing=False) == [("sprung", 29.54), "play"]


def test_doppelklick_pausiert_springt_und_setzt_fort():
    assert _fenster(playing=True, paused=True) == [("sprung", 29.54), "play"]


def test_doppelklick_laufend_springt_nur():
    # _on_play() wuerde einen laufenden Song von vorne starten
    assert _fenster(playing=True) == [("sprung", 29.54)]
