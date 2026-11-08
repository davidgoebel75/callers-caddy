"""Schliessen der Pausen-Uhr ueber das X bricht eine laufende Pause ab (intern#221).

Abgebrochen, nicht abgelaufen: kein break_finished. Nur das echte Schliessen
zaehlt, blosses Ausblenden (Ansicht-Menue, Rule, Layout) laesst die Uhr laufen.
"""
import pytest


@pytest.fixture
def uhr_im_dock(keep):
    from PySide6.QtWidgets import QDockWidget
    from caddy.breaks.break_widget import BreakWidget
    uhr = BreakWidget()
    dock = keep(QDockWidget())          # besitzt die Uhr nach setWidget
    dock.setWidget(uhr)
    uhr.cancel_on_close(dock)
    uhr.fertig = []
    uhr.on_break_finished = lambda: uhr.fertig.append(1)
    dock.show()
    return uhr, dock


def test_x_bricht_laufende_pause_ab(uhr_im_dock):
    from caddy.breaks.break_clock import BreakState
    uhr, dock = uhr_im_dock
    uhr.start_break(120)
    dock.close()
    assert uhr.state == BreakState(total=120, remaining=120)
    assert uhr.fertig == []


def test_x_laesst_angehaltene_uhr_stehen(uhr_im_dock, monkeypatch):
    import caddy.breaks.break_widget as modul
    uhr, dock = uhr_im_dock
    jetzt = [100.0]
    monkeypatch.setattr(modul.time, "monotonic", lambda: jetzt[0])
    uhr.start_break(120)
    uhr._timer.timeout.emit()           # erster Tick: nur Zeitmarke
    jetzt[0] = 130.0
    uhr._timer.timeout.emit()           # 30 s vergangen
    uhr._btn_start.click()              # anhalten
    dock.close()
    assert uhr.state.remaining == 90    # nicht auf 120 zurueckgesetzt


def test_ausblenden_bricht_nicht_ab(uhr_im_dock):
    uhr, dock = uhr_im_dock
    uhr.start_break(120)
    dock.hide()                         # Ansicht-Menue, Rule, Layout-Restore
    assert uhr.state.running
    assert uhr.fertig == []
