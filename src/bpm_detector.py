"""
BPM-Erkennung und Beat-Grid fuer Square-Dance-Musik.
Verwendet nur scipy + numpy + soundfile (keine neuen Dependencies).

Ansatz: Onset-Strength-Envelope + Comb-Filter-Bank fuer feine BPM-Aufloesung.
Beat-Grid: Phase-Offset-Suche fuer exakte Beat-Zeitpunkte.
"""

import numpy as np
import soundfile as sf
from scipy import signal


# Square-Dance-Musik (von/fuer Square Dance produziert) liegt praktisch immer im
# Band 115-135 BPM. Alles darunter oder darueber ist Fremdmaterial und wird
# bewusst in dieses Band gezwungen. Das sehr enge Band (135/115 = 1.17, deutlich
# unter einer Oktave) verhindert, dass der Comb-Filter auf einer Sub-/Superharm-
# onischen oder auf einem falschen metrischen Puls einrastet:
#   - frueher: "Waltzing Matilda" als 90-BPM-Walzer (Subharmonische)
#   - frueher: "Quando, Quando, Quando" als 104 statt 130 — der 4er-Puls (104)
#     resonierte staerker als der echte 5er-Puls (130); beide sind Vielfache von
#     ~26 BPM, also KEIN Oktavfehler, den die Vielfachen-Korrektur unten faengt.
# Beide Faelle fallen jetzt aus dem Band heraus, wodurch der korrekte Wert gewinnt.
# Anpassbar ueber die min_bpm/max_bpm-Parameter, falls ein Song wirklich ausserhalb
# liegt (die Vielfachen-Korrektur unten greift dann wieder als Schutz).
_MIN_BPM_DEFAULT = 115.0
_MAX_BPM_DEFAULT = 135.0


def detect_bpm(filepath: str, min_bpm: float = _MIN_BPM_DEFAULT,
               max_bpm: float = _MAX_BPM_DEFAULT) -> float:
    """
    Erkennt die BPM eines Audio-Files via Onset + Comb-Filter-Bank.

    Args:
        filepath: Pfad zur Audio-Datei (MP3, WAV, FLAC, ...)
        min_bpm: Untere Grenze fuer BPM-Suche (Default 115)
        max_bpm: Obere Grenze fuer BPM-Suche (Default 135)

    Returns:
        Erkannte BPM als float (1 Dezimalstelle)

    Raises:
        RuntimeError: Wenn BPM nicht erkannt werden konnte
    """
    # 1) Audio laden
    data, sr = sf.read(filepath, dtype='float32')

    # 2) Mono-Downmix
    if data.ndim > 1:
        mono = np.mean(data, axis=1)
    else:
        mono = data

    # 3) Auf 22050 Hz resamplen (spart Rechenzeit)
    target_sr = 22050
    if sr != target_sr:
        num_samples = int(len(mono) * target_sr / sr)
        mono = signal.resample(mono, num_samples)
        sr = target_sr

    # 4) Onset-Strength-Envelope (kleiner Hop fuer bessere Aufloesung)
    onset_env = _onset_strength(mono, sr)

    # 5) Comb-Filter-Bank → feingranulare BPM-Suche
    bpm = _comb_filter_bpm(onset_env, sr, min_bpm, max_bpm)

    if bpm <= 0:
        raise RuntimeError("BPM konnte nicht erkannt werden")

    return round(bpm, 1)


# Globale Konstante fuer Hop-Size
_HOP = 128  # ~5.8ms bei 22050 Hz → onset_sr ~172 Hz


def _onset_strength(mono: np.ndarray, sr: int) -> np.ndarray:
    """Berechnet Onset-Strength-Envelope via spektrale Differenz."""
    nperseg = 1024
    hop = _HOP

    # Spectrogram (Magnitude)
    _, _, Sxx = signal.spectrogram(
        mono, fs=sr, nperseg=nperseg, noverlap=nperseg - hop,
        mode='magnitude'
    )

    # Spektrale Differenz: positive Aenderungen summieren (Half-Wave Rectification)
    diff = np.diff(Sxx, axis=1)
    diff = np.maximum(diff, 0)
    onset = np.sum(diff, axis=0)

    # Normalisieren
    if onset.max() > 0:
        onset = onset / onset.max()

    return onset


def _comb_filter_bpm(onset: np.ndarray, sr: int,
                      min_bpm: float, max_bpm: float) -> float:
    """
    Comb-Filter-Bank: Fuer jeden Kandidaten-BPM wird ein Kamm-Filter
    auf die Onset-Envelope angewendet. Der BPM mit der hoechsten
    Resonanz gewinnt. Aufloesung: 0.1 BPM.
    """
    onset_sr = sr / _HOP
    n = len(onset)

    # Kandidaten in 0.1 BPM Schritten
    bpm_candidates = np.arange(min_bpm, max_bpm + 0.05, 0.1)
    scores = np.zeros(len(bpm_candidates))

    for i, bpm in enumerate(bpm_candidates):
        # Periode in Onset-Samples
        period = onset_sr * 60.0 / bpm

        # Comb-Filter: Summe der Onset-Werte an Beat-Positionen
        # Ueber mehrere Phasen mitteln (phasen-unabhaengig)
        num_phases = max(4, int(period / 2))
        num_phases = min(num_phases, 16)
        phase_scores = np.zeros(num_phases)

        for p in range(num_phases):
            phase_offset = p * period / num_phases
            # Beat-Positionen fuer diese Phase
            positions = np.arange(phase_offset, n, period)
            indices = np.round(positions).astype(int)
            indices = indices[indices < n]
            if len(indices) > 0:
                phase_scores[p] = np.sum(onset[indices]) / len(indices)

        # Beste Phase zaehlt (Caller startet nicht immer auf Beat 1)
        scores[i] = np.max(phase_scores)

    # Besten BPM-Kandidaten finden
    best_idx = np.argmax(scores)
    if scores[best_idx] <= 0:
        return 0.0

    raw_bpm = bpm_candidates[best_idx]
    raw_score = scores[best_idx]

    # Sub-Harmonischen-Korrektur: Pruefen ob ein Vielfaches (×2, ×3/2, ×3)
    # einen aehnlich guten Score hat — dann ist das hoehere Tempo korrekt,
    # weil der niedrigere Wert nur jeden 2./3. Beat trifft.
    multipliers = [2.0, 1.5, 3.0]
    for mult in multipliers:
        candidate = raw_bpm * mult
        if candidate < min_bpm or candidate > max_bpm:
            continue
        # Score des Kandidaten nachschlagen
        idx = int(round((candidate - min_bpm) / 0.1))
        if 0 <= idx < len(scores):
            # Vielfaches gewinnt wenn sein Score mindestens 80% des Rohwerts erreicht
            if scores[idx] >= raw_score * 0.80:
                raw_bpm = bpm_candidates[idx]
                raw_score = scores[idx]
                break  # Nur einmal korrigieren

    return raw_bpm


def detect_beat_grid(filepath: str, bpm: float = None,
                     min_bpm: float = _MIN_BPM_DEFAULT,
                     max_bpm: float = _MAX_BPM_DEFAULT):
    """
    Berechnet ein Beat-Grid (Array aller Beat-Zeitpunkte) fuer einen Song.

    Args:
        filepath: Pfad zur Audio-Datei
        bpm: Bekannte BPM (optional, sonst Auto-Detect)
        min_bpm: Untere Grenze fuer BPM-Suche
        max_bpm: Obere Grenze fuer BPM-Suche

    Returns:
        (bpm, beat_times) — bpm als float, beat_times als numpy-Array in Sekunden
    """
    # Audio laden + Mono-Downmix + Resample (gleicher Code wie detect_bpm)
    data, sr = sf.read(filepath, dtype='float32')
    if data.ndim > 1:
        mono = np.mean(data, axis=1)
    else:
        mono = data

    target_sr = 22050
    if sr != target_sr:
        num_samples = int(len(mono) * target_sr / sr)
        mono = signal.resample(mono, num_samples)
        sr = target_sr

    duration = len(mono) / sr

    # BPM ermitteln falls nicht angegeben
    if bpm is None or bpm <= 0:
        onset_env = _onset_strength(mono, sr)
        bpm = _comb_filter_bpm(onset_env, sr, min_bpm, max_bpm)
        if bpm <= 0:
            raise RuntimeError("BPM konnte nicht erkannt werden")
        bpm = round(bpm, 1)
    else:
        onset_env = _onset_strength(mono, sr)

    # Phase-Offset finden: wo faellt der erste Beat?
    onset_sr = sr / _HOP
    period = onset_sr * 60.0 / bpm  # Beat-Abstand in Onset-Samples
    n = len(onset_env)

    # Alle moeglichen Phase-Offsets testen (feine Aufloesung)
    num_phases = max(8, int(period))
    num_phases = min(num_phases, int(period * 2))
    best_phase = 0.0
    best_score = -1.0

    for p in range(num_phases):
        phase_offset = p * period / num_phases
        positions = np.arange(phase_offset, n, period)
        indices = np.round(positions).astype(int)
        indices = indices[indices < n]
        if len(indices) > 0:
            score = np.sum(onset_env[indices]) / len(indices)
            if score > best_score:
                best_score = score
                best_phase = phase_offset

    # Phase-Offset in Sekunden umrechnen
    first_beat = best_phase / onset_sr

    # Beat-Grid generieren
    beat_interval = 60.0 / bpm
    beat_times = np.arange(first_beat, duration, beat_interval)

    return (bpm, beat_times)
