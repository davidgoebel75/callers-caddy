"""Suchfenster des Loop Finders: Preset + Songdauer -> Sekunden (intern#207).

Prozent- und Zeit-Presets, alte Presets ohne ``mode`` und die Grenzfaelle,
in denen keine Analyse laufen soll.
"""
import json

import pytest

import loop_windows as lw


def test_preset_ohne_mode_gilt_als_prozent():
    old = {"in_start": 10, "in_end": 20, "out_start": 70, "out_end": 80}
    assert lw.preset_mode(old) == lw.MODE_PCT
    assert lw.resolve_windows(old, 200.0) == (20.0, 40.0, 140.0, 160.0)


def test_unbekannter_mode_gilt_als_prozent():
    assert lw.preset_mode({"mode": "xyz"}) == lw.MODE_PCT


def test_singing_preset_ist_prozent():
    p = lw.singing_preset()
    assert p["mode"] == lw.MODE_PCT
    assert lw.resolve_windows(p, 100.0) == (7.0, 21.0, 64.0, 79.0)


def test_zeit_preset_loop_in_ab_beginn_loop_out_vor_ende():
    p = {"mode": "time", "in_start": 20, "in_end": 59,
         "out_start": 50, "out_end": 20}
    assert lw.resolve_windows(p, 180.0) == (20.0, 59.0, 130.0, 160.0)


@pytest.mark.parametrize("preset, duration", [
    # Fenster ueberschneiden sich (Loop-In reicht in Loop-Out)
    ({"mode": "time", "in_start": 20, "in_end": 100,
      "out_start": 90, "out_end": 20}, 150.0),
    # Song zu kurz: Loop-In ragt ueber das Ende hinaus
    ({"mode": "time", "in_start": 20, "in_end": 59,
      "out_start": 50, "out_end": 20}, 40.0),
    # Loop-Out reicht vor den Songbeginn
    ({"mode": "time", "in_start": 0, "in_end": 5,
      "out_start": 200, "out_end": 10}, 120.0),
    # Leeres Fenster
    ({"mode": "time", "in_start": 30, "in_end": 30,
      "out_start": 50, "out_end": 20}, 180.0),
    # Prozent ueber 100
    ({"in_start": 10, "in_end": 20, "out_start": 70, "out_end": 120}, 200.0),
])
def test_unpassende_fenster_liefern_none(preset, duration):
    assert lw.resolve_windows(preset, duration) is None


@pytest.mark.parametrize("duration", [0, -1, None])
def test_ohne_songdauer_kein_fenster(duration):
    assert lw.resolve_windows(lw.singing_preset(), duration) is None


def test_kaputte_werte_liefern_none():
    assert lw.resolve_windows({"in_start": "abc"}, 100.0) is None


def test_umrechnung_prozent_zeit_und_zurueck():
    t = lw.pct_to_time((7, 21, 64, 79), 200.0)
    assert t == (14, 42, 72, 42)
    assert lw.time_to_pct(t, 200.0) == (7, 21, 64, 79)


def test_umrechnung_nach_prozent_bleibt_in_0_bis_100():
    assert lw.time_to_pct((0, 300, 400, 0), 200.0) == (0, 100, 0, 100)


def test_load_preset_file(tmp_path):
    (tmp_path / "Intro.json").write_text(json.dumps(
        {"mode": "time", "in_start": 20, "in_end": 59,
         "out_start": 50, "out_end": 20}), encoding="utf-8")
    assert lw.load_preset_file("Intro", str(tmp_path))["mode"] == "time"
    # Unbekannt, alter Name oder ohne Ordner -> Singing
    assert lw.load_preset_file("Fehlt", str(tmp_path)) == lw.singing_preset()
    assert lw.load_preset_file("Standard", str(tmp_path)) == lw.singing_preset()
    assert lw.load_preset_file("Intro", None) == lw.singing_preset()


def test_load_preset_file_kaputtes_json(tmp_path):
    (tmp_path / "Kaputt.json").write_text("{", encoding="utf-8")
    assert lw.load_preset_file("Kaputt", str(tmp_path)) == lw.singing_preset()
