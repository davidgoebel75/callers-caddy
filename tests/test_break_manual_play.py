"""Manuelles Play waehrend der Pause (intern#130).

Startet der Caller waehrend der Pause von Hand einen Song, ist die Pause
vorbei (Entscheidung David): Wartemusik-Zustand verwerfen (nichts stoppen,
nichts nachladen), Pausen-Uhr zuruecksetzen, 'break_finished' feuert NICHT.
Gilt auch ohne Wartemusik. Ohne Eingriff bleibt alles wie bisher.

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
    _end_break_on_manual_play = W._end_break_on_manual_play
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
        self.pausen_uhr_beendet = []
        self.break_widget = SimpleNamespace(
            set_music_stopped=lambda: None,
            end_break=lambda: self.pausen_uhr_beendet.append(True))
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


def test_manuelles_play_beendet_die_pause(fenster):
    fenster._current_song = SimpleNamespace(id=VON_HAND)
    fenster._end_break_on_manual_play()
    # Historie und Rules gelten sofort wieder fuer den neuen Song
    assert not fenster._suppress_play_log
    assert "break_music" not in fenster.rule_engine.gesperrt
    assert not fenster._break_music_active
    # nichts gestoppt, nichts nachgeladen, Pausen-Uhr zurueckgesetzt
    assert fenster.gestoppt == []
    assert fenster.nachgeladen == []
    assert fenster._current_song.id == VON_HAND
    assert fenster.pausen_uhr_beendet == [True]
    # break_finished feuert nicht (abgebrochen, nicht abgelaufen)
    QCoreApplication.processEvents()
    assert fenster.rule_engine.trigger == []


def test_manuelles_play_ohne_wartemusik_beendet_die_pause(fenster):
    fenster._break_music_active = False
    fenster._break_music_song_id = None
    fenster._pre_break_song_id = None
    fenster._suppress_play_log = False
    fenster._current_song = SimpleNamespace(id=VON_HAND)
    fenster._end_break_on_manual_play()
    assert fenster.pausen_uhr_beendet == [True]
    assert fenster.gestoppt == [] and fenster.nachgeladen == []


@pytest.mark.parametrize("audition, suppress", [(True, True), (False, True)])
def test_vorhoeren_beendet_die_pause_nicht(fenster, audition, suppress):
    """Audition bzw. Testlauf (Loop-Finder, Sync-Modus, ZIP-Vorhoeren) ohne
    Wartemusik ist kein manuelles Play."""
    fenster._break_music_active = False
    fenster._in_audition = audition
    fenster._suppress_play_log = suppress
    fenster._current_song = SimpleNamespace(id=VON_HAND)
    fenster._end_break_on_manual_play()
    assert fenster.pausen_uhr_beendet == []


def test_ohne_eingriff_wie_bisher(fenster):
    _pausenende(fenster)
    assert fenster.gestoppt == [PAUSEN_SONG]
    assert fenster.nachgeladen == [VOR_DER_PAUSE]
    assert not fenster._break_music_active
    assert "break_music" not in fenster.rule_engine.gesperrt
    assert fenster.rule_engine.trigger == ["break_finished"]


def test_play_der_wartemusik_selbst_aendert_nichts(fenster):
    fenster._end_break_on_manual_play()
    assert fenster._break_music_active
    assert fenster._pre_break_song_id == VOR_DER_PAUSE
    assert "break_music" in fenster.rule_engine.gesperrt
    assert fenster.pausen_uhr_beendet == []


def test_pausen_uhr_end_break_setzt_zurueck_ohne_finished(qapp):
    from break_photo_widget import BreakWidget
    w = BreakWidget()
    fertig = []
    w.on_break_finished = lambda: fertig.append(1)
    assert not w.end_break()                 # laeuft nicht -> nichts zu tun
    w.start_break(120)
    w._remaining = 37.0
    assert w.end_break()
    assert not w._running and not w._finished
    assert w._remaining == w._total == 120.0
    assert fertig == []
