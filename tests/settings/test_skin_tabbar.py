"""Reiterleisten der gestapelten Docks: kein weisser Streifen neben den Reitern.

Ohne eigene Regel fuer QTabBar zeichnet Qt neben den Reitern die Grundleiste in
der Windows-Palette (weiss), auch in dunklen Skins. Jeder Skin macht die Leiste
darum durchsichtig; sichtbar ist dann der Fensterhintergrund.
"""
import os
import re

import pytest

SRC_SKINS = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                         "src", "skins")
SKINS = sorted(d for d in os.listdir(SRC_SKINS)
               if os.path.isfile(os.path.join(SRC_SKINS, d, "skin.qss")))
assert SKINS, f"keine Skins unter {SRC_SKINS}"   # sonst liefe der Test still mit 0 Faellen


@pytest.mark.parametrize("skin", SKINS)
def test_reiterleiste_durchsichtig(skin):
    with open(os.path.join(SRC_SKINS, skin, "skin.qss"), encoding="utf-8") as f:
        qss = f.read()
    m = re.search(r"(?m)^QTabBar\s*\{([^}]*)\}", qss)
    assert m, f"{skin}: keine Regel fuer QTabBar"
    assert re.search(r"background(-color)?\s*:\s*transparent", m.group(1)), skin
