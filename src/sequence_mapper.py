"""
Sequence Mapper: Teaching-Order-Hilfsfunktionen
=================================================
Liest Teaching-Order-Daten aus der SQLite-Datenbank
(Tabellen: teaching_order_calls, call_text_mappings).

Das eigentliche Mapping (Call-Texte → Entity-IDs) wird extern
durch tools/map_sequence_calls.py erledigt und in der DB gespeichert.
Dieses Modul stellt nur Abfrage-Funktionen bereit fuer die UI.

Kein Qt — reines Python-Modul.
"""

import re
from difflib import SequenceMatcher
from typing import Optional

# ---------------------------------------------------------------------------
# Call-Text-Normalisierung und Matching
# ---------------------------------------------------------------------------

_ROLE_PREFIX_RE = re.compile(
    r'^(original\s+)?(heads?|hds?|sides?|sds?|centers?|boys?|girls?|men|ladies|'
    r'all\s+8|all\s+eight|all|ends?|leaders?|trailers?)\s+',
    re.IGNORECASE
)
_SUFFIX_RE = re.compile(
    r'(\s*\([^)]*\)|\s+\d+/\d+|\s+\d+|\s+again)\s*$',
    re.IGNORECASE
)


def normalize_call_text(text: str) -> str:
    """Normalisiert einen Call-Text fuer Matching-Zwecke.

    Entfernt fuehrende Rollen-Prefixe (Heads, Sides, Centers, Boys, Girls ...)
    und abschliessende Zahlen, Brueche und Klammern. Bis zu 3 Prefixe werden
    sukzessive entfernt.

    Beispiele:
        'Heads Square Thru 3'  -> 'square thru'
        'Centers Pass Thru'    -> 'pass thru'
        'Swing Thru (again)'   -> 'swing thru'
        'All 8 Circulate'      -> 'circulate'
    """
    t = text.strip()
    for _ in range(3):
        new = _ROLE_PREFIX_RE.sub('', t)
        if new == t:
            break
        t = new
    t = _SUFFIX_RE.sub('', t)
    return t.strip().lower()


class CallMatcher:
    """Drei-Stufen-Matcher fuer Call-Text → Canonical-Name-Zuordnung.

    Wird einmalig mit der Liste aller Teaching-Order-Calls initialisiert
    (normalisiert sie dabei vor). Pro unmapped Text liefert suggest() einen
    Score und eine entity_id.

    Stufen:
        1. Exakter Vergleich nach Normalisierung          → score 1.0
        2. Bidirektionaler Token-Overlap (Jaccard-aehnl.) → score bis 0.92
        3. difflib.SequenceMatcher als Fallback            → score bis 0.85

    Kein Netzwerk, keine API, laeuft in Millisekunden fuer 1000×200 Paare.

    Args:
        canonicals: [(entity_id, canonical_name, teaching_order, program), ...]
    """

    # Konfidenz-Schwellen
    CONFIDENT  = 0.85   # gruene Markierung — sicher
    UNCERTAIN  = 0.50   # gelbe Markierung — menschliche Pruefung empfohlen
    # < UNCERTAIN → keine Vorauswahl, rote Markierung

    def __init__(self, canonicals: list):
        self._exact: dict[str, str] = {}          # norm_text → entity_id
        self._data:  list[tuple]    = []           # [(eid, norm_can, frozenset_tokens)]
        # Invertierter Index Wort → [Indizes in self._data]. Damit muss suggest()
        # einen Text nur noch gegen Calls pruefen, die MINDESTENS EIN Wort teilen —
        # Calls ohne gemeinsames Wort haben ohnehin Token-Score 0 und koennen nie
        # gewinnen. Aus ~10k×776 Vergleichen werden so wenige pro Text.
        self._token_index: dict[str, list] = {}

        for eid, cname, *_ in canonicals:
            norm = normalize_call_text(cname)
            if not norm:
                continue
            if norm not in self._exact:
                self._exact[norm] = eid
                idx = len(self._data)
                toks = frozenset(norm.split())
                self._data.append((eid, norm, toks))
                for t in toks:
                    self._token_index.setdefault(t, []).append(idx)

    def suggest(self, raw_text: str) -> tuple:
        """Gibt (score, entity_id) fuer den besten Treffer zurueck.

        score == 0.0 und entity_id == None bedeutet: kein ausreichender Treffer.
        """
        norm_raw = normalize_call_text(raw_text)
        if not norm_raw:
            return (0.0, None)

        # Stufe 1: exakter Vergleich
        if norm_raw in self._exact:
            return (1.0, self._exact[norm_raw])

        raw_tokens = frozenset(norm_raw.split())
        best_score = 0.0
        best_eid   = None

        # Kandidaten: nur Calls, die mindestens ein Wort mit dem Text teilen
        # (ueber den invertierten Index). Alle uebrigen haetten Overlap 0 und
        # damit Token-Score 0 — sie koennen den besten Treffer nie stellen, also
        # gar nicht erst anfassen. Ergebnis ist identisch zur vollen Schleife.
        candidates = set()
        for t in raw_tokens:
            candidates.update(self._token_index.get(t, ()))

        # WICHTIG: in Index-Reihenfolge (= Teaching-Order) durchgehen. Bei
        # Score-Gleichstand gewinnt so — wie in der frueheren vollen Schleife —
        # der Call mit der niedrigsten Teaching-Order. Ueber ein set() iteriert
        # waere die Wahl nichtdeterministisch (andere Zuordnung bei Gleichstand).
        for idx in sorted(candidates):
            eid, norm_can, can_tokens = self._data[idx]

            # Stufe 2: bidirektionaler Token-Overlap (Overlap >= 1 garantiert)
            overlap = len(raw_tokens & can_tokens)
            precision  = overlap / len(can_tokens)   # Canonical vollstaendig erklaert?
            recall     = overlap / len(raw_tokens)   # Raw vollstaendig erklaert?
            token_score = (precision * recall) ** 0.5 * 0.92

            # Stufe 3: SequenceMatcher (nur wenn Token-Score vielversprechend)
            if token_score >= 0.30:
                fuzzy_score = SequenceMatcher(
                    None, norm_raw, norm_can, autojunk=False
                ).ratio() * 0.85
            else:
                fuzzy_score = 0.0

            score = max(token_score, fuzzy_score)
            if score > best_score:
                best_score = score
                best_eid   = eid

        if best_score < self.UNCERTAIN:
            return (0.0, None)
        return (best_score, best_eid)

    def exact_entity(self, raw_text: str) -> Optional[str]:
        """Nur Stufe 1: entity_id bei EXAKTEM Treffer (Score 1.0) nach
        Normalisierung, sonst None.

        Fuer Massen-Auto-Mapping (Startup-Backfill, Bulk-Import, Remapping) —
        ohne den teuren Fuzzy-Loop, damit Tausende Texte in Millisekunden
        laufen. Entspricht suggest()>=0.999, aber als O(1)-Dict-Lookup.
        """
        norm = normalize_call_text(raw_text)
        if not norm:
            return None
        return self._exact.get(norm)


# Programm-Grenzen: (program_id, label)
_PROGRAMS = [
    (10, "Basic 1"),
    (20, "Basic 2"),
    (30, "Mainstream"),
    (40, "Plus"),
    (50, "A1"),
    (60, "A2"),
    (70, "C1"),
    (80, "C2"),
    (90, "C3a"),
    (100, "C3b"),
]


def get_program_label(teaching_order: Optional[float]) -> str:
    """Gibt das Programm-Label fuer eine Teaching Order zurueck.

    Beispiel: 10.000100 → "Basic 1", 30.001500 → "Mainstream"
    """
    if teaching_order is None:
        return "?"

    program_id = int(teaching_order)
    for pid, label in _PROGRAMS:
        if pid == program_id:
            return label
    return "?"


def get_all_calls_sorted(db) -> list[tuple]:
    """Alle Calls aus der DB sortiert nach Teaching Order.

    Returns:
        [(canonical_name, entity_id, teaching_order), ...]
    """
    rows = db.get_teaching_order_calls()
    return [(name, eid, to) for eid, name, to, _prog in rows]


