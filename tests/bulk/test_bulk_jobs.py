"""bpm_step zusammen mit run_bulk auf einer echten Test-DB (intern#139)."""
import contextlib
import functools
import io

import pytest

from caddy.bulk.bulk_jobs import bpm_step
from caddy.bulk.bulk_run import run_bulk
from song_db import SongDatabase


@pytest.fixture
def db(tmp_path):
    with contextlib.redirect_stdout(io.StringIO()):
        d = SongDatabase(str(tmp_path / "j.db"))
    for n in ("a", "b", "c"):
        d._conn.execute("INSERT INTO songs (filename, title) VALUES (?, ?)",
                        (n + ".mp3", n))
    d._conn.commit()
    yield d
    d.close()


def _jobs(db):
    return [(r[0], r[1], r[2]) for r in db._conn.execute(
        "SELECT id, filename, title FROM songs ORDER BY id")]


def _run(db, detect):
    conn = db.open_worker_connection()
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            res = run_bulk(_jobs(db), functools.partial(bpm_step, detect=detect),
                           conn=conn, is_cancelled=lambda: False,
                           on_progress=lambda *a: None)
    finally:
        conn.close()
    return res


def _bpms(db):
    return [r[0] for r in db._conn.execute(
        "SELECT base_bpm FROM songs ORDER BY id")]


def test_bpm_written(db):
    res = _run(db, lambda fp: 128.0)
    assert (res.done, res.skipped) == (3, 0)
    assert _bpms(db) == [128.0] * 3


@pytest.mark.parametrize("value", [0, None, -5.0])
def test_no_bpm_skips_and_writes_nothing(db, value):
    res = _run(db, lambda fp: value)
    assert (res.done, res.skipped) == (0, 3)
    assert all(not b for b in _bpms(db))


def test_detect_raises_skips_song_rest_runs(db):
    def detect(fp):
        if fp == "b.mp3":
            raise RuntimeError("defekt")
        return 100.0
    res = _run(db, detect)
    assert (res.done, res.skipped) == (2, 1)
    assert _bpms(db)[0] == 100.0 and not _bpms(db)[1] and _bpms(db)[2] == 100.0
