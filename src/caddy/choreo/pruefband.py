"""Endkontrolle einer Sequenz: Pruefband + Taminations-Aufloesungsprobe (intern#163, #247).

Portiert aus dem Pruefstand `choreo-engines/eval/tam_pruefband.py` (Stand 1e69832).

Zwei Stufen (Davids Abnahmekriterien):
  Stufe 1  Taminations nimmt die Sequenz vollstaendig an (kein Abbruch).
  Stufe 2  Die Sequenz geht korrekt aus: Pruefband je Sequenz-Typ gruen
           (Zielpaare Nachbarn in der Reihenfolge rund um die Mitte, Paarung Boy 1 im
           Uhrzeigersinn vor Boy 2; bei gleichen Winkeln Naehe bzw. nach AL/RLG "schauen sich an").

Zwei Pruefer:
- Pruefer 1: Pruefband (Feld "band").
- Pruefer 2: Taminations' eigene Aufloesungspruefung (promenade_home.dart) als Probe am
  Koerper-Ende (Feld "tam", Probe-Call in "tam_probe").
- urteil: Band rot -> rot; Band gruen UND Taminations aufgeloest -> gruen;
  Band gruen, Taminations nein -> strittig (geht an den Caller); nur_band_gruen = Probe ohne Aussage.

Ablauf je Sequenz:
- Singer: Pruefung am Ende des Koerpers (vor dem Promenade; Taminations fuehrt bei
  "Promenade Home" zum Originalpartner). Swing + Promenade wird nur fuer die Beats mitgetanzt.
- Sonst mit Aufloese-Call: Koerper + Aufloese-Call tanzen; klappt das, Pruefung danach
  (nach AL/RLG im Modus "schauen sich an"), sonst vor dem Aufloese-Call.
- Ohne Aufloese-Call (z. B. Zero Line -> Zero Line): Pruefung am Ende.
- Zweiter Durchgang: Endet die erste Fassung nicht gruen und gibt es eine zweite Fassung
  (mapping.finish), wird diese gemessen und genommen, wenn sie gruen endet.

`run` ist eine Funktion request -> response (engine.TamEngine.run); sie blockiert.
"""
import math

QT_FREE = True

# Praefix des Sequenz-Typs (klein) -> Zielpaare am Ende
TARGETS = [
    ("singer (corner progression)", [("1B", "4G"), ("1G", "2B")]),
    ("zero line ➔ zero line", [("1B", "1G"), ("2B", "2G")]),
    ("zero line ➔ resolve", [("1B", "1G"), ("2B", "2G")]),
    ("static set ➔ zero box", [("1B", "4G"), ("2B", "1G")]),
    ("zero box ➔ resolve", [("1B", "1G"), ("2B", "2G")]),
    ("static set ➔ resolve", [("1B", "1G"), ("2B", "2G")]),
    # 2026-11-11 (David): weitere Typen; "Stir the bucket" und "Two Couples" ohne Pruefband
    ("static set ➔ zero line", [("1B", "1G"), ("2B", "2G")]),
    ("zero box ➔ zero box", [("1B", "4G"), ("2B", "1G")]),
    ("zero line ➔ zero box", [("1B", "4G"), ("2B", "1G")]),
    ("zero box ➔ zero line", [("1B", "1G"), ("2B", "2G")]),
    ("zero (facing couples)", [("1B", "4G"), ("2B", "1G")]),
    ("zero (eight chain thru)", [("1B", "4G"), ("2B", "1G")]),
    ("zero (parallel waves)", [("1B", "4G"), ("2B", "1G")]),
    ("zero (facing lines)", [("1B", "1G"), ("2B", "2G")]),
    ("singer (r-h lady progression)", [("1B", "2G"), ("2B", "3G")]),
    ("singing break", [("1B", "1G"), ("2B", "2G")]),
]
IGNORED = ("stir the bucket", "two couples")      # David: nicht bewerten

BLICK_WELLE = True      # gegenlaeufig nebeneinander (Welle, Hand in Hand) gilt als Paar
BLICK_KULANZ = 5        # Grad Kulanz auf alle Grenzen der Blickregel (gegen Rundungsfehler)


def targets_for(seq_type):
    t = (seq_type or "").lower()
    return next((pairs for pre, pairs in TARGETS if t.startswith(pre)), None)


def wrap(d):
    return ((d + 540) % 360) - 180


def end_check(dancers, pos, pairs, facing_mode, info=None):
    """pos: je Taenzer [x, y, winkel_grad] (Reihenfolge wie dancers). Wie endCheck() im Pruefstand.
    info (dict, optional) bekommt "kriterium": ring | naehe | schauen und "blick".
    -> "gruen" | "nicht_zusammen" | "reihenfolge" | "blick" | None (Paare nicht gefunden)."""
    def idx(t):
        return next((k for k, d in enumerate(dancers)
                     if str(d["couple"]) == t[0] and bool(d["boy"]) == (t[1] == "B")), -1)
    bp = [(idx(a), idx(b)) for a, b in pairs]
    if any(a < 0 or b < 0 for a, b in bp) or len(bp) != 2:
        return None

    def at(i):                                            # Bildschirm-Koordinaten
        return (-pos[i][1], -pos[i][0])

    def dist(i, j):
        return math.hypot(at(i)[0] - at(j)[0], at(i)[1] - at(j)[1])

    def raw(i, j):
        return math.hypot(pos[i][0] - pos[j][0], pos[i][1] - pos[j][1])

    def other(i, k):
        return k != i and bool(dancers[k]["boy"]) != bool(dancers[i]["boy"])

    def is_nearest(i, j):
        bd = min((dist(i, k) for k in range(len(dancers)) if other(i, k)), default=math.inf)
        return dist(i, j) <= bd + 0.05

    def blick_zu(i, j):                                   # Winkel zwischen Blick und Zielperson
        dx, dy = pos[j][0] - pos[i][0], pos[j][1] - pos[i][1]
        return abs(wrap(math.degrees(math.atan2(dy, dx)) - pos[i][2]))

    def looks_at(i, j):
        return blick_zu(i, j) <= 60

    def sees_first(i, j):
        if not looks_at(i, j):
            return False
        bd = min((raw(i, k) for k in range(len(dancers)) if other(i, k) and looks_at(i, k)),
                 default=math.inf)
        return raw(i, j) <= bd + 0.05

    # Ring-Kriterium (2026-11-11, Schleife 3): Taenzer nach Winkel um die Mitte sortieren, die
    # Zielpaare muessen Nachbarn sein. Naehe allein irrt am Sequenzende (Corner steht oft weiter
    # weg als ein anderer Taenzer). Bei gleichen Winkeln (z. B. Tidal Wave durch die Mitte) ist
    # die Reihenfolge unklar -> bisheriges Kriterium (Naehe bzw. nach AL/RLG "schauen sich an").
    angs = [math.atan2(p[1], p[0]) for p in pos]
    rounded = [round(a, 3) for a in angs]
    ties = len(set(rounded)) < len(rounded) or any(math.hypot(p[0], p[1]) < 0.01 for p in pos)
    if info is not None:
        info["kriterium"] = "ring" if not ties else ("schauen" if facing_mode else "naehe")
    if not ties:
        order = sorted(range(len(pos)), key=lambda k: angs[k])
        n = len(order)
        near = all((order.index(a) - order.index(b)) % n in (1, n - 1) for a, b in bp)
    else:
        near = all((sees_first(a, b) and sees_first(b, a)) if facing_mode
                   else (is_nearest(a, b) and is_nearest(b, a)) for a, b in bp)
    mids = [((at(a)[0] + at(b)[0]) / 2, (at(a)[1] + at(b)[1]) / 2) for a, b in bp]

    def ang(m):
        return math.degrees(math.atan2(m[1], m[0]))
    order = wrap(ang(mids[0]) - ang(mids[1])) > 0
    # Blickrichtung (2026-11-13, David): Zielpaare schauen sich an, schauen in dieselbe Richtung
    # (Couple, Promenade) oder stehen Hand in Hand gegenlaeufig (Welle). Ruecken an Ruecken oder quer:
    # kein Swing moeglich (10705). Alle Grenzen mit BLICK_KULANZ Grad Kulanz gegen Rundungsfehler.
    k = BLICK_KULANZ

    def weg(a, b):                                        # Ruecken an Ruecken
        return blick_zu(a, b) >= 120 + k and blick_zu(b, a) >= 120 + k

    def blick_ok(a, b):
        if blick_zu(a, b) <= 60 + k and blick_zu(b, a) <= 60 + k:
            return True                                   # schauen sich an
        dw = abs(wrap(pos[a][2] - pos[b][2]))
        if dw <= 45 + k:
            return True                                   # gleiche Richtung (Couple, Promenade)
        if facing_mode:
            # nach Allemande Left / RLG endet die Taminations-Animation mitten in der Drehung,
            # Partner stehen dann quer (4307, von David als korrekt beurteilt): nur Ruecken an Ruecken rot
            return not weg(a, b)
        # gegenlaeufig nebeneinander (Welle, Hand in Hand)
        return BLICK_WELLE and dw >= 135 - k and not weg(a, b)
    blick = all(blick_ok(a, b) for a, b in bp)
    if info is not None:
        info["blick"] = blick
    if near and order and blick:
        return "gruen"
    return "nicht_zusammen" if not near else ("reihenfolge" if not order else "blick")


def final_pos(r):
    """Endstellung aus 'positions' (pro Call [nummer, x, y, winkel]) -> [[x, y, w], ...]"""
    if not r.get("positions"):
        return None
    return [[d[1], d[2], d[3]] for d in r["positions"][-1]]


#   Zweiter Pruefer (2026-11-13): Taminations' eigene Aufloesungspruefung in promenade_home.dart.
#   Je Paar (Partner / Corner / Right Hand Girl) muss der Mittelpunkt in einem eigenen Quadranten
#   stehen, die Paare 1-4 in Sequenz; sonst bricht der Call ab. Die Probe laeuft immer auf dem
#   Koerper-Ende (vor dem Aufloese-Call) und nimmt die Paarung, die dort stimmen muss: vor Allemande
#   Left die Corner, vor Right and Left Grand / Promenade Home die Partner, ohne Aufloese-Call die
#   Zielpaare des Typs, beim Singer die neue Partnerin. Die AL/RLG-Warnung von Taminations
#   (checkResolution) ist dafuer zu schwach; sie wird nur als "aufl_warnung" mitgeschrieben.
PROMENADE = {
    (("1B", "1G"), ("2B", "2G")): "Promenade Home",
    (("1B", "4G"), ("2B", "1G")): "Promenade Corner",
    (("1B", "2G"), ("2B", "3G")): "Promenade Your Right Hand Girl",
}
PROBE_VOR_AUFL = {"allemande left": "Promenade Corner",
                  "right and left grand": "Promenade Home",
                  "promenade home": "Promenade Home"}
NICHT_AUFGELOEST = ("not resolved", "not positioned properly")
AUFL_CALLS = ("allemande left", "right and left grand", "dixie grand")


def probe_call(seq_type, end, pairs):
    """Promenade-Variante fuer die Probe am Koerper-Ende."""
    singer = (seq_type or "").lower().startswith("singer")
    if end and not singer:
        return PROBE_VOR_AUFL.get(end.lower())
    norm = tuple(sorted(tuple(sorted(p, key=lambda t: t[1] != "B")) for p in pairs))
    return PROMENADE.get(norm)


def tam_judge(run, lines, call):
    """Promenade-Probe auf der Stellung nach `lines`: True = aufgeloest, False = nicht,
    None = Probe nicht aussagekraeftig (anderer Fehler)."""
    if not call:
        return None, ""
    r = run({"lines": lines + [call]})
    if r["ok"]:
        return True, call
    err = (r.get("error") or "").lower()
    return (False if any(t in err for t in NICHT_AUFGELOEST) else None), call


def endurteil(band, tam):
    """Gesamturteil aus Pruefband und Taminations-Pruefer (Regel seit 2026-11-13, David):
    - Band rot -> rot, egal was Taminations sagt (die Promenade-Probe ist zu grosszuegig).
    - Band gruen UND Taminations aufgeloest -> gruen (Zweitmeinung als Bedingung).
    - Band gruen, Taminations nein -> strittig (an den Caller).
    - Band gruen, keine Aussage von Taminations -> nur_band_gruen."""
    if band not in ("gruen", "nicht_zusammen", "reihenfolge", "blick"):
        return band
    if band != "gruen":
        return "rot"
    if tam is None:
        return "nur_band_gruen"
    return "gruen" if tam else "strittig"


def measure(run, seq_type, end, n_start, lines, frames=None):
    """Eine Fassung tanzen und pruefen. frames: Beat-Schritt fuer die Animation (None = ohne).
    -> dict mit stufe1, band, urteil, beats je Zeile, Engine-Antwort ("engine")."""
    pairs = targets_for(seq_type)
    seq_type = seq_type or ""
    q = {"lines": lines, "positions": True, "frames": frames if frames else 1e9}
    r = run({**q, "end": end})
    res = {"stufe1": r["ok"], "band": None, "resolved": None, "fail_pos": r["fail_pos"],
           "error": r.get("error") or "", "pruefpunkt": None, "kriterium": None, "tam": None,
           "tam_probe": "", "aufl_warnung": None, "urteil": None,
           "line_beats": list(r.get("beats") or []), "beats_koerper": None, "beats_ende": None,
           "beats": None, "engine": r}
    if not r["ok"] or not pairs:
        res["band"] = res["urteil"] = None if not r["ok"] else "kein_band"
        return res
    dancers = (r.get("animation") or {}).get("dancers", [])
    pos, facing = final_pos(r), False
    singer = seq_type.lower().startswith("singer")
    # Singing Calls: endet die Sequenz mit "Swing Corner / Right Hand Girl and Promenade"
    # (Regel singer_ende), wird das mitgetanzt; geprueft wird am Koerper-Ende.
    singer_swing = singer and bool(end) and end.lower().startswith("swing")
    n0 = n_start or 0
    res["beats_koerper"] = round(sum(r["beats"][n0:len(lines)]), 1)
    res["pruefpunkt"] = "koerper_ende" if singer else "ende"
    if singer_swing:
        # Nur fuer die Beats mittanzen: Nach "Swing Corner and Promenade" stellt Taminations die
        # Paare selbst an die Heimplaetze, das Band waere dann fast immer gruen (2109).
        r2 = run({"lines": lines + [end]})
        res["ende_ok"] = bool(r2["ok"])
        if r2["ok"]:
            res["beats_ende"] = round(r2["beats"][len(lines)], 1)
    elif end and not singer:
        r2 = run({**q, "lines": lines + [end]})
        if r2["ok"] and r2.get("positions"):
            pos, res["resolved"] = final_pos(r2), True
            res["pruefpunkt"] = "nach_aufl"
            res["beats_ende"] = round(r2["beats"][len(lines)], 1)
            facing = end.lower() in ("allemande left", "right and left grand")
            if end.lower() in AUFL_CALLS:
                last = [w for w in r2.get("warnings", []) if w.startswith(f"{len(lines)}:")]
                res["aufl_warnung"] = any("not resolved" in w for w in last)
        else:
            res["resolved"] = False
            res["pruefpunkt"] = "vor_aufl"
    res["beats"] = round(res["beats_koerper"] + (res["beats_ende"] or 0), 1)
    info = {}
    res["band"] = end_check(dancers, pos, pairs, facing, info) if pos else None
    res["kriterium"] = info.get("kriterium")
    # Taminations-Pruefer immer auf der Stellung vor dem Aufloese-Call (Koerper-Ende)
    res["tam"], res["tam_probe"] = tam_judge(run, lines, probe_call(seq_type, end, pairs))
    res["urteil"] = endurteil(res["band"], res["tam"])
    return res


ERGAENZT = ("kreis", "kontext")


def lesart(lines, alt_used):
    """woertlich | rueckfall | fortgeschrieben | app | mehrfach: welche Art Lesart getanzt wurde
    (ergaenzter Designator an erster Stelle = Fortschreibung, spaeter = Rueckfall)."""
    def used_kind(i, l):
        if not isinstance(l, dict) or i >= len(alt_used or []):
            return None, None
        u, k = alt_used[i], l.get("kinds") or []
        return (u, k[u]) if u is not None and 0 <= u < len(k) else (u, None)
    kinds = [used_kind(i, l) for i, l in enumerate(lines)]
    if any(k == "app" for _, k in kinds):
        return "app"               # Annahmen-Runde 3: Callname aus dem App-Mapping getanzt
    if any(k == "mehrfach" for _, k in kinds):
        return "mehrfach"          # Annahmen-Runde 4: Zeile in Einzel-Calls zerlegt
    res = "woertlich"
    for u, k in kinds:
        if k in ERGAENZT:
            if u == 0:
                return "fortgeschrieben"
            res = "rueckfall"
    return res


def analyse(run, seq_type, end, n_start, lines, zweit=None, zweit_art=None, frames=None):
    """Endkontrolle mit zweitem Durchgang. -> Ergebnis von measure() plus
    "lesart", "fassung" ("erste" | "zweite") und "lines" (die gemessene Fassung)."""
    res = measure(run, seq_type, end, n_start, lines, frames)
    res["lesart"] = lesart(lines, res["engine"].get("alt_used")) if res["stufe1"] else None
    res["fassung"], res["lines"] = "erste", lines
    if zweit and res["urteil"] != "gruen":
        res2 = measure(run, seq_type, end, n_start, zweit, frames)
        if res2["urteil"] == "gruen":
            erst = res["urteil"] if res["stufe1"] else "abbruch"
            res2["lesart"] = "woertlich_2" if zweit_art == "woertlich" else "ergaenzt"
            res2["erste_fassung_urteil"] = erst
            res2["fassung"], res2["lines"] = "zweite", zweit
            return res2
    return res
