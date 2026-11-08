"""Charakterisierung der Empfehlungsregel (intern#141).

Friert das heutige Verhalten aller Kopien ein, bevor sie auf das Modul
`caddy.songs.recommendation` umgehaengt werden. Gruen davor und danach:

  K1  Songliste        SongFilterBar.filter_and_sort
  K2  Shortcode-Wahl   P29MainWindow._rule_load_song
  K3  Abendplaner      SongScorer
  K4  Helfer           Tage seit zuletzt gespielt, Score, gewichtete Reihenfolge
      (bis zum Umbau in ui_helpers, danach im Modul; Erwartungen unveraendert)

Die Kopien weichen bewusst voneinander ab (issues/.../abweichungen-fuer-david.md,
A1 bis A7). Jede Abweichung ist hier ein Test, keine wird korrigiert.
Zufall kommt nur ueber feste Werte herein.
"""
import itertools
import math
import random
import sqlite3
from datetime import date, datetime, timedelta
from types import SimpleNamespace

import pytest

import main
import songdata_widget
from caddy.songs import recommendation
from evening_planner_widget import SongScorer
from song_db import Song

HEUTE = date.today()


def _vor(tage):
    """ISO-Datum von vor `tage` Tagen (negativ = Zukunft)."""
    return (HEUTE - timedelta(days=tage)).isoformat()


START = HEUTE - timedelta(days=100)

# id: (Qualitaet, zuletzt gespielt, date_added, Typ-Flags)
#   1 q5, vor 10 Tagen          Score  50
#   2 q3, vor 20 Tagen          Score  60
#   3 q0 (unbewertet), vor 30   Score   0
#   4 q4, nie gespielt          Score 400 (100 Tage ab START)
#   5 q5, heute gespielt        Score   0
#   6 q2, in der Zukunft (+3)   Score  -6
#   7 q3, kaputter String       faellt auf START zurueck: 300
#   8 q3, vor 20 Tagen          Score  60 (Gleichstand mit 2)
_LP = {1: _vor(10), 2: _vor(20), 3: _vor(30), 5: _vor(0), 6: _vor(-3),
       7: "kaputt", 8: _vor(20)}
_QUAL = {1: 5, 2: 3, 3: 0, 4: 4, 5: 5, 6: 2, 7: 3, 8: 3}
_ADDED = {1: "2026-01-05", 2: "2026-03-01", 3: "", 4: "2026-03-01",
          5: "kaputt", 6: "2025-12-31", 7: "", 8: "2026-02-01"}
# Tiebreak-Werte: Gleichstand 2 gegen 8 wird bei aktivem Tiebreak umgedreht
_TB = {1: .8, 2: .9, 3: .5, 4: .1, 5: .7, 6: .2, 7: .3, 8: .1}
_DRAW = {1: .5, 2: .9, 3: .2, 4: .7, 5: .3, 6: .8, 7: .6, 8: .4}


def _songs():
    return [SimpleNamespace(
        id=i, title=f"S{i}", filename=f"s{i}.mp3", label="", is_pattern=1,
        is_singing=1, quality=_QUAL[i], date_added=_ADDED[i], err=0)
        for i in range(1, 9)]


def _ids(songs):
    return [s.id for s in songs]


# ---------------------------------------------------------------------------
# K4 Helfer
# ---------------------------------------------------------------------------

def _tage(song_id, lpm, fallback):
    return recommendation.days_since(lpm.get(song_id), HEUTE, fallback)


def test_k4_tage_seit_zuletzt_gespielt():
    f = _tage
    assert f(1, _LP, START) == 10
    assert f(5, _LP, START) == 0
    assert f(6, _LP, START) == -3          # A7: Zukunft ergibt negative Tage
    assert f(4, _LP, START) == 100         # nie gespielt: ab fallback_date
    assert f(7, _LP, START) == 100         # kaputter String: ebenso
    assert f(4, _LP, HEUTE) == 0           # A4: ohne Startdatum 0 Tage


def test_k4_tage_nehmen_nur_das_datum_vom_zeitstempel():
    lp = {1: _vor(4) + " 23:59:59"}
    assert _tage(1, lp, START) == 4


def test_k4_score_ist_qualitaet_mal_tage_als_ganzzahl():
    songs = {s.id: s for s in _songs()}

    def f(song, lpm, fallback):
        return recommendation.song_score(song, lpm, HEUTE, fallback)
    assert f(songs[1], _LP, START) == 50
    assert f(songs[3], _LP, START) == 0     # A2: unbewertet = Score 0
    assert f(songs[4], _LP, START) == 400
    assert f(songs[6], _LP, START) == -6    # A7


def test_k4_gewichtete_reihenfolge_mit_festen_ziehungen():
    songs = _songs()
    weights = {1: 50, 2: 10, 3: 1, 4: 400, 5: 1, 6: 1, 7: 300, 8: 10}
    out = recommendation.weighted_order(
        songs, lambda s: weights[s.id], lambda sid: _DRAW[sid])
    keys = {i: -math.log(_DRAW[i]) / weights[i] for i in weights}
    assert _ids(out) == sorted(keys, key=keys.get)
    assert _ids(out) == [4, 7, 2, 1, 8, 6, 5, 3]


def test_k4_unbewertet_in_zufall_ist_fuenf():
    assert recommendation.UNRATED_IN_RANDOM == 5


# ---------------------------------------------------------------------------
# K1 Songliste
# ---------------------------------------------------------------------------

SB = songdata_widget.SongFilterBar


@pytest.fixture
def bar(keep):
    return keep(SB(show_recommendation=True))


def _sortiere(bar, mode, tiebreak, added_fallback=None, start=START):
    bar._combo_sort.setCurrentIndex(bar._combo_sort.findData(mode))
    bar._chk_random_tb.setChecked(tiebreak)
    bar._sort_random.clear()
    bar._sort_random.update(_TB)
    bar._sort_draw.clear()
    bar._sort_draw.update(_DRAW)
    return _ids(bar.filter_and_sort(_songs(), dict(_LP), start_date=start,
                                    added_fallback=added_fallback))


@pytest.mark.parametrize("mode, tb, erwartet", [
    (SB.SORT_ALPHA, False, [1, 2, 3, 4, 5, 6, 7, 8]),
    (SB.SORT_ALPHA, True, [1, 2, 3, 4, 5, 6, 7, 8]),
    # Qualitaet absteigend; Gleichstaende ohne Tiebreak in Listenreihenfolge
    (SB.SORT_QUALITY, False, [1, 5, 4, 2, 7, 8, 6, 3]),
    # mit Tiebreak entscheidet der kleinere Wert: 8(.1) 7(.3) 2(.9), 1(.8) 5(.7)
    (SB.SORT_QUALITY, True, [5, 1, 4, 8, 7, 2, 6, 3]),
    # Tage absteigend: 4,7 = 100; 3 = 30; 2,8 = 20; 1 = 10; 5 = 0; 6 = -3
    # kein Tiebreak bei "zuletzt gespielt", auch nicht mit Haken
    (SB.SORT_LAST_PLAYED, False, [4, 7, 3, 2, 8, 1, 5, 6]),
    (SB.SORT_LAST_PLAYED, True, [4, 7, 3, 2, 8, 1, 5, 6]),
    # Score: 4=400, 7=300, 2=8=60, 1=50, 3=5=0, 6=-6
    (SB.SORT_RECOMMENDATION, False, [4, 7, 2, 8, 1, 3, 5, 6]),
    (SB.SORT_RECOMMENDATION, True, [4, 7, 8, 2, 1, 3, 5, 6]),
    # Reiner Zufall: aufsteigend nach Ziehung, Tiebreak ohne Wirkung
    (SB.SORT_RANDOM, False, [3, 5, 8, 1, 7, 4, 6, 2]),
    (SB.SORT_RANDOM, True, [3, 5, 8, 1, 7, 4, 6, 2]),
])
def test_k1_sortierung(bar, mode, tb, erwartet):
    assert _sortiere(bar, mode, tb) == erwartet


@pytest.mark.parametrize("tb", [False, True])
def test_k1_gewichteter_zufall(bar, tb):
    # Gewichte: q (unbewertet = 5) * Tage + 1, mindestens 1.
    # 1: 51, 2: 61, 3: 5*30+1 = 151, 4: 401, 5: 1, 6: 1 (Zukunft), 7: 301, 8: 61
    w = {1: 51, 2: 61, 3: 151, 4: 401, 5: 1, 6: 1, 7: 301, 8: 61}
    keys = {i: -math.log(_DRAW[i]) / w[i] for i in w}
    erwartet = sorted(keys, key=keys.get)
    assert _sortiere(bar, SB.SORT_WEIGHTED_RANDOM, tb) == erwartet
    assert erwartet == [4, 7, 2, 3, 1, 8, 6, 5]


def test_k1_datum_erbe_fuer_songs_ohne_einfuegedatum(bar):
    # Neueste zuerst. Erbe-Datum: added_fallback, sonst start_date.
    # 2, 4: 2026-03-01 | 8: 02-01 | 1: 01-05 | 6: 2025-12-31 | 3, 5, 7: Erbe
    spaet = date(2026, 2, 15)
    assert _sortiere(bar, SB.SORT_DATE_ADDED, False, added_fallback=spaet) == \
        [2, 4, 3, 5, 7, 8, 1, 6]
    # Ohne added_fallback erbt start_date (hier START = heute - 100 Tage,
    # also nach den Daten von 2026 oder davor, je nach Laufdatum): fest
    # waehlen, damit der Test nicht vom Kalender abhaengt.
    start = date(2026, 1, 20)
    assert _sortiere(bar, SB.SORT_DATE_ADDED, False, start=start) == \
        [2, 4, 8, 3, 5, 7, 1, 6]


def test_k1_datum_tiebreak(bar):
    spaet = date(2026, 2, 15)
    # Gleichstaende (2/4) und (3/5/7) laufen mit Tiebreak nach kleinem Wert
    assert _sortiere(bar, SB.SORT_DATE_ADDED, True, added_fallback=spaet) == \
        [4, 2, 7, 3, 5, 8, 1, 6]


def test_k1_ohne_startdatum_zaehlt_nie_gespielt_als_null_tage(bar):
    # A4: start_date=None -> heute; Song 4 und 7 haben dann 0 Tage, Score 0
    ids = _sortiere(bar, SB.SORT_RECOMMENDATION, False, start=None)
    assert ids == [2, 8, 1, 3, 4, 5, 7, 6]


# ---------------------------------------------------------------------------
# K2 Shortcode-Wahl
# ---------------------------------------------------------------------------

class _Fenster:
    _rule_load_song = main.P29MainWindow._rule_load_song

    def __init__(self, songs, lpm, start):
        self.loaded = []
        self.song_list = SimpleNamespace(
            _all_songs=songs, _last_played_map=lpm, _start_date=start,
            _filter_bar=SimpleNamespace(set_type_filter=lambda _i: None),
            _row_by_id={},
            table=SimpleNamespace(selectRow=lambda r: None,
                                  item=lambda r, c: None,
                                  scrollToItem=lambda *a: None))

    def _on_song_selected(self, song_id, offer_copy=True):
        self.loaded.append(song_id)


def _songs_k2():
    return [Song(id=i, filename=f"s{i}.mp3", title=f"S{i}",
                 quality=_QUAL[i], date_added=_ADDED[i],
                 is_pattern=1, is_singing=1) for i in range(1, 9)]


def _lade(monkeypatch, sort, draws=(), start=START, lpm=None, songs=None):
    """Fuehrt die Regel-Aktion aus; `draws` sind die aufeinanderfolgenden
    Rueckgabewerte von random.random() (danach 0.5)."""
    folge = itertools.chain(draws, itertools.repeat(0.5))
    monkeypatch.setattr(random, "random", lambda: next(folge))
    f = _Fenster(songs or _songs_k2(), dict(_LP) if lpm is None else lpm, start)
    f._rule_load_song({"type": "Singing", "sort": sort})
    return f.loaded


def test_k2_alphabetisch_ohne_zufall(monkeypatch):
    assert _lade(monkeypatch, "Alphabetical") == [1]


def test_k2_empfehlung_nimmt_hoechsten_score(monkeypatch):
    assert _lade(monkeypatch, "Recommendation") == [4]


def test_k2_empfehlung_gleichstand_entscheidet_frischer_zufall(monkeypatch):
    # nur 2 und 8 (beide Score 60), je ein Zufallswert in Listenreihenfolge
    zwei = [s for s in _songs_k2() if s.id in (2, 8)]
    assert _lade(monkeypatch, "Recommendation", [0.2, 0.9], songs=zwei) == [8]
    assert _lade(monkeypatch, "Recommendation", [0.9, 0.2], songs=zwei) == [2]


def test_k2_empfehlung_unbewertete_haben_score_null(monkeypatch):
    # A2: nur unbewertet (q0) gegen heute gespielt (Score 0): reiner Zufall
    s = [x for x in _songs_k2() if x.id in (3, 5)]
    assert _lade(monkeypatch, "Recommendation", [0.9, 0.1], songs=s) == [3]
    assert _lade(monkeypatch, "Recommendation", [0.1, 0.9], songs=s) == [5]


def test_k2_gewichtet_unbewertet_zaehlt_fuenf(monkeypatch):
    # Gewichte siehe K1; hoechstes Gewicht = 4 (401) bei gleicher Ziehung
    assert _lade(monkeypatch, "Weighted random",
                 [0.5] * 8) == [4]


def test_k2_gewichtet_feste_ziehung(monkeypatch):
    # Song 3 (q0 -> 5) bekommt die kleinste Ziehung, 4 eine grosse:
    # Schluessel -ln(u)/w; 3: -ln(.999)/151 ~ 6.6e-6 gewinnt vor 4
    ziehungen = [.5, .5, .999, .9, .5, .5, .5, .5]
    assert _lade(monkeypatch, "Weighted random", ziehungen) == [3]


def test_k2_qualitaet_mit_zufalls_tiebreak(monkeypatch):
    # Q5: Songs 1 und 5. Zufallswerte in Listenreihenfolge ueber alle 8 Songs
    ziehungen = [.9, 0, 0, 0, .1, 0, 0, 0]
    assert _lade(monkeypatch, "Quality", ziehungen) == [1]
    ziehungen = [.1, 0, 0, 0, .9, 0, 0, 0]
    assert _lade(monkeypatch, "Quality", ziehungen) == [5]


def test_k2_zuletzt_gespielt_hat_zufalls_tiebreak(monkeypatch):
    # A5: Songs 4 und 7 haben je 100 Tage; K1 wuerfelt hier nie
    ziehungen = [0, 0, 0, .1, 0, 0, .9, 0]
    assert _lade(monkeypatch, "Last played", ziehungen) == [7]
    ziehungen = [0, 0, 0, .9, 0, 0, .1, 0]
    assert _lade(monkeypatch, "Last played", ziehungen) == [4]


def test_k2_einfuegedatum_erbt_nur_start_date(monkeypatch):
    # A6: ohne added_fallback. Erbe-Datum 2026-01-20: Songs 2 und 4
    # (2026-03-01) vorn, Zufall entscheidet.
    start = date(2026, 1, 20)
    assert _lade(monkeypatch, "Date added", [0, .9, 0, .1, 0, 0, 0, 0],
                 start=start) == [2]
    assert _lade(monkeypatch, "Date added", [0, .1, 0, .9, 0, 0, 0, 0],
                 start=start) == [4]


# ---------------------------------------------------------------------------
# K3 Abendplaner
# ---------------------------------------------------------------------------

class _FakeDb:
    def __init__(self, rows):
        self.rows = rows
        self.args = None

    def get_planner_candidates(self, target_err, location_id, days_fallback):
        self.args = (target_err, location_id, days_fallback)
        return self.rows


#       sid, title, label, err, quality, isPattern, isSinging, days, genres
_ROWS = [
    (1, "A", "L", 5, 4, 1, 0, 10, "rock,pop"),     # 4*10*1.0   = 40
    (2, "B", "L", 4, 4, 1, 0, 10, "rock"),         # 4*10*0.5   = 20
    (3, "C", "L", 0, 4, 1, 0, 10, ""),             # 4*10*0.25  = 10
    (4, "D", "L", 5, 2, 0, 1, 20, "pop"),          # 2*20*1.0   = 40
    (5, "E", "L", 5, 4, 1, 0, 0, ""),              # Score 0: verworfen
    (6, "F", "L", 7, 3, 1, 1, 10, "jazz"),         # 3*10*(1/3) = 10
]


def _kandidaten(**kw):
    sc = SongScorer(_FakeDb(_ROWS), tiebreaker=kw.pop("tiebreaker", None))
    return sc.candidates(5, 1, kw.pop("pattern", True), kw.pop("singing", True),
                         limit=kw.pop("limit", None), **kw), sc


def test_k3_score_formel():
    s = SongScorer._score
    assert s(4, 10, 5, 5) == 40.0      # Ziel getroffen
    assert s(4, 10, 4, 5) == 20.0      # 1 daneben: halb
    assert s(4, 10, 7, 5) == pytest.approx(40 / 3)
    assert s(4, 10, 0, 5) == 10.0      # A3: ERR nicht gepflegt = 0.25
    assert s(4, 10.9, 5, 5) == 40.0    # Tage werden abgeschnitten
    assert s(4, 0, 5, 5) == 0.0


def test_k3_kandidaten_ohne_tiebreak():
    res, sc = _kandidaten()
    assert [(c.song_id, c.score) for c in res] == [
        (1, 40.0), (4, 40.0), (2, 20.0), (3, 10.0), (6, pytest.approx(10.0))]
    assert sc._db.args[:2] == (5, 1)
    assert res[0].genres == ("rock", "pop") and res[2].days == 10


def test_k3_gleichstand_entscheidet_tiebreaker():
    tb = {1: .9, 4: .1, 3: .7, 6: .2}
    res, _ = _kandidaten(tiebreaker=lambda sid: tb.get(sid, 0))
    assert [c.song_id for c in res] == [4, 1, 2, 6, 3]


def test_k3_typ_genre_ausschluss_und_limit():
    res, _ = _kandidaten(pattern=True, singing=False)
    assert [c.song_id for c in res] == [1, 2, 3, 6]
    res, _ = _kandidaten(pattern=False, singing=True)
    assert [c.song_id for c in res] == [4, 6]
    res, _ = _kandidaten(genre_filter=["pop"])
    assert [c.song_id for c in res] == [1, 4]
    res, _ = _kandidaten(exclude_ids={1, 4})
    assert [c.song_id for c in res] == [2, 3, 6]
    res, _ = _kandidaten(limit=2)
    assert [c.song_id for c in res] == [1, 4]


def test_a1_sql_jetzt_ist_utc_waehrend_last_played_ortszeit_ist():
    # Abendplaner-SQL rechnet mit julianday('now') (UTC), last_played wird mit
    # datetime('now','localtime') geschrieben (song_db.py). Ein eben
    # geschriebener Zeitstempel liegt daher um den UTC-Versatz in der
    # "Zukunft". Der Test dokumentiert das; korrigiert wird es nicht.
    con = sqlite3.connect(":memory:")
    delta = con.execute(
        "SELECT julianday('now') - julianday(datetime('now','localtime'))"
    ).fetchone()[0]
    versatz = datetime.now().astimezone().utcoffset().total_seconds() / 86400
    assert delta == pytest.approx(-versatz, abs=1e-3)
