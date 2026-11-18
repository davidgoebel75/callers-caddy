"""Pilot-Square-Farben in Square Flow (Phase 3, intern#249).

Qt-frei. Der Pilot Square liefert je Taenzer (Couple 1-4, Mann/Frau) eine Farbe oder
nichts. Die Engine fuehrt jeden Taenzer mit "couple" und "boy" ueber alle Calls und
Figuren mit, die Farbe haengt also am Taenzer, nicht am Platz. Wer keine Pilot-Farbe hat,
behaelt die Standard-Paarfarbe; Form (Mann/Frau) und Nummer bleiben als Bezug.
"""

QT_FREE = True


def key(couple, boy):
    """Schluessel einer Pilot-Farbe: (Couple-Nummer, Mann?)."""
    try:
        return int(couple), bool(boy)
    except (TypeError, ValueError):
        return None


def clean(colors):
    """Nur gesetzte Farben mit gueltigem Schluessel behalten."""
    out = {}
    for (couple, boy), color in (colors or {}).items():
        k = key(couple, boy)
        if k is not None and color:
            out[k] = str(color)
    return out


def fill_for(colors, dancer):
    """Pilot-Farbe fuer einen Engine-Taenzer (dict mit couple/boy), None = Standardfarbe."""
    if not colors or not dancer:
        return None
    return colors.get(key(dancer.get("couple"), dancer.get("boy")))


def text_on(hex_color):
    """Schwarz oder Weiss fuer die Nummer auf hex_color ("#rrggbb")."""
    h = str(hex_color or "").lstrip("#")
    if len(h) != 6:
        return "#141414"
    try:
        r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return "#141414"
    return "#141414" if 0.299 * r + 0.587 * g + 0.114 * b > 150 else "#f5f5f5"
