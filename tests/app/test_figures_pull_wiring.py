"""Verdrahtung des Figuren-Vorbaus in main.py (intern#274, Review #204).

- Der Pull-Takt zieht nie bei laufender Musik (TIC-0025).
- Beim Beenden: Pull-Takt aus, Prefetch-Worker vor db.close() beenden.
- Figuren aus dem Worker landen ausdruecklich in der Warteschlange des Hauptthreads.
"""
import inspect
from types import SimpleNamespace

import main

W = main.P29MainWindow


class _Fenster:
    _pull_figures = W._pull_figures

    def __init__(self, playing):
        self.engine = SimpleNamespace(is_playing=lambda: playing)
        self.pulls = 0
        self._figures_task = SimpleNamespace(pull=self._pull)

    def _pull(self):
        self.pulls += 1
        return True


def test_bei_laufender_musik_wird_nicht_gezogen():
    f = _Fenster(playing=True)
    f._pull_figures()
    assert f.pulls == 0


def test_ohne_musik_wird_gezogen():
    f = _Fenster(playing=False)
    f._pull_figures()
    assert f.pulls == 1


def test_beenden_in_der_richtigen_reihenfolge():
    src = inspect.getsource(W.closeEvent)
    i_timer = src.index("_figures_pull_timer.stop()")
    i_prefetch = src.index("_seq_prefetch.shutdown()")
    i_close = src.index("self.db.close()")
    assert i_timer < i_prefetch < i_close


def test_figuren_signal_ausdruecklich_in_die_warteschlange():
    src = inspect.getsource(W)
    assert "figures_ready.connect(self._on_seq_figures_ready" in src
    i = src.index("figures_ready.connect(self._on_seq_figures_ready")
    assert "Qt.QueuedConnection" in src[i:i + 160]


def test_figuren_uebernahme_ruft_die_db():
    got = []
    f = SimpleNamespace(db=SimpleNamespace(adopt_sequence_figures=lambda v, figs:
                                           got.append((v, figs))))
    W._on_seq_figures_ready(f, (7, {"x": 1}))
    assert got == [(7, {"x": 1})]
