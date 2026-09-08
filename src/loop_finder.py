"""
Auto-Loop-Finder fuer Square-Dance-Musik.

Sucht im ersten und letzten Viertel eines Songs nach klanglich aehnlichen
Stellen, die gute Loop-Kandidaten ergeben.

Kernidee: Alle Beats werden von Anfang an durchnummeriert (1-8, 1-8, ...).
Loop-In und Loop-Out muessen auf derselben Beat-Position liegen, damit der
Sprung musikalisch unsichtbar ist. Kein Downbeat-Raten noetig.

Verwendet nur scipy + numpy + soundfile (keine neuen Dependencies).
"""

import numpy as np
import soundfile as sf
from scipy import signal as sig
from dataclasses import dataclass

from bpm_detector import detect_beat_grid, _onset_strength, _HOP


# ---------------------------------------------------------------------------
# Datenstrukturen
# ---------------------------------------------------------------------------

@dataclass
class LoopCandidate:
    """Ein Loop-Vorschlag mit Bewertung."""
    loop_in: float          # Sekunden
    loop_out: float         # Sekunden
    score: float            # 0.0 - 1.0 Gesamtscore
    chroma_score: float     # Harmonie-Aehnlichkeit
    onset_score: float      # Rhythmus-Aehnlichkeit
    energy_score: float     # Lautstaerke-Aehnlichkeit
    beat_pos: int           # Beat-Position im 8er-Raster (1-8)
    loop_beats: int         # Laenge des Loops in Beats
    downbeat: int = 0       # Erkannter Downbeat (1-8), 0=unbekannt


# ---------------------------------------------------------------------------
# Haupt-API
# ---------------------------------------------------------------------------

def find_loop_candidates(filepath: str, bpm: float = None,
                         compare_beats: int = 16,
                         in_start: float = None, in_end: float = None,
                         out_start: float = None, out_end: float = None) -> list:
    """
    Findet die besten Loop-Kandidaten in einem Song.

    Alle Beats werden 1-8 durchnummeriert. Nur Paare mit gleicher
    Beat-Position werden zugelassen (Beat 1 -> Beat 1, Beat 5 -> Beat 5).

    Args:
        filepath: Pfad zur Audio-Datei
        bpm: Bekannte BPM (optional, sonst Auto-Detect)
        compare_beats: Groesse des Vergleichsfensters in Beats (4, 8, 16, 32, 64)
        in_start/in_end: Suchbereich fuer Loop-In (Sekunden), Default: 0 bis 25%
        out_start/out_end: Suchbereich fuer Loop-Out (Sekunden), Default: 75% bis Ende

    Returns:
        Liste von LoopCandidate, sortiert nach Score (beste zuerst)
    """
    # 1) Audio laden
    mono, sr = _load_audio(filepath)
    duration = len(mono) / sr

    # 2) Beat-Grid erzeugen
    detected_bpm, beat_times = detect_beat_grid(filepath, bpm=bpm)

    if len(beat_times) < 16:
        return []  # Song zu kurz

    # 3) Beats durchnummerieren (1-8, 1-8, ...)
    beat_positions = np.array([(i % 8) + 1 for i in range(len(beat_times))])

    # 4) Downbeat erkennen: welche Beat-Position (1-8) ist die musikalische "1"?
    downbeat_pos = _estimate_downbeat(mono, sr, beat_times, beat_positions)

    # 5) Features pro Beat berechnen
    chroma_per_beat = _compute_chroma_per_beat(mono, sr, beat_times, duration)
    onset_per_beat = _compute_onset_per_beat(mono, sr, beat_times, duration)
    energy_per_beat = _compute_energy_per_beat(mono, sr, beat_times, duration)

    # 6) Suchbereiche: Default = 1. Viertel / letztes Viertel
    if in_start is None:
        in_start = 0.0
    if in_end is None:
        in_end = duration * 0.25
    if out_start is None:
        out_start = duration * 0.75
    if out_end is None:
        out_end = duration

    # 7) Kandidaten sammeln: nur Paare mit gleicher Beat-Position
    candidates = _find_and_score_candidates(
        beat_times, beat_positions, downbeat_pos,
        chroma_per_beat, onset_per_beat, energy_per_beat,
        duration, compare_beats,
        in_start, in_end, out_start, out_end
    )

    # 7) Nach Score sortieren, deduplizieren — ALLE zurueckgeben
    candidates.sort(key=lambda c: c.score, reverse=True)
    return _deduplicate(candidates, min_distance=2.0)


# ---------------------------------------------------------------------------
# Audio laden
# ---------------------------------------------------------------------------

def _load_audio(filepath: str, target_sr: int = 22050):
    """Laedt Audio als Mono, resampled auf target_sr."""
    data, sr = sf.read(filepath, dtype='float32')
    if data.ndim > 1:
        mono = np.mean(data, axis=1)
    else:
        mono = data

    if sr != target_sr:
        num_samples = int(len(mono) * target_sr / sr)
        mono = sig.resample(mono, num_samples)
        sr = target_sr

    return mono, sr


# ---------------------------------------------------------------------------
# Downbeat-Erkennung
# ---------------------------------------------------------------------------

def _estimate_downbeat(mono: np.ndarray, sr: int,
                       beat_times: np.ndarray,
                       beat_positions: np.ndarray) -> int:
    """
    Schaetzt welche Beat-Position (1-8) der musikalische Downbeat ist.

    Kombiniert drei Signale:
    1. Bass-Energie (Kick-Drum): Downbeat hat typisch die staerkste Kick
    2. Harmonie-Wechsel: Akkordwechsel passieren oft auf dem Downbeat
    3. Gesamtenergie-Akzent: Downbeat ist oft der lauteste Beat

    Returns:
        Beat-Position 1-8 die am wahrscheinlichsten der Downbeat ist
    """
    if len(beat_times) < 16:
        return 1

    # --- Signal 1: Bass/Kick-Energie pro Beat-Position ---
    nyq = sr / 2
    cutoff = min(150.0, nyq * 0.9)
    b, a = sig.butter(4, cutoff / nyq, btype='low')
    bass = sig.filtfilt(b, a, mono)

    window_samples = int(0.04 * sr)  # 40ms Fenster
    bass_per_pos = np.zeros(8)
    counts = np.zeros(8)

    for i, t in enumerate(beat_times):
        center = int(t * sr)
        start = max(0, center - window_samples)
        end = min(len(bass), center + window_samples)
        if end > start:
            pos = int(beat_positions[i]) - 1  # 0-basiert
            bass_per_pos[pos] += np.mean(bass[start:end] ** 2)
            counts[pos] += 1

    # Mittelwert pro Position
    for p in range(8):
        if counts[p] > 0:
            bass_per_pos[p] /= counts[p]

    # --- Signal 2: Harmonie-Wechsel (Chroma-Differenz) ---
    # Grobe Chroma pro Beat, dann Differenz zum Vorgaenger
    n_fft = 4096
    chroma_diff_per_pos = np.zeros(8)
    diff_counts = np.zeros(8)
    prev_chroma = None

    for i, t in enumerate(beat_times):
        start_smp = int(t * sr)
        end_smp = start_smp + n_fft
        if end_smp > len(mono):
            continue

        frame = mono[start_smp:end_smp] * np.hanning(n_fft)
        spectrum = np.abs(np.fft.rfft(frame))
        freqs = np.fft.rfftfreq(n_fft, 1.0 / sr)

        chroma = np.zeros(12)
        mask = (freqs >= 65.0) & (freqs <= 2100.0)
        for f, mag in zip(freqs[mask], spectrum[mask]):
            note = _freq_to_chroma(f)
            if 0 <= note < 12:
                chroma[note] += mag ** 2

        norm = np.linalg.norm(chroma)
        if norm > 0:
            chroma /= norm

        if prev_chroma is not None:
            diff = np.linalg.norm(chroma - prev_chroma)
            pos = int(beat_positions[i]) - 1
            chroma_diff_per_pos[pos] += diff
            diff_counts[pos] += 1

        prev_chroma = chroma

    for p in range(8):
        if diff_counts[p] > 0:
            chroma_diff_per_pos[p] /= diff_counts[p]

    # --- Signal 3: Gesamtenergie-Akzent ---
    energy_per_pos = np.zeros(8)
    e_counts = np.zeros(8)

    for i, t in enumerate(beat_times):
        center = int(t * sr)
        start = max(0, center - window_samples)
        end = min(len(mono), center + window_samples)
        if end > start:
            pos = int(beat_positions[i]) - 1
            energy_per_pos[pos] += np.mean(mono[start:end] ** 2)
            e_counts[pos] += 1

    for p in range(8):
        if e_counts[p] > 0:
            energy_per_pos[p] /= e_counts[p]

    # --- Normalisieren und kombinieren ---
    def _normalize(arr):
        mx = arr.max()
        if mx > 0:
            return arr / mx
        return arr

    bass_norm = _normalize(bass_per_pos)
    chroma_norm = _normalize(chroma_diff_per_pos)
    energy_norm = _normalize(energy_per_pos)

    # Gewichteter Score: Bass (Kick) am wichtigsten, dann Harmonie, dann Energie
    combined = 0.45 * bass_norm + 0.35 * chroma_norm + 0.20 * energy_norm

    best_pos = int(np.argmax(combined)) + 1  # 1-basiert
    return best_pos


# ---------------------------------------------------------------------------
# Chroma-Berechnung (FFT -> 12 Halbtoene)
# ---------------------------------------------------------------------------

_A4 = 440.0
_MIN_FREQ = 65.0    # C2
_MAX_FREQ = 2100.0  # C7


def _freq_to_chroma(freq: float) -> int:
    """Ordnet eine Frequenz einem der 12 Halbtoene zu (0-11)."""
    if freq <= 0:
        return -1
    return int(round(12 * np.log2(freq / _A4))) % 12


def _compute_chroma(segment: np.ndarray, sr: int) -> np.ndarray:
    """
    Berechnet einen 12-dimensionalen Chroma-Vektor fuer ein Audio-Segment.
    FFT -> Frequenz-Bins -> auf 12 Halbtoene mappen -> normalisieren.
    """
    n_fft = 4096
    if len(segment) < n_fft:
        segment = np.pad(segment, (0, n_fft - len(segment)))

    window = np.hanning(n_fft)
    hop = n_fft // 2
    chroma = np.zeros(12)
    n_frames = 0

    for start in range(0, len(segment) - n_fft, hop):
        frame = segment[start:start + n_fft] * window
        spectrum = np.abs(np.fft.rfft(frame))
        freqs = np.fft.rfftfreq(n_fft, 1.0 / sr)

        mask = (freqs >= _MIN_FREQ) & (freqs <= _MAX_FREQ)
        for f, mag in zip(freqs[mask], spectrum[mask]):
            bin_idx = _freq_to_chroma(f)
            if 0 <= bin_idx < 12:
                chroma[bin_idx] += mag ** 2
        n_frames += 1

    if n_frames > 0:
        chroma /= n_frames

    norm = np.linalg.norm(chroma)
    if norm > 0:
        chroma /= norm

    return chroma


def _compute_chroma_per_beat(mono: np.ndarray, sr: int,
                             beat_times: np.ndarray,
                             duration: float) -> np.ndarray:
    """Berechnet Chroma-Vektor fuer jeden Beat."""
    n_beats = len(beat_times)
    chroma_matrix = np.zeros((n_beats, 12))

    for i in range(n_beats):
        start_sec = beat_times[i]
        end_sec = beat_times[i + 1] if i + 1 < n_beats else duration
        start_smp = int(start_sec * sr)
        end_smp = min(int(end_sec * sr), len(mono))

        if end_smp > start_smp:
            chroma_matrix[i] = _compute_chroma(mono[start_smp:end_smp], sr)

    return chroma_matrix


# ---------------------------------------------------------------------------
# Onset-Staerke pro Beat
# ---------------------------------------------------------------------------

def _compute_onset_per_beat(mono: np.ndarray, sr: int,
                            beat_times: np.ndarray,
                            duration: float) -> np.ndarray:
    """Berechnet Onset-Staerke pro Beat (Skalar, nicht Pattern)."""
    onset_env = _onset_strength(mono, sr)
    onset_sr = sr / _HOP
    n_beats = len(beat_times)
    onset_values = np.zeros(n_beats)

    for i in range(n_beats):
        t = beat_times[i]
        idx = int(t * onset_sr)
        win = int(0.03 * onset_sr)  # ~30ms
        start_idx = max(0, idx - win)
        end_idx = min(len(onset_env), idx + win + 1)
        if end_idx > start_idx:
            onset_values[i] = np.mean(onset_env[start_idx:end_idx])

    # Global normalisieren
    max_val = onset_values.max()
    if max_val > 0:
        onset_values /= max_val

    return onset_values


# ---------------------------------------------------------------------------
# Energie pro Beat
# ---------------------------------------------------------------------------

def _compute_energy_per_beat(mono: np.ndarray, sr: int,
                             beat_times: np.ndarray,
                             duration: float) -> np.ndarray:
    """Berechnet RMS-Energie pro Beat."""
    n_beats = len(beat_times)
    energy = np.zeros(n_beats)

    for i in range(n_beats):
        start_sec = beat_times[i]
        end_sec = beat_times[i + 1] if i + 1 < n_beats else duration
        start_smp = int(start_sec * sr)
        end_smp = min(int(end_sec * sr), len(mono))

        if end_smp > start_smp:
            energy[i] = np.sqrt(np.mean(mono[start_smp:end_smp] ** 2))

    return energy


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Kosinus-Aehnlichkeit zwischen zwei Vektoren (0-1)."""
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))


def _score_candidate(beat_in: int, beat_out: int,
                     chroma: np.ndarray, onset: np.ndarray,
                     energy: np.ndarray,
                     compare_beats: int = 16) -> dict:
    """
    Bewertet ein Loop-In/Loop-Out-Paar.

    Kernidee: Wir vergleichen die Phrase AB Loop-In mit der Phrase AB Loop-Out.
    Wenn beide gleich klingen, hoert man den Sprung nicht — denn der Player
    springt von Loop-Out zurueck zu Loop-In, und dort beginnt dieselbe Musik.
    """
    n_beats = len(chroma)
    context = compare_beats

    # Chroma-Aehnlichkeit: Phrase AB Loop-In vs. Phrase AB Loop-Out
    chroma_scores = []
    for offset in range(context):
        in_beat = beat_in + offset
        out_beat = beat_out + offset
        if in_beat < n_beats and out_beat < n_beats:
            sim = _cosine_similarity(chroma[in_beat], chroma[out_beat])
            chroma_scores.append(sim)
    chroma_score = np.mean(chroma_scores) if chroma_scores else 0.0

    # Onset-Aehnlichkeit: gleiches Prinzip
    onset_scores = []
    for offset in range(context):
        in_beat = beat_in + offset
        out_beat = beat_out + offset
        if in_beat < n_beats and out_beat < n_beats:
            diff = abs(onset[in_beat] - onset[out_beat])
            onset_scores.append(1.0 - diff)
    onset_score = np.mean(onset_scores) if onset_scores else 0.0

    # Energie-Aehnlichkeit: RMS-Verhaeltnis
    energy_scores = []
    for offset in range(context):
        in_beat = beat_in + offset
        out_beat = beat_out + offset
        if in_beat < n_beats and out_beat < n_beats:
            e_in = energy[in_beat]
            e_out = energy[out_beat]
            if max(e_in, e_out) > 0:
                ratio = min(e_in, e_out) / max(e_in, e_out)
                energy_scores.append(ratio)
    energy_score = np.mean(energy_scores) if energy_scores else 0.0

    # Gewichteter Gesamtscore
    total = (0.40 * chroma_score
             + 0.35 * onset_score
             + 0.25 * energy_score)

    return {
        'score': total,
        'chroma_score': chroma_score,
        'onset_score': onset_score,
        'energy_score': energy_score,
    }


# ---------------------------------------------------------------------------
# Kandidaten-Suche
# ---------------------------------------------------------------------------

def _find_and_score_candidates(beat_times: np.ndarray,
                               beat_positions: np.ndarray,
                               downbeat_pos: int,
                               chroma: np.ndarray,
                               onset: np.ndarray,
                               energy: np.ndarray,
                               duration: float,
                               compare_beats: int = 16,
                               in_start: float = 0.0,
                               in_end: float = None,
                               out_start: float = None,
                               out_end: float = None) -> list:
    """
    Sammelt alle sinnvollen Loop-In/Loop-Out-Paare und bewertet sie.

    Regel: Loop-In und Loop-Out muessen dieselbe Beat-Position (1-8) haben.
    Bonus: Kandidaten auf dem erkannten Downbeat werden bevorzugt.
    Loop-In: nur Beats im Bereich [in_start, in_end]
    Loop-Out: nur Beats im Bereich [out_start, out_end]
    """
    if in_end is None:
        in_end = duration * 0.25
    if out_start is None:
        out_start = duration * 0.75
    if out_end is None:
        out_end = duration
    min_loop_beats = 16  # Mindestens 16 Beats (2 Phrasen)

    # Kandidaten-Beats nach Position gruppieren
    in_by_pos = {}   # {beat_pos: [beat_idx, ...]}
    out_by_pos = {}

    for i, t in enumerate(beat_times):
        pos = int(beat_positions[i])
        if in_start <= t <= in_end:
            in_by_pos.setdefault(pos, []).append(i)
        if out_start <= t <= out_end:
            out_by_pos.setdefault(pos, []).append(i)

    candidates = []

    # Nur Paare mit gleicher Beat-Position (1->1, 2->2, ..., 8->8)
    for pos in range(1, 9):
        in_beats = in_by_pos.get(pos, [])
        out_beats = out_by_pos.get(pos, [])

        for beat_in in in_beats:
            for beat_out in out_beats:
                loop_beats = beat_out - beat_in
                if loop_beats < min_loop_beats:
                    continue

                scores = _score_candidate(beat_in, beat_out,
                                          chroma, onset, energy,
                                          compare_beats)

                # Downbeat-Bonus: Kandidaten auf dem erkannten Downbeat
                # bekommen bis zu 15% Bonus. Je weiter weg vom Downbeat,
                # desto weniger Bonus.
                if pos == downbeat_pos:
                    downbeat_bonus = 0.15
                elif pos == ((downbeat_pos - 1 + 4) % 8) + 1:
                    # Halbtakt-Position (4 Beats versetzt) = kleiner Bonus
                    downbeat_bonus = 0.07
                else:
                    downbeat_bonus = 0.0

                total_score = scores['score'] * (1.0 - 0.15) + downbeat_bonus

                candidates.append(LoopCandidate(
                    loop_in=float(beat_times[beat_in]),
                    loop_out=float(beat_times[beat_out]),
                    score=total_score,
                    chroma_score=scores['chroma_score'],
                    onset_score=scores['onset_score'],
                    energy_score=scores['energy_score'],
                    beat_pos=pos,
                    loop_beats=loop_beats,
                    downbeat=downbeat_pos,
                ))

    return candidates


# ---------------------------------------------------------------------------
# Deduplizierung
# ---------------------------------------------------------------------------

def apply_selection_strategy(candidates: list, strategy: str) -> object:
    """
    Waehlt den besten Kandidaten gemaess der benannten Strategie.

    Strategien:
      "best_64"  — Hoechster Score unter Vielfachen von 64 Beats;
                   Fallback: hoechster Gesamtscore (candidates[0]).
      "best_8"   — Hoechster Score unter Vielfachen von 8 Beats;
                   Fallback: hoechster Gesamtscore (candidates[0]).
      Unbekannte Strategie: Fallback auf candidates[0].

    Args:
        candidates: Sortierte Liste von LoopCandidate (bester Score zuerst).
        strategy:   Strategie-Bezeichner (String).

    Returns:
        Gewahlter LoopCandidate, oder None wenn Liste leer.
    """
    if not candidates:
        return None

    if strategy == "best_64":
        best = None
        for c in candidates:
            if c.loop_beats > 0 and c.loop_beats % 64 == 0:
                if best is None or c.score > best.score:
                    best = c
        return best if best is not None else candidates[0]

    if strategy == "best_8":
        best = None
        for c in candidates:
            if c.loop_beats > 0 and c.loop_beats % 8 == 0:
                if best is None or c.score > best.score:
                    best = c
        return best if best is not None else candidates[0]

    # Unbekannte / zukuenftige Strategien: bester Gesamtscore
    return candidates[0]


# Verfuegbare Strategien (Name -> Anzeigetext fuer UI)
SELECTION_STRATEGIES = {
    "best_64": "Bestes Vielfaches von 64 Beats",
    "best_8": "Bestes Vielfaches von 8 Beats",
}


def _deduplicate(candidates: list, min_distance: float = 2.0) -> list:
    """
    Entfernt Kandidaten die zu nah beieinander liegen.
    Behaelt immer den mit dem hoeheren Score.
    """
    if not candidates:
        return []

    result = [candidates[0]]
    for c in candidates[1:]:
        too_close = False
        for existing in result:
            if (abs(c.loop_in - existing.loop_in) < min_distance and
                    abs(c.loop_out - existing.loop_out) < min_distance):
                too_close = True
                break
        if not too_close:
            result.append(c)

    return result
