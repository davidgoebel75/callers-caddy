"""Automatische Erkennung des Singing-Call-Body (Anfang + Ende).

Ein Singing Call besteht starr aus 7 Abschnitten a 64 Beats (= 448 Beats).
Intro und Outro davor/danach sind kuerzer/anders. Dieses Modul findet den
Zeitpunkt, an dem der Body beginnt (musikalischer Beat 1), und leitet das Ende
als Anfang + 448 Beats ab. Es liefert einen Vorschlag mit Confidence-Wert; der
Nutzer bestaetigt oder korrigiert ihn (kein stilles Schreiben).

Verfahren (offline validiert an 55 Gehoer-Marken, siehe tools/-Experimente):
  1. Beat-Grid via bpm_detector.detect_beat_grid — mit DB-BPM als Anker, sonst
     rutscht der Detektor auf Halb-/Doppeltempo (unmoegliche Grids).
  2. Beat-synchrones log-Mel-Timbre + Energie + Kick-Transient je Beat.
  3. Checkerboard-Novelty (Foote) auf dem Timbre → Arrangement-Kanten.
  4. 8-Zinken-Kamm: der Body erzeugt Kanten an allen 8 Sektionsgrenzen
     c, c+64, ..., c+448 gleichzeitig; zufaellige Einzelkanten nicht.
  5. Downbeat-Snap auf die Phrasen-"1" (Kick-Akzent mod 8) im Kamm-Plateau.
  6. H2-Tiebreak (Chroma-Figuren-Paare) gegen den +-32-Beat-Halbsektions-Alias.
  7. Kalibrier-Offset (Default +2 Beats) gleicht den systematischen Versatz aus
     Klick-Latenz + Detektor aus.

Confidence = Kamm-Margin (bester Offset vs. bester >= 8 Beats entfernter). Hoch
= scharfe, eindeutige Spitze. GUI-frei, kein Qt — Aufruf gehoert in einen
Worker-Thread (Audio-Prioritaet).
"""

from __future__ import annotations

import numpy as np

from caddy.lyrics.sync_keys import SINGING_BODY_BEATS as BODY_BEATS
from loop_finder import _load_audio
from bpm_detector import detect_beat_grid

SECTION_BEATS = 64
DEFAULT_CALIB_OFFSET = 2      # Beats; gleicht Klick-Latenz + Detektor-Versatz aus

# Mehrdeutigkeits-Schwelle: die Spannweite (disagree) der Start-Offsets, auf die
# drei unabhaengige Verfahren zeigen (Kamm-Kante, Timbre-Kohaerenz, Break/Figur-
# Kontrast). Empirisch an 64 Ohr-Marken: ALLE 11 harten Fehl-Locks hatten
# disagree >= 19, kein guter Song darunter war falsch. 18 = 1 Beat Sicherheits-
# puffer. Darueber: Song ist mehrdeutig -> ehrlich flaggen statt still falsch
# setzen. Ein einzelner Zweitgutachter reicht NICHT (leakt); erst das Quorum aus
# zweien macht die Trennung robust. Kostet keinen zweiten Audio-Pass (beide
# Zweitmeinungen fallen aus den ohnehin berechneten Timbre-Features).
AMBIGUITY_THRESHOLD = 18
_BREAK_IDX = (0, 3, 6)        # Opener / Middle Break / Closer
_FIGURE_IDX = (1, 2, 4, 5)   # die vier Figuren


# ---------------------------------------------------------------------------
# Beat-synchrone Features
# ---------------------------------------------------------------------------

def _mel_filterbank(sr: int, n_fft: int, n_bands: int = 20,
                    fmin: float = 60.0, fmax: float = 8000.0) -> np.ndarray:
    """Dreiecks-Filterbank auf Mel-Skala (n_bands, n_fft//2+1)."""
    def hz2mel(f):
        return 2595.0 * np.log10(1.0 + np.asarray(f, dtype=float) / 700.0)

    def mel2hz(m):
        return 700.0 * (10.0 ** (np.asarray(m, dtype=float) / 2595.0) - 1.0)

    freqs = np.fft.rfftfreq(n_fft, 1.0 / sr)
    edges = mel2hz(np.linspace(hz2mel(fmin), hz2mel(min(fmax, sr / 2.0)),
                               n_bands + 2))
    fb = np.zeros((n_bands, len(freqs)))
    for i in range(n_bands):
        lo, ce, hi = edges[i], edges[i + 1], edges[i + 2]
        left = (freqs - lo) / max(ce - lo, 1e-9)
        right = (hi - freqs) / max(hi - ce, 1e-9)
        fb[i] = np.clip(np.minimum(left, right), 0.0, 1.0)
    return fb


def _chroma_filterbank(sr: int, n_fft: int,
                       fmin: float = 60.0, fmax: float = 5000.0) -> np.ndarray:
    """Binaere 12-Halbton-Filterbank (Frequenz-Bin -> Pitch-Class)."""
    freqs = np.fft.rfftfreq(n_fft, 1.0 / sr)
    fb = np.zeros((12, len(freqs)))
    mask = (freqs >= fmin) & (freqs <= fmax)
    idx = np.where(mask)[0]
    notes = np.round(12 * np.log2(freqs[idx] / 440.0)).astype(int) % 12
    for pc in range(12):
        fb[pc, idx[notes == pc]] = 1.0
    return fb


def _z(x: np.ndarray) -> np.ndarray:
    return (x - x.mean()) / (x.std() + 1e-9)


def _beat_features(mono, sr, beat_times, duration,
                   n_fft=2048, hop=512, n_bands=20):
    """Beat-synchron: Mel-Timbre, L2-Chroma, log-Energie, Bass, Kick-Transient."""
    n = len(mono)
    starts = np.arange(0, max(1, n - n_fft + 1), hop)
    mel_fb = _mel_filterbank(sr, n_fft, n_bands)
    chr_fb = _chroma_filterbank(sr, n_fft)
    freqs = np.fft.rfftfreq(n_fft, 1.0 / sr)
    bass_mask = (freqs >= 60.0) & (freqs < 250.0)
    high_mask = (freqs >= 3000.0) & (freqs <= 10000.0)
    win = np.hanning(n_fft)

    n_fr = len(starts)
    mel_p = np.empty((n_fr, n_bands))
    chr_p = np.empty((n_fr, 12))
    bass_p = np.empty(n_fr)
    high_p = np.empty(n_fr)
    B = 256                                    # Frame-Batches: schnell + speicherarm
    for s0 in range(0, n_fr, B):
        idx = starts[s0:s0 + B]
        seg = np.stack([mono[i:i + n_fft] for i in idx]) * win
        spec = np.abs(np.fft.rfft(seg, axis=1)) ** 2
        sl = slice(s0, s0 + len(idx))
        mel_p[sl] = spec @ mel_fb.T
        chr_p[sl] = spec @ chr_fb.T
        bass_p[sl] = spec[:, bass_mask].sum(axis=1)
        high_p[sl] = spec[:, high_mask].sum(axis=1)
    frame_t = (starts + n_fft / 2.0) / sr

    n_beats = len(beat_times)
    edges = np.concatenate([beat_times, [duration]])
    fidx = np.searchsorted(frame_t, edges)
    kidx = np.searchsorted(frame_t, beat_times + 0.15)   # erste 150 ms = Kick
    timbre = np.empty((n_beats, n_bands))
    chroma = np.empty((n_beats, 12))
    energy = np.empty(n_beats)
    e_bass = np.empty(n_beats)
    e_high = np.empty(n_beats)
    kick = np.empty(n_beats)
    for i in range(n_beats):
        a = min(int(fidx[i]), n_fr - 1)
        b = max(a + 1, min(int(fidx[i + 1]), n_fr))
        timbre[i] = np.log10(mel_p[a:b].mean(axis=0) + 1e-12)
        cv = chr_p[a:b].mean(axis=0)
        nrm = np.linalg.norm(cv)
        chroma[i] = cv / nrm if nrm > 0 else cv
        e_bass[i] = 10.0 * np.log10(bass_p[a:b].mean() + 1e-12)
        e_high[i] = 10.0 * np.log10(high_p[a:b].mean() + 1e-12)
        k = max(a + 1, min(int(kidx[i]), n_fr))
        kick[i] = 10.0 * np.log10(bass_p[a:k].max() + 1e-12)
        s = int(beat_times[i] * sr)
        e = max(s + 1, min(int(edges[i + 1] * sr), n))
        energy[i] = 10.0 * np.log10(float(np.mean(mono[s:e] ** 2)) + 1e-12)
    return timbre, chroma, energy, e_bass, e_high, kick


def _norm_rows(x: np.ndarray) -> np.ndarray:
    """Z-Norm je Spalte (ueber alle Beats), dann L2 je Zeile (Beat) → Kosinus."""
    z = (x - x.mean(axis=0)) / (x.std(axis=0) + 1e-9)
    return z / (np.linalg.norm(z, axis=1, keepdims=True) + 1e-9)


def _section_scores(feat_rows: np.ndarray, c: int) -> tuple:
    """7×7 Beat-fuer-Beat-Aehnlichkeit der Abschnitte ab Offset c.

    Rueckgabe (kohaerenz, kontrast):
      kohaerenz = mittlere Aehnlichkeit aller Abschnittspaare (off-diagonal)
      kontrast  = intra(Break-Break, Fig-Fig) − inter(Break-Fig)
    Nur als ZWEITMEINUNG fuer die Mehrdeutigkeits-Erkennung — NICHT zur
    Offset-Wahl (dafuer scheiterte Inhaltsvergleich, siehe Experimente)."""
    n_sec = BODY_BEATS // SECTION_BEATS
    body = feat_rows[c:c + BODY_BEATS].reshape(n_sec, SECTION_BEATS, -1)
    sim = np.einsum("ipd,jpd->ij", body, body) / float(SECTION_BEATS)
    coh = (sim.sum() - np.trace(sim)) / (n_sec * n_sec - n_sec)
    intra, inter = [], []
    for grp in (_BREAK_IDX, _FIGURE_IDX):
        for a in range(len(grp)):
            for b in range(a + 1, len(grp)):
                intra.append(sim[grp[a], grp[b]])
    for a in _BREAK_IDX:
        for b in _FIGURE_IDX:
            inter.append(sim[a, b])
    return float(coh), float(np.mean(intra) - np.mean(inter))


def _novelty_and_step(timbre, energy, K=16):
    """Checkerboard-Novelty + Energie-Stufe an jeder Beat-Grenze b in 0..n.

    Silence-Padding vor/hinter dem Song, damit Grenzen nahe Anfang/Ende volle
    K-Fenster haben (Outro->Stille ist eine echte Kante)."""
    n = len(energy)
    sil_t = timbre.min(axis=0) - 1.0
    sil_e = float(energy.min()) - 10.0
    tp = np.vstack([np.tile(sil_t, (K, 1)), timbre, np.tile(sil_t, (K, 1))])
    ep = np.concatenate([np.full(K, sil_e), energy, np.full(K, sil_e)])

    mu, sd = timbre.mean(axis=0), timbre.std(axis=0) + 1e-9
    tz = (tp - mu) / sd
    R = tz / (np.linalg.norm(tz, axis=1, keepdims=True) + 1e-9)
    S = R @ R.T

    nov = np.empty(n + 1)
    step = np.empty(n + 1)
    for b in range(n + 1):
        i = b + K
        pre = S[i - K:i, i - K:i]
        post = S[i:i + K, i:i + K]
        cross = S[i - K:i, i:i + K]
        nov[b] = pre.mean() + post.mean() - 2.0 * cross.mean()
        step[b] = ep[i:i + K].mean() - ep[i - K:i].mean()
    return nov, step


# ---------------------------------------------------------------------------
# Oeffentliche API
# ---------------------------------------------------------------------------

def detect_singing_body(filepath: str, bpm_hint: float = None,
                        calib_offset: int = DEFAULT_CALIB_OFFSET,
                        K: int = 16) -> dict:
    """Findet Anfang + Ende des Singing-Call-Body.

    Args:
        filepath:     Pfad zur Audiodatei.
        bpm_hint:     Bekannte BPM (aus der DB) — WICHTIG als Tempo-Anker, sonst
                      Halb-/Doppeltempo-Fehler. None -> Auto-Detect.
        calib_offset: Beats, die zum Ergebnis addiert werden (Default +2).
        K:            Novelty-Fensterbreite in Beats.

    Returns:
        dict mit "ok". Bei Erfolg zusaetzlich:
          start_sec, end_sec  — Vorschlag in Sekunden
          bpm, beat_period, n_beats
          confidence          — Kamm-Margin (hoch = scharfe, eindeutige Spitze)
          start_beat           — Beat-Index des Anfangs
        Bei Misserfolg: "reason".
    """
    mono, sr = _load_audio(filepath)
    duration = len(mono) / sr
    hint = bpm_hint if (bpm_hint and bpm_hint > 40.0) else None
    bpm, beat_times = detect_beat_grid(filepath, bpm=hint)
    beat_times = np.asarray(beat_times, dtype=float)
    n = len(beat_times)
    if n < BODY_BEATS + 2:
        return {"ok": False,
                "reason": f"Song zu kurz fuer einen 7x64-Body ({n} Beats)"}
    beat_period = float(np.median(np.diff(beat_times)))

    timbre, chroma, energy, e_bass, e_high, kick = _beat_features(
        mono, sr, beat_times, duration)
    nov, step = _novelty_and_step(timbre, energy, K=K)
    novz, stepz = _z(nov), _z(step)

    # Hochband-Transient ("Crash") je Beat gegen den Vortakt — eine Kamm-Zinke.
    crash = np.zeros(n)
    for b in range(n):
        prev = e_high[max(0, b - 4):b]
        crash[b] = e_high[b] - (prev.mean() if prev.size else 0.0)
    crashz = _z(crash)

    bass_in = np.zeros(n)
    for b in range(n):
        prev = e_bass[max(0, b - 8):b]
        post = e_bass[b:min(n, b + 8)]
        bass_in[b] = post.mean() - (prev.mean() if prev.size else post.mean())
    bassz = _z(bass_in)

    max_off = n - BODY_BEATS
    start_min = min(8, max_off)               # Intro >= 8 Beats (2 Takte Vorlauf)

    def comb(c: int) -> float:
        s = 0.0
        for k in range(8):
            b = c + SECTION_BEATS * k
            s += 1.0 * float(np.max(novz[max(0, b - 4):min(n, b + 2) + 1]))
            bc = min(b, n - 1)
            s += 0.7 * float(np.max(crashz[bc:min(n - 1, b + 1) + 1]))
        s += 0.7 * float(np.max(stepz[max(0, c - 4):c + 3]))
        eL = max(0, c + BODY_BEATS - 4)
        eH = min(n, c + BODY_BEATS + 2)
        s -= 0.7 * float(np.min(stepz[eL:eH + 1]))
        s += 0.5 * float(bassz[min(c, n - 1)])
        return s

    score = np.full(max_off + 1, -np.inf)
    for c in range(start_min, max_off + 1):
        score[c] = comb(c)
    best_raw = int(np.argmax(score))
    offs = np.arange(max_off + 1)
    finite = np.isfinite(score)
    far = offs[(np.abs(offs - best_raw) >= 8) & finite]
    margin = (float(score[best_raw]) - float(score[far].max())
              if far.size else 0.0)

    # --- Intrinsische Mehrdeutigkeits-Erkennung (ohne Ground Truth) -----------
    # Zwei unabhaengige Zweitmeinungen aus denselben Timbre-Features: wohin
    # zeigen Timbre-Kohaerenz bzw. Break/Figur-Kontrast? Streuen Kamm + beide
    # weit auseinander, ist der Song mehrdeutig (Figuren 2× getanzt, schwache
    # Intro-Kante ...) → ehrlich als "unsicher" melden. margin taugt dafuer
    # NICHT (Kamm ist bei Fehlern selbstsicher); erst die Uneinigkeit verraet ihn.
    tim_rows = _norm_rows(timbre)
    coh_curve = np.full(max_off + 1, -np.inf)
    con_curve = np.full(max_off + 1, -np.inf)
    for c in range(start_min, max_off + 1):
        coh_curve[c], con_curve[c] = _section_scores(tim_rows, c)
    picks = [best_raw, int(np.argmax(coh_curve)), int(np.argmax(con_curve))]
    disagree = int(max(picks) - min(picks))
    ambiguous = bool(disagree >= AMBIGUITY_THRESHOLD)

    # Downbeat-Snap: Phrasen-"1" aus dem Kick-Akzent (mod 8) im Body.
    kz = _z(kick)
    acc = np.zeros(8)
    cnt = np.zeros(8)
    for b in range(max(0, best_raw), min(n, best_raw + BODY_BEATS)):
        acc[b % 8] += kz[b]
        cnt[b % 8] += 1
    acc = acc / np.maximum(cnt, 1)
    p8 = int(np.argmax(acc))
    cand = [c for c in range(max(start_min, best_raw - 6),
                             min(max_off, best_raw + 6) + 1)
            if c % 8 == p8]
    best = max(cand, key=lambda c: score[c]) if cand else best_raw

    # H2-Tiebreak gegen den +-32-Halbsektions-Alias (Chroma-Figuren-Paare).
    def fig_pair(c: int) -> float:
        if c < 0 or c + BODY_BEATS > n:
            return float("-inf")

        def pair(i: int, j: int) -> float:
            a = chroma[c + SECTION_BEATS * i: c + SECTION_BEATS * i + SECTION_BEATS]
            b = chroma[c + SECTION_BEATS * j: c + SECTION_BEATS * j + SECTION_BEATS]
            return float(np.mean(np.sum(a * b, axis=1)))

        return (pair(1, 2) + pair(4, 5)
                + 0.5 * (pair(0, 3) + pair(3, 6))) / 3.0

    cands32 = [best + d for d in (-32, 0, 32)
               if start_min <= best + d <= max_off]
    if len(cands32) > 1:
        fps = {c: fig_pair(c) for c in cands32}
        alt = max(cands32, key=lambda c: fps[c])
        if alt != best and fps[alt] - fps[best] > 0.01:
            best = alt

    if calib_offset:
        best = max(start_min, min(best + calib_offset, max_off))

    end_beat = best + BODY_BEATS
    return {
        "ok": True,
        "start_sec": float(beat_times[best]),
        "end_sec": (float(beat_times[end_beat]) if end_beat < n else duration),
        "start_beat": int(best),
        "bpm": float(bpm),
        "beat_period": beat_period,
        "n_beats": int(n),
        "confidence": float(margin),
        "disagree": disagree,
        "ambiguous": ambiguous,
    }
