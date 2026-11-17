"""DB-Cache sequence_choreo (intern#247): Treffer ohne Engine-Start, ungueltig bei Aenderung."""
import contextlib
import io
import time

import pytest

from caddy.choreo import analysis, engine
from caddy.choreo.flow_worker import SquareFlowWorker
from song_db import SongDatabase
from song_db_sequences import read_choreo_cache, write_choreo_cache

CALLS = ("Heads Square Thru 4", "Swing Thru", "Boys Run", "Ferris Wheel",
         "Centers Pass Thru", "Swing & Promenade")
TYPE = "Singer (Corner progression)"


def _db(tmp_path, keep):
    path = tmp_path / "cc.db"
    with contextlib.redirect_stdout(io.StringIO()):
        keep(SongDatabase(str(path)))
    return str(path)


def _wait(qapp, worker, n, timeout=20):
    got = []
    worker.ready.connect(lambda tok, res: got.append(res))
    return got, lambda: _spin(qapp, got, n, timeout)


def _spin(qapp, got, n, timeout):
    end = time.time() + timeout
    while len(got) < n and time.time() < end:
        qapp.processEvents()
        time.sleep(0.01)
    return got


def test_lesen_schreiben_und_tabelle_da(tmp_path, keep):
    db = _db(tmp_path, keep)
    assert read_choreo_cache(db, 5) is None
    assert write_choreo_cache(db, 5, "h", "e", '{"a": 1}')
    assert write_choreo_cache(db, 5, "h2", "e", '{"a": 2}')         # ersetzt
    assert read_choreo_cache(db, 5) == ("h2", "e", '{"a": 2}')


def test_hash_aendert_sich_mit_zeilen_typ_und_app():
    h = analysis.input_hash(CALLS, TYPE)
    assert h == analysis.input_hash(list(CALLS), TYPE)
    assert h != analysis.input_hash(CALLS[:-1], TYPE)
    assert h != analysis.input_hash(CALLS, "Static Set ➔ Resolve")
    assert h != analysis.input_hash(CALLS, TYPE, {"Boys Run": "Run"})
    assert h == analysis.input_hash(CALLS, TYPE, {"Andere Zeile": "X"})


def test_cache_ohne_animation_rund():
    res = {"urteil": "gruen", "card_beats": [4, 6], "animation": {"frames": [1]}}
    back = analysis.from_cache(analysis.to_cache(res))
    assert back["urteil"] == "gruen" and back["animation"] is None and back["cached"]
    assert analysis.from_cache("kaputt") is None


@pytest.mark.skipif(engine.find_engine() is None, reason="tam_cli nicht vorhanden")
def test_treffer_ohne_engine_start(tmp_path, keep, qapp):
    db = _db(tmp_path, keep)
    w1 = SquareFlowWorker(db)
    got, spin = _wait(qapp, w1, 1)
    w1.request(1, CALLS, TYPE, seq_id=42, need_animation=False)
    spin()
    w1.shutdown()
    assert got and got[0]["urteil"] == "gruen" and got[0]["animation"]
    assert read_choreo_cache(db, 42) is not None

    w2 = SquareFlowWorker(db)                     # neue Sitzung: nur die DB kennt es
    got2, spin2 = _wait(qapp, w2, 1)
    w2.request(1, CALLS, TYPE, seq_id=42, need_animation=False)
    spin2()
    assert got2 and got2[0].get("cached") and got2[0]["card_beats"] == got[0]["card_beats"]
    assert w2.engine()._proc is None              # Engine nicht gestartet
    w2.shutdown()

    w3 = SquareFlowWorker(db)                     # geaenderte Sequenz: neu rechnen
    got3, spin3 = _wait(qapp, w3, 1)
    w3.request(1, CALLS[:-1] + ("Swing & Promenade Home",), TYPE, seq_id=42,
               need_animation=False)
    spin3()
    w3.shutdown()
    assert got3 and not got3[0].get("cached")
