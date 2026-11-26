"""Leere Sequenzliste im Sequenz-Detail (intern#270).

Liefert der Filter keine Sequenz mehr, darf current_calls() nicht die vorige
Sequenz melden: Square Flow rechnete sie sonst ohne ID neu ("Analyse seq=-").
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


def _buttons(w):
    return [b.isEnabled() for b in (w._btn_prev, w._btn_next, w._btn_delete,
                                    w._btn_edit, w._btn_to_notes)]


def test_filter_ohne_treffer_leert_calls(db, keep):
    a = db.insert_sequence(["Heads Square Thru 4", "Allemande Left"])
    b = db.insert_sequence(["Sides Square Thru 4"])
    w = keep(SequenceViewWidget(db=db))
    w.set_sequence(db, [a, b], 0)
    assert w.current_calls() == ["Heads Square Thru 4", "Allemande Left"]

    w.set_sequence(db, [], 0)                       # Filter ohne Treffer
    assert w.current_calls() == []
    assert w.current_sequence_id() is None
    assert w._lbl_pos.text() == "0 / 0"
    assert _buttons(w) == [False] * 5

    w.set_sequence(db, [b], 0)                      # wieder mit Treffer
    assert w.current_calls() == ["Sides Square Thru 4"]
    assert _buttons(w)[2:] == [True] * 3


def test_letzte_sequenz_geloescht_gleich_leerer_filter(db, keep):
    a = db.insert_sequence(["Heads Square Thru 4"])
    w = keep(SequenceViewWidget(db=db))
    w.set_sequence(db, [a], 0)
    changed = []
    w.on_sequences_changed = lambda *a_: changed.append(1)
    w.remove_id_after_delete(a)
    assert w.current_calls() == [] and w._lbl_pos.text() == "0 / 0"
    assert _buttons(w) == [False] * 5
    assert changed                                  # Liste geaendert gemeldet


def test_square_flow_rechnet_bei_leerer_liste_nicht(db, keep):
    """Verdrahtet wie main._push_sequence_to_square_flow: kein Auftrag ohne Sequenz."""
    # Mit Typ: alt (calls, "Hoedown") und neu ([], "") unterscheiden sich, ohne
    # den Fix wuerde Square Flow die alten Calls also als neue Sequenz rechnen.
    a = db.insert_sequence(["Heads Square Thru 4", "Allemande Left"],
                           seq_type="Hoedown")
    view = keep(SequenceViewWidget(db=db))
    flow = keep(SquareFlowWidget(settings=_Settings(enabled=True)))
    jobs = []

    class _Worker:
        def request(self, *args, **kw):
            jobs.append((args, kw))

    flow._worker = _Worker()
    view.on_current_sequence_changed = lambda: flow.set_sequence(
        view.current_calls(), view.current_sequence_type(),
        seq_id=view.current_sequence_id())
    view.set_sequence(db, [a], 0)
    assert len(jobs) == 1 and jobs[0][1]["seq_id"] == a
    view.set_sequence(db, [], 0)
    assert len(jobs) == 1                           # kein Lauf "seq=-"
    assert flow._seq is None


def test_leere_liste_raeumt_kopfzeile_und_warnknopf_auf(db, keep):
    """Review #203: Kopfzeile (Text, Tooltip) und Square-Flow-Warnknopf der
    vorigen Sequenz duerfen bei leerer Liste nicht stehen bleiben."""
    calls = ["Heads Square Thru 4", "Allemande Left"]
    a = db.insert_sequence(calls, seq_type="Hoedown", difficulty="leicht")
    for leeren in ("filter", "loeschen"):
        w = keep(SequenceViewWidget(db=db))
        w.set_taminations_enabled(True)
        w.set_sequence(db, [a], 0)
        w.set_flow_info(calls, {"beats": [8, 8], "total": 16, "singer": False,
                                "fail_card": None, "warn": True,
                                "warn_text": "Testwarnung"})
        assert "Hoedown" in w._header_text
        assert not w._btn_flow_warn.isHidden()

        if leeren == "filter":
            w.set_sequence(db, [], 0)
        else:
            w.remove_id_after_delete(a)
        assert w._header_text == "" and w._lbl_header.text() == ""
        assert w._lbl_header.toolTip() == ""
        assert w._btn_flow_warn.isHidden()
        assert w.current_sequence_type() == ""
