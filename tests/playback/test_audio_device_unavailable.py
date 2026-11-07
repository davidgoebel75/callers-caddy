"""Ausgabegeraet beim Play nicht erreichbar (intern#237).

Crash-Report: sd.OutputStream() ging durch, erst stream.start() warf
PortAudioError (WDM-KS GLE 0x48F = ERROR_DEVICE_NOT_CONNECTED). Die Fallbacks in
_ensure_stream sicherten nur das Oeffnen ab, nicht das Starten. Geprueft ohne
Audiogeraet mit einem nachgebauten OutputStream.
"""
import numpy as np
import pytest
import soundfile as sf

import audio_engine as ae

SR = 22050
GEWAEHLT = 3


class _FakeStream:
    """OutputStream-Ersatz: start() scheitert fuer Geraete in ``kaputt``."""

    def __init__(self, kaputt, log, **kwargs):
        self.device = kwargs.get("device")
        self.samplerate = kwargs["samplerate"]
        self.channels = kwargs["channels"]
        self.blocksize = kwargs.get("blocksize")
        self.latency = 0.01
        self.active = False
        self.closed = False
        self._kaputt = kaputt
        log.append(self)

    def start(self):
        if self.device in self._kaputt:
            raise RuntimeError("Error starting stream: Unanticipated host error "
                               "[PaErrorCode -9999] GLE = 0x0000048F")
        self.active = True

    def close(self):
        self.closed = True
        self.active = False


@pytest.fixture
def engine(tmp_path, monkeypatch):
    path = tmp_path / "kurz.wav"
    sf.write(str(path), np.zeros((SR, 2), np.float32), SR)
    e = ae.AudioEngine()
    e.load(str(path))
    e._output_device = GEWAEHLT
    monkeypatch.setattr(ae.sd, "query_devices",
                        lambda *a, **k: {"name": "Headset (Hands-Free)",
                                         "hostapi": 0, "default_samplerate": SR})
    monkeypatch.setattr(e, "_wasapi_lookup_delayed", lambda: None)
    yield e
    e.shutdown()   # Feeder-Thread beenden, sonst bleibt je Test einer zurueck


def _geraete(monkeypatch, kaputt):
    log = []
    monkeypatch.setattr(ae.sd, "OutputStream",
                        lambda **kw: _FakeStream(kaputt, log, **kw))
    return log


def test_start_scheitert_weicht_auf_standardgeraet_aus(engine, monkeypatch):
    log = _geraete(monkeypatch, kaputt={GEWAEHLT})
    engine.play()
    assert engine.playing
    assert engine.stream.device is None and engine.stream.active
    assert engine._device_fallback[GEWAEHLT] is None
    assert engine.take_device_notice() == ("fallback", "Headset (Hands-Free)")
    # Halb geoeffnete Streams auf dem gewaehlten Geraet sind wieder zu
    assert all(s.closed for s in log if s.device == GEWAEHLT)


def test_hinweis_nur_einmal(engine, monkeypatch):
    _geraete(monkeypatch, kaputt={GEWAEHLT})
    engine.play()
    engine.take_device_notice()
    assert engine.take_device_notice() is None
    engine.stop()
    engine.play()  # Stream wird wiederverwendet, kein neuer Ausweich-Fall
    assert engine.playing
    assert engine.take_device_notice() is None


def test_kein_geraet_startbar_kein_absturz(engine, monkeypatch):
    log = _geraete(monkeypatch, kaputt={GEWAEHLT, None})
    engine.play()  # darf nicht werfen
    assert not engine.playing
    assert engine.stream is None
    assert engine._stream_device is None
    assert all(s.closed for s in log)
    kind, detail = engine.take_device_notice()
    assert kind == "failed" and "0x0000048F" in detail


def test_nach_ausfall_neuer_versuch_beim_naechsten_play(engine, monkeypatch):
    _geraete(monkeypatch, kaputt={GEWAEHLT, None})
    engine.play()
    engine.take_device_notice()
    _geraete(monkeypatch, kaputt=set())  # Geraet wieder da
    engine.play()
    assert engine.playing
    assert engine.stream.device == GEWAEHLT
    assert engine.take_device_notice() is None


def test_recovery_mitten_im_song_versucht_weiter(engine, monkeypatch):
    """Geraet faellt waehrend der Wiedergabe weg und gar nichts startet: Die
    Recovery (UI-Timer) muss es weiter versuchen, auch wenn stream None ist."""
    _geraete(monkeypatch, kaputt=set())
    engine.play()
    engine.stream.active = False                 # Geraet weg
    _geraete(monkeypatch, kaputt={GEWAEHLT, None})
    engine.ensure_stream_alive()
    assert engine.stream is None and engine.playing
    _geraete(monkeypatch, kaputt=set())          # Geraet wieder da
    engine._last_recovery_attempt = 0.0          # 2-s-Drossel ueberspringen
    engine.ensure_stream_alive()
    assert engine.stream is not None and engine.stream.active
    assert engine.stream.device == GEWAEHLT


def test_recovery_weicht_mit_hinweis_aus(engine, monkeypatch):
    _geraete(monkeypatch, kaputt=set())
    engine.play()
    engine.stream.active = False
    _geraete(monkeypatch, kaputt={GEWAEHLT})
    engine.ensure_stream_alive()
    assert engine.stream.device is None and engine.stream.active
    assert engine.take_device_notice() == ("fallback", "Headset (Hands-Free)")


def test_echte_portaudio_fehlerklasse(engine, monkeypatch):
    """Wie im Crash-Report: sounddevice.PortAudioError beim start()."""
    log = []

    class _PaStream(_FakeStream):
        def start(self):
            raise ae.sd.PortAudioError(
                "Error starting stream: Unanticipated host error", -9999)

    monkeypatch.setattr(ae.sd, "OutputStream",
                        lambda **kw: _PaStream(set(), log, **kw))
    engine.play()
    assert not engine.playing
    assert engine.take_device_notice()[0] == "failed"


def test_normalfall_unveraendert(engine, monkeypatch):
    log = _geraete(monkeypatch, kaputt=set())
    engine.play()
    assert engine.playing
    assert len(log) == 1 and log[0].device == GEWAEHLT
    assert engine.take_device_notice() is None


# ---- Ausweichen aufheben (Review #158) ----------------------------------

ANDERES = 7


def test_bewusste_wahl_versucht_geraet_wieder(engine, monkeypatch):
    """Headset weg -> Standardgeraet; Headset wieder da, Nutzerin waehlt ein
    anderes Geraet und dann wieder das Headset -> Headset wird erneut versucht."""
    _geraete(monkeypatch, kaputt={GEWAEHLT})
    engine.play()
    assert engine.stream.device is None
    engine.take_device_notice()
    _geraete(monkeypatch, kaputt=set())           # Headset wieder da
    for dev in (ANDERES, GEWAEHLT):               # wie _on_audio_device_changed
        engine.forget_device_fallback(dev)
        engine.set_output_device(dev)
    assert engine.stream.device == GEWAEHLT and engine.stream.active
    assert GEWAEHLT not in engine._device_fallback
    assert engine.take_device_notice() is None


def test_bewusste_wahl_desselben_geraets_versucht_sofort(engine, monkeypatch):
    _geraete(monkeypatch, kaputt={GEWAEHLT})
    engine.play()
    _geraete(monkeypatch, kaputt=set())
    engine.forget_device_fallback(GEWAEHLT)      # z. B. ueber die Einstellungen
    assert engine.stream.device == GEWAEHLT and engine.stream.active


def test_vorhoeren_behaelt_ausweichen(engine, monkeypatch):
    """Das Vorhoeren schaltet nur per set_output_device hin und zurueck: Ein in
    dieser Sitzung gescheitertes Geraet wird dabei nicht erneut versucht."""
    _geraete(monkeypatch, kaputt={GEWAEHLT})
    engine.play()
    engine.take_device_notice()
    log = _geraete(monkeypatch, kaputt={GEWAEHLT})
    engine.set_output_device(ANDERES)            # Vorhoeren an
    engine.set_output_device(GEWAEHLT)           # Vorhoeren aus
    assert engine.stream.device is None
    assert not any(s.device == GEWAEHLT for s in log)
    assert engine.take_device_notice() is None


# ---- Recovery scheitert komplett (Review #158) --------------------------

def test_recovery_ohne_geraet_meldet_einmal(engine, monkeypatch):
    _geraete(monkeypatch, kaputt=set())
    engine.play()
    engine.stream.active = False                 # Geraet weg
    _geraete(monkeypatch, kaputt={GEWAEHLT, None})
    engine.ensure_stream_alive()
    kind, detail = engine.take_device_notice()
    assert kind == "lost" and "0x0000048F" in detail
    engine._last_recovery_attempt = 0.0
    engine.ensure_stream_alive()                 # weiterer Fehlversuch
    assert engine.take_device_notice() is None   # nicht alle 2 s erneut
    _geraete(monkeypatch, kaputt=set())          # Geraet wieder da
    engine._last_recovery_attempt = 0.0
    engine.ensure_stream_alive()
    engine.stream.active = False                 # naechster Ausfall
    _geraete(monkeypatch, kaputt={GEWAEHLT, None})
    engine._last_recovery_attempt = 0.0
    engine.ensure_stream_alive()
    assert engine.take_device_notice()[0] == "lost"
