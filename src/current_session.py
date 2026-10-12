"""Aktuelle Sitzung (intern#142): was gerade im Programm gilt, an einer Stelle.

Widgets melden sich auf die Signale an und lesen beim Erzeugen den aktuellen
Wert, statt dass main.py jeden Wechsel von Hand weiterreicht. Schrittweise:
zuerst die Lokation, Song und Tanzprogramm-Wahl folgen.
"""
from PySide6.QtCore import QObject, Signal


class CurrentSession(QObject):
    # Location oder None. Feuert bei jedem set_location, auch bei derselben
    # Lokation: eine im Dialog geaenderte Lokation soll sofort wirken.
    location_changed = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._location = None

    @property
    def location(self):
        # Nur lesend: Schreiben geht ueber set_location, sonst fehlt das Signal
        return self._location

    @property
    def location_id(self):
        return self._location.id if self._location else None

    def set_location(self, location):
        self._location = location
        self.location_changed.emit(location)
