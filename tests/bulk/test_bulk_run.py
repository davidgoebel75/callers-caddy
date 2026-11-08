"""run_bulk: Schleife der Massenlaeufe ohne Qt, mit Attrappen (intern#139)."""
import contextlib
import io

import pytest

from caddy.bulk.bulk_run import BulkCounts, BulkResult, run_bulk


class FakeConn:
    def __init__(self):
        self.calls = []

    def commit(self):
        self.calls.append("commit")

    def rollback(self):
        self.calls.append("rollback")


def _run(jobs, step, conn=None, is_cancelled=lambda: False, progress=None):
    conn = conn or FakeConn()
    with contextlib.redirect_stdout(io.StringIO()):
        res = run_bulk(jobs, step, conn=conn, is_cancelled=is_cancelled,
                       on_progress=(progress or (lambda *a: None)),
                       name_of=lambda j: j[2], label="Test")
    return res, conn


JOBS = [(1, "a", "A"), (2, "b", "B"), (3, "c", "C")]


def test_counts_done_and_skipped():
    res, _ = _run(JOBS, lambda c, j: j[0] != 2)
    assert res == BulkResult(done=2, skipped=1, cancelled=False)


def test_commit_only_for_done_jobs():
    _, conn = _run(JOBS, lambda c, j: j[0] != 2)
    assert conn.calls == ["commit", "commit"]


def test_exception_skips_rolls_back_and_continues():
    def step(c, j):
        if j[0] == 1:
            raise RuntimeError("kaputt")
        return True
    res, conn = _run(JOBS, step)
    assert res == BulkResult(done=2, skipped=1, cancelled=False)
    assert conn.calls == ["rollback", "commit", "commit"]


def test_cancel_between_jobs_keeps_done_count():
    seen = []

    def step(c, j):
        seen.append(j[0])
        return True
    res, _ = _run(JOBS, step, is_cancelled=lambda: len(seen) >= 2)
    assert res == BulkResult(done=2, skipped=0, cancelled=True)
    assert seen == [1, 2]


def test_progress_reported_in_order():
    got = []
    _run(JOBS, lambda c, j: True, progress=lambda i, n, name: got.append((i, n, name)))
    assert got == [(1, 3, "A"), (2, 3, "B"), (3, 3, "C")]


def test_rollback_failure_does_not_stop_run():
    class Dead(FakeConn):
        def rollback(self):
            raise RuntimeError("tot")

    def step(c, j):
        if j[0] == 1:
            raise ValueError("x")
        return True
    res, _ = _run(JOBS, step, conn=Dead())
    assert res.done == 2 and res.skipped == 1


def test_skipped_counts_every_skip():
    res, _ = _run(JOBS, lambda c, j: False)
    assert res == BulkResult(done=0, skipped=3, cancelled=False)


def test_cancel_stops_loop_even_if_flag_drops_again():
    calls = iter([False, True])
    res, _ = _run(JOBS + [(4, "d", "D")], lambda c, j: True,
                  is_cancelled=lambda: next(calls, False))
    assert res == BulkResult(done=1, skipped=0, cancelled=True)


def test_error_and_rollback_failure_are_logged_with_song_id():
    class Dead(FakeConn):
        def rollback(self):
            raise RuntimeError("tot")

    def step(c, j):
        raise ValueError("kaputt")
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        run_bulk([(7, "x")], step, conn=Dead(), is_cancelled=lambda: False,
                 on_progress=lambda *a: None, label="Test")
    assert out.getvalue().splitlines() == [
        "[Test] Fehler bei Song #7: kaputt",
        "[Test] Rollback fehlgeschlagen: tot"]


def test_default_name_is_empty():
    got = []
    run_bulk([(1,)], lambda c, j: True, conn=FakeConn(), is_cancelled=lambda: False,
             on_progress=lambda i, n, name: got.append(name))
    assert got == [""]


def test_counts_hold_state_when_loop_raises():
    """counts traegt den Stand auch, wenn run_bulk aussteigt (intern#239)."""
    counts = BulkCounts()

    def progress(i, n, name):
        if i == 3:
            raise RuntimeError("weg")
    with pytest.raises(RuntimeError):
        run_bulk([(1,), (2,), (3,)], lambda c, j: j[0] == 1, conn=FakeConn(),
                 is_cancelled=lambda: False, on_progress=progress, counts=counts)
    assert counts == BulkCounts(done=1, skipped=1)
