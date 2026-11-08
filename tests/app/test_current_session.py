"""Aktuelle Sitzung: Lokation an einer Stelle, Widgets hoeren zu (intern#142).

Geprueft wird an den vereinbarten Seams: CurrentSession meldet einen
Lokationswechsel, und ein Widget, das erst danach entsteht, uebernimmt die
aktuelle Lokation selbst — ohne Zwischenspeicher in main.py. Beobachtet wird
das, was der Caller sieht (Notizliste, Tips-Zahl, heutiges Tempo).
"""
from types import SimpleNamespace

import pytest

from current_session import CurrentSession
from playlist_widget import PlaylistWidget


@pytest.fixture
def session(keep):
    return keep(CurrentSession())


def _loc(loc_id=1, name="Club", **kw):
    fields = dict(id=loc_id, name=name, planned_tips=None, temp_tempo=None,
                  has_target_bpm=False, target_bpm=None)
    fields.update(kw)
    return SimpleNamespace(**fields)


def test_set_location_notifies_listeners(session):
    seen = []
    session.location_changed.connect(seen.append)
    loc = _loc(5)
    session.set_location(loc)
    assert session.location is loc
    assert session.location_id == 5
    assert seen == [loc]


def test_no_location_has_no_id(session):
    assert session.location_id is None


def test_same_location_notifies_again(session):
    """Im Dialog geaenderte Lokation (z. B. Tips-Zahl) wirkt sofort."""
    seen = []
    session.location_changed.connect(seen.append)
    loc = _loc()
    session.set_location(loc)
    session.set_location(loc)
    assert seen == [loc, loc]


# ---- Song ---------------------------------------------------------------------

def test_set_song_notifies_listeners(session):
    seen = []
    session.song_changed.connect(seen.append)
    song = SimpleNamespace(id=9)
    session.set_song(song)
    assert session.song is song
    assert session.song_id == 9
    assert seen == [song]


def test_no_song_has_no_id(session):
    assert session.song is None
    assert session.song_id is None


def test_same_song_notifies_again(session):
    """Frisch aus der DB geholter Song mit neuen Werten wirkt sofort."""
    seen = []
    session.song_changed.connect(seen.append)
    song = SimpleNamespace(id=1)
    session.set_song(song)
    session.set_song(song)
    assert seen == [song, song]


def test_set_song_none_notifies_none(session):
    session.set_song(SimpleNamespace(id=1))
    seen = []
    session.song_changed.connect(seen.append)
    session.set_song(None)
    assert seen == [None]
    assert session.song_id is None

# ---- Notizen ------------------------------------------------------------------

class _NotesDB:
    """Je Lokation genau eine offene Notiz mit dem Lokationsnamen."""

    def get_notes(self, location_id):
        return [dict(id=location_id, text=f"Notiz {location_id}",
                     note_type="normal", status="open")]

    def get_location_name(self, location_id):
        return f"Club {location_id}"


def _note_texts(widget):
    from notes_widget import _NoteRow
    return [r._text for r in widget._open_list.rows() if isinstance(r, _NoteRow)]


def test_notes_created_later_show_current_location(session, keep):
    from notes_widget import NotesWidget
    session.set_location(_loc(7))
    notes = keep(NotesWidget(_NotesDB(), session=session))
    assert _note_texts(notes) == ["Notiz 7"]


def test_notes_follow_location_change(session, keep):
    from notes_widget import NotesWidget
    notes = keep(NotesWidget(_NotesDB(), session=session))
    session.set_location(_loc(3))
    assert _note_texts(notes) == ["Notiz 3"]


# ---- Abendplaner ----------------------------------------------------------------

def _planner(tmp_path, session, keep):
    from song_db import SongDatabase
    from evening_planner_widget import EveningPlannerWidget
    db = keep(SongDatabase(str(tmp_path / "t.db")))
    return keep(EveningPlannerWidget(db, session=session))


def test_planner_created_later_takes_planned_tips(session, keep, tmp_path):
    session.set_location(_loc(planned_tips=6))
    planner = _planner(tmp_path, session, keep)
    assert planner._spin_tips.value() == 6


def test_planner_follows_planned_tips(session, keep, tmp_path):
    planner = _planner(tmp_path, session, keep)
    session.set_location(_loc(planned_tips=9))
    assert planner._spin_tips.value() == 9


# ---- Player ---------------------------------------------------------------------

def test_player_applies_location_tempo(session, keep):
    """Temporaeres Tempo der Lokation (BL-086) setzt der Player selbst."""
    from player_widget import PlayerWidget
    engine = _TempoEngine()
    player = keep(PlayerWidget(engine=engine, paths=None, session=session))
    session.set_location(_loc(temp_tempo=94))
    assert player.spin_today_tempo.value() == 94
    assert engine.today_tempo == 0.94


class _TempoEngine:
    """Nur das, was der Player beim Aendern des heutigen Tempos aufruft."""
    today_tempo = None

    def set_tempo(self, factor):
        pass

    def set_today_tempo(self, factor):
        self.today_tempo = factor

# ---- Song: Player, Playlist, Song-Daten-Dock -------------------------------------

class _PlayerDB:
    def __init__(self):
        self.saved = []

    def save_playback_settings(self, song_id, **kw):
        self.saved.append((song_id, kw))


def _player_with_dirty_tempo(session, keep, tempo_percent):
    from player_widget import PlayerWidget
    player = keep(PlayerWidget(engine=_TempoEngine(), paths=None, session=session))
    player._db = _PlayerDB()
    player.spin_tempo.setValue(tempo_percent)
    player._tempo_dirty = True
    return player


def test_player_flush_writes_tempo_to_session_song(session, keep):
    song = SimpleNamespace(id=4, standard_tempo=1.0)
    other = SimpleNamespace(id=5, standard_tempo=1.0)
    session.set_song(song)
    player = _player_with_dirty_tempo(session, keep, 92)
    player._flush_tempo()
    assert song.standard_tempo == 0.92
    assert other.standard_tempo == 1.0
    assert player._db.saved == [(4, {"tempo": 0.92})]


def test_player_flush_without_song_clears_dirty_flag(session, keep):
    player = _player_with_dirty_tempo(session, keep, 92)
    player._flush_tempo()
    assert player._db.saved == []
    assert not player._tempo_dirty


def test_player_flush_after_song_change_hits_new_song(session, keep):
    """Der Flush vor dem Wechsel trifft den alten Song, danach den neuen."""
    old = SimpleNamespace(id=1, standard_tempo=1.0)
    new = SimpleNamespace(id=2, standard_tempo=1.0)
    session.set_song(old)
    player = _player_with_dirty_tempo(session, keep, 90)
    player._flush_tempo()
    session.set_song(new)
    player.spin_tempo.setValue(110)
    player._tempo_dirty = True
    player._flush_tempo()
    assert (old.standard_tempo, new.standard_tempo) == (0.9, 1.1)


class _Liste:
    """Nur was anchor_to_song braucht (kein echtes Widget)."""
    anchor_to_song = PlaylistWidget.anchor_to_song

    def __init__(self, eintraege):
        self._playlist = eintraege
        self._current_index = -1


def _eintrag(song_id, played=False):
    return SimpleNamespace(song=SimpleNamespace(id=song_id), played=played)


def test_anchor_takes_first_unplayed_entry_of_song():
    liste = _Liste([_eintrag(1), _eintrag(2, played=True), _eintrag(2), _eintrag(2)])
    assert liste.anchor_to_song(2) == 2
    assert liste._current_index == 2


def test_anchor_unknown_song_keeps_index():
    liste = _Liste([_eintrag(1, played=True)])
    assert liste.anchor_to_song(1) == -1
    assert liste.anchor_to_song(99) == -1
    assert liste._current_index == -1


def test_replace_shown_song_shows_fresh_rating(keep):
    from PySide6.QtWidgets import QComboBox, QSpinBox
    from songdata_widget import SongDataWidget

    class _Dock:
        shown_song = SongDataWidget.shown_song
        replace_shown_song = SongDataWidget.replace_shown_song

        def __init__(self):
            self._current_song = SimpleNamespace(id=3, quality=1, err=0)
            self.spin_quality = keep(QSpinBox())
            self.combo_err = keep(QComboBox())
            for v in (0, 1, 2):
                self.combo_err.addItem(str(v), v)

    dock = _Dock()
    fresh = SimpleNamespace(id=3, quality=4, err=2)
    dock.replace_shown_song(fresh)
    assert dock.shown_song is fresh
    assert dock.spin_quality.value() == 4
    assert dock.combo_err.currentData() == 2
