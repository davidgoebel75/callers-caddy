"""Tanzprogramm-Wahl ohne Qt (intern#143): Band, Programm-Reihe, Figuren."""
import program_selection as ps

# (id, code, label, sort_order, target_duration_min, sequence_limit_to)
PROGRAMS = [
    (1, "B1", "Basic 1", 10, 0, 10.999999),
    (2, "B2", "Basic 2", 20, 0, 20.999999),
    (3, "MS", "Mainstream", 29, 0, 29.999999),
    (4, "MS26", "Mainstream 2026", 30, 0, 30.999999),
    (5, "MS26C", "Mainstream 2026 Class", 31, 0, 30.999999),
    (6, "PL26", "Plus 2026", 40, 0, 40.999999),
    (7, "FREI", "Ohne Limit", 99, 0, None),
]


def test_bands_for():
    assert ps.bands_for(PROGRAMS, []) is None
    assert ps.bands_for(PROGRAMS, [7]) is None
    assert ps.bands_for(PROGRAMS, [1, 4, 5, 7]) == {10, 30}


def test_top_program():
    assert ps.top_program(PROGRAMS, []) == (None, "")
    assert ps.top_program(PROGRAMS, [1, 6, 4]) == (6, "PL26")
    assert ps.top_program(PROGRAMS, [7]) == (7, "FREI")
    assert ps.top_program(PROGRAMS, [7, 2]) == (2, "B2")


def test_program_by_code():
    assert ps.program_by_code(PROGRAMS, "MS")[5] == 29.999999
    assert ps.program_by_code(PROGRAMS, "XX") is None


def test_primary_program_skips_class_variant():
    assert ps.primary_program_by_band(PROGRAMS) == {10: 1, 20: 2, 29: 3, 30: 4, 40: 6}


def test_predecessor_bands_keeps_program_lines_apart():
    bands = [10, 20, 29, 30, 39, 40, 60]
    assert ps.predecessor_bands(bands, None) == []
    assert ps.predecessor_bands(bands, 39) == [10, 20, 29]
    assert ps.predecessor_bands(bands, 40) == [30]
    assert ps.predecessor_bands(bands, 60) == [30, 40]


def test_calls_in_bands_lowest_band_wins():
    calls = [("--MS--", None, 29.0), ("Dosado", 1, 10.1), ("Dosado", 1, 30.1),
             ("Recycle", 2, 30.5), ("Spin Chain Thru", 3, 40.2), ("X", 4, None)]
    assert ps.calls_in_bands(calls, None) == calls
    assert ps.calls_in_bands(calls, {30, 40}) == [
        ("Dosado", 1, 30.1), ("Recycle", 2, 30.5), ("Spin Chain Thru", 3, 40.2)]
    assert ps.calls_in_bands(calls, {10, 30})[0] == ("Dosado", 1, 10.1)


def test_label_by_band_takes_regular_program():
    assert ps.label_by_band(PROGRAMS) == {
        10: "Basic 1", 20: "Basic 2", 29: "Mainstream", 30: "Mainstream 2026",
        40: "Plus 2026"}


def test_call_program_label():
    # intern#176: niedrigstes gewaehltes Band der Figur, sonst niedrigstes
    # ueberhaupt; bei mehreren Figuren das hoechste dieser Baender.
    labels = ps.label_by_band(PROGRAMS)
    dosado = [10.0003, 30.0002]
    fold = [29.0062, 30.0048]
    peel = [40.0043]
    label = ps.call_program_label
    assert label([dosado], {10, 30}, labels) == "Basic 1"
    assert label([dosado], {30, 40}, labels) == "Mainstream 2026"
    assert label([fold], {30}, labels) == "Mainstream 2026"
    assert label([fold], None, labels) == "Mainstream"         # keine Wahl
    assert label([peel], {30}, labels) == "Plus 2026"          # ausserhalb der Wahl
    assert label([dosado, peel], {30, 40}, labels) == "Plus 2026"  # mehrere Figuren
    assert label([[None]], {30}, labels) == ""                 # Figur ohne Band
    assert label([], {30}, labels) == ""


# ---- parse_ids (INI-Wert 'sequences/dance_programs') ----------------------------

def test_parse_ids_empty_and_none():
    assert ps.parse_ids("") == []
    assert ps.parse_ids(None) == []


def test_parse_ids_keeps_order_and_ignores_blanks():
    assert ps.parse_ids(" 3, 1 ,2") == [3, 1, 2]


def test_parse_ids_skips_garbage():
    assert ps.parse_ids("1,x,,3") == [1, 3]
