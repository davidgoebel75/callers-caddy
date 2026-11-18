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


def _singer_result():
    """Volle Singing-Call-Figur: 8 Taenzer, endet zu Hause mit der Corner als Partnerin."""
    from caddy.choreo import square_chain as sc
    couple, square = [[-3.0, 1.0, 0.0], [-3.0, -1.0, 0.0]], []
    for _c in range(4):
        square += couple
        couple = sc.rotate_pose(couple)
    end = [square[2 * ((i // 2 + 1) % 4) + 1] if i % 2 else square[i] for i in range(8)]
    r = _result()
    r.update({"type": "Singer", "with_end": True, "card_spans": [(0.0, 4.0), (4.0, 8.0)]})
    r["animation"] = {
        "dancers": [{"n": str(i + 1), "couple": str(i // 2 + 1), "boy": i % 2 == 0}
                    for i in range(8)],
        "call_starts": [0.0, 4.0], "total_beats": 8.0,
        "frames": [[0.0, square], [8.0, end]]}
    return r


def test_paare_tanzen_weiter_und_spiegeln(keep):
    w = keep(SquareFlowWidget(settings=_Settings(enabled=True)))
    w._seq = (("Heads Square Thru 4", "Allemande Left"), "Singer")
    w._token = 1
    w._on_ready(1, _singer_result())
    w.follow((-1, -1, None, None, False), 1.0)          # Opener: eigene Partner
    assert [d["couple"] for d in w._floor.dancers][:2] == ["1", "1"]
    w.follow((0, 0, 10.0, 18.0, False), 17.0)           # Figur 1 getanzt
    w.follow((-1, 0, None, None, False), 19.0)          # danach: Frau 4 beim Mann 1
    assert w._floor.dancers[1]["couple"] == "4" and w._floor.dancers[0]["couple"] == "1"
    w.follow((1, 1, 30.0, 38.0, True), 30.0)            # Figur 2 gespiegelt (Sides)
    assert w._view_rot
    x, y, a = w._floor.pose[0]
    assert (round(x, 3), round(y, 3), a) == (-1.0, -3.0, 90.0)   # Engine-Mann 1 auf Platz 2
    assert w._floor.dancers[0]["couple"] == "2"
    w.follow_off()
    assert not w._view_rot and w._floor.dancers[1]["couple"] == "1"


def test_versatz_in_sekunden(keep):
    w = keep(SquareFlowWidget(settings=_Settings(enabled=True, lag_beats=4)))
    assert w.lag_seconds(120) == 2.0
    w0 = keep(SquareFlowWidget(settings=_Settings(enabled=True, lag_beats=0)))
    assert w0.lag_seconds(120) == 0.0


def _following_widget(keep):
    w = keep(SquareFlowWidget(settings=_Settings(enabled=True)))
    w._seq = (("Heads Square Thru 4", "Allemande Left"), "Static Set ➔ Resolve")
    w._token = 1
    w._on_ready(1, _result())
    cards = []
    w.current_card_changed.connect(cards.append)
    return w, cards


def test_mitlaufen_anteilig_im_figuren_fenster(keep):
    """Phase 2: Fenster 10..18 s, 8 Beats -> 14 s = Beat 4 = zweite Kartenzeile."""
    w, cards = _following_widget(keep)
    w.follow((0, 0, 10.0, 18.0, False), 14.0)
    assert w.following() and w._beat == pytest.approx(4.0)
    assert cards[-1] == 1 and not w._timer.isActive()
    w.follow((-1, 0, None, None, False), 20.0)                 # Middle Break: Ausgangsstellung
    assert w._beat == 0.0 and cards[-1] == -1
    w.follow(None, 21.0)                                # Dynamic Lyrics aus: manuell
    assert not w.following()


def test_eingriff_haelt_bis_zur_naechsten_figur(keep):
    w, _cards = _following_widget(keep)
    w.follow((0, 0, 10.0, 18.0, False), 12.0)
    w.next_call()                                       # Nutzer greift ein
    beat = w._beat
    w.follow((0, 0, 10.0, 18.0, False), 17.0)
    assert not w.following() and w._beat == beat        # gleiche Figur: Nutzer bleibt dran
    w.follow((-1, 0, None, None, False), 19.0)
    assert not w.following()                            # auch im Middle Break
    w.follow((1, 1, 30.0, 38.0, False), 32.0)                  # naechste Figur: Song uebernimmt
    assert w.following() and w._beat == pytest.approx(2.0)


def test_abbruch_tanzt_im_song_tempo_bis_zur_abbruchzeile(keep):
    w, _cards = _following_widget(keep)
    w._result["stufe1"] = False
    w._bpm_source = lambda: 120.0
    w.follow((0, 0, 10.0, 40.0, False), 12.0)                  # 2 s bei 120 BPM = 4 Beats
    assert w._beat == pytest.approx(4.0)
    w.follow((0, 0, 10.0, 40.0, False), 30.0)
    assert w._beat == pytest.approx(8.0)                # Animation endet: Square steht


def test_ausgeschaltet_kein_worker(keep):
    w = keep(SquareFlowWidget(settings=_Settings(enabled=False)))
    w.show()
    w.set_sequence(["Heads Square Thru 4"], "Static Set ➔ Resolve")
    assert w._worker is None
    assert not w.enabled()


class _FakeWorker:
    def __init__(self, *a, **k):
        self.jobs = []
        from PySide6.QtCore import QObject, Signal

        class _S(QObject):
            ready = Signal(int, object)
        self._s = _S()
        self.ready = self._s.ready

    def request(self, token, calls, seq_type, seq_id=None, need_animation=True):
        self.jobs.append((token, calls, seq_type, seq_id, need_animation))


def test_freigegeben_rechnet_auch_bei_geschlossenem_dock(keep, monkeypatch):
    """Die Takte im Sequenz-Detail brauchen das Ergebnis auch ohne sichtbares Dock."""
    from caddy.choreo import flow_worker
    monkeypatch.setattr(flow_worker, "SquareFlowWorker", _FakeWorker)
    w = keep(SquareFlowWidget(settings=_Settings(enabled=True)))
    w.set_sequence(["Heads Square Thru 4"], "Static Set ➔ Resolve", seq_id=7)
    assert not w.isVisible()
    assert w._worker.jobs == [(1, ("Heads Square Thru 4",), "Static Set ➔ Resolve", 7, False)]


def test_ergebnis_zeigt_status_und_karte(keep):
    w = keep(SquareFlowWidget(settings=_Settings(enabled=True)))
    w._seq = (("Heads Square Thru 4", "Allemande Left"), "Static Set ➔ Resolve")
    cards, results = [], []
    w.current_card_changed.connect(cards.append)
    w.result_ready.connect(lambda c, r: results.append((c, r)))
    w._token = 3
    w._on_ready(2, _result())                   # veraltet: ignoriert
    assert w._result is None and results == []
    w._on_ready(3, _result())
    assert "8 Beats" in w._status.text()
    assert results[-1][0] == ("Heads Square Thru 4", "Allemande Left")
    assert cards == []                          # ohne Wiedergabe keine Markierung
    w.next_call()
    assert cards[-1] == 1 and w._floor.bands is None
    w.next_call()                               # Ende = Pruefpunkt: Baender gruen
    assert w._floor.bands is not None and w._floor.bands[1] is True
    w.restart()
    assert cards[-1] == -1


def test_hinweise_bei_abbruch_und_ergaenzung():
    r = {"stufe1": False, "fail_card": 1, "urteil": None, "type": "",
         "read_as": [{"card": 0, "text": "Heads Bend The Line", "kind": "kontext",
                      "meaning": True},
                     {"card": 2, "text": "Allemande Left", "kind": "roh", "meaning": False}]}
    lines, strong = SquareFlowWidget.hint_lines(r, ("Bend The Line", "Boys Rnu", "L.A."))
    assert strong
    assert "Boys Rnu" in lines[0]
    assert any("Heads Bend The Line" in x for x in lines)
    assert not any("Allemande Left" in x for x in lines)


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


class _RwSettings(_Settings):
    def setValue(self, key, value):
        self.vals[key] = value


def test_zoom_begrenzt_und_gemerkt(keep):
    from caddy.choreo import square_flow_widget as sfw
    st = _RwSettings(enabled=True)
    w = keep(SquareFlowWidget(settings=st))
    w.zoom_by(50)
    assert w._floor.zoom == sfw.ZOOM_MAX
    assert st.vals["square_flow/zoom_pct"] == int(round(sfw.ZOOM_MAX * 100))
    w.zoom_by(-80)
    assert w._floor.zoom == sfw.ZOOM_MIN
    w.reset_zoom()
    assert w._floor.zoom == 1.0
    w2 = keep(SquareFlowWidget(settings=_Settings(enabled=True, zoom_pct=999)))
    assert w2._floor.zoom == sfw.ZOOM_MAX       # Wert aus der INI wird begrenzt


def test_tasten_lage_waehlbar_und_gemerkt(keep):
    from PySide6.QtWidgets import QBoxLayout
    st = _RwSettings(enabled=True)
    w = keep(SquareFlowWidget(settings=st))
    assert w._stage.direction() == QBoxLayout.TopToBottom
    w.set_controls_pos("left")
    assert w._stage.direction() == QBoxLayout.RightToLeft
    assert w._controls_lay.direction() == QBoxLayout.TopToBottom
    assert st.vals["square_flow/controls_pos"] == "left"
    w.set_controls_pos("quer")                  # unbekannt: bleibt
    assert w._controls_pos == "left"
    w2 = keep(SquareFlowWidget(settings=_Settings(enabled=True, controls_pos="above")))
    assert w2._stage.direction() == QBoxLayout.BottomToTop


def test_pilot_farben_am_taenzer_und_umschaltbar(keep):
    """Phase 3 (intern#249): Pilot-Farbe je Taenzer, ohne Farbe Standard, Umschalter gemerkt."""
    st = _RwSettings(enabled=True)
    w = keep(SquareFlowWidget(settings=st))
    assert w._use_pilot is True                     # Standard an
    w.set_pilot_data({(1, True): {"color": "#e74c3c", "name": ""}, (2, False): {"color": None, "name": ""}})
    assert w._floor.pilot == {(1, True): {"color": "#e74c3c", "name": ""}}  # leer -> nicht drin
    w.set_use_pilot_colors(False)
    assert w._floor.pilot == {}
    assert st.vals["square_flow/pilot_colors"] is False
    w.set_use_pilot_colors(True)
    assert w._floor.pilot == {(1, True): {"color": "#e74c3c", "name": ""}}
    w.set_pilot_data({})
    assert w._floor.pilot == {}
    w2 = keep(SquareFlowWidget(settings=_Settings(enabled=True, pilot_colors=False)))
    assert w2._use_pilot is False


def test_doppelklick_meldet_taenzer(keep):
    """Doppelklick auf einen Taenzer fordert die Bearbeitung im Pilot Square an (#249)."""
    from PySide6.QtCore import QPointF
    w = keep(SquareFlowWidget(settings=_Settings(enabled=True)))
    got = []
    w.dancer_edit_requested.connect(lambda c, b: got.append((c, b)))
    d = {"n": "3", "couple": "2", "boy": False}
    w._floor._hits = [(QPointF(50, 50), 10.0, d)]
    assert w._floor.dancer_at(QPointF(90, 90)) is None
    assert w._floor.dancer_at(QPointF(55, 52)) is d
    w._on_dancer_double_click(d)
    assert got == [(2, False)]


def test_abbruch_mit_fehlertext_wird_getanzt_engine_fehler_nicht(keep):
    """Ein Abbruch traegt den Fehlertext der Engine, ist aber ein Ergebnis (intern#247)."""
    w = keep(SquareFlowWidget(settings=_Settings(enabled=True)))
    w._seq = (("Heads Square Thru 4", "Foo"), "Static Set ➔ Resolve")
    results = []
    w.result_ready.connect(lambda c, r: results.append(r))
    w._token = 1
    r = _result()
    r.update({"stufe1": False, "urteil": None, "fail_card": 1,
              "error": "Call Foo not found"})
    w._on_ready(1, r)
    assert w._result is r and results[-1] is r
    w._on_ready(1, {"error": "engine_missing"})
    assert results[-1] == {"error": "engine_missing"}    # Sequenz-Detail erfaehrt es
    assert w._result is r                                 # letzte Animation bleibt
