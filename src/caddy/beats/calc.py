"""Beat-Rechnung nach den CALLERLAB-Timing-Charts (intern#164).

Rechnet je Kartenzeile und je Sequenz einen Bereich (von-bis) aus den Zeilen der Beat-Tabelle.
Die Tabelle ist die Quelle der Wahrheit; Taminations-Beats ersetzen nur dynamische Werte
(Promenade Home, Swing and Promenade ...), wenn Square Flow sie liefert.

Ablauf je Kartenzeile (App-Calls aus dem Mapping: Haupt-Call + weitere Figuren):
1. Kombinationen zuerst: eine Tabellenzeile `a+b` (z. B. All 4 Couples Pass Thru) gilt, wenn
   alle Teile in der Zeile stehen; die Teile zaehlen dann nicht mehr einzeln.
2. Je uebriger App-Call die Chart-Zeile waehlen (`variant_rules.choose`).
3. Basis = Summe der Calls mit Wert (fest, bereich, dynamisch; `parts` = Summe der Teile).
4. Zuschlaege um die Basis, innen nach aussen:
   `call_plus` (Call + n: and Cross, & Roll, & Spread), dann `plus_call` (n + Call: Explode and),
   `max` (groesser von n und Call: Clover and) und `anything_ab` (Transfer and: n, der Call
   beginnt auf Beat k, also max(n, k-1 + Call)).
5. `not_timed` (Any Hand, As Couples) traegt nichts bei, kennzeichnet die Zeile.
6. Wiederholung im Text: "Twice" / nachgestelltes "Double" x2, "1 & 1/2" x1,5, "3 Times" x3.
   Ein vorangestelltes "Double" ist Teil des Namens (Double Pass Thru) und zaehlt nicht.

Kein pauschaler Zuschlag fuer den Start aus dem Squared Set: Die Chart nennt ihn je Call
(SS-Zeilen, `ss` in variante_regel), z. B. Square Thru nur bei ungerader Zahl.
"""
import re
from dataclasses import dataclass, field

from caddy.beats import variant_rules as vr

QT_FREE = True

CHART_ORDER = ("MS", "Plus", "A1", "A2")
VALUE_TYPES = ("fest", "bereich", "dynamisch")
PASS_THRU = "call_pass_thru"

# Kennzeichen einer Zeile/Sequenz
NOT_TIMED = "not_timed"      # Konzept ohne Timing beteiligt
UNKNOWN = "unknown"          # App-Call ohne Tabellenzeile oder Zeile ohne App-Call
DYNAMIC = "dynamic"          # Wert haengt vom Weg ab (Nennwert/Bereich, ohne Engine)
TAMINATIONS = "taminations"  # dynamischer Wert aus Taminations uebernommen

GREEN, YELLOW, RED = "green", "yellow", "red"


@dataclass(frozen=True)
class Beats:
    lo: float = 0.0
    hi: float = 0.0
    flags: frozenset = field(default_factory=frozenset)


class BeatTable:
    """Tabellenzeilen (Dicts mit den Spalten der Pflegedatei), indiziert nach App-Call."""

    def __init__(self, rows):
        self.single = {}     # entity -> {chart: [rows]}
        self.combos = []     # (frozenset(entities), chart, row)
        for r in rows:
            ids = r.get("entity_ids") or ""
            for alt in (x for x in ids.split("|") if x):
                if "+" in alt:
                    self.combos.append((frozenset(alt.split("+")), r["programm"], r))
                else:
                    self.single.setdefault(alt, {}).setdefault(r["programm"], []).append(r)

    def rows_for(self, entity, chart=None):
        charts = self.single.get(entity)
        if not charts:
            return []
        if chart in charts:
            return charts[chart]
        for c in CHART_ORDER:
            if c in charts:
                return charts[c]
        return next(iter(charts.values()))


def _value(r):
    lo = float(r["beats"]) if r.get("beats") not in (None, "") else 0.0
    hi = float(r["beats_bis"]) if r.get("beats_bis") not in (None, "") else lo
    return lo, hi


_REPEAT = (
    (re.compile(r"\b(?:1|one)\s*(?:&|and)?\s*(?:1/2|a half)\b", re.I), 1.5),
    (re.compile(r"\b(?:3|three)\s+times\b", re.I), 3.0),
    (re.compile(r"\btwice\b|\bdouble\s*(?:$|,)", re.I), 2.0),
)


def repeat_factor(text):
    """Wiederholungsfaktor aus dem Kartentext (1 ohne Angabe)."""
    for pat, f in _REPEAT:
        if pat.search(text):
            return f
    return 1.0


def _parts_value(rows, text):
    """Eight Chain N: ungerade Teile aus der 'odd'-Zeile, gerade aus der 'even'-Zeile."""
    n = vr.text_count(text) or 0
    part = {}
    for r in rows:
        if "parts" in vr.parse(r.get("variante_regel", "")):
            v = (r.get("variante") or "").lower()
            part["even" if "even" in v else "odd"] = _value(r)
    odd, even = part.get("odd", (0, 0)), part.get("even", part.get("odd", (0, 0)))
    n_odd, n_even = (n + 1) // 2, n // 2
    return (n_odd * odd[0] + n_even * even[0], n_odd * odd[1] + n_even * even[1])


def line_beats(table, entities, text, squared_set=None, chart=None, tam_beats=None):
    """Beats einer Kartenzeile. entities: App-Calls der Zeile (Iterable)."""
    ents = [e for e in dict.fromkeys(entities or ()) if e]
    if not ents:
        return Beats(flags=frozenset({UNKNOWN}))
    flags = set()
    lo = hi = 0.0
    wrappers = []   # (typ, row)

    # 1. Kombinationen
    present = set(ents)
    for parts, c, r in sorted(table.combos, key=lambda x: (x[1] != chart, -len(x[0]))):
        if parts <= present:
            a, b = _value(r)
            lo, hi = lo + a, hi + b
            if r["typ"] == "dynamisch":
                flags.add(DYNAMIC)
            present -= parts
            ents = [e for e in ents if e not in parts]

    # 2./3. Einzelne Calls
    for e in ents:
        rows = table.rows_for(e, chart)
        if not rows:
            flags.add(UNKNOWN)
            continue
        row, _how = vr.choose(rows, text, squared_set)
        typ = row["typ"]
        rule = vr.parse(row.get("variante_regel", ""))
        if typ in ("call_plus", "plus_call") and not e.startswith("concept_") \
                and len(rows) > 1:
            # Zuschlag auf denselben Call (Square Thru: SS odd numbers: add 2 to previous count)
            rest = [r for r in rows if r is not row]
            base, _ = vr.choose(rest, text, squared_set)
            a, b = _value(base)
            n = float(row["beats"])
            lo, hi = lo + a + n, hi + b + n
            continue
        if typ in VALUE_TYPES:
            a, b = _parts_value(rows, text) if "parts" in rule else _value(row)
            if row.get("anything_ab"):
                wrappers.append(("anything_ab", row))
                continue
            if "minus_pass_thru" in rule and PASS_THRU not in present \
                    and "pass thru" not in text.lower():
                a, b = max(a - 2, 0), max(b - 2, 0)
            lo, hi = lo + a, hi + b
            if typ == "dynamisch":
                flags.add(DYNAMIC)
        elif typ == "not_timed":
            flags.add(NOT_TIMED)
        elif typ in ("call_plus", "plus_call", "max"):
            wrappers.append((typ, row))
        else:
            flags.add(UNKNOWN)

    # 4. Zuschlaege: zuerst Call + n (bindet direkt), dann die umschliessenden
    for typ, row in sorted(wrappers, key=lambda w: w[0] != "call_plus"):
        n = float(row["beats"])
        if typ in ("call_plus", "plus_call"):
            lo, hi = lo + n, hi + n
        elif typ == "max":
            lo, hi = max(n, lo), max(n, hi)
        elif typ == "anything_ab":
            k = float(row["anything_ab"]) - 1
            lo, hi = max(n, k + lo), max(n, k + hi)

    f = repeat_factor(text)
    if f != 1.0:
        lo, hi = lo * f, hi * f

    if DYNAMIC in flags and tam_beats is not None:
        lo = hi = float(tam_beats)
        flags.discard(DYNAMIC)
        flags.add(TAMINATIONS)
    return Beats(lo, hi, frozenset(flags))


def sequence_beats(lines):
    """Summe ueber die Zeilen (Iterable von Beats)."""
    lo = hi = 0.0
    flags = set()
    for b in lines:
        lo, hi = lo + b.lo, hi + b.hi
        flags |= b.flags
    return Beats(lo, hi, frozenset(flags))


def traffic_light(total):
    """Ampel fuer eine 64-Beat-Figur nach dem Hoechstwert (Entscheidung David 2026-11-23):
    gruen bis 64, gelb 65-68, rot darueber."""
    if total.hi <= 64:
        return GREEN
    if total.hi <= 68:
        return YELLOW
    return RED


def deviation(beats, tam_beats):
    """Abstand eines Taminations-Werts zum Tabellenbereich (0 = im Bereich)."""
    if tam_beats is None or TAMINATIONS in beats.flags:
        return 0.0
    t = float(tam_beats)
    return 0.0 if beats.lo <= t <= beats.hi else (t - beats.hi if t > beats.hi else t - beats.lo)


def warn_deviation(beats, tam_beats, limit=2.0):
    """Hinweis im Sequenz-Detail ab 2 Beats Abweichung (Entscheidung David 2026-11-23)."""
    return abs(deviation(beats, tam_beats)) >= limit


def fmt(beats):
    """Anzeige: '10', '7-8', '>= 58 + ?' (Not Timed / unbekannt)."""
    lo, hi = f"{beats.lo:g}", f"{beats.hi:g}"
    s = lo if lo == hi else f"{lo}–{hi}"
    if beats.flags & {NOT_TIMED, UNKNOWN}:
        s = f"≥ {lo} + ?"
    return s
