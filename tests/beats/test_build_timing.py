"""intern#164: Build-Werkzeug der Beat-Tabelle (Pruefung + JSON)."""
import importlib.util
import json
from pathlib import Path

import pytest

from caddy.beats import calc

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location(
    "build_callerlab_timing", ROOT / "tools" / "beats" / "build_callerlab_timing.py")
bt = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bt)

REF = {"call_a", "call_b", "call_c"}


def row(**kw):
    r = {c: "" for c in bt.COLUMNS}
    r.update(programm="MS", call="A", entity_ids="call_a", variante="", typ="fest",
             beats="4", quelle="MS 2026-07-05", standard="1")
    r.update(kw)
    return r


def errors(*rows):
    return bt.validate(list(bt.COLUMNS), list(rows), REF)


def test_gueltige_zeilen():
    assert errors(row(), row(call="B", entity_ids="call_b|call_c", standard="1"),
                  row(call="AB", entity_ids="call_a+call_b", standard="")) == []


@pytest.mark.parametrize("kw, teil", [
    (dict(pruefen="bitte ansehen"), "noch zu pruefen"),
    (dict(programm="C1"), "programm"),
    (dict(typ="fix"), "typ"),
    (dict(beats="4.5"), "keine ganze Zahl"),
    (dict(beats=""), "braucht beats"),
    (dict(typ="bereich"), "braucht beats_bis"),
    (dict(typ="bereich", beats_bis="4"), "nicht groesser"),
    (dict(beats_bis="6"), "nur bei bereich"),
    (dict(typ="not_timed"), "not_timed ohne"),
    (dict(variante_regel="numbr=4"), "variante_regel"),
    (dict(entity_ids="call_x"), "fehlt in reference_calls"),
    (dict(entity_ids="call_a|"), "leeres Teilstueck"),
    (dict(entity_ids="call_a+call_a"), "doppelt in der Kombination"),
    (dict(quelle="MS 2022"), "quelle"),
    (dict(standard="ja"), "standard"),
])
def test_fehler_werden_gemeldet(kw, teil):
    assert any(teil in e for e in errors(row(**kw))), errors(row(**kw))


def test_standard_genau_einmal_je_call_und_chart():
    assert any("2 Standard-Zeilen" in e for e in errors(row(), row(variante="SS")))
    assert any("0 Standard-Zeilen" in e for e in errors(row(standard="")))
    assert errors(row(), row(programm="Plus")) == []


def test_doppelte_zeile():
    assert any("doppelt" in e for e in errors(row(), row(standard="")))


def test_falsche_spalten():
    assert bt.validate(["programm", "call"], [], REF)


def test_pflegedatei_besteht_die_pruefung():
    fieldnames, rows = bt.read_csv()
    assert bt.validate(fieldnames, rows, bt.reference_ids()) == []


def test_json_ist_aktuell():
    _, rows = bt.read_csv()
    assert Path(bt.JSON_PATH).read_text(encoding="utf-8") == bt.dump(bt.build(rows)), \
        "tools/beats/build_callerlab_timing.py ausfuehren"


def test_json_laesst_sich_rechnen():
    data = json.loads(Path(bt.JSON_PATH).read_text(encoding="utf-8"))
    assert len(data["version"]) == 16 and "pruefen" not in data["rows"][0]
    table = calc.BeatTable(data["rows"])
    b = calc.line_beats(table, ["call_square_thru"], "Square Thru 4")
    assert (b.lo, b.hi) == (10, 10)


def test_version_folgt_dem_inhalt():
    _, rows = bt.read_csv()
    v1 = bt.build(rows)["version"]
    rows[0] = dict(rows[0], bemerkung="geaendert")
    assert bt.build(rows)["version"] != v1
