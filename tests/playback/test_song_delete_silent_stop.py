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
import potential_widget
from playlist_widget import PlaylistWidget
from potential_widget import PotentialWidget

W = main.P29MainWindow


class _Fenster:
    _on_songs_deleted = W._on_songs_deleted
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
        # Einzel-Loeschen: Song Data hat den Song schon vor dem Callback losgelassen
        self.song_data = SimpleNamespace(
            _current_song=None, clear_song=lambda: self.calls.append("song_data"))
        self.playlist_widget = SimpleNamespace(
            remove_songs=lambda ids: self.calls.append(("playlist", sorted(ids))))
        self.refreshed = []
        self.song_list = SimpleNamespace(refresh=lambda: self.refreshed.append("song_list"))
        self.playlist_manager = SimpleNamespace(
            refresh=lambda: self.refreshed.append("planner"))
        self.potential_widget = SimpleNamespace(
            refresh=lambda: self.refreshed.append("potential"))


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
    f._on_songs_deleted([7])
    assert feedback == []
    assert f.fired == []
    assert f._current_song is None
    assert f._stop_silently is False      # gilt nur fuer diesen einen Stopp
    assert f.calls == ["player", "lyrics", "song_data", ("playlist", [7])]


def test_normaler_stopp_zeigt_feedback_und_feuert(feedback):
    f = _Fenster()
    f._on_manual_stop()
    assert feedback == [7]
    assert f.fired == ["song_stopped"]


def test_loeschen_eines_anderen_songs_laesst_player_in_ruhe(feedback):
    f = _Fenster()
    f._on_songs_deleted([99])
    assert feedback == [] and f.fired == []
    assert f._current_song.id == 7
    # Song Data zeigte den geloeschten Song; die Playlist verliert ihn
    assert f.calls == ["song_data", ("playlist", [99])]


# ---- Massen-Loeschen im Potential (intern#214) ----

def test_massen_loeschen_mit_geladenem_song_raeumt_alles_einmal_auf(feedback):
    f = _Fenster()
    f.song_data._current_song = SimpleNamespace(id=7)
    f._on_songs_deleted([3, 7])
    assert feedback == [] and f.fired == []
    assert f._current_song is None
    assert f.calls == ["player", "lyrics", "song_data", ("playlist", [3, 7])]
    assert sorted(f.refreshed) == ["planner", "potential", "song_list"]


def test_massen_loeschen_laesst_song_data_mit_anderem_song_stehen(feedback):
    f = _Fenster()
    f.song_data._current_song = SimpleNamespace(id=5)
    f._on_songs_deleted([3, 4])
    assert f._current_song.id == 7
    assert f.calls == [("playlist", [3, 4])]


# ---- Playlist: alle Eintraege eines Songs entfernen ----

class _Playlist:
    remove_songs = PlaylistWidget.remove_songs
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


def test_playlist_entfernt_alle_eintraege_der_songs():
    pl = _Playlist([1, 7, 2, 7, 3, 8], current=2)     # aktuell: Song 2
    pl.remove_songs({7, 8})
    assert [e.song.id for e in pl._playlist] == [1, 2, 3]
    assert pl._playlist[pl._current_index].song.id == 2
    assert pl.refreshed == 1                          # ein Refresh fuer alles


def test_playlist_ohne_den_song_bleibt_unveraendert():
    pl = _Playlist([1, 2], current=0)
    pl.remove_songs({7})
    assert [e.song.id for e in pl._playlist] == [1, 2]
    assert pl.refreshed == 0


# ---- Echter Player: nach dem Leeren bleibt er leer (Review PR #136) -----------

class _VolleEngine:
    """Engine, die die Audiodaten des geloeschten Songs noch haelt."""
    playing = False
    paused = False

    def __init__(self):
        self.gestartet = 0

    def is_loaded(self):
        return True

    def is_playing(self):
        return False

    def is_paused(self):
        return False

    def play(self, *_a, **_kw):
        self.gestartet += 1


def test_geleerter_player_schaltet_play_nicht_wieder_ein(keep):
    from player_widget import PlayerWidget
    engine = _VolleEngine()
    player = keep(PlayerWidget(engine=engine, paths=None))
    player._current_filename = "geloescht.mp3"       # wie nach _load_file
    player.btn_play.setEnabled(True)

    player.clear_loaded_song()
    player.update_display()                          # naechster 50-ms-Tick

    assert not player.has_file()
    assert not player.btn_play.isEnabled()
    player._on_play()                                # Rule/Doppelklick-Weg
    assert engine.gestartet == 0


# ---- Potential: Nachfrage und Abschluss des Massen-Loeschens (intern#214) ----

class _Potential:
    _on_bulk_delete_clicked = PotentialWidget._on_bulk_delete_clicked
    _on_bulk_delete_finished = PotentialWidget._on_bulk_delete_finished

    def __init__(self, ids, running=None):
        self._bulk_delete_worker = None
        self._bulk_selected_ids = lambda: ids
        self.get_running_song = lambda: running
        self.deleted = []
        self.on_songs_deleted = self.deleted.append
        self.refreshed = 0
        self._load_bulk_table = lambda: None

    def refresh(self):
        self.refreshed += 1


@pytest.fixture
def fragen(monkeypatch):
    texte = []

    def _frage(_parent, _titel, text, *_a):
        texte.append(text)
        return potential_widget.QMessageBox.No       # Abbruch nach der Nachfrage
    monkeypatch.setattr(potential_widget.QMessageBox, "question", _frage)
    monkeypatch.setattr(potential_widget.QMessageBox, "information",
                        lambda *_a: None)
    return texte


def test_nachfrage_nennt_den_laufenden_song(fragen):
    pot = _Potential([3, 7], running=SimpleNamespace(id=7, title="Hey Baby"))
    pot._on_bulk_delete_clicked()
    assert "Hey Baby" in fragen[0]


def test_nachfrage_ohne_laufenden_song_in_der_auswahl(fragen):
    pot = _Potential([3, 4], running=SimpleNamespace(id=7, title="Hey Baby"))
    pot._on_bulk_delete_clicked()
    assert "Hey Baby" not in fragen[0]


def test_nach_dem_massen_loeschen_raeumt_das_hauptfenster_auf(fragen):
    pot = _Potential([3, 7])
    pot._bulk_delete_ids = [3, 7]
    pot._on_bulk_delete_finished(2)
    assert pot.deleted == [[3, 7]]
    assert pot.refreshed == 0             # frischt das Hauptfenster einmal auf
