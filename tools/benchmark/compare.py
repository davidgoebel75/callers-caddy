"""Vergleicht zwei (oder mehr) Benchmark-JSON-Reports Schritt fuer Schritt.

Matcht die Schritte per 'name' und zeigt eine Tabelle mit ms je Lauf plus Delta
und Prozent gegenueber dem ERSTEN uebergebenen Lauf (der Baseline). Ideal fuer
den Vorher/Nachher-Vergleich oder leere vs. volle DB.

Aufruf:
    python tools/benchmark/compare.py vorher.json nachher.json
    python tools/benchmark/compare.py results/bench_*.json      # (Shell-Glob)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def load(path: str) -> dict:
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    steps = {s["name"]: s for s in doc.get("steps", [])}
    label = doc.get("run", {}).get("label") or Path(path).stem
    return {"label": label, "steps": steps, "path": path}


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("Mindestens zwei JSON-Reports angeben (erster = Baseline).")
        return 2

    runs = [load(p) for p in argv]
    base = runs[0]

    # Schritt-Reihenfolge aus der Baseline, dann alle weiteren Namen anhaengen.
    order = list(base["steps"].keys())
    for r in runs[1:]:
        for name in r["steps"]:
            if name not in order:
                order.append(name)

    headers = [r["label"] for r in runs]
    print(f"\nBaseline: {base['label']}  ({base['path']})\n")
    name_w = max([len("Schritt")] + [len(n) for n in order])
    col_w = 14

    line = "Schritt".ljust(name_w)
    for h in headers:
        line += "  " + h[:col_w].rjust(col_w)
    line += "  " + "Delta".rjust(10) + "  " + "%".rjust(7)
    print(line)
    print("-" * len(line))

    for name in order:
        row = name.ljust(name_w)
        base_ms = base["steps"].get(name, {}).get("ms")
        for r in runs:
            ms = r["steps"].get(name, {}).get("ms")
            row += "  " + ("-" if ms is None else f"{ms:.1f}").rjust(col_w)
        # Delta = letzter Lauf gegen Baseline
        last_ms = runs[-1]["steps"].get(name, {}).get("ms")
        if base_ms is not None and last_ms is not None and len(runs) >= 2:
            delta = last_ms - base_ms
            pct = (delta / base_ms * 100.0) if base_ms else 0.0
            row += "  " + f"{delta:+.1f}".rjust(10) + "  " + f"{pct:+.1f}".rjust(7)
        else:
            row += "  " + "-".rjust(10) + "  " + "-".rjust(7)
        print(row)

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
