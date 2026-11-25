"""Gegenprobe des Choreo-Mappings gegen einen Referenz-Export (intern#247).

Aufruf (aus dem Repo-Stamm):
  python -I tools/choreo_mapping_check.py <db> <referenz.json> [--band <pruefband.json>]
                                          [--golden <ziel.json> --n 300]

<db>           Kopie einer App-DB (nur lesend), z. B. die Testbasis vom 2026-11-08
<referenz.json> Export des Pruefstands (tam_input.json eines Messlaufs), gleiche DB
Engine: CC_TAM_CLI oder src/caddy/choreo/bin/tam_cli.exe (fuer die Heimplatz-Pruefung).

Prueft fuer jede Sequenz der Referenz, ob caddy.choreo.mapping dieselben Felder liefert
(n_start, end, orig, lines, lines_woertlich, lines_ergaenzt). Mit --golden wird zusaetzlich
eine Stichprobe (jede k-te Sequenz plus alle mit zweiter Fassung) als Testdaten geschrieben:
Eingabe (calls, type, App-Namen der vorkommenden Texte) und erwartetes Ergebnis.
"""
import json
import os
import sqlite3
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
from caddy.choreo import mapping  # noqa: E402
from caddy.choreo import pruefband  # noqa: E402
from caddy.choreo.engine import TamEngine  # noqa: E402
from song_db_sequences import read_choreo_call_names  # noqa: E402

FIELDS = ("n_start", "end", "orig", "lines", "lines_woertlich", "lines_ergaenzt")
BAND_FIELDS = ("stufe1", "band", "resolved", "fail_pos", "pruefpunkt", "kriterium", "tam",
               "tam_probe", "aufl_warnung", "urteil", "beats_koerper", "beats_ende", "beats",
               "lesart")


def export_item(sid, prep, eng):
    req = mapping.heimplatz_request(prep)
    resp = eng.run({"id": sid, **req}) if req else None
    lines, zweit, art = mapping.finish(prep, resp)
    item = {"n_start": prep["n_start"], "end": prep["end"], "orig": prep["orig"], "lines": lines}
    if art == "woertlich":
        item["lines_woertlich"] = zweit
    elif art == "ergaenzt":
        item["lines_ergaenzt"] = zweit
    return item


def main():
    args = sys.argv[1:]
    golden = args[args.index("--golden") + 1] if "--golden" in args else None
    n_golden = int(args[args.index("--n") + 1]) if "--n" in args else 300
    db, ref_path = args[0], args[1]
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    app = read_choreo_call_names(db)
    ref = json.load(open(ref_path, encoding="utf-8"))
    band_ref = None
    if "--band" in args:
        band_ref = {b["id"]: b for b in json.load(
            open(args[args.index("--band") + 1], encoding="utf-8"))}
    eng = TamEngine()
    if not eng.available():
        sys.exit("Engine fehlt (CC_TAM_CLI setzen)")
    diffs, samples = 0, []
    step = max(1, len(ref) // n_golden)
    for k, r in enumerate(ref):
        sid = r["id"]
        calls = [x[0] for x in con.execute(
            "select call_text from sequence_calls where sequence_id=? order by position", (sid,))]
        prep = mapping.prepare(calls, r["type"], app)
        item = export_item(sid, prep, eng)
        bad = [f for f in FIELDS if item.get(f) != r.get(f)]
        if band_ref is not None:
            zweit = item.get("lines_woertlich") or item.get("lines_ergaenzt")
            art = "woertlich" if item.get("lines_woertlich") else ("ergaenzt" if zweit else None)
            res = pruefband.analyse(lambda q: eng.run({"id": sid, **q}), r["type"], item["end"],
                                    item["n_start"], item["lines"], zweit, art)
            exp = band_ref[sid]
            bad += [f"band.{f}" for f in BAND_FIELDS if res.get(f) != exp.get(f)]
        if bad:
            diffs += 1
            if diffs <= 10:
                print(f"{sid}: abweichend in {bad}")
        if golden and (k % step == 0 or prep.get("zweit")):
            samples.append({"id": sid, "type": r["type"], "calls": calls,
                            "app": {c: app[c] for c in calls if c in app},
                            "heimplatz_response":
                                eng.run({"id": sid, **mapping.heimplatz_request(prep)})
                                if prep.get("zweit") else None,
                            "expected": {f: r.get(f) for f in FIELDS}})
    eng.close()
    print(f"{len(ref)} Sequenzen, {diffs} abweichend")
    if golden:
        for s in samples:                      # nur die Felder der Heimplatz-Pruefung behalten
            h = s["heimplatz_response"]
            if h:
                s["heimplatz_response"] = {"positions": h.get("positions"),
                                           "animation": h.get("animation")}
        with open(golden, "w", encoding="utf-8") as f:
            json.dump(samples, f, ensure_ascii=False, separators=(",", ":"))
        print(f"{len(samples)} Testfaelle nach {golden}")
    sys.exit(1 if diffs else 0)


if __name__ == "__main__":
    main()
