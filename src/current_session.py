"""Aktuelle Sitzung (intern#142): was gerade im Programm gilt, an einer Stelle.

Widgets melden sich auf die Signale an und lesen beim Erzeugen den aktuellen
Wert, statt dass main.py jeden Wechsel von Hand weiterreicht. Schrittweise:
Lokation, aktueller Song (der geladene Song des Players) und Tanzprogramm-Wahl
liegen hier. Das Song-Daten-Dock zeigt ein eigenes Objekt und kann
vom geladenen Song abweichen.
"""
from PySide6.QtCore import QObject, Signal


class CurrentSession(QObject):
    # Location oder None. Feuert bei jedem set_location, auch bei derselben
    # Lokation: eine im Dialog geaenderte Lokation soll sofort wirken.
    location_changed = Signal(object)
    # Song oder None. Feuert bei jedem set_song, auch beim selben Song (z. B.
    # frisch aus der DB): Listener muessen idempotent sein. Nur das Setzen
    # meldet; Felder am Song aendert man wie bisher am Objekt selbst.
    song_changed = Signal(object)
    # Liste der gewaehlten Tanzprogramm-IDs (list[int]). Feuert bei jedem
    # set_program_ids, auch bei gleicher Wahl. Die Sitzung kennt weder INI noch
    # DB noch die Regel (program_selection): sie haelt nur die Wahl.
    program_ids_changed = Signal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._location = None
        self._song = None
        self._program_ids = []

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

    @property
    def song(self):
        return self._song

    @property
    def song_id(self):
        return self._song.id if self._song else None

    def set_song(self, song):
        self._song = song
        self.song_changed.emit(song)

    @property
    def program_ids(self):
        # Kopie: Aendern der Liste von aussen aendert die Sitzung nicht
        return list(self._program_ids)

    def set_program_ids(self, ids):
        # Unveraendert uebernehmen: nicht sortieren, nicht entdoppeln
        self._program_ids = list(ids or [])
        self.program_ids_changed.emit(list(self._program_ids))
