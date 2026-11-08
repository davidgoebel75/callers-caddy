"""Loop-Dialog bei doppeltem Song in der Playlist (intern#184).

Steht derselbe Song zweimal in der Playlist, greift der Sofort-Abgleich mit der
Engine nur fuer den Eintrag, der gerade geladen ist, nicht fuer den anderen.

Geprueft werden die echten Methoden von P29MainWindow auf einem schlanken
Ersatzfenster (ohne Audio, DB und Docks).
"""
from types import SimpleNamespace

import main
from playlist_widget import PlaylistEntry
from song_db import Song
from song_types import PlayMode

W = main.P29MainWindow


class _Sitzung:
    """Fake der aktuellen Sitzung: kein QObject (Windows-Crash-Falle), nur song/set_song."""

    def __init__(self, song=None, **kw):
        self.song = song
        self.__dict__.update(kw)

    def set_song(self, song):
        self.song = song


class _Fenster:
    _sync_loop_settings_if_loaded = W._sync_loop_settings_if_loaded
    _loaded_playlist_entry = W._loaded_playlist_entry

    def __init__(self, song, current_entry):
        self.session = _Sitzung(song)
        self.playlist_widget = SimpleNamespace(get_current_entry=lambda: current_entry)
        self.an_engine = []

    def _apply_loop_settings_to_engine(self, entry):
        self.an_engine.append(entry)


def _zwei_eintraege():
    song = Song(id=7, filename="x.mp3", is_pattern=1)
    return song, PlaylistEntry(song, PlayMode.LOOP), PlaylistEntry(song, PlayMode.ONCE)


def test_anderer_eintrag_laesst_engine_in_ruhe():
    song, laeuft, anderer = _zwei_eintraege()
    fenster = _Fenster(song, laeuft)
    fenster._sync_loop_settings_if_loaded(anderer)
    assert fenster.an_engine == []


def test_laufender_eintrag_geht_sofort_an_die_engine():
    song, laeuft, _ = _zwei_eintraege()
    fenster = _Fenster(song, laeuft)
    fenster._sync_loop_settings_if_loaded(laeuft)
    assert fenster.an_engine == [laeuft]


def test_aktueller_eintrag_mit_anderem_song_zaehlt_nicht():
    # Song aus der Songliste geladen, Playlist-Zeiger steht auf einem anderen Song
    song, eintrag, _ = _zwei_eintraege()
    fenster = _Fenster(Song(id=8, filename="y.mp3"), eintrag)
    fenster._sync_loop_settings_if_loaded(eintrag)
    assert fenster.an_engine == []
