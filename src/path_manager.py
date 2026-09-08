"""
Portable Pfadverwaltung fuer Callers Caddy
============================================
Zentrale Stelle fuer alle Verzeichnis-Pfade.

Design-Prinzipien:
  - ALLE Pfade relativ zum App-Verzeichnis (APP_DIR)
  - In der INI werden NUR relative Pfade gespeichert
  - Beim Laden werden relative Pfade aufgeloest gegen APP_DIR
  - Ordner werden bei Bedarf automatisch erstellt

Default-Ordnerstruktur (nach Installation):
  <portable_root>/
    app/                   APP_DIR (enthaelt main.py, callers_caddy.db, INI)
    music/                 MUSIC_DIR_1 (Haupt-Musikbibliothek)
    neu/                   IMPORT_DIR (neue, noch nicht importierte Songs)
    lyrics/                LYRICS_DIR (Lyrics-Textdateien)

Bis zu 4 Musik-Verzeichnisse konfigurierbar (music_dir_1..4).
find_song_file() sucht in Reihenfolge Slot 1→2→3→4.

Warum relativ?
  - Ordner kann komplett verschoben/kopiert werden
  - USB-Stick: verschiedene Laufwerksbuchstaben
  - Kein Anpassen noetig nach dem Kopieren
"""

import os
from PySide6.QtCore import QSettings


# Anzahl unterstuetzter Musik-Pfad-Slots
MUSIC_DIR_SLOTS = 4

# Relative Default-Pfade (von APP_DIR aus gesehen)
_DEFAULTS = {
    "music_dir_1": "music",
    "import_dir":  "neu",
    "lyrics_dir":  "lyrics",
    "playlist_dir": "playlists",
}

# INI-Keys
_INI_MUSIC_KEY = "paths/music_dir_{slot}"   # slot = 1..4
_INI_KEYS = {
    "import_dir":   "paths/import_dir",
    "lyrics_dir":   "paths/lyrics_dir",
    "playlist_dir": "paths/playlist_dir",
}


# ---- Relative-Pfad-Helfer (BL-147) ----------------------------------------
# Kanonische DB-Speicherform fuer relative Datei-Pfade ist IMMER POSIX ('/').
# Grund: get_by_filename() / update_filename() vergleichen exakte Strings —
# gemischte Separatoren (Sub\song.mp3 vs. Sub/song.mp3) wuerden Dedup und den
# UNIQUE-Constraint brechen.

def _to_posix(rel: str) -> str:
    """Normalisiert einen relativen Pfad auf POSIX-Forward-Slashes (DB-Form)."""
    return rel.replace("\\", "/")


def _from_posix(rel: str) -> str:
    """Wandelt kanonisch gespeicherte '/'-Pfade in OS-native Separatoren zurueck."""
    return rel.replace("/", os.sep) if rel else rel


def _is_within(path: str, base: str) -> bool:
    """True, wenn path innerhalb von base liegt.

    Sichere Pruefung statt str.startswith() — vermeidet den Bug, dass
    C:\\music2 faelschlich als unter C:\\music liegend gilt. Faengt auch
    Cross-Drive-Faelle ab (os.path.relpath wirft dort ValueError).
    """
    try:
        rel = os.path.relpath(path, base)
    except ValueError:
        return False  # anderes Laufwerk (Windows)
    return rel != os.pardir \
        and not rel.startswith(os.pardir + os.sep) \
        and not os.path.isabs(rel)


class PathManager:
    """Zentrale Pfadverwaltung — gibt nur absolute, aufgeloeste Pfade raus.

    Intern werden Pfade relativ zu APP_DIR gespeichert (in der INI).
    Nach aussen liefert der PathManager immer absolute Pfade.

    Musik-Slots 1–4:
      - Slot 1 ist der eigene Callers-Caddy-Musikordner (Pflicht, Default: music/).
      - Slots 2–4 sind optionale externe Pfade (leer = nicht genutzt).
    """

    def __init__(self, settings: QSettings):
        """
        Args:
            settings: QSettings-Objekt (INI-basiert, liegt in APP_DIR)
        """
        self._settings = settings
        self._app_dir = os.path.dirname(os.path.abspath(settings.fileName()))
        print(f"[PathManager] APP_DIR = {self._app_dir}")
        self._migrate()

    # ---- Migration ----

    def _migrate(self):
        """Migriert alte INI-Schluessel auf das neue Multi-Pfad-Format.

        Alt: paths/music_dir
        Neu: paths/music_dir_1 .. paths/music_dir_4
        """
        old_key = "paths/music_dir"
        new_key = _INI_MUSIC_KEY.format(slot=1)
        if self._settings.contains(old_key) and not self._settings.contains(new_key):
            old_value = self._settings.value(old_key)
            self._settings.setValue(new_key, old_value)
            self._settings.remove(old_key)
            print(f"[PathManager] Migration: {old_key} → {new_key} = {old_value}")

    # ---- App-Verzeichnis ----

    @property
    def app_dir(self) -> str:
        """Absoluter Pfad zum Anwendungsverzeichnis (enthaelt main.py, DB, INI)."""
        return self._app_dir

    @property
    def db_path(self) -> str:
        """Absoluter Pfad zur Song-Datenbank."""
        return os.path.join(self._app_dir, "callers_caddy.db")

    @property
    def ini_path(self) -> str:
        """Absoluter Pfad zur INI-Datei."""
        return os.path.abspath(self._settings.fileName())

    # ---- Musik-Verzeichnisse (Multi-Slot) ----

    @property
    def music_dir(self) -> str:
        """Absoluter Pfad zu Musik-Slot 1 (Haupt-Musikordner, Pflicht)."""
        return self._resolve_music_slot(1)

    @property
    def music_dirs(self) -> list:
        """Liste aller konfigurierten Musik-Pfade (Slot 1–4, nur nicht-leere).

        Reihenfolge entspricht der Suchprioritat: Slot 1 zuerst.
        """
        result = []
        for slot in range(1, MUSIC_DIR_SLOTS + 1):
            path = self._resolve_music_slot(slot)
            if path:
                result.append(path)
        return result

    def get_music_dir_raw(self, slot: int) -> str:
        """Gibt den gespeicherten Rohwert eines Slots zurueck (fuer UI-Anzeige).

        Returns den absoluten aufgeloesten Pfad, oder '' wenn Slot leer/nicht konfiguriert.
        """
        if slot == 1:
            return self._resolve_music_slot(1)  # Slot 1 hat immer einen Wert (Default)
        ini_key = _INI_MUSIC_KEY.format(slot=slot)
        raw = self._settings.value(ini_key, "")
        if not raw:
            return ""
        return os.path.normpath(os.path.join(self._app_dir, raw))

    def set_music_dir(self, absolute_path: str, slot: int = 1):
        """Setzt einen Musik-Pfad-Slot (wird relativ gespeichert wenn moeglich).

        Args:
            absolute_path: Absoluter Pfad zum Musik-Ordner, oder '' zum Leeren.
            slot: 1–4
        """
        ini_key = _INI_MUSIC_KEY.format(slot=slot)
        if not absolute_path:
            if slot > 1:
                self._settings.setValue(ini_key, "")
                print(f"[PathManager] music_dir_{slot} geleert")
            return
        self._store_path(ini_key, absolute_path, f"music_dir_{slot}")

    def find_free_music_slot(self) -> int:
        """Gibt den ersten freien Musik-Slot (2–4) zurueck, oder 0 wenn keiner frei.

        Slot 1 wird nicht als "frei" betrachtet (Pflichtfeld).
        """
        for slot in range(2, MUSIC_DIR_SLOTS + 1):
            ini_key = _INI_MUSIC_KEY.format(slot=slot)
            raw = self._settings.value(ini_key, "")
            if not raw:
                return slot
        return 0

    def has_path_in_music_dirs(self, absolute_path: str) -> bool:
        """Prueft ob ein Pfad bereits als Musik-Slot eingetragen ist."""
        norm = os.path.normpath(absolute_path)
        for slot in range(1, MUSIC_DIR_SLOTS + 1):
            existing = self._resolve_music_slot(slot)
            if existing and os.path.normpath(existing) == norm:
                return True
        return False

    # ---- Song-Datei suchen ----

    def find_song_file(self, filename: str) -> str:
        """Sucht eine Song-Datei in allen konfigurierten Musik-Verzeichnissen.

        Sucht in Reihenfolge Slot 1 → Slot 2 → Slot 3 → Slot 4.
        Gibt den ersten gefundenen absoluten Pfad zurueck, oder None.

        Args:
            filename: Dateiname ODER relativer Unterpfad, wie in der DB
                gespeichert. Relative Pfade werden kanonisch mit '/' gespeichert
                (BL-147) und hier auf OS-native Separatoren zurueckgewandelt.
        """
        name = _from_posix(filename)
        for music_dir in self.music_dirs:
            candidate = os.path.join(music_dir, name)
            if os.path.isfile(candidate):
                return candidate
        return None

    def find_lyric_file(self, filename: str) -> str:
        """Sucht eine Lyrik-Datei im konfigurierten Lyrics-Verzeichnis.

        Gibt den absoluten Pfad zurueck, oder None wenn nicht gefunden.

        Args:
            filename: Dateiname ODER relativer Unterpfad (kanonisch mit '/').
        """
        candidate = os.path.join(self.lyrics_dir, _from_posix(filename))
        if os.path.isfile(candidate):
            return candidate
        return None

    # ---- Absolute Pfade in relative DB-Speicherform wandeln (BL-147) ----

    def to_relative_filename(self, absolute_path: str) -> str:
        """Wandelt einen absoluten Songpfad in die kanonische DB-Speicherform.

        Probiert die Musik-Slots 1→4 in Reihenfolge (First come first serve):
        Liegt die Datei unter einem Slot, wird der relative Pfad zu DIESEM Slot
        zurueckgegeben (POSIX-normalisiert, '/'). Andernfalls nur der Basename.

        Die Slot-Reihenfolge ist identisch zu find_song_file() — ein so gebildeter
        relativer Pfad loest garantiert wieder gegen denselben Slot auf, auch wenn
        sich Wurzeln ueberlappen (z.B. Slot1=C:\\, Slot2=C:\\music).
        """
        fp = os.path.normpath(absolute_path)
        for music_dir in self.music_dirs:
            base = os.path.normpath(music_dir)
            if _is_within(fp, base):
                return _to_posix(os.path.relpath(fp, base))
        return os.path.basename(fp)

    def to_relative_lyric_filename(self, absolute_path: str) -> str:
        """Wie to_relative_filename(), aber gegen das Lyrics-Verzeichnis."""
        fp = os.path.normpath(absolute_path)
        base = os.path.normpath(self.lyrics_dir)
        if _is_within(fp, base):
            return _to_posix(os.path.relpath(fp, base))
        return os.path.basename(fp)

    # ---- Andere konfigurierbare Verzeichnisse ----

    @property
    def import_dir(self) -> str:
        """Absoluter Pfad zum Import-Verzeichnis ('neu/')."""
        return self._resolve("import_dir")

    @property
    def lyrics_dir(self) -> str:
        """Absoluter Pfad zum Lyrics-Verzeichnis."""
        return self._resolve("lyrics_dir")

    @property
    def playlist_dir(self) -> str:
        """Absoluter Pfad zum Playlist-Verzeichnis."""
        return self._resolve("playlist_dir")

    @property
    def loop_presets_dir(self) -> str:
        """Absoluter Pfad zum Loop-Presets-Verzeichnis (loop_presets/)."""
        return os.path.normpath(os.path.join(self._app_dir, "loop_presets"))

    @property
    def notes_dir(self) -> str:
        """Absoluter Pfad zum Notizen-Export-Verzeichnis (notes/)."""
        return os.path.normpath(os.path.join(self._app_dir, "notes"))

    def set_import_dir(self, absolute_path: str):
        """Setzt das Import-Verzeichnis."""
        self._store_path(_INI_KEYS["import_dir"], absolute_path, "import_dir")

    def set_lyrics_dir(self, absolute_path: str):
        """Setzt das Lyrics-Verzeichnis."""
        self._store_path(_INI_KEYS["lyrics_dir"], absolute_path, "lyrics_dir")

    def set_playlist_dir(self, absolute_path: str):
        """Setzt das Playlist-Verzeichnis."""
        self._store_path(_INI_KEYS["playlist_dir"], absolute_path, "playlist_dir")

    # ---- Verzeichnisse erstellen ----

    def ensure_directories(self):
        """Erstellt Pflicht-Verzeichnisse, falls sie nicht existieren."""
        for dir_path in [self.music_dir, self.import_dir, self.lyrics_dir,
                         self.playlist_dir, self.loop_presets_dir, self.notes_dir]:
            if not os.path.exists(dir_path):
                os.makedirs(dir_path, exist_ok=True)
                print(f"[PathManager] Verzeichnis erstellt: {dir_path}")

    # ---- Debug / Info ----

    def get_info(self) -> dict:
        """Gibt alle Pfade als Dictionary zurueck (fuer Debug/UI)."""
        info = {
            "app_dir":              self.app_dir,
            "db_path":              self.db_path,
            "ini_path":             self.ini_path,
            "import_dir":           self.import_dir,
            "lyrics_dir":           self.lyrics_dir,
            "playlist_dir":         self.playlist_dir,
            "import_dir_exists":    os.path.isdir(self.import_dir),
            "lyrics_dir_exists":    os.path.isdir(self.lyrics_dir),
            "playlist_dir_exists":  os.path.isdir(self.playlist_dir),
        }
        for slot in range(1, MUSIC_DIR_SLOTS + 1):
            path = self._resolve_music_slot(slot)
            info[f"music_dir_{slot}"] = path
            info[f"music_dir_{slot}_exists"] = os.path.isdir(path) if path else False
        return info

    # ---- Intern ----

    def _resolve_music_slot(self, slot: int) -> str:
        """Liest und loest einen Musik-Slot-Pfad auf. Leere Slots ergeben ''."""
        ini_key = _INI_MUSIC_KEY.format(slot=slot)
        default = _DEFAULTS.get(f"music_dir_{slot}", "")
        raw = self._settings.value(ini_key, default)
        if not raw:
            return ""
        return os.path.normpath(os.path.join(self._app_dir, raw))

    def _resolve(self, key: str) -> str:
        """Liest einen relativen Pfad aus der INI und loest ihn absolut auf."""
        ini_key = _INI_KEYS[key]
        relative = self._settings.value(ini_key, _DEFAULTS.get(key, ""))
        return os.path.normpath(os.path.join(self._app_dir, relative))

    def _store_path(self, ini_key: str, absolute_path: str, label: str):
        """Konvertiert einen absoluten Pfad in einen relativen und speichert ihn.

        Falls der Pfad auf einem anderen Laufwerk liegt (Windows),
        wird er als absoluter Pfad gespeichert (Fallback).
        """
        try:
            relative = os.path.relpath(absolute_path, self._app_dir)
            self._settings.setValue(ini_key, relative)
            print(f"[PathManager] {label} = {relative} (relativ)")
        except ValueError:
            # Windows: verschiedene Laufwerke (z.B. C: vs D:)
            self._settings.setValue(ini_key, absolute_path)
            print(f"[PathManager] {label} = {absolute_path} (absolut, anderes Laufwerk)")
