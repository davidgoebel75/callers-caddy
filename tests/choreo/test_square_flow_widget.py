"""Square Flow (intern#247): Freigabe, Laden bei Bedarf, Wiedergabe."""
import pytest

from caddy.choreo import analysis, engine
from caddy.choreo.square_flow_widget import SquareFlowWidget
from caddy.settings import ini_keys


class _Settings:
    def __init__(self, **vals):
        self.vals = {f"square_flow/{k}": v for k, v in vals.items()}

    def value(self, key, default=None, type=None):
        return self.vals.get(key, default)


def _result():
    """Kleines Ergebnis wie analysis.analyse_sequence, zwei Kartenzeilen."""
    return {
        "type": "Static Set ➔ Resolve", "stufe1": True, "urteil": "gruen", "with_end": False,
        "error": "", "fail_card": None, "beats_total": 8.0,
        "targets": [("1B", "1G"), ("2B", "2G")],
        "card_beats": [4.0, 4.0], "card_spans": [(0.0, 4.0), (4.0, 8.0)],
        "animation": {"dancers": [{"n": "1", "couple": "1", "boy": True},
                                  {"n": "2", "couple": "1", "boy": False}],
                      "call_starts": [0.0, 4.0], "total_beats": 8.0,
                      "frames": [[0.0, [[-3, 1, 0], [-3, -1, 0]]],
                                 [8.0, [[-1, 1, 0], [-1, -1, 0]]]]},
    }


def test_ausgeschaltet_kein_worker(keep):
    w = keep(SquareFlowWidget(settings=_Settings(enabled=False)))
    w.show()
    w.set_sequence(["Heads Square Thru 4"], "Static Set ➔ Resolve")
    assert w._worker is None
    assert not w.enabled()


def test_unsichtbar_rechnet_noch_nicht(keep):
    w = keep(SquareFlowWidget(settings=_Settings(enabled=True)))
    w.set_sequence(["Heads Square Thru 4"], "Static Set ➔ Resolve")
    assert not w.isVisible()
    assert w._worker is None and w._dirty


def test_ergebnis_zeigt_status_und_karte(keep):
    w = keep(SquareFlowWidget(settings=_Settings(enabled=True)))
    w._seq = (("Heads Square Thru 4", "Allemande Left"), "Static Set ➔ Resolve")
    cards = []
    w.current_card_changed.connect(cards.append)
    w._token = 3
    w._on_ready(2, _result())                   # veraltet: ignoriert
    assert w._result is None
    w._on_ready(3, _result())
    assert "8 Beats" in w._status.text()
    assert cards[-1] == 0
    w._seek(8.0)
    assert w._floor.bands is not None and w._floor.bands[1] is True
    assert cards[-1] == 1


def test_karte_spielen_haelt_am_ende(keep):
    w = keep(SquareFlowWidget(settings=_Settings(enabled=True), bpm_source=lambda: 120.0))
    w._seq = (("A", "B"), "Static Set ➔ Resolve")
    w._token = 1
    w._on_ready(1, _result())
    w.play_card(1)
    assert w._timer.isActive() and w._stop_at == 8.0 and w._beat == 4.0
    w._beat = 7.99
    w._clock.start()
    w._tick()
    w._beat = 8.5                               # Ueberlauf: Tick haelt an
    w._clock.start()
    w._tick()
    assert not w._timer.isActive() and w._beat == 8.0


def test_bpm_rueckfall_ohne_song(keep):
    w = keep(SquareFlowWidget(settings=_Settings(enabled=True), bpm_source=lambda: 0.0))
    assert w._bpm() == 128.0


def test_ini_standard_aus():
    assert ini_keys.default(ini_keys.SQUARE_FLOW_ENABLED) is False


@pytest.mark.skipif(engine.find_engine() is None, reason="tam_cli nicht vorhanden")
def test_analyse_mit_engine_kartenzeilen():
    eng = engine.TamEngine()
    try:
        calls = ["Heads Square Thru 4", "Swing Thru", "Boys Run", "Ferris Wheel",
                 "Centers Pass Thru", "Swing & Promenade"]
        r = analysis.analyse_sequence(eng.run, calls, "Singer (Corner progression)")
        assert r["urteil"] == "gruen" and r["with_end"]
        assert len(r["card_beats"]) == len(calls) and None not in r["card_beats"]
        assert r["card_spans"][0][0] == 0.0
        assert r["card_spans"][-1][1] == r["animation"]["total_beats"]
    finally:
        eng.close()
