"""Wartezeit vor der Engine im Square-Flow-Worker (intern#272).

Ein Engine-Lauf startet erst ENGINE_DELAY_S nach dem Auftrag; ein neuerer Auftrag in der
Wartezeit ersetzt ihn. Treffer aus dem Speicher kommen ohne Wartezeit.
"""
import time

from caddy.choreo import analysis, flow_worker
from caddy.choreo.flow_worker import SquareFlowWorker

CALLS_A = ("Heads Square Thru 4", "Swing Thru", "Boys Run")
CALLS_B = ("Sides Square Thru 4", "Swing Thru", "Girls Run")
TYPE = "Hoedown"


class _Engine:
    """Ersatz-Engine: verfuegbar, startet nie einen Prozess."""
    path = None
    start_count = 0

    def available(self):
        return True

    def run(self, *a, **kw):            # pragma: no cover - analyse_sequence ist ersetzt
        raise AssertionError("Engine darf im Test nicht laufen")

    def close(self):
        pass


def _worker(monkeypatch, delay):
    runs = []

    def fake_analyse(run, calls, seq_type, app):
        runs.append((tuple(calls), time.perf_counter()))
        return {"urteil": "gruen", "calls": list(calls)}

    monkeypatch.setattr(flow_worker.analysis, "analyse_sequence", fake_analyse)
    monkeypatch.setattr(SquareFlowWorker, "ENGINE_DELAY_S", delay)
    w = SquareFlowWorker(db_path=None, engine=_Engine())
    got = []
    w.ready.connect(lambda tok, res: got.append((tok, res, time.perf_counter())))
    return w, runs, got


def _spin(qapp, cond, timeout=5.0):
    end = time.perf_counter() + timeout
    while not cond() and time.perf_counter() < end:
        qapp.processEvents()
        time.sleep(0.005)


def test_engine_wartet_vor_dem_lauf(qapp, monkeypatch):
    w, runs, got = _worker(monkeypatch, 0.3)
    t0 = time.perf_counter()
    w.request(1, CALLS_A, TYPE)
    _spin(qapp, lambda: got)
    w.shutdown()
    assert [c for c, _ in runs] == [CALLS_A]
    assert runs[0][1] - t0 >= 0.25            # erst nach der Wartezeit gerechnet
    assert got[0][0] == 1


def test_neuer_auftrag_in_der_wartezeit_ersetzt_den_alten(qapp, monkeypatch):
    w, runs, got = _worker(monkeypatch, 0.3)
    w.request(1, CALLS_A, TYPE)
    time.sleep(0.05)                          # Worker steht in der Wartezeit von A
    w.request(2, CALLS_B, TYPE)
    _spin(qapp, lambda: got)
    _spin(qapp, lambda: False, timeout=0.4)   # ein spaeter Lauf von A faellt hier auf
    w.shutdown()
    assert [c for c, _ in runs] == [CALLS_B]  # A nie gerechnet
    assert [tok for tok, _, _ in got] == [2]


def test_speicher_treffer_ohne_wartezeit(qapp, monkeypatch):
    w, runs, got = _worker(monkeypatch, 5.0)
    known = {"urteil": "gruen", "animation": {"frames": [1]}}
    w._remember(analysis.input_hash(CALLS_A, TYPE, {}), known)
    t0 = time.perf_counter()
    w.request(1, CALLS_A, TYPE)
    _spin(qapp, lambda: got, timeout=2.0)
    w.shutdown()
    assert got and got[0][1] is known
    assert got[0][2] - t0 < 1.0               # nicht die 5 s Wartezeit
    assert runs == []


def test_beenden_in_der_wartezeit_rechnet_nicht(qapp, monkeypatch):
    w, runs, got = _worker(monkeypatch, 5.0)
    w.request(1, CALLS_A, TYPE)
    time.sleep(0.05)
    t0 = time.perf_counter()
    w.shutdown()
    w._thread.join(2.0)
    assert not w._thread.is_alive()
    assert time.perf_counter() - t0 < 2.0     # wartet nicht die 5 s ab
    assert runs == [] and got == []
