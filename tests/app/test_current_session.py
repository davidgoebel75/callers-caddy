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


# ---- Tanzprogramm-Wahl ----------------------------------------------------------

def test_set_program_ids_notifies_listeners(session):
    seen = []
    session.program_ids_changed.connect(seen.append)
    session.set_program_ids([3, 1])
    assert session.program_ids == [3, 1]
    assert seen == [[3, 1]]


def test_no_program_choice_is_empty_list(session):
    assert session.program_ids == []


def test_program_ids_is_a_copy(session):
    session.set_program_ids([2])
    session.program_ids.append(99)
    assert session.program_ids == [2]


def test_set_program_ids_copies_input(session):
    ids = [2, 4]
    session.set_program_ids(ids)
    ids.append(7)
    assert session.program_ids == [2, 4]


def test_set_program_ids_none_means_empty(session):
    session.set_program_ids([5])
    seen = []
    session.program_ids_changed.connect(seen.append)
    session.set_program_ids(None)
    assert seen == [[]]
    assert session.program_ids == []


def test_same_program_ids_notify_again(session):
    """Reihenfolge und Doppelte bleiben, jedes Setzen meldet."""
    seen = []
    session.program_ids_changed.connect(seen.append)
    session.set_program_ids([4, 4, 1])
    session.set_program_ids([4, 4, 1])
    assert seen == [[4, 4, 1], [4, 4, 1]]


# ---- Tanzprogramm-Wahl: Sequenzen, Sequenz-Detail, Player ------------------------

MS, PLUS = 1, 3          # Seed-IDs: Mainstream (Band 29), Plus (Band 39)


@pytest.fixture
def seq_db(tmp_path, keep):
    from song_db import SongDatabase
    d = keep(SongDatabase(str(tmp_path / "t.db")))
    d.set_call_text_figures("Swing Thru", ["call_swing_thru"], mapped_by="manual")
    d.insert_sequence(["Swing Thru"])
    d.recompute_sequence_max_to()
    return d


def test_sequences_created_later_take_choice_without_loading(session, keep, seq_db):
    """Beim Start nur Baender setzen: das Laden macht _init_sequences nach show()."""
    from sequences_widget import SequencesWidget
    session.set_program_ids([MS])
    w = keep(SequencesWidget(seq_db, session=session))
    assert w._program_bands == {29}
    assert w._table.rowCount() == 0


def test_sequences_follow_choice(session, keep, seq_db, qapp):
    from sequences_widget import SequencesWidget
    w = keep(SequencesWidget(seq_db, session=session))
    session.set_program_ids([PLUS])
    qapp.processEvents()         # Slot ist per singleShot(0) entkoppelt (Audio-Regel)
    assert w._program_bands == {39}
    session.set_program_ids([])
    qapp.processEvents()
    assert w._program_bands is None


def test_sequences_deferred_slot_reads_latest_choice(session, keep, seq_db, qapp):
    """Mehrfaches Setzen vor dem Abarbeiten: es gilt die letzte Wahl."""
    from sequences_widget import SequencesWidget
    w = keep(SequencesWidget(seq_db, session=session))
    session.set_program_ids([PLUS])
    session.set_program_ids([MS])
    qapp.processEvents()
    assert w._program_bands == {29}


def test_sequence_view_created_later_takes_choice(session, keep, seq_db):
    from sequences_widget import SequenceViewWidget
    session.set_program_ids([PLUS])
    v = keep(SequenceViewWidget(seq_db, session=session))
    assert v._program_bands == {39}


def test_sequence_view_follows_choice(session, keep, seq_db):
    from sequences_widget import SequenceViewWidget
    v = keep(SequenceViewWidget(seq_db, session=session))
    session.set_program_ids([MS])
    assert v._program_bands == {29}


class _ProgramDB:
    def get_all_dance_programs(self):
        return [(MS, "MS", "Mainstream", 30, 7.0, 29.999999),
                (PLUS, "PL", "Plus", 60, 7.0, 39.999999)]


def _player(session, keep, db=None):
    from player_widget import PlayerWidget
    p = keep(PlayerWidget(engine=_TempoEngine(), paths=None, session=session))
    p._db = db
    return p


def test_player_shows_top_program_of_choice(session, keep):
    player = _player(session, keep, _ProgramDB())
    session.set_program_ids([MS, PLUS])
    assert (player._dance_program_id, player._dance_program_code) == (PLUS, "PL")
    session.set_program_ids([])
    assert (player._dance_program_id, player._dance_program_code) == (None, "")


def test_player_without_db_ignores_choice(session, keep):
    player = _player(session, keep)
    session.set_program_ids([MS])
    assert player._dance_program_id is None


def test_player_applies_choice_made_before_db_was_set(session, keep):
    """Start: die Wahl steht schon in der Sitzung, die DB kommt spaeter."""
    session.set_program_ids([MS])
    player = _player(session, keep)
    player._db = _ProgramDB()
    player.apply_program_selection()
    assert player._dance_program_code == "MS"


def test_player_reports_program_change_to_main(session, keep):
    player = _player(session, keep, _ProgramDB())
    seen = []
    player.on_dance_program_changed = seen.append
    session.set_program_ids([PLUS])
    assert seen == ["PL"]


# ---- Tanzprogramm-Wahl: INI im Hauptfenster -------------------------------------

class _CountingSettings:
    """QSettings auf tmp_path, zaehlt die sync()-Aufrufe."""

    def __init__(self, ini):
        from PySide6.QtCore import QSettings
        self.q = QSettings(str(ini), QSettings.IniFormat)
        self.syncs = 0

    def value(self, key, default=None):
        return self.q.value(key, default)

    def setValue(self, key, val):
        self.q.setValue(key, val)

    def sync(self):
        self.syncs += 1
        self.q.sync()


def _ini_window(tmp_path, keep, stored=None):
    import main
    settings = _CountingSettings(tmp_path / "t.ini")
    keep(settings.q)
    if stored is not None:
        settings.q.setValue("sequences/dance_programs", stored)
    win = SimpleNamespace(_settings=settings)
    win.on_changed = lambda ids: main.P29MainWindow._on_program_ids_changed(win, ids)
    return win, settings


def test_program_choice_is_written_to_ini(keep, tmp_path):
    win, settings = _ini_window(tmp_path, keep)
    win.on_changed([3, 1])
    assert settings.value("sequences/dance_programs") == "3,1"
    # intern#268: Die Datei wird erst nach dem Wechsel geschrieben, nicht mittendrin
    assert settings.syncs == 0
    from PySide6.QtCore import QCoreApplication
    QCoreApplication.processEvents()
    assert settings.syncs == 1


def test_program_choice_not_written_twice(keep, tmp_path):
    """Kam der Wert aus dem Einstellungsfenster, steht er schon in der INI."""
    win, settings = _ini_window(tmp_path, keep, stored="3,1")
    win.on_changed([3, 1])
    assert settings.syncs == 0


def test_empty_choice_clears_ini(keep, tmp_path):
    win, settings = _ini_window(tmp_path, keep, stored="3")
    win.on_changed([])
    assert settings.value("sequences/dance_programs") == ""
