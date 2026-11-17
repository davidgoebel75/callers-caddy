"""Evening-Planner-Vorbau nach geschlossener Datenbank (intern#211).

Der Vorbau laeuft per einmaligem Timer 3 s nach dem Start. Wurde die App
vorher geschlossen, ist die Datenbank zu und der Vorbau muss entfallen,
statt mit einem Crash-Report abzubrechen.

Waehrend der Wiedergabe darf der Vorbau nicht laufen (blockiert den GUI-Thread
~1 s); er plant sich dann neu ein.
"""
from types import SimpleNamespace

import main

W = main.P29MainWindow


class _Fenster:
    _preload_evening_planner = W._preload_evening_planner

    def __init__(self, db_open, playing=False):
        self.evening_planner = None
        self.db = SimpleNamespace(is_open=lambda: db_open)
        self.engine = SimpleNamespace(is_playing=lambda: playing)
        self.dock_evening_planner = SimpleNamespace(
            visibilityChanged=SimpleNamespace(disconnect=lambda *_: None))
        self._on_evening_planner_visibility = None
        self.built = 0

    def _init_evening_planner(self):
        self.built += 1


def test_geschlossene_datenbank_kein_vorbau():
    f = _Fenster(db_open=False)
    f._preload_evening_planner()
    assert f.built == 0


def test_offene_datenbank_baut_vor():
    f = _Fenster(db_open=True)
    f._preload_evening_planner()
    assert f.built == 1


def test_waehrend_wiedergabe_kein_vorbau_sondern_neu_einplanen(monkeypatch):
    geplant = []
    monkeypatch.setattr(main.QTimer, "singleShot",
                        lambda ms, fn: geplant.append((ms, fn)))
    f = _Fenster(db_open=True, playing=True)
    f._preload_evening_planner()
    assert f.built == 0
    assert len(geplant) == 1
    ms, fn = geplant[0]
    assert ms > 0
    assert fn == f._preload_evening_planner
