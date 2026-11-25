"""Choreo-Mapping (intern#247): Portierung aus dem Pruefstand bleibt ergebnisgleich.

mapping_golden.json ist eine Stichprobe der Testbasis (DB-Stand 2026-11-08, 6.838 Sequenzen
MS50-A2) mit dem erwarteten Export des Pruefstand-Laufs `kontrolle_2026-11-15` und der
Engine-Antwort fuer die Heimplatz-Pruefung. Erzeugt mit tools/choreo_mapping_check.py --golden;
die volle Gegenprobe (alle Sequenzen, auch Pruefband) laeuft mit demselben Werkzeug.
Wer eine Regel bewusst aendert, erzeugt die Datei neu und begruendet die Abweichungen im Issue.
"""
import json
import os

import pytest

from caddy.choreo import mapping

GOLDEN = os.path.join(os.path.dirname(__file__), "mapping_golden.json")
FIELDS = ("n_start", "end", "orig", "lines", "lines_woertlich", "lines_ergaenzt")


def _cases():
    with open(GOLDEN, encoding="utf-8") as f:
        return json.load(f)


def _export(case):
    prep = mapping.prepare(case["calls"], case["type"], case["app"])
    lines, zweit, art = mapping.finish(prep, case["heimplatz_response"])
    item = {"n_start": prep["n_start"], "end": prep["end"], "orig": prep["orig"], "lines": lines,
            "lines_woertlich": zweit if art == "woertlich" else None,
            "lines_ergaenzt": zweit if art == "ergaenzt" else None}
    return item


def test_stichprobe_gleich_wie_pruefstand():
    cases = _cases()
    assert len(cases) > 300
    bad = [c["id"] for c in cases
           if any(_export(c)[f] != c["expected"].get(f) for f in FIELDS)]
    assert bad == []


def test_stichprobe_enthaelt_gekuerzte_heimplatz_fassung():
    """Mindestens ein Fall, in dem die Heimplatz-Pruefung die ergaenzte Fassung kuerzt."""
    n = 0
    for c in _cases():
        prep = mapping.prepare(c["calls"], c["type"], c["app"])
        if prep["zweit"] and c["heimplatz_response"]:
            cut = mapping.heimplatz_cut(prep["zweit"], prep["lines"], prep["kreis_of"],
                                        c["heimplatz_response"])
            n += cut != prep["zweit"]
    assert n >= 1


def test_zero_box_aus_typ_und_singer_ende():
    prep = mapping.prepare(["Heads Square Thru 4", "Swing Thru", "Boys Run", "Swing & Promenade"],
                           "Singer (Corner progression)")
    assert prep["n_start"] == 0
    assert prep["end"] == "Swing Corner and Promenade"
    assert prep["orig"] == ["Heads Square Thru 4", "Swing Thru", "Boys Run"]


def test_kartenzeile_je_gesendeter_zeile():
    calls = ["Pass Thru", "Tag The Line Right", "Ferris Wheel", "L.A."]
    prep = mapping.prepare(calls, "Zero Box ➔ Resolve")
    # Zero Box aus dem Typ: Pseudo-Zeile ohne Kartenzeile; Tag The Line Right = zwei Zeilen
    assert prep["n_start"] == 1
    assert prep["src"] == [None, 0, 1, 1, 2]
    assert prep["end"] == "Allemande Left"
    assert prep["end_src"] == 3


def test_kartenzeile_bei_doppeltem_text():
    calls = ["Heads Square Thru 4", "Ends Circulate", "Ends Circulate", "Allemande Left"]
    prep = mapping.prepare(calls, "Static Set ➔ Resolve")
    assert prep["src"] == [0, 1, 2]
    assert prep["end_src"] == 3


@pytest.mark.parametrize("rule", ["tabelle", "kreis_fortschreiben"])
def test_regel_abschaltbar_fuer_gegenprobe(monkeypatch, rule):
    monkeypatch.setattr(mapping, "RULES", set(mapping.ALL_RULES) - {rule})
    mapping.prepare(["Heads Swing Thru", "Boys Run"], "Static Set ➔ Resolve")
