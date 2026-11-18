"""Pilot-Square-Farben in Square Flow (intern#249), Qt-freie Zuordnung."""
from caddy.choreo import pilot_colors as pc


def test_farbe_haengt_am_taenzer_nicht_am_platz():
    colors = pc.clean({(1, True): "#e74c3c", (3, False): "#3498db", (2, True): None})
    assert colors == {(1, True): "#e74c3c", (3, False): "#3498db"}
    # Engine liefert couple als Text
    assert pc.fill_for(colors, {"couple": "1", "boy": True}) == "#e74c3c"
    assert pc.fill_for(colors, {"couple": "1", "boy": False}) is None   # Partnerin ohne Farbe
    assert pc.fill_for(colors, {"couple": "3", "boy": False}) == "#3498db"
    assert pc.fill_for({}, {"couple": "1", "boy": True}) is None
    assert pc.fill_for(colors, {"couple": "x", "boy": True}) is None


def test_nummer_lesbar():
    assert pc.text_on("#f1c40f") == "#141414"    # hell -> dunkle Nummer
    assert pc.text_on("#34495e") == "#f5f5f5"    # dunkel -> helle Nummer
    assert pc.text_on("kaputt") == "#141414"
