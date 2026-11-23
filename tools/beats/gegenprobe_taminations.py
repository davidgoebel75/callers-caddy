"""intern#164: Gegenprobe der CALLERLAB-Beat-Tabelle gegen einen Taminations-Messlauf.

Aufruf (aus dem Repo-Stamm):
  python -I tools/beats/gegenprobe_taminations.py <db> <messlauf-ordner> [--min-n 15]

<db>               Kopie einer App-DB (nur lesend), z. B. die Testbasis vom 2026-11-08.
                   Liefert die Zuordnung Kartentext -> App-Calls (call_text_mappings,
                   call_text_figures_extra), also dieselbe wie in der App.
<messlauf-ordner>  tam_input.json, tam_results.json, pruefband.json eines Messlaufs aus
                   intern#163 (z. B. kontrolle_2026-11-15, Branch choreo-engines-all-the).

Gezaehlt werden nur Zeilen gruener Sequenzen (Urteil Pruefband), ohne einleitende Calls,
deren Kartentext genau EINEN App-Call hat. Je Call der Tabelle:
- Median, Quartile und Anzahl der Taminations-Beats,
- Wert der Standard-Variante und Abweichung zum Median,
- die Variante, deren Wert dem Median am naechsten liegt (Hinweis fuer die Standardwahl).

Taminations zaehlt nach der Animation (inkl. Zurechtruecken), CALLERLAB ab Kontaktpunkt.
Der Median ist eine Plausibilitaetspruefung, nie ein Wert fuer die Tabelle.
Das Ergebnis geht nach stdout; zum Ablegen umleiten.
"""
import argparse
import collections
import csv
import json
import os
import sqlite3
import statistics as st
import sys

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
CSV_PATH = os.path.join(HERE, "callerlab_timing.csv")
VALUE_TYPES = ("fest", "bereich", "dynamisch")
STD_NOTE = "Standard-Variante vorgeschlagen, bitte bestaetigen"  # aus zuordnung_vorschlag.py


def entity_map(db_path):
    """Kartentext -> Menge App-Calls (Haupt-Call + weitere Figuren)."""
    con = sqlite3.connect(f"file:{db_path}?immutable=1", uri=True)
    m = collections.defaultdict(set)
    for t, e in con.execute("SELECT call_text, entity_id FROM call_text_mappings "
                            "WHERE entity_id IS NOT NULL"):
        m[t].add(e)
    for t, e in con.execute("SELECT call_text, entity_id FROM call_text_figures_extra"):
        m[t].add(e)
    return m


def samples(folder, emap):
    load = lambda n: json.load(open(os.path.join(folder, n), encoding="utf-8"))  # noqa: E731
    inp = {s["id"]: s for s in load("tam_input.json")}
    res = load("tam_results.json")
    band = {r["id"]: r for r in load("pruefband.json")}
    out = collections.defaultdict(list)
    for r in res:
        sid = r["id"]
        if not r.get("ok") or band.get(sid, {}).get("urteil") != "gruen" or sid not in inp:
            continue
        s = inp[sid]
        for i, (text, b) in enumerate(zip(s["orig"], r.get("beats") or [])):
            if i < s.get("n_start", 0) or b is None:
                continue
            ents = emap.get(text, set())
            if len(ents) == 1:
                out[next(iter(ents))].append(float(b))
    return out


def row_value(r):
    lo = float(r["beats"])
    hi = float(r["beats_bis"]) if r["beats_bis"] else lo
    return lo, hi


def dist(med, lo, hi):
    return 0.0 if lo <= med <= hi else (med - hi if med > hi else med - lo)


def fmt(lo, hi):
    return f"{lo:g}" if lo == hi else f"{lo:g}-{hi:g}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("db")
    ap.add_argument("folder")
    ap.add_argument("--min-n", type=int, default=15)
    ap.add_argument("--bestaetigen", action="store_true",
                    help="Standard-Variante, die Taminations bestaetigt (Abschnitt C), in der "
                         "CSV als geprueft markieren (Hinweis in 'pruefen' entfernen)")
    a = ap.parse_args()

    tb = samples(a.folder, entity_map(a.db))
    rows = list(csv.DictReader(open(CSV_PATH, encoding="utf-8-sig"), delimiter=";"))
    groups = collections.OrderedDict()
    for r in rows:
        groups.setdefault((r["programm"], r["call"]), []).append(r)

    out, ohne = [], []
    for (prog, call), grp in groups.items():
        ents = {e for r in grp for e in r["entity_ids"].split("|") if e and "+" not in e}
        v = [b for e in ents for b in tb.get(e, [])]
        vals = [r for r in grp if r["typ"] in VALUE_TYPES and r["beats"]]
        if not vals:
            continue
        if len(v) < a.min_n:
            ohne.append(f"{prog} {call} (n={len(v)})")
            continue
        med = st.median(v)
        q = st.quantiles(v, n=4) if len(v) >= 4 else [med, med, med]
        std = next((r for r in vals if r["standard"] == "1"), vals[0])
        slo, shi = row_value(std)
        d = dist(med, slo, shi)
        near = min(vals, key=lambda r: abs(dist(med, *row_value(r))))
        out.append(dict(grp=grp, prog=prog, call=call, n=len(v), med=med, q1=q[0], q3=q[2], d=d,
                        std=std["variante"] or "(ohne)", sval=fmt(slo, shi),
                        near=near["variante"] or "(ohne)", nval=fmt(*row_value(near)),
                        multi=len(vals) > 1, other=near is not std
                        and abs(dist(med, *row_value(near))) < abs(d)))

    c = collections.Counter("im Wert" if o["d"] == 0 else "bis 1" if abs(o["d"]) <= 1
                            else "bis 2" if abs(o["d"]) <= 2 else "mehr als 2" for o in out)
    print(f"Gegenprobe CALLERLAB gegen Taminations, Messlauf {os.path.basename(a.folder.rstrip('/'))}")
    print(f"{len(out)} Calls mit mind. {a.min_n} Vorkommen. Standard-Variante gegen Median: "
          + ", ".join(f"{k} {c[k]}" for k in ("im Wert", "bis 1", "bis 2", "mehr als 2")))

    print("\n## A. Standard-Variante: eine andere Variante passt besser zum Median\n")
    print(f"{'Prog':4} {'Call':40} {'n':>5} {'Median':>6} {'Q1-Q3':>9}  Standard -> naeher")
    for o in sorted((o for o in out if o["multi"] and o["other"]), key=lambda o: -o["n"]):
        print(f"{o['prog']:4} {o['call'][:40]:40} {o['n']:5} {o['med']:6g} "
              f"{o['q1']:4g}-{o['q3']:<4g}  {o['std']} ({o['sval']}) -> {o['near']} ({o['nval']})")

    print("\n## B. Standard-Wert weicht um mehr als 2 Beats vom Median ab\n")
    print(f"{'Prog':4} {'Call':40} {'n':>5} {'Median':>6} {'Q1-Q3':>9} {'Chart':>6} {'Abw.':>5}")
    for o in sorted((o for o in out if abs(o["d"]) > 2), key=lambda o: -abs(o["d"])):
        print(f"{o['prog']:4} {o['call'][:40]:40} {o['n']:5} {o['med']:6g} "
              f"{o['q1']:4g}-{o['q3']:<4g} {o['sval']:>6} {o['d']:+5g}")

    print("\n## C. Standard-Variante bestaetigt (mehrere Varianten, Standard am naechsten)\n")
    for o in out:
        if o["multi"] and not o["other"]:
            print(f"{o['prog']:4} {o['call'][:40]:40} n={o['n']:<5} Median {o['med']:g}, "
                  f"Standard {o['std']} ({o['sval']})")

    if a.bestaetigen:
        n = 0
        for o in out:
            if o["multi"] and not o["other"]:
                for r in o["grp"]:
                    neu = "; ".join(x for x in r["pruefen"].split("; ") if x and x != STD_NOTE)
                    n += neu != r["pruefen"]
                    r["pruefen"] = neu
        with open(CSV_PATH, "w", encoding="utf-8-sig", newline="") as f:
            wr = csv.DictWriter(f, fieldnames=list(rows[0]), delimiter=";", lineterminator="\n")
            wr.writeheader()
            wr.writerows(rows)
        print(f"[--bestaetigen] {n} Zeilen als geprueft markiert", file=sys.stderr)

    print(f"\n## D. Ohne genug Taminations-Daten (< {a.min_n}): {len(ohne)} Calls\n")
    print("; ".join(ohne))


if __name__ == "__main__":
    main()
