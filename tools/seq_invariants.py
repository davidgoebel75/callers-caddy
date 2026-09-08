"""Summenprobe/Invarianten-Fingerabdruck des Sequenz-Datenmodells.

Zweck: beweist "vorher == nachher" bei der Umstellung auf calls_json (Option C).
Erfasst ueber die echte SongDatabase-API alle Groessen, die sich durch das
Refactoring NICHT aendern duerfen (fuer den Alt-Bestand mit <=15 Calls):

  - Sequenz-Gesamtzahl
  - Summe aller Calls (die eigentliche Summenprobe)
  - Pro-Sequenz-Callliste (Hash) via get_sequence_calls  -> deckt Dynamic Lyrics ab
  - "enthält"-Filter: Trefferzahl je entity_id (voller Fingerabdruck)
  - "Limit bis" / "nur"-Filter: Trefferzahl je Teaching-Order-Schwelle
  - Dublettenzahl, ungemappte Call-Texte, Distinct-Call-Texte

Aufruf:
    python seq_invariants.py --db PFAD --out snapshot.json
    python seq_invariants.py --db PFAD --compare snapshot.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys

_SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src")
sys.path.insert(0, os.path.abspath(_SRC))

from song_db import SongDatabase  # noqa: E402


def _hash(obj) -> str:
    return hashlib.sha256(
        json.dumps(obj, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


def capture(db_path: str) -> dict:
    db = SongDatabase(db_path)
    conn = db._conn

    snap: dict = {}

    # --- 1. Gesamtzahl ---
    snap["seq_total"] = conn.execute("SELECT COUNT(*) FROM sequences").fetchone()[0]

    # --- 2./3. Pro-Sequenz-Calllisten via get_sequence_calls (Dynamic-Lyrics-Pfad) ---
    ids = [r[0] for r in conn.execute("SELECT id FROM sequences ORDER BY id")]
    per_seq = {}
    calls_sum = 0
    for sid in ids:
        calls = [row[1] for row in db.get_sequence_calls(sid)]  # row[1] = call_text
        per_seq[str(sid)] = calls
        calls_sum += len(calls)
    snap["calls_sum"] = calls_sum
    snap["per_seq_hash"] = _hash(per_seq)
    snap["per_seq_len_hash"] = _hash({k: len(v) for k, v in per_seq.items()})

    # --- 4. "enthält"-Filter: Trefferzahl je entity_id ---
    entity_ids = [r[0] for r in conn.execute(
        "SELECT DISTINCT entity_id FROM call_text_mappings "
        "WHERE entity_id IS NOT NULL ORDER BY entity_id")]
    contains = {}
    for eid in entity_ids:
        contains[eid] = db.get_filtered_count(entity_id_filter=eid)
    snap["contains_entity_count"] = len(entity_ids)
    snap["contains_total_hits"] = sum(contains.values())
    snap["contains_hash"] = _hash(contains)

    # --- 5./6. Teaching-Order-Schwellen fuer "Limit bis" (max_to) und "nur" (min_to) ---
    tos = sorted({round(r[0], 6) for r in conn.execute(
        "SELECT DISTINCT teaching_order FROM teaching_order_calls "
        "WHERE teaching_order IS NOT NULL")})
    # zusaetzlich ein paar Programm-typische Schwellen
    thresholds = tos
    limit_counts = {str(t): db.get_filtered_count(max_to_filter=t) for t in thresholds}
    only_counts = {str(t): db.get_filtered_count(min_to_filter=t) for t in thresholds}
    snap["threshold_count"] = len(thresholds)
    snap["limit_hash"] = _hash(limit_counts)
    snap["only_hash"] = _hash(only_counts)
    snap["limit_total"] = sum(limit_counts.values())
    snap["only_total"] = sum(only_counts.values())

    # --- 7. Dubletten ---
    total, dup_groups, to_delete = db.count_duplicate_sequences()
    snap["dup_groups"] = dup_groups
    snap["dup_to_delete"] = to_delete

    # --- 8./9. Mapping-Statistik ---
    snap["unmapped_count"] = len(db.get_unmapped_call_texts())
    snap["distinct_call_texts"] = len(db.get_all_call_texts_with_mapping())

    return snap


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--out")
    ap.add_argument("--compare")
    args = ap.parse_args()

    snap = capture(args.db)

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(snap, f, ensure_ascii=False, indent=2)
        print(f"[Snapshot] geschrieben: {args.out}")

    print("\n=== Invarianten-Fingerabdruck ===")
    for k, v in snap.items():
        print(f"  {k:24} {v}")

    if args.compare:
        with open(args.compare, encoding="utf-8") as f:
            base = json.load(f)
        print("\n=== Vergleich gegen Baseline ===")
        ok = True
        keys = sorted(set(base) | set(snap))
        for k in keys:
            a, b = base.get(k), snap.get(k)
            flag = "OK  " if a == b else "DIFF"
            if a != b:
                ok = False
            print(f"  {flag} {k:24} baseline={a}  jetzt={b}")
        print("\nERGEBNIS:", "ALLE GLEICH ✓" if ok else "ABWEICHUNGEN ✗")
        sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
