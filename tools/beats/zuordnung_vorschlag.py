"""intern#164: Schlaegt je Zeile der CALLERLAB-Beat-Tabelle die App-Calls (entity_id) vor.

Einmal-Werkzeug fuer die Ersteinrichtung. Liest `callerlab_timing.csv` und die
gebuendelte Referenz `src/reference_calls.json`, ergaenzt die Spalten
`entity_ids`, `standard`, `variante_regel` und `pruefen` und schreibt die CSV zurueck.

- `entity_ids`: App-Calls der Zeile, mit `|` getrennt.
- `standard`: `1` = Standard-Variante des Calls (gilt ohne Square Flow, wenn der
  Kartentext die Variante nicht verraet). Bei nur einer Zeile je Call automatisch.
- `pruefen`: Grund, warum David die Zeile ansehen soll. Leer = sicher. Das
  Build-Werkzeug nimmt spaeter nur Tabellen an, in denen `pruefen` ueberall leer ist.

Aufruf (aus dem Repo-Stamm):  python tools/beats/zuordnung_vorschlag.py
Bereits gefuellte `entity_ids`/`standard` bleiben unangetastet (nur leere werden gefuellt).
"""
import csv
import difflib
import json
import os
import re
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
CSV_PATH = os.path.join(HERE, "callerlab_timing.csv")
REF_PATH = os.path.join(HERE, "..", "..", "src", "reference_calls.json")

NEW_COLS = ("entity_ids", "standard", "variante_regel", "pruefen")

# Programm-Familie der Chart -> Teaching-Order-Baender der Referenz
_PROG_BANDS = {"MS": (10, 39), "Plus": (39, 49), "A1": (49, 60), "A2": (60, 70)}


# Von Hand geklaert (Abgleich mit reference_calls.json und den Kartentexten der
# DB-Kopie 08.11.). Schreibweise: `|` = einer davon, `+` = alle zusammen in einer
# Zeile (Konzept + Call, z. B. All 4 Couples Pass Thru). Wert = (entity_ids,
# Pruefhinweis oder "").
OVERRIDES = {
    "Cast Off 3/4": ("call_cast_off_three_quarters", ""),
    "First Couple Go Left/Right, Next Couple Go Right/Left": ("call_first_go_next_go", ""),
    "Ladies Chain": ("call_two_ladies_chain", ""),
    "Promenade Couples": ("call_couples_promenade", ""),
    "Separate around 1 to a Line": ("call_separate_around_to_a_line", ""),
    "Separate around 2 to a Line": ("call_separate_around_to_a_line", ""),
    "Separate around 1 into the Middle": ("call_separate_around_come_into_middle", ""),
    "Separate around 2 into the Middle": ("call_separate_around_come_into_middle", ""),
    "Star Right / Left": ("call_right_hand_star|call_left_hand_star", ""),
    "Swing": ("call_swing", ""),
    "(Named Dancers) Trade": ("call_named_dancers_trade", ""),
    "Eight Chain 1, 2, 3, etc.": ("call_eight_chain_thru", ""),
    "Shoot the Star Full Around": ("call_shoot_the_star", ""),
    "Walk Around the Corner": ("call_walk_around", ""),
    "Any Hand (Anything)": ("concept_any_hand", ""),
    "Brace Thru (formerly Half Breed Thru)": ("call_brace_thru", ""),
    "Chain Reaction (1/4 Tag)": ("call_chain_reaction", ""),
    "Right (Left) Roll to a Wave": ("call_roll_to_a_wave", ""),
    "All 4 Couples Chase Right": ("concept_all_4_couples+call_chase_right", ""),
    "All 4 Couples Cross Trail Thru": ("concept_all_4_couples+call_cross_trail_thru", ""),
    "All 4 Couples Pass Thru": ("concept_all_4_couples+call_pass_thru", ""),
    "All 4 Couples Right and Left Thru": ("concept_all_4_couples+call_right_and_left_thru", ""),
    "All 4 Couples Star Thru": ("concept_all_4_couples+call_star_thru", ""),
    "All 8 Swing Thru": ("concept_all_8+call_swing_thru", ""),
    "All 8 Dixie Style to a Wave": ("concept_all_8+call_dixie_style_to_a_wave", ""),
    "All 8 Walk and Dodge": ("concept_all_8+call_walk_and_dodge", ""),
    "All 8 Mix": ("concept_all_8+call_mix", ""),
    "Recycle": ("call_recycle", ""),
    "Split / Box Counter Rotate": ("call_split_counter_rotate|call_box_counter_rotate", ""),
    "Split / Box Transfer": ("call_split_transfer|call_box_transfer", ""),
    "Zig Zag and variations": ("call_zig_zag", ""),
    "Promenade Home": ("call_couples_promenade", ""),
    "Swing and Promenade (Singing-Call-Ende)": ("call_swing+call_couples_promenade", ""),
    "Circulates": ("call_named_dancers_circulate|call_couples_circulate|call_all_eight_circulate"
                   "|call_split_circulate|call_single_file_circulate",
                   "Welche Circulates meint die Chart? Vorschlag: die fuenf MS-Circulates"),
}


# Standard-Variante von Hand, wo die Heuristik daneben liegt: Call -> Variante
STANDARD_OVERRIDES = {
    "Arm Turns": "1/2 around",
    "Allemande Left (or Allemande Right)": "1/2 Arm Turn",  # David: halber Arm Turn + Pass Thru
    "Dosado": "otherwise",
    "Forward and Back": "all others",
    "Square Thru / Left Square Thru": "FC 4",
    "Remake": "Others (including Grand)",
    "Circle Left (or Right)": "SS 8 Dancers full around",
    "Split Square Thru": "from Box full",
    # Parallele Teile (Bemerkung "parallel: ..."): es zaehlt die laengere Bewegung
    "Dive Thru": "Couple making arch",
    "Pass to the Center": "new Ends",
    "Spin Chain Thru": "resulting Centers",
}


def norm(s: str) -> str:
    s = s.lower().replace("&", " and ").replace("-", " ")
    s = re.sub(r"[()\[\]'\".,]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def alternatives(name: str) -> list:
    """Namensvarianten aus der Chart-Schreibweise:
    'A / B', 'X (or Y)', 'X (formerly Y)', 'Right (Left) Roll' ..."""
    out = []
    for part in [p.strip() for p in name.split(" / ")]:
        m = re.match(r"^(.*?)\s*\((?:or|formerly)\s+(.+?)\)\s*$", part, re.I)
        if m:
            base, alt = m.group(1), m.group(2)
            out.append(base)
            # 'Circle Left (or Right)' -> 'Circle Right'
            words = base.split()
            if len(alt.split()) == 1 and len(words) > 1:
                out.append(" ".join(words[:-1] + [alt]))
            else:
                out.append(alt)
            continue
        m = re.match(r"^(\w+)\s*\((\w+)\)\s*(.*)$", part)
        if m and not part.startswith("("):      # 'Right (Left) Roll to a Wave'
            out += [f"{m.group(1)} {m.group(3)}", f"{m.group(2)} {m.group(3)}"]
            continue
        out.append(part)
    # 'Star Right / Left' -> zweiter Teil ohne Stamm
    if len(out) == 2 and len(out[1].split()) == 1 and len(out[0].split()) > 1:
        out[1] = " ".join(out[0].split()[:-1] + [out[1]])
    return out


def load_ref():
    ref = json.load(open(REF_PATH, encoding="utf-8"))
    names = {}          # norm(name) -> entity_id
    bands = defaultdict(set)
    for r in ref["call_programs"]:
        e = r["entity_id"]
        n = r.get("canonical_name") or e
        names.setdefault(norm(n), e)
        if r.get("teaching_order") is not None:
            bands[e].add(int(r["teaching_order"]))
    return names, bands


def in_band(eid, prog, bands):
    lo, hi = _PROG_BANDS.get(prog, (0, 999))
    return any(lo <= t < hi for t in bands.get(eid, ())) or not bands.get(eid)


def guess_standard(variants):
    """Index der vorgeschlagenen Standard-Variante."""
    prefs = (r"^$", r"\bfc\b|facing", r"full", r"line of four", r"8 active", r"\bwaves?\b")
    for p in prefs:
        for i, v in enumerate(variants):
            if re.search(p, v.lower()):
                return i
    return 0


def main():
    with open(CSV_PATH, encoding="utf-8-sig", newline="") as f:
        rd = csv.DictReader(f, delimiter=";")
        fields = list(rd.fieldnames)
        rows = list(rd)
    for c in NEW_COLS:
        if c not in fields:
            fields.insert(fields.index("call") + 1 if c == "entity_ids" else len(fields), c)
            for r in rows:
                r[c] = ""

    names, bands = load_ref()
    keys = list(names)
    stats = defaultdict(int)

    groups = defaultdict(list)
    for r in rows:
        groups[(r["programm"], r["call"])].append(r)

    for (prog, call), grp in groups.items():
        if not grp[0]["entity_ids"] and call in OVERRIDES:
            ids_txt, note = OVERRIDES[call]
            unknown = [e for e in re.split(r"[|+]", ids_txt) if e not in bands]
            if unknown:
                note = "; ".join(x for x in (note, "unbekannt: " + ", ".join(unknown)) if x)
            for r in grp:
                r["entity_ids"] = ids_txt
                r["pruefen"] = note
            stats["von_hand"] += 1
        if not grp[0]["entity_ids"]:
            ids, notes = [], []
            for alt in alternatives(call):
                n = norm(alt)
                if n in names:
                    ids.append(names[n])
                    if not in_band(names[n], prog, bands):
                        notes.append(f"'{alt}' nicht im Programm {prog}")
                    continue
                cand = difflib.get_close_matches(n, keys, n=3, cutoff=0.75)
                if cand:
                    ids.append(names[cand[0]])
                    notes.append(f"'{alt}' unscharf: " + ", ".join(names[c] for c in cand))
                else:
                    notes.append(f"'{alt}' kein App-Call gefunden")
            ids = list(dict.fromkeys(ids))
            for r in grp:
                r["entity_ids"] = "|".join(ids)
                if notes:
                    r["pruefen"] = "; ".join(notes)
            stats["unsicher" if notes else "sicher"] += 1
        if not any(r["standard"] for r in grp):
            if len(grp) == 1:
                grp[0]["standard"] = "1"
            else:
                variants = [r["variante"] for r in grp]
                want = STANDARD_OVERRIDES.get(call)
                i = variants.index(want) if want in variants else guess_standard(variants)
                grp[i]["standard"] = "1"
                note = "Standard-Variante vorgeschlagen, bitte bestaetigen"
                for r in grp:
                    r["pruefen"] = "; ".join(x for x in (r["pruefen"], note) if x)
                stats["standard_vorschlag"] += 1

    with open(CSV_PATH, "w", encoding="utf-8-sig", newline="") as f:
        wr = csv.DictWriter(f, fieldnames=fields, delimiter=";", lineterminator="\n")
        wr.writeheader()
        wr.writerows(rows)
    print(dict(stats), "Calls;", sum(1 for r in rows if r["pruefen"]), "Zeilen mit 'pruefen'")


if __name__ == "__main__":
    main()
