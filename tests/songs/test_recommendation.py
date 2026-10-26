"""Empfehlungsregel `caddy.songs.recommendation`, ohne Qt (intern#141).

Dieselben Daten und Erwartungen wie die Charakterisierung der Ist-Kopien
(test_empfehlung_charakterisierung.py): das Modul muss deren Ergebnisse
reproduzieren.
"""
import itertools
import math
from datetime import date, timedelta
from types import SimpleNamespace

import pytest

from caddy.songs import recommendation as rec

HEUTE = date(2026, 10, 20)
START = HEUTE - timedelta(days=100)


def _vor(tage):
    return (HEUTE - timedelta(days=tage)).isoformat()


LP = {1: _vor(10), 2: _vor(20), 3: _vor(30), 5: _vor(0), 6: _vor(-3),
      7: "kaputt", 8: _vor(20)}
QUAL = {1: 5, 2: 3, 3: 0, 4: 4, 5: 5, 6: 2, 7: 3, 8: 3}
ADDED = {1: "2026-01-05", 2: "2026-03-01", 3: "", 4: "2026-03-01",
         5: "kaputt", 6: "2025-12-31", 7: "", 8: "2026-02-01"}
TB = {1: .8, 2: .9, 3: .5, 4: .1, 5: .7, 6: .2, 7: .3, 8: .1}
DRAW = {1: .5, 2: .9, 3: .2, 4: .7, 5: .3, 6: .8, 7: .6, 8: .4}
SONGS = [SimpleNamespace(id=i, title=f"S{i}", filename=f"s{i}.mp3",
                         quality=QUAL[i], date_added=ADDED[i])
         for i in range(1, 9)]


def _rank(mode, tb=False, **kw):
    out = rec.rank(SONGS, mode, last_played_map=LP, today=HEUTE,
                   fallback_date=kw.pop("fallback_date", START),
                   tiebreak=TB.get if tb else None, draw=DRAW.get, **kw)
    return [s.id for s in out]


def test_tage_seit_zuletzt_gespielt():
    assert rec.days_since(_vor(10), HEUTE, START) == 10
    assert rec.days_since(_vor(4) + " 23:59:59", HEUTE, START) == 4
    assert rec.days_since(_vor(-3), HEUTE, START) == -3
    assert rec.days_since(None, HEUTE, START) == 100
    assert rec.days_since("kaputt", HEUTE, START) == 100
    assert rec.days_since(None, HEUTE, HEUTE) == 0


def test_anzeige_score():
    assert rec.display_score(5, 10) == 50
    assert rec.display_score(0, 30) == 0
    assert rec.display_score(2, -3) == -6


def test_song_score_nutzt_dieselben_tage_wie_die_sortierung():
    by_id = {s.id: s for s in SONGS}
    erwartet = {1: 50, 3: 0, 4: 400, 6: -6, 7: 300}
    assert {i: rec.song_score(by_id[i], LP, HEUTE, START)
            for i in erwartet} == erwartet


def test_planner_score_und_err_passung():
    assert rec.score(4, 10, 5, 5) == 40.0
    assert rec.score(4, 10, 4, 5) == 20.0
    assert rec.score(4, 10, 7, 5) == pytest.approx(40 / 3)
    assert rec.score(4, 10, 0, 5) == 10.0
    assert rec.score(4, 10.9, 5, 5) == 40.0
    assert rec.score(4, 0, 5, 5) == 0.0
    assert rec.err_match(5, 5) == 1.0


@pytest.mark.parametrize("quality, days, erwartet", [
    (3, 20, 61), (0, 30, 151), (5, 0, 1), (2, -3, 1), (4, 100, 401)])
def test_gewicht_im_zufall(quality, days, erwartet):
    assert rec.weight(quality, days) == erwartet


@pytest.mark.parametrize("mode, tb, erwartet", [
    (rec.SORT_ALPHA, False, [1, 2, 3, 4, 5, 6, 7, 8]),
    (rec.SORT_QUALITY, False, [1, 5, 4, 2, 7, 8, 6, 3]),
    (rec.SORT_QUALITY, True, [5, 1, 4, 8, 7, 2, 6, 3]),
    (rec.SORT_LAST_PLAYED, False, [4, 7, 3, 2, 8, 1, 5, 6]),
    (rec.SORT_LAST_PLAYED, True, [4, 7, 3, 2, 8, 1, 5, 6]),
    (rec.SORT_RECOMMENDATION, False, [4, 7, 2, 8, 1, 3, 5, 6]),
    (rec.SORT_RECOMMENDATION, True, [4, 7, 8, 2, 1, 3, 5, 6]),
    (rec.SORT_RANDOM, True, [3, 5, 8, 1, 7, 4, 6, 2]),
    (rec.SORT_WEIGHTED_RANDOM, False, [4, 7, 2, 3, 1, 8, 6, 5]),
])
def test_rank_reproduziert_die_songliste(mode, tb, erwartet):
    assert _rank(mode, tb) == erwartet


def test_rank_einfuegedatum_und_erbe():
    assert _rank(rec.SORT_DATE_ADDED, added_fallback=date(2026, 2, 15)) == \
        [2, 4, 3, 5, 7, 8, 1, 6]
    assert _rank(rec.SORT_DATE_ADDED, True, added_fallback=date(2026, 2, 15)) \
        == [4, 2, 7, 3, 5, 8, 1, 6]
    # ohne added_fallback erbt das Startdatum
    assert _rank(rec.SORT_DATE_ADDED, fallback_date=date(2026, 1, 20)) == \
        [2, 4, 8, 3, 5, 7, 1, 6]


def test_rank_tiebreak_modes_machen_last_played_waehlbar():
    ids = [s.id for s in rec.rank(
        SONGS, rec.SORT_LAST_PLAYED, last_played_map=LP, today=HEUTE,
        fallback_date=START, tiebreak=TB.get,
        tiebreak_modes=rec.LIST_TIEBREAK_MODES | {rec.SORT_LAST_PLAYED})]
    assert ids == [4, 7, 3, 8, 2, 1, 5, 6]


def test_rank_laesst_die_eingabe_unveraendert():
    vorher = list(SONGS)
    _rank(rec.SORT_QUALITY, True)
    assert SONGS == vorher


class _Rng:
    """random-Ersatz: feste Folge fuer random(), choice nimmt die letzte Stelle."""

    def __init__(self, draws=()):
        self._it = itertools.chain(draws, itertools.repeat(0.5))

    def random(self):
        return next(self._it)

    def choice(self, seq):
        return seq[-1]


def _pick(mode, draws=(), songs=SONGS, **kw):
    return rec.pick(songs, mode, last_played_map=LP, today=HEUTE,
                    fallback_date=kw.pop("fallback_date", START),
                    rng=_Rng(draws), **kw).id


def test_pick_ohne_zufall_und_hoechster_score():
    assert _pick(rec.SORT_ALPHA) == 1
    assert _pick(rec.SORT_RECOMMENDATION) == 4
    assert _pick(rec.SORT_RANDOM) == 8


def test_pick_gleichstand_entscheidet_der_frische_zufall():
    zwei = [s for s in SONGS if s.id in (2, 8)]
    assert _pick(rec.SORT_RECOMMENDATION, [.2, .9], songs=zwei) == 8
    assert _pick(rec.SORT_RECOMMENDATION, [.9, .2], songs=zwei) == 2


def test_pick_zuletzt_gespielt_wuerfelt_auch():
    assert _pick(rec.SORT_LAST_PLAYED, [0, 0, 0, .1, 0, 0, .9, 0]) == 7
    assert _pick(rec.SORT_LAST_PLAYED, [0, 0, 0, .9, 0, 0, .1, 0]) == 4


def test_pick_qualitaet_und_einfuegedatum():
    assert _pick(rec.SORT_QUALITY, [.9, 0, 0, 0, .1, 0, 0, 0]) == 1
    assert _pick(rec.SORT_QUALITY, [.1, 0, 0, 0, .9, 0, 0, 0]) == 5
    start = date(2026, 1, 20)
    assert _pick(rec.SORT_DATE_ADDED, [0, .9, 0, .1, 0, 0, 0, 0],
                 fallback_date=start) == 2


def test_pick_gewichtet_entspricht_dem_ersten_der_gewichteten_reihenfolge():
    for draws in ([.5] * 8, [.5, .5, .999, .9, .5, .5, .5, .5],
                  [.1, .2, .3, .4, .5, .6, .7, .8]):
        gezogen = dict(zip(range(1, 9), draws))
        erster = rec.weighted_order(
            SONGS,
            lambda s: rec.weight(
                s.quality, rec.days_since(LP.get(s.id), HEUTE, START)),
            gezogen.get)[0].id
        assert _pick(rec.SORT_WEIGHTED_RANDOM, draws) == erster


def test_gewichtete_reihenfolge_folgt_der_schluesselformel():
    w = {s.id: 1 + s.id for s in SONGS}
    out = rec.weighted_order(SONGS, lambda s: w[s.id], DRAW.get)
    keys = {i: -math.log(DRAW[i]) / w[i] for i in w}
    assert [s.id for s in out] == sorted(keys, key=keys.get)


def test_sortmodus_zahlen_sind_die_ini_werte():
    assert [rec.SORT_ALPHA, rec.SORT_QUALITY, rec.SORT_LAST_PLAYED,
            rec.SORT_RECOMMENDATION, rec.SORT_DATE_ADDED, rec.SORT_RANDOM,
            rec.SORT_WEIGHTED_RANDOM] == [0, 1, 2, 3, 4, 5, 6]


def test_gewicht_qualitaet_eins_zaehlt_als_eins():
    assert rec.weight(1, 10) == 11
    assert rec.weight(0, 10) == rec.UNRATED_IN_RANDOM * 10 + 1


def test_einfuegedatum_mit_uhrzeit_wird_gelesen():
    s = SimpleNamespace(id=1, title="a", filename="a", quality=1,
                        date_added="2026-03-01 12:30:00")
    assert rec._added_ordinal(s, 0) == date(2026, 3, 1).toordinal()


def test_alphabetisch_ohne_titel_nimmt_dateiname():
    songs = [SimpleNamespace(id=1, title="", filename="b.mp3"),
             SimpleNamespace(id=2, title=None, filename="a.mp3"),
             SimpleNamespace(id=3, title="C", filename="a0.mp3")]
    kw = dict(last_played_map={}, today=HEUTE, fallback_date=START)
    assert [s.id for s in rec.rank(songs, rec.SORT_ALPHA, **kw)] == [2, 1, 3]
    assert rec.pick(songs, rec.SORT_ALPHA, **kw).id == 2
