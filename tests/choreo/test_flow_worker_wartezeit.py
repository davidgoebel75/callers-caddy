"""Wartezeit vor der Engine im Square-Flow-Worker (intern#272).

Ein Engine-Lauf startet erst ENGINE_DELAY_S nach dem Auftrag; ein neuerer Auftrag in der
Wartezeit ersetzt ihn, eine leere Liste oder das Ausschalten verwirft ihn. Treffer aus
Speicher und DB kommen ohne Wartezeit.
"""
import time

from caddy.choreo import analysis, flow_worker
from caddy.choreo.flow_worker import SquareFlowWorker
from caddy.choreo.square_flow_widget import SquareFlowWidget
from i18n import _t
from song_db import SongDatabase
from song_db_sequences import write_choreo_cache

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


def test_abbrechen_in_der_wartezeit_rechnet_nicht(qapp, monkeypatch):
    w, runs, got = _worker(monkeypatch, 0.3)
    w.request(1, CALLS_A, TYPE)
    time.sleep(0.05)
    w.cancel()
    _spin(qapp, lambda: False, timeout=0.5)
    assert runs == [] and got == []
    w.request(2, CALLS_B, TYPE)               # danach rechnet der Worker wieder
    _spin(qapp, lambda: got)
    w.shutdown()
    assert [c for c, _ in runs] == [CALLS_B]
    assert [tok for tok, _, _ in got] == [2]


def test_db_treffer_ohne_wartezeit(qapp, monkeypatch, tmp_path, keep):
    path = str(tmp_path / "cc.db")
    keep(SongDatabase(path))
    w, runs, got = _worker(monkeypatch, 5.0)
    w._db_path = path
    ihash = analysis.input_hash(CALLS_A, TYPE, w._load_app(CALLS_A))
    known = {"urteil": "gruen", "calls": list(CALLS_A)}
    assert write_choreo_cache(path, 7, ihash, "", analysis.to_cache(known))
    t0 = time.perf_counter()
    w.request(1, CALLS_A, TYPE, seq_id=7, need_animation=False)
    _spin(qapp, lambda: got, timeout=2.0)
    w.shutdown()
    assert got and got[0][1]["urteil"] == "gruen"
    assert got[0][2] - t0 < 1.0               # nicht die 5 s Wartezeit
    assert runs == []


def test_perf_marke_ohne_wartezeit(qapp, monkeypatch):
    marks = []

    def fake_line(seq_id, n_calls, source, ms, **kw):
        marks.append(ms)
        return ""

    monkeypatch.setattr(flow_worker.perf, "is_enabled", lambda: True)
    monkeypatch.setattr(flow_worker.perf, "perf_write", lambda line: None)
    monkeypatch.setattr(flow_worker.perf_marks, "analyse_line", fake_line)
    w, runs, got = _worker(monkeypatch, 0.5)
    w.request(1, CALLS_A, TYPE)
    _spin(qapp, lambda: marks)
    w.shutdown()
    assert marks and marks[0] < 300           # ohne die 500 ms Wartezeit


# --- Widget: nichts mehr zu rechnen ------------------------------------------

class _Settings:
    def __init__(self):
        self.vals = {"square_flow/enabled": True}

    def value(self, key, default=None, type=None):
        return self.vals.get(key, default)


def _waiting_widget(monkeypatch, keep):
    """Square Flow mit echtem Worker, dessen Auftrag gerade in der Wartezeit steht."""
    worker, runs, got = _worker(monkeypatch, 0.3)
    settings = _Settings()
    widget = keep(SquareFlowWidget(settings=settings))
    widget._worker = worker
    worker.ready.connect(widget._on_ready)
    widget.set_sequence(CALLS_A, TYPE)
    time.sleep(0.05)
    return widget, settings, runs, got


def test_leere_liste_in_der_wartezeit_rechnet_nicht(qapp, monkeypatch, keep):
    widget, _, runs, got = _waiting_widget(monkeypatch, keep)
    token = widget._token
    widget.set_sequence([], TYPE)
    _spin(qapp, lambda: False, timeout=0.5)
    widget.shutdown()
    assert runs == [] and got == []
    assert widget._status.text() == _t("sf_no_sequence")
    widget._on_ready(token, {"error": "x"})   # Lauf, der schon unterwegs war
    assert widget._status.text() == _t("sf_no_sequence")


def test_ausschalten_in_der_wartezeit_rechnet_nicht(qapp, monkeypatch, keep):
    widget, settings, runs, got = _waiting_widget(monkeypatch, keep)
    token = widget._token
    settings.vals["square_flow/enabled"] = False
    widget.reload_settings()
    _spin(qapp, lambda: False, timeout=0.5)
    assert runs == [] and got == []
    assert widget._status.text() == _t("sf_disabled")
    widget._on_ready(token, {"error": "x"})
    assert widget._status.text() == _t("sf_disabled")
    settings.vals["square_flow/enabled"] = True
    widget.reload_settings()                  # wieder ein: dieselbe Sequenz rechnen
    _spin(qapp, lambda: got)
    widget.shutdown()
    assert [c for c, _ in runs] == [CALLS_A]
