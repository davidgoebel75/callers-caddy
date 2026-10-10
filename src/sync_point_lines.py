"""SyncPoint und Textzeile (intern#171).

Qt-frei. Ein SyncPoint speichert eine Zeichenposition im Lyrics-Text. Zu
welcher Zeile er gehoert, entscheidet die Textzeile (bis zum naechsten
Zeilenumbruch im Text), nicht die sichtbare Bildschirmzeile: Die haengt von
Fensterbreite und Schriftgroesse ab. Ein Punkt kann mitten in der Zeile
stehen, etwa nachdem die Lyrics-Datei ausserhalb der App geaendert wurde.
"""


def line_span(text: str, pos: int) -> tuple:
    """(Anfang, Ende) der Textzeile, in der pos liegt. Ende ist die Position
    des Zeilenumbruchs bzw. die Textlaenge; pos genau auf dem Umbruch gehoert
    zur Zeile davor."""
    pos = max(0, min(int(pos), len(text)))
    start = text.rfind("\n", 0, pos) + 1
    end = text.find("\n", pos)
    if end < 0:
        end = len(text)
    return start, end


def indices_in_span(anchors, start: int, end: int) -> list:
    """Indizes der Anker [sekunde, position], deren Position in der Zeile
    start..end liegt (Ende eingeschlossen: ein Punkt am Zeilenende)."""
    return [i for i, (_sec, p) in enumerate(anchors)
            if int(start) <= int(p) <= int(end)]
