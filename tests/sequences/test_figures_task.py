"""Figuren nach Datenaenderungen neu vorbauen, Pull-Verfahren (intern#274).

pull() stoesst den Vorbau nur an, wenn die Figuren veraltet sind, der Trigger-
Zaehler seit dem letzten Pull stillsteht und kein Vorbau unterwegs ist.
"""
import time

import pytest

from caddy.sequences.figures_task import FiguresPrefetchTask
from caddy.sequences.prefetch_worker import SequencePrefetchWorker

MAPPED = "Swing Thru"


@pytest.fixture
def db(tmp_path, keep):
    from song_db import SongDatabase

    d = keep(SongDatabase(str(tmp_path / "t.db")))
    eid = d.get_teaching_order_calls()[0][0]
    d.set_call_text_figures(MAPPED, [eid], mapped_by="manual")
    d.ids = [d.insert_sequence([MAPPED, f"Call {i}"]) for i in range(4)]
    d.recompute_sequence_max_to()
    return d


class _Worker:
    def __init__(self):
        self.requests = 0
        self.pending = False

    def figures_pending(self):
        return self.pending

    def request_figures(self):
        self.requests += 1


def _figuren_da(db):
    """Figuren fuer den aktuellen Datenstand aufbauen (wie nach einem Vorbau)."""
    db.has_sequence_figures()                          # Cache-Stand abgleichen
    db._sequence_figures()
    assert db.has_sequence_figures()


def _wait(qapp, cond, timeout=10.0):
    end = time.perf_counter() + timeout
    while time.perf_counter() < end:
        qapp.processEvents()
        if cond():
            return True
        time.sleep(0.005)
    return False


def test_ohne_figuren_und_ruhige_daten_wird_vorgebaut(db):
    db.invalidate_band_cache()
    w = _Worker()
    task = FiguresPrefetchTask(db, w)
    assert task.pull() is True
    assert w.requests == 1


def test_mit_passenden_figuren_nichts_zu_tun(db):
    _figuren_da(db)
    w = _Worker()
    task = FiguresPrefetchTask(db, w)
    for _ in range(3):
        assert task.pull() is False
    assert w.requests == 0


def test_nach_datenaenderung_erst_wenn_der_zaehler_stillsteht(db):
    _figuren_da(db)
    w = _Worker()
    task = FiguresPrefetchTask(db, w)
    db.insert_sequence([MAPPED, "Neu"])                # z. B. Import, Zaehler steigt
    assert not db.has_sequence_figures()
    assert task.pull() is False                        # Zaehler hat sich bewegt
    assert w.requests == 0
    assert task.pull() is True                         # steht still: jetzt vorbauen
    assert w.requests == 1


def test_waehrend_eines_imports_wartet_der_pull(db):
    _figuren_da(db)
    w = _Worker()
    task = FiguresPrefetchTask(db, w)
    for i in range(3):                                 # zwischen jedem Pull ein Schreiben
        db.insert_sequence([MAPPED, f"Import {i}"])
        assert task.pull() is False
    assert w.requests == 0
    assert task.pull() is True


def test_kein_zweiter_auftrag_solange_einer_unterwegs_ist(db):
    db.invalidate_band_cache()
    w = _Worker()
    w.pending = True
    task = FiguresPrefetchTask(db, w)
    assert task.pull() is False
    assert w.requests == 0


def test_mit_echtem_worker_nach_aenderung_wieder_figuren(db, keep, qapp):
    """Ganzer Weg: Daten aendern, zweimal ziehen, Worker baut, Hauptthread uebernimmt."""
    worker = SequencePrefetchWorker(db.open_worker_connection)
    try:
        worker.figures_ready.connect(lambda res: db.adopt_sequence_figures(*res))
        _figuren_da(db)
        task = FiguresPrefetchTask(db, worker)
        db.insert_sequence([MAPPED, "Neu"])
        task.pull()
        assert task.pull() is True
        assert _wait(qapp, db.has_sequence_figures)
        assert _wait(qapp, lambda: not worker.figures_pending())
        assert task.pull() is False                    # erledigt, nichts mehr zu tun
    finally:
        worker.shutdown()


def test_figures_pending_bis_der_vorbau_fertig_ist(db, qapp):
    worker = SequencePrefetchWorker(db.open_worker_connection)
    try:
        assert worker.figures_pending() is False
        worker.request_figures()
        assert worker.figures_pending() is True
        assert _wait(qapp, lambda: not worker.figures_pending())
    finally:
        worker.shutdown()


def test_nach_shutdown_kein_figuren_signal(db, qapp, monkeypatch):
    """Review #204: Laeuft der Vorbau beim Beenden noch, darf danach kein Signal
    mehr kommen (die App schliesst dann schon DB und Engine)."""
    import song_db
    worker = SequencePrefetchWorker(db.open_worker_connection)
    orig = song_db.SongDatabase.build_sequence_figures_on_connection

    def langsam(conn):
        res = orig(conn)
        time.sleep(0.3)                                # Beenden faellt in den Aufbau
        return res

    monkeypatch.setattr(song_db.SongDatabase, "build_sequence_figures_on_connection",
                        staticmethod(langsam))
    got = []
    worker.figures_ready.connect(lambda res: got.append(res))
    worker.request_figures()
    time.sleep(0.1)
    worker.shutdown(wait=2.0)
    _wait(qapp, lambda: False, timeout=0.3)
    assert got == []
