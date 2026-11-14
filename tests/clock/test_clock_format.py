"""Uhr (intern#235): Anzeigetext und Takt ohne Qt."""
from caddy.clock.clock_format import format_clock, ms_until_change


def test_24h_ohne_sekunden():
    assert format_clock(9, 5, 30) == ("09:05", "")


def test_24h_mit_sekunden():
    assert format_clock(21, 0, 7, seconds=True) == ("21:00:07", "")


def test_12h_mitternacht_und_mittag():
    assert format_clock(0, 15, 0, twelve_hour=True) == ("12:15", "AM")
    assert format_clock(12, 15, 0, twelve_hour=True) == ("12:15", "PM")


def test_12h_nachmittag_mit_sekunden():
    assert format_clock(19, 45, 3, seconds=True, twelve_hour=True) == ("7:45:03", "PM")


def test_takt_mit_sekunden_bis_zur_naechsten_sekunde():
    assert ms_until_change(10, 300, seconds=True) == 720


def test_takt_ohne_sekunden_bis_zur_vollen_minute():
    assert ms_until_change(59, 900) == 120
    assert ms_until_change(0, 0) == 60020
