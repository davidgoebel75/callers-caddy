"""Hintergrund-Lesen fuer Sequenzfenster und Sequenz-Detail (intern#268).

Der Worker nutzt dieselben Funktionen der DB-Schicht wie der Hauptthread, auf
einer Verbindung aus open_worker_connection. Uebernommen wird nur bei passender
Datenversion; ohne Worker bleibt alles wie bisher (Rueckfall).
"""
import time

import pytest

import song_db_sequences
from caddy.sequences.prefetch_worker import SequencePrefetchWorker
from sequences_widget import SequenceViewWidget

MAPPED = "Swing Thru"


@pytest.fixture
def db(tmp_path, keep):
    from song_db import SongDatabase

    d = keep(SongDatabase(str(tmp_path / "t.db")))
    eid = d.get_teaching_order_calls()[0][0]
    d.set_call_text_figures(MAPPED, [eid], mapped_by="manual")
    d.ids = [d.insert_sequence([MAPPED, f"Call {i}"]) for i in range(6)]
    d.recompute_sequence_max_to()
    return d


@pytest.fixture
def worker(db, keep):
    w = SequencePrefetchWorker(db.open_worker_connection)
    yield w
    w.shutdown()


def _wait(qapp, cond, timeout=10.0):
    end = time.perf_counter() + timeout
    while time.perf_counter() < end:
        qapp.processEvents()
        if cond():
            return True
        time.sleep(0.005)
    return False


# ---- DB-Schicht -------------------------------------------------------------

def test_figuren_auf_worker_verbindung_gleich_hauptthread(db):
    conn = db.open_worker_connection()
    try:
        ver, figs = db.build_sequence_figures_on_connection(conn)
    finally:
        conn.close()
    db.invalidate_band_cache()
    assert figs == db._sequence_figures()
    assert ver == db.sequence_data_version()


def test_uebernahme_nur_bei_passender_version(db):
    db.invalidate_band_cache()
    ver = db.sequence_data_version()
    assert not db.has_sequence_figures()
    assert not db.adopt_sequence_figures(ver - 1, {})          # veraltet
    assert not db.has_sequence_figures()
    assert db.adopt_sequence_figures(ver, {1: frozenset()})
    assert db.has_sequence_figures()
    assert not db.adopt_sequence_figures(ver, {})              # schon da
    db.insert_sequence([MAPPED])                               # Daten aendern sich
    assert not db.has_sequence_figures()


def test_cover_nach_uebernahme_ohne_aufbau_im_hauptthread(db, monkeypatch):
    conn = db.open_worker_connection()
    try:
        ver, figs = db.build_sequence_figures_on_connection(conn)
    finally:
        conn.close()
    db.invalidate_band_cache()
    expected = db._cover_ids(frozenset({10, 20, 30, 40, 50, 60}))
    db.invalidate_band_cache()
    db._conn.execute("DELETE FROM _band_cover")                # kein persistenter Treffer
    db._conn.commit()
    assert db.adopt_sequence_figures(ver, figs)
    monkeypatch.setattr(song_db_sequences, "_build_sequence_figures",
                        lambda conn: pytest.fail("Aufbau im Hauptthread"))
    assert db._cover_ids(frozenset({10, 20, 30, 40, 50, 60})) == expected


def test_ohne_vorbau_rechnet_der_hauptthread_wie_bisher(db):
    db.invalidate_band_cache()
    db._conn.execute("DELETE FROM _band_cover")                # kein persistenter Treffer
    db._conn.commit()
    assert not db.has_sequence_figures()                       # gleicht auch die Version ab
    db._cover_ids(frozenset({10, 20, 30, 40, 50, 60}))         # Rueckfall: baut selbst
    assert db.has_sequence_figures()


def test_details_auf_worker_verbindung_gleich_hauptthread(db):
    conn = db.open_worker_connection()
    try:
        many = db.sequence_details_on_connection(conn, db.ids)
    finally:
        conn.close()
    assert many == db.get_sequence_details_many(db.ids)


def test_enthaelt_calls_aus_dem_speicher(db):
    first = db.get_teaching_order_calls()
    other_eid = first[1][0]
    first.clear()                                              # Kopie, Speicher bleibt
    assert db.get_teaching_order_calls()
    calls = []
    db._conn.set_trace_callback(calls.append)
    try:
        db.get_teaching_order_calls()
        assert not any("teaching_order_calls" in c for c in calls)
        old = db._to_calls[0]
        db.set_call_text_figures("Neuer Text", [other_eid])
        calls.clear()
        db.get_teaching_order_calls()                          # Zaehler gestiegen
        assert db._to_calls[0] != old
        assert any("teaching_order_calls" in c for c in calls)
    finally:
        db._conn.set_trace_callback(None)


# ---- Worker ---------------------------------------------------------------

def test_worker_baut_figuren_vor(db, worker, qapp):
    db.invalidate_band_cache()
    got = []
    worker.figures_ready.connect(lambda res: got.append(db.adopt_sequence_figures(*res)))
    worker.request_figures()
    assert _wait(qapp, lambda: got)
    assert got == [True] and db.has_sequence_figures()


def test_detail_liest_im_hauptthread_nur_die_gezeigte(db, worker, keep, qapp, monkeypatch):
    view = keep(SequenceViewWidget(db=db))
    view.set_prefetch_worker(worker)
    main_reads = []
    orig = db.get_sequence_details_many
    monkeypatch.setattr(db, "get_sequence_details_many",
                        lambda ids: main_reads.append(list(ids)) or orig(ids))
    view.set_sequence(db, db.ids, 2)
    assert main_reads == [[db.ids[2]]]
    assert view.current_calls() == [MAPPED, "Call 2"]
    assert _wait(qapp, lambda: set(db.ids) <= set(view._details))
    main_reads.clear()
    for _ in range(3):
        view._on_next()
    assert main_reads == []                                    # alles aus dem Speicher
    assert view.current_calls() == [MAPPED, "Call 5"]


def test_veraltetes_worker_ergebnis_wird_verworfen(db, worker, keep):
    view = keep(SequenceViewWidget(db=db))
    view.set_prefetch_worker(worker)
    view.set_sequence(db, db.ids[:2], 0)
    old_token = view._prefetch_token
    view.set_sequence(db, db.ids[2:4], 0)
    fake = {db.ids[5]: (("x",), "", "")}
    view._on_details_ready(old_token, view._details_ver, fake)     # andere Liste
    view._on_details_ready(view._prefetch_token, -1, fake)        # andere Version
    assert db.ids[5] not in view._details


def test_ohne_worker_liest_der_hauptthread_die_liste_wie_bisher(db, keep, monkeypatch):
    view = keep(SequenceViewWidget(db=db))
    reads = []
    orig = db.get_sequence_details_many
    monkeypatch.setattr(db, "get_sequence_details_many",
                        lambda ids: reads.append(list(ids)) or orig(ids))
    view.set_sequence(db, db.ids, 0)
    assert reads == [db.ids]
