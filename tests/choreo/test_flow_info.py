"""Aufbereitung des Square-Flow-Ergebnisses fuer die Anzeige (intern#247)."""
from caddy.choreo import flow_info


def test_hinweise_bei_abbruch_und_ergaenzung():
    r = {"stufe1": False, "fail_card": 1, "urteil": None, "type": "",
         "read_as": [{"card": 0, "text": "Heads Bend The Line", "kind": "kontext",
                      "meaning": True},
                     {"card": 2, "text": "Allemande Left", "kind": "roh", "meaning": False}]}
    lines, strong = flow_info.hint_lines(r, ("Bend The Line", "Boys Rnu", "L.A."))
    assert strong
    assert "Boys Rnu" in lines[0]
    assert any("Heads Bend The Line" in x for x in lines)
    assert not any("Allemande Left" in x for x in lines)


def test_detail_info_engine_fehlt_oder_stuerzt_ab():
    missing = flow_info.detail_info(("Dosado",), {"error": "engine_missing"})
    assert missing["warn"] and missing["warn_text"]
    crash = flow_info.detail_info(("Dosado",), {"error": "BrokenPipeError: x"})
    assert crash["warn"] and "BrokenPipeError" in crash["warn_text"]
    assert "beats" not in crash
    assert flow_info.detail_info(("Dosado",), None) is None


def test_detail_info_mit_ergebnis():
    r = {"stufe1": True, "urteil": "gruen", "type": "Singer", "card_beats": [8, 16],
         "beats_total": 24, "fail_card": None, "read_as": []}
    info = flow_info.detail_info(("Dosado", "Swing"), r)
    assert info == {"beats": [8, 16], "total": 24, "singer": True, "fail_card": None,
                    "warn": False, "warn_text": ""}
    rot = flow_info.detail_info(("Dosado",), dict(r, urteil="rot"))
    assert rot["warn"] and rot["warn_text"]
