"""Empfehlungsregel: welcher Song als naechstes, ohne Qt (intern#141).

Empfehlungs-Score = Qualitaet x Tage seit zuletzt gespielt. Nie gespielte Songs
zaehlen ab dem Erstaufnahme-Datum (INI playlist/start_date).

Gemeinsame Quelle fuer die Songliste (`rank`), die Shortcode-Auswahl (`pick`),
den Abendplaner (`score`) und die Score-Anzeige (`display_score`). Die Kopien
verhalten sich bewusst weiter wie vorher; was sie unterscheidet, steht in den
Parametern (`tiebreak_modes`, `added_fallback`, `rng`), nicht in der Logik.
Nur Sortierung und Score, keine Filter.
"""
import math
import random
from datetime import date

QT_FREE = True

# Zahlenwerte stehen als sort/default_mode in der INI: nicht aendern.
SORT_ALPHA = 0
SORT_QUALITY = 1
SORT_LAST_PLAYED = 2
SORT_RECOMMENDATION = 3
SORT_DATE_ADDED = 4
SORT_RANDOM = 5            # BL-170: reiner Zufall (Gleichverteilung)
SORT_WEIGHTED_RANDOM = 6   # BL-170: gewichteter Zufall (Roulette-Wheel)

# BL-170: Ersatz-Qualitaet fuer unbewertete Songs beim gewichteten Zufall.
# quality 0 = "noch nicht bewertet", nicht "schlecht".
UNRATED_IN_RANDOM = 5

# Modi, in denen die Songliste einen Zufalls-Tiebreaker nutzt (BL-113). Bei
# "zuletzt gespielt" bewusst nicht; die Shortcode-Auswahl wuerfelt dort trotzdem
# (siehe pick, Abweichung A5).
LIST_TIEBREAK_MODES = frozenset(
    {SORT_QUALITY, SORT_RECOMMENDATION, SORT_DATE_ADDED})


def days_since(last_played, today, fallback_date) -> int:
    """Tage seit dem letzten Spielen.

    last_played: ISO-Zeitstempel oder None. Nie gespielt oder nicht lesbar ->
    gemessen ab fallback_date (Erstaufnahme-Grenze), NICHT ab heute.
    """
    if last_played:
        try:
            return (today - date.fromisoformat(last_played[:10])).days
        except (ValueError, TypeError):
            pass
    return (today - fallback_date).days


def base_score(quality, days) -> int:
    """Qualitaet x Tage. Unbewertet (0) ergibt 0, ein Zukunftsdatum negativ."""
    return quality * days


def display_score(quality, days) -> int:
    """Der in der Songliste angezeigte Score (Ganzzahl)."""
    return int(base_score(quality, days))


def song_score(song, last_played_map, today, fallback_date) -> int:
    """Angezeigter Score eines Songs, mit denselben Tagen wie die Sortierung."""
    return display_score(song.quality, days_since(
        last_played_map.get(song.id), today, fallback_date))


def err_match(err, target_err) -> float:
    """Passung des Song-ERR zum Ziel-ERR: 1.0 genau, 0.5 eins daneben, ...
    ERR 0 heisst "nicht gepflegt" und zaehlt niedrig (0.25)."""
    if err == 0:
        return 0.25
    return 1.0 / (abs(err - target_err) + 1)


def score(quality, days, err, target_err) -> float:
    """Score des Abendplaners: Qualitaet x ganze Tage x ERR-Passung."""
    return quality * int(days) * err_match(err, target_err)


def weight(quality, days) -> int:
    """Gewicht im gewichteten Zufall: Score + 1, mindestens 1.

    Unbewertete Songs zaehlen hier (und nur hier) als UNRATED_IN_RANDOM, sonst
    kaemen sie nie dran und koennten nie bewertet werden. Ein heute gespielter
    Song behaelt Gewicht 1; max() faengt ein Zukunftsdatum ab.
    """
    q = quality if quality > 0 else UNRATED_IN_RANDOM
    return max(1, q * days + 1)


def weighted_order(songs, weight_of, draw_of):
    """Gewichtete Zufalls-Reihenfolge (BL-170, Roulette-Wheel-Selection).

    Verfahren nach Efraimidis/Spirakis: zu jedem Song mit Gewicht w wird aus
    einer Gleichverteilung u in (0,1) der Schluessel -ln(u)/w gebildet;
    aufsteigend sortiert entspricht das dem wiederholten Ziehen ohne
    Zuruecklegen, in O(n log n).

    weight_of: Callable(song) -> Gewicht > 0.
    draw_of: Callable(song_id) -> Zufallszahl u aus (0,1). Ein Cache des
    Aufrufers haelt die Reihenfolge stabil, solange nur gefiltert wird.
    """
    keys = [(-math.log(draw_of(s.id)) / weight_of(s), s) for s in songs]
    keys.sort(key=lambda x: x[0])
    return [s for _, s in keys]


def _added_ordinal(song, fallback_ordinal):
    """Einfuegedatum als Ordinalzahl; ohne gueltiges Datum das Erbe-Datum."""
    try:
        return date.fromisoformat(song.date_added[:10]).toordinal()
    except (ValueError, TypeError):
        return fallback_ordinal


def rank(songs, mode, *, last_played_map, today, fallback_date,
         added_fallback=None, tiebreak=None, draw=None,
         tiebreak_modes=LIST_TIEBREAK_MODES):
    """Sortiert die Songs nach `mode`; Ergebnis ist eine neue Liste.

    today: einmal pro Aufruf vom Aufrufer (testbar, kein date.today() je Song).
    fallback_date: Erstaufnahme-Datum fuer "nie gespielt".
    added_fallback: Erbe-Datum fuer Songs ohne date_added (Standard: fallback_date).
    tiebreak: Callable(song_id) -> float, entscheidet Gleichstaende in den
        `tiebreak_modes`; None = kein Tiebreak (Reihenfolge der Eingabe).
    draw: Callable(song_id) -> u aus (0,1) fuer die beiden Zufallsmodi.
    """
    def days(s):
        return days_since(last_played_map.get(s.id), today, fallback_date)

    tb = tiebreak if (tiebreak is not None and mode in tiebreak_modes) \
        else (lambda _sid: 0)

    if mode == SORT_ALPHA:
        return sorted(songs, key=lambda s: (s.title or s.filename).lower())
    if mode == SORT_QUALITY:
        return sorted(songs, key=lambda s: (-s.quality, tb(s.id)))
    if mode == SORT_LAST_PLAYED:
        return sorted(songs, key=lambda s: (-days(s), tb(s.id)))
    if mode == SORT_RECOMMENDATION:
        return sorted(songs, key=lambda s: (-base_score(s.quality, days(s)),
                                            tb(s.id)))
    if mode == SORT_DATE_ADDED:
        fb = (added_fallback or fallback_date).toordinal()
        # Neueste Zugaenge zuerst.
        return sorted(songs, key=lambda s: (-_added_ordinal(s, fb), tb(s.id)))
    if mode == SORT_RANDOM:
        return sorted(songs, key=lambda s: draw(s.id))
    if mode == SORT_WEIGHTED_RANDOM:
        return weighted_order(songs, lambda s: weight(s.quality, days(s)), draw)
    return list(songs)


def pick(songs, mode, *, last_played_map, today, fallback_date,
         added_fallback=None, rng=random):
    """Waehlt EINEN Song nach `mode` (Shortcode-Auswahl), O(n) ohne Sortierung.

    Gleichstaende entscheidet ein frisch gewuerfelter Wert aus `rng.random()`,
    in allen Modi ausser Alphabetisch und Zufall, auch bei "zuletzt gespielt".
    Pro Song wird einmal in Listenreihenfolge gewuerfelt. Die Zufallsmodi
    ziehen bei jedem Aufruf neu (kein Cache). songs darf nicht leer sein.
    """
    def days(s):
        return days_since(last_played_map.get(s.id), today, fallback_date)

    if mode == SORT_ALPHA:
        return min(songs, key=lambda s: (s.title or s.filename).lower())
    if mode == SORT_RANDOM:
        return rng.choice(songs)
    if mode == SORT_WEIGHTED_RANDOM:
        # Erster Eintrag von weighted_order, ohne zu sortieren.
        return min(((-math.log(rng.random() or 1e-12)
                     / weight(s.quality, days(s)), i, s)
                    for i, s in enumerate(songs)),
                   key=lambda t: t[:2])[2]
    if mode == SORT_QUALITY:
        return max(songs, key=lambda s: (s.quality, rng.random()))
    if mode == SORT_LAST_PLAYED:
        return max(songs, key=lambda s: (days(s), rng.random()))
    if mode == SORT_DATE_ADDED:
        fb = (added_fallback or fallback_date).toordinal()
        return max(songs, key=lambda s: (_added_ordinal(s, fb), rng.random()))
    return max(songs, key=lambda s: (base_score(s.quality, days(s)),
                                     rng.random()))
