"""Potential „Alle Loops setzen“ / Beautify: Preset bestimmt die Suche (intern#207).

Der Bulk-Worker rechnet die Fenster pro Song ueber loop_windows aus,
reicht Vergleichsfenster und Strategie des Presets durch und ueberspringt
Songs, zu deren Laenge die Fenster nicht passen.
"""
import sqlite3
from types import SimpleNamespace

import pytest

import loop_finder
from potential_widget import _BulkAutoLoopWorker


@pytest.fixture
def db_path(tmp_path):
    path = tmp_path / "songs.db"
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE songs (id INTEGER PRIMARY KEY, loop_in REAL, loop_out REAL)")
    conn.executemany("INSERT INTO songs VALUES (?, 0, 0)", [(1,), (2,)])
    conn.commit()
    conn.close()
    return str(path)


@pytest.fixture
def fake_analysis(monkeypatch):
    calls = []
    durations = {"lang.mp3": 180.0, "kurz.mp3": 40.0}

    def _find(fp, bpm=None, compare_beats=16, in_start=None, in_end=None,
              out_start=None, out_end=None):
        calls.append(dict(fp=fp, compare_beats=compare_beats,
                          windows=(in_start, in_end, out_start, out_end)))
        return [SimpleNamespace(loop_in=in_start + 1, loop_out=out_end - 1)]

    def _strategy(candidates, strategy):
        calls[-1]["strategy"] = strategy
        return candidates[0]

    import soundfile
    monkeypatch.setattr(loop_finder, "find_loop_candidates", _find)
    monkeypatch.setattr(loop_finder, "apply_selection_strategy", _strategy)
    monkeypatch.setattr(soundfile, "info",
                        lambda fp: SimpleNamespace(duration=durations[fp]))
    return calls


def _run(worker):
    result = []
    worker.finished.connect(lambda done, skipped: result.append((done, skipped)))
    worker.run()
    return result[0]


def test_zeit_preset_setzt_loop_und_ueberspringt_zu_kurzen_song(
        qapp, db_path, fake_analysis):
    preset = {"mode": "time", "in_start": 20, "in_end": 59,
              "out_start": 50, "out_end": 20,
              "compare_beats": 32, "selection_strategy": "best_8"}
    jobs = [(1, "lang.mp3", 120, "Lang"), (2, "kurz.mp3", 120, "Kurz")]
    worker = _BulkAutoLoopWorker(jobs, db_path, preset=preset)
    try:
        assert _run(worker) == (1, 1)
    finally:
        worker.deleteLater()

    assert len(fake_analysis) == 1          # der kurze Song wurde nicht analysiert
    call = fake_analysis[0]
    assert call["windows"] == (20.0, 59.0, 130.0, 160.0)
    assert call["compare_beats"] == 32
    assert call["strategy"] == "best_8"

    conn = sqlite3.connect(db_path)
    rows = dict((r[0], r[1:]) for r in conn.execute("SELECT * FROM songs"))
    conn.close()
    assert rows[1] == (21.0, 159.0)
    assert rows[2] == (0.0, 0.0)


def test_ohne_preset_gilt_singing(qapp, db_path, fake_analysis):
    worker = _BulkAutoLoopWorker([(1, "lang.mp3", 120, "Lang")], db_path)
    try:
        assert _run(worker) == (1, 0)
    finally:
        worker.deleteLater()
    assert fake_analysis[0]["windows"] == pytest.approx((12.6, 37.8, 115.2, 142.2))
    assert fake_analysis[0]["strategy"] == "best_64"
