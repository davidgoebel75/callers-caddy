"""Song loeschen stoppt still: kein Feedback, keine Rules (intern#212).

Wird der gerade geladene Song geloescht, stoppt der Player ueber den
normalen Stopp-Pfad. Fuer einen Song, den es gleich nicht mehr gibt, soll
dabei weder das Feedback-Fenster erscheinen noch song_stopped feuern. Ein
normaler Stopp bleibt unveraendert.
"""
from types import SimpleNamespace

import pytest

import main

W = main.P29MainWindow


class _Fenster:
    _on_song_deleted = W._on_song_deleted
    _on_manual_stop = W._on_manual_stop
    _trigger_song_stopped = W._trigger_song_stopped

    def __init__(self):
        self._settings = SimpleNamespace(value=lambda key, default=None, type=None: True)
        self._countdown_overlay = SimpleNamespace(hide_overlay=lambda: None)
        self._in_audition = False
        self.fired = []
        self.rule_engine = SimpleNamespace(
            is_suspended=False, fire_trigger=self.fired.append)
        self.session = SimpleNamespace(location_id=1)
        self._current_song = SimpleNamespace(id=7, quality=0, err=0)
        self.player = SimpleNamespace(_on_stop=self._on_manual_stop)
        self.song_list = SimpleNamespace(refresh=lambda: None)
        self.playlist_manager = SimpleNamespace(refresh=lambda: None)
        self.potential_widget = None


@pytest.fixture
def feedback(monkeypatch):
    shown = []

    class _Dialog:
        suppress_session = False

        def __init__(self, song, *_a, **_kw):
            shown.append(song.id)

        def exec(self):
            return 0
    monkeypatch.setattr(main, "FeedbackDialog", _Dialog)
    return shown


def test_loeschen_des_geladenen_songs_ohne_feedback_und_rules(feedback):
    f = _Fenster()
    f._on_song_deleted(7)
    assert feedback == []
    assert f.fired == []
    assert f._current_song is None
    assert f._stop_silently is False      # gilt nur fuer diesen einen Stopp


def test_normaler_stopp_zeigt_feedback_und_feuert(feedback):
    f = _Fenster()
    f._on_manual_stop()
    assert feedback == [7]
    assert f.fired == ["song_stopped"]


def test_loeschen_eines_anderen_songs_stoppt_nicht(feedback):
    f = _Fenster()
    f._on_song_deleted(99)
    assert feedback == [] and f.fired == []
    assert f._current_song.id == 7
