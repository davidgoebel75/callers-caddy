"""Experiment: Automatische Erkennung des 7×64-Body eines Singing Calls.

Ziel (Stufe A automatisieren)
-----------------------------
Ein Singing Call besteht aus 7 gleich langen Teilen à 64 Beats:

    1 Opener · 2 Figure · 3 Figure · 4 Middle Break · 5 Figure · 6 Figure · 7 Closer

Intro/Outro werden ignoriert. Bisher klickt der Nutzer Anfang und Ende manuell;
dieses Skript versucht, den Body (448 Beats) automatisch im Song zu finden.

Kernidee — Ausrichtungsproblem mit EINEM Freiheitsgrad
------------------------------------------------------
Weil der Body starr 448 Beats lang ist und wir ein Beatraster haben, ist die
einzige Unbekannte: auf welchem Beat sitzt Teil 1 (Opener)? Wir schieben ein
448-Beat-Fenster über alle Beat-Offsets und bewerten je Position, wie gut die
BEKANNTE innere Struktur passt:

    - Teile 1/4/7 (Opener/Middle/Closer) ähneln sich untereinander stark
    - Teile 2/3/5/6 (Figuren)             ähneln sich untereinander stark
    - die beiden Gruppen unterscheiden sich voneinander

Als Fingerabdruck je Teil dient beat-synchrones Chroma (Melodie/Harmonie),
gemittelt über die 64 Beats des Teils. Intro/Outro erzeugen dieses saubere
Muster NICHT — nur der echte Body. Ein Medley (jeder Teil ein anderer Song)
zeigt kaum Selbstähnlichkeit → niedriger Score → ehrliches "unsicher".

Der Score ist damit kein angeschraubtes Extra, sondern fällt aus der Methode:
    contrast = mittlere Intra-Ähnlichkeit − mittlere Inter-Ähnlichkeit
    margin   = Abstand des besten Offsets zum besten weit entfernten Offset

Validierung
-----------
Gegen die bereits manuell gesetzten Marken (song_properties:
singing_start_m1 / singing_end_m1, in Sekunden). Ausgegeben wird der Fehler in
Beats sowie die aus der Marke abgeleitete Body-Länge (Selbsttest: ~448 Beats?).

GUI-frei und eigenständig (wie singing_sections.py / zip_import): nutzt nur die
vorhandene Feature-Pipeline aus loop_finder + bpm_detector, kein Qt, kein
Eingriff in App-Code.

Aufruf (aus beliebigem Verzeichnis)::

    python 1_Source/src/tools/singing_section_experiment.py
    python .../singing_section_experiment.py --song 535 --save-images
    python .../singing_section_experiment.py --db PFAD --music PFAD

Standardpfade zeigen auf 2_Test/.
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from pathlib import Path

import numpy as np

# --- Projektpfade & Import der vorhandenen Feature-Pipeline ------------------
_THIS = Path(__file__).resolve()
SRC_DIR = _THIS.parents[1]          # 1_Source/src
REPO_ROOT = _THIS.parents[3]        # Callers-Caddy/
TEST_DIR = REPO_ROOT / "2_Test"

sys.path.insert(0, str(SRC_DIR))    # loop_finder, bpm_detector importierbar machen

from loop_finder import (            # noqa: E402
    _load_audio, _compute_chroma_per_beat,
    _estimate_downbeat,
)
from bpm_detector import detect_beat_grid  # noqa: E402


# --- Struktur-Konstanten ----------------------------------------------------
SECTION_BEATS = 64
N_SECTIONS = 7
BODY_BEATS = SECTION_BEATS * N_SECTIONS          # 448

# 0-basierte Teil-Indizes: Breaks = 1/4/7, Figuren = 2/3/5/6
BREAK_IDX = (0, 3, 6)
FIGURE_IDX = (1, 2, 4, 5)


# ---------------------------------------------------------------------------
# Ground Truth aus der DB
# ---------------------------------------------------------------------------

def load_ground_truth(db_path: str) -> list:
    """Liest alle Songs mit gesetztem singing_start_m1 + singing_end_m1.

    Rueckgabe: Liste von dicts {id, filename, title, gt_start, gt_end}.
    (Nur Slot 1 = Primaerdatei; Varianten m2/m3… bleiben im Experiment aussen vor.)
    """
    con = sqlite3.connect(db_path)
    cur = con.cursor()
    props: dict = {}
    for sid, key, val in cur.execute(
        "SELECT song_id, key, value FROM song_properties "
        "WHERE key IN ('singing_start_m1', 'singing_end_m1')"
    ):
        props.setdefault(sid, {})[key] = val

    out = []
    for sid, kv in props.items():
        if "singing_start_m1" not in kv or "singing_end_m1" not in kv:
            continue
        try:
            gt_start = float(kv["singing_start_m1"])
            gt_end = float(kv["singing_end_m1"])
        except (ValueError, TypeError):
            continue
        row = cur.execute(
            "SELECT filename, title FROM songs WHERE id = ?", (sid,)
        ).fetchone()
        if not row:
            continue
        out.append({
            "id": sid, "filename": row[0], "title": row[1] or row[0],
            "gt_start": gt_start, "gt_end": gt_end,
        })
    con.close()
    out.sort(key=lambda d: d["id"])
    return out


def load_songs_by_ids(db_path: str, ids: list) -> list:
    """Laedt beliebige Songs per ID — GT (singing_start/end_m1) optional angehaengt.

    Fuer Songs ohne gesetzte Marken (z.B. neue Testfaelle, Medleys als
    Negativkontrolle) ist gt_start/gt_end None → der Detektor laeuft trotzdem,
    nur der Fehler-gegen-Marke-Block entfaellt.
    """
    con = sqlite3.connect(db_path)
    cur = con.cursor()
    out = []
    for sid in ids:
        row = cur.execute(
            "SELECT filename, title, base_bpm FROM songs WHERE id = ?", (sid,)
        ).fetchone()
        if not row:
            print(f"WARNUNG: Song-ID {sid} nicht in der DB gefunden.")
            continue
        kv = dict(cur.execute(
            "SELECT key, value FROM song_properties WHERE song_id = ? "
            "AND key IN ('singing_start_m1', 'singing_end_m1')", (sid,)))
        gt_start = gt_end = None
        try:
            if "singing_start_m1" in kv and "singing_end_m1" in kv:
                gt_start = float(kv["singing_start_m1"])
                gt_end = float(kv["singing_end_m1"])
        except (ValueError, TypeError):
            gt_start = gt_end = None
        out.append({"id": sid, "filename": row[0], "title": row[1] or row[0],
                    "gt_start": gt_start, "gt_end": gt_end,
                    "bpm": float(row[2]) if row[2] else None})
    con.close()
    return out


def resolve_audio_path(filename: str, music_dir: str) -> str | None:
    """Loest den DB-Dateinamen gegen den Musikordner auf."""
    cands = []
    if os.path.isabs(filename):
        cands.append(filename)
    cands.append(os.path.join(music_dir, filename))
    cands.append(os.path.join(music_dir, os.path.basename(filename)))
    for c in cands:
        if os.path.isfile(c):
            return c
    return None


# ---------------------------------------------------------------------------
# Kern: Body-Offset finden
# ---------------------------------------------------------------------------

def _section_similarity(chroma: np.ndarray, offset: int) -> np.ndarray:
    """7×7 Beat-fuer-Beat-Aehnlichkeit der Abschnitte ab `offset`.

    NICHT den Abschnitt zu einem Durchschnitts-Chroma verdichten (das kollabiert
    auf das ueber den ganzen Song fast konstante Tonart-Profil und macht alle
    Abschnitte ununterscheidbar). Stattdessen vergleichen wir die MELODIE-KONTUR
    Beat fuer Beat: Beat p von Abschnitt i gegen Beat p von Abschnitt j.

    chroma-Zeilen sind bereits L2-normiert (_compute_chroma) → Skalarprodukt =
    Kosinus. sim[i,j] = Mittel ueber die 64 Beat-Positionen von
    cos(chroma[i-ter Abschnitt, p], chroma[j-ter Abschnitt, p]).
    """
    body = chroma[offset:offset + BODY_BEATS].reshape(
        N_SECTIONS, SECTION_BEATS, 12)
    # einsum: Summe ueber d (=Kosinus je Beat) und ueber p, dann /64 = Mittel.
    return np.einsum("ipd,jpd->ij", body, body) / float(SECTION_BEATS)


def _cohesion(sim: np.ndarray) -> float:
    """Innere Kohaerenz = mittlere Aehnlichkeit ALLER Phrasen-Paare (ohne Diagonale).

    Hoch = die 7 Phrasen im Fenster gehoeren zur selben, sich wiederholenden
    Melodie (egal ob Break oder Figur). Das ist unser eigentliches Zielsignal.
    """
    n = sim.shape[0]
    off_diag = (sim.sum() - np.trace(sim)) / (n * n - n)
    return float(off_diag)


def _edge_similarity(chroma: np.ndarray, offset: int, n_beats: int) -> tuple:
    """Aehnlichkeit der 64 Beats DIREKT vor/nach dem Body zu den Body-Phrasen.

    Alle Phrasen liegen phasengleich auf dem 64er-Raster: Beat k vor dem Body
    entspricht Phrasenposition (64−L+k), Beat k nach dem Body der Position k.
    Darum ist ein Beat-fuer-Beat-Vergleich mit den Body-Phrasen phasenkorrekt.

    Niedrige Werte = Intro/Outro sind anderes Material → sauberer Blockrand.
    Rueckgabe (pre_sim, post_sim); None wenn zu wenig Beats am Rand (<8).
    """
    body = chroma[offset:offset + BODY_BEATS].reshape(
        N_SECTIONS, SECTION_BEATS, 12)

    def seg_vs_body(seg: np.ndarray, from_end: bool):
        L = seg.shape[0]
        if L < 8:                       # zu kurz fuer eine belastbare Aussage
            return None
        ref = body[:, SECTION_BEATS - L:, :] if from_end else body[:, :L, :]
        return float(np.einsum("kd,pkd->", seg, ref) / (L * N_SECTIONS))

    pre_len = min(SECTION_BEATS, offset)
    pre_sim = seg_vs_body(chroma[offset - pre_len:offset], from_end=True) \
        if pre_len > 0 else None

    avail = n_beats - (offset + BODY_BEATS)
    post_len = min(SECTION_BEATS, max(0, avail))
    post_sim = seg_vs_body(
        chroma[offset + BODY_BEATS:offset + BODY_BEATS + post_len],
        from_end=False) if post_len > 0 else None

    return pre_sim, post_sim


def _signature(sim: np.ndarray) -> tuple:
    """Diagnose-Kennzahl (nicht mehr fuer die Offset-Wahl): Break/Figure-Kontrast.

    Rueckgabe: (contrast, intra_mean, inter_mean, sim7x7).
    """
    intra, inter = [], []
    for group in (BREAK_IDX, FIGURE_IDX):
        for a_i in range(len(group)):
            for b_i in range(a_i + 1, len(group)):
                intra.append(sim[group[a_i], group[b_i]])
    for a in BREAK_IDX:
        for b in FIGURE_IDX:
            inter.append(sim[a, b])

    intra_mean = float(np.mean(intra)) if intra else 0.0
    inter_mean = float(np.mean(inter)) if inter else 0.0
    return intra_mean - inter_mean, intra_mean, inter_mean, sim


def analyze(filepath: str) -> dict:
    """Findet den besten Body-Offset und liefert alle Diagnosewerte."""
    mono, sr = _load_audio(filepath)
    duration = len(mono) / sr
    _bpm, beat_times = detect_beat_grid(filepath)
    beat_times = np.asarray(beat_times, dtype=float)
    n_beats = len(beat_times)
    if n_beats < BODY_BEATS + 1:
        return {"ok": False, "reason": f"zu kurz ({n_beats} Beats < {BODY_BEATS + 1})"}

    beat_period = float(np.median(np.diff(beat_times)))

    # Chroma pro Beat (Zeilen bereits L2-normiert) — Basis fuer Sequenzvergleich
    chroma = _compute_chroma_per_beat(mono, sr, beat_times, duration)  # (n_beats,12)

    # Je Offset zwei Signale berechnen und kombinieren:
    #   block    = Kohaerenz − Randaehnlichkeit   (stark bei uniformen Tunes)
    #   contrast = Break/Figur-Kontrast           (stark bei strukturierten)
    #   combined = block + contrast               (deckt beide Song-Typen ab)
    max_offset = n_beats - BODY_BEATS
    block = np.full(max_offset + 1, -np.inf)
    contrast = np.full(max_offset + 1, -np.inf)
    cohes = np.zeros(max_offset + 1)
    bound = np.zeros(max_offset + 1)
    for off in range(max_offset + 1):
        sim = _section_similarity(chroma, off)
        cohes[off] = _cohesion(sim)
        contrast[off] = _signature(sim)[0]
        pre_sim, post_sim = _edge_similarity(chroma, off, n_beats)
        edges = [e for e in (pre_sim, post_sim) if e is not None]
        bound[off] = float(np.mean(edges)) if edges else 0.0
        block[off] = cohes[off] - bound[off]
    combined = block + contrast

    # Downbeat-Snap: der Body beginnt auf einer Phrasen-"1" (alle 8 Beats).
    # _estimate_downbeat liefert, welche der 8 Positionen die musikalische "1"
    # ist → Kandidaten-Offsets auf genau diese Phase beschraenken.
    beat_positions = np.array([(i % 8) + 1 for i in range(n_beats)])
    downbeat_pos = int(_estimate_downbeat(mono, sr, beat_times, beat_positions))
    offs = np.arange(max_offset + 1)
    cand = offs[(offs % 8) == (downbeat_pos - 1)]
    if cand.size == 0:
        cand = offs  # Fallback (sollte nicht vorkommen)

    best_raw = int(np.argmax(combined))                 # ungesnappt (Diagnose)
    best = int(cand[int(np.argmax(combined[cand]))])    # auf Phrasen-"1" gesnappt

    # Margin unter den Phrasen-"1"-Kandidaten (naechster Kandidat >= 8 Beats weg)
    far = cand[np.abs(cand - best) >= 8]
    margin = (float(combined[best]) - float(np.max(combined[far]))
              if far.size else float("nan"))

    order = cand[np.argsort(combined[cand])[::-1][:5]]

    detected_start = float(beat_times[best])
    end_beat = best + BODY_BEATS
    detected_end = float(beat_times[end_beat]) if end_beat < n_beats \
        else detected_start + BODY_BEATS * beat_period

    _c, intra_mean, inter_mean, sim = _signature(_section_similarity(chroma, best))

    return {
        "ok": True,
        "n_beats": n_beats,
        "bpm": float(_bpm),
        "beat_period": beat_period,
        "best_offset": best,
        "best_raw": best_raw,
        "downbeat_pos": downbeat_pos,
        "detected_start": detected_start,
        "detected_end": detected_end,
        "combined": float(combined[best]),
        "block": float(block[best]),
        "cohesion": float(cohes[best]),
        "boundary": float(bound[best]),
        "margin": margin,
        "contrast": float(contrast[best]),
        "sim": sim,
        "top": [(int(o), float(combined[o])) for o in order],
        "block_curve": combined,   # fuer Referenz-Rang-Auswertung
        "beat_times": beat_times,
    }


# ---------------------------------------------------------------------------
# Ausgabe
# ---------------------------------------------------------------------------

def _print_matrix(sim: np.ndarray) -> None:
    print("    7×7 Ähnlichkeit (Zeilen/Spalten = Teile 1..7; Breaks=1,4,7):")
    header = "        " + " ".join(f"T{j + 1}  " for j in range(N_SECTIONS))
    print(header)
    for i in range(N_SECTIONS):
        cells = " ".join(f"{sim[i, j]:.2f}" for j in range(N_SECTIONS))
        print(f"      T{i + 1}  {cells}")


def _save_image(sim: np.ndarray, out_path: str, title: str) -> bool:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return False
    fig, ax = plt.subplots(figsize=(4, 4))
    im = ax.imshow(sim, vmin=0, vmax=1, cmap="magma")
    ax.set_xticks(range(N_SECTIONS)); ax.set_yticks(range(N_SECTIONS))
    ax.set_xticklabels([str(i + 1) for i in range(N_SECTIONS)])
    ax.set_yticklabels([str(i + 1) for i in range(N_SECTIONS)])
    ax.set_title(title, fontsize=8)
    fig.colorbar(im, ax=ax, shrink=0.8)
    fig.tight_layout()
    fig.savefig(out_path, dpi=110)
    plt.close(fig)
    return True


def report(song: dict, res: dict, img_dir: str | None) -> dict:
    """Druckt einen Song-Block und liefert Kennzahlen fuer die Zusammenfassung."""
    tag_medley = "/" in (song["title"] or "") or "medley" in (song["title"] or "").lower()
    head = f"=== #{song['id']}  {song['title']}  ({song['filename']})"
    if tag_medley:
        head += "   [Titel-Heuristik: evtl. Medley]"
    print(head)

    if not res["ok"]:
        print(f"    ÜBERSPRUNGEN: {res['reason']}\n")
        return {"ok": False}

    bp = res["beat_period"]
    print(f"    Beatraster: bpm≈{res['bpm']:.1f}  Beats={res['n_beats']}  "
          f"Beat≈{bp * 1000:.0f} ms")
    print(f"    Offset (auf Phrasen-1 gesnappt): Beat {res['best_offset']}  "
          f"→ Anfang {res['detected_start']:.2f}s   Ende {res['detected_end']:.2f}s")
    print(f"    Downbeat-Phase: Position {res['downbeat_pos']}/8   "
          f"(roher argmax war Beat {res['best_raw']})")
    print(f"    combined={res['combined']:.2f}  (BLOCK={res['block']:.2f} + "
          f"contrast={res['contrast']:.2f})   margin={res['margin']:.2f}")
    print("    Top-Kandidaten (Beat:combined): " +
          "  ".join(f"{o}:{c:.2f}" for o, c in res["top"]))
    _print_matrix(res["sim"])

    summary = {"ok": True, "id": song["id"], "medley_guess": tag_medley,
               "combined": res["combined"], "block": res["block"],
               "contrast": res["contrast"], "margin": res["margin"]}

    # Referenz-Anfang: DB-Marke bevorzugt, sonst Gehoer-Referenz (--ref-starts)
    if song.get("gt_start") is not None:
        eff_start, src = song["gt_start"], "DB-Marke"
    elif song.get("ref_start") is not None:
        eff_start, src = song["ref_start"], "Gehör-Ref"
    else:
        eff_start, src = None, None

    if eff_start is not None:
        err_start_s = res["detected_start"] - eff_start
        err_start_b = err_start_s / bp
        # Rang des Referenz-Beats in der Block-Kurve: 0 = Referenz IST das Maximum.
        bc = res["block_curve"]
        bt = res["beat_times"][:len(bc)]
        off_ref = int(np.argmin(np.abs(bt - eff_start)))
        rank = int(np.sum(bc > bc[off_ref]))
        print(f"    REFERENZ ({src}): Anfang={eff_start:.2f}s")
        print(f"      Fehler Anfang = {err_start_s:+.2f}s ({err_start_b:+.1f} Beats)"
              f"   [Detektor-Offset {res['best_offset']} vs. Referenz-Offset {off_ref}]")
        print(f"      Referenz-Beat: BLOCK={bc[off_ref]:.2f}  Rang {rank} "
              f"(0 = Spitze) — zeigt, ob das Signal stimmt und nur die Auflösung hakt")
        summary["err_start_b"] = err_start_b
        # Ende nur bei vollstaendiger DB-Marke (Gehoer-Ref liefert nur Anfang)
        if song.get("gt_end") is not None:
            gt_end = song["gt_end"]
            gt_len_beats = (gt_end - eff_start) / bp
            err_end_s = res["detected_end"] - gt_end
            err_end_b = err_end_s / bp
            print(f"      Ende={gt_end:.2f}s  Länge={gt_len_beats:.1f} Beats "
                  f"(Erwartung ~{BODY_BEATS})   "
                  f"Fehler Ende = {err_end_s:+.2f}s ({err_end_b:+.1f} Beats)")
            summary.update({"err_end_b": err_end_b, "gt_len_beats": gt_len_beats})
    else:
        print("    REFERENZ: (keine — nur Detektion)")

    if img_dir:
        os.makedirs(img_dir, exist_ok=True)
        out = os.path.join(img_dir, f"song_{song['id']}_sim7x7.png")
        if _save_image(res["sim"], out, f"#{song['id']} {song['title'][:30]}"):
            print(f"    Bild gespeichert: {out}")

    print()
    return summary


def print_summary(rows: list) -> None:
    ok = [r for r in rows if r.get("ok")]
    print("=" * 70)
    print(f"ZUSAMMENFASSUNG — {len(ok)} Songs analysiert")
    print("=" * 70)
    if not ok:
        return

    have_gt = [r for r in ok if "err_start_b" in r]
    if have_gt:
        for thr in (1, 2, 4):
            hits = sum(1 for r in have_gt if abs(r["err_start_b"]) <= thr)
            print(f"  Anfang-Treffer ≤ {thr} Beat(s): "
                  f"{hits}/{len(have_gt)}  ({100 * hits / len(have_gt):.0f}%)")
        med_start = float(np.median([abs(r["err_start_b"]) for r in have_gt]))
        print(f"  Median |Fehler Anfang|: {med_start:.1f} Beats")
        lens = [r["gt_len_beats"] for r in have_gt]
        print(f"  GT-Body-Länge: min={min(lens):.0f}  median="
              f"{np.median(lens):.0f}  max={max(lens):.0f}  (Erwartung {BODY_BEATS})")

    print("\n  combined-Verteilung (Confidence-Kandidat = Blockschärfe der Spitze):")
    for r in sorted(ok, key=lambda x: -x["combined"]):
        flag = " ← Medley-Verdacht" if r.get("medley_guess") else ""
        m = r.get("margin")
        m_s = f"{m:.2f}" if m == m else " nan"   # nan-Check
        hit = ""
        if "err_start_b" in r:
            hit = f"  |Fehler|={abs(r['err_start_b']):.1f}b"
        print(f"    #{r['id']:<4}  combined={r['combined']:.2f}  "
              f"(BLOCK={r['block']:.2f} contrast={r['contrast']:.2f})  "
              f"margin={m_s}{hit}{flag}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    # Windows-Konsole ist cp1252 → UTF-8 erzwingen, sonst crasht die Ausgabe an
    # Sonderzeichen (≈, ×, →) und deutschen Umlauten.
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default=str(TEST_DIR / "callers_caddy.db"),
                    help="Pfad zur SQLite-DB (Default: 2_Test/callers_caddy.db)")
    ap.add_argument("--music", default=str(TEST_DIR / "music"),
                    help="Musikordner (Default: 2_Test/music)")
    ap.add_argument("--song", type=int, default=None,
                    help="Nur diese Song-ID analysieren (aus der GT-Liste)")
    ap.add_argument("--ids", default=None,
                    help="Komma-Liste von Song-IDs — analysiert diese direkt, "
                         "auch ohne gesetzte Marken (GT optional)")
    ap.add_argument("--list", action="store_true",
                    help="Nur auflisten, welche Songs Ground Truth haben")
    ap.add_argument("--save-images", action="store_true",
                    help="7×7-Matrix je Song als PNG speichern (braucht matplotlib)")
    ap.add_argument("--ref-starts", default=None,
                    help="Gehör-Referenzen fuer den Anfang (ohne DB-Schreiben): "
                         "\"id:sekunden,...\" z.B. \"10:6.78,157:18.39\"")
    args = ap.parse_args()

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

    if not os.path.isfile(args.db):
        print(f"FEHLER: DB nicht gefunden: {args.db}")
        return 1

    if args.ids:
        try:
            id_list = [int(x) for x in args.ids.replace(" ", "").split(",") if x]
        except ValueError:
            print("FEHLER: --ids erwartet eine Komma-Liste von Zahlen.")
            return 1
        songs = load_songs_by_ids(args.db, id_list)
    else:
        songs = load_ground_truth(args.db)
        if args.song is not None:
            songs = [s for s in songs if s["id"] == args.song]

    if not songs:
        print("Keine passenden Songs gefunden "
              "(weder --ids noch gesetzte singing_start_m1/singing_end_m1).")
        return 0

    if args.list:
        print(f"{len(songs)} Songs mit Ground Truth:")
        for s in songs:
            print(f"  #{s['id']:<4} {s['title']}  "
                  f"(Anfang {s['gt_start']:.1f}s, Ende {s['gt_end']:.1f}s)")
        return 0

    for s in songs:                       # Gehör-Referenzen anheften
        if s["id"] in ref_starts:
            s["ref_start"] = ref_starts[s["id"]]

    img_dir = str(_THIS.parent / "experiment_out") if args.save_images else None
    rows = []
    for s in songs:
        path = resolve_audio_path(s["filename"], args.music)
        if not path:
            print(f"=== #{s['id']}  {s['title']}")
            print(f"    ÜBERSPRUNGEN: Audiodatei nicht gefunden ({s['filename']})\n")
            continue
        try:
            res = analyze(path)
        except Exception as e:  # robuster Experimentierlauf — ein Song stoppt nicht alles
            print(f"=== #{s['id']}  {s['title']}")
            print(f"    FEHLER bei Analyse: {e}\n")
            continue
        rows.append(report(s, res, img_dir))

    print_summary(rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
