"""Audio-Favoriten 1 und 2 (intern#173). Qt-frei.

Favorit 1 ist der Hauptausgang (INI audio/primary_device), Favorit 2 der
Vorhoer-Kanal (audio/secondary_device). Der Toggle-Knopf im Footer schaltet die
Hauptausgabe zwischen beiden um. Ein leerer INI-Wert steht fuer den
System-Standard (Geraet None).
"""

PRIMARY_KEY = "audio/primary_device"
SECONDARY_KEY = "audio/secondary_device"

UNREADABLE = object()   # INI-Wert ist weder leer noch eine Zahl


def parse_device(raw):
    """INI-Wert -> Geraete-Index, None fuer System-Standard, UNREADABLE sonst."""
    text = "" if raw is None else str(raw).strip()
    if not text:
        return None
    try:
        return int(text)
    except ValueError:
        return UNREADABLE


def favorite_devices(primary_raw, secondary_raw) -> dict:
    """{1: Geraet von Favorit 1, 2: Geraet von Favorit 2} aus den INI-Werten."""
    return {1: parse_device(primary_raw), 2: parse_device(secondary_raw)}


def other(favorite: int) -> int:
    """Der jeweils andere Favorit."""
    return 2 if favorite == 1 else 1


def marks(devices: dict) -> dict:
    """Kennzeichnung fuer die Geraeteliste: {Geraet: "1" | "2" | "1+2"}.
    Unlesbare Favoriten kennzeichnen nichts."""
    out = {}
    for fav in (1, 2):
        dev = devices.get(fav, UNREADABLE)
        if dev is UNREADABLE:
            continue
        out[dev] = f"{out[dev]}+{fav}" if dev in out else str(fav)
    return out
