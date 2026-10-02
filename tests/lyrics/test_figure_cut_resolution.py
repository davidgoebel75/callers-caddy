"""Tests fuer die Schnitt-Zeilen-Aufloesung im LyricsWidget (BL-200).

_resolve_block_cut entscheidet je Figuren-Block: manueller User-Override (per
Drag gesetzt) vor Algorithmus-Default. Der Override wird auf den Block geklemmt.
Rein logisch pruefbar ueber ein uninitialisiertes Widget (__new__) mit gesetzten
Attributen — kein Browser noetig, weil _block_default_cut hier mit expliziten
`lines` aufgerufen wird.
"""
import lyrics_widget as lw


def _make(sections, cuts):
    w = lw.LyricsWidget.__new__(lw.LyricsWidget)
    w._DYNAMIC_FIGURES = ("figure1", "figure2", "figure3", "figure4")
    w._lyric_sections = sections
    w._figure_cuts = cuts
    return w


# Ein Block: Kopfzeile 3, Inhalt 4..11, echte Heim-Promenade auf Zeile 9.
LINES = [""] * 3 + [
    "FIGURE",                       # 3 (Kopf)
    "heads promenade half way",     # 4
    "square thru four",             # 5
    "swing thru",                   # 6
    "boys run",                     # 7
    "square thru three",            # 8
    "swing corner and promenade",   # 9 = Algorithmus-Schnitt
    "song tail one",                # 10
    "song tail two",                # 11
]


def test_default_ohne_override():
    w = _make({"figure1": (3, 11)}, {})
    assert w._resolve_block_cut(3, 11, LINES) == 9


def test_override_gewinnt():
    w = _make({"figure1": (3, 11)}, {"figure1": 8})
    assert w._resolve_block_cut(3, 11, LINES) == 8


def test_override_wird_auf_block_geklemmt():
    # Zu weit unten -> auf l1, zu weit oben -> auf l0+1.
    assert _make({"figure1": (3, 11)}, {"figure1": 99})._resolve_block_cut(3, 11, LINES) == 11
    assert _make({"figure1": (3, 11)}, {"figure1": 0})._resolve_block_cut(3, 11, LINES) == 4


def test_override_nur_bei_passendem_bereich():
    # Ein Override haengt am exakten Block; ein anderer Block (kein Override,
    # kein Promenade-Signal) faellt auf den Default = end_line zurueck.
    lines = LINES + [""] * 20  # Zeilen 20..28 leer -> kein Schnitt
    w = _make({"figure1": (3, 11)}, {"figure1": 8})
    assert w._resolve_block_cut(20, 28, lines) == 28
