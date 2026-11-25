"""Uhr: Anzeigetext und naechster Takt, ohne Qt (intern#235).

Reine Funktionen: Das Widget liest die Systemzeit, laesst hier den Text bauen
und plant den naechsten Neuzeichnen-Zeitpunkt.
"""

QT_FREE = True


def format_clock(hour, minute, second, *, seconds=False, twelve_hour=False):
    """(Zeittext, Zusatz) fuer die Anzeige.

    24 h: "09:05" bzw. "09:05:30", Zusatz leer.
    12 h: "9:05" bzw. "9:05:30", Zusatz "AM"/"PM" (0 Uhr = 12 AM, 12 Uhr = 12 PM).
    """
    if twelve_hour:
        suffix = "AM" if hour < 12 else "PM"
        text = f"{hour % 12 or 12}:{minute:02d}"
    else:
        suffix = ""
        text = f"{hour:02d}:{minute:02d}"
    if seconds:
        text += f":{second:02d}"
    return text, suffix


def ms_until_change(second, msec, *, seconds=False):
    """Millisekunden bis zum naechsten Wechsel des Anzeigetextes.

    Ohne Sekunden wechselt der Text zur vollen Minute, mit Sekunden zur vollen
    Sekunde. Ein kleiner Vorlauf (+20 ms) stellt sicher, dass der Timer nach
    dem Wechsel feuert und nicht knapp davor.
    """
    to_next_second = 1000 - msec
    if seconds:
        return to_next_second + 20
    return (59 - second) * 1000 + to_next_second + 20
