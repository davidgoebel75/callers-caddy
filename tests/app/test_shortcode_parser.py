"""Shortcodes in Notizen: parsen und zurueck in Text (shortcode_parser)."""
import pytest

from shortcode_parser import (Shortcode, parse_shortcodes, shortcode_text,
                              song_shortcode_text)


@pytest.mark.parametrize("text, erwartet", [
    ("[sequence_view]", [("sequence_view", {})]),
    ('[load_song "Cotton-Eyed Joe"]', [("load_song", {"_value": "Cotton-Eyed Joe"})]),
    ("[load_song 'Single']", [("load_song", {"_value": "Single"})]),
    ("[sequence_view id=42]", [("sequence_view", {"id": 42})]),
    ('[sequence_view contains="Swing Thru" limit="MS"]',
     [("sequence_view", {"contains": "Swing Thru", "limit": "MS"})]),
    ("[x a='1' b=2]", [("x", {"a": "1", "b": 2})]),     # Zahl in Quotes bleibt Text
    ('[x id="7" id=8]', [("x", {"id": "7"})]),          # String vor Int
    ("[x id=42abc]", [("x", {})]),                      # keine reine Zahl
    ('[x "pos" id=4]', [("x", {"id": 4})]),             # Benannt schlaegt positional
    ("[_a1]", [("_a1", {})]),
])
def test_parse(text, erwartet):
    assert parse_shortcodes(text) == [Shortcode(a, p) for a, p in erwartet]


def test_parse_mehrere_in_reihenfolge_mit_fliesstext():
    text = 'Erst [a] dann\n[b id=1] und [c "x"] Ende.'
    assert [s.action_id for s in parse_shortcodes(text)] == ["a", "b", "c"]


@pytest.mark.parametrize("text", [
    "", "kein Code", "[1abc]", "[ leer]", "[-x]", "[offen", "offen]"])
def test_parse_nichts(text):
    assert parse_shortcodes(text) == []


@pytest.mark.parametrize("action, params, text", [
    ("a", {}, "[a]"),
    ("load_song", {"_value": "Joe"}, '[load_song "Joe"]'),
    ("v", {"id": 42}, "[v id=42]"),
    ("v", {"contains": "Swing Thru", "id": 3},
     '[v contains="Swing Thru" id=3]'),
])
def test_text(action, params, text):
    assert shortcode_text(action, params) == text


@pytest.mark.parametrize("action, params", [
    ("a", {}),
    ("load_song", {"_value": "Cotton-Eyed Joe"}),
    ("to_call", {"program": "Mainstream (2026)", "except": "Scoot Back, Hinge"}),
    ("v", {"contains": "Swing Thru", "limit": "MS", "id": 0}),
])
def test_rundweg(action, params):
    assert parse_shortcodes(shortcode_text(action, params)) == [
        Shortcode(action, params)]


@pytest.mark.parametrize("mode, text", [
    ("", '[load_song "Joe"]'),
    ("P", '[load_song title="Joe" mode="P"]'),
    ("S", '[load_song title="Joe" mode="S"]'),
])
def test_song_shortcode(mode, text):
    assert song_shortcode_text("Joe", mode) == text


def test_song_shortcode_ohne_mode_ist_positional():
    assert song_shortcode_text("Joe") == '[load_song "Joe"]'


def test_song_shortcode_mit_mode_wird_benannt_gelesen():
    sc, = parse_shortcodes(song_shortcode_text("Joe", "P"))
    assert sc.params == {"title": "Joe", "mode": "P"}
