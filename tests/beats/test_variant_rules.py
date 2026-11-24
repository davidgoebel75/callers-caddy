"""intern#164: Variantenregeln der Beat-Tabelle (caddy.beats.variant_rules) und Pflegedatei."""
import collections
import csv
from pathlib import Path

import pytest

from caddy.beats import variant_rules as vr

CSV_PATH = Path(__file__).resolve().parents[2] / "tools" / "beats" / "callerlab_timing.csv"


@pytest.mark.parametrize("text, expected", [
    ("", {}),
    ("number=4", {"number": "4"}),
    ("ss, odd", {"ss": True, "odd": True}),
    ("number=2,minus_pass_thru", {"number": "2", "minus_pass_thru": True}),
    ("fraction=3/4", {"fraction": "3/4"}),
])
def test_parse_gueltig(text, expected):
    assert vr.parse(text) == expected


@pytest.mark.parametrize("text", [
    "nummer=4", "number", "number=vier", "fraction=2/3", "ss=1", "odd,even", "ss,ss",
])
def test_parse_weist_falsches_ab(text):
    with pytest.raises(vr.RuleError):
        vr.parse(text)


@pytest.mark.parametrize("text, frac", [
    ("Promenade 1/2", "1/2"), ("Promenade Halfway", "1/2"), ("Half Tag", "1/2"),
    ("Circle Left 3/4", "3/4"), ("Circle Left Three Quarters", "3/4"),
    ("Shoot The Star Full Turn", "full"), ("Promenade", None),
])
def test_bruchteil_im_text(text, frac):
    assert vr.text_fraction(text) == frac


def test_zahl_im_text_ignoriert_brueche_und_nimmt_die_letzte():
    assert vr.text_number("Heads Square Thru 4") == 4
    assert vr.text_number("Center 4 Square Thru 2") == 2
    assert vr.text_number("Square Thru 3/4") is None
    assert vr.text_number("Square Thru") is None


def test_squared_set_erkennung():
    assert vr.from_squared_set("Heads Pass Thru")
    assert vr.from_squared_set("(Then) Sides Square Thru 4")
    assert not vr.from_squared_set("Pass Thru")
    assert not vr.from_squared_set("Centers Pass Thru")


SQUARE_THRU = [
    {"variante": "FC 1", "variante_regel": "number=1", "standard": ""},
    {"variante": "FC 2", "variante_regel": "number=2", "standard": ""},
    {"variante": "FC 3", "variante_regel": "number=3", "standard": ""},
    {"variante": "FC 4", "variante_regel": "number=4", "standard": "1"},
    {"variante": "SS odd", "variante_regel": "ss,odd", "standard": ""},
]


@pytest.mark.parametrize("text, variante, wie", [
    ("Square Thru 2", "FC 2", "regel"),
    ("Square Thru", "FC 4", "standard"),
    ("Heads Square Thru 4", "FC 4", "regel"),
    ("Heads Square Thru 3", "SS odd", "regel"),      # spezifischere Regel gewinnt
    ("Square Thru 5", "FC 4", "standard"),
])
def test_choose_square_thru(text, variante, wie):
    row, how = vr.choose(SQUARE_THRU, text)
    assert (row["variante"], how) == (variante, wie)


def test_ss_nur_aus_dem_squared_set():
    rows = [{"variante": "FC", "variante_regel": "", "standard": "1"},
            {"variante": "SS", "variante_regel": "ss", "standard": ""}]
    assert vr.choose(rows, "Heads Pass Thru")[0]["variante"] == "SS"
    assert vr.choose(rows, "Heads Pass Thru", squared_set=True)[0]["variante"] == "SS"
    assert vr.choose(rows, "Heads Pass Thru", squared_set=False)[0]["variante"] == "FC"


def test_choose_parts_nur_mit_zahl():
    rows = [{"variante": "eight hands", "variante_regel": "", "standard": "1"},
            {"variante": "odd part", "variante_regel": "parts", "standard": ""}]
    assert vr.choose(rows, "Eight Chain Thru")[0]["variante"] == "eight hands"
    assert vr.choose(rows, "Eight Chain 4")[0]["variante"] == "odd part"


# ---- Pflegedatei ----

def _rows():
    with open(CSV_PATH, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f, delimiter=";"))


def test_pflegedatei_regeln_sind_gueltig():
    for r in _rows():
        vr.parse(r["variante_regel"])


def test_pflegedatei_genau_ein_standard_je_app_call_und_chart():
    std, have = collections.Counter(), set()
    for r in _rows():
        for e in (x for x in r["entity_ids"].split("|") if x):
            have.add((r["programm"], e))
            std[(r["programm"], e)] += r["standard"] == "1"
    assert sorted(k for k in have if std[k] != 1) == []
