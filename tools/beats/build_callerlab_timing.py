"""intern#164: Prueft die Pflegedatei `callerlab_timing.csv` und erzeugt `src/callerlab_timing.json`.

Die CSV wird nicht ausgeliefert. Die App liest das JSON beim Start und uebernimmt es in die DB.
Das Werkzeug nimmt die Tabelle nur an, wenn jede Zeile die Pruefung besteht; sonst listet es alle
Fehler auf und schreibt nichts.

Aufruf:
    python tools/beats/build_callerlab_timing.py          # pruefen und JSON schreiben
    python tools/beats/build_callerlab_timing.py --check  # nur pruefen, ob das JSON aktuell ist

Format des JSON: `version` (Inhalts-Hash der Zeilen; aendert sich genau dann, wenn sich die
Daten aendern, und steuert das Neubefuellen der DB), `notice`, `rows`. Jede Zeile traegt die
Spalten der CSV ohne `pruefen`, als Text wie in der CSV, damit `caddy.beats.calc.BeatTable`
CSV und JSON gleich liest.
"""
import collections
import csv
import hashlib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
SRC = os.path.join(ROOT, "src")
sys.path.insert(0, SRC)

from caddy.beats import variant_rules as vr  # noqa: E402
from caddy.beats.calc import CHART_ORDER  # noqa: E402

CSV_PATH = os.path.join(HERE, "callerlab_timing.csv")
JSON_PATH = os.path.join(SRC, "callerlab_timing.json")
REF_PATH = os.path.join(SRC, "reference_calls.json")

COLUMNS = ("programm", "call", "entity_ids", "variante", "typ", "beats", "beats_bis",
           "anything_ab", "quelle", "bemerkung", "standard", "variante_regel", "pruefen")
OUT_COLUMNS = tuple(c for c in COLUMNS if c != "pruefen")
TYPES = ("fest", "bereich", "call_plus", "plus_call", "max", "not_timed", "dynamisch")
SOURCES = ("MS 2026-07-05", "Plus 2026-07-05", "A1 2025-06-12", "A2 2025-06-12", "abgeleitet")
NOTICE = "Reprinted with permission of CALLERLAB."


def read_csv(path=CSV_PATH):
    with open(path, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f, delimiter=";")
        return list(reader.fieldnames or ()), list(reader)


def reference_ids(path=REF_PATH):
    with open(path, encoding="utf-8") as f:
        return {r["entity_id"] for r in json.load(f)["call_programs"]}


def _number(val):
    """Ganze Zahl >= 0 als Text -> int, sonst None."""
    return int(val) if val.isdigit() else None


def validate(fieldnames, rows, ref_ids):
    """Liste der Fehler (leer = Tabelle angenommen). Zeilennummern wie in Excel (Kopf = 1)."""
    errors = []
    if tuple(fieldnames) != COLUMNS:
        errors.append(f"Spalten {fieldnames} statt {list(COLUMNS)}")
        return errors

    seen = {}
    standard = collections.Counter()
    pairs = set()
    for no, r in enumerate(rows, start=2):
        def err(msg):
            errors.append(f"Zeile {no} ({r.get('programm')} {r.get('call')!r} "
                          f"{r.get('variante')!r}): {msg}")

        r = {k: (v or "").strip() if isinstance(v, str) else v for k, v in r.items()}
        if None in r:
            err("mehr Felder als Spalten")
            continue
        if r["pruefen"]:
            err(f"noch zu pruefen: {r['pruefen']}")
        if r["programm"] not in CHART_ORDER:
            err(f"programm {r['programm']!r} unbekannt, erlaubt: {', '.join(CHART_ORDER)}")
        if not r["call"]:
            err("call leer")
        if r["quelle"] not in SOURCES:
            err(f"quelle {r['quelle']!r} unbekannt, erlaubt: {', '.join(SOURCES)}")
        if r["standard"] not in ("", "1"):
            err(f"standard {r['standard']!r}: nur 1 oder leer")

        key = (r["programm"], r["call"], r["variante"])
        if key in seen:
            err(f"doppelt (wie Zeile {seen[key]})")
        seen.setdefault(key, no)

        typ = r["typ"]
        beats, bis, ab = (_number(r[c]) for c in ("beats", "beats_bis", "anything_ab"))
        for col in ("beats", "beats_bis", "anything_ab"):
            if r[col] and _number(r[col]) is None:
                err(f"{col} {r[col]!r}: keine ganze Zahl")
        if typ not in TYPES:
            err(f"typ {typ!r} unbekannt, erlaubt: {', '.join(TYPES)}")
        elif typ == "not_timed":
            if r["beats"] or r["beats_bis"]:
                err("not_timed ohne beats/beats_bis")
        else:
            if not r["beats"]:
                err(f"{typ} braucht beats")
            if typ == "bereich" and not r["beats_bis"]:
                err("bereich braucht beats_bis")
            if r["beats_bis"] and typ not in ("bereich", "dynamisch"):
                err(f"beats_bis nur bei bereich oder dynamisch, nicht bei {typ}")
            if beats is not None and bis is not None and bis <= beats:
                err(f"beats_bis {bis} nicht groesser als beats {beats}")
        if r["anything_ab"] and beats is not None and ab is not None and ab > beats + 1:
            err(f"anything_ab {ab} liegt hinter dem Ende ({beats} Beats)")

        try:
            vr.parse(r["variante_regel"])
        except vr.RuleError as e:
            err(f"variante_regel: {e}")

        if not r["entity_ids"]:
            err("entity_ids leer")
        for alt in r["entity_ids"].split("|"):
            parts = alt.split("+")
            if not alt or any(not p for p in parts):
                err(f"entity_ids {r['entity_ids']!r}: leeres Teilstueck")
                continue
            if len(set(parts)) != len(parts):
                err(f"entity_ids {alt!r}: Call doppelt in der Kombination")
            for p in parts:
                if p not in ref_ids:
                    err(f"entity_id {p!r} fehlt in reference_calls.json")
            if len(parts) == 1:
                pairs.add((r["programm"], alt))
                standard[(r["programm"], alt)] += r["standard"] == "1"

    for prog, ent in sorted(pairs):
        if standard[(prog, ent)] != 1:
            errors.append(f"{prog} {ent}: {standard[(prog, ent)]} Standard-Zeilen statt genau einer")
    return errors


def build(rows):
    """JSON-Inhalt aus geprueften Zeilen."""
    out = [{c: (r[c] or "").strip() for c in OUT_COLUMNS} for r in rows]
    payload = json.dumps(out, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    version = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
    return {"version": version, "notice": NOTICE, "rows": out}


def dump(data):
    """Eine Tabellenzeile je Textzeile, damit Diffs lesbar bleiben."""
    head = {k: v for k, v in data.items() if k != "rows"}
    lines = [json.dumps(r, ensure_ascii=False) for r in data["rows"]]
    inner = ",\n  ".join(lines)
    top = json.dumps(head, ensure_ascii=False, indent=1)[:-2]
    return f'{top},\n "rows": [\n  {inner}\n ]\n}}\n'


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    check = "--check" in argv
    fieldnames, rows = read_csv()
    errors = validate(fieldnames, rows, reference_ids())
    if errors:
        print(f"{len(errors)} Fehler in {os.path.relpath(CSV_PATH, ROOT)}:")
        for e in errors:
            print("  " + e)
        return 1
    text = dump(build(rows))
    current = open(JSON_PATH, encoding="utf-8").read() if os.path.exists(JSON_PATH) else None
    if check:
        if current != text:
            print("callerlab_timing.json ist nicht aktuell: build_callerlab_timing.py ausfuehren")
            return 1
        print(f"OK: {len(rows)} Zeilen, JSON aktuell")
        return 0
    if current == text:
        print(f"OK: {len(rows)} Zeilen, JSON unveraendert")
        return 0
    with open(JSON_PATH, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    print(f"OK: {len(rows)} Zeilen -> {os.path.relpath(JSON_PATH, ROOT)} "
          f"(version {json.loads(text)['version']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
