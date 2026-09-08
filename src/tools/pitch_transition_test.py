"""
Pitch-Transition-Test
=====================
Spielt einen reinen 1 kHz-Sinus durch die echte AudioEngine, ruft mitten in
der Wiedergabe `set_pitch(+3)` auf und zeichnet den Output-Stream als WAV
auf. Ziel: das hoerbare "Leiern" waehrend der ca. 1-2 s Einschwingphase
nach einem Pitch-Wechsel messtechnisch greifbar machen.

Aufruf (im 2_Test/-Ordner oder direkt):
    python ../1_Source/src/tools/pitch_transition_test.py

Erzeugt:
    pitch_transition_capture.wav     — Mono float32, Sample-Rate wie Engine
    pitch_transition_events.txt      — Sample-Index der set_pitch-Aufrufe

Die Analyse uebernimmt `pitch_transition_analyze.py` (STFT + Peak-Tracking).

WICHTIG: das Skript schreibt eine temporaere WAV ins TEMP-Verzeichnis und
laedt sie ueber die normale `AudioEngine.load()`-Methode — der Pfad durch
Stretcher + Pitcher ist also identisch zum Live-Betrieb. Nichts an der
Audio-Engine selbst wird umgangen.
"""

from __future__ import annotations

import os
import sys
import time
import tempfile
import numpy as np
import soundfile as sf

# src/ in den Pfad aufnehmen, damit AudioEngine importiert werden kann
HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, SRC)

from audio_engine import AudioEngine  # noqa: E402


# --- Parameter (oben anpassbar) ---------------------------------------------

TONE_HZ = 1000.0           # Traeger-Frequenz (zeigt Pitch)
ENVELOPE_HZ = 5.0          # AM-Huellkurve (zeigt Tempo via Nulldurchgaenge)
ENVELOPE_DEPTH = 1.0       # 1.0 = volle Modulation (0..1), 0.5 = halb
TONE_SECONDS = 12.0
SAMPLE_RATE = 44100
CHANNELS = 2

# Zeitpunkte (Sekunden seit play())
T_PITCH_UP = 3.0       # set_pitch(+3) — eine Terz hoch
T_PITCH_BACK = 7.0     # set_pitch(0)  — wieder runter
T_STOP = 11.0          # capture stoppen
PITCH_UP_SEMITONES = 3.0

# Ausgabe
OUT_DIR = os.path.dirname(os.path.abspath(__file__))
OUT_WAV = os.path.join(OUT_DIR, "pitch_transition_capture.wav")
OUT_EVT = os.path.join(OUT_DIR, "pitch_transition_events.txt")


def make_test_tone_wav() -> str:
    """Schreibt AM-modulierten Sinus als WAV in eine Tempdatei.

    s(t) = sin(2*pi*TONE_HZ*t) * (1 - depth/2 + depth/2 * sin(2*pi*ENVELOPE_HZ*t))

    Traeger-Frequenz → Pitch.
    Huellkurven-Frequenz → Tempo (via Nulldurchgang-Analyse).
    """
    n = int(TONE_SECONDS * SAMPLE_RATE)
    t = np.arange(n, dtype=np.float64) / SAMPLE_RATE
    carrier = np.sin(2.0 * np.pi * TONE_HZ * t)
    # Huellkurve schwingt um 1.0 (Mittelwert), Amplitude depth/2
    envelope = (1.0 - ENVELOPE_DEPTH / 2.0) + (ENVELOPE_DEPTH / 2.0) * np.sin(
        2.0 * np.pi * ENVELOPE_HZ * t
    )
    # Sanftes Fade-In/Out, damit kein Klick am Datei-Anfang/Ende reinmischt
    fade_n = int(0.02 * SAMPLE_RATE)
    fade = np.ones(n, dtype=np.float64)
    fade[:fade_n] = np.linspace(0.0, 1.0, fade_n)
    fade[-fade_n:] = np.linspace(1.0, 0.0, fade_n)
    mono = 0.5 * carrier * envelope * fade
    if CHANNELS == 2:
        data = np.stack([mono, mono], axis=1).astype(np.float32)
    else:
        data = mono.astype(np.float32).reshape(-1, 1)
    fd, path = tempfile.mkstemp(suffix=".wav", prefix="pitch_test_")
    os.close(fd)
    sf.write(path, data, SAMPLE_RATE, subtype="FLOAT")
    return path


def main():
    tone_path = make_test_tone_wav()
    print(f"[Test] Test-Ton geschrieben: {tone_path}")

    eng = AudioEngine()
    eng.load(tone_path)
    print(f"[Test] Engine geladen: sr={eng.sample_rate}, ch={eng.channels}")

    # Capture starten BEVOR play() — Buffer steht direkt ab dem ersten Callback
    eng.start_output_capture(seconds=T_STOP + 1.0)

    eng.play()
    t0 = time.monotonic()

    pitch_up_done = False
    pitch_back_done = False
    while True:
        elapsed = time.monotonic() - t0
        if not pitch_up_done and elapsed >= T_PITCH_UP:
            eng.capture_mark(f"set_pitch({PITCH_UP_SEMITONES:+.2f})")
            eng.set_pitch(PITCH_UP_SEMITONES)
            print(f"[Test] t={elapsed:.3f}s set_pitch({PITCH_UP_SEMITONES:+.2f})")
            pitch_up_done = True
        if not pitch_back_done and elapsed >= T_PITCH_BACK:
            eng.capture_mark("set_pitch(0.0)")
            eng.set_pitch(0.0)
            print(f"[Test] t={elapsed:.3f}s set_pitch(0.0)")
            pitch_back_done = True
        if elapsed >= T_STOP:
            break
        time.sleep(0.005)

    samples, sr, events = eng.stop_output_capture()
    eng.stop()
    if eng.stream:
        try:
            eng.stream.close()
        except Exception:
            pass

    if samples is None or len(samples) == 0:
        print("[Test] FEHLER: kein Capture-Output. Wurde der Stream geoeffnet?")
        return 1

    # Mono fuer Analyse (Stereo war eh identisch)
    mono = samples.mean(axis=1) if samples.ndim == 2 else samples
    sf.write(OUT_WAV, mono.astype(np.float32), sr, subtype="FLOAT")
    print(f"[Test] Capture geschrieben: {OUT_WAV} ({len(mono)/sr:.2f}s @ {sr} Hz)")

    with open(OUT_EVT, "w", encoding="utf-8") as f:
        f.write(f"# sample_rate {sr}\n")
        for idx, tag in events:
            f.write(f"{idx}\t{idx/sr:.4f}\t{tag}\n")
    print(f"[Test] Events geschrieben: {OUT_EVT}")

    try:
        os.remove(tone_path)
    except OSError:
        pass

    print("[Test] Fertig. Analyse:  python pitch_transition_analyze.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
