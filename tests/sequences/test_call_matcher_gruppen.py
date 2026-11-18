"""Volltreffer im CallMatcher: Gruppe vorn im Call-Text (intern#89).

Eine Figur, die eine Gruppe fest im Namen traegt ("All Eight Circulate",
"Centers In"), darf nicht den Schluessel des blanken Calls belegen. Die
(Named Dancers)-Figur steht fuer "beliebige Gruppe" und faengt die Call-Texte
mit Rolle vorn. Ein Call-Text, der eine Figur samt Gruppe woertlich nennt,
trifft genau diese Figur.

Die Figuren in Teaching-Order-Reihenfolge wie aus get_teaching_order_calls():
(entity_id, Name, teaching_order, Programm).
"""
import pytest

from sequence_mapper import CallMatcher

FIGUREN = [
    ("call_named_dancers_circulate", "(Named Dancers) Circulate", 10.002101, "MS"),
    ("call_couples_circulate", "Couples Circulate", 10.002102, "MS"),
    ("call_all_eight_circulate", "All Eight Circulate", 10.002103, "MS"),
    ("call_centers_in", "Centers In", 10.003, "MS"),
    ("call_ends_bend", "Ends Bend", 10.004, "MS"),
    ("call_right_and_left_thru", "Right and Left Thru", 10.005, "MS"),
    ("call_recycle", "Recycle", 10.006, "MS"),
    ("call_spin_the_top", "Spin the Top", 10.007, "MS"),
    ("call_all_8_spin_the_top", "All 8 Spin the Top", 30.001, "Plus"),
    ("call_all_8_recycle", "All 8 Recycle", 30.002, "Plus"),
    ("call_swing", "Swing (your Partner)", 10.008, "Basic"),
    ("call_track_2", "Track 2", 30.003, "Plus"),
    ("call_track", "Track", 40.001, "A2"),
    ("call_swing_a2", "Swing", 40.002, "A2"),
    ("call_ladies_in_men_sashay", "Ladies In Men Sashay", 30.004, "Plus"),
]


@pytest.fixture(scope="module")
def matcher():
    return CallMatcher(FIGUREN)


@pytest.mark.parametrize("text, figur", [
    ("Circulate", "call_named_dancers_circulate"),
    ("Heads Circulate", "call_named_dancers_circulate"),
    ("Ends Circulate", "call_named_dancers_circulate"),
    ("Circulate (again)", "call_named_dancers_circulate"),
    ("All 8 Circulate", "call_all_eight_circulate"),
    ("All Eight Circulate", "call_all_eight_circulate"),
    ("All 8 Spin The Top", "call_all_8_spin_the_top"),
    ("All Eight Recycle", "call_all_8_recycle"),
    ("All 8 Recycle (odd)", "call_all_8_recycle"),
    ("Recycle", "call_recycle"),
    ("Centers In", "call_centers_in"),
    ("Heads Centers In", "call_centers_in"),
    ("Ladies In Men Sashay", "call_ladies_in_men_sashay"),
    ("Heads Ladies In Men Sashay", "call_ladies_in_men_sashay"),
    ("Ends Bend", "call_ends_bend"),
    ("Right & Left Thru", "call_right_and_left_thru"),
    ("Heads Right and Left Thru", "call_right_and_left_thru"),
    # Ohne Gruppe im Namen bleibt es beim Bisherigen: erster in Teaching-Order
    ("Swing", "call_swing"),
    ("Swing (The One You Face)", "call_swing"),
    ("Track 2", "call_track_2"),
    ("Track 3", "call_track_2"),
])
def test_volltreffer(matcher, text, figur):
    assert matcher.exact_entity(text) == figur
    assert matcher.suggest(text) == (1.0, figur)


@pytest.mark.parametrize("text", ["Heads In", "Centers Bend", "In"])
def test_rolle_im_figurennamen_ist_kein_volltreffer_fuer_andere_gruppen(matcher, text):
    assert matcher.exact_entity(text) is None
    assert matcher.suggest(text)[0] < 1.0
