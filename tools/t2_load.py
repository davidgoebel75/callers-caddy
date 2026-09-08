"""T2-Lasttest-Loader: importiert die gescrapten Ceder-Sequenzen in eine
Wegwerf-Kopie, um die Performance bei ~11.700 Sequenzen zu messen.

Bewusst KEIN Eingriff in die echte 2_Test-DB — nur eine Kopie. Nutzt die
kanonische song_db-Logik (calls_json + Mirror + canonicalize) per Bulk-INSERT
und baut danach Index + max_teaching_order einmal auf.

Aufruf:
    python t2_load.py --db KOPIE.db --scrape PFAD/output
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys

_SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src")
sys.path.insert(0, os.path.abspath(_SRC))

from song_db import (SongDatabase, calls_to_json, calls_to_mirror_fields,  # noqa: E402
                     canonicalize_seq_type)


def load_scraped(scrape_dir: str) -> list:
    seen = set()
    out = []
    files = sorted(glob.glob(os.path.join(scrape_dir, "type_*__level_*.json")))
    for path in files:
        for seq in json.load(open(path, encoding="utf-8")):
            cid = seq.get("id", "")
            if cid and cid in seen:
                continue
            if cid:
                seen.add(cid)
            if seq.get("calls"):
                out.append(seq)
    print(f"[T2] {len(files)} Dateien, {len(out)} eindeutige Sequenzen mit Calls")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--scrape", required=True)
    args = ap.parse_args()

    seqs = load_scraped(args.scrape)
    db = SongDatabase(args.db)
    conn = db._conn

    before = conn.execute("SELECT COUNT(*) FROM sequences").fetchone()[0]

    rows = []
    for s in seqs:
        calls = s.get("calls", [])
        mirror = calls_to_mirror_fields(calls)
        rows.append(tuple(mirror) + (
            s.get("level", "") or "",
            None,  # max_teaching_order — spaeter berechnet
            canonicalize_seq_type(s.get("seq_type", "") or ""),
            s.get("difficulty", "") or "",
            calls_to_json(calls),
        ))

    conn.executemany(
        "INSERT INTO sequences (field_1, field_2, field_3, field_4, field_5, "
        "field_6, field_7, field_8, field_9, field_10, field_11, field_12, "
        "field_13, field_14, field_15, level_original, max_teaching_order, "
        "type, difficulty, calls_json) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
    conn.commit()

    after = conn.execute("SELECT COUNT(*) FROM sequences").fetchone()[0]
    print(f"[T2] Sequenzen: {before} -> {after} (+{after - before})")

    # Index + Cache einmal aufbauen (Bulk-INSERT umging insert_sequence)
    db.rebuild_sequence_calls_index()
    db.recompute_sequence_max_to()
    over15 = conn.execute(
        "SELECT COUNT(*) FROM sequences WHERE json_array_length(calls_json) > 15"
    ).fetchone()[0]
    print(f"[T2] Sequenzen mit >15 Calls: {over15}")
    print("[T2] fertig.")


if __name__ == "__main__":
    main()
