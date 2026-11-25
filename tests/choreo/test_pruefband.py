"""Endkontrolle (intern#247): Pruefband, Urteil, Lesart, Probe-Call."""
import math
import os

import pytest

from caddy.choreo import engine, mapping, pruefband

# Static Square, wie tam_cli ihn liefert (animation.dancers / frames[0], 1.6.115)
DANCERS = [{"n": n, "couple": c, "boy": b} for n, c, b in
           [("1", "1", True), ("5", "3", True), ("2", "1", False), ("6", "3", False),
            ("3", "2", True), ("7", "4", True), ("4", "2", False), ("8", "4", False)]]
STATIC = [[-3.0, 1.0, 0.0], [3.0, -1.0, 180.0], [-3.0, -1.0, 0.0], [3.0, 1.0, 180.0],
          [-1.0, -3.0, 90.0], [1.0, 3.0, -90.0], [1.0, -3.0, 90.0], [-1.0, 3.0, -90.0]]


def _static_square():
    return [list(p) for p in STATIC]


def test_gedrehter_square_bleibt_gruen():
    rot = [[-y, x, w + 90] for x, y, w in STATIC]
    assert pruefband.end_check(DANCERS, rot, [("1B", "1G"), ("2B", "2G")], False) == "gruen"
    assert math.isclose(rot[0][2], 90.0)


def test_partner_im_static_square_gruen():
    res = pruefband.end_check(DANCERS, _static_square(), [("1B", "1G"), ("2B", "2G")], False)
    assert res == "gruen"


def test_corner_im_static_square_nicht_zusammen():
    res = pruefband.end_check(DANCERS, _static_square(), [("1B", "2G"), ("2B", "3G")], False)
    assert res == "nicht_zusammen"


def test_unbekanntes_paar_ohne_aussage():
    assert pruefband.end_check(DANCERS[:4], _static_square()[:4],
                               [("1B", "1G"), ("2B", "2G")], False) is None


@pytest.mark.parametrize("band,tam,urteil", [
    ("gruen", True, "gruen"), ("gruen", False, "strittig"), ("gruen", None, "nur_band_gruen"),
    ("blick", True, "rot"), ("nicht_zusammen", None, "rot"), (None, True, None),
])
def test_endurteil(band, tam, urteil):
    assert pruefband.endurteil(band, tam) == urteil


def test_targets_und_ignorierte_typen():
    assert pruefband.targets_for("Singer (Corner progression)") == [("1B", "4G"), ("1G", "2B")]
    assert pruefband.targets_for("Stir the bucket") is None


def test_probe_call():
    pairs = pruefband.targets_for("Static Set ➔ Resolve")
    assert pruefband.probe_call("Static Set ➔ Resolve", "Allemande Left", pairs) == "Promenade Corner"
    sing = pruefband.targets_for("Singer (Corner progression)")
    assert pruefband.probe_call("Singer (Corner progression)", "Swing Corner and Promenade",
                                sing) == "Promenade Corner"


def test_lesart():
    lines = ["Heads Square Thru 4",
             {"alts": [["Swing Thru"], ["Heads Swing Thru"]], "kinds": ["roh", "kontext"]}]
    assert pruefband.lesart(lines, [0, 0]) == "woertlich"
    assert pruefband.lesart(lines, [0, 1]) == "rueckfall"


def test_ohne_engine_kein_absturz():
    eng = engine.TamEngine(path=os.path.join(os.path.dirname(__file__), "gibt_es_nicht.exe"))
    assert not eng.available()
    res = pruefband.analyse(eng.run, "Static Set ➔ Resolve", "Allemande Left", 0,
                            ["Heads Square Thru 4"])
    assert res["stufe1"] is False and res["urteil"] is None
    assert res["engine"]["error"] == "engine_missing"


@pytest.mark.skipif(engine.find_engine() is None, reason="tam_cli nicht vorhanden")
def test_mit_engine_einfache_sequenz_gruen():
    eng = engine.TamEngine()
    try:
        prep = mapping.prepare(["Heads Square Thru 4", "Right & Left Thru", "Dive Thru",
                                "Square Thru 3", "L.A."], "Static Set ➔ Resolve")
        lines, zweit, art = mapping.finish(prep)
        res = pruefband.analyse(eng.run, prep["type"], prep["end"], prep["n_start"],
                                lines, zweit, art)
        assert res["stufe1"] and res["urteil"] == "gruen"
        assert len(res["line_beats"]) == len(lines)
        assert eng.version()
    finally:
        eng.close()
