"""
Pitch-Transition-Analyse
========================
Liest `pitch_transition_capture.wav` + `pitch_transition_events.txt` und
zeichnet die Momentan-Frequenz des aufgenommenen Test-Tons ueber die Zeit.

Methode:
  1. STFT mit nperseg=4096, hop=256 (≈ 5,8 ms Aufloesung bei 44,1 kHz)
  2. Pro Fenster: dominanten Spektral-Peak suchen, parabolisch interpolieren
     (Sub-Bin-Aufloesung — wichtig bei nur 4096 Bins)
  3. Plot f(t), mit vertikalen Linien an den set_pitch-Events
  4. Kennzahlen pro Transition (Einschwingdauer, max. Abweichung, RMS)

Aufruf:
    python pitch_transition_analyze.py
    python pitch_transition_analyze.py mein_capture.wav
"""

from __future__ import annotations

import os
import sys
import numpy as np
import soundfile as sf
from scipy.signal import stft, butter, sosfiltfilt

try:
    import matplotlib.pyplot as plt
    HAVE_MPL = True
except ImportError:
    HAVE_MPL = False


HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_WAV = os.path.join(HERE, "pitch_transition_capture.wav")
DEFAULT_EVT = os.path.join(HERE, "pitch_transition_events.txt")

NPERSEG = 4096
HOP = 256
SETTLE_TOLERANCE_HZ = 1.0   # ab wann gilt der Pitch als "eingeschwungen"

# Erwartete Huellkurve im Test-Signal — muss mit pitch_transition_test.py uebereinstimmen
EXPECTED_ENVELOPE_HZ = 5.0
ENV_LP_CUTOFF = 50.0        # Tiefpass nach Gleichrichtung (Hz) — laesst Huellkurve durch, killt Traeger
ENV_HP_CUTOFF = 1.0         # Hochpass — entfernt DC-Offset der gleichgerichteten Huellkurve


def load_events(path: str):
    """Liest sample_index + tag aus events.txt. Gibt Liste (zeit_s, tag) zurueck."""
    out = []
    sr_from_file = None
    if not os.path.exists(path):
        return out, sr_from_file
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            if line.startswith("#"):
                if "sample_rate" in line:
                    try:
                        sr_from_file = int(line.split()[-1])
                    except ValueError:
                        pass
                continue
            parts = line.split("\t")
            if len(parts) >= 3:
                try:
                    t = float(parts[1])
                    tag = parts[2]
                    out.append((t, tag))
                except ValueError:
                    pass
    return out, sr_from_file


def parabolic_peak(spectrum: np.ndarray) -> tuple[float, float]:
    """Findet Peak-Bin und interpoliert sub-bin (gibt (bin_float, mag) zurueck)."""
    k = int(np.argmax(spectrum))
    if 0 < k < len(spectrum) - 1:
        a, b, c = spectrum[k - 1], spectrum[k], spectrum[k + 1]
        denom = (a - 2 * b + c)
        if abs(denom) > 1e-12:
            offset = 0.5 * (a - c) / denom
            return k + offset, float(b)
    return float(k), float(spectrum[k])


def instantaneous_frequency(samples: np.ndarray, sr: int) -> tuple[np.ndarray, np.ndarray]:
    """STFT-basiertes Peak-Tracking. Liefert (t_s, f_hz)."""
    f, t, Z = stft(
        samples,
        fs=sr,
        window="hann",
        nperseg=NPERSEG,
        noverlap=NPERSEG - HOP,
        boundary=None,
        padded=False,
        return_onesided=True,
    )
    mag = np.abs(Z)
    bin_hz = sr / NPERSEG
    f_inst = np.zeros(mag.shape[1], dtype=np.float64)
    for i in range(mag.shape[1]):
        bin_float, _ = parabolic_peak(mag[:, i])
        f_inst[i] = bin_float * bin_hz
    return t, f_inst


def semitones_to_ratio(s: float) -> float:
    return 2.0 ** (s / 12.0)


def extract_envelope(samples: np.ndarray, sr: int) -> np.ndarray:
    """Halbwellen-gleichrichten + Tiefpass + Hochpass -> AM-Huellkurve um Null.

    Ergebnis schwingt symmetrisch um 0 -> saubere Nulldurchgangs-Detektion moeglich.
    """
    rectified = np.abs(samples)
    sos_lp = butter(4, ENV_LP_CUTOFF / (sr / 2), btype="low", output="sos")
    env = sosfiltfilt(sos_lp, rectified)
    sos_hp = butter(2, ENV_HP_CUTOFF / (sr / 2), btype="high", output="sos")
    env_ac = sosfiltfilt(sos_hp, env)
    return env_ac


def rising_zero_crossings(signal: np.ndarray, sr: int) -> np.ndarray:
    """Findet steigende Nulldurchgaenge mit Sub-Sample-Interpolation. Gibt Zeiten in s zurueck."""
    s = np.asarray(signal)
    # Index k mit s[k] < 0 <= s[k+1]
    cross_idx = np.where((s[:-1] < 0.0) & (s[1:] >= 0.0))[0]
    if len(cross_idx) == 0:
        return np.array([], dtype=np.float64)
    y0 = s[cross_idx]
    y1 = s[cross_idx + 1]
    denom = (y1 - y0)
    # Lineare Interpolation: t = (k + (-y0 / (y1-y0))) / sr
    frac = np.where(denom != 0.0, -y0 / denom, 0.0)
    return (cross_idx.astype(np.float64) + frac) / sr


def envelope_frequency_curve(env_ac: np.ndarray, sr: int):
    """Liefert (mid_times_s, env_freq_hz) — Momentan-Periodendauer zwischen aufeinanderfolgenden
    steigenden Nulldurchgaengen, invertiert zur Frequenz."""
    zc = rising_zero_crossings(env_ac, sr)
    if len(zc) < 2:
        return np.array([]), np.array([])
    periods = np.diff(zc)
    mid = 0.5 * (zc[:-1] + zc[1:])
    freq = 1.0 / periods
    return mid, freq


def analyze_transition(t: np.ndarray, f: np.ndarray, t_event: float,
                       f_target: float, label: str):
    """Druckt Kennzahlen fuer ein Uebergangsfenster."""
    # Fenster: t_event bis +3 s
    mask = (t >= t_event) & (t <= t_event + 3.0)
    if not mask.any():
        print(f"  {label}: kein Fenster gefunden (t_event={t_event:.3f}s)")
        return
    tt = t[mask] - t_event
    ff = f[mask]
    err = ff - f_target

    # Settle-Time: erster Index ab dem |err| dauerhaft (>= 100 ms) unter Toleranz bleibt
    win_n = max(1, int(0.1 * len(tt) / (tt[-1] if tt[-1] > 0 else 1.0)))
    settle_t = None
    for i in range(len(tt)):
        if i + win_n <= len(tt) and np.all(np.abs(err[i:i + win_n]) < SETTLE_TOLERANCE_HZ):
            settle_t = tt[i]
            break

    max_dev = float(np.max(np.abs(err)))
    rms_dev = float(np.sqrt(np.mean(err ** 2)))
    settle_str = f"{settle_t*1000:.0f} ms" if settle_t is not None else ">3000 ms"

    print(f"  {label}")
    print(f"    Ziel-Frequenz:      {f_target:.2f} Hz")
    print(f"    Einschwingzeit:     {settle_str}  (Toleranz ±{SETTLE_TOLERANCE_HZ} Hz, 100 ms stabil)")
    print(f"    Max. Abweichung:    {max_dev:6.2f} Hz")
    print(f"    RMS-Abweichung:     {rms_dev:6.2f} Hz")


def main(argv: list[str]):
    wav_path = argv[1] if len(argv) > 1 else DEFAULT_WAV
    evt_path = DEFAULT_EVT
    if not os.path.exists(wav_path):
        print(f"FEHLER: {wav_path} nicht gefunden — vorher pitch_transition_test.py laufen lassen.")
        return 1

    samples, sr = sf.read(wav_path, dtype="float64", always_2d=False)
    if samples.ndim == 2:
        samples = samples.mean(axis=1)
    print(f"[Analyse] {wav_path}: {len(samples)/sr:.2f}s @ {sr} Hz")

    events, sr_from_file = load_events(evt_path)
    if sr_from_file and sr_from_file != sr:
        print(f"[Warn] WAV-SR={sr} aber events.txt-SR={sr_from_file}")

    t, f_inst = instantaneous_frequency(samples, sr)
    print(f"[Analyse] STFT-Frames: {len(t)}  (Aufloesung {(t[1]-t[0])*1000:.2f} ms)")

    # Huellkurven-Analyse (Tempo via Nulldurchgaenge)
    env_ac = extract_envelope(samples, sr)
    env_t, env_f = envelope_frequency_curve(env_ac, sr)
    if len(env_t):
        print(f"[Analyse] Huellkurven-Nulldurchgaenge: {len(env_t)+1}  "
              f"(Soll 5 Hz -> ~{int(len(samples)/sr*EXPECTED_ENVELOPE_HZ)} Perioden)")

    # Erwartete Plateau-Frequenz aus Events ableiten
    print("\n[Kennzahlen pro Transition — TRAEGER (Pitch)]")
    base_hz = 1000.0
    current_target = base_hz
    for (t_evt, tag) in events:
        # set_pitch(X) — Ziel-Frequenz neu berechnen
        if "set_pitch" in tag:
            try:
                inner = tag.split("(", 1)[1].rsplit(")", 1)[0]
                semitones = float(inner)
                new_target = base_hz * semitones_to_ratio(semitones)
            except (ValueError, IndexError):
                new_target = current_target
            analyze_transition(t, f_inst, t_evt, new_target,
                               f"t={t_evt:.2f}s  {tag}  ->  Soll {new_target:.2f} Hz")
            current_target = new_target

    # Tempo-Kennzahlen ueber die Huellkurve
    print("\n[Kennzahlen pro Transition — HUELLKURVE (Tempo)]")
    print(f"  Soll-Huellkurve: {EXPECTED_ENVELOPE_HZ:.2f} Hz")
    if len(env_t):
        for (t_evt, tag) in events:
            mask = (env_t >= t_evt) & (env_t <= t_evt + 4.0)
            if mask.any():
                ff = env_f[mask]
                dev = ff - EXPECTED_ENVELOPE_HZ
                print(f"  t={t_evt:.2f}s  {tag}")
                print(f"    Min/Max Huellkurve: {ff.min():.3f} / {ff.max():.3f} Hz")
                print(f"    Max. Abweichung:    {np.max(np.abs(dev)):.3f} Hz  "
                      f"({np.max(np.abs(dev))/EXPECTED_ENVELOPE_HZ*100:.1f} %)")
                print(f"    RMS-Abweichung:     {np.sqrt(np.mean(dev**2)):.3f} Hz")

    # Plot — zwei Subplots: Traeger oben, Huellkurve unten
    if HAVE_MPL:
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(11, 7), sharex=True)
        # Subplot 1: Traegerfrequenz
        ax1.plot(t, f_inst, lw=0.9, color="tab:blue", label="Traeger (Pitch)")
        ax1.set_ylabel("Traeger-Frequenz (Hz)")
        ax1.set_title("Pitch-Transition — Traeger (Pitch) und Huellkurve (Tempo)")
        ax1.grid(alpha=0.3)
        # Subplot 2: Huellkurve
        if len(env_t):
            ax2.plot(env_t, env_f, lw=1.0, color="tab:orange",
                     marker="o", markersize=2, label="Huellkurve (Tempo)")
        ax2.axhline(EXPECTED_ENVELOPE_HZ, color="gray", ls=":", lw=0.8,
                    label=f"Soll {EXPECTED_ENVELOPE_HZ} Hz")
        ax2.set_xlabel("Zeit (s)")
        ax2.set_ylabel("Huellkurven-Frequenz (Hz)")
        ax2.grid(alpha=0.3)
        ax2.legend(loc="lower right", fontsize=8)
        # Event-Marker auf beiden Subplots
        for (t_evt, tag) in events:
            for ax in (ax1, ax2):
                ax.axvline(t_evt, color="red", ls="--", lw=0.8)
            ax1.text(t_evt, ax1.get_ylim()[1], tag, rotation=90,
                     va="top", ha="right", fontsize=8, color="red")
        out_png = os.path.splitext(wav_path)[0] + ".png"
        fig.tight_layout()
        fig.savefig(out_png, dpi=120)
        print(f"\n[Analyse] Plot gespeichert: {out_png}")
        plt.show()
    else:
        print("\n[Hinweis] matplotlib nicht installiert — Plot uebersprungen.")
        print("          pip install matplotlib  fuer Diagramm.")

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
