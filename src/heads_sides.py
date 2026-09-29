"""Heads/Sides invertieren fuer Dynamic Lyrics (intern#127).

Reine Logik, ohne Qt: tauscht in einer Sequenz Heads und Sides (samt
Couple-Nummern), damit ein Singing Call in ausgewaehlten Figure Parts von der
anderen Seite getanzt wird. Die Regeln stammen aus der Analyse aller Lyrics und
Sequenzen (siehe intern#127):

1. Immer tauschen, gleichzeitig und mit Erhalt der Schreibweise:
   Heads<->Sides, Head<->Side, HDS<->SDS, HD<->SD (HD/SD nicht vor einer Zahl,
   sonst trifft es Label-Codes wie 'SD-205').
2. Nie tauschen: 'each side', 'Cross Head Tie' (Call-Name), Wortteile
   ('left-side'), Apostroph-s.
3. Couple-Nummern: 1->2->3->4->1. 'first couple', '1st couple' usw. nicht.
4. Einzelbuchstaben nur in Klammern: '(H)'<->'(S)'.
5. Asymmetrische Choreo bleibt komplett unveraendert: Nennt eine Sequenz
   benachbarte Paare in EINER Nennung ('Couples 1 & 2', 'Couple #4 and #1')
   oder 'Your Couple Number', wird darin nichts getauscht.
"""

from __future__ import annotations

import re

# Figure Parts werden fortlaufend gezaehlt (1 Opener, 2 Figure 1, 3 Figure 2,
# 4 Break, 5 Figure 3, 6 Figure 4, 7 Closer). Hier direkt als Figur-Nummer:
# HHSS tauscht in Figure 3+4, HSSH in Figure 2+3, HSHS in Figure 2+4.
INVERT_MODES = {
    "HHSS": frozenset({3, 4}),
    "HSSH": frozenset({2, 3}),
    "HSHS": frozenset({2, 4}),
}


def inverted_figures(mode: str) -> frozenset:
    """Figur-Nummern (1..4), in denen bei dieser Art getauscht wird. Unbekannte
    oder leere Art: keine."""
    return INVERT_MODES.get((mode or "").upper(), frozenset())


# ---------------------------------------------------------------------------
# Regel 1/2: Woerter
# ---------------------------------------------------------------------------

_WORD_SWAP = {
    "heads": "sides", "sides": "heads",
    "head": "side", "side": "head",
    "hds": "sds", "sds": "hds",
    "hd": "sd", "sd": "hd",
}

# Kein Wortteil: davor kein Buchstabe/Ziffer/Bindestrich/Apostroph, danach
# weder Buchstabe/Ziffer/Bindestrich noch Apostroph-s.
_WORD_RE = re.compile(
    r"(?<![\w'’-])(heads|sides|head|side|hds|sds|hd|sd)"
    r"(?![\w-])(?!['’]s\b)",
    re.IGNORECASE)
_EACH_BEFORE = re.compile(r"\beach\s+$", re.IGNORECASE)
_CROSS_BEFORE = re.compile(r"\bcross\s+$", re.IGNORECASE)
_TIE_AFTER = re.compile(r"\s+tie\b", re.IGNORECASE)
_DIGIT_AFTER = re.compile(r"[\s-]*\d")

# Regel 4: Einzelbuchstabe nur in Klammern
_PAREN_RE = re.compile(r"\(([HhSs])\)")
_PAREN_SWAP = {"H": "S", "S": "H", "h": "s", "s": "h"}


def _match_case(src: str, repl: str) -> str:
    if src.isupper():
        return repl.upper()
    if src[:1].isupper():
        return repl[:1].upper() + repl[1:]
    return repl


def _word_edits(line: str) -> list:
    """(start, end, ersatz) fuer alle zu tauschenden Woerter einer Zeile."""
    edits = []
    for m in _WORD_RE.finditer(line):
        word = m.group(1)
        low = word.lower()
        before, after = line[:m.start()], line[m.end():]
        if low in ("side", "sides") and _EACH_BEFORE.search(before):
            continue
        if low == "head" and _CROSS_BEFORE.search(before) \
                and _TIE_AFTER.match(after):
            continue
        if low in ("hd", "sd") and _DIGIT_AFTER.match(after):
            continue
        edits.append((m.start(), m.end(), _match_case(word, _WORD_SWAP[low])))
    for m in _PAREN_RE.finditer(line):
        edits.append((m.start(1), m.end(1), _PAREN_SWAP[m.group(1)]))
    return edits


# ---------------------------------------------------------------------------
# Regel 3/5: Couple-Nummern
# ---------------------------------------------------------------------------

_NUM = r"(?:#[ \t]*)?[1-4]"
# Nach 'Couple(s)' [Number]: Liste mit , & + and
_COUPLE_RE = re.compile(
    r"\bcouples?[ \t]*(?:number[ \t]*)?"
    rf"({_NUM}(?:[ \t]*(?:,|&|\+|and)[ \t]*{_NUM})*)(?![\d/])",
    re.IGNORECASE)
# Ohne 'Couple': Paar mit & + and ('1 & 3', '#1 & #4', '2+4'), nicht in
# Bruechen ('1 & 1/2') oder Ordinalzahlen ('1st'). Ebenfalls nicht die
# Formation '3 & 1 Lines' bzw. '(from 3&1)' - das sind keine Couple-Nummern.
_PAIR_RE = re.compile(
    rf"(?<![\w/#.])(?<!from )({_NUM}[ \t]*(?:&|\+|and)[ \t]*{_NUM})"
    r"(?![\w/])(?![ \t]*lines?\b)",
    re.IGNORECASE)
# Einzelnes '#1'
_HASH_RE = re.compile(r"(?<![\w#])(#[ \t]*[1-4])(?![\d/])")
_DIGIT_RE = re.compile(r"[1-4]")
_YOUR_COUPLE_NUMBER = re.compile(r"\byour\s+couple\s+number\b", re.IGNORECASE)


def _couple_mentions(line: str) -> list:
    """(start, end) der Zahlen-Bereiche je Nennung, ohne Ueberlappung."""
    spans = []
    for rx in (_COUPLE_RE, _PAIR_RE, _HASH_RE):
        for m in rx.finditer(line):
            s, e = m.span(1)
            if not any(s < pe and ps < e for ps, pe in spans):
                spans.append((s, e))
    return spans


def _is_adjacent(numbers: list) -> bool:
    """True, wenn zwei der Nummern Nachbarn sind (Abstand 1, zyklisch 4->1)."""
    nums = set(numbers)
    return any(((n % 4) + 1) in nums for n in nums)


def is_asymmetric(calls: list) -> bool:
    """Regel 5: Sequenz nennt benachbarte Paare in einer Nennung oder
    'Your Couple Number' -> gar nicht tauschen."""
    for line in calls:
        if _YOUR_COUPLE_NUMBER.search(line):
            return True
        for s, e in _couple_mentions(line):
            nums = [int(d) for d in _DIGIT_RE.findall(line[s:e])]
            if _is_adjacent(nums):
                return True
    return False


def _couple_edits(line: str) -> list:
    edits = []
    for s, e in _couple_mentions(line):
        for m in _DIGIT_RE.finditer(line, s, e):
            edits.append((m.start(), m.end(), str(int(m.group()) % 4 + 1)))
    return edits


# ---------------------------------------------------------------------------
# Oeffentliche API
# ---------------------------------------------------------------------------

def invert_line(line: str) -> str:
    """Tauscht Heads/Sides und Couple-Nummern in EINER Zeile, gleichzeitig
    (kein Doppeltausch). Die Asymmetrie-Pruefung macht invert_sequence()."""
    edits = sorted(_word_edits(line) + _couple_edits(line))
    out, pos = [], 0
    for s, e, repl in edits:
        if s < pos:
            continue   # Ueberlappung (sollte nicht vorkommen): erster gewinnt
        out.append(line[pos:s])
        out.append(repl)
        pos = e
    out.append(line[pos:])
    return "".join(out)


def invert_sequence(calls: list) -> list:
    """Invertiert eine Sequenz (Liste von Call-Zeilen). Asymmetrische Choreo
    (Regel 5) kommt unveraendert zurueck."""
    if is_asymmetric(calls):
        return list(calls)
    return [invert_line(c) for c in calls]
