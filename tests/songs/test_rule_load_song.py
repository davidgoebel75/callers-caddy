"""Regel-Aktion "Load Song" und die Filter der Songliste (intern#169).

Die Aktion laedt einen Song in den Player. Die Filter der Songliste bleiben,
wie der Caller sie gesetzt hat; markiert wird der Song nur, wenn er dort
gerade sichtbar ist.

Geprueft wird die echte Methode von P29MainWindow auf einem schlanken
Ersatzfenster (ohne Audio, DB und Docks).
"""
from datetime import date
from types import SimpleNamespace

import main
from song_db import Song

W = main.P29MainWindow

PATTER = Song(id=1, filename="a.mp3", title="Alpha", is_pattern=1)
SINGING = Song(id=2, filename="b.mp3", title="Beta", is_singing=1)


class _Fenster:
    _rule_load_song = W._rule_load_song

    def __init__(self, visible_ids):
        self.filter_calls = []
        self.selected_rows = []
        self.loaded = []
        self.song_list = SimpleNamespace(
            _all_songs=[PATTER, SINGING],
            _last_played_map={},
            _start_date=date.today(),
            _filter_bar=SimpleNamespace(set_type_filter=self.filter_calls.append),
            _row_by_id={sid: row for row, sid in enumerate(visible_ids)},
            table=SimpleNamespace(selectRow=self.selected_rows.append,
                                  item=lambda row, col: None,
                                  scrollToItem=lambda *a: None))

    def _on_song_selected(self, song_id, offer_copy=True):
        self.loaded.append(song_id)


def _load_patter(fenster):
    fenster._rule_load_song({"type": "Patter", "sort": "Alphabetical"})


def test_typ_filter_der_songliste_bleibt_unberuehrt():
    fenster = _Fenster(visible_ids=[SINGING.id])   # Liste zeigt gerade Singing
    _load_patter(fenster)
    assert fenster.filter_calls == []


def test_ausgeblendeter_song_wird_geladen_aber_nicht_markiert():
    fenster = _Fenster(visible_ids=[SINGING.id])
    _load_patter(fenster)
    assert fenster.loaded == [PATTER.id]
    assert fenster.selected_rows == []


def test_sichtbarer_song_wird_markiert():
    fenster = _Fenster(visible_ids=[SINGING.id, PATTER.id])
    _load_patter(fenster)
    assert fenster.loaded == [PATTER.id]
    assert fenster.selected_rows == [1]
