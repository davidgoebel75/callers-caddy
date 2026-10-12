"""Aktuelle Sitzung: Lokation an einer Stelle, Widgets hoeren zu (intern#142).

Geprueft wird an den vereinbarten Seams: CurrentSession meldet einen
Lokationswechsel, und ein Widget, das erst danach entsteht, uebernimmt die
aktuelle Lokation selbst — ohne Zwischenspeicher in main.py. Beobachtet wird
das, was der Caller sieht (Notizliste, Tips-Zahl, heutiges Tempo).
"""
from types import SimpleNamespace

import pytest
import shiboken6

from current_session import CurrentSession


@pytest.fixture
def keep(qapp):
    """Raeumt Widgets, Sitzung und Test-DB am Testende gezielt ab. Bleiben sie
    liegen, sammelt ein spaeterer gc.collect() sie an zufaelliger Stelle ein —
    bei David brach so die volle Suite mit 0xc0000374 ab (PR #119)."""
    objs = []

    def _keep(obj):
        objs.append(obj)
        return obj
    yield _keep
    # Aufgeschobene Aufrufe der Widgets (QTimer.singleShot) noch zu Lebzeiten
    # abarbeiten, sonst laufen sie spaeter gegen geloeschte Objekte
    qapp.processEvents()
    for obj in reversed(objs):   # erst die Widgets, dann Sitzung bzw. DB
        if hasattr(obj, "_conn"):
            obj.close()
        else:
            shiboken6.delete(obj)


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

    def set_today_tempo(self, factor):
        self.today_tempo = factor
