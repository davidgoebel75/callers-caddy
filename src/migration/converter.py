"""Konvertierungslogik fuer Callers Caddy 1.0 / SqView → 2.0 Migration.

Wandelt die Rohdaten aus verschiedenen Quellsystemen in das neue SQLite-Format um.
"""

import os
import re


# Songtype → (is_pattern, is_singing)
_SONGTYPE_MAP = {
    "HD":    (True, False),   # Hoedown = Pattern
    "SD":    (False, True),   # Singing Call
    "HDSD":  (True, True),    # Beides
    "SD,HD": (True, True),    # Beides (alternatives Format)
    "X":     (False, False),  # Sonstige
}


class Converter:
    """Statische Konvertierungsmethoden fuer die Migration."""

    @staticmethod
    def convert_speed(speed) -> float:
        """Alte Speed-Korrektur → neuer Tempo-Faktor.

        Alt: Speed 0 = 100%, Speed 5 = 105%, Speed -3 = 97%
        Neu: standard_tempo 1.0 = 100%, 1.05 = 105%, 0.97 = 97%
        """
        try:
            s = float(speed) if speed is not None else 0.0
        except (ValueError, TypeError):
            return 1.0
        return 1.0 + (s / 100.0)

    @staticmethod
    def convert_pitch(pitch) -> float:
        """Pitch: identisch (Halbtoene)."""
        try:
            return float(pitch) if pitch is not None else 0.0
        except (ValueError, TypeError):
            return 0.0

    @staticmethod
    def convert_volume(volume) -> float:
        """Alte Lautstaerke (0-100) → neuer Faktor (0.0-1.0).

        Alt: Volume 100 = normal
        Neu: volume 1.0 = normal (max)
        """
        try:
            v = int(volume) if volume is not None else 100
        except (ValueError, TypeError):
            return 1.0
        return min(1.0, max(0.0, v / 100.0))

    @staticmethod
    def convert_loop_ms(ms_str) -> float:
        """Loop-Position als ms-String → Sekunden.

        Alt: " 18120" (String mit Leerzeichen, Millisekunden)
        Neu: 18.12 (float, Sekunden)
        """
        if not ms_str:
            return 0.0
        try:
            ms = int(str(ms_str).strip())
            return ms / 1000.0
        except (ValueError, TypeError):
            return 0.0

    @staticmethod
    def convert_songtype(songtype) -> tuple[bool, bool]:
        """Songtype-String → (is_pattern, is_singing).

        HD = Pattern, SD = Singing Call, HDSD/SD,HD = Beides.
        """
        st = str(songtype).strip().upper() if songtype else ""
        return _SONGTYPE_MAP.get(st, (False, False))

    @staticmethod
    def extract_rating(rating_str) -> int:
        """Rating-String → Integer (0-9).

        Beispiele: "6" → 6, "6 OK" → 6, "" → 0, None → 0, "5 OK" → 5
        """
        if not rating_str:
            return 0
        s = str(rating_str).strip()
        if not s:
            return 0
        # Erste Ziffer(n) extrahieren
        match = re.match(r"(\d+)", s)
        if match:
            return min(9, int(match.group(1)))
        return 0

    @staticmethod
    def convert_bpm(bpm) -> float:
        """BPM: direkt uebernehmen."""
        try:
            return float(bpm) if bpm is not None else 0.0
        except (ValueError, TypeError):
            return 0.0

    # =================================================================
    # SqView-spezifische Konvertierungen
    # =================================================================

    @staticmethod
    def sqview_parse_filename(fullpath: str) -> tuple[str, str, str]:
        """Extrahiert Dateiname, Titel und Label aus SqView-Pfad.

        SqView-Namensformat: "Title-Label.mp3" (z.B. "A Friend Like Me-DGR014+.mp3")
        Returns: (filename, title, label)
        """
        filename = os.path.basename(fullpath)
        name_no_ext = filename.rsplit(".", 1)[0] if "." in filename else filename

        # Versuche "Titel-Label" zu trennen (letzter Bindestrich)
        if "-" in name_no_ext:
            parts = name_no_ext.rsplit("-", 1)
            title = parts[0].strip()
            label = parts[1].strip()
        else:
            title = name_no_ext.strip()
            label = ""

        return filename, title, label

    @staticmethod
    def sqview_convert_speed(speed, pitch_semitones) -> float:
        """SqView Speed (Sample-Rate) → Tempo-Faktor.

        SqView: speed = Sample-Rate (44100 = normal). Aenderung der Sample-Rate
        aendert Tempo UND Pitch zusammen. Da CC2 Tempo und Pitch getrennt hat,
        ignorieren wir Speed-basierte Tempo-Aenderungen (selten genutzt).
        """
        return 1.0

    @staticmethod
    def sqview_convert_pitch(pitch) -> float:
        """SqView Pitch → CC2 Pitch (Halbtoene, direkt)."""
        try:
            return float(pitch) if pitch else 0.0
        except (ValueError, TypeError):
            return 0.0

    @classmethod
    def convert_sqview_song(cls, raw: dict, marriages: dict) -> dict:
        """Konvertiert einen SqView music-Dict → Callers-Caddy-2.0-Song-Dict."""
        fullpath = str(raw.get("path", "") or "").strip()
        filename, title, label = cls.sqview_parse_filename(fullpath)

        volume = cls.convert_volume(raw.get("volume"))
        pitch = cls.sqview_convert_pitch(raw.get("pitch"))
        loop_in = float(raw.get("loopset", 0) or 0)
        loop_out = float(raw.get("loopstop", 0) or 0)
        quality = int(raw.get("rate", 0) or 0)

        # Lyrics: aus marry-Tabelle (Vollpfad → nur Dateiname)
        lyrics_file = ""
        marry_path = marriages.get(fullpath.lower(), "")
        if marry_path:
            lyrics_file = os.path.basename(marry_path)

        return {
            "filename": filename,
            "title": title,
            "artist": "",
            "label": label,
            "quality": min(9, max(0, quality)),
            "base_bpm": 0.0,
            "standard_tempo": 1.0,
            "pitch": pitch,
            "volume": volume,
            "loop_in": loop_in,
            "loop_out": loop_out,
            "lyrics_file": lyrics_file,
            "is_pattern": 1,
            "is_singing": 1,
        }

    # =================================================================
    # CC 1.0 (Access) Konvertierungen
    # =================================================================

    @classmethod
    def convert_song(cls, raw: dict) -> dict:
        """Konvertiert einen MDB-Song-Dict → Callers-Caddy-2.0-Song-Dict."""
        is_pattern, is_singing = cls.convert_songtype(raw.get("Songtype"))

        rating_p = cls.extract_rating(raw.get("Rating_Pattern"))
        rating_s = cls.extract_rating(raw.get("Rating_Singing"))
        quality = max(rating_p, rating_s)

        filename = str(raw.get("URL_Music", "") or "").strip()
        title = str(raw.get("Name", "") or "").strip()
        if not title and filename:
            # Fallback: Dateiname ohne Extension
            title = filename.rsplit(".", 1)[0] if "." in filename else filename

        return {
            "filename": filename,
            "title": title,
            "artist": str(raw.get("Artist", "") or "").strip(),
            "label": str(raw.get("Label", "") or "").strip(),
            "quality": quality,
            "base_bpm": cls.convert_bpm(raw.get("BPM")),
            "standard_tempo": cls.convert_speed(raw.get("Speed")),
            "pitch": cls.convert_pitch(raw.get("Pitch")),
            "volume": cls.convert_volume(raw.get("Volume")),
            "loop_in": cls.convert_loop_ms(raw.get("Loop_Start")),
            "loop_out": cls.convert_loop_ms(raw.get("Loop_End")),
            "lyrics_file": str(raw.get("URL_Lyric", "") or "").strip(),
            "is_pattern": 1 if is_pattern else 0,
            "is_singing": 1 if is_singing else 0,
            "genre": str(raw.get("Genre", "") or "").strip(),
            # BL-125: Vocal-Version aus CC1 (wird vor DB-Insert herausgepoppt)
            "url_vocal": str(raw.get("URL_Vocal", "") or "").strip(),
        }
