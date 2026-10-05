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
from functools import lru_cache
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

# Wie _ROLE_PREFIX_RE, aber OHNE 'all 8'/'all eight' -- fuer die
# Volltreffer-Pruefung in suggest_figure_set() (BL-210.7). Dort muss ein
# gewoehnlicher Rollen-Praefix ('Heads Right & Left Thru' -> 'Right & Left
# Thru') weiterhin fallen, aber 'All 8'/'All Eight' duerfen NICHT als blosses
# 'All' + Rest verstuemmelt werden -- sonst ist 'All Eight Circulate' vom
# blanken 'Circulate' nicht mehr unterscheidbar. Wird darum nur auf Texte
# angewendet, die (noch) nicht auf den All-8/All-4-Couples-Praefix passen.
_GENERIC_ROLE_PREFIX_RE = re.compile(
    r'^(original\s+)?(heads?|hds?|sides?|sds?|centers?|boys?|girls?|men|ladies|'
    r'all|ends?|leaders?|trailers?)\s+',
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
        # canon_key(roher kanonischer Name) → (entity_id, teaching_order).
        # Fuer exact_by_canonical() -- getrennt von self._exact, das ueber
        # normalize_call_text laeuft und darum "All 8 Circulate" und
        # "Swing Thru" ununterscheidbar machen wuerde (BL-210.7). canon_key
        # (nicht blosses .lower()) ist Pflicht: exact_lookup/rest_lookup fuer
        # suggest_figure_set() sind ebenfalls canon_key-Schluessel, sonst
        # findet z. B. "(Anything) & Roll" seinen Eintrag nicht, wenn er
        # ueber diese Methode gebaut wurde ('&' vs. 'and'). Bei mehrfach
        # vorkommenden Namen gewinnt deterministisch die niedrigste
        # teaching_order, sonst wandert die entity_id der (Anything)-Figur
        # zwischen Laeufen.
        self._by_canonical: dict[str, tuple] = {}

        for eid, cname, *rest in canonicals:
            teaching_order = rest[0] if rest else None
            key = canon_key(cname)
            if key:
                prev = self._by_canonical.get(key)
                if prev is None or (
                        teaching_order is not None and
                        (prev[1] is None or teaching_order < prev[1])):
                    self._by_canonical[key] = (eid, teaching_order)

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

    def exact_by_canonical(self, name: str) -> Optional[str]:
        """entity_id fuer einen ROHEN kanonischen Namen (canon_key-Vergleich:
        case-insensitiv, '&' == 'and', Zahlwoerter == Ziffern), ohne die
        Normalisierung von normalize_call_text (kein Abschneiden von
        'All 8'/Rollen-Praefixen o.ae.) -- sonst None.

        Fuer die Aufloesung der (Anything)-Figuren (BL-210.7): der Aufrufer
        kennt den exakten kanonischen Namen (z. B. eine (Anything)-Figur oder
        ein Konzept) und will dessen entity_id -- egal ob er ihn mit '&' oder
        'and' schreibt. Existiert der Name mehrfach (z. B.
        'Explode & (Anything)' einmal je Programm), liefert diese Methode
        stabil die Variante mit der niedrigsten teaching_order.
        """
        if not name or not name.strip():
            return None
        entry = self._by_canonical.get(canon_key(name))
        return entry[0] if entry else None


# ---------------------------------------------------------------------------
# Figuren-Mengen-Vorschlag (BL-210.7)
# ---------------------------------------------------------------------------
# ``exact_lookup`` ist ein Dict canon_key(kanonischer Name) -> entity_id, das
# ALLE bekannten Figuren/Konzepte enthaelt (auch die 7 (Anything)-Figuren und
# die beiden All-8/All-4-Couples-Konzepte). ``rest_lookup`` (optional) ist
# zusaetzlich ein Dict canon_key(bereits gemappter Call-Text) -> entity_id,
# z. B. aus den bestehenden ``call_text_mappings`` -- fuer Restaufloesungen,
# bei denen der rohe kanonische Name allein nicht reicht (siehe
# suggest_figure_set()). Der Aufrufer baut BEIDE Dicts ueber ``canon_key()``
# (oder ueber CallMatcher.exact_by_canonical(), das denselben Schluessel
# benutzt) -- suggest_figure_set() und Helfer lesen hier nur.

_DIGIT_WORD_RE = (
    (re.compile(r'\beight\b'), '8'),
    (re.compile(r'\bfour\b'), '4'),
)


@lru_cache(maxsize=4096)
def canon_key(text: str) -> str:
    """Vereinheitlicht einen Text fuer den Volltreffer-Vergleich gegen rohe
    kanonische Namen: Kleinschreibung, '&' -> 'and', Zahlwoerter -> Ziffern,
    Mehrfach-Leerzeichen zusammengezogen.

    Bewusst KEINE Rollen-Praefix- oder Suffix-Entfernung (anders als
    normalize_call_text) -- 'All 8'/'All Eight' bleiben Teil des Namens,
    sonst waere 'All 8 Swing Thru' von 'Swing Thru' nicht mehr unterscheidbar.

    Oeffentlich (Teil des Vertrags): der Aufrufer baut ``exact_lookup`` und
    ``rest_lookup`` fuer suggest_figure_set() MIT dieser Funktion, sonst
    passen die Schluessel nicht zusammen. lru_cache, weil sie beim Durchlauf
    ueber viele Call-Texte oft mit denselben Namen (kanonische Namen,
    (Anything)-Figuren) aufgerufen wird.
    """
    t = text.lower().replace('&', ' and ')
    # Vorpruefung spart die beiden Regex-Laeufe fuer fast alle Texte.
    if 'eight' in t or 'four' in t:
        for pat, digit in _DIGIT_WORD_RE:
            t = pat.sub(digit, t)
    return ' '.join(t.split())


# Zusaetzliche Endungen, die vor der Volltreffer-Pruefung abgeschnitten werden
# -- ueber die Klammern/Zahlen/'again' aus _SUFFIX_RE hinaus (siehe BL-210.7,
# Nachtrag 'All-8 ist der gefaehrliche Fall'). Ohne sie faellt z. B.
# 'All 8 Circulate Double' aus dem Volltreffer heraus und bekommt faelschlich
# einen Konzept-Vorschlag. In einer Schleife angewendet (eine Endung pro
# Durchlauf), wie es auch _SUFFIX_RE bei mehrfachem Aufruf braucht.
_REPEAT_SUFFIX_RE = re.compile(
    r'('
    r'\s*\([^)]*\)'          # Klammerzusatz, z. B. "(again)", "(!)"
    r'|\s+\d+\s*&\s*\d+/\d+'  # "1 & 1/2"
    r'|\s+\d+/\d+'            # blanker Bruch, z. B. "1/2"
    r'|\s+\d+'                # blanke Zahl
    r'|\s+again'
    r'|,?\s+go\s+double'
    r'|\s+double'
    r'|\s+twice'
    r'|\s+two\s+times'
    r'|\s+\d+\s+times'
    r'|\s+once\s+and\s+half'
    r'|\s*&\s*'
    r'|\s+and\s*'
    r')$',
    re.IGNORECASE,
)


# Jede Alternative von _REPEAT_SUFFIX_RE endet auf ')', '&', eine Ziffer oder
# eines dieser Woerter. Der Regex selbst probiert jede Textposition durch
# (fuehrendes \s*) -- die Vorpruefung erspart ihn den meisten Texten.
_REPEAT_SUFFIX_ENDINGS = ('again', 'double', 'twice', 'times', 'half', 'and')


def _strip_repeat_suffixes(text: str) -> str:
    t = text.strip()
    for _ in range(6):
        if not t or not (t[-1] in ')&' or t[-1].isdigit()
                         or t.casefold().endswith(_REPEAT_SUFFIX_ENDINGS)):
            break
        new = _REPEAT_SUFFIX_RE.sub('', t).strip()
        if new == t:
            break
        t = new
    return t


def _raw_exact_match(text: str, exact_lookup: dict,
                      rest_lookup: Optional[dict] = None) -> Optional[str]:
    """Volltreffer-Pruefung: trifft der GANZE Text (nach Rollen-Praefix- und
    Endungs-Bereinigung, vereinheitlicht) einen rohen kanonischen Namen?

    ``rest_lookup`` (optional) wird NUR gefragt, wenn ``exact_lookup`` keinen
    Treffer liefert, und zwar sowohl mit der Endungs-bereinigten Form (fuer
    Konsistenz mit exact_lookup) als auch mit der UNbereinigten Form -- ein
    Eintrag wie 'touch 1/4' aus bestehenden call_text_mappings waere sonst
    nicht wiederzufinden, weil die Wiederholungs-Endungs-Bereinigung den
    Bruch '1/4' als vermeintliche Zaehlangabe abschneiden wuerde.
    """
    if not text or not text.strip():
        return None
    t = text.strip()

    # Gewoehnliche Rollen-Praefixe faellt weg ('Heads Right & Left Thru' ->
    # 'Right & Left Thru'), aber nicht bei All-8/All-4-Couples-Texten --
    # die behandelt suggest_all8_figures() gesondert.
    if not (_ALL8_PREFIX_RE.match(t) or _ALL4_COUPLES_PREFIX_RE.match(t)):
        for _ in range(3):
            new = _GENERIC_ROLE_PREFIX_RE.sub('', t)
            if new == t:
                break
            t = new

    stripped = _strip_repeat_suffixes(t)
    if stripped:
        eid = exact_lookup.get(canon_key(stripped))
        if eid is not None:
            return eid

    if rest_lookup:
        if stripped:
            eid = rest_lookup.get(canon_key(stripped))
            if eid is not None:
                return eid
        key = canon_key(t)
        if key:
            return rest_lookup.get(key)

    return None


def figure_set_lookups(to_calls, figure_sets: dict) -> tuple:
    """(exact_lookup, rest_lookup) fuer suggest_figure_set() -- EINE Stelle
    fuer Call-Mapping-Dialog und Sequenz-Editor (BL-210.12).

    to_calls: get_teaching_order_calls(), aufsteigend nach Teaching Order --
    setdefault behaelt je Name die niedrigste Variante. figure_sets:
    get_all_call_text_figures(). rest_lookup nimmt nur EINDEUTIGE
    Zuordnungen und wird NIE in exact_lookup gemischt (sonst waere jeder
    gemappte Text ein Volltreffer und bekaeme keinen Vorschlag mehr).
    """
    exact_lookup = {}
    for eid, cname, _to, _prog in to_calls:
        exact_lookup.setdefault(canon_key(cname), eid)
    rest_lookup = {canon_key(t): f[0]
                   for t, f in figure_sets.items() if len(f) == 1}
    return exact_lookup, rest_lookup


def suggest_figure_set(raw_text: str, exact_lookup: dict,
                        rest_lookup: Optional[dict] = None) -> tuple:
    """Schlaegt eine Figuren-Menge fuer einen Call-Text vor, der erkennbar
    mehrere Figuren enthaelt.

    Reihenfolge (siehe BL-210.7):
        1. Volltreffer gegen rohe kanonische Namen -> kein Vorschlag. Nutzt
           NUR exact_lookup, nie rest_lookup -- ein Text, der bereits ueber
           eine bestehende Zuordnung aufloest, ist explizit einer der Faelle,
           fuer die BL-210.8 einen Vorschlag sehen will (siehe rest_lookup
           unten), kein Grund zur Unterdrueckung.
        2. All-8/All-4-Couples-Praefix (terminal: greift es, wird hier
           IMMER geantwortet -- K2 mit Vorschlag oder K3 ohne, nie ein
           Durchfallen zu Split). Einzige Ausnahme davor: der ganze Text
           ist eine (Anything)-Figur mit einer K1-Figur als Ziel
           ('All 8 Spin The Top & Spread') -> (Anything)-Figur statt Konzept.
        3. (Anything)-Figuren.
        4. Trennung an Komma/'&'/'and' (Split) -- zuletzt, sonst zerschneidet
           sie z. B. '(Anything) & Roll' am '&'.

    Args:
        exact_lookup: Pflicht. Dict canon_key(kanonischer Name) -> entity_id
            fuer ALLE bekannten Figuren und Konzepte (siehe canon_key).
        rest_lookup: Optional. Dict canon_key(bereits gemappter Call-Text)
            -> entity_id, z. B. aus bestehenden call_text_mappings. Wird NUR
            fuer die Restaufloesung hinter dem All-8/All-4-Couples-Praefix
            und fuer die Zielfigur der (Anything)-Figuren benutzt, IMMER
            nachrangig zu exact_lookup ('erst exact_lookup, dann
            rest_lookup'). OHNE rest_lookup bleibt das Verhalten exakt wie
            vorher. Split greift NIE auf rest_lookup zu -- es loest
            ausschliesslich ueber rohe kanonische Namen auf (BL-210.7,
            Nachtrag: sonst verdoppelt sich die Split-Klasse durch
            Bruchstuecke wie 'Explode' oder '1/2 Circulate').

    Returns:
        (figure_set, pattern) -- figure_set ist eine Liste von entity_ids
        oder None (kein Vorschlag). pattern ist 'all8' / 'anything' / 'split'
        oder None. Reihenfolge INNERHALB von figure_set ist kein einheitlicher
        Vertrag: suggest_all8_figures() liefert [Konzept, ...Rest],
        suggest_anything_figures() liefert [Zielfigur, (Anything)-Figur].
        BL-210.8 sollte figure_set als Menge vergleichen, nicht als Sequenz.
    """
    text = (raw_text or "").strip()
    if not text:
        return (None, None)

    if _raw_exact_match(text, exact_lookup) is not None:
        return (None, None)

    if _ALL8_PREFIX_RE.match(text) or _ALL4_COUPLES_PREFIX_RE.match(text):
        # K1-Figur mit (Anything)-Figur ('All 8 Spin The Top & Spread'):
        # die (Anything)-Figur mit der K1-Figur als Ziel gewinnt, sonst
        # kaeme das Konzept dazu. Nur exact_lookup -- das Ziel muss selbst
        # eine Figur mit All-8-Namen sein (BL-210.11, Stichprobe).
        figures = suggest_anything_figures(text, exact_lookup)
        if figures is not None:
            return (figures, "anything")
        figures = suggest_all8_figures(text, exact_lookup, rest_lookup)
        return (figures, "all8") if figures is not None else (None, None)

    figures = suggest_anything_figures(text, exact_lookup, rest_lookup)
    if figures is not None:
        return (figures, "anything")

    figures = suggest_split_figures(text, exact_lookup)
    if figures is not None:
        return (figures, "split")

    return (None, None)


# --- All-8 / All-4-Couples -------------------------------------------------

_ALL8_PREFIX_RE = re.compile(r'^all\s+(?:8|eight)\b\s*', re.IGNORECASE)
_ALL4_COUPLES_PREFIX_RE = re.compile(
    r'^all\s+(?:4|four)\s+couples\b\s*', re.IGNORECASE)


def _resolve_all8_rest(rest_text: str, exact_lookup: dict,
                        rest_lookup: Optional[dict] = None) -> Optional[list]:
    """Loest den Rest hinter dem All-8/All-4-Couples-Praefix auf.

    Erst Volltreffer (der Rest ist selbst genau eine Figur, ueber
    exact_lookup und -- falls gegeben -- rest_lookup), sonst rekursiv ueber
    die (Anything)-Erkennung. Split wird hier bewusst NICHT versucht -- der
    All-8-Zweig ist terminal, und der Rest soll nicht zusaetzlich am
    '&'/'and' zerschnitten werden.
    """
    rest = rest_text.strip()
    if not rest:
        return None

    single = _raw_exact_match(rest, exact_lookup, rest_lookup)
    if single is not None:
        return [single]

    figures, pattern = suggest_figure_set(rest, exact_lookup, rest_lookup)
    if figures is not None and pattern == "anything":
        return list(figures)

    return None


def suggest_all8_figures(raw_text: str, exact_lookup: dict,
                          rest_lookup: Optional[dict] = None) -> Optional[list]:
    """Konzept-Figur + aufgeloester Rest fuer 'All 8 ...'/'All 4 Couples ...'.

    None bedeutet K3 (Zweifelsfall) -- im Zweifel lieber kein Vorschlag als
    ein falscher (siehe BL-210.7, Nachtrag). ``rest_lookup`` siehe
    suggest_figure_set().
    """
    text = raw_text.strip()

    m = _ALL4_COUPLES_PREFIX_RE.match(text)
    concept_name = "All 4 Couples Concept"
    if not m:
        m = _ALL8_PREFIX_RE.match(text)
        concept_name = "All 8 Concept"
    if not m:
        return None

    concept_id = exact_lookup.get(canon_key(concept_name))
    if concept_id is None:
        return None

    rest_figures = _resolve_all8_rest(text[m.end():], exact_lookup, rest_lookup)
    if rest_figures is None:
        return None

    return [concept_id] + rest_figures


# --- (Anything)-Figuren ----------------------------------------------------

# (canonical_name der (Anything)-Figur, Platzhalter-Position). 'suffix' =
# "(Anything)" steht am Anfang, der Rest steht im Text VOR dem festen Teil.
# 'prefix' = "(Anything)" steht am Ende, der Rest steht im Text DANACH.
_ANYTHING_TEMPLATES = (
    ("(Anything) & Roll", "suffix"),
    ("(Anything) & Spread", "suffix"),
    ("Explode & (Anything)", "prefix"),
    ("Clover and (Anything)", "prefix"),
    ("(Anything) and Cross", "suffix"),
    ("Cross Clover and (Anything)", "prefix"),
    ("Transfer and (Anything)", "prefix"),
)

# (canon_key der (Anything)-Figur, canon_key des festen Teils, Position) --
# einmal beim Laden statt fuer jeden Call-Text neu (BL-210.11, Laufzeit beim
# Oeffnen).
_ANYTHING_KEYS = tuple(
    (canon_key(t), canon_key(t.replace("(Anything)", "")), pos)
    for t, pos in _ANYTHING_TEMPLATES)


def _lookup_target(rest_canon: str, lookup: Optional[dict]) -> Optional[str]:
    """entity_id fuer einen canon_key-Rest in ``lookup``, mit einem zweiten
    Versuch nach Abzug eines gewoehnlichen Rollen-Praefixes (z. B. 'Boys
    Trade & Roll' -> Rest 'boys trade' -> 'trade'). ``lookup`` darf None sein
    (z. B. rest_lookup, wenn der Aufrufer keins mitgibt).
    """
    if not lookup:
        return None
    eid = lookup.get(rest_canon)
    if eid is not None:
        return eid
    stripped = _GENERIC_ROLE_PREFIX_RE.sub('', rest_canon)
    if stripped != rest_canon:
        return lookup.get(stripped.strip())
    return None


def suggest_anything_figures(raw_text: str, exact_lookup: dict,
                              rest_lookup: Optional[dict] = None) -> Optional[list]:
    """Prueft die 7 (Anything)-Figuren. Der Text-Rest neben dem festen Teil
    muss exakt einer Figur entsprechen, sonst kein Treffer fuer diese
    (Anything)-Figur.

    Ziel-Aufloesung erst ueber exact_lookup, dann -- falls gegeben -- ueber
    rest_lookup (siehe suggest_figure_set()).
    """
    full_canon = canon_key(raw_text)
    if not full_canon:
        return None

    for template_key, fixed, position in _ANYTHING_KEYS:
        concept_id = exact_lookup.get(template_key)
        if concept_id is None:
            continue

        if position == "suffix":
            suffix = " " + fixed
            if not full_canon.endswith(suffix) or full_canon == fixed:
                continue
            rest_canon = full_canon[:-len(suffix)]
        else:
            prefix = fixed + " "
            if not full_canon.startswith(prefix):
                continue
            rest_canon = full_canon[len(prefix):]

        if not rest_canon:
            continue

        target_id = _lookup_target(rest_canon, exact_lookup)
        if target_id is None:
            target_id = _lookup_target(rest_canon, rest_lookup)
        if target_id is None:
            continue

        return [target_id, concept_id]

    return None


# --- Split -------------------------------------------------------------

_SPLIT_DELIM_RE = re.compile(r'\s*(?:,|&|\band\b)\s*', re.IGNORECASE)


def suggest_split_figures(raw_text: str, exact_lookup: dict) -> Optional[list]:
    """Trennt an Komma/'&'/'and'. Nur ein Treffer, wenn JEDER Teil eindeutig
    exakt einer Figur entspricht.

    Das Ergebnis ist eine MENGE: Reihenfolge wie im Text, aber ohne Duplikate.
    Loesen mehrere Teile auf dieselbe Figur auf ('Boys Trade, Girls Trade' —
    beides 'Trade', 'Swing Thru, Swing Thru Again'), bleibt danach nur eine
    Figur uebrig. Dann ist es kein Mehrfachfall und es gibt keinen Vorschlag:
    die Figur ist ueber den normalen Einzel-Vorschlag schon abgedeckt.
    """
    parts = [p for p in _SPLIT_DELIM_RE.split(raw_text) if p.strip()]
    if len(parts) < 2:
        return None

    entity_ids = []
    for part in parts:
        eid = _raw_exact_match(part, exact_lookup)
        if eid is None:
            return None
        entity_ids.append(eid)

    unique = list(dict.fromkeys(entity_ids))
    return unique if len(unique) > 1 else None


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




# ---- Zuordnungs-Logik des Call-Mapping-Dialogs (intern#143) ----

def suggestion_differs(suggestion, current) -> bool:
    """Filter "Vorschlag weicht ab": es gibt einen Mengen-Vorschlag, und er
    weicht als MENGE von der Zuordnung ab (Reihenfolge egal)."""
    return bool(suggestion) and set(current or ()) != set(suggestion)


def optimize_groups(call_texts, suggestions: dict, figure_sets: dict) -> dict:
    """Teilt die abweichenden Mengen-Vorschlaege (genau die Zeilen des
    Filters "Vorschlag weicht ab") in drei Gruppen:
    new    -> bisher ohne Zuordnung
    extend -> Vorschlag ist echte Obermenge der Zuordnung (fehlende Figuren)
    change -> Vorschlag weicht anders ab
    suggestions = {call_text: Vorschlag}, figure_sets = {call_text: Zuordnung}.
    Werte: {call_text: Vorschlag}."""
    groups = {"new": {}, "extend": {}, "change": {}}
    for call_text in dict.fromkeys(call_texts):
        sug = suggestions.get(call_text)
        current = figure_sets.get(call_text)
        if not suggestion_differs(sug, current):
            continue
        if not current:
            key = "new"
        elif set(current) < set(sug):
            key = "extend"
        else:
            key = "change"
        groups[key][call_text] = sug
    return groups


_fuzzy_cache = (None, {})


def fuzzy_suggest_cache(to_calls) -> dict:
    """Zwischenspeicher fuer CallMatcher.suggest je Call-Text: call_text ->
    (score, entity_id). Der Fuzzy-Vorschlag ist teuer (~2 s ueber alle ~10k
    ungemappten); haelt er die Sitzung ueber, oeffnet der Dialog beim zweiten
    Mal sofort. Aendert sich die Kanonisch-Call-Liste, beginnt er leer."""
    global _fuzzy_cache
    sig = hash(tuple((c[0], c[1]) for c in to_calls))
    if _fuzzy_cache[0] != sig:
        _fuzzy_cache = (sig, {})
    return _fuzzy_cache[1]
