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
  - Mengengeruest je Tanzprogramm (BL-210.1): Trefferzahl im Band-Modus je
    Tanzprogramm-Wahl, mit und ohne "Nur"-Filter -> band_sets, band_counts,
    band_counts_hash

--compare stellt die Zahlen aus band_counts eintragsweise gegenueber (nicht nur
den Hash). Schluessel, die eine aeltere Baseline noch nicht kennt, werden als
"neu" gemeldet und gelten nicht als Abweichung — alte Snapshots bleiben also
vergleichbar.

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
from sequence_filter import filter_query_args  # noqa: E402


def _hash(obj) -> str:
    return hashlib.sha256(
        json.dumps(obj, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


# Die beiden Band-Linien der Referenz: alte Linie (Mainstream 29, Plus 39,
# A1 49) und 2026er Linie (30 / 40 / 50). Alles ab Band 60 (A2 und hoeher)
# steht in BEIDEN Linien, ebenso Basic 1/2 (10/20).
_BAND_LINE_OLD = (10, 20, 29, 39, 49, 60, 70, 80, 90, 100)
_BAND_LINE_2026 = (10, 20, 30, 40, 50, 60, 70, 80, 90, 100)


def band_set_for(band: int) -> list:
    """Kumulative Band-Menge eines Tanzprogramms — sortiert und deterministisch.

    Menge = alle Baender der Linie des Programms bis zum eigenen Band
    (einschliesslich), so wie ein Caller dieses Programms die tieferen Programme
    mitnutzen darf (vgl. ``main.py::_bands_for_program_ids``, das die Baender der
    tatsaechlich gewaehlten Programme einsammelt).

    Steht das Band in BEIDEN Linien (10, 20 und alles ab 60), ist die Menge die
    Vereinigung beider Linien bis zu diesem Band: ein A2-Caller darf die Figuren
    der alten UND der 2026er Programme darunter ansagen. Ein unbekanntes Band
    (selbst angelegtes Programm) wird genauso behandelt — alle bekannten Baender
    bis dorthin.
    """
    out = set()
    for line in (_BAND_LINE_OLD, _BAND_LINE_2026):
        if band in line:
            out.update(b for b in line if b <= band)
    if not out:
        for line in (_BAND_LINE_OLD, _BAND_LINE_2026):
            out.update(b for b in line if b <= band)
    return sorted(out)


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
    # BL-210: alle Figuren der Mengen. Ohne Mengen liefert die VIEW dieselben
    # entity_ids wie call_text_mappings, alte Snapshots bleiben vergleichbar.
    entity_ids = [r[0] for r in conn.execute(
        "SELECT DISTINCT entity_id FROM call_text_figures ORDER BY entity_id")]
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
    snap["unmapped_count"] = len(db.get_unmapped_call_texts_by_frequency())
    snap["distinct_call_texts"] = len(db.get_all_call_texts_with_mapping())

    # --- 10. Mengengeruest je Tanzprogramm (Band-Modus, BL-210.1) ---
    # Je Tanzprogramm zwei Zahlen, genau wie die Sequenz-Liste sie zeigt:
    #   bands_<code>      = Treffer mit der kumulativen Band-Menge des Programms
    #   bands_<code>_only = dasselbe mit "Nur"-Filter (Baender darunter gesetzt)
    band_counts = {}
    band_sets = 0
    for _pid, code, _label, _so, _dur, limit_to in db.get_all_dance_programs():
        if limit_to is None:
            continue   # Programm ohne Band -> keine Band-Menge ableitbar
        bands = band_set_for(int(limit_to))
        band_sets += 1
        # Dieselbe Regel wie die Sequenz-Liste (sequence_filter)
        band_counts[f"bands_{code}"] = db.get_filtered_count(
            **filter_query_args(bands=bands))
        band_counts[f"bands_{code}_only"] = db.get_filtered_count(
            **filter_query_args(bands=bands, only=True))
    snap["band_sets"] = band_sets
    snap["band_counts"] = band_counts
    snap["band_counts_hash"] = _hash(band_counts)

    return snap


def _compare_table(name: str, base: dict, now: dict) -> bool:
    """Stellt zwei Zahlen-Tabellen (z.B. band_counts) EINTRAGSWEISE gegenueber.

    Zeigt nur die Abweichungen — mit beiden Zahlen, damit man sieht WIE stark es
    auseinanderlaeuft, nicht nur dass ein Hash anders ist. Eintraege, die die
    Baseline noch nicht kannte (neues Tanzprogramm), gelten als "neu" und nicht
    als Abweichung. Rueckgabe: True = keine Abweichung.
    """
    diffs = []
    for key in sorted(set(base) | set(now)):
        a, b = base.get(key), now.get(key)
        if a == b:
            continue
        mark = "neu" if key not in base else ("fehlt" if key not in now else "DIFF")
        diffs.append((mark, key, a, b))
    real = [d for d in diffs if d[0] != "neu"]
    if not diffs:
        print(f"  OK   {name:24} {len(now)} Eintraege gleich")
        return True
    print(f"  {'DIFF' if real else 'NEU '} {name:24} "
          f"{len(diffs)} von {len(set(base) | set(now))} Eintraegen abweichend")
    for mark, key, a, b in diffs:
        print(f"       {mark:5} {key:30} baseline={a}  jetzt={b}")
    return not real


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
        if isinstance(v, dict):
            # Unter-Tabellen (band_counts) zeilenweise — die Zahlen sind das
            # eigentliche Ergebnis, nicht nur der Hash darueber.
            print(f"  {k:24} ({len(v)} Eintraege)")
            for sub, val in v.items():
                print(f"    {sub:30} {val}")
        else:
            print(f"  {k:24} {v}")

    if args.compare:
        with open(args.compare, encoding="utf-8") as f:
            base = json.load(f)
        print("\n=== Vergleich gegen Baseline ===")
        ok = True
        keys = sorted(set(base) | set(snap))
        for k in keys:
            a, b = base.get(k), snap.get(k)
            if isinstance(a, dict) or isinstance(b, dict):
                # Zahlen-Tabelle (band_counts): eintragsweise gegenueberstellen
                if not _compare_table(k, a if isinstance(a, dict) else {},
                                      b if isinstance(b, dict) else {}):
                    ok = False
                continue
            if k not in base:
                # Aeltere Baseline kennt den Schluessel nicht (z.B. band_sets
                # aus BL-210.1) -> kein Fehler, nur als "neu" ausweisen.
                print(f"  NEU  {k:24} jetzt={b}")
                continue
            flag = "OK  " if a == b else "DIFF"
            if a != b:
                ok = False
            print(f"  {flag} {k:24} baseline={a}  jetzt={b}")
        # Nur ASCII: die Windows-Konsole (cp1252) bricht bei Haken/Kreuz ab und
        # verschluckt damit genau das Ergebnis, auf das es ankommt.
        print("\nERGEBNIS:", "ALLE GLEICH" if ok else "ABWEICHUNGEN")
        sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
