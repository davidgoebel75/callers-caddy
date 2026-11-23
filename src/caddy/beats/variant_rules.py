"""Variantenregeln der Beat-Tabelle (intern#164): welche Zeile einer Chart gilt fuer einen Kartentext.

Die Spalte `variante_regel` der Tabelle enthaelt feste englische Kuerzel, mit Komma getrennt.
Freie Suchmuster gibt es bewusst nicht: Die Pflegedatei soll sich nicht kaputtschreiben lassen,
`parse()` weist alles Unbekannte ab.

Auswahl-Kuerzel (entscheiden, ob eine Zeile zum Text passt):
- `number=N`      die Zahl im Text ist N (Square Thru 4; "1/2 Square Thru" = 2, "3/4" = 3).
                  Ohne Zahl passt die Zeile nicht.
- `odd` / `even`  die Zahl im Text ist ungerade / gerade
- `fraction=X`    Bruchteil im Text: `1/4`, `1/2`, `3/4`, `full` (auch "half", "quarter",
                  "three quarter", "all the way"). Ohne Bruchteil passt die Zeile nicht,
                  auch `full` nicht ("Shoot the Star" ist nicht "Shoot the Star Full Around").
- `ss`            aus dem Squared Set: der Text beginnt mit Heads/Sides
- `home`          der Text enthaelt "home" (Promenade Home)
- `named`         nur genannte Taenzer tanzen: der Text beginnt mit einer Gruppe
                  (Ends, Centers, Outsides, Heads, Boys ...), z. B. "Ends Cloverleaf" = 4 active
- `parts`         Summe ueber N Teile; ungerade und gerade Teile stehen in je einer Zeile.
                  Passt nur, wenn der Text eine Zahl enthaelt (Eight Chain 4, nicht
                  Eight Chain Thru). Die Summe bildet die Beat-Rechnung.

Rechen-Kuerzel (aendern den Wert, waehlen nichts aus; ausgewertet in der Beat-Rechnung):
- `minus_pass_thru`   Chart-Wert enthaelt ein vorangehendes Pass Thru; steht es nicht in
                      derselben Kartenzeile, 2 Beats abziehen

Ausgewaehlt wird unter ALLEN Zeilen eines App-Calls in einer Chart, auch wenn sie in der Chart
unter verschiedenen Namen stehen (Separate Around 1 / 2, Eight Chain Thru / Eight Chain N).
Passt keine Zeile, gilt die Standard-Variante (Spalte `standard`, genau eine je App-Call und Chart).
"""
import re

QT_FREE = True

SELECT_KEYS = ("number", "odd", "even", "fraction", "ss", "home", "parts", "named")
CALC_KEYS = ("minus_pass_thru",)
_WITH_VALUE = {"number", "fraction"}
FRACTIONS = ("1/4", "1/2", "3/4", "full")

_FRACTION_WORDS = (
    (r"\bthree[ -]quarters?\b", "3/4"),
    (r"\b3/4\b", "3/4"),
    (r"\b1/2\b|\bhalf(?:way)?\b", "1/2"),
    (r"\b1/4\b|\bquarter\b", "1/4"),
    (r"\bfull\b|\ball the way\b|\bfull around\b", "full"),
)
_NAMED_RE = re.compile(
    r"^\s*(?:\([^)]*\)\s*)?(?:the\s+)?(?:heads?|sides?|ends|centers|outsides|insides|boys|girls|"
    r"men|ladies|leaders|trailers|beaus|belles|very centers|new centers|new ends|"
    r"center (?:four|4|boys|girls)|end (?:boys|girls))\b", re.I)
_SS_RE = re.compile(r"^\s*(?:\([^)]*\)\s*)?(?:the\s+)?(?:heads?|sides?)\b", re.I)


class RuleError(ValueError):
    """Unbekanntes oder falsch geschriebenes Kuerzel in `variante_regel`."""


def parse(text):
    """'number=4, ss' -> {'number': '4', 'ss': True}. Leer -> {}. Wirft RuleError."""
    out = {}
    for part in (p.strip() for p in (text or "").split(",")):
        if not part:
            continue
        key, _, val = part.partition("=")
        key, val = key.strip(), val.strip()
        if key not in SELECT_KEYS + CALC_KEYS:
            raise RuleError(f"unbekanntes Kuerzel: {key!r}")
        if key in _WITH_VALUE:
            if not val:
                raise RuleError(f"{key} braucht einen Wert, z. B. {key}=…")
            if key == "number" and not val.isdigit():
                raise RuleError(f"number={val!r}: keine ganze Zahl")
            if key == "fraction" and val not in FRACTIONS:
                raise RuleError(f"fraction={val!r}: erlaubt sind {', '.join(FRACTIONS)}")
        elif val:
            raise RuleError(f"{key} hat keinen Wert")
        if key in out:
            raise RuleError(f"{key} doppelt")
        out[key] = val or True
    if "odd" in out and "even" in out:
        raise RuleError("odd und even schliessen sich aus")
    return out


def text_fraction(text):
    """Bruchteil im Kartentext ('1/4', '1/2', '3/4', 'full') oder None ohne Angabe."""
    t = text.lower()
    for pat, val in _FRACTION_WORDS:
        if re.search(pat, t):
            return val
    return None


def text_number(text):
    """Letzte ganze Zahl im Text, die nicht Teil eines Bruchs ist. Die letzte, weil
    Gruppen vorne Zahlen tragen koennen ("Center 4 Square Thru 2")."""
    nums = re.findall(r"(?<![\d/])(\d+)(?![\d/])", text)
    return int(nums[-1]) if nums else None


_FRACTION_HANDS = {"1/4": 1, "1/2": 2, "3/4": 3}


def text_count(text):
    """Zahl fuer `number`/`odd`/`even`/`parts`: ganze Zahl im Text, sonst ein vorangestellter
    Bruchteil als Haende ("1/2 Square Thru" = Square Thru 2, "3/4" = 3)."""
    n = text_number(text)
    if n is None:
        n = _FRACTION_HANDS.get(text_fraction(text) or "")
    return n


def from_squared_set(text):
    return bool(_SS_RE.match(text))


def matches(rule, text, squared_set=None):
    """Passt eine geparste Regel (nur Auswahl-Kuerzel) zum Kartentext?
    Eine Regel ohne Auswahl-Kuerzel passt nie (die Zeile gilt nur als Standard).

    squared_set: steht der Square vor dieser Zeile im Squared Set (erste Zeile der Sequenz)?
    None = unbekannt, dann entscheidet allein der Text. Mitten in der Sequenz ist
    "Heads Pass Thru" kein Start aus dem Squared Set."""
    sel = {k: v for k, v in rule.items() if k in SELECT_KEYS}
    if not sel:
        return False
    n = text_count(text)
    for key, val in sel.items():
        if key == "number" and n != int(val):
            return False
        if key == "odd" and (n is None or n % 2 == 0):
            return False
        if key == "even" and (n is None or n % 2 == 1):
            return False
        if key == "fraction" and text_fraction(text) != val:
            return False
        if key == "ss" and (squared_set is False or not from_squared_set(text)):
            return False
        if key == "home" and not re.search(r"\bhome\b", text, re.I):
            return False
        if key == "parts" and n is None:
            return False
        if key == "named" and not _NAMED_RE.match(text):
            return False
    return True


def choose(rows, text, squared_set=None):
    """Zeile fuer den Text aus den Zeilen EINES App-Calls einer Chart.

    rows: Folge von Dicts mit 'variante_regel' (Text) und 'standard' ('1' oder leer).
    Gewinnt die passende Zeile mit den meisten Auswahl-Kuerzeln (spezifischste Regel),
    sonst die Standard-Zeile, sonst die erste. Rueckgabe (row, 'regel'|'standard')."""
    best, best_n = None, 0
    for r in rows:
        rule = parse(r.get("variante_regel", ""))
        n_sel = sum(1 for k in rule if k in SELECT_KEYS)
        if n_sel > best_n and matches(rule, text, squared_set):
            best, best_n = r, n_sel
    if best is not None:
        return best, "regel"
    std = next((r for r in rows if str(r.get("standard", "")) == "1"), rows[0])
    return std, "standard"
