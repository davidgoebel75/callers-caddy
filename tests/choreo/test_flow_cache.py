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


class _FakeEngine:
    path = None

    def available(self):
        return True

    def run(self, *_a, **_k):
        raise AssertionError("analyse_sequence ist im Test ersetzt")

    def close(self):
        pass


def test_geaendertes_call_mapping_rechnet_neu(tmp_path, keep, qapp, monkeypatch):
    """Review #192, Punkt 7: Der Worker liest das Call-Mapping bei jedem Lauf neu.
    Eine Zuordnung, die nach dem ersten Lauf dazukommt, fuehrt zu einer neuen
    Berechnung, ohne dass jemand invalidate() aufruft."""
    db_path = _db(tmp_path, keep)
    runs = []

    def _fake_analyse(_run, calls, seq_type, app):
        runs.append(dict(app))
        return {"stufe1": True, "urteil": "gruen", "card_beats": [], "animation": None}

    monkeypatch.setattr(analysis, "analyse_sequence", _fake_analyse)
    w = SquareFlowWorker(db_path, engine=_FakeEngine())
    got, _ = _wait(qapp, w, 0)
    w.request(1, ("Boys Rnu",), TYPE)
    _spin(qapp, got, 1, 10)
    w.request(2, ("Boys Rnu",), TYPE)                       # gleich: aus dem Speicher
    _spin(qapp, got, 2, 10)
    assert len(runs) == 1

    with contextlib.redirect_stdout(io.StringIO()):
        db = keep(SongDatabase(db_path))
    eid = db._conn.execute("SELECT entity_id FROM calls WHERE canonical_name = 'Run'"
                           ).fetchone()[0]
    db.set_call_text_mapping("Boys Rnu", eid, mapped_by="manual")
    w.request(3, ("Boys Rnu",), TYPE)
    _spin(qapp, got, 3, 10)
    w.shutdown()
    assert len(runs) == 2 and runs[1].get("Boys Rnu") == "Run"


def test_zuordnungen_nur_fuer_die_zeilen_der_sequenz(tmp_path, keep):
    """intern#263: gefiltert gelesen gibt es dieselben Eintraege wie aus der ganzen Tabelle,
    also denselben Cache-Schluessel; nur fremde Kartentexte fehlen."""
    from song_db_sequences import read_choreo_call_names
    db_path = _db(tmp_path, keep)
    with contextlib.redirect_stdout(io.StringIO()):
        db = keep(SongDatabase(db_path))
    eid = db._conn.execute("SELECT entity_id FROM calls WHERE canonical_name = 'Run'"
                           ).fetchone()[0]
    for text in ("Boys Rnu", " Boys Rnu ", "Girls Rnu", "(Zero Box)"):
        db.set_call_text_mapping(text, eid, mapped_by="manual")
    full = read_choreo_call_names(db_path)
    calls = ("(Zero Box)", " Boys Rnu ", "Swing Thru")
    w = SquareFlowWorker(db_path, engine=_FakeEngine())
    part = w._load_app(calls)
    assert "Girls Rnu" in full and "Girls Rnu" not in part
    assert {k: v for k, v in full.items() if k in part} == part
    for c in calls:                            # Text wie gegeben und ohne Leerraum
        for t in (c, c.strip()):
            assert part.get(t) == full.get(t)
    assert analysis.input_hash(calls, TYPE, part) == analysis.input_hash(calls, TYPE, full)
    assert read_choreo_call_names(db_path, []) == {}


def test_zuordnungen_viele_texte_in_teilen(tmp_path, keep):
    """Mehr Kartentexte als SQL-Parameter erlaubt: wird in Teilen gelesen."""
    from song_db_sequences import read_choreo_call_names
    db_path = _db(tmp_path, keep)
    full = read_choreo_call_names(db_path)
    texts = list(full)[:1500] + [f"Unbekannt {i}" for i in range(1200)]
    got = read_choreo_call_names(db_path, texts)
    assert got == {k: full[k] for k in texts if k in full}
