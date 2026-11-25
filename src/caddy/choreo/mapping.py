"""Kartentext -> Taminations-Zeilen (intern#163, Square Flow intern#247).

Portiert aus dem Pruefstand `choreo-engines/eval/tam_export.py` (Stand 1e69832, Kontrolle
2026-11-15). Seit 2026-11-17 ist dies der einzige Ort der Regeln. Alle Regeln sind fest
eingeschaltet (`RULES`); die Namen bleiben, damit Gegenproben ohne eine Regel moeglich sind
(`monkeypatch` auf `RULES` in Tests).

Ergebnis je Sequenz (`prepare`):
  orig      Kartenzeilen, wie sie zu den gesendeten Zeilen gehoeren (eine Kartenzeile kann
            mehrere Zeilen erzeugen, z. B. "(Zero Line)" -> Heads Lead Right | Circle To A Line)
  lines     an Taminations: je Eintrag ein Call-Text oder {"alts": [...], "kinds": [...]}
            (Alternativen mit Rueckfall; kinds = Herkunft je Lesart)
  n_start   Anzahl einleitender Zeilen aus der Startformation (zaehlen nicht zur Sequenz)
  end       Aufloese-Call (Allemande Left, Promenade Home ...) oder None
  zweit     zweite Fassung (ergaenzter Kreis) oder None; siehe apply_heimplatz()
  kreis_of  je Zeile der fortgeschriebene Kreis ("Heads"/"Sides") oder None

Die Regel `kreis_heimplatz` braucht die Engine (Positionen); sie laeuft in
`apply_heimplatz()` mit einer uebergebenen Funktion run(request) -> response.
"""
import re

from caddy.choreo import call_table as _cm

QT_FREE = True

_ROWS = _cm.read_rows()
TABLE = _cm.load_fixed(_ROWS)
# Annahmen-Runde 3: gepruefte Vorschlaege aus dem App-Mapping (quelle=app_mapping) ersetzen die Zeile
# NICHT, sondern sind ihre letzte Lesart (beurteilt an Beispielen, in denen die Zeile sonst scheitert;
# als Ersatz verdraengten sie richtige Lesarten: 1150 "Heads Box Circulate", 4108 "Left Spin Chain ...")
APP_FEST = _cm.load_app_fixed(_ROWS)
for _k in APP_FEST:
    TABLE.pop(_k, None)

END_FORMATION = {"(zero line)", "(zero box)", "(rotated)"}
ABBREV = {"l.a": "Allemande Left", "la": "Allemande Left",
          "r.l.g": "Right and Left Grand", "rlg": "Right and Left Grand"}
# Endmarken: separat als Aufloese-Call gesendet.
# Taminations prueft bei diesen Calls selbst, ob die Taenzer aufgeloest sind.
END_CALL = {
    "l.a": "Allemande Left", "la": "Allemande Left", "allemande left": "Allemande Left",
    "left allemande": "Allemande Left",
    "r.l.g": "Right and Left Grand", "rlg": "Right and Left Grand",
    "right and left grand": "Right and Left Grand",
    "swing and promenade": "Promenade Home", "swing and promenade home": "Promenade Home",
    "promenade home": "Promenade Home", "promenade": "Promenade Home",
    "swing corner and promenade home": "Promenade Home",
    "swing corner and promenade": "Promenade Home",
    "you're home": None, "home": None,
}


class CardLine(str):
    """Kartentext mit Index der Kartenzeile (`idx`); laeuft als `orig` unveraendert durch die
    Regeln, damit jede gesendete Zeile ihre Kartenzeile kennt (Sequenz-Detail, Zeitachse)."""

    def __new__(cls, text, idx):
        s = super().__new__(cls, text)
        s.idx = idx
        return s


def _strip(c):
    s = c.strip()
    return CardLine(s, c.idx) if isinstance(c, CardLine) else s


def map_sequence(calls, app=None):
    """-> (out, n_start, end, erg). out/erg: Liste (Kartenzeile, gesendeter Eintrag)."""
    calls = [_strip(c) for c in calls if c and c.strip()]
    out = []                              # (orig, gesendet)
    if calls and calls[0].lower() == "(zero box)":
        out += [("(Zero Box)", "Heads Square Thru 4")]
        calls = calls[1:]
    elif calls and calls[0].lower() == "(zero line)":
        out += [("(Zero Line)", "Heads Lead Right"), ("(Zero Line)", "Circle To A Line")]
        calls = calls[1:]
    n_start = len(out)
    end = None
    if calls and calls[-1].lower() in END_FORMATION:
        calls = calls[:-1]
    elif calls:
        last = calls[-1].lower()
        if "ende_klammer" in RULES:              # R7: "(keep her) Promenade Home" ist der Aufloese-Call
            last = re.sub(r"\([^)]*\)", " ", last)
        last = re.sub(r"\s+", " ", last.replace("&", "and")).strip(" .")
        if last in END_CALL:
            end, calls = END_CALL[last], calls[:-1]
    for c in calls:
        t = c
        if re.fullmatch(r"\(.*\)", t.strip()):
            continue
        t = re.sub(r"\s*\(again\)\s*", " ", t, flags=re.I)
        t = re.sub(r"[()]", "", t)
        t = re.sub(r"\s+", " ", t).strip()
        t = ABBREV.get(t.lower(), t)
        if "tabelle" in RULES:
            fixed = TABLE.get(_cm.norm(c)) or TABLE.get(_cm.norm(t))
            if fixed:
                out += [(c, f) for f in fixed]
                continue
        if t:
            out.append((c, t))
    out = out[:n_start] + apply_r2(out[n_start:], first_is_start=(n_start == 0))
    # R3: Sequenz ohne Startangabe, deren 1. Call nicht aus dem Squared Set geht
    #     -> Zero Box annehmen (abschaltbar, durch typ_start ersetzt)
    if "implizit_zero_box" in RULES and n_start == 0 and out \
            and not SQUARED_START.match(out[0][1]):
        out = [("(implizit Zero Box)", "Heads Square Thru 4")] + out
        n_start = 1
    if "heads_kontext" in RULES:
        out = out[:n_start] + heads_context(out[n_start:])
    erg = None
    if RULES & set(R4_RULES + R5_RULES + R7_RULES + R8_RULES + R9_RULES):
        body, erg, kreis_of = alternatives(out[n_start:], static=(n_start == 0), app=app)
        erg = (out[:n_start] + erg, [None] * n_start + kreis_of) if erg else None
        out = out[:n_start] + body
    return out, n_start, end, erg


# ---- Runde 4: Alternativen mit Rueckfall (die Engine probiert sie nur, wenn
#      der Eintrag unveraendert scheitert; siehe tam_cli "alts") ----
R4_RULES = ["zeilen_split", "gruppen_kontext", "others", "hilfsklammern"]

GROUP = re.compile(
    r"^(very centers|center (?:boys|girls|four|4|six|6)|end (?:boys|girls)|heads|sides|centers|ends|"
    r"boys|girls|leaders|trailers|beaus|belles|outsides|insides|lead couples|trailing couples)\b", re.I)
OTHERS = {"centers": "Ends", "ends": "Centers", "heads": "Sides", "sides": "Heads",
          "boys": "Girls", "girls": "Boys", "leaders": "Trailers", "trailers": "Leaders",
          "beaus": "Belles", "belles": "Beaus", "outsides": "Centers", "insides": "Ends",
          "very centers": "Others", "center four": "Outsides", "center 4": "Outsides"}
MAX_ALTS = 8


def _group(t):
    m = GROUP.match(t.strip())
    return m.group(1).lower() if m else None


def _resolve_others(parts, prev_group):
    """'Others X' -> Gegenstueck der zuletzt genannten Gruppe (innerhalb der Teile fortlaufend)."""
    out, g = [], prev_group
    for p in parts:
        m = re.match(r"^(others?|the others)\b\s*(.*)$", p.strip(), re.I)
        if m and g and OTHERS.get(g, "Others") != "Others":
            p = f"{OTHERS[g]} {m.group(2)}".strip()
        out.append(p)
        g = _group(p) or g
    return out


def _splits(t):
    """Moegliche Aufteilungen einer Zeile in Einzel-Calls (Komma, dann je ein '&'/'and')."""
    res = []
    commas = [p.strip() for p in t.split(",") if p.strip()]
    if len(commas) > 1:
        res.append(commas)
    base = commas if len(commas) > 1 else [t]
    for i, part in enumerate(base):
        for m in re.finditer(r"\s+(?:&|and)\s+", part, re.I):
            a, b = part[:m.start()].strip(), part[m.end():].strip()
            if a and b:
                res.append(base[:i] + [a, b] + base[i + 1:])
    return res


# ---- Runde 5: Named Dancers + "X Only" (ebenfalls als Alternativen mit Rueckfall) ----
R5_RULES = ["named_dancers", "only"]
NAMED = [  # (Muster am Zeilenanfang, Ersatz) - Taminations kennt die Langform nicht
    (re.compile(r"^new (centers?|ends|leaders|trailers)\b", re.I), lambda m: m.group(1).title()),
    # "New Heads" = wer jetzt auf Kopfposition steht; "Heads" allein ist in Taminations
    # mehrdeutig (Original Heads / Head Positions) -> Head/Side Positions (David, 2026-11-15)
    (re.compile(r"^new (head|side)s\b", re.I), lambda m: m.group(1).title() + " Positions"),
    (re.compile(r"^those facing\b", re.I), lambda m: "Facing Dancers"),
    (re.compile(r"^(?:those|other) (boys|girls|four|4)\b", re.I), lambda m: m.group(1).title()),
    (re.compile(r"^(?:those|other|same) (ladies|men)\b", re.I),
     lambda m: "Girls" if m.group(1).lower() == "ladies" else "Boys"),
]
SAME = re.compile(r"^same (?:4|four|couples|dancers)\b", re.I)
KLAMMER_DESIG = re.compile(r"^\s*\(\s*same (?:4|four|couples|dancers)\s*\)", re.I)
ONLY = re.compile(r"^(" + GROUP.pattern[1:] + r")\s+only\b,?\s*", re.I)


def _named(part, prev_group):
    p = part.strip()
    for rx, rep in NAMED:
        m = rx.match(p)
        if m:
            return rep(m) + p[m.end():]
    m = SAME.match(p)
    if m and prev_group:
        return prev_group.title() + p[m.end():]
    return p


def _r5(parts, prev_group):
    out, g = [], prev_group
    for p in parts:
        if "named_dancers" in RULES:
            p = _named(p, g)
        if "only" in RULES:
            m = ONLY.match(p)
            if m and p[m.end():]:
                p = f"{m.group(1)} {p[m.end():]}"
        out.append(p)
        g = _group(p) or g
    return out


# ---- Runde 7: Reihenfolge der Lesarten (Schleife 2, David) ----
# Taminations nimmt manche falsche Lesart stillschweigend an; der Fehler zeigt sich erst
# eine Zeile spaeter, wo der Rueckfall ihn verdeckt. Deshalb die wahrscheinlichere Lesart zuerst:
# - komma_zuerst:    "Boys Run, Girls Trade" = zwei Calls (Taminations tanzt es sonst als einen);
#                    der Designator gilt weiter ("Heads R&L Thru, Backaway" -> Heads Backaway).
#                    Ausnahme: Stern-Modifikation ", Turn the Star 1/2" und "...And X" gehoeren zum Call
# - others_zuerst:   "Others Trade" -> "Ends Trade" vor dem rohen "Others" (Taminations loest falsch auf)
# - klammern_zuerst: Klammern sind Hinweise ("Rollaway (half sashay)", "(lefty)") -> ohne zuerst
R7_RULES = ["komma_zuerst", "others_zuerst", "klammern_zuerst"]
OTHERS_RX = re.compile(r"^(others?|the others)\b", re.I)
STAR_MOD = re.compile(r",\s*(?:do not )?turn the star\b", re.I)
# Calls fuer alle: kein Designator aus dem Teil davor ("Girls Trade, Couples Circulate")
FOR_ALL = re.compile(r"^(couples?|all|everyone|everybody)\b", re.I)


def _comma_carry(t):
    """Komma-Teile als Einzel-Calls; der Designator gilt weiter, bis ein neuer kommt:
    "Heads Right & Left Thru, Backaway" -> Heads Right & Left Thru | Heads Backaway,
    "Center 4, Couples Trade" -> Center 4 Couples Trade (reiner Designator gehoert zum Folge-Call).
    None, wenn die Zeile nicht so zerlegt werden soll (Stern-Modifikation, "...And X")."""
    parts = [p.strip() for p in t.split(",") if p.strip()]
    if len(parts) < 2 or STAR_MOD.search(t) or any(p.startswith("...") for p in parts):
        return None
    out, desig, pending = [], None, ""
    for p in parts:
        p = f"{pending} {p}".strip() if pending else p
        pending = ""
        m = GROUP.match(p)
        if m:
            desig = m.group(1)
            if not p[m.end():].strip():          # nur Designator -> mit dem naechsten Teil
                pending = p
                continue
        elif desig and not FOR_ALL.match(p):
            p = f"{desig} {p}"
        out.append(p)
    if pending:
        return None
    return out if len(out) > 1 else None


def _r7_order(alts, t, stripped_alt, komma_alt):
    resolved_exists = any(not any(OTHERS_RX.match(x) for x in a) for a in alts)

    def key(a):
        k_others = 1 if ("others_zuerst" in RULES and resolved_exists
                         and any(OTHERS_RX.match(x) for x in a)) else 0
        k_klammer = 0 if ("klammern_zuerst" in RULES and stripped_alt is not None
                          and [x.lower() for x in a] == [x.lower() for x in stripped_alt]) else 1
        k_komma = 0 if (komma_alt is not None
                        and [x.lower() for x in a] == [x.lower() for x in komma_alt]) else 1
        return (k_others, k_klammer, k_komma)
    return sorted(alts, key=key)          # stabil: sonst bleibt die bisherige Reihenfolge


# ---- Runde 8: aktiven Kreis fortschreiben (Schleife 3, Thomas) ----
# Aus dem Static Set gilt nach "Heads X" der Kreis der Heads weiter: Zeilen ohne Designator
# ("Single Hinge") und mit Geschlecht allein ("Men Run", "Those Men Run") meinen die Aktiven.
# Taminations tanzt die woertliche Lesart sonst still fuer alle 8. Deshalb die fortgeschriebene
# Lesart ZUERST ("Heads Single Hinge", "Head Boys Run"), die woertliche bleibt Rueckfall.
# Der Kreis endet bei einem anderen Designator, bei Calls fuer alle (KREIS_ENDE_VOR, ohne
# Fortschreibung) und nach Calls, mit denen die Aktiven auf die Inaktiven treffen
# (KREIS_ENDE_NACH, Teilregel "kreis_ende_nach": diese Zeile noch mit Fortschreibung).
R8_RULES = ["kreis_fortschreiben", "kreis_ende_nach"]
KREIS_START = re.compile(r"^(head|side)s?\b", re.I)
GENDER = re.compile(r"^(?:(?:those|same|other|the)\s+)?(men|boys|ladies|girls)\b\s*", re.I)
KREIS_ENDE_VOR = re.compile(
    r"^(circle|promenade|allemande|left allemande|right (?:&|and) left grand|grand\b|"
    r"swing(?! thru)|weave|star (?:right|left)|all\b|everyone|everybody|couples?\b|others?\b|"
    r"the others|(?:4|four|8|eight)\b|extend|chain reaction|ping pong circulate|"
    r"double pass thru|track (?:2|two)|acey deucey|scoot chain thru|crossover circulate)", re.I)
# auch innerhalb zusammengesetzter Calls ("Recycle & Pass Thru", "Explode & Square Thru 2")
KREIS_ENDE_NACH = re.compile(
    r"(?:^|&\s*|and\s+)(pass thru|(?:1/2 )?square thru|veer (?:left|right)|lead (?:right|left)|"
    r"separate|split two|around|dive thru|trade by|walk (?:&|and) dodge)\b", re.I)
# Calls, nach denen die Taenzer wieder auf den Heimplaetzen stehen (Static Set bleibt)
HOME_CALL = re.compile(
    r"^(promenade (?:1/2|half(?: ?way)?|3/4|full|all the way)|(?:4 |four |two |2 )?ladies chain"
    r"(?: 3/4| across)?$|right (?:&|and) left thru$|(?:reverse )?flutter wheel$|half sashay$|"
    r"rollaway|roll ?a ?way|courtesy turn$|circle (?:left|right)|bow|honor|dosado$|swing$)", re.I)
# Start-Calls, nach denen die Aktiven in der Mitte unter sich bleiben (Thomas, Schleife 3:
# 1330, 2053, 2109, 2800, 7425, 9928-9994, 10022-10074)
KREIS_START_OK = re.compile(
    r"^(swing thru|touch 1/4|pass the ocean|step to a wave|dosado to a wave|pass thru|"
    r"square thru 3/4|square thru 3|veer (?:left|right)|slide thru|"
    r"single circle to a wave)$", re.I)


# ---- Annahmen-Runde 2 (David, 2026-11-13, Urteile zur Lesarten-Seite) ----
# kreis_ende_fix:  "Split 2 Around 1" beendet den Kreis nach der Zeile (bisher nur "split two",
#                  2897); "Spin the Windmill" ist ein Call fuer alle (8392)
# scoot_back_alle: "Scoot Back" ist ein Call fuer alle, nicht fortschreiben (1485, 6207)
# kreis_heimplatz: Positions-Pruefung statt Call-Listen (R8b): die ergaenzte Fassung wird getanzt;
#                  ab der ersten fortgeschriebenen Zeile, vor der ein Inaktiver nicht mehr auf
#                  seinem Heimplatz steht (Ort oder Blickrichtung), gilt wieder die woertliche Lesart
# kreis_geprueft_zuerst: die ergaenzte Fassung, die die Heimplatz-Pruefung besteht, kommt ZUERST
#                  ("lines"); die woertliche geht als zweite Fassung in den zweiten Durchgang
#                  (Entscheidung David: in den 18 Lesarten-Faellen 18/18 statt 15/18 richtig)
R10_RULES = ["kreis_ende_fix", "scoot_back_alle", "kreis_heimplatz", "kreis_geprueft_zuerst"]
ENDE_VOR_FIX = re.compile(r"^spin the windmill\b", re.I)
ENDE_VOR_SCOOT = re.compile(r"^scoot back\b", re.I)
ENDE_NACH_FIX = re.compile(r"(?:^|&\s*|and\s+)split (?:2|two) around (?:1|one)\b", re.I)


def _ende_vor(p):
    return bool(KREIS_ENDE_VOR.match(p)
                or ("kreis_ende_fix" in RULES and ENDE_VOR_FIX.match(p))
                or ("scoot_back_alle" in RULES and ENDE_VOR_SCOOT.match(p)))


def _ende_nach(c):
    return bool(KREIS_ENDE_NACH.search(c) or ("kreis_ende_fix" in RULES and ENDE_NACH_FIX.search(c)))


def _kreis_call(p):
    """Call ohne fuehrenden Designator ("Head Boys Run" -> "Run", "Heads Pass Thru" -> "Pass Thru")."""
    p = re.sub(r"^(?:(head|side)s?\s+)", "", p.strip(), flags=re.I)
    m = GENDER.match(p) or GROUP.match(p)
    return p[m.end():].strip() if m else p


def _kreis_teil(p, kreis):
    """Einen Call-Teil auf den aktiven Kreis beziehen; None = Teil gehoert nicht zum Kreis."""
    gm = GENDER.match(p)
    if gm:
        g = "Boys" if gm.group(1).lower() in ("men", "boys") else "Girls"
        rest = p[gm.end():].strip()
        return f"{kreis[:-1]} {g} {rest}".strip() if rest else None
    if KREIS_START.match(p) or re.match(r"^(same|those|new|other)\b", p, re.I):
        return p                       # schon benannt ("Same 4 Recycle", "New Centers ...")
    if _group(p) is not None or _ende_vor(p):
        return None
    return f"{kreis} {p}"


# ---- Annahmen-Runde 1: woertliche Lesart zuerst (David, 2026-11-13) ----
# Lesarten mit ergaenztem Designator (Herkunft "kreis" = R8-Fortschreibung, "kontext" = aus dem
# Kontext dazugedacht) kommen immer HINTER die woertlichen; sie greifen nur noch, wenn die
# woertliche Lesart an dieser Zeile scheitert (Rueckfall). Die R8-Reihenfolge (Fortschreibung
# zuerst) geht als zweite Fassung mit; die Endkontrolle misst sie nur, wenn die woertliche Fassung
# nicht gruen endet (Endkontrolle als Schiedsrichter).
R9_RULES = ["woertlich_zuerst"]
ERGAENZT = ("kreis", "kontext")


def _woertlich_zuerst(uniq, kinds_of):
    """Stabile Teilung: woertliche Lesarten zuerst, ergaenzte Designatoren dahinter."""
    return ([a for a in uniq if kinds_of(a) not in ERGAENZT]
            + [a for a in uniq if kinds_of(a) in ERGAENZT])


def alternatives(body, static=False, app=None):
    """-> (Zeilen, Zeilen in R8-Reihenfolge oder None, wenn gleich, Kreis je Zeile)."""
    out, out_erg, kreis_of = [], [], []      # kreis_of: Kreis je fortgeschriebener Zeile
    prev_groups = []                       # Designatoren der vorherigen Zeilen (neueste zuerst)
    kreis = None                           # R8: aktiver Kreis ("Heads"/"Sides") im Static Set
    zuhause = True                         # R8: Inaktive stehen noch auf den Heimplaetzen
    for orig, t in body:
        # Herkunft jeder Lesart: roh, split, named, others, kontext (Designator aus dem Kontext
        # dazugedacht), klammer, kreis, app, mehrfach
        kinds = {}
        kreis_zeile = None

        def add(a, kind):
            kinds.setdefault(tuple(x.lower() for x in a), kind)
            alts.append(a)
        alts = []
        add([t], "roh")
        if "zeilen_split" in RULES:
            for a in _splits(t):
                add(a, "split")
        komma_alt = _comma_carry(t) if "komma_zuerst" in RULES else None
        if komma_alt:
            add(komma_alt, "split")
        if RULES & set(R5_RULES):
            for a in list(alts):
                r = _r5(a, prev_groups[0] if prev_groups else None)
                if r != a:
                    add(r, "named")
        if "others" in RULES and prev_groups:
            for a in list(alts):
                r = _resolve_others(a, prev_groups[0])
                if r != a:
                    add(r, "others")
        if "gruppen_kontext" in RULES and _group(t) is None \
                and not re.match(r"^(others?|the others|all|everyone|everybody)\b", t.strip(), re.I):
            for g in prev_groups[:2]:
                name = g.title()
                for a in list(alts):
                    if _group(a[0]) is None:
                        add([f"{name} {a[0]}"] + a[1:], "kontext")
        stripped_alt = None
        # "(Same 4) X" ist ein Designator, kein Hinweis: nicht als Klammer-Lesart weglassen
        # (David, 11303: die Centers aus der Zeile davor tanzen den Pass Out)
        klammer_desig = "klammer_designator" in RULES and KLAMMER_DESIG.match(orig)
        if "hilfsklammern" in RULES and re.search(r"\(.*?\)", orig) and not klammer_desig:
            stripped = re.sub(r"\s*\([^)]*\)\s*", " ", orig).strip()
            stripped = re.sub(r"\s+", " ", stripped)
            if stripped:
                # R7: dieselben Umschreibungen wie fuer die Zeile selbst (Stern, Brueche ...),
                # sonst wuerde die Lesart ohne Klammer an der Schreibweise scheitern
                if "klammern_zuerst" in RULES and not TABLE.get(_cm.norm(orig)):
                    stripped_alt = [p for _, p in apply_r2([(orig, stripped)], False)] or [stripped]
                    add(stripped_alt, "klammer")
                else:
                    add([stripped], "klammer")
        # doppelte entfernen
        seen, uniq = set(), []
        for a in alts:
            k = tuple(x.lower() for x in a)
            if k not in seen:
                seen.add(k)
                uniq.append(a)
        if RULES & set(R7_RULES):
            uniq = _r7_order(uniq, t, stripped_alt, komma_alt)
        if "kreis_fortschreiben" in RULES and static:
            # Zustand: zuhause (alle im Static Set) -> kreis (nur Heads/Sides aktiv) -> vorbei
            km = KREIS_START.match(t)
            calls = [_kreis_call(p) for p in uniq[0]]           # Call ohne Designator
            nach = "kreis_ende_nach" in RULES
            if kreis is None and zuhause:
                if km and not all(HOME_CALL.match(c) for c in calls):
                    # Startzeile: nur nach Calls, bei denen die Aktiven unter sich in der Mitte
                    # bleiben (Positivliste KREIS_START_OK, aus Thomas' Faellen). Nach
                    # "Heads Square Thru 2/4", "Star Thru", "Lead Right" stehen sie vor den Inaktiven.
                    if all(KREIS_START_OK.match(c) or HOME_CALL.match(c) for c in calls) \
                            and KREIS_START_OK.match(calls[-1]):
                        kreis = "Heads" if km.group(1).lower() == "head" else "Sides"
                    zuhause = False
                elif not km and not all(HOME_CALL.match(c) for c in calls):
                    zuhause = False                         # erster Call fuer alle
                # "Heads Promenade 1/2", "4 Ladies Chain" ...: alle wieder zu Hause
            elif kreis and km:
                same = kreis.lower().startswith(km.group(1).lower())
                if not same or (nach and any(_ende_nach(c) for c in calls)):
                    kreis = None                            # Heads, dann Sides: alle aktiv
            elif kreis:
                teile = [_kreis_teil(p, kreis) for p in uniq[0]]
                if any(x is None for x in teile):
                    kreis = None
                else:
                    key = [x.lower() for x in teile]
                    uniq = [teile] + [a for a in uniq if [x.lower() for x in a] != key]
                    kreis_zeile = kreis
                    kinds.setdefault(tuple(key), "kreis")
                    if nach and any(_ende_nach(c) for c in calls):
                        kreis = None
        uniq = uniq[:MAX_ALTS]
        app_alt = []                            # Runde 3: App-Lesart, s. mit_app()
        geprueft = False
        if "app_mapping" in RULES:
            a = _app_alt(orig, t, app or {})
            if a and tuple(x.lower() for x in a) not in kinds:
                kinds[tuple(x.lower() for x in a)] = "app"
                app_alt = [a]
                geprueft = _cm.norm(orig) in APP_FEST
        mehr = []                               # Runde 4: Mehrfach-Calls, ganz hinten
        if "mehrfach" in RULES:
            a = _mehrfach(t)
            if a and tuple(x.lower() for x in a) not in kinds:
                kinds[tuple(x.lower() for x in a)] = "mehrfach"
                mehr = [a]

        def kind(a):
            return kinds[tuple(x.lower() for x in a)]

        def mit_app(u):
            """Automatische Schreibvariante: letzte Lesart. Gepruefter Eintrag: vor den dazugedachten
            Designatoren (Rueckfall "kontext"/"kreis" ab Stelle 2), die sonst Autorenfehler verdecken
            (9635, 2997: "Heads Box Circulate" statt Split Circulate). Mehrfach-Calls ganz hinten."""
            if not geprueft:
                return u + app_alt + mehr
            k = next((i for i in range(1, len(u)) if kind(u[i]) in ERGAENZT), len(u))
            return u[:k] + app_alt + u[k:] + mehr

        def entry(u):
            return t if len(u) == 1 else {"alts": u, "kinds": [kind(a) for a in u]}
        out_erg.append((orig, entry(mit_app(uniq))))
        kreis_of.append(kreis_zeile)
        if "woertlich_zuerst" in RULES:
            uniq = _woertlich_zuerst(uniq, kind)
        out.append((orig, entry(mit_app(uniq))))
        g = _group(_r5([t], prev_groups[0] if prev_groups else None)[0]) \
            if RULES & set(R5_RULES) else _group(t)
        if g:
            prev_groups = [g] + [x for x in prev_groups if x != g]
    return out, (out_erg if out_erg != out else None), kreis_of


# ---- Runde 3 ----
SQUARED_START = re.compile(
    r"^(heads?|sides?|original|four|4|all|everyone|everybody|circle|allemande|left allemande|"
    r"promenade|grand|ladies|swing(?! thru)|rollaway|half sashay|bow|honor|right and left grand|"
    r"right & left grand|dosado|weave)\b", re.I)
# Heads-Calls im Squared Set, nach denen die Heads weiter die Aktiven sind
HEADS_STAY = re.compile(
    r"^(heads|sides) (star thru|slide thru|right (&|and) left thru|flutter wheel|"
    r"reverse flutter wheel|ladies chain|promenade 1/2|promenade 3/4|half sashay|rollaway)$", re.I)
# typische Calls aktiver Paare; nur diese bekommen den Designator (nicht z. B. Double Pass Thru)
ACTIVE_NEXT = re.compile(
    r"^(pass thru|lead (right|left)|square thru( \d)?|1/2 square thru|sweep 1/4|star thru|"
    r"slide thru|right (&|and) left thru|flutter wheel|reverse flutter wheel|pass the ocean|"
    r"touch 1/4|ladies chain|half sashay|rollaway|step to a wave|dosado to a wave|"
    r"wheel thru|left wheel thru|veer (left|right))$", re.I)


def heads_context(body):
    out = []
    for o, t in body:
        if out and HEADS_STAY.match(out[-1][1]) and ACTIVE_NEXT.match(t):
            t = f"{DESIG.match(out[-1][1]).group(1).capitalize()} {t}"
        out.append((o, t))
    return out


# ---- Regeln (alle eingeschaltet; Namen fuer Gegenproben) ----
ALL_RULES = ["synonyme", "all_prefix", "brueche", "tag_richtung",
             "split_square_start", "designator_kontext", "come_down",
             # Runde 3
             "heads_kontext", "typ_start",
             # Runde 4 (Alternativen mit Rueckfall)
             "zeilen_split", "gruppen_kontext", "others", "hilfsklammern",
             # Runde 5 (Named Dancers, "X Only")
             "named_dancers", "only",
             # Runde 5b (Stern-Modifikation bei Chain Reaction / Motivate)
             "star_drehung",
             # Runde 6: feste Eintraege aus call_mapping.csv
             "tabelle",
             # Runde 6b: Clover & Anything
             "clover_anything",
             # Runde 7: Reihenfolge der Lesarten (Schleife 2)
             "komma_zuerst", "others_zuerst", "klammern_zuerst", "ende_klammer",
             # Runde 8: aktiven Kreis fortschreiben (Schleife 3)
             "kreis_fortschreiben", "kreis_ende_nach",
             # Annahmen-Runde 1: woertliche Lesart zuerst, Ergaenzung als Rueckfall / 2. Fassung
             "woertlich_zuerst",
             # Annahmen-Runde 2: Kreis-Ende (Fix, Scoot Back, Heimplatz-Pruefung)
             "kreis_ende_fix", "scoot_back_alle", "kreis_heimplatz", "kreis_geprueft_zuerst",
             # Annahmen-Runde 3: Callname aus dem Call-Mapping der App als letzte Lesart
             "app_mapping",
             # Annahmen-Runde 4: Mehrfach-Calls als letzte Lesart
             "mehrfach",
             # Singing Calls: Swing + Promenade der neuen Partnerin als Aufloese-Call (Beatzaehlung)
             "singer_ende",
             # 2026-11-15 (Kontrolle 8192/11303): Cast-a-Shadow-Variante, (Same 4) als Designator
             "shadow_variante", "klammer_designator"]
# Nicht eingeschaltet, nur fuer Gegenproben: "implizit_zero_box" (durch typ_start ersetzt),
# "ketten" (Komma-Ketten zerlegen, in Runde 2 negativ), "app_mapping_breit".
RULES = set(ALL_RULES)

I = re.I
SUBS = {
    # "Head Position" NICHT auf "Heads" mappen: Taminations unterscheidet
    # "Original Heads" und "Head Positions" (sonst "Ambiguous")
    "synonyme": [(r"^hds\b", "Heads"), (r"^sds\b", "Sides"),
                 (r"^(two|2) ladies chain", "Ladies Chain"),
                 (r"\bto an ocean wave\b", "to a Wave")],
    # "All the Boys Run" meint die Gruppe, nicht Everyone: Taminations kennt nur
    # "Boys Run" ("Everyone the Boys" / "All the Boys" / "The Boys" -> not found)
    "all_prefix": [(r"^all eight\b", "All 8"),
                   (r"^all the (?=(?:boys|girls|ladies|men|beaus|belles)\b)", ""),
                   (r"^all (?!8\b|4\b|four\b)", "Everyone ")],
    "brueche": [(r"\b(\d) & 1/2\b", r"\1 1/2"), (r"\b(\d) and 1/2\b", r"\1 1/2"),
                (r"\bpromenade (1/2 way|half ?way)\b", "Promenade 1/2"),
                (r" double$", " Twice"), (r"^1/2 tag the line$", "Half Tag")],
    # R5b: Stern-Modifikation (kein zweiter Call) in Taminations-Schreibweise
    # R6b: "(Cross) Clover & <Call>" ist EIN Call (David); Taminations kennt nur "and"
    "clover_anything": [(r"\b((?:cross )?clover)\s*&\s*(?=\S)", r"\1 and ")],
    "star_drehung": [(r"\b(chain reaction|motivate),?\s+(?:but,?\s+)?(?:turn the\s+)?stars?\s+(\d/\d)\b",
                      r"\1, Turn the Star \2"),
                     (r"\b(chain reaction|motivate),?\s+(?:but,?\s+)?(?:don'?t|do not)\s+turn the star\b",
                      r"\1, Do Not Turn the Star")],
    # Variante von Cast a Shadow (David, 8192): die Trailing Centers drehen 3/4 statt Hinge.
    # Taminations kennt sie als "Cast a Shadow, Centers Go 3/4" (coded_call.dart); sonst
    # tanzt es "Trailing Centers Cast Off 3/4" als zweiten Call hinterher.
    "shadow_variante": [(r"\bcast a shadow,?\s+(?:but,?\s+)?(?:the\s+)?(?:trailing\s+)?centers?\s+"
                         r"(?:go|cast(?: off)?)\s+3/4\b", "Cast a Shadow, Centers Go 3/4")],
}
DESIG = re.compile(r"^(heads|sides)\b", I)
COME_DOWN = re.compile(r"^come (down|into|in to) the middle\s*(?:(?:&|and)\s*(.*))?$", I)


def apply_r2(body, first_is_start):
    if not RULES:
        return body
    res = []
    for orig, t in body:
        for rule in ("synonyme", "star_drehung", "shadow_variante", "clover_anything"):
            if rule in RULES:
                for pat, rep in SUBS[rule]:
                    t = re.sub(pat, rep, t, flags=I)
        parts = [p.strip() for p in t.split(",")] if "ketten" in RULES else [t]
        for p in parts:
            if not p:
                continue
            for rule in ("all_prefix", "brueche"):
                if rule in RULES:
                    for pat, rep in SUBS[rule]:
                        p = re.sub(pat, rep, p, flags=I)
            m = re.fullmatch(r"(.*tag the line) (right|left|in|out)", p, flags=I)
            if "tag_richtung" in RULES and m:
                res += [(orig, m.group(1)), (orig, "Face " + m.group(2).capitalize())]
            else:
                res.append((orig, p))
    # Startposition: "Heads Split Square Thru" verlangt "Heads Start ..."
    if "split_square_start" in RULES and first_is_start and res:
        o, t = res[0]
        res[0] = (o, re.sub(r"^(heads|sides) split square thru", r"\1 Start Split Square Thru",
                            t, flags=I))
    # Designator-Kontext: letzter Heads/Sides-Designator gilt fuer "Separate ..."
    # bzw. fuer den Call nach "Come Down The Middle"
    out, last, pending = [], None, False
    for o, t in res:
        if "come_down" in RULES:
            m = COME_DOWN.match(t)
            if m:
                pending = True
                if not m.group(2):
                    continue
                t = m.group(2)
        need = pending or ("designator_kontext" in RULES and re.match(r"^separate\b", t, I))
        if need and last and not DESIG.match(t):
            t = f"{last} {t}"
        pending = False
        d = DESIG.match(t)
        if d:
            last = d.group(1).capitalize()
        out.append((o, t))
    return out


# ---- Startformation aus dem Sequenztyp (intern#163) ----
def typ_start(seq_type, calls):
    """Startformation aus sequences.type ableiten, wenn die Sequenz selbst keine
    Startangabe hat: als Pseudo-Eintrag "(Zero Box)"/"(Zero Line)" voranstellen."""
    t = (seq_type or "").lower()
    if calls and calls[0].strip().lower() in ("(zero box)", "(zero line)"):
        return calls
    if t.startswith("zero box") or t in ("zero (facing couples)", "two couples (facing couples)",
                                         "zero (eight chain thru)"):
        return ["(Zero Box)"] + calls
    if t.startswith("zero line") or t == "zero (facing lines)":
        return ["(Zero Line)"] + calls
    if t == "zero (parallel waves)":
        return ["(Zero Box)", "Step To A Wave"] + calls
    return calls


# ---- Singing Calls: Swing + Promenade am Ende (David, 2026-11-13) ----
# Jede Singer-Sequenz endet mit Swing und Promenade der neuen Partnerin; die gehoeren in die
# Beatzaehlung (eine Singing-Call-Figur hat hoechstens 64 Beats). Taminations tanzt das als EINEN
# Call und prueft dabei selbst die Aufloesung (promenade_home.dart). Die eigene Schluss-Zeile der
# Karte ("Swing & Promenade", "Swing (corner), Promenade", "Corner Swing & Promenade Home" ...)
# entfaellt dafuer.
SINGER_ENDE = {"singer (corner progression)": "Swing Corner and Promenade",
               "singer (r-h lady progression)": "Swing Right Hand Girl and Promenade"}
SINGER_SCHLUSS = re.compile(
    r"^(?:all\s+)?(?:\(?keep (?:her|the girl)\)?\s*(?:&|and)?\s*)?(?:swing\b|corner swing\b|"
    r"take your corner\b|come back\b|promenade\b).*\bpromenade\b|^(?:\(?keep (?:her|the girl)\)?\s*)?"
    r"promenade(?: home)?$", re.I)


def singer_ende(styp, body, end, erg):
    ende = SINGER_ENDE.get((styp or "").lower())
    if not ende:
        return body, end, erg
    if end is None and body and SINGER_SCHLUSS.search(body[-1][0].strip()) \
            and "wrong way" not in body[-1][0].lower():
        body = body[:-1]
        if erg:
            erg = (erg[0][:-1], erg[1][:-1])
    return body, ende, erg


KREIS_PAARE = {"Heads": ("1", "3"), "Sides": ("2", "4")}


def _zuhause(start, now, dancers, kreis, tol=0.75):
    """Stehen alle Inaktiven (Paare ausserhalb des Kreises) auf Heimplatz und schauen zur Mitte?
    Toleranz 0.75: Taminations rueckt Inaktive zum Platzmachen um 0.5 nach aussen (9928, 10038).
    Heimplatz = irgendein Platz des Static Square mit dessen Blickrichtung, nicht der eigene
    Startplatz: nach "Four Ladies Chain" stehen die Girls beim anderen Paar (7721)."""
    for k, d in enumerate(dancers):
        if str(d["couple"]) in KREIS_PAARE[kreis]:
            continue
        x1, y1, w1 = now[k]
        if not any(abs(x1 - x0) <= tol and abs(y1 - y0) <= tol
                   and abs(((w1 - w0 + 540) % 360) - 180) <= 30 for x0, y0, w0 in start):
            return False
    return True


def heimplatz_cut(erg, lines, kreis_of, response):
    """Regel kreis_heimplatz fuer EINE Sequenz: die ergaenzte Fassung `erg` an der ersten
    fortgeschriebenen Zeile kuerzen, vor der ein Inaktiver nicht mehr zu Hause steht (ab dort
    gelten die woertlichen Lesarten aus `lines`). `response` = Engine-Antwort auf `erg` mit
    positions und frames. -> neue ergaenzte Fassung oder None (= gleich der woertlichen)."""
    an = response.get("animation") or {}
    if not an.get("frames"):
        return erg
    start = an["frames"][0][1]
    pos = [[[d[1], d[2], d[3]] for d in step] for step in (response.get("positions") or [])]
    for i, kr in enumerate(kreis_of):
        if not kr:
            continue
        if i > len(pos):                       # Fassung bricht vorher ab: keine Aussage
            break
        now = start if i == 0 else pos[i - 1]
        if not _zuhause(start, now, an["dancers"], kr):
            new = erg[:i] + lines[i:]
            return None if new == lines else new
    return erg


# ---- Annahmen-Runde 4: Mehrfach-Calls (David, 2026-11-13) ----
# Eine Kartenzeile mit mehreren Calls oder einem Zaehler wird als letzte Lesart in Einzel-Calls
# zerlegt: Trenner Komma, "but", " - ", "then" ("&"/"and" teilt schon zeilen_split; viele Calls
# enthalten "and"). Je Teil: Zaehler ausgeschrieben ("Ends Circulate 2" -> 2x Ends Circulate,
# "3 Times", "2 Places", "Twice", "Once"), "Square Thru On 3rd Hand X" -> Square Thru 2 | X,
# R.L.G./L.A. ausgeschrieben. Der Designator gilt weiter wie beim Komma (_comma_carry).
MEHR_TRENNER = re.compile(r"\s*,\s*|\s+but\s+|\s+-\s+|\s+then\s+", re.I)
MEHR_ZAHL = {"1": 1, "one": 1, "once": 1, "2": 2, "two": 2, "twice": 2, "double": 2,
             "3": 3, "three": 3, "4": 4, "four": 4}
MEHR_WIEDER = re.compile(r"^(.*\S)\s+(?:(\d|one|two|three|four)\s+(?:times|places?)|(once|twice|double))$", re.I)
MEHR_CIRC = re.compile(r"^(.*\bcirculate)\s+(\d)$", re.I)
MEHR_HAND = re.compile(r"^(.*\bsquare thru)\s+(?:but\s+)?on\s+(?:the\s+)?(\d)(?:st|nd|rd|th)\s+hand\b\s*(.*)$", re.I)
MEHR_ABK = [(re.compile(r"^r\.?\s?l\.?\s?g\.?$", re.I), "Right and Left Grand"),
            (re.compile(r"^l\.?\s?a\.?$", re.I), "Allemande Left")]


def _mehr_teil(p):
    p = p.strip(" .")
    for rx, rep in MEHR_ABK:
        if rx.match(p):
            return [rep]
    m = MEHR_HAND.match(p)
    if m:
        n = int(m.group(2)) - 1
        rest = [x for x in (_mehr_teil(m.group(3)) if m.group(3).strip() else [])]
        return ([f"{m.group(1)} {n}"] if n > 0 else []) + rest
    m = MEHR_WIEDER.match(p)
    if m:
        n = MEHR_ZAHL.get((m.group(2) or m.group(3)).lower())
        if n:
            return [m.group(1)] * n
    m = MEHR_CIRC.match(p)
    if m and int(m.group(2)) <= 4:
        return [m.group(1)] * int(m.group(2))
    return [p] if p else []


def _mehrfach(t):
    if MEHR_HAND.match(t.strip(" .")):                 # "... But On 3rd Hand ..." vor dem Trennen
        out = _mehr_teil(t)
        return out if out and [x.lower() for x in out] != [t.lower()] else None
    teile = []
    for x in MEHR_TRENNER.split(t):
        if not x or not x.strip():
            continue
        if teile and re.fullmatch(r"(left|right|in|out)", x.strip(), re.I):
            teile[-1] = f"{teile[-1]} {x.strip()}"     # "Tag The Line - Left" -> Tag The Line Left
        else:
            teile.append(x)
    if len(teile) > 1:
        carried = _comma_carry(", ".join(teile)) or teile
    else:
        carried = teile
    out = []
    for p in carried:
        out += _mehr_teil(p)
    if not out or [x.lower() for x in out] == [t.lower()]:
        return None
    return out


# ---- Annahmen-Runde 3: Call-Mapping der App als Rueckfall (David, 2026-11-13) ----
# Die App ordnet jeden Kartentext einem Call zu (call_text_mappings -> calls.canonical_name).
# Scheitert eine Zeile mit allen anderen Lesarten, probiert Taminations als LETZTE Lesart den
# Callnamen der App (Herkunft "app"), mit dem Designator der Zeile ("Heads Right & Left Thru" ->
# "Heads Right and Left Thru").
# Nicht genommen: Mehrfach-Calls (call_text_figures_extra) und Texte mit Bruch/Wiederholung, die
# der Callname verlieren wuerde ("Circle Left 3/4" -> "Circle Left" waere eine andere Choreo).
# Streng: nur reine Schreibvarianten. Der Callname der App ist eine Einordnung, nicht immer
# dieselbe Choreo ("Face Partner" -> Partner Tag, "Extend 3 Times" -> Extend). Deshalb muessen Text
# und Callname bis auf harmlose Woerter (APP_HARMLOS) dieselben Woerter haben. Alles andere (auch
# "Box Circulate" -> Split Circulate) ist ein Vorschlag fuer call_mapping.csv.
APP_SKIP = re.compile(r"\d+/\d+|\b(twice|double|again|once|1 1/2|one and a half)\b", re.I)
APP_STOP = {"a", "an", "the", "your", "to", "of"}
APP_HARMLOS = {"each", "side", "on", "all", "four", "eight", "join", "hand", "and", "put", "home",
               "full", "way", "across", "ocean"}
APP_WORT = {"4": "four", "8": "eight", "2": "two", "3": "three", "1": "one", "neighbour": "neighbor"}


def _app_woerter(s):
    s = s.lower().replace("&", " and ")
    s = re.sub(r"\br\.?\s?l\.?\s?g\b\.?", " right and left grand ", s)
    s = re.sub(r"\bl\.?\s?a\b\.?", " allemande left ", s)
    out = set()
    for w in re.findall(r"[a-z0-9/]+", s):
        w = APP_WORT.get(w, w)
        if len(w) > 4 and w.endswith("s") and not w.endswith("ss"):
            w = w[:-1]
        if w not in APP_STOP:
            out.add(w)
    return out


def _app_schreibvariante(text, name):
    a, b = _app_woerter(text), _app_woerter(name)
    return (b - a) <= APP_HARMLOS and (a - b) <= APP_HARMLOS


def _app_alt(orig, t, app):
    fest = APP_FEST.get(_cm.norm(orig))
    if fest:
        return list(fest) if [x.lower() for x in fest] != [t.lower()] else None
    name = app.get(orig)
    if not name:
        return None
    if APP_SKIP.search(orig) and not APP_SKIP.search(name):
        return None
    m = GROUP.match(t.strip()) or KREIS_START.match(t.strip())
    if m:
        d = t.strip()[:m.end()]
        if not name.lower().startswith(d.lower()):
            name = f"{d} {name}"
    if "app_mapping_breit" not in RULES and not _app_schreibvariante(orig, name):
        return None
    if name.lower() == t.lower():
        return None
    return [name]


# ---- Eine Sequenz vorbereiten ----
def prepare(calls, seq_type, app=None):
    """Kartenzeilen einer Sequenz -> dict wie der Pruefstand-Export (ohne Heimplatz-Pruefung).

    calls     Call-Texte der Sequenz in Reihenfolge
    seq_type  sequences.type (z. B. "Singer (Corner progression)")
    app       Kartentext -> Callname der App (song_db_sequences.read_choreo_call_names)
              oder None
    -> {"type", "n_start", "end", "orig", "src", "end_src", "lines", "zweit", "kreis_of"}
       src      je gesendeter Zeile der Index der Kartenzeile (None = aus der Startformation)
       end_src  Kartenzeile, aus der der Aufloese-Call stammt (None = ergaenzt bzw. keiner)
       zweit    ergaenzte Fassung (R8-Reihenfolge) oder None
    """
    tagged = [CardLine(c, i) if isinstance(c, str) else c for i, c in enumerate(calls)]
    calls = list(tagged)
    if "typ_start" in RULES:
        calls = typ_start(seq_type, calls)
    body, n_start, end, erg = map_sequence(calls, app)
    if "singer_ende" in RULES:
        body, end, erg = singer_ende(seq_type, body, end, erg)
    src = [getattr(o, "idx", None) for o, _ in body]
    end_src = None
    if end:
        # Der Aufloese-Call (bzw. Swing + Promenade beim Singer) ersetzt die letzte Kartenzeile
        # hinter der letzten gesendeten Zeile, die kein reiner Formations-Hinweis ist.
        last = max([s for s in src if s is not None], default=-1)
        tail = [j for j in range(last + 1, len(tagged))
                if tagged[j] and tagged[j].strip() and not re.fullmatch(r"\(.*\)", tagged[j].strip())]
        end_src = tail[-1] if tail else None
    return {"type": seq_type or "", "n_start": n_start, "end": end,
            "orig": [str(o) for o, _ in body], "src": src, "end_src": end_src,
            "lines": [s for _, s in body],
            "zweit": [s for _, s in erg[0]] if erg else None,
            "kreis_of": erg[1] if erg else None}


def heimplatz_request(prep):
    """Engine-Anfrage fuer die Heimplatz-Pruefung, None wenn keine ergaenzte Fassung da ist."""
    if not prep.get("zweit"):
        return None
    return {"lines": prep["zweit"], "positions": True, "frames": 1e9}


def finish(prep, heimplatz_response=None):
    """Heimplatz-Pruefung anwenden und Fassungen ordnen (kreis_geprueft_zuerst).
    -> (lines, zweit, zweit_art); zweit_art = "woertlich" | "ergaenzt" | None.
    Ohne Antwort (Engine nicht verfuegbar) bleibt die ergaenzte Fassung ungekuerzt."""
    lines, zweit = prep["lines"], prep.get("zweit")
    if zweit and "kreis_heimplatz" in RULES and heimplatz_response is not None:
        zweit = heimplatz_cut(zweit, lines, prep["kreis_of"], heimplatz_response)
    if not zweit:
        return lines, None, None
    if "kreis_geprueft_zuerst" in RULES and "kreis_heimplatz" in RULES:
        return zweit, lines, "woertlich"
    return lines, zweit, "ergaenzt"
