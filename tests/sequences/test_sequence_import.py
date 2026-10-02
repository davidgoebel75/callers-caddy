"""Tests fuer den Sequenz-Import (sequence_import.py, intern#21).

Qt-frei: Strings bzw. temporaere Dateien rein, Sequenz-Dicts raus.
MDB bleibt ungetestet (braucht den Access-Treiber).
"""
import json

import pytest

import sequence_import as si


def _write(tmp_path, name, content, newline=None):
    p = tmp_path / name
    with open(p, "w", encoding="utf-8", newline=newline) as f:
        f.write(content)
    return str(p)


# ---- Freitext ----

def test_freitext_eine_zeile_pro_sequenz_mit_komma():
    text = "Heads Square Thru 4, Swing Thru, Boys Run\nSides Lead Right, Veer Left\n"
    # Ohne Leerzeile ist beides EIN Block -> zwei Zeilen = zwei Calls
    assert si.parse_freetext(text) == [
        ["Heads Square Thru 4, Swing Thru, Boys Run", "Sides Lead Right, Veer Left"]]
    text = "Heads Square Thru 4, Swing Thru, Boys Run\n\nSides Lead Right, Veer Left\n"
    assert si.parse_freetext(text) == [
        ["Heads Square Thru 4", "Swing Thru", "Boys Run"],
        ["Sides Lead Right", "Veer Left"],
    ]


def test_freitext_ein_call_pro_zeile_mit_trennzeichen():
    text = "Heads Square Thru 4,\nSwing Thru;\n\n\nSides Pass Thru\nTrade By\n"
    assert si.parse_freetext(text) == [
        ["Heads Square Thru 4", "Swing Thru"],
        ["Sides Pass Thru", "Trade By"],
    ]


def test_freitext_ceder_header_trennt_und_wird_verworfen():
    text = ("Mainstream -- Singer (Corner progression)   Easy   ID=6734   Print\n"
            "Heads Promenade Half\n"
            "Plus -- Singer   Hard   ID=12   Print\n"
            "Sides Touch 1/4\n")
    assert si.parse_freetext(text) == [["Heads Promenade Half"], ["Sides Touch 1/4"]]


def test_freitext_doppeltes_cr_erzeugt_keine_phantom_sequenzen(tmp_path):
    # SqView-Export: '\r\r\n' je Zeile. Darf nicht jeden Call zur Sequenz machen.
    content = "Heads Pass Thru\r\r\nSwing Thru\r\r\n\r\r\nSides Pass Thru\r\r\n"
    path = _write(tmp_path, "sqview.txt", content, newline="")
    seqs = si.parse_files([path], si.FMT_FREETEXT)
    assert [s["calls"] for s in seqs] == [["Heads Pass Thru", "Swing Thru"],
                                          ["Sides Pass Thru"]]


# ---- CSDS ----

CSDS = """@
#PROOFREAD#
#EASY#
#REC=6734#
#SEQTYPE=10#
#AUTHOR=Someone#
Heads Square Thru 4,
<C ALT="Swing Thru">Swing Thru</C>,
Boys Run,
@
#HARD#
#REC=77#
#SEQTYPE=999#
Sides Lead Right,
@
"""


def test_csds_meta_und_calls(tmp_path):
    seqs = si.parse_files([_write(tmp_path, "a.csds", CSDS)], si.FMT_CSDS)
    assert seqs[0] == {
        "calls": ["Heads Square Thru 4", "Swing Thru", "Boys Run"],
        "seq_type": "Singer (Corner progression)",
        "difficulty": "Easy",
        "level": "",
        "source_id": "6734",
    }
    # Unbekannte SEQTYPE-Nummer bleibt als Rohwert stehen
    assert seqs[1]["seq_type"] == "999"
    assert seqs[1]["difficulty"] == "Hard"


def test_csds_dubletten_ueber_rec_auch_ueber_dateien(tmp_path):
    a = _write(tmp_path, "a.csds", CSDS)
    b = _write(tmp_path, "b.csds", CSDS)
    seqs = si.parse_files([a, b], si.FMT_CSDS)
    assert [s["source_id"] for s in seqs] == ["6734", "77"]


# ---- JSON ----

def test_json_dubletten_ueber_id_und_leere_calls(tmp_path):
    data = [
        {"id": "1", "calls": ["Heads Pass Thru", " "], "seq_type": "Singing break",
         "difficulty": "Easy", "level": "MS"},
        {"id": "1", "calls": ["Doppelt"]},
        {"id": "2", "calls": []},
        "kein dict",
        {"calls": ["Ohne Id"]},
    ]
    path = _write(tmp_path, "a.json", json.dumps(data))
    seqs = si.parse_files([path], si.FMT_JSON)
    assert [s["calls"] for s in seqs] == [["Heads Pass Thru"], ["Ohne Id"]]
    assert seqs[0]["seq_type"] == "Singing break"
    assert seqs[0]["level"] == "MS"


def test_json_ohne_array_wird_uebersprungen(tmp_path):
    obj = _write(tmp_path, "obj.json", json.dumps({"calls": ["X"]}))
    kaputt = _write(tmp_path, "kaputt.json", "[{")
    assert si.parse_files([obj, kaputt], si.FMT_JSON) == []


# ---- Format-Erkennung ----

@pytest.mark.parametrize("name,content,fmt", [
    ("alt.mdb", "", si.FMT_MDB),
    ("alt.ACCDB", "", si.FMT_MDB),
    ("x.txt", CSDS, si.FMT_CSDS),
    ("x.txt", '[{"calls": ["A"]}]', si.FMT_JSON),
    ("x.json", "kein json", si.FMT_FREETEXT),
    ("x.txt", "Heads Pass Thru\nSwing Thru\n", si.FMT_FREETEXT),
])
def test_detect_format(tmp_path, name, content, fmt):
    assert si.detect_format(_write(tmp_path, name, content)) == fmt


# ---- Schreibweise ----

@pytest.mark.parametrize("text,mode,expected", [
    ("1ST GIRL", si.CASE_TITLE, "1st Girl"),
    ("WALK-GIRLS", si.CASE_TITLE, "Walk-Girls"),
    ("(LOOK AT HER)", si.CASE_TITLE, "(Look At Her)"),
    ("swing thru", si.CASE_UPPER, "SWING THRU"),
    ("sWiNg", si.CASE_ASIS, "sWiNg"),
])
def test_apply_case(text, mode, expected):
    assert si.apply_case(text, mode) == expected


# ---- Invariante zu song_db ----

def test_seqtype_namen_sind_kanonisch():
    from song_db import canonicalize_seq_type
    for name in si.SEQTYPE_NAMES.values():
        assert canonicalize_seq_type(name) == name
