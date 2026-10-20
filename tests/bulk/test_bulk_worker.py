"""BulkWorker: Signale und Verbindung, run() synchron (intern#139)."""
import contextlib
import io

from caddy.bulk.bulk_worker import BulkWorker

JOBS = [(1, "a", "A"), (2, "b", "B")]


class FakeConn:
    closed = False

    def commit(self):
        pass

    def rollback(self):
        pass

    def close(self):
        self.closed = True


def _collect(worker):
    events = []
    worker.progress.connect(lambda c, t, n: events.append(("progress", c, t, n)))
    worker.finished.connect(lambda d, s: events.append(("finished", d, s)))
    worker.error.connect(lambda m: events.append(("error", m)))
    with contextlib.redirect_stdout(io.StringIO()):
        worker.run()
    return events


def test_signals_in_order_and_connection_closed(keep):
    conn = FakeConn()
    w = keep(BulkWorker(JOBS, lambda c, j: j[0] == 1, lambda: conn,
                        name_of=lambda j: j[2], label="T"))
    assert _collect(w) == [("progress", 1, 2, "A"), ("progress", 2, 2, "B"),
                           ("finished", 1, 1)]
    assert conn.closed


def test_connection_error_emits_error_and_finished(keep):
    def boom():
        raise RuntimeError("gesperrt")
    w = keep(BulkWorker(JOBS, lambda c, j: True, boom, label="T"))
    assert _collect(w) == [("error", "gesperrt"), ("finished", 0, 0)]


def test_cancel_property_and_stop(keep):
    conn = FakeConn()
    w = keep(BulkWorker(JOBS, lambda c, j: True, lambda: conn, label="T"))
    assert w.cancelled is False
    w.cancel()
    assert w.cancelled is True
    assert _collect(w) == [("finished", 0, 0)]
    assert conn.closed
