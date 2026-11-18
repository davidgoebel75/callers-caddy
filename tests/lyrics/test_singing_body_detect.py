"""Erkennung des Singing-Call-Body an einem synthetischen Song.

Audio-Laden und Beat-Grid sind ersetzt: der Test baut ein Signal mit bekanntem
Intro, sieben Abschnitten a 64 Beats (je eigener Ton, Crash am Abschnittsanfang,
Kick-Akzent auf jeder Phrasen-"1") und Outro.
"""
import numpy as np
import pytest

import singing_body_detect as sbd

SR, BPM = 8000, 128.0
SPB = int(SR * 60.0 / BPM)          # Samples pro Beat
BODY = sbd.BODY_BEATS


def _song(intro, outro=32, seed=1):
    rng = np.random.default_rng(seed)
    t = np.arange(SPB) / SR
    kick = np.sin(2 * np.pi * 80 * t) * np.exp(-t * 30)

    def seg(freq, n, loud):
        return [loud * np.sin(2 * np.pi * freq * t)
                + 0.02 * rng.standard_normal(SPB)
                + (0.9 if b % 8 == 0 else 0.4) * kick for b in range(n)]

    beats = seg(150, intro, 0.05)
    for freq in (220, 330, 440, 262, 494, 392, 294):
        sec = seg(freq, sbd.SECTION_BEATS, 0.5)
        sec[0] = sec[0] + 0.6 * rng.standard_normal(SPB) * np.exp(-t * 20)
        beats += sec
    beats += seg(150, outro, 0.05)
    return np.concatenate(beats), np.arange(len(beats)) * SPB / SR


@pytest.fixture
def fake_song(monkeypatch):
    calls = {}

    def use(intro, outro=32, n_beats=None):
        mono, beat_times = _song(intro, outro)
        if n_beats is not None:
            mono, beat_times = mono[:SPB * n_beats], beat_times[:n_beats]
        monkeypatch.setattr(sbd, "_load_audio", lambda f: (mono, SR))

        def grid(f, bpm=None):
            calls["bpm"] = bpm
            return BPM, beat_times
        monkeypatch.setattr(sbd, "detect_beat_grid", grid)
        return mono, beat_times
    use.calls = calls
    return use


@pytest.mark.parametrize("intro", [16, 40])
def test_findet_body_anfang(fake_song, intro):
    mono, bt = fake_song(intro)
    r = sbd.detect_singing_body("x.mp3", bpm_hint=BPM, calib_offset=0)
    assert r["ok"] and r["start_beat"] == intro
    assert r["start_sec"] == pytest.approx(bt[intro])
    assert r["end_sec"] == pytest.approx(bt[intro + BODY])
    assert r["n_beats"] == len(bt)
    assert r["bpm"] == BPM
    assert r["beat_period"] == pytest.approx(SPB / SR)
    assert r["confidence"] > 0
    assert r["ambiguous"] is False and r["disagree"] < sbd.AMBIGUITY_THRESHOLD


def test_kalibrier_offset_default(fake_song):
    fake_song(16)
    r = sbd.detect_singing_body("x.mp3", bpm_hint=BPM)
    assert r["start_beat"] == 16 + sbd.DEFAULT_CALIB_OFFSET


def test_kalibrier_offset_bleibt_im_song(fake_song):
    mono, _ = fake_song(16, outro=0)            # max. Startbeat = 16
    r = sbd.detect_singing_body("x.mp3", bpm_hint=BPM, calib_offset=5)
    assert r["start_beat"] == 16
    assert r["end_sec"] == pytest.approx(len(mono) / SR)   # Ende = Songende


@pytest.mark.parametrize("n_beats, ok", [(BODY + 1, False), (BODY + 2, True)])
def test_mindestlaenge(fake_song, n_beats, ok):
    fake_song(8, outro=0, n_beats=n_beats)
    r = sbd.detect_singing_body("x.mp3")
    assert r["ok"] is ok
    if not ok:
        assert f"({n_beats} Beats)" in r["reason"]


@pytest.mark.parametrize("hint, weiter", [
    (128.0, 128.0), (40.0, None), (0, None), (None, None), (41.0, 41.0)])
def test_bpm_hinweis_nur_wenn_plausibel(fake_song, hint, weiter):
    fake_song(16)
    sbd.detect_singing_body("x.mp3", bpm_hint=hint)
    assert fake_song.calls["bpm"] == weiter


def test_filterbaenke():
    mel = sbd._mel_filterbank(8000, 512, n_bands=10)
    assert mel.shape == (10, 257)
    assert mel.min() >= 0 and mel.max() <= 1
    assert (mel.max(axis=1) > 0).all()            # kein leeres Band
    chroma = sbd._chroma_filterbank(8000, 4096)
    assert chroma.shape == (12, 2049)
    a4 = round(440 * 4096 / 8000)                 # Bin von A4 -> Pitch-Class 0
    assert chroma[0, a4] == 1 and chroma[:, a4].sum() == 1
    assert chroma[:, 0].sum() == 0                # unter fmin: keine Klasse
