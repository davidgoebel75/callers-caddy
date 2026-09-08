"""Experiment: Body-Sektion per INHALTS-Vergleich der 7 Abschnitte lokalisieren.

Motivation (David, 2026-07-06)
------------------------------
Der Produktions-Detektor (singing_body_detect.py) rastet bei ~8 von 55 Songs auf
der FALSCHEN 64er-Sektion ein (Fehler ±8/16/32/64 Beats). Grund: die reine
Grenz-/Kamm-Zielfunktion ist SHIFT-SYMMETRISCH — verschiebt man das 448-Fenster
um 64, landen wieder alle 8 Zinken auf echten Kanten. Sie bestimmt also nur die
PHASE (c mod 64), nicht die absolute Sektion.

Der absolute Anker steckt im INHALT ZWISCHEN den Grenzen: das 448-Fenster ist
endlich. Sitzt es korrekt, sind alle 7 Abschnitte echter Body. Verschoben frisst
sich ein Randabschnitt in Intro/Outro — und der passt inhaltlich NICHT zu den
anderen. Die innere Kohaerenz der 7 Abschnitte ist damit NICHT shift-symmetrisch
und bricht die ±64-Degeneriertheit.

Zwei Schaerfungen gegenueber dem frueheren (gescheiterten) Chroma-Kohaerenz-
Versuch:
  1. TIMBRE statt nur Chroma. Instrumentale Intros spielen die Melodie oft schon
     mit (Chroma_Intro ≈ Chroma_Body) — aber sind duenner instrumentiert
     (Timbre trennt, wo Chroma versagt).
  2. KEY-CHANGE im 7. Abschnitt. Viele Singing Calls modulieren den Closer um
     +1/+2 Halbtoene. Das ist ein POSITIONSFESTES, asymmetrisches Ereignis bei
     c+384 → pinnt c absolut und killt jeden ±32/±64-Alias. Nur Bonus wenn
     vorhanden (nicht jeder Song moduliert), nie Strafe.

Dieses Skript vergleicht mehrere Score-Varianten gegen die 55(+) Ohr-Marken und
misst je Variante: |Fehler| in Beats, ≤2/≤4-Trefferquote und — der eigentliche
Test — ob es die harten Fehl-Locks des Produktions-Kamms repariert, ohne die
bereits guten Songs zu verschlechtern. GUI-frei, kein Eingriff in App-Code.

Aufruf (aus 2_Test/ oder beliebig)::

    python 1_Source/src/tools/singing_body_content.py
    python .../singing_body_content.py --ids 442,206,27,455 --verbose
"""

from __future__ import annotations

import argparse
import io
import os
import sqlite3
import sys
from pathlib import Path

import numpy as np

_THIS = Path(__file__).resolve()
SRC_DIR = _THIS.parents[1]           # 1_Source/src
REPO_ROOT = _THIS.parents[3]         # Callers-Caddy/
TEST_DIR = REPO_ROOT / "2_Test"
OUT_DIR = _THIS.parent / "experiment_out"

sys.path.insert(0, str(SRC_DIR))

# Produktions-Feature-Pipeline wiederverwenden (identische Beats/Features).
from singing_body_detect import (        # noqa: E402
    _beat_features, _novelty_and_step, _z, BODY_BEATS, SECTION_BEATS,
)
from bpm_detector import detect_beat_grid  # noqa: E402
from loop_finder import _load_audio        # noqa: E402
from singing_section_experiment import resolve_audio_path  # noqa: E402

N_SECTIONS = 7
BREAK_IDX = (0, 3, 6)                  # Opener / Middle Break / Closer
FIGURE_IDX = (1, 2, 4, 5)             # die vier Figuren
CATASTROPHES = {206, 211, 236, 442, 27, 415, 118, 455}  # Kamm-Fehl-Locks (>6 b)


# ---------------------------------------------------------------------------
# Ground Truth
# ---------------------------------------------------------------------------

def load_ground_truth(gt_file: str, db_path: str) -> dict:
    """Ohr-Marken aus ground_truth_55.txt UNION volle DB-Marken (id -> start_sec)."""
    gt: dict = {}
    if os.path.isfile(gt_file):
        for line in io.open(gt_file, encoding="utf-8"):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split(";")
            try:
                gt[int(parts[0])] = float(parts[1])
            except (ValueError, IndexError):
                continue
    con = sqlite3.connect(db_path)
    cur = con.cursor()
    by: dict = {}
    for sid, k, v in cur.execute(
        "SELECT song_id, key, value FROM song_properties "
        "WHERE key IN ('singing_start_m1','singing_end_m1')"
    ):
        by.setdefault(sid, {})[k] = v
    for sid, kv in by.items():
        if "singing_start_m1" in kv and "singing_end_m1" in kv and sid not in gt:
            try:
                gt[sid] = float(kv["singing_start_m1"])
            except (ValueError, TypeError):
                pass
    con.close()
    return gt


def song_meta(db_path: str, ids: list) -> dict:
    con = sqlite3.connect(db_path)
    cur = con.cursor()
    out = {}
    for sid in ids:
        row = cur.execute(
            "SELECT filename, title, base_bpm FROM songs WHERE id=?", (sid,)
        ).fetchone()
        if row:
            out[sid] = {"filename": row[0], "title": row[1] or row[0],
                        "bpm": float(row[2]) if row[2] else None}
    con.close()
    return out


# ---------------------------------------------------------------------------
# Feature-Aufbereitung
# ---------------------------------------------------------------------------

def _norm_rows(x: np.ndarray) -> np.ndarray:
    """Z-Norm je Spalte (ueber alle Beats), dann L2 je Zeile (Beat) → Kosinus."""
    z = (x - x.mean(axis=0)) / (x.std(axis=0) + 1e-9)
    return z / (np.linalg.norm(z, axis=1, keepdims=True) + 1e-9)


def _beat_envelope(mono, sr, beat_times, duration, K=16) -> np.ndarray:
    """Rohe Amplituden-Huellkurve je Beat: K Sub-Frame-RMS-Werte pro Beat.

    Davids "unfilterter Wellenform-Vergleich" — aber rektifiziert (RMS), damit er
    NICHT an der 5-ms-Phasenverschiebung des Beat-Rasters zerbricht. Kein Spektrum,
    kein Mel, kein Chroma: nur der Lautheits-/Rhythmus-Mikroverlauf. Zeile i =
    Envelope-Kontur von Beat i (K Werte)."""
    n = len(beat_times)
    edges = np.concatenate([beat_times, [duration]])
    env = np.zeros((n, K))
    for i in range(n):
        s = int(edges[i] * sr)
        e = max(s + K, int(edges[i + 1] * sr))
        seg = mono[s:min(e, len(mono))]
        if seg.size < K:
            continue
        sub = np.array_split(seg, K)
        env[i] = [float(np.sqrt(np.mean(f.astype(np.float64) ** 2)) + 1e-12)
                  for f in sub]
    return np.log10(env)          # log → Dynamik komprimieren wie bei Timbre


def _coherence(feat_rows: np.ndarray, c: int):
    """7×7 Beat-fuer-Beat-Aehnlichkeit ab Offset c + abgeleitete Kennzahlen.

    feat_rows: (n_beats, D), zeilen-L2-normiert. Rueckgabe (coh, contrast, sim).
      coh      = mittlere Aehnlichkeit ALLER Abschnittspaare (off-diagonal)
      contrast = intra(Break-Break, Fig-Fig) − inter(Break-Fig)   [strukturiert]
    """
    body = feat_rows[c:c + BODY_BEATS].reshape(N_SECTIONS, SECTION_BEATS, -1)
    sim = np.einsum("ipd,jpd->ij", body, body) / float(SECTION_BEATS)
    n = N_SECTIONS
    coh = (sim.sum() - np.trace(sim)) / (n * n - n)
    intra, inter = [], []
    for grp in (BREAK_IDX, FIGURE_IDX):
        for a in range(len(grp)):
            for b in range(a + 1, len(grp)):
                intra.append(sim[grp[a], grp[b]])
    for a in BREAK_IDX:
        for b in FIGURE_IDX:
            inter.append(sim[a, b])
    contrast = float(np.mean(intra)) - float(np.mean(inter))
    return float(coh), contrast, sim


def _edge(feat_rows: np.ndarray, c: int, n_beats: int) -> float:
    """Aehnlichkeit der 64 Beats vor c / nach c+448 zu den Body-Abschnitten.

    Phasengleich auf dem 64er-Raster. Niedrig = Intro/Outro ist anderes Material
    → sauberer Blockrand (der asymmetrische Anker). Mittel aus pre/post."""
    body = feat_rows[c:c + BODY_BEATS].reshape(N_SECTIONS, SECTION_BEATS, -1)

    def seg_vs_body(seg, from_end):
        L = seg.shape[0]
        if L < 8:
            return None
        ref = body[:, SECTION_BEATS - L:, :] if from_end else body[:, :L, :]
        return float(np.einsum("kd,pkd->", seg, ref) / (L * N_SECTIONS))

    vals = []
    pre_len = min(SECTION_BEATS, c)
    if pre_len > 0:
        v = seg_vs_body(feat_rows[c - pre_len:c], True)
        if v is not None:
            vals.append(v)
    avail = n_beats - (c + BODY_BEATS)
    post_len = min(SECTION_BEATS, max(0, avail))
    if post_len > 0:
        v = seg_vs_body(feat_rows[c + BODY_BEATS:c + BODY_BEATS + post_len], False)
        if v is not None:
            vals.append(v)
    return float(np.mean(vals)) if vals else 0.0


def _keychange(chroma: np.ndarray, c: int) -> float:
    """Key-Change-Bonus: passt Abschnitt 7 besser zu einer TRANSPONIERTEN Version
    der Abschnitte 1..6? +1/+2 Halbtoene = Chroma-Rotation um 1/2 Bins.

    >0 → Closer moduliert nach oben → das spricht fuer genau dieses c (der
    Wechsel faellt exakt auf die Sektion-6/7-Grenze c+384). Sonst ~0."""
    base = chroma[c:c + 6 * SECTION_BEATS].mean(axis=0)
    base = base / (np.linalg.norm(base) + 1e-9)
    sec7 = chroma[c + 6 * SECTION_BEATS:c + BODY_BEATS].mean(axis=0)
    sec7 = sec7 / (np.linalg.norm(sec7) + 1e-9)
    d0 = float(sec7 @ base)
    up = max(float(sec7 @ np.roll(base, r)) for r in (1, 2))
    return up - d0


def _comb_baseline(novz, crashz, stepz, bassz, n, start_min, max_off):
    """Reproduziert den Produktions-Kamm-Score (ohne Snap/Calib) → Roh-argmax."""
    score = np.full(max_off + 1, -np.inf)
    for c in range(start_min, max_off + 1):
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
        score[c] = s
    return score


# ---------------------------------------------------------------------------
# Analyse eines Songs
# ---------------------------------------------------------------------------

SCORE_VARIANTS = [
    "kamm",            # Produktions-Kamm (Baseline)
    "coh_tim",         # nur Timbre-Kohaerenz
    "coh_tim-edge",    # Timbre-Kohaerenz − Randaehnlichkeit  (Davids Kernidee)
    "coh_chr-edge",    # Chroma-Variante zum Vergleich
    "contrast_tim",    # strukturierter Break/Figur-Kontrast (Timbre)
    "coh_env",         # rohe RMS-Huellkurve, nur Kohaerenz
    "coh_env-edge",    # rohe RMS-Huellkurve, Kohaerenz − Rand
    "contrast_env",    # rohe RMS-Huellkurve, Break/Figur-Kontrast
    "content_full",    # coh_tim − edge_tim + 0.5*coh_chr + keychange-Bonus
    "kamm+content",    # Kamm-Phase + Content waehlt die Sektion (2-stufig)
]


def analyze(path: str, bpm_hint):
    mono, sr = _load_audio(path)
    duration = len(mono) / sr
    hint = bpm_hint if (bpm_hint and bpm_hint > 40.0) else None
    bpm, beat_times = detect_beat_grid(path, bpm=hint)
    beat_times = np.asarray(beat_times, dtype=float)
    n = len(beat_times)
    if n < BODY_BEATS + 2:
        return None, f"zu kurz ({n} Beats)"
    bp = float(np.median(np.diff(beat_times)))

    timbre, chroma, energy, e_bass, e_high, kick = _beat_features(
        mono, sr, beat_times, duration)
    nov, step = _novelty_and_step(timbre, energy, K=16)
    novz, stepz = _z(nov), _z(step)
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

    tim_rows = _norm_rows(timbre)         # Chroma ist bereits zeilen-L2 (Produktion)
    env_rows = _norm_rows(_beat_envelope(mono, sr, beat_times, duration))

    max_off = n - BODY_BEATS
    start_min = min(8, max_off)
    rng = range(start_min, max_off + 1)

    coh_tim = np.full(max_off + 1, -np.inf)
    coh_chr = np.full(max_off + 1, -np.inf)
    coh_env = np.full(max_off + 1, -np.inf)
    con_tim = np.full(max_off + 1, -np.inf)
    con_env = np.full(max_off + 1, -np.inf)
    edge_tim = np.zeros(max_off + 1)
    edge_chr = np.zeros(max_off + 1)
    edge_env = np.zeros(max_off + 1)
    keyc = np.zeros(max_off + 1)
    for c in rng:
        ct, cont_t, _ = _coherence(tim_rows, c)
        cc, _, _ = _coherence(chroma, c)
        ce, cont_e, _ = _coherence(env_rows, c)
        coh_tim[c], con_tim[c], coh_chr[c] = ct, cont_t, cc
        coh_env[c], con_env[c] = ce, cont_e
        edge_tim[c] = _edge(tim_rows, c, n)
        edge_chr[c] = _edge(chroma, c, n)
        edge_env[c] = _edge(env_rows, c, n)
        keyc[c] = _keychange(chroma, c)

    kamm = _comb_baseline(novz, crashz, stepz, bassz, n, start_min, max_off)

    def masked(arr):
        m = np.full(max_off + 1, -np.inf)
        for c in rng:
            m[c] = arr[c]
        return m

    scores = {
        "kamm": kamm,
        "coh_tim": masked(coh_tim),
        "coh_tim-edge": masked(coh_tim - edge_tim),
        "coh_chr-edge": masked(coh_chr - edge_chr),
        "contrast_tim": masked(con_tim),
        "coh_env": masked(coh_env),
        "coh_env-edge": masked(coh_env - edge_env),
        "contrast_env": masked(con_env),
        "content_full": masked(coh_tim - edge_tim + 0.5 * coh_chr + keyc),
    }
    # 2-stufig: Kamm liefert Phase (mod 64); Content waehlt unter den ~7
    # Sektionskandidaten derselben Phase.
    kamm_best = int(np.nanargmax(np.where(np.isfinite(kamm), kamm, np.nan)))
    phase = kamm_best % SECTION_BEATS
    cont = coh_tim - edge_tim + 0.5 * coh_chr + keyc
    sect_cand = [c for c in rng if c % SECTION_BEATS == phase]
    two = max(sect_cand, key=lambda c: cont[c]) if sect_cand else kamm_best
    two_arr = np.full(max_off + 1, -np.inf)
    two_arr[two] = 1.0
    scores["kamm+content"] = two_arr

    best = {name: int(np.nanargmax(np.where(np.isfinite(s), s, -np.inf)))
            for name, s in scores.items()}

    # Intrinsische Konfidenz (OHNE Ground Truth): Kamm-Margin = Abstand des besten
    # Kamm-Offsets zum besten mind. 8 Beats entfernten. Flach = mehrdeutig.
    offs = np.arange(max_off + 1)
    fin = np.isfinite(kamm)
    far = offs[(np.abs(offs - best["kamm"]) >= 8) & fin]
    kamm_margin = (float(kamm[best["kamm"]]) - float(kamm[far].max())
                   if far.size else float("nan"))
    return {
        "n": n, "bp": bp, "bpm": float(bpm), "beat_times": beat_times,
        "max_off": max_off, "start_min": start_min,
        "best": best, "scores": scores, "keyc": keyc,
        "kamm_margin": kamm_margin,
    }, None


# ---------------------------------------------------------------------------
# Lauf & Auswertung
# ---------------------------------------------------------------------------

def ref_beat(beat_times, ref_sec):
    return int(np.argmin(np.abs(beat_times - ref_sec)))


def main() -> int:
    for st in (sys.stdout, sys.stderr):
        try:
            st.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default=str(TEST_DIR / "callers_caddy.db"))
    ap.add_argument("--music", default=str(TEST_DIR / "music"))
    ap.add_argument("--gt", default=str(OUT_DIR / "ground_truth_55.txt"))
    ap.add_argument("--ids", default=None, help="Komma-Liste; sonst alle GT-Songs")
    ap.add_argument("--verbose", action="store_true",
                    help="Pro Song alle Score-Varianten + Key-Change ausgeben")
    args = ap.parse_args()

    if not os.path.isfile(args.db):
        print(f"FEHLER: DB nicht gefunden: {args.db}")
        return 1

    gt = load_ground_truth(args.gt, args.db)
    if args.ids:
        ids = [int(x) for x in args.ids.replace(" ", "").split(",") if x]
    else:
        ids = sorted(gt)
    meta = song_meta(args.db, ids)

    rows = []
    for sid in ids:
        if sid not in gt or sid not in meta:
            continue
        m = meta[sid]
        path = resolve_audio_path(m["filename"], args.music)
        if not path:
            print(f"#{sid:<4} {m['title'][:32]:32}  ÜBERSPRUNGEN (Datei fehlt)")
            continue
        try:
            res, err = analyze(path, m["bpm"])
        except Exception as e:
            print(f"#{sid:<4} {m['title'][:32]:32}  FEHLER: {e}")
            continue
        if res is None:
            print(f"#{sid:<4} {m['title'][:32]:32}  ÜBERSPRUNGEN ({err})")
            continue

        rb = ref_beat(res["beat_times"], gt[sid])
        errs = {name: res["best"][name] - rb for name in SCORE_VARIANTS}
        kc_ref = res["keyc"][rb] if rb <= res["max_off"] else float("nan")

        # Intrinsische Unsicherheits-Signale (KEIN Ground Truth verwendet):
        picks = [res["best"][mn] for mn in
                 ("kamm", "coh_tim", "contrast_tim", "coh_env")]
        disagree = max(picks) - min(picks)             # Spannweite der Methoden
        consensus = sum(1 for p in picks if abs(p - res["best"]["kamm"]) <= 4)
        rows.append({"id": sid, "title": m["title"], "rb": rb,
                     "errs": errs, "kc_ref": kc_ref,
                     "cat": sid in CATASTROPHES,
                     "kamm_err": errs["kamm"], "disagree": disagree,
                     "consensus": consensus, "margin": res["kamm_margin"],
                     "picks": {mn: res["best"][mn] for mn in SCORE_VARIANTS}})

        if args.verbose:
            print(f"\n=== #{sid}  {m['title']}   (ref Beat {rb} = {gt[sid]:.2f}s, "
                  f"n={res['n']}, bpm≈{res['bpm']:.1f})")
            for name in SCORE_VARIANTS:
                e = errs[name]
                flag = " ✓" if abs(e) <= 4 else (" ✗✗" if abs(e) > 6 else "")
                print(f"    {name:16} Beat {res['best'][name]:3d}  "
                      f"Fehler {e:+3d}b{flag}")
            print(f"    Key-Change @ref = {kc_ref:+.3f}  "
                  f"({'moduliert' if kc_ref > 0.02 else 'kein/schwach'})")

    # ---- Zusammenfassung -------------------------------------------------
    print("\n" + "=" * 78)
    print(f"ZUSAMMENFASSUNG — {len(rows)} Songs "
          f"(davon {sum(r['cat'] for r in rows)} Kamm-Fehl-Locks markiert)")
    print("=" * 78)
    header = f"  {'Variante':16} {'≤2b':>6} {'≤4b':>6} {'>6b':>6} {'Median':>7}   Fehl-Locks-repariert"
    print(header)
    for name in SCORE_VARIANTS:
        ae = [abs(r["errs"][name]) for r in rows]
        le2 = sum(1 for x in ae if x <= 2)
        le4 = sum(1 for x in ae if x <= 4)
        gt6 = sum(1 for x in ae if x > 6)
        med = float(np.median(ae)) if ae else float("nan")
        fixed = sum(1 for r in rows if r["cat"] and abs(r["errs"][name]) <= 4)
        ncat = sum(1 for r in rows if r["cat"])
        print(f"  {name:16} {le2:3d}/{len(rows):<3} {le4:3d}/{len(rows):<3} "
              f"{gt6:3d}    {med:5.1f}    {fixed}/{ncat}")

    print("\n  Key-Change-Diagnose (kc@ref > 0.02 = Closer moduliert):")
    modul = [r for r in rows if r["kc_ref"] > 0.02]
    print(f"    moduliert bei {len(modul)}/{len(rows)} Songs — "
          f"IDs: {sorted(r['id'] for r in modul)}")

    # ---- KERNFRAGE: Kann man die Ausreisser OHNE Ground Truth vorhersagen? ----
    print("\n" + "-" * 78)
    print("  INTRINSISCHE VORHERSAGE — Ausreisser erkennen OHNE Beat-1-Zeiten")
    print("-" * 78)
    wrong = [r for r in rows if abs(r["kamm_err"]) > 6]      # tatsaechlich falsch
    good = [r for r in rows if abs(r["kamm_err"]) <= 6]
    print(f"  Tatsaechlich: {len(wrong)} falsch (>6b), {len(good)} gut (≤6b)\n")

    def gate_eval(key, thresholds, hi_is_bad=True):
        """Fuer jeden Schwellwert: wie viele Falsche gefangen / Gute faelschlich geflaggt."""
        print(f"  Flag-Regel '{key}' ({'hoch' if hi_is_bad else 'niedrig'}=unsicher):")
        print(f"    {'Schwelle':>9} {'gefangen':>14} {'Fehlalarm':>14} {'Abdeckung-auto':>15}")
        for t in thresholds:
            if hi_is_bad:
                flagged_bad = [r for r in wrong if r[key] >= t]
                flagged_good = [r for r in good if r[key] >= t]
            else:
                flagged_bad = [r for r in wrong if r[key] <= t]
                flagged_good = [r for r in good if r[key] <= t]
            auto = len(rows) - len(flagged_bad) - len(flagged_good)
            print(f"    {t:>9.1f} {len(flagged_bad):>3}/{len(wrong):<3}      "
                  f"{len(flagged_good):>3}/{len(good):<3}      "
                  f"{auto:>3}/{len(rows)} still uebernommen")

    # --- Welches Methoden-Subset trennt am guenstigsten? (Rechenzeit sparen) ---
    # Timbre-Methoden (coh_tim/contrast_tim) sind GRATIS — sie fallen aus den
    # Features, die der Kamm ohnehin rechnet. Nur coh_env braucht einen 2. Pass.
    subsets = {
        "Kamm+coh_tim  (gratis)":       ("kamm", "coh_tim"),
        "Kamm+contrast_tim (gratis)":   ("kamm", "contrast_tim"),
        "Kamm+2×Timbre (gratis)":       ("kamm", "coh_tim", "contrast_tim"),
        "Kamm+coh_env (1 Extra-Pass)":  ("kamm", "coh_env"),
        "alle 4 (Extra-Pass)":          ("kamm", "coh_tim", "contrast_tim", "coh_env"),
    }
    print("  SUBSET-VERGLEICH — kleinste disagree unter den 11 Falschen (=sichere")
    print("  Untergrenze) und Fehlalarm/Abdeckung an genau dieser Schwelle:")
    print(f"    {'Subset':30} {'min_bad':>8} {'gefangen':>9} {'Fehlalarm':>10} {'auto':>7}")
    for label, names in subsets.items():
        def dis(r):
            ps = [r["picks"][x] for x in names]
            return max(ps) - min(ps)
        wrong_dis = [dis(r) for r in wrong]
        t = min(wrong_dis)                      # sichere Untergrenze (kein Leak)
        caught = sum(1 for r in wrong if dis(r) >= t)
        false_al = sum(1 for r in good if dis(r) >= t)
        auto = len(rows) - caught - false_al
        print(f"    {label:30} {t:>8} {caught:>4}/{len(wrong):<3} "
              f"{false_al:>4}/{len(good):<3} {auto:>4}/{len(rows)}")
    print()

    gate_eval("disagree", [8, 12, 16, 24, 32], hi_is_bad=True)
    print()
    gate_eval("consensus", [1, 2, 3], hi_is_bad=False)
    print()
    gate_eval("margin", [1.0, 2.0, 3.0, 4.0], hi_is_bad=False)

    print("\n  Rohdaten je Song (sortiert nach Uneinigkeit):")
    print(f"    {'id':>5} {'kamm_err':>9} {'disagree':>9} {'consensus':>10} {'margin':>7}  falsch?")
    for r in sorted(rows, key=lambda x: -x["disagree"]):
        mk = "  <<< FALSCH" if abs(r["kamm_err"]) > 6 else ""
        print(f"    #{r['id']:<4} {r['kamm_err']:+8d} {r['disagree']:>9} "
              f"{r['consensus']:>10} {r['margin']:>7.2f}{mk}")

    print("\n  Fehl-Lock-Detail (Kamm >6b) — hilft Content?")
    print(f"    {'id':>5} {'kamm':>6} {'coh_tim-edge':>13} {'content_full':>13} "
          f"{'kamm+content':>13} {'kc@ref':>7}")
    for r in sorted(rows, key=lambda x: -abs(x["errs"]["kamm"])):
        if abs(r["errs"]["kamm"]) <= 6:
            continue
        print(f"    #{r['id']:<4} {r['errs']['kamm']:+5d} "
              f"{r['errs']['coh_tim-edge']:+12d} {r['errs']['content_full']:+12d} "
              f"{r['errs']['kamm+content']:+12d}  {r['kc_ref']:+.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
