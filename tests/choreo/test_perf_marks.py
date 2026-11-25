"""Perf-Marken von Square Flow (intern#263): Zeilenformat, Sammelfenster, nur bei Logging."""
import perf
from caddy.choreo import flow_worker, perf_marks
from caddy.choreo.flow_worker import SquareFlowWorker
from caddy.choreo.square_flow_widget import SquareFlowWidget

from test_square_flow_widget import _Settings, _result


class _Clock:
    def __init__(self):
        self.t = 100.0

    def __call__(self):
        return self.t


class _Engine:
    path = None
    start_count = 0

    def available(self):
        return True

    def run(self, request):                      # wird durch den Patch nicht gerufen
        raise AssertionError


def _capture(monkeypatch, enabled):
    lines = []
    monkeypatch.setattr(perf, "is_enabled", lambda: enabled)
    monkeypatch.setattr(perf, "perf_write", lines.append)
    return lines


# --- Zeilen -------------------------------------------------------------------

def test_analyse_zeile():
    line = perf_marks.analyse_line(1234, 37, perf_marks.SOURCE_ENGINE, 819.6,
                                   engine_started=True)
    assert line == ("[SquareFlow] Analyse seq=1234 (37 Calls): Engine 820 ms, "
                    "mit Engine-Start")
    assert perf_marks.analyse_line(None, 2, perf_marks.SOURCE_MEMORY, 0.2) == \
        "[SquareFlow] Analyse seq=- (2 Calls): Speicher 0 ms"
    assert perf_marks.analyse_line(5, 1, "Engine", 3, error="engine_missing").endswith(
        ", Fehler: engine_missing")


def test_zeilen_nicht_als_perf_event():
    """Der Haenger-Detektor merkt sich nur [Perf]-Zeilen (Hauptthread)."""
    assert not perf_marks.analyse_line(1, 1, "Engine", 1).startswith("[Perf]")


def test_sammelfenster():
    clock = _Clock()
    st = perf_marks.AnimStats(period=5.0, clock=clock)
    st.paint(2.0)
    st.paint(4.0)
    st.step(1.0)
    st.step(3.4)
    clock.t += 4.9
    assert st.poll() is None                     # Fenster noch offen
    clock.t += 0.2
    assert st.poll() == ("[SquareFlow] Animation 5s: 2 Frames, paint avg 3.0 / max 4 ms, "
                         "Schritt max 3 ms")
    clock.t += 6.0
    assert st.poll() is None                     # ohne Bilder keine Zeile
    st.paint(1.0)
    clock.t += 1.0
    assert st.poll(force=True).startswith("[SquareFlow] Animation 1s: 1 Frames")


# --- Worker -------------------------------------------------------------------

def test_worker_schreibt_nichts_ohne_logging(monkeypatch):
    lines = _capture(monkeypatch, enabled=False)
    w = SquareFlowWorker(engine=_Engine())
    monkeypatch.setattr(flow_worker.analysis, "analyse_sequence",
                        lambda run, calls, typ, app: {"urteil": "gruen"})
    w._run_job(1, ("A", "B"), "Singer", 7, True)
    assert lines == []


def test_worker_marke_je_quelle(monkeypatch):
    lines = _capture(monkeypatch, enabled=True)
    eng = _Engine()

    def analyse(run, calls, typ, app):
        eng.start_count += 1                     # erster Lauf startet die Engine
        return {"urteil": "gruen"}

    monkeypatch.setattr(flow_worker.analysis, "analyse_sequence", analyse)
    w = SquareFlowWorker(engine=eng)
    w._run_job(1, ("A", "B"), "Singer", 7, True)
    w._run_job(2, ("A", "B"), "Singer", 7, True)
    assert lines[0].startswith("[SquareFlow] Analyse seq=7 (2 Calls): Engine ")
    assert lines[0].endswith(", mit Engine-Start")
    assert lines[1].startswith("[SquareFlow] Analyse seq=7 (2 Calls): Speicher ")


# --- Widget -------------------------------------------------------------------

def _widget(keep):
    w = keep(SquareFlowWidget(settings=_Settings(enabled=True)))
    w._seq = (("A", "B"), "Static Set ➔ Resolve")
    w._token = 1
    return w


def test_widget_ohne_logging_keine_statistik(monkeypatch, keep):
    lines = _capture(monkeypatch, enabled=False)
    w = _widget(keep)
    w._on_ready(1, _result())
    w.play()
    assert w._floor.stats is None
    w.pause()
    assert lines == []


def test_widget_sammelzeile_beim_anhalten(monkeypatch, keep):
    lines = _capture(monkeypatch, enabled=True)
    w = _widget(keep)
    w._on_ready(1, _result())
    w.play()
    assert w._floor.stats is w._anim_stats
    w._anim_stats.paint(2.0)                     # ein Bild, ohne echtes Neuzeichnen
    w._tick()
    w.pause()
    assert w._floor.stats is None
    assert any(l.startswith("[SquareFlow] Animation") for l in lines)


def test_mitlaufen_startet_und_beendet_statistik(monkeypatch, keep):
    _capture(monkeypatch, enabled=True)
    w = _widget(keep)
    w._on_ready(1, _result())
    w.follow((0, 0, 0.0, 4.0, False), 1.0)
    assert w._floor.stats is w._anim_stats
    w.follow_off()
    assert w._floor.stats is None
