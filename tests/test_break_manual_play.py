"""Manuelles Play waehrend der Wartemusik (intern#130).

Startet der Caller waehrend der Wartemusik von Hand einen anderen Song, hat
seine Handlung Vorrang: Das Pausenende stoppt danach nichts und laedt nichts
neu. Ohne Eingriff bleibt alles wie bisher. Die Pausen-Trigger feuern in
beiden Faellen.

Geprueft werden die echten Methoden von P29MainWindow auf einem schlanken
Ersatzfenster (ohne Audio, DB und Docks).
"""
from types import SimpleNamespace

import pytest
from PySide6.QtCore import QCoreApplication

import main

W = main.P29MainWindow

PAUSEN_SONG = 1        # laeuft als Wartemusik
VOR_DER_PAUSE = 2      # war vor der Pause geladen
VON_HAND = 3           # vom Caller waehrend der Wartemusik gestartet


class _Rules:
    def __init__(self):
        self.gesperrt = {"break_music"}
        self.trigger = []

    def resume(self, grund):
        self.gesperrt.discard(grund)

    def fire_trigger(self, name, **_kw):
        self.trigger.append(name)


class _Fenster:
    _end_break_music_on_manual_play = W._end_break_music_on_manual_play
    _leave_break_music = W._leave_break_music
    _on_break_stop_last = W._on_break_stop_last
    _on_break_finished = W._on_break_finished

    def __init__(self):
        # Zustand wie direkt nach _on_break_play_last
        self._break_music_active = True
        self._break_music_song_id = PAUSEN_SONG
        self._pre_break_song_id = VOR_DER_PAUSE
        self._break_music_timer = None
        self._break_music_suppress_feedback = True
        self._suppress_play_log = True
        self._was_playing = True
        self._current_song = SimpleNamespace(id=PAUSEN_SONG)
        self.rule_engine = _Rules()
        self.gestoppt = []
        self.engine = SimpleNamespace(stop=lambda: self.gestoppt.append(
            self._current_song.id))
        self.break_widget = SimpleNamespace(set_music_stopped=lambda: None)
        self.nachgeladen = []

    def _restore_pre_break_song(self):
        song_id, self._pre_break_song_id = self._pre_break_song_id, None
        if song_id:
            self.nachgeladen.append(song_id)
            self._current_song = SimpleNamespace(id=song_id)


@pytest.fixture
def fenster(qapp):
    return _Fenster()


def _pausenende(fenster):
    fenster._on_break_finished()
    QCoreApplication.processEvents()   # break_finished wird deferred gefeuert


def test_manuelles_play_hat_vorrang(fenster):
    fenster._current_song = SimpleNamespace(id=VON_HAND)
    fenster._end_break_music_on_manual_play()
    # Historie und Rules gelten sofort wieder fuer den neuen Song
    assert not fenster._suppress_play_log
    assert "break_music" not in fenster.rule_engine.gesperrt
    _pausenende(fenster)
    assert fenster.gestoppt == []
    assert fenster.nachgeladen == []
    assert fenster._current_song.id == VON_HAND
    assert fenster.rule_engine.trigger == ["break_finished"]


def test_ohne_eingriff_wie_bisher(fenster):
    _pausenende(fenster)
    assert fenster.gestoppt == [PAUSEN_SONG]
    assert fenster.nachgeladen == [VOR_DER_PAUSE]
    assert not fenster._break_music_active
    assert "break_music" not in fenster.rule_engine.gesperrt
    assert fenster.rule_engine.trigger == ["break_finished"]


def test_play_der_wartemusik_selbst_aendert_nichts(fenster):
    fenster._end_break_music_on_manual_play()
    assert fenster._break_music_active
    assert fenster._pre_break_song_id == VOR_DER_PAUSE
    assert "break_music" in fenster.rule_engine.gesperrt
