"""Rule-Aktion "Set System Volume" und Zeitpunkt von "App Started" (intern#222)."""
import types

import pytest

from caddy.rules import system_volume
from caddy.rules.system_volume import pick_endpoint, target_level


@pytest.mark.parametrize("current, percent, mode, erwartet", [
    (0.30, 80, "at_least", 0.80),   # zu leise -> anheben
    (0.95, 80, "at_least", None),   # bewusst lauter -> stehen lassen
    (0.95, 80, "exact", 0.80),      # exakt -> auch absenken
    (0.80, 80, "exact", None),      # schon richtig -> nichts tun
    (0.50, 150, "exact", 1.0),      # auf 0-100 % begrenzt
    (0.50, -5, "exact", 0.0),
])
def test_zielpegel(current, percent, mode, erwartet):
    assert target_level(current, percent, mode) == erwartet


ENDPOINTS = [("Lautsprecher (Realtek(R) Audio)", "realtek"),
             ("Kopfhörer (USB Audio Device)", "usb"),
             ("Lautsprecher (3- Samson Meteor Mic)", "samson")]


@pytest.mark.parametrize("name, erwartet", [
    ("Kopfhörer (USB Audio Device)", "usb"),       # WASAPI: voller Name
    ("Lautsprecher (Realtek(R) Audi", "realtek"),  # MME: auf 31 Zeichen gekuerzt
    ("Lautsprecher (Samson Meteor Mic)", "samson"),  # WDM-KS: ohne "3- "
    ("lautsprecher (realtek(r) audio)", "realtek"),
    ("SPDIF Out (Realtek)", None),                 # kein Treffer -> Standardgeraet
    (None, None),
    ("", None),
])
def test_geraet_ueber_namen(name, erwartet):
    assert pick_endpoint(name, ENDPOINTS) == erwartet


def test_mehrdeutiger_praefix_nimmt_das_standardgeraet():
    zwei = [("Lautsprecher (Realtek(R) Audio)", "erstes"),
            ("Lautsprecher (Realtek(R) Audio 2)", "zweites")]
    assert pick_endpoint("Lautsprecher (Realtek(R) Audi", zwei) is None
    assert pick_endpoint("Lautsprecher (Realtek(R) Audio)", zwei) == "erstes"
    assert pick_endpoint("Lautsprecher (Realtek(R) Audio 2)", zwei) == "zweites"


def test_aktion_laeuft_im_thread_und_loggt(monkeypatch):
    main_thread = system_volume.threading.current_thread()
    seen = {}

    def fake(percent, mode, device_name):
        seen["thread"] = system_volume.threading.current_thread()
        return f"ok {percent} {mode} {device_name}"
    monkeypatch.setattr(system_volume, "set_system_volume", fake)
    lines = []

    t = system_volume.start_system_volume(70, "exact", "Gerät", log=lines.append)
    t.join(5)

    assert t.daemon
    assert seen["thread"] is not main_thread
    assert lines == ["ok 70 exact Gerät"]


def test_fehler_im_thread_landet_im_log(monkeypatch):
    def kaputt(*_a):
        raise OSError("COM weg")
    monkeypatch.setattr(system_volume, "set_system_volume", kaputt)
    lines = []

    system_volume.start_system_volume(70, log=lines.append).join(5)

    assert lines == ["Set System Volume: Fehler COM weg"]


def test_aktion_registriert(tmp_path):
    from rule_definitions import register_v1_definitions
    from rule_engine import RuleEngine

    eng = RuleEngine(str(tmp_path))
    register_v1_definitions(eng)
    a = eng.registry.actions["system_volume_set"]
    assert a.group == "Audio"
    assert a.params_schema["value"]["default"] == 80
    assert a.params_schema["mode"]["choices"] == ["at_least", "exact"]
    assert a.params_schema["mode"]["default"] == "at_least"


def _start_win(detect, broken=None):
    import main

    fired = []
    win = types.SimpleNamespace(
        _auto_detect_location_on_startup=detect,
        rule_engine=types.SimpleNamespace(fire_trigger=fired.append,
                                          broken_user_rules_path=broken))
    return main, win, fired


def test_start_meldet_beiseitegelegte_regeldatei(monkeypatch):
    """intern#257: Meldung vor der Lokations-Erkennung, mit dem Pfad."""
    ablauf = []
    main, win, fired = _start_win(lambda: ablauf.append("lokation"),
                                  broken="C:/x/rules_user.json.broken-1")
    monkeypatch.setattr(main.QMessageBox, "warning",
                        lambda parent, title, text: ablauf.append(text))

    main.P29MainWindow._finish_startup(win)

    assert ablauf[1:] == ["lokation"]
    assert "C:/x/rules_user.json.broken-1" in ablauf[0]


def test_app_started_kommt_nach_der_lokations_erkennung():
    ablauf = []
    main, win, fired = _start_win(lambda: ablauf.append("lokation"))
    win.rule_engine.fire_trigger = lambda t: ablauf.append(t)

    main.P29MainWindow._finish_startup(win)

    assert ablauf == ["lokation", "app_started"]


def test_app_started_feuert_auch_wenn_die_erkennung_scheitert():
    def kaputt():
        raise RuntimeError("DB weg")
    main, win, fired = _start_win(kaputt)

    with pytest.raises(RuntimeError):
        main.P29MainWindow._finish_startup(win)
    assert fired == ["app_started"]
