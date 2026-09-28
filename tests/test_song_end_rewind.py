"""Nach Songende auf Anfang zurueckspulen (intern#122).

Laeuft ein Song bis zum Ende, setzt der Audio-Callback nur playing=False; die
Position bliebe am Ende stehen und Play wuerde sofort wieder enden. Das
Hauptfenster ruft deshalb beim erkannten Songende engine.stop() auf. Geprueft
ohne Audiogeraet: Feeder und Callback werden von Hand abwechselnd aufgerufen,
bis der Callback das natuerliche Ende meldet.
"""
import numpy as np
import pytest
import soundfile as sf

import audio_engine as ae

SR = 22050
FRAMES = 1024


@pytest.fixture
def engine(tmp_path):
    rng = np.random.default_rng(3)
    noise = rng.uniform(-0.5, 0.5, (SR * 5, 2)).astype(np.float32)
    path = tmp_path / "kurz.wav"
    sf.write(str(path), noise, SR)
    e = ae.AudioEngine()
    e.load(str(path))
    yield e
    e.playing = False


def _bis_zum_ende(e):
    """Wie _feeder_loop + Audio-Callback im Wechsel, bis der Song endet."""
    e.playing = True
    e.paused = False
    for _ in range(200):
        with e._lock:
            e._feed_stretcher()
        e.stretcher.preprocess(int(ae.PREPROCESS_OUTPUT_SECONDS * SR))
        out = np.zeros((FRAMES, 2), np.float32)
        e._callback(out, FRAMES, None, None)
        if not e.playing:
            return
    pytest.fail("Song ist nicht zu Ende gelaufen")


def test_songende_dann_stop_spult_auf_anfang(engine):
    e = engine
    e.seek(4.0)
    _bis_zum_ende(e)
    # Ohne Zurueckspulen steht die Position am Ende
    assert e.get_position_seconds() > 4.0
    e.stop()
    assert e._feed_pos == 0
    assert e._playback_sample == 0
    assert e.get_position_seconds() == pytest.approx(0.0, abs=0.01)


def test_songende_dann_stop_spult_auf_loop_in(engine):
    e = engine
    e.seek(4.0)
    _bis_zum_ende(e)
    # Loop erst nach dem Ende aktivieren: mit aktivem Loop endet der Song nie
    e.set_loop_in(1.0)
    e.set_loop_out(3.0)
    e.set_loop_active(True)
    e.stop()
    assert e._feed_pos == e._loop_in
    assert e.get_position_seconds() == pytest.approx(1.0, abs=0.01)
