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
    assert read_choreo_cache(db, 5) == ("h2", "e", '{"a": 2}', None)
    assert write_choreo_cache(db, 5, "h3", "e", '{"a": 3}', b"z")
    assert read_choreo_cache(db, 5)[3] == b"z"


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


def test_animation_gepackt_rund():
    """intern#263: Animation in anim_z, from_cache macht das Ergebnis wieder vollstaendig."""
    anim = {"frames": [[0.0, [1, 2, 3]], [0.25, [1, 2, 4]]], "total_beats": 8}
    res = {"urteil": "gruen", "card_beats": [4, 6], "animation": anim}
    blob = analysis.anim_to_blob(res)
    assert isinstance(blob, bytes) and len(blob) < len(str(anim)) + 50
    back = analysis.from_cache(analysis.to_cache(res), blob)
    assert back["animation"] == anim and back["cached"] and back["card_beats"] == [4, 6]
    assert analysis.anim_to_blob({"animation": {}}) == analysis.NO_ANIM
    assert analysis.anim_to_blob({"animation": None}) == analysis.NO_ANIM
    assert analysis.anim_to_blob({"animation": {}, "transient": True}) is None
    assert analysis.anim_from_blob(analysis.NO_ANIM) is None
    assert analysis.anim_from_blob(b"kaputt") is None
    assert analysis.from_cache(analysis.to_cache(res), b"kaputt")["animation"] is None


@pytest.mark.skipif(engine.find_engine() is None, reason="tam_cli nicht vorhanden")
def test_neue_sitzung_mit_animation_ohne_engine(tmp_path, keep, qapp):
    """intern#263: Square Flow sichtbar (need_animation) und die Sequenz ist aus einer
    frueheren Sitzung bekannt: Ergebnis samt Animation aus der DB, Engine bleibt aus."""
    db = _db(tmp_path, keep)
    w1 = SquareFlowWorker(db)
    got, spin = _wait(qapp, w1, 1)
    w1.request(1, CALLS, TYPE, seq_id=7, need_animation=True)
    spin()
    w1.shutdown()
    assert got and got[0]["animation"]
    assert read_choreo_cache(db, 7)[3]                     # Animation gespeichert

    w2 = SquareFlowWorker(db)
    got2, spin2 = _wait(qapp, w2, 1)
    w2.request(1, CALLS, TYPE, seq_id=7, need_animation=True)
    spin2()
    _spin(qapp, got2, 2, 1)                                # kein zweites Ergebnis
    assert len(got2) == 1 and got2[0].get("cached")
    assert got2[0]["animation"] == got[0]["animation"]
    assert w2.engine()._proc is None                       # Engine nicht gestartet
    w2.request(2, CALLS, TYPE, seq_id=7, need_animation=True)   # jetzt aus dem Speicher
    _spin(qapp, got2, 2, 10)
    assert got2[1]["animation"] == got[0]["animation"]
    assert w2.engine()._proc is None
    w2.shutdown()


def test_marker_keine_animation_zaehlt_als_fertig(tmp_path, keep):
    """Review #196, Punkt 1: NO_ANIM in anim_z ist vollstaendig, NULL nicht."""
    db = _db(tmp_path, keep)
    res = {"urteil": "rot", "card_beats": [], "animation": {}}
    write_choreo_cache(db, 3, "h", "e", analysis.to_cache(res), analysis.anim_to_blob(res))
    row = read_choreo_cache(db, 3)
    assert row[3] == analysis.NO_ANIM                      # leeres Blob, nicht NULL
    cached = analysis.from_cache(row[2], row[3])
    assert cached["animation"] is None and analysis.cache_complete(cached, row[3])
    write_choreo_cache(db, 3, "h", "e", analysis.to_cache(res), None)
    row = read_choreo_cache(db, 3)
    assert not analysis.cache_complete(analysis.from_cache(row[2], row[3]), row[3])


def test_analyse_merkt_abbruch_ohne_engine_urteil():
    """Review #196, Punkt 1: Timeout oder Engine-Abbruch macht das Ergebnis vorlaeufig."""
    def _timeout(req):
        return engine.failed_response(req, "timeout (30 s)")

    res = analysis.analyse_sequence(_timeout, list(CALLS), TYPE)
    assert res["transient"] and not res["animation"]
    assert analysis.anim_to_blob(res) is None


@pytest.mark.parametrize("transient, runs_expected", [(False, 1), (True, 2)])
def test_ohne_animation_neue_sitzung(tmp_path, keep, qapp, monkeypatch,
                                     transient, runs_expected):
    """Review #196, Punkt 1: Liefert die Engine endgueltig keine Animation, rechnet die
    naechste Sitzung nicht neu; nach einem Timeout schon."""
    db_path = _db(tmp_path, keep)
    runs = []

    def _fake_analyse(_run, calls, seq_type, app):
        runs.append(1)
        return {"stufe1": False, "urteil": None, "card_beats": [], "animation": {},
                "transient": transient}

    monkeypatch.setattr(analysis, "analyse_sequence", _fake_analyse)
    for tok in (1, 2):                                     # zwei Sitzungen
        w = SquareFlowWorker(db_path, engine=_FakeEngine())
        got, _ = _wait(qapp, w, 0)
        w.request(tok, ("Boys Rnu",), TYPE, seq_id=11, need_animation=True)
        _spin(qapp, got, 1, 10)
        _spin(qapp, got, 2, 0.3)
        w.shutdown()
    assert len(runs) == runs_expected


def test_abbruch_landet_nicht_in_der_db(tmp_path, keep, qapp, monkeypatch):
    """Review #196 (Freigabe): Nach einem Timeout steht nichts in sequence_choreo. Die
    naechste Sitzung rechnet auch bei verstecktem Dock neu, statt den abgebrochenen Lauf
    zu zeigen; in der laufenden Sitzung kommt er aus dem Speicher."""
    db_path = _db(tmp_path, keep)
    runs = []

    def _fake_analyse(_run, calls, seq_type, app):
        runs.append(1)
        return {"stufe1": False, "urteil": None, "card_beats": [], "animation": {},
                "transient": True}

    monkeypatch.setattr(analysis, "analyse_sequence", _fake_analyse)
    w = SquareFlowWorker(db_path, engine=_FakeEngine())
    got, _ = _wait(qapp, w, 0)
    w.request(1, ("Boys Rnu",), TYPE, seq_id=12, need_animation=False)
    _spin(qapp, got, 1, 10)
    w.request(2, ("Boys Rnu",), TYPE, seq_id=12, need_animation=False)
    _spin(qapp, got, 2, 10)
    w.shutdown()
    assert read_choreo_cache(db_path, 12) is None
    assert len(runs) == 1                                  # zweiter Auftrag aus dem Speicher

    w2 = SquareFlowWorker(db_path, engine=_FakeEngine())
    got2, _ = _wait(qapp, w2, 0)
    w2.request(1, ("Boys Rnu",), TYPE, seq_id=12, need_animation=False)
    _spin(qapp, got2, 1, 10)
    w2.shutdown()
    assert len(runs) == 2 and not got2[0].get("cached")
