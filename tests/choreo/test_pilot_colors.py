"""Pilot-Square-Daten in Square Flow (intern#249), Qt-freie Zuordnung."""
from caddy.choreo import pilot_colors as pc


def test_daten_haengen_am_taenzer_nicht_am_platz():
    data = pc.clean({(1, True): {"color": "#e74c3c", "name": "Anna\nB."},
                     (3, False): {"color": "#3498db", "name": ""},
                     (2, True): {"color": None, "name": "  "},
                     (4, False): {"color": None, "name": "Eva"}})
    assert data == {(1, True): {"color": "#e74c3c", "name": "Anna B."},
                    (3, False): {"color": "#3498db", "name": ""},
                    (4, False): {"color": None, "name": "Eva"}}
    # Engine liefert couple als Text
    assert pc.fill_for(data, {"couple": "1", "boy": True}) == "#e74c3c"
    assert pc.name_for(data, {"couple": "1", "boy": True}) == "Anna B."
    assert pc.fill_for(data, {"couple": "1", "boy": False}) is None   # Partnerin leer
    assert pc.fill_for(data, {"couple": "4", "boy": False}) is None   # Name ohne Farbe
    assert pc.name_for(data, {"couple": "4", "boy": False}) == "Eva"
    assert pc.fill_for({}, {"couple": "1", "boy": True}) is None
    assert pc.name_for(data, {"couple": "x", "boy": True}) == ""


def test_nummer_lesbar():
    assert pc.text_on("#f1c40f") == "#141414"    # hell -> dunkle Nummer
    assert pc.text_on("#34495e") == "#f5f5f5"    # dunkel -> helle Nummer
    assert pc.text_on("kaputt") == "#141414"
