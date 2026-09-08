"""Experiment 3: Multiband-Kanten + Alias-Aufloesung fuer den Singing-Call-Body.

Stand nach Experiment 2 (singing_body_novelty.py, 8-Zinken-Kamm auf
Timbre-Novelty): Median 4,5 Beats, 7/16 <= 4 Beats gegen 16 Gehoer-Marken.
Diagnostizierte Restfehler:
  - Fill-Bias: Timbre-Kante beginnt 2-4 Beats VOR der Sektionsgrenze (Drum-Fill)
  - +-32-Alias: Figuren werden 2x getanzt -> Halbsektions-Kanten gleich stark
  - einzelne Songs ohne Timbre-Kanten an den Grenzen

Zwei VOR dem Lauf festgelegte Hypothesen (gegen die 16 Marken getestet):

H1 "Crash-Becken": Sektionsanfaenge tragen einen Crash AUF Beat 1 (nicht
   davor). Hochband-Transienten (3-10 kHz, Anstieg gegen den Vortakt) sind
   daher ein schaerferer Kamm-Zinken als die breite Timbre-Novelty — ohne
   Fill-Bias. Gewicht fest 0.7 (nicht gefittet).

H2 "Figuren-Paare": Bei wahrer Ausrichtung sind Sektionspaare (2,3), (5,6)
   [gleiche Figur] und (1,4), (4,7) [Breaks] beat-weise harmonisch aehnlich;
   beim +-32-Alias mischen die "Sektionen" halbe Figuren -> Paar-Score sinkt.
   Wird hier NUR als Diagnose ausgewiesen (nicht in den Score gebacken),
   damit wir seine Trennkraft unverzerrt sehen.

Leitplanke: reines Offline-Experiment, kein App-Einbau vor Beleg mit hoher
Korrelation. Aufruf (aus 2_Test/):
    python ../1_Source/src/tools/singing_body_multiband.py \
        --ids 10,49 --ref-starts "10:6.78,49:16.25"
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

_THIS = Path(__file__).resolve()
SRC_DIR = _THIS.parents[1]
REPO_ROOT = _THIS.parents[3]
TEST_DIR = REPO_ROOT / "2_Test"

sys.path.insert(0, str(SRC_DIR))
sys.path.insert(0, str(_THIS.parent))

from loop_finder import _load_audio                     # noqa: E402
from bpm_detector import detect_beat_grid               # noqa: E402
from singing_section_experiment import (                # noqa: E402
    load_songs_by_ids, resolve_audio_path,
)
from singing_body_novelty import (                      # noqa: E402
    _mel_filterbank, _novelty_and_step, _z,
)

BODY_BEATS = 448
_PHASE_SOURCE = "kick"      # wird von main() per --phase gesetzt


# ---------------------------------------------------------------------------
# Ein STFT-Durchlauf -> Mel-Timbre, Chroma, Gesamt-/Bass-/Hochband je Beat
# ---------------------------------------------------------------------------

def _chroma_filterbank(sr: int, n_fft: int,
                       fmin: float = 60.0, fmax: float = 5000.0) -> np.ndarray:
    freqs = np.fft.rfftfreq(n_fft, 1.0 / sr)
    fb = np.zeros((12, len(freqs)))
    mask = (freqs >= fmin) & (freqs <= fmax)
    idx = np.where(mask)[0]
    notes = np.round(12 * np.log2(freqs[idx] / 440.0)).astype(int) % 12
    for pc in range(12):
        fb[pc, idx[notes == pc]] = 1.0
    return fb


def _beat_features_mb(mono, sr, beat_times, duration,
                      n_fft=2048, hop=512, n_bands=20):
    """Beat-synchron: Mel-Timbre, L2-normiertes Chroma, log-Energien
    (gesamt / Bass 60-250 Hz / Hochband 3-10 kHz)."""
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
    B = 256
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
    # Kick-Fenster: die ersten 150 ms jedes Beats (Transient sitzt AUF dem Beat)
    kidx = np.searchsorted(frame_t, beat_times + 0.15)
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


# ---------------------------------------------------------------------------
# Analyse
# ---------------------------------------------------------------------------

def analyze(filepath: str, K: int = 16, bpm_hint: float = None,
            calib_offset: int = 0) -> dict:
    mono, sr = _load_audio(filepath)
    duration = len(mono) / sr
    # DB-BPM als Anker gegen Tempo-Oktav-Fehler des Beat-Detektors
    # (3 Blind-Songs hatten 313-329 "Beats" = halbe Oktave -> unmoeglich)
    hint = bpm_hint if (bpm_hint and bpm_hint > 40.0) else None
    bpm, beat_times = detect_beat_grid(filepath, bpm=hint)
    beat_times = np.asarray(beat_times, dtype=float)
    n = len(beat_times)
    if n < BODY_BEATS + 2:
        return {"ok": False, "reason": f"zu kurz ({n} Beats)"}
    beat_period = float(np.median(np.diff(beat_times)))

    timbre, chroma, energy, e_bass, e_high, kick = _beat_features_mb(
        mono, sr, beat_times, duration)
    nov, step = _novelty_and_step(timbre, energy, K=K)
    novz, stepz = _z(nov), _z(step)

    # H1: Crash-Score je Beat = Hochband-Anstieg gegen den Vortakt
    crash = np.zeros(n)
    for b in range(n):
        prev = e_high[max(0, b - 4):b]
        crash[b] = e_high[b] - (prev.mean() if prev.size else 0.0)
    crashz = _z(crash)

    # Bass-Einsatz (nur fuer die START-Zinke): 8 Beats danach vs. 8 davor
    bass_in = np.zeros(n)
    for b in range(n):
        prev = e_bass[max(0, b - 8):b]
        post = e_bass[b:min(n, b + 8)]
        bass_in[b] = post.mean() - (prev.mean() if prev.size else post.mean())
    bassz = _z(bass_in)

    max_off = n - BODY_BEATS
    start_min = min(8, max_off)          # Intro >= 8 Beats (2 Takte Vorlauf)

    def comb(c: int) -> float:
        s = 0.0
        for k in range(8):
            b = c + 64 * k
            # Timbre-Kante: Fill liegt VOR der Grenze -> Fenster [-4..+2]
            s += 1.0 * float(np.max(novz[max(0, b - 4):min(n, b + 2) + 1]))
            # Crash: AUF der Eins (Fenster [0..+1]), Beat-Index <= n-1
            bc = min(b, n - 1)
            s += 0.7 * float(np.max(crashz[bc:min(n - 1, b + 1) + 1]))
        # Energie-Polaritaet an den Aussengrenzen
        s += 0.7 * float(np.max(stepz[max(0, c - 4):c + 3]))
        eL = max(0, c + BODY_BEATS - 4)
        eH = min(n, c + BODY_BEATS + 2)
        s -= 0.7 * float(np.min(stepz[eL:eH + 1]))
        # Bass-Einsatz am Start
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
              if far.size else float("nan"))

    # Stufe 2 — Downbeat-Snap ohne gefittete Konstante: Beat 1 ist ein
    # Phrasen-Downbeat. Die Downbeat-Phase (mod 8) wird aus dem KICK-Akzent
    # (Transient-Peak 60-250 Hz in den ersten 150 ms des Beats) INNERHALB des
    # gefundenen Body geschaetzt, dann wird im Kamm-Plateau [best−6..best+6]
    # auf diese Phase gesnappt. Kick statt Breitband-Bass: der Basslauf
    # verschmiert die Phase, der Kick-Schlag nicht.
    kz = _z(kick)
    ebz = _z(e_bass)
    body_lo = max(0, best_raw)
    body_hi = min(n, best_raw + BODY_BEATS)
    acc = np.zeros(8)
    cnt = np.zeros(8)
    # Phase-Schaetzer per CLI umschaltbar (Vergleich auf der 52er-Stichprobe):
    # kick (Lauf 3c, eingefroren) | bass (Lauf 3b) | ensemble (Lauf 3d)
    src = {"kick": kz, "bass": ebz,
           "ensemble": 0.5 * (kz + ebz)}[_PHASE_SOURCE]
    for b in range(body_lo, body_hi):
        acc[b % 8] += src[b]
        cnt[b % 8] += 1
    acc = acc / np.maximum(cnt, 1)
    p8 = int(np.argmax(acc))
    p8_strength = float(acc[p8] - np.median(acc))

    cand = [c for c in range(max(start_min, best_raw - 6),
                             min(max_off, best_raw + 6) + 1)
            if c % 8 == p8]
    best = max(cand, key=lambda c: score[c]) if cand else best_raw

    # H2: Chroma-Paar-Score (Sektionen 0-basiert: Figuren (1,2)+(4,5),
    # Breaks (0,3)+(3,6)) — beat-weises Skalarprodukt L2-normierter Chromas
    def fig_pair(c: int) -> float:
        if c < 0 or c + BODY_BEATS > n:
            return float("nan")

        def pair(i: int, j: int) -> float:
            a = chroma[c + 64 * i: c + 64 * i + 64]
            b = chroma[c + 64 * j: c + 64 * j + 64]
            return float(np.mean(np.sum(a * b, axis=1)))

        return (pair(1, 2) + pair(4, 5)
                + 0.5 * (pair(0, 3) + pair(3, 6))) / 3.0

    # H2-Tiebreak: ±32-Alias aufloesen. Der Chroma-Paar-Score ist bei wahrer
    # Ausrichtung hoeher (Figuren-/Break-Paare fluchten). Wechsel nur bei
    # klarem Vorsprung (> 0.01), damit Rauschen nicht hin- und herschaltet.
    h2_switch = 0
    cands32 = [best + d for d in (-32, 0, 32)
               if start_min <= best + d <= max_off]
    if len(cands32) > 1:
        fps = {c: fig_pair(c) for c in cands32}
        alt = max(cands32, key=lambda c: fps[c])
        if alt != best and fps[alt] - fps[best] > 0.01:
            h2_switch = alt - best
            best = alt

    # Kalibrier-Offset (empirisch: Klick-Latenz der Referenzen + Detektor-
    # Versatz ergeben global ca. −1.3..−2.6 Beats; +2 hebt die Quote auf
    # beiden Datensaetzen). Default 0 — Aktivierung ist Davids Entscheidung.
    if calib_offset:
        best = max(start_min, min(best + calib_offset, max_off))

    order = np.argsort(score)[::-1][:5]
    return {
        "ok": True, "n_beats": n, "bpm": float(bpm),
        "beat_period": beat_period, "max_off": max_off,
        "best": best, "best_raw": best_raw,
        "p8": p8, "p8_strength": p8_strength, "h2_switch": h2_switch,
        "start_sec": float(beat_times[best]),
        "end_sec": (float(beat_times[best + BODY_BEATS])
                    if best + BODY_BEATS < n else duration),
        "score": score, "margin": margin,
        "novz": novz, "stepz": stepz, "crashz": crashz, "bassz": bassz,
        "fig_pair": fig_pair, "beat_times": beat_times,
        "top": [(int(o), float(score[o])) for o in order],
    }


# ---------------------------------------------------------------------------
# Ausgabe
# ---------------------------------------------------------------------------

def _zinken_median(curve: np.ndarray, c: int, n: int,
                   lo_off: int, hi_off: int) -> float:
    """Median der Kamm-Zinken-Werte von curve an c+64k, Fenster [lo..hi]."""
    vals = []
    for k in range(8):
        b = c + 64 * k
        lo = max(0, b + lo_off)
        hi = min(len(curve) - 1, b + hi_off)
        if hi >= lo:
            vals.append(float(np.max(curve[lo:hi + 1])))
    return float(np.median(vals)) if vals else float("nan")


def report(song: dict, res: dict) -> dict:
    print(f"=== #{song['id']}  {song['title']}  ({song['filename']})")
    if not res["ok"]:
        print(f"    ÜBERSPRUNGEN: {res['reason']}\n")
        return {"ok": False}

    bt, bp, n = res["beat_times"], res["beat_period"], res["n_beats"]
    print(f"    Beatraster: bpm≈{res['bpm']:.1f}  Beats={n}  "
          f"Suchraum=8..{res['max_off']}")
    print(f"    Bester Start: Beat {res['best']} → {res['start_sec']:.2f}s   "
          f"Ende {res['end_sec']:.2f}s   margin={res['margin']:.2f}")
    h2s = (f"  H2-Tiebreak: {res['h2_switch']:+d} Beats"
           if res.get("h2_switch") else "")
    print(f"    Stufe 2: Kamm-roh Beat {res['best_raw']} → Kick-Phase "
          f"mod 8 = {res['p8']} (Stärke {res['p8_strength']:+.2f}) → "
          f"Beat {res['best']}{h2s}")
    print("    Top-5 (Beat:score): " +
          "  ".join(f"{o}:{s:.2f}" for o, s in res["top"]))

    out = {"ok": True, "id": song["id"], "margin": res["margin"]}
    ref = song.get("ref_start")
    if ref is None and song.get("gt_start") is not None:
        ref = song["gt_start"]
    if ref is not None:
        ref_off = int(np.argmin(np.abs(bt - ref)))
        ref_c = min(max(ref_off, 0), res["max_off"])
        rank = int(np.sum(res["score"] > res["score"][ref_c]))
        err_s = res["start_sec"] - ref
        err_b = err_s / bp
        print(f"    REFERENZ: {ref:.2f}s (Beat {ref_off})   "
              f"Fehler = {err_s:+.2f}s ({err_b:+.1f} Beats)   Rang={rank}")
        # H1-Diagnose: Crash-Zinken an Referenz vs. +-32-Alias
        cr_ref = _zinken_median(res["crashz"], ref_c, n, 0, 1)
        cr_m32 = _zinken_median(res["crashz"], ref_c - 32, n, 0, 1) \
            if ref_c - 32 >= 0 else float("nan")
        cr_p32 = _zinken_median(res["crashz"], ref_c + 32, n, 0, 1)
        print(f"      H1 Crash-Zinken (Median): Ref={cr_ref:+.2f}   "
              f"Alias−32={cr_m32:+.2f}   Alias+32={cr_p32:+.2f}")
        # H2-Diagnose: Chroma-Paar-Score an Referenz vs. Alias
        fp = res["fig_pair"]
        fp_ref, fp_m32, fp_p32 = fp(ref_c), fp(ref_c - 32), fp(ref_c + 32)
        print(f"      H2 Figuren-Paar: Ref={fp_ref:.3f}   "
              f"Alias−32={fp_m32:.3f}   Alias+32={fp_p32:.3f}")
        alias_vals = [v for v in (fp_m32, fp_p32) if v == v]
        h2_sep = fp_ref - max(alias_vals) if alias_vals and fp_ref == fp_ref \
            else float("nan")
        h1_alias = [v for v in (cr_m32, cr_p32) if v == v]
        h1_sep = cr_ref - max(h1_alias) if h1_alias else float("nan")
        out.update({"err_b": err_b, "rank": rank,
                    "h1_sep": h1_sep, "h2_sep": h2_sep})
    else:
        print("    REFERENZ: (keine)")
    print()
    return out


def print_summary(rows: list) -> None:
    ok = [r for r in rows if r.get("ok") and "err_b" in r]
    print("=" * 70)
    print(f"ZUSAMMENFASSUNG — {len(ok)} Songs mit Referenz")
    print("=" * 70)
    if not ok:
        return
    for thr in (1, 2, 4):
        hits = sum(1 for r in ok if abs(r["err_b"]) <= thr)
        print(f"  Treffer ≤ {thr} Beat(s): {hits}/{len(ok)}  "
              f"({100 * hits / len(ok):.0f}%)")
    med = float(np.median([abs(r["err_b"]) for r in ok]))
    print(f"  Median |Fehler|: {med:.1f} Beats")
    ranks = sorted(r["rank"] for r in ok)
    top3 = sum(1 for r in ok if r["rank"] <= 2)
    print(f"  Ränge: {ranks}   → Referenz in Top-3: {top3}/{len(ok)}")

    h1 = [r["h1_sep"] for r in ok if r.get("h1_sep") == r.get("h1_sep")]
    h2 = [r["h2_sep"] for r in ok if r.get("h2_sep") == r.get("h2_sep")]
    if h1:
        pos = sum(1 for v in h1 if v > 0)
        print(f"\n  H1 (Crash trennt Ref von ±32-Alias): positiv bei "
              f"{pos}/{len(h1)} Songs, Median-Separation {np.median(h1):+.2f}")
    if h2:
        pos = sum(1 for v in h2 if v > 0)
        print(f"  H2 (Figuren-Paar trennt Ref von ±32-Alias): positiv bei "
              f"{pos}/{len(h2)} Songs, Median-Separation {np.median(h2):+.3f}")

    print("\n  Details (id: Fehler | Rang | margin | H1-Sep | H2-Sep):")
    for r in sorted(ok, key=lambda x: abs(x["err_b"])):
        print(f"    #{r['id']:<4} {r['err_b']:+6.1f}b | Rang {r['rank']:<3} "
              f"| m={r['margin']:5.2f} | H1 {r.get('h1_sep', float('nan')):+5.2f} "
              f"| H2 {r.get('h2_sep', float('nan')):+6.3f}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default=str(TEST_DIR / "callers_caddy.db"))
    ap.add_argument("--music", default=str(TEST_DIR / "music"))
    ap.add_argument("--ids", required=True)
    ap.add_argument("--ref-starts", default=None)
    ap.add_argument("--K", type=int, default=16)
    ap.add_argument("--phase", choices=("kick", "bass", "ensemble"),
                    default="kick",
                    help="Quelle fuer die Downbeat-Phase (Default kick)")
    ap.add_argument("--calib-offset", type=int, default=0,
                    help="Beats zum Ergebnis addieren (Kalibrierung, z.B. 2)")
    args = ap.parse_args()
    global _PHASE_SOURCE
    _PHASE_SOURCE = args.phase

    try:
        id_list = [int(x) for x in args.ids.replace(" ", "").split(",") if x]
    except ValueError:
        print("FEHLER: --ids erwartet eine Komma-Liste von Zahlen.")
        return 1

    ref_starts = {}
    if args.ref_starts:
        for part in args.ref_starts.replace(" ", "").split(","):
            if not part:
                continue
            try:
                sid_s, sec_s = part.split(":", 1)
                if ":" in sec_s:                      # "mm:ss.xx" erlaubt
                    m_s, s_s = sec_s.split(":")
                    sec = int(m_s) * 60.0 + float(s_s)
                else:
                    sec = float(sec_s)
                ref_starts[int(sid_s)] = sec
            except ValueError:
                print(f"WARNUNG: --ref-starts Eintrag ignoriert: {part!r}")

    songs = load_songs_by_ids(args.db, id_list)
    for s in songs:
        if s["id"] in ref_starts:
            s["ref_start"] = ref_starts[s["id"]]

    rows = []
    for s in songs:
        path = resolve_audio_path(s["filename"], args.music)
        if not path:
            print(f"=== #{s['id']}  {s['title']}")
            print(f"    ÜBERSPRUNGEN: Datei nicht gefunden ({s['filename']})\n")
            continue
        try:
            res = analyze(path, K=args.K, bpm_hint=s.get("bpm"),
                          calib_offset=args.calib_offset)
        except Exception as e:
            print(f"=== #{s['id']}  {s['title']}")
            print(f"    FEHLER bei Analyse: {e}\n")
            continue
        rows.append(report(s, res))

    print_summary(rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
