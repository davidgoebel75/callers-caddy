"""Song loeschen stoppt still und raeumt auf (intern#212).

Wird der gerade geladene Song geloescht, stoppt der Player ueber den
normalen Stopp-Pfad. Fuer einen Song, den es gleich nicht mehr gibt, soll
dabei weder das Feedback-Fenster erscheinen noch song_stopped feuern. Danach
ist nichts mehr von ihm sichtbar oder startbar: Song Data leer, Player ohne
Datei, keine Eintraege mehr in der Playlist. Ein normaler Stopp bleibt
unveraendert.
"""
from types import SimpleNamespace

import pytest

import main
from playlist_widget import PlaylistWidget

W = main.P29MainWindow


class _Fenster:
    _on_song_deleted = W._on_song_deleted
    _on_manual_stop = W._on_manual_stop
    _trigger_song_stopped = W._trigger_song_stopped

    def __init__(self):
        self.calls = []
        self._settings = SimpleNamespace(value=lambda key, default=None, type=None: True)
        self._countdown_overlay = SimpleNamespace(hide_overlay=lambda: None)
        self._in_audition = False
        self.fired = []
        self.rule_engine = SimpleNamespace(
            is_suspended=False, fire_trigger=self.fired.append)
        self.session = SimpleNamespace(location_id=1)
        self._current_song = SimpleNamespace(id=7, quality=0, err=0)
        self.player = SimpleNamespace(
            _on_stop=self._on_manual_stop,
            clear_loaded_song=lambda: self.calls.append("player"))
        self.lyrics_widget = SimpleNamespace(clear=lambda: self.calls.append("lyrics"))
        self.song_data = SimpleNamespace(clear_song=lambda: self.calls.append("song_data"))
        self.playlist_widget = SimpleNamespace(
            remove_song=lambda sid: self.calls.append(("playlist", sid)))
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
    assert f.calls == ["player", "lyrics", "song_data", ("playlist", 7)]


def test_normaler_stopp_zeigt_feedback_und_feuert(feedback):
    f = _Fenster()
    f._on_manual_stop()
    assert feedback == [7]
    assert f.fired == ["song_stopped"]


def test_loeschen_eines_anderen_songs_laesst_player_in_ruhe(feedback):
    f = _Fenster()
    f._on_song_deleted(99)
    assert feedback == [] and f.fired == []
    assert f._current_song.id == 7
    # Song Data zeigte den geloeschten Song; die Playlist verliert ihn
    assert f.calls == ["song_data", ("playlist", 99)]


# ---- Playlist: alle Eintraege eines Songs entfernen ----

class _Playlist:
    remove_song = PlaylistWidget.remove_song
    remove_rows = PlaylistWidget.remove_rows
    _reanchor_current = PlaylistWidget._reanchor_current

    def __init__(self, ids, current):
        self._playlist = [SimpleNamespace(song=SimpleNamespace(id=i)) for i in ids]
        self._current_index = current
        self.refreshed = 0

    def refresh_display(self):
        self.refreshed += 1

    def _notify_changed(self):
        pass


def test_playlist_entfernt_alle_eintraege_des_songs():
    pl = _Playlist([1, 7, 2, 7, 3], current=2)        # aktuell: Song 2
    pl.remove_song(7)
    assert [e.song.id for e in pl._playlist] == [1, 2, 3]
    assert pl._playlist[pl._current_index].song.id == 2
    assert pl.refreshed == 1                          # ein Refresh fuer alles


def test_playlist_ohne_den_song_bleibt_unveraendert():
    pl = _Playlist([1, 2], current=0)
    pl.remove_song(7)
    assert [e.song.id for e in pl._playlist] == [1, 2]
    assert pl.refreshed == 0
