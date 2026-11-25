"""Speicher der Sequenz-Daten im Sequenz-Detail (intern#263).

Calls mit Teaching-Orders, Typ und Schwierigkeit der Liste werden beim Setzen
der Liste auf einmal gelesen; der Wechsel liest dann nicht mehr einzeln.
"""
import pytest

from sequences_widget import SequenceViewWidget


@pytest.fixture
def db(tmp_path, keep):
    from song_db import SongDatabase

    return keep(SongDatabase(str(tmp_path / "test.db")))


def _add(db, calls, seq_type="", difficulty=""):
    sid = db.insert_sequence(calls)
    db._conn.execute("UPDATE sequences SET type = ?, difficulty = ? WHERE id = ?",
                     (seq_type, difficulty, sid))
    db._conn.commit()
    return sid


def test_sammelabfrage_gleich_einzelabfrage(db):
    eid = db._conn.execute("SELECT entity_id FROM calls LIMIT 1").fetchone()[0]
    assert eid
    a = _add(db, ["Square Thru 4", "Unbekannter Text"], "Singer", "leicht")
    b = _add(db, ["Square Thru 4"])
    db.set_call_text_mappings([("Square Thru 4", eid)])
    many = db.get_sequence_details_many([a, b, 99999])
    assert set(many) == {a, b}                       # fehlende Sequenz fehlt
    # Regel "niedrigstes Band je Call-Text" (intern#87) wie die fruehere
    # Einzelabfrage in SQL; get_sequence_calls laeuft seit Review #196 ueber
    # get_sequence_details_many, der Vergleich damit allein waere leer.
    best = db._conn.execute(
        "SELECT m.entity_id, t.teaching_order, t.canonical_name "
        "FROM call_text_mappings m "
        "LEFT JOIN teaching_order_calls t ON t.entity_id = m.entity_id "
        "WHERE m.call_text = ? ORDER BY t.teaching_order LIMIT 1",
        ("Square Thru 4",)).fetchone()
    assert many[a][0][0][2:5] == tuple(best)
    assert many[a][0][1][1:5] == ("Unbekannter Text", None, None, None)
    assert db.get_sequence_calls(99999) == []
    for sid in (a, b):
        calls, seq_type, difficulty = many[sid]
        assert calls == db.get_sequence_calls(sid)
        raw = db.get_sequence_raw(sid)
        assert (seq_type or "") == raw["seq_type"]
        assert (difficulty or "") == raw["difficulty"]


def test_wechsel_liest_nicht_mehr_einzeln(db, keep, monkeypatch):
    ids = [_add(db, [f"Call {i}"], "Singer") for i in range(5)]
    w = keep(SequenceViewWidget(db=db))
    w.set_sequence(db, ids, 0)
    einzeln = []
    monkeypatch.setattr(db, "get_sequence_calls",
                        lambda sid: einzeln.append(sid) or [])
    monkeypatch.setattr(db, "get_sequence_raw",
                        lambda sid: einzeln.append(sid) or {})
    for _ in range(4):
        w.advance()
    assert einzeln == []
    assert w.current_calls() == ["Call 4"]


def test_aenderung_am_mapping_verwirft_den_speicher(db, keep):
    eid = db._conn.execute("SELECT entity_id FROM calls LIMIT 1").fetchone()[0]
    assert eid
    sid = _add(db, ["Mein Text"])
    w = keep(SequenceViewWidget(db=db))
    w.set_sequence(db, [sid], 0)
    assert w._calls[0][2] is None                    # noch ohne Zuordnung
    db.set_call_text_mappings([("Mein Text", eid)])  # Trigger erhoeht den Zaehler
    w._update_content()
    assert w._calls[0][2] == eid


def test_grosse_liste_in_abschnitten(db, keep, monkeypatch):
    ids = [_add(db, [f"C{i}"]) for i in range(7)]
    w = keep(SequenceViewWidget(db=db))
    monkeypatch.setattr(SequenceViewWidget, "_PRELOAD_MAX", 3)
    monkeypatch.setattr(SequenceViewWidget, "_CHUNK", 2)
    w.set_sequence(db, ids, 0)
    assert set(w._details) == {ids[0], ids[1]}
    w.advance()
    w.advance()                                      # Luecke -> naechster Abschnitt
    assert w.current_calls() == ["C2"]
    assert {ids[2], ids[3]} <= set(w._details)


def test_fehlende_sequenz_wird_nicht_immer_neu_gefragt(db, keep, monkeypatch):
    """Review #196: _detail merkt sich auch Sequenzen, die es nicht gibt."""
    sid = _add(db, ["C0"])
    w = keep(SequenceViewWidget(db=db))
    w.set_sequence(db, [sid, 99999], 0)
    fragen = []
    many = db.get_sequence_details_many
    monkeypatch.setattr(db, "get_sequence_details_many",
                        lambda ids: fragen.append(list(ids)) or many(ids))
    for _ in range(3):
        assert w._detail(99999) == SequenceViewWidget._NO_DETAIL
    assert fragen == []
