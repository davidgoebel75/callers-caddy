"""Performance-Benchmark der Sequenz-Hotpaths (Option-C-Umstellung).

Misst dieselben Operationen an drei Punkten vergleichbar:
  T0  alter Code (field_1..15),   ~1705 Sequenzen
  T1  neuer Code (calls_json),    ~1705 Sequenzen   -> reiner Speicherart-Effekt
  T2  neuer Code,                 ~11700 Sequenzen   -> Skalierung

Deterministische Stichproben (sortiert + fester Stride), damit T0/T1/T2
denselben Arbeitsumfang messen. Je Operation Warmup + R Wiederholungen,
Ausgabe von Median und Minimum (ms).

Aufruf:
    python seq_bench.py --db PFAD --out bench_T0.json [--label T0]
    python seq_bench.py --db PFAD --compare bench_T0.json
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time

_SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src")
sys.path.insert(0, os.path.abspath(_SRC))

from song_db import SongDatabase  # noqa: E402


def _stride_sample(items: list, k: int) -> list:
    """Deterministische k-Stichprobe: sortiert, gleichmaessiger Stride."""
    items = sorted(items)
    if len(items) <= k:
        return items
    step = len(items) / k
    return [items[int(i * step)] for i in range(k)]


def _timeit(fn, reps: int) -> dict:
    # Warmup
    fn()
    samples = []
    for _ in range(reps):
        t = time.perf_counter()
        fn()
        samples.append((time.perf_counter() - t) * 1000.0)
    return {"median_ms": round(statistics.median(samples), 3),
            "min_ms": round(min(samples), 3)}


def bench(db_path: str, reps: int = 5) -> dict:
    db = SongDatabase(db_path)
    conn = db._conn

    seq_total = conn.execute("SELECT COUNT(*) FROM sequences").fetchone()[0]
    ids = [r[0] for r in conn.execute("SELECT id FROM sequences")]
    entity_ids = [r[0] for r in conn.execute(
        "SELECT DISTINCT entity_id FROM call_text_mappings "
        "WHERE entity_id IS NOT NULL")]
    tos = sorted({round(r[0], 6) for r in conn.execute(
        "SELECT DISTINCT teaching_order FROM teaching_order_calls "
        "WHERE teaching_order IS NOT NULL")})

    # Deterministische Stichproben (stabil ueber T0/T1/T2)
    id_sample = _stride_sample(ids, 200)
    ent_sample = _stride_sample(entity_ids, 60)
    thr_sample = _stride_sample(tos, 40)

    results = {"_meta": {
        "seq_total": seq_total,
        "sqlite": __import__("sqlite3").sqlite_version,
        "reps": reps,
        "id_sample": len(id_sample),
        "ent_sample": len(ent_sample),
        "thr_sample": len(thr_sample),
    }}

    # 1. "enthält"-Filter: COUNT je entity_id (ganze Stichprobe = 1 Messung)
    def op_contains_count():
        for e in ent_sample:
            db.get_filtered_count(entity_id_filter=e)
    results["contains_count"] = _timeit(op_contains_count, reps)

    # 2. "enthält"-Filter: erste Seite (50) je entity_id
    def op_contains_page():
        for e in ent_sample:
            db.get_filtered_sequences(entity_id_filter=e, limit=50, offset=0)
    results["contains_page50"] = _timeit(op_contains_page, reps)

    # 3. "Limit bis"-Filter: COUNT je Schwelle
    def op_limit_count():
        for t in thr_sample:
            db.get_filtered_count(max_to_filter=t)
    results["limit_count"] = _timeit(op_limit_count, reps)

    # 4. "nur"-Filter: COUNT je Schwelle
    def op_only_count():
        for t in thr_sample:
            db.get_filtered_count(min_to_filter=t)
    results["only_count"] = _timeit(op_only_count, reps)

    # 5. get_sequence_calls (Dynamic-Lyrics/Navigation-Hotpath) je id
    def op_get_calls():
        for sid in id_sample:
            db.get_sequence_calls(sid)
    results["get_sequence_calls_x200"] = _timeit(op_get_calls, reps)

    # 6. Tabellen-Seite ohne Filter (Scrollen)
    def op_table_page():
        db.get_filtered_sequences(limit=50, offset=0)
        db.get_filtered_sequences(limit=50, offset=500)
    results["table_page50"] = _timeit(op_table_page, reps)

    # 7. Dublettenzaehlung (GROUP BY ueber alle Calls)
    results["dup_count"] = _timeit(lambda: db.count_duplicate_sequences(), reps)

    # 8. Ungemappte Call-Texte sammeln (UNION/json_each ueber alle Sequenzen)
    results["unmapped_collect"] = _timeit(
        lambda: db.get_unmapped_call_texts_by_frequency(), reps)

    # 9. Alle Call-Texte mit Mapping (Distinct-Aggregat)
    results["distinct_calls_collect"] = _timeit(
        lambda: db.get_all_call_texts_with_mapping(), reps)

    return results


def run_series(db_path: str, series: int, reps: int) -> dict:
    """Fuehrt den Benchmark `series`-mal als unabhaengige Messreihe aus und
    aggregiert je Operation ueber die Reihen (Median/Min/Max/Stdev/CV%).

    Jede Reihe erhaelt eine frische DB-Verbindung (eigener SQLite-Cache-Zustand),
    damit die Reihen wirklich unabhaengig sind und System-/Cache-Rauschen sichtbar
    wird statt sich zu verstecken.
    """
    per_op: dict[str, list[float]] = {}
    meta = None
    for s in range(series):
        one = bench(db_path, reps=reps)
        meta = one["_meta"]
        for k, v in one.items():
            if k == "_meta":
                continue
            per_op.setdefault(k, []).append(v["median_ms"])

    agg = {"_meta": {**meta, "series": series}}
    for k, vals in per_op.items():
        mean = statistics.mean(vals)
        stdev = statistics.stdev(vals) if len(vals) > 1 else 0.0
        agg[k] = {
            "median_ms": round(statistics.median(vals), 3),
            "min_ms": round(min(vals), 3),
            "max_ms": round(max(vals), 3),
            "stdev_ms": round(stdev, 3),
            "cv_pct": round(100.0 * stdev / mean, 1) if mean else 0.0,
            "series_ms": [round(x, 3) for x in vals],
        }
    return agg


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--out")
    ap.add_argument("--label", default="")
    ap.add_argument("--reps", type=int, default=7,
                    help="Wiederholungen je Operation INNERHALB einer Reihe")
    ap.add_argument("--series", type=int, default=5,
                    help="Anzahl unabhaengiger Messreihen")
    ap.add_argument("--compare")
    args = ap.parse_args()

    res = run_series(args.db, series=args.series, reps=args.reps)
    if args.label:
        res["_meta"]["label"] = args.label

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(res, f, ensure_ascii=False, indent=2)
        print(f"[Bench] geschrieben: {args.out}")

    m = res["_meta"]
    print(f"\n=== Benchmark {args.label}  (seq_total={m['seq_total']}, "
          f"series={m['series']} x reps={m['reps']}) ===")
    print(f"  {'Operation':28} {'median':>9} {'min':>9} {'max':>9} {'CV%':>6}")
    for k, v in res.items():
        if k == "_meta":
            continue
        print(f"  {k:28} {v['median_ms']:>9.3f} {v['min_ms']:>9.3f} "
              f"{v['max_ms']:>9.3f} {v['cv_pct']:>6.1f}")

    if args.compare:
        with open(args.compare, encoding="utf-8") as f:
            base = json.load(f)
        bm = base["_meta"]
        print(f"\n=== Vergleich gegen {bm.get('label','baseline')} "
              f"(seq_total {bm['seq_total']} -> {m['seq_total']}) ===")
        print(f"  {'Operation':28} {'base_med':>9} {'neu_med':>9} {'Faktor':>8} {'CV% b/n':>10}")
        for k, v in res.items():
            if k == "_meta":
                continue
            b = base.get(k, {})
            bmed = b.get("median_ms")
            n = v["median_ms"]
            fac = f"{n/bmed:.2f}x" if bmed else "-"
            cvs = f"{b.get('cv_pct','?')}/{v['cv_pct']}"
            print(f"  {k:28} {bmed:>9} {n:>9} {fac:>8} {cvs:>10}")


if __name__ == "__main__":
    main()
