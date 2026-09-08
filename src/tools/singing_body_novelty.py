"""Experiment 2: Singing-Call-Body ueber ARRANGEMENT-Kanten finden.

Vorgeschichte (siehe singing_section_experiment.py): Der Versuch, den 7x64-Body
ueber Melodie-Selbstaehnlichkeit (Chroma) zu finden, ist auf Zufallsdaten
gescheitert (2/9 <= 2 Beats; Gehoer-Referenz lag auf Rang 9-19 der Score-Kurve).
Ursache: Die instrumentalen Intros spielen die Melodie bereits an — die
HARMONIE traegt die Intro->Body-Grenze nicht.

Neue Hypothese: Die Grenze lebt im ARRANGEMENT, nicht in der Tonhoehe.
Am Body-Start setzt typischerweise die volle Besetzung ein (Rhythmusgruppe,
Bass, dichteres Spektrum), am Body-Ende beginnt der Tag/Ausklang. Solche
Besetzungswechsel zeigen sich im TIMBRE (Spektralform, log-Mel-Baender) und in
der ENERGIE — auch wenn die Melodie identisch weiterlaeuft.

Methode (Foote-Novelty, beat-synchron):
  1. Beat-Grid (bpm_detector) + log-Mel-Timbre (20 Baender) + log-RMS je Beat
  2. Beat-SSM ueber z-transformierte Timbre-Vektoren
  3. Checkerboard-Novelty nov(b) = Kohaerenz(vor b) + Kohaerenz(nach b)
     − 2·Kreuzaehnlichkeit  → spitz genau an Arrangement-Kanten
  4. Energie-Stufe step(b) = Mittel(nach b) − Mittel(vor b)
  5. Harter Domaenen-Anker: Start- und Ende-Kante liegen EXAKT 448 Beats
     auseinander → bewertet werden KANTEN-PAARE:
        score(c) = [nov(c) + w·step(c)] + [nov(c+448) − w·step(c+448)]
     (Energie RAUF am Start, RUNTER am Ende; ±slack Beats fuer Grid-Drift.)
     Zufaellige Einzelkanten paaren sich nicht bei genau 448 Beats Abstand.
  6. Diagnose je Song: RANG der Gehoer-Referenz in der Score-Kurve.
     Rang ~0–2 ⇒ Signal vorhanden (nur Auswahl/Feinschliff noetig);
     Rang verstreut ⇒ Audio traegt die Grenze auch im Timbre nicht.

GUI-frei; nutzt nur numpy + die vorhandene Pipeline (loop_finder/bpm_detector).
Aufruf (aus 2_Test/):
    python ../1_Source/src/tools/singing_body_novelty.py \
        --ids 10,49 --ref-starts "10:6.78,49:16.25"
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

_THIS = Path(__file__).resolve()
SRC_DIR = _THIS.parents[1]          # 1_Source/src
REPO_ROOT = _THIS.parents[3]        # Callers-Caddy/
TEST_DIR = REPO_ROOT / "2_Test"

sys.path.insert(0, str(SRC_DIR))
sys.path.insert(0, str(_THIS.parent))

from loop_finder import _load_audio                     # noqa: E402
from bpm_detector import detect_beat_grid               # noqa: E402
from singing_section_experiment import (                # noqa: E402
    load_songs_by_ids, resolve_audio_path,              # Loader wiederverwenden
)

BODY_BEATS = 448


# ---------------------------------------------------------------------------
# Beat-synchrone Features: log-Mel-Timbre + Energie
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


def _beat_features(mono, sr, beat_times, duration,
                   n_fft=2048, hop=512, n_bands=20):
    """log-Mel-Timbre (n_beats, n_bands) und log-Energie in dB (n_beats,)."""
    n = len(mono)
    starts = np.arange(0, max(1, n - n_fft + 1), hop)
    fb = _mel_filterbank(sr, n_fft, n_bands)
    win = np.hanning(n_fft)
    powers = np.empty((len(starts), n_bands))
    B = 256                                   # Frame-Batches: schnell + speicherarm
    for s0 in range(0, len(starts), B):
        idx = starts[s0:s0 + B]
        seg = np.stack([mono[i:i + n_fft] for i in idx]) * win
        spec = np.abs(np.fft.rfft(seg, axis=1)) ** 2
        powers[s0:s0 + len(idx)] = spec @ fb.T
    frame_t = (starts + n_fft / 2.0) / sr

    n_beats = len(beat_times)
    edges = np.concatenate([beat_times, [duration]])
    fidx = np.searchsorted(frame_t, edges)
    timbre = np.empty((n_beats, n_bands))
    energy = np.empty(n_beats)
    for i in range(n_beats):
        a = min(int(fidx[i]), len(starts) - 1)
        b = max(a + 1, min(int(fidx[i + 1]), len(starts)))
        timbre[i] = np.log10(powers[a:b].mean(axis=0) + 1e-12)
        s = int(beat_times[i] * sr)
        e = max(s + 1, min(int(edges[i + 1] * sr), n))
        energy[i] = 10.0 * np.log10(float(np.mean(mono[s:e] ** 2)) + 1e-12)
    return timbre, energy


def _z(x: np.ndarray) -> np.ndarray:
    return (x - x.mean()) / (x.std() + 1e-9)


def _novelty_and_step(timbre, energy, K=16):
    """Checkerboard-Novelty + Energie-Stufe an jeder Beat-Grenze b in 0..n.

    Grenze b liegt ZWISCHEN Beat b−1 und Beat b (b = erster Beat danach).
    Silence-Padding vor/hinter dem Song, damit auch Grenzen nahe Dateianfang/
    -ende volle K-Fenster haben — der Uebergang Outro→Stille ist eine echte
    Kante (Bright-Side-Typ: Outro nur wenige Beats).
    """
    n = len(energy)
    sil_t = timbre.min(axis=0) - 1.0          # ~10 dB unter Song-Minimum je Band
    sil_e = float(energy.min()) - 10.0
    tp = np.vstack([np.tile(sil_t, (K, 1)), timbre, np.tile(sil_t, (K, 1))])
    ep = np.concatenate([np.full(K, sil_e), energy, np.full(K, sil_e)])

    # z-Transform je Band — Parameter NUR aus echten Beats, auf Padding angewandt
    mu, sd = timbre.mean(axis=0), timbre.std(axis=0) + 1e-9
    tz = (tp - mu) / sd
    R = tz / (np.linalg.norm(tz, axis=1, keepdims=True) + 1e-9)
    S = R @ R.T

    nov = np.empty(n + 1)
    step = np.empty(n + 1)
    for b in range(n + 1):
        i = b + K                              # Index im gepolsterten Raum
        pre = S[i - K:i, i - K:i]
        post = S[i:i + K, i:i + K]
        cross = S[i - K:i, i:i + K]
        nov[b] = pre.mean() + post.mean() - 2.0 * cross.mean()
        step[b] = ep[i:i + K].mean() - ep[i - K:i].mean()
    return nov, step


# ---------------------------------------------------------------------------
# Analyse: Kanten-Paare im 448er-Abstand
# ---------------------------------------------------------------------------

def analyze(filepath: str, K: int = 16, slack: int = 1,
            w_energy: float = 0.5) -> dict:
    mono, sr = _load_audio(filepath)
    duration = len(mono) / sr
    bpm, beat_times = detect_beat_grid(filepath)
    beat_times = np.asarray(beat_times, dtype=float)
    n = len(beat_times)
    if n < BODY_BEATS + 2:
        return {"ok": False, "reason": f"zu kurz ({n} Beats < {BODY_BEATS + 2})"}
    beat_period = float(np.median(np.diff(beat_times)))

    timbre, energy = _beat_features(mono, sr, beat_times, duration)
    nov, step = _novelty_and_step(timbre, energy, K=K)
    novz, stepz = _z(nov), _z(step)
    start_term = novz + w_energy * stepz       # Energie RAUF am Body-Start
    end_term = novz - w_energy * stepz         # Energie RUNTER am Body-Ende

    max_off = n - BODY_BEATS
    score = np.full(max_off + 1, -np.inf)      # 2-Kanten-Paar (alt, Vergleich)
    score_t = np.full(max_off + 1, -np.inf)    # nur Timbre (Diagnose)
    end_pick = np.zeros(max_off + 1, dtype=int)
    for c in range(max_off + 1):
        lo = max(0, c + BODY_BEATS - slack)
        hi = min(n, c + BODY_BEATS + slack)
        j = lo + int(np.argmax(end_term[lo:hi + 1]))
        score[c] = start_term[c] + end_term[j]
        end_pick[c] = j
        score_t[c] = novz[c] + float(np.max(novz[lo:hi + 1]))

    # 8-Zinken-Kamm: der Body erzeugt Kanten an ALLEN 8 Sektionsgrenzen
    # c, c+64, ..., c+448. Zufallskanten fluchten nicht 8-mal.
    # Zinken-Fenster asymmetrisch [-4..+2]: der Drum-Fill, den die Novelty als
    # Kantenbeginn sieht, liegt im letzten Takt VOR der Grenze — Beat 1 bleibt
    # die Grenze selbst. Intro >= 8 Beats (mindestens 2 Takte Vorlauf existieren
    # immer; verhindert Halbsektions-Alias mit unmoeglichem Mini-Intro).
    JIT_PRE, JIT_POST = 4, 2
    START_MIN = min(8, max_off)
    score8 = np.full(max_off + 1, -np.inf)
    for c in range(START_MIN, max_off + 1):
        s = 0.0
        for k in range(8):
            b = c + 64 * k
            lo = max(0, b - JIT_PRE)
            hi = min(n, b + JIT_POST)
            s += float(np.max(novz[lo:hi + 1]))
        # Energie-Polaritaet: rauf am Start, runter am Ende
        lo0, hi0 = max(0, c - JIT_PRE), min(n, c + JIT_POST)
        loE, hiE = (max(0, c + BODY_BEATS - JIT_PRE),
                    min(n, c + BODY_BEATS + JIT_POST))
        s += 0.5 * float(np.max(stepz[lo0:hi0 + 1]))
        s -= 0.5 * float(np.min(stepz[loE:hiE + 1]))
        score8[c] = s

    best = int(np.argmax(score8))
    e = min(best + BODY_BEATS, n)
    start_sec = float(beat_times[best])
    end_sec = float(beat_times[e]) if e < n else duration
    # Margin des Kamms: bester vs. bester Kandidat >= 8 Beats entfernt
    offs = np.arange(max_off + 1)
    far = offs[np.abs(offs - best) >= 8]
    margin8 = (float(score8[best]) - float(np.max(score8[far]))
               if far.size else float("nan"))

    # Staerkste Einzel-Kanten (Diagnose: existieren ueberhaupt Kanten?)
    peaks = []
    for b in np.argsort(nov[:n])[::-1]:
        if all(abs(int(b) - p) >= 4 for p in peaks):
            peaks.append(int(b))
        if len(peaks) >= 6:
            break

    # 64er-Raster-Phase: Novelty modulo 64 falten — auf welcher Phase liegen
    # die Arrangement-Kanten? (Beobachtung #49: Spitzen exakt auf einem
    # 64er-Lattice, aber phasenverschoben zur Gehoer-Marke.)
    fold = np.zeros(64)
    fold_cnt = np.zeros(64)
    for b in range(n):
        fold[b % 64] += novz[b]
        fold_cnt[b % 64] += 1
    fold_mean = fold / np.maximum(fold_cnt, 1)
    lattice_phase = int(np.argmax(fold_mean))
    lattice_strength = float(fold_mean[lattice_phase] -
                             np.median(fold_mean))

    order = np.argsort(score8)[::-1][:5]
    return {
        "ok": True, "n_beats": n, "bpm": float(bpm),
        "beat_period": beat_period, "max_off": max_off,
        "best": best, "end": e, "start_sec": start_sec, "end_sec": end_sec,
        "score": score, "score_t": score_t, "score8": score8,
        "margin8": margin8,
        "novz": novz, "stepz": stepz,
        "peaks": peaks, "beat_times": beat_times,
        "lattice_phase": lattice_phase,
        "lattice_strength": lattice_strength,
        "top": [(int(o), float(score8[o])) for o in order],
    }


# ---------------------------------------------------------------------------
# Ausgabe
# ---------------------------------------------------------------------------

def report(song: dict, res: dict) -> dict:
    print(f"=== #{song['id']}  {song['title']}  ({song['filename']})")
    if not res["ok"]:
        print(f"    ÜBERSPRUNGEN: {res['reason']}\n")
        return {"ok": False}

    bt, bp = res["beat_times"], res["beat_period"]
    print(f"    Beatraster: bpm≈{res['bpm']:.1f}  Beats={res['n_beats']}  "
          f"Beat≈{bp * 1000:.0f} ms  Suchraum=0..{res['max_off']}")
    pk = "  ".join(f"{b}({bt[b]:.1f}s)" if b < len(bt) else f"{b}(Ende)"
                   for b in res["peaks"])
    print(f"    Novelty-Spitzen (Kante an Beat): {pk}")
    print(f"    Bester Start (8-Zinken-Kamm): Beat {res['best']} → "
          f"{res['start_sec']:.2f}s   Ende: Beat {res['end']} → "
          f"{res['end_sec']:.2f}s   margin={res['margin8']:.2f}")
    print("    Top-5 (Beat:score8): " +
          "  ".join(f"{o}:{s:.2f}" for o, s in res["top"]))

    out = {"ok": True, "id": song["id"]}
    ref = song.get("ref_start")
    if ref is None and song.get("gt_start") is not None:
        ref = song["gt_start"]
    if ref is not None:
        ref_off = int(np.argmin(np.abs(bt - ref)))
        ref_c = min(ref_off, res["max_off"])
        rank = int(np.sum(res["score8"] > res["score8"][ref_c]))
        rank_t = int(np.sum(res["score_t"] > res["score_t"][ref_c]))
        err_s = res["start_sec"] - ref
        err_b = err_s / bp
        nz, sz = res["novz"], res["stepz"]
        re_ = min(ref_c + BODY_BEATS, res["n_beats"])
        ref_phase = ref_off % 64
        delta = (res["lattice_phase"] - ref_phase) % 64
        print(f"    REFERENZ: {ref:.2f}s (Beat {ref_off})   "
              f"Fehler = {err_s:+.2f}s ({err_b:+.1f} Beats)")
        print(f"      Rang der Referenz: kamm8={rank}  nur-Timbre-Paar={rank_t} "
              f"(0 = Spitze)")
        print(f"      Terme an Referenz: nov(start)={nz[ref_c]:+.2f} "
              f"step(start)={sz[ref_c]:+.2f}  |  nov(ende)={nz[re_]:+.2f} "
              f"step(ende)={sz[re_]:+.2f}")
        print(f"      64er-Raster: Kanten-Phase={res['lattice_phase']} "
              f"(Stärke {res['lattice_strength']:.2f})  Referenz-Phase={ref_phase}"
              f"  → Delta=(Kante−Ref) mod 64 = {delta}")
        out.update({"err_b": err_b, "rank": rank, "rank_t": rank_t,
                    "delta": delta, "lattice_strength": res["lattice_strength"],
                    "margin8": res["margin8"]})
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
    ranks_t = sorted(r["rank_t"] for r in ok)
    top3 = sum(1 for r in ok if r["rank"] <= 2)
    top3_t = sum(1 for r in ok if r["rank_t"] <= 2)
    print(f"  Ränge kamm8:      {ranks}   → Referenz in Top-3: {top3}/{len(ok)}")
    print(f"  Ränge Paar (alt): {ranks_t}   → Referenz in Top-3: {top3_t}/{len(ok)}")
    print("\n  Details (id: Fehler in Beats | Rang | margin8 | Raster-Delta):")
    for r in sorted(ok, key=lambda x: abs(x["err_b"])):
        print(f"    #{r['id']:<4} {r['err_b']:+6.1f}b  | Rang {r['rank']:<3} "
              f"| m8={r.get('margin8', 0):.2f} "
              f"| Delta {r.get('delta', '?'):>2}")
    deltas = [r["delta"] for r in ok if "delta" in r]
    print(f"\n  Raster-Deltas gesammelt: {sorted(deltas)}")
    print("  (Konstantes Delta über Songs ⇒ Kanten-Phase + Konstante = "
          "Startphase ⇒ Detektor gefunden)")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    for _stream in (sys.stdout, sys.stderr):   # Windows-Konsole ist cp1252
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default=str(TEST_DIR / "callers_caddy.db"))
    ap.add_argument("--music", default=str(TEST_DIR / "music"))
    ap.add_argument("--ids", required=True,
                    help="Komma-Liste von Song-IDs")
    ap.add_argument("--ref-starts", default=None,
                    help='Gehör-Referenzen "id:sekunden,..." (nur Auswertung)')
    ap.add_argument("--K", type=int, default=16,
                    help="Novelty-Fensterbreite in Beats (Default 16)")
    ap.add_argument("--slack", type=int, default=1,
                    help="Toleranz der 448er-Paarung in Beats (Default 1)")
    args = ap.parse_args()

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
                sid_s, sec_s = part.split(":")
                ref_starts[int(sid_s)] = float(sec_s)
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
            res = analyze(path, K=args.K, slack=args.slack)
        except Exception as e:
            print(f"=== #{s['id']}  {s['title']}")
            print(f"    FEHLER bei Analyse: {e}\n")
            continue
        rows.append(report(s, res))

    print_summary(rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
