"""Sequenz loeschen im Sequenz-Detail (intern#275).

Nach dem Loeschen zeigt das Detail die naechste Sequenz oder ist leer. Den Wechsel
muss es melden, sonst tanzt Square Flow weiter die geloeschte Sequenz und das
Lyric-Feld bleibt stehen. Ohne Sequenz ist auch "Taminations" gesperrt.
"""
import pytest

from sequences_widget import SequenceViewWidget
from caddy.choreo.square_flow_widget import SquareFlowWidget


class _Settings:
    def __init__(self, **vals):
        self.vals = {f"square_flow/{k}": v for k, v in vals.items()}

    def value(self, key, default=None, type=None):
        return self.vals.get(key, default)


@pytest.fixture
def db(tmp_path, keep):
    from song_db import SongDatabase

    return keep(SongDatabase(str(tmp_path / "test.db")))


def _verdrahtet(db, keep):
    """Sequenz-Detail und Square Flow wie main._push_sequence_to_square_flow."""
    view = keep(SequenceViewWidget(db=db))
    flow = keep(SquareFlowWidget(settings=_Settings(enabled=True)))
    jobs = []

    class _Worker:
        def request(self, *args, **kw):
            jobs.append((args, kw))

    flow._worker = _Worker()
    meldungen = []

    def gewechselt():
        meldungen.append(view.current_sequence_id())
        flow.set_sequence(view.current_calls(), view.current_sequence_type(),
                          seq_id=view.current_sequence_id())

    view.on_current_sequence_changed = gewechselt
    return view, flow, jobs, meldungen


def test_loeschen_meldet_die_naechste_sequenz(db, keep):
    a = db.insert_sequence(["Heads Square Thru 4", "Allemande Left"], seq_type="Hoedown")
    b = db.insert_sequence(["Sides Square Thru 4", "Right And Left Grand"],
                           seq_type="Hoedown")
    view, flow, jobs, meldungen = _verdrahtet(db, keep)
    view.set_sequence(db, [a, b], 0)
    assert flow._seq[0] == ("Heads Square Thru 4", "Allemande Left")
    meldungen.clear()

    db.delete_sequences([a])
    view.remove_id_after_delete(a)
    assert meldungen == [b]                                   # Wechsel gemeldet
    assert flow._seq[0] == ("Sides Square Thru 4", "Right And Left Grand")
    assert jobs[-1][1]["seq_id"] == b                         # Square Flow rechnet b


def test_letzte_geloescht_square_flow_zeigt_keine_sequenz(db, keep):
    a = db.insert_sequence(["Heads Square Thru 4", "Allemande Left"], seq_type="Hoedown")
    view, flow, jobs, meldungen = _verdrahtet(db, keep)
    view.set_sequence(db, [a], 0)
    assert flow._seq is not None
    n_jobs = len(jobs)
    meldungen.clear()

    db.delete_sequences([a])
    view.remove_id_after_delete(a)
    assert meldungen == [None]                                # Wechsel auf "leer" gemeldet
    assert flow._seq is None                                  # keine Sequenz mehr
    assert len(jobs) == n_jobs                                # kein neuer Lauf


def test_taminations_ohne_sequenz_gesperrt(db, keep):
    a = db.insert_sequence(["Heads Square Thru 4", "Allemande Left"])
    w = keep(SequenceViewWidget(db=db))
    w.set_sequence(db, [a], 0)
    w.set_taminations_enabled(True, online=True)
    assert w._btn_tam.isEnabled()

    w.set_sequence(db, [], 0)                                 # Filter ohne Treffer
    assert not w._btn_tam.isEnabled()
    w.set_taminations_enabled(True, online=True)              # z. B. Online-Wechsel
    assert not w._btn_tam.isEnabled()

    w.set_sequence(db, [a], 0)                                # wieder mit Treffer
    assert w._btn_tam.isEnabled()
    w.remove_id_after_delete(a)                               # letzte geloescht
    assert not w._btn_tam.isEnabled()


def test_taminations_offline_bleibt_gesperrt(db, keep):
    a = db.insert_sequence(["Heads Square Thru 4"])
    w = keep(SequenceViewWidget(db=db))
    w.set_taminations_enabled(True, online=False)
    w.set_sequence(db, [a], 0)                                # Liste da, aber offline
    assert not w._btn_tam.isEnabled()
