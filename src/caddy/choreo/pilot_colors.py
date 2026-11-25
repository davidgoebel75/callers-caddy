"""Pilot-Square-Daten in Square Flow (Phase 3, intern#249).

Qt-frei. Der Pilot Square haelt je Taenzer (Couple 1-4, Mann/Frau) Farbe und Name; er ist
die EINZIGE Ablage, Square Flow zeigt nur an. Die Engine fuehrt jeden Taenzer mit "couple"
und "boy" ueber alle Calls und Figuren mit, die Daten haengen also am Taenzer, nicht am
Platz. Ohne Pilot-Farbe bleibt die Standard-Paarfarbe; Form (Mann/Frau) und Nummer bleiben
als Bezug.

Datenform: {(Couple, Mann?): {"color": "#rrggbb" oder None, "name": str}}
"""

QT_FREE = True


def key(couple, boy):
    """Schluessel eines Taenzers: (Couple-Nummer, Mann?)."""
    try:
        return int(couple), bool(boy)
    except (TypeError, ValueError):
        return None


def one_line(text):
    """Name aus dem Pilot-Square-Feld einzeilig (Zeilen mit Leerzeichen verbunden)."""
    return " ".join(part.strip() for part in str(text or "").splitlines() if part.strip())


def clean(data):
    """Nur Taenzer mit Farbe oder Name und gueltigem Schluessel behalten."""
    out = {}
    for (couple, boy), entry in (data or {}).items():
        k = key(couple, boy)
        entry = entry or {}
        color = entry.get("color") or None
        name = one_line(entry.get("name"))
        if k is not None and (color or name):
            out[k] = {"color": str(color) if color else None, "name": name}
    return out


def _entry(data, dancer):
    if not data or not dancer:
        return {}
    return data.get(key(dancer.get("couple"), dancer.get("boy"))) or {}


def fill_for(data, dancer):
    """Pilot-Farbe fuer einen Engine-Taenzer (dict mit couple/boy), None = Standardfarbe."""
    return _entry(data, dancer).get("color")


def name_for(data, dancer):
    """Pilot-Name fuer einen Engine-Taenzer, "" = keiner."""
    return _entry(data, dancer).get("name") or ""


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
