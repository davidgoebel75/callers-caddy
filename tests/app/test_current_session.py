"""Aktuelle Sitzung: Lokation an einer Stelle, Widgets hoeren zu (intern#142).

Geprueft wird an den vereinbarten Seams: CurrentSession meldet einen
Lokationswechsel, und ein Widget, das erst danach entsteht, uebernimmt die
aktuelle Lokation selbst — ohne Zwischenspeicher in main.py. Beobachtet wird
das, was der Caller sieht (Notizliste, Tips-Zahl, heutiges Tempo).
"""
from types import SimpleNamespace

from current_session import CurrentSession


def _loc(loc_id=1, name="Club", **kw):
    fields = dict(id=loc_id, name=name, planned_tips=None, temp_tempo=None,
                  has_target_bpm=False, target_bpm=None)
    fields.update(kw)
    return SimpleNamespace(**fields)


def test_set_location_notifies_listeners(qapp):
    session = CurrentSession()
    seen = []
    session.location_changed.connect(seen.append)
    loc = _loc(5)
    session.set_location(loc)
    assert session.location is loc
    assert session.location_id == 5
    assert seen == [loc]


def test_no_location_has_no_id(qapp):
    assert CurrentSession().location_id is None


def test_same_location_notifies_again(qapp):
    """Im Dialog geaenderte Lokation (z. B. Tips-Zahl) wirkt sofort."""
    session = CurrentSession()
    seen = []
    session.location_changed.connect(seen.append)
    loc = _loc()
    session.set_location(loc)
    session.set_location(loc)
    assert seen == [loc, loc]


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


def test_notes_created_later_show_current_location(qapp):
    from notes_widget import NotesWidget
    session = CurrentSession()
    session.set_location(_loc(7))
    notes = NotesWidget(_NotesDB(), session=session)
    assert _note_texts(notes) == ["Notiz 7"]


def test_notes_follow_location_change(qapp):
    from notes_widget import NotesWidget
    session = CurrentSession()
    notes = NotesWidget(_NotesDB(), session=session)
    session.set_location(_loc(3))
    assert _note_texts(notes) == ["Notiz 3"]


# ---- Abendplaner ----------------------------------------------------------------

def _planner(tmp_path, session):
    from song_db import SongDatabase
    from evening_planner_widget import EveningPlannerWidget
    return EveningPlannerWidget(SongDatabase(str(tmp_path / "t.db")), session=session)


def test_planner_created_later_takes_planned_tips(qapp, tmp_path):
    session = CurrentSession()
    session.set_location(_loc(planned_tips=6))
    planner = _planner(tmp_path, session)
    assert planner._spin_tips.value() == 6


def test_planner_follows_planned_tips(qapp, tmp_path):
    session = CurrentSession()
    planner = _planner(tmp_path, session)
    session.set_location(_loc(planned_tips=9))
    assert planner._spin_tips.value() == 9


# ---- Player ---------------------------------------------------------------------

def test_player_applies_location_tempo(qapp):
    """Temporaeres Tempo der Lokation (BL-086) setzt der Player selbst."""
    from player_widget import PlayerWidget
    session = CurrentSession()
    player = PlayerWidget(engine=None, paths=None, session=session)
    session.set_location(_loc(temp_tempo=94))
    assert player.spin_today_tempo.value() == 94
