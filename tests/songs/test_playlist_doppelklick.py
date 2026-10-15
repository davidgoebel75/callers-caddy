"""Doppelklick in der Playlist startet den Song (intern#213).

Wie in der Songliste: Der Einfachklick davor hat den Eintrag schon geladen,
der Doppelklick startet ihn. Die Spalte Loops oeffnet weiter die Loop-Anzahl.
"""
from types import SimpleNamespace

import pytest
from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

import main
from playlist_widget import PlaylistEntry, PlaylistWidget
from song_db import Song
from song_types import PlayMode

LOOPS = 3


def _playlist(keep):
    pw = keep(PlaylistWidget(db=None, paths=SimpleNamespace(find_song_file=lambda f: None)))
    for nr in (1, 2):
        pw.add_entry(PlaylistEntry(song=Song(id=nr, filename=f"{nr}.mp3"),
                                   play_mode=PlayMode.ONCE))
    started, loop_edits = [], []
    pw.on_playlist_song_activated = started.append
    pw.on_loop_count_edit = loop_edits.append
    return pw, started, loop_edits


def _doppelklick(pw, row, col):
    pw._pl_table.on_col_double_click(row, col)


def test_doppelklick_auf_titel_startet_den_eintrag(keep):
    pw, started, loop_edits = _playlist(keep)
    _doppelklick(pw, 1, 2)
    assert [e.song.id for e in started] == [2]
    assert loop_edits == []


def test_doppelklick_auf_loops_oeffnet_weiter_die_loop_anzahl(keep):
    pw, started, loop_edits = _playlist(keep)
    _doppelklick(pw, 0, LOOPS)
    assert loop_edits == [0]
    assert started == []


@pytest.mark.parametrize("taste", [Qt.ControlModifier, Qt.ShiftModifier])
def test_doppelklick_mit_auswahl_taste_startet_nichts(keep, monkeypatch, taste):
    # Strg/Umschalt baut nur die Mehrfachauswahl auf, der Einfachklick hat
    # dabei nichts geladen (intern#93)
    pw, started, _ = _playlist(keep)
    monkeypatch.setattr(QApplication, "keyboardModifiers", staticmethod(lambda: taste))
    _doppelklick(pw, 0, 2)
    assert started == []


def test_echter_doppelklick_laedt_danach_nicht_noch_einmal(keep):
    # Echte Ereignisfolge: Druecken, Loslassen, Druecken, Doppelklick,
    # Loslassen. Das letzte Loslassen darf kein cellClicked mehr ausloesen,
    # sonst laedt die Playlist den eben gestarteten Song neu und er stoppt.
    pw, started, _ = _playlist(keep)
    selected = []
    pw.on_playlist_song_selected = selected.append
    pw.resize(600, 300)
    pw.show()
    vp = pw._pl_table.viewport()
    p = pw._pl_table.visualRect(pw._pl_table.model().index(1, 2)).center()
    QTest.mousePress(vp, Qt.LeftButton, Qt.NoModifier, p)
    QTest.mouseRelease(vp, Qt.LeftButton, Qt.NoModifier, p)
    QTest.mousePress(vp, Qt.LeftButton, Qt.NoModifier, p)
    QApplication.sendEvent(vp, QMouseEvent(
        QEvent.MouseButtonDblClick, QPointF(p), QPointF(vp.mapToGlobal(p)),
        Qt.LeftButton, Qt.LeftButton, Qt.NoModifier))
    QTest.mouseRelease(vp, Qt.LeftButton, Qt.NoModifier, p)
    assert [e.song.id for e in selected] == [2]
    assert [e.song.id for e in started] == [2]


class _Fenster:
    """Nur was der Start-Handler des Hauptfensters braucht."""
    _on_playlist_song_activated = main.P29MainWindow._on_playlist_song_activated

    def __init__(self, geladen_id, engine_geladen=True):
        self._current_song = Song(id=geladen_id) if geladen_id else None
        self.plays = 0
        self.player = SimpleNamespace(
            engine=SimpleNamespace(is_loaded=lambda: engine_geladen),
            _on_play=self._play)

    def _play(self):
        self.plays += 1


def _eintrag(song_id):
    return PlaylistEntry(song=Song(id=song_id), play_mode=PlayMode.ONCE)


def test_geladener_eintrag_wird_abgespielt():
    f = _Fenster(geladen_id=2)
    f._on_playlist_song_activated(_eintrag(2))
    assert f.plays == 1


@pytest.mark.parametrize("geladen_id, engine_geladen", [
    (1, True),      # Laden des Eintrags gescheitert, der alte Song ist noch da
    (None, True),
    (2, False),
])
def test_ohne_passend_geladenen_song_startet_nichts(geladen_id, engine_geladen):
    f = _Fenster(geladen_id, engine_geladen)
    f._on_playlist_song_activated(_eintrag(2))
    assert f.plays == 0
