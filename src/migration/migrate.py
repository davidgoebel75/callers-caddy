"""Callers Caddy Migration Tool — Standalone PySide6-App.

Migriert Daten aus verschiedenen Quellsystemen nach Callers Caddy 2.0 (SQLite).
Unterstuetzte Quellen:
  - Callers Caddy 1.0 (Access 97)
  - SqView (kommt demnaechst)
  - SDPlayer (kommt demnaechst)

Aufruf:  python -m migration.migrate [zielordner] [--lang de|en]
         python src/migration/migrate.py [zielordner] [--lang de|en]
"""

import configparser
import os
import sys
import glob
import shutil
from datetime import datetime

# Sicherstellen dass src/ im Python-Pfad liegt (fuer gemeinsame i18n.py)
_SRC_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QLineEdit, QPushButton, QTextEdit, QProgressBar,
    QFileDialog, QGroupBox, QMessageBox, QRadioButton, QStackedWidget,
)
from PySide6.QtCore import Qt, QThread, Signal, QSettings

from i18n import _t, set_language, get_language
from migration.mdb_reader import MdbReader
from migration.sqview_reader import SqViewReader
from migration.converter import Converter
from migration.db_writer import DbWriter


# ===========================================================================
# Relative-Pfad-Helfer (BL-147) — migration-lokal gehalten, spiegelt die in
# path_manager.py verifizierte Logik. Kanonische Speicherform: POSIX '/'.
# ===========================================================================

def _to_posix(rel: str) -> str:
    """Normalisiert einen relativen Pfad auf POSIX-Forward-Slashes (DB-Form)."""
    return rel.replace("\\", "/")


def _is_within(path: str, base: str) -> bool:
    """True, wenn path innerhalb von base liegt (sichere Pruefung).

    Vermeidet den startswith-Bug (C:\\music2 unter C:\\music) und faengt
    Cross-Drive-Faelle ab (os.path.relpath wirft dort ValueError).
    """
    try:
        rel = os.path.relpath(path, base)
    except ValueError:
        return False  # anderes Laufwerk (Windows)
    return rel != os.pardir \
        and not rel.startswith(os.pardir + os.sep) \
        and not os.path.isabs(rel)


def _rel_to_first_root(fullpath: str, roots: list) -> str:
    """Relativer Pfad (POSIX '/') von fullpath gegen die ERSTE passende Wurzel.

    First come first serve in Reihenfolge der roots-Liste — identische Semantik
    zu PathManager.to_relative_filename()/find_song_file(), damit gespeicherte
    relative Pfade spaeter wieder gegen denselben Slot aufloesen. Liegt die Datei
    unter keiner Wurzel, wird nur der Basename zurueckgegeben.
    """
    fp = os.path.normpath(fullpath)
    for root in roots:
        if not root:
            continue
        base = os.path.normpath(root)
        if _is_within(fp, base):
            return _to_posix(os.path.relpath(fp, base))
    return os.path.basename(fp)


def _write_target_music_slots(target_dir: str, roots: list):
    """Schreibt die genutzten Wurzeln als Musik-Slots in die Ziel-INI (BL-147).

    Nur fuer den Verknuepfen-Modus noetig: Die App liest die Slots aus
    <target>/callers_caddy.ini (paths/music_dir_1..4). Pfade werden absolut
    gespeichert — PathManager loest absolute Werte korrekt auf.
    """
    ini_path = os.path.join(target_dir, "callers_caddy.ini")
    settings = QSettings(ini_path, QSettings.IniFormat)
    slot = 1
    seen = set()
    for root in roots:
        if not root or slot > 4:
            continue
        norm = os.path.normpath(root)
        key = norm.lower()
        if key in seen or not os.path.isdir(norm):
            continue
        seen.add(key)
        settings.setValue(f"paths/music_dir_{slot}", norm)
        slot += 1
    settings.sync()


# ===========================================================================
# Migrations-Logger (Detaillogfile im Zielordner)
# ===========================================================================

class MigrationLogger:
    """Schreibt ein detailliertes Migrationslog als Textdatei in den Zielordner.

    Texte sind uebersetzt (gewaehlte Sprache). Die Stufen-Tags
    DONE/WARNING/ERROR bleiben sprachunabhaengig konstant, damit das
    Logfile maschinell durchsuchbar bleibt.
    Jede Zeile wird sofort geflusht — auch bei Absturz mitten im Lauf
    ist alles bis dahin in der Datei.
    """

    DONE = "DONE"
    WARNING = "WARNING"
    ERROR = "ERROR"

    # Sprachunabhaengige THEMA-Tokens je Kategorie. Zusammen mit dem
    # SCHWEREGRAD ergibt sich ein suchbarer Doppel-Schluessel wie
    # "ERROR MUSIC" oder "DONE LYRIC", den man im Logfile direkt findet.
    TOPICS = {
        "record": "RECORD",
        "record_skipped": "RECORD",
        "record_fallback": "RECORD",
        "db_insert_failed": "RECORD",
        "mp3_linked": "MUSIC",
        "mp3_missing": "MUSIC",
        "mp3_blind": "MUSIC",
        "mp3_copy_failed": "MUSIC",
        "mp3_dupe_name": "MUSIC",
        "lyrics_marry": "LYRIC",
        "lyrics_marry_missing": "LYRIC",
        "lyrics_match": "LYRIC",
        "lyrics_missing": "LYRIC",
        "lyrics_none": "LYRIC",
        "lyrics_copy_failed": "LYRIC",
        "loops": "LOOP",
        "pitch": "PITCH",
        "bpm": "BPM",
        "quality": "QUALITY",
        "vocal": "VOCAL",
        "location": "LOCATION",
        "history": "HISTORY",
        "history_no_song": "HISTORY",
        "history_no_group": "HISTORY",
        "genres": "GENRE",
        "classified": "TYPE",
    }

    # Breite des Doppel-Schluessels "SCHWEREGRAD THEMA" fuer buendige Ausgabe.
    TAG_WIDTH = 16

    @staticmethod
    def topic_for(cat_key: str) -> str:
        """Liefert das THEMA-Token (z.B. 'MUSIC') zu einer Kategorie."""
        return MigrationLogger.TOPICS.get(cat_key, "INFO")

    @staticmethod
    def tag(level: str, cat_key: str) -> str:
        """Baut den suchbaren Doppel-Schluessel, z.B. 'ERROR MUSIC'."""
        return f"{level} {MigrationLogger.topic_for(cat_key)}"

    def __init__(self, target_dir: str, source_name: str):
        ts = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        self.path = os.path.join(target_dir, f"migration_log_{ts}.txt")
        self._fh = open(self.path, "w", encoding="utf-8")
        self._counts = {}        # {(level, cat_key): count}
        self._cat_labels = {}    # {cat_key: uebersetztes Label}
        self._current_song = None
        self._write(_t("mig_logfile_header", source=source_name,
                       target=target_dir,
                       ts=datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        self._write("=" * 70)

    def _write(self, text: str):
        if self._fh:
            self._fh.write(text + "\n")
            self._fh.flush()

    def info(self, text: str = ""):
        """Freitext-Zeile (Phasen-Infos, Hinweise)."""
        self._current_song = None
        self._write(text)

    def section(self, title: str):
        self._current_song = None
        self._write("")
        self._write(f"--- {title} ---")

    def step(self, level: str, cat_key: str, cat_label: str,
             song_label: str = None, detail: str = ""):
        """Schreibt einen Schritt-Eintrag und zaehlt ihn fuer die Summary.

        song_label gruppiert Eintraege pro Song: bei Wechsel wird eine
        Kopfzeile mit dem Songtitel geschrieben. Jede Zeile beginnt mit dem
        suchbaren Doppel-Schluessel "SCHWEREGRAD THEMA" (z.B. "DONE LYRIC").
        """
        key = (level, cat_key)
        self._counts[key] = self._counts.get(key, 0) + 1
        self._cat_labels[cat_key] = cat_label

        if song_label is not None and song_label != self._current_song:
            self._write(song_label)
            self._current_song = song_label
        indent = "  " if song_label is not None else ""
        tag = MigrationLogger.tag(level, cat_key).ljust(self.TAG_WIDTH)
        line = f"{indent}{tag}{cat_label}"
        if detail:
            line += f": {detail}"
        self._write(line)

    def error_block(self, text: str):
        """Schreibt einen mehrzeiligen Fehlerblock (z.B. Traceback)."""
        self._current_song = None
        self._write("")
        self._write("ERROR CRASH " + "=" * 58)
        self._write(text)

    def write_summary(self) -> str:
        """Schreibt die Kategorie-Summary ans Logende und gibt sie zurueck."""
        lines = ["", "=" * 70, _t("mig_logfile_summary_title"), ""]
        for level in (self.ERROR, self.WARNING, self.DONE):
            cats = sorted(
                (cat, n) for (lvl, cat), n in self._counts.items()
                if lvl == level
            )
            for cat, n in cats:
                tag = MigrationLogger.tag(level, cat).ljust(self.TAG_WIDTH)
                lines.append(f"  {tag}{self._cat_labels[cat]}: {n}")
        if len(lines) == 4:
            lines.append("  " + _t("mig_logfile_summary_empty"))
        lines.append("=" * 70)
        text = "\n".join(lines)
        self._write(text)
        return text

    def close(self):
        if self._fh:
            self._write("")
            self._write(_t("mig_logfile_footer",
                ts=datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
            self._fh.close()
            self._fh = None


# ===========================================================================
# Worker-Basisklasse (Signale + Logging-Helfer)
# ===========================================================================

class _LoggingWorker(QThread):
    """Gemeinsame Basis fuer alle Migrations-Worker.

    Stellt Signale, Detaillog-Anbindung und die Schritt-Helfer bereit.
    GUI-Regel: Phasen-Infos und alle WARNING/ERROR-Zeilen gehen ins GUI,
    DONE-Detailzeilen pro Song landen nur im Logfile.
    """
    progress = Signal(int, int)      # (current, total)
    log_msg = Signal(str)            # Log-Nachricht (GUI)
    log_file = Signal(str)           # Pfad zum Detaillogfile
    finished_ok = Signal(str)        # Erfolgs-Zusammenfassung
    finished_err = Signal(str)       # Fehlermeldung

    SOURCE_NAME = "?"

    def __init__(self):
        super().__init__()
        self._logger = None

    def run(self):
        # Migrations-Log UND Live-Anzeige bewusst immer Englisch rendern,
        # damit das Detaillogfile fuer den Support unabhaengig von der
        # gewaehlten UI-Sprache (z.B. Japanisch) lesbar bleibt. Die uebrige
        # UI wurde bereits vorher in der Nutzersprache aufgebaut; nach dem
        # Lauf wird die Sprache wiederhergestellt.
        _prev_lang = get_language()
        set_language("en")
        try:
            self._do_migration()
        except Exception as e:
            import traceback
            traceback.print_exc()
            if self._logger:
                try:
                    self._logger.error_block(traceback.format_exc())
                    self._logger.write_summary()
                    self._logger.close()
                except Exception:
                    pass
            self.finished_err.emit(_t("mig_log_error", error=e))
        finally:
            set_language(_prev_lang)

    def _start_log(self, target_dir):
        """Erzeugt das Detaillogfile und meldet den Pfad ans GUI."""
        self._logger = MigrationLogger(target_dir, self.SOURCE_NAME)
        self.log_file.emit(self._logger.path)
        self.log_msg.emit(_t("mig_log_file_hint", path=self._logger.path))

    def _both(self, msg):
        """Nachricht ins GUI und ins Logfile."""
        self.log_msg.emit(msg)
        self._logger.info(msg)

    def _step(self, level, cat_key, song_label=None, detail=""):
        """Schritt ins Logfile; WARNING/ERROR zusaetzlich ins GUI."""
        cat_label = _t("mig_cat_" + cat_key)
        self._logger.step(level, cat_key, cat_label, song_label, detail)
        if level != MigrationLogger.DONE:
            prefix = f"{song_label} — " if song_label else ""
            line = f"  {MigrationLogger.tag(level, cat_key)}  {prefix}{cat_label}"
            if detail:
                line += f": {detail}"
            self.log_msg.emit(line)

    def _file_step(self, level, cat_key, song_label=None, detail=""):
        """Schritt NUR ins Logfile (fuer Massen-Eintraege wie Historie)."""
        cat_label = _t("mig_cat_" + cat_key)
        self._logger.step(level, cat_key, cat_label, song_label, detail)

    def _finish(self, gui_summary):
        """Kategorie-Summary schreiben, Log schliessen, Erfolg melden."""
        cat_summary = self._logger.write_summary()
        log_path = self._logger.path
        self._logger.close()
        self.finished_ok.emit(
            gui_summary + "\n" + cat_summary + "\n"
            + _t("mig_log_file_hint", path=log_path))


# ===========================================================================
# Worker-Thread (laeuft im Hintergrund, sendet Fortschritt per Signal)
# ===========================================================================

class MigrationWorker(_LoggingWorker):
    """Fuehrt die eigentliche Migration im Hintergrund-Thread aus."""

    SOURCE_NAME = "Callers Caddy 1.0"

    def __init__(self, mdb_path, songs_dirs, lyrics_dir, playlists_dir,
                 notes_dir, target_dir, copy_mode=True, music_root=""):
        super().__init__()
        self.mdb_path = mdb_path
        self.songs_dirs = songs_dirs       # Liste von Verzeichnis-Pfaden
        self.lyrics_dir = lyrics_dir
        self.playlists_dir = playlists_dir
        self.notes_dir = notes_dir
        self.target_dir = target_dir
        self.copy_mode = copy_mode         # True=kopieren, False=verknuepfen (BL-147)
        self.music_root = music_root       # Wurzelverzeichnis fuer relative Pfade

    def _do_migration(self):
        self._start_log(self.target_dir)

        # --- Phase 0: MDB lesen ---
        self._both(_t("mig_log_reading_mdb"))
        reader = MdbReader(self.mdb_path)
        raw_songs = reader.read_songs()
        raw_groups = reader.read_groups()
        raw_history = reader.read_history()
        self._both(_t("mig_log_mdb_summary",
            songs=len(raw_songs), groups=len(raw_groups),
            history=len(raw_history)))

        # Zielverzeichnisse anlegen
        music_dir = os.path.join(self.target_dir, "music")
        lyrics_dir_target = os.path.join(self.target_dir, "lyrics")
        playlists_dir_target = os.path.join(self.target_dir, "playlists")
        notes_dir_target = os.path.join(self.target_dir, "notes")
        for d in [music_dir, lyrics_dir_target, playlists_dir_target,
                  notes_dir_target]:
            os.makedirs(d, exist_ok=True)

        # MP3s aus allen Quellverzeichnissen sammeln (Duplikate vermeiden)
        # BL-147: Wurzeln fuer relative Pfade (First come first serve, max 4).
        # Reihenfolge: vom User gewaehlte Wurzel zuerst, dann die Quellordner.
        roots = []
        for r in [self.music_root] + list(self.songs_dirs):
            if r and os.path.isdir(r):
                norm = os.path.normpath(r)
                if norm.lower() not in [x.lower() for x in roots]:
                    roots.append(norm)
        roots = roots[:4]

        # MP3s rekursiv (inkl. Unterordner) sammeln.
        # CC1 referenziert Songs nur per Dateiname -> Key = Basename.
        # store_name = relativer Pfad (POSIX) gegen die passende Wurzel.
        mp3_files = {}    # {basename_lower: full_path}  — erster Fund gewinnt
        mp3_relname = {}  # {basename_lower: store_name (relativer Pfad)}
        mp3_dupes = 0     # gleichnamige Zusatztreffer (mehrdeutig, ignoriert)
        for sdir in self.songs_dirs:
            if not sdir or not os.path.isdir(sdir):
                continue
            for root_d, _dirs, files in os.walk(sdir):
                for f in files:
                    if not f.lower().endswith(".mp3"):
                        continue
                    full = os.path.join(root_d, f)
                    key = f.lower()
                    if key not in mp3_files:
                        mp3_files[key] = full
                        mp3_relname[key] = _rel_to_first_root(full, roots)
                    elif os.path.normpath(full).lower() != \
                            os.path.normpath(mp3_files[key]).lower():
                        mp3_dupes += 1
        if mp3_dupes:
            self._step(MigrationLogger.WARNING, "mp3_dupe_name",
                       detail=str(mp3_dupes))

        # Gesamtschritte berechnen
        total = len(mp3_files)
        if self.lyrics_dir:
            total += len(os.listdir(self.lyrics_dir))
        if self.playlists_dir:
            total += len(glob.glob(os.path.join(self.playlists_dir, "*.txt")))
        if self.notes_dir:
            total += len(glob.glob(os.path.join(self.notes_dir, "*.txt")))
        total += len(raw_songs)   # DB-Songs
        total += len(raw_groups)  # DB-Gruppen
        total += len(raw_history) # DB-Historie
        current = 0

        # --- Phase 1: Dateien kopieren ---

        # MP3s (aus allen Quellverzeichnissen)
        mp3_copied = 0
        mp3_failed = []
        if mp3_files:
            if not self.copy_mode:
                # BL-147 Verknuepfen: nichts kopieren, Dateien bleiben am Ort
                self._both(_t("mig_log_linking_mode", count=len(mp3_files)))
                current += len(mp3_files)
                self.progress.emit(current, total)
            else:
                if len(self.songs_dirs) > 1:
                    self._both(_t("mig_log_copying_mp3_multi",
                        count=len(mp3_files), dirs=len(self.songs_dirs)))
                else:
                    self._both(_t("mig_log_copying_mp3", count=len(mp3_files)))
                mp3_total = len(mp3_files)
                for key, mp3 in mp3_files.items():
                    # Strukturerhaltend ins Ziel kopieren (Unterordner anlegen)
                    store_name = mp3_relname[key]
                    dest = os.path.join(music_dir, store_name.replace("/", os.sep))
                    try:
                        os.makedirs(os.path.dirname(dest), exist_ok=True)
                        if not os.path.exists(dest):
                            shutil.copy2(mp3, dest)
                        mp3_copied += 1
                    except Exception as e:
                        mp3_failed.append((store_name, str(e)))
                        self._step(MigrationLogger.ERROR, "mp3_copy_failed",
                                   detail=f"{store_name}: {e}")
                    current += 1
                    if (mp3_copied + len(mp3_failed)) % 50 == 0:
                        self.progress.emit(current, total)
                        self.log_msg.emit(_t("mig_log_mp3_progress",
                            current=mp3_copied, total=mp3_total))
                self.progress.emit(current, total)
                self._both(_t("mig_log_mp3_done", count=mp3_copied))

        # Lyrics
        lyrics_copied = 0
        if self.lyrics_dir and os.path.isdir(self.lyrics_dir):
            lyric_files = os.listdir(self.lyrics_dir)
            self._both(_t("mig_log_copying_lyrics", count=len(lyric_files)))
            for lf in lyric_files:
                src = os.path.join(self.lyrics_dir, lf)
                if os.path.isfile(src):
                    dest = os.path.join(lyrics_dir_target, lf)
                    if not os.path.exists(dest):
                        shutil.copy2(src, dest)
                    lyrics_copied += 1
                current += 1
            self.progress.emit(current, total)
            self._both(_t("mig_log_lyrics_done", count=lyrics_copied))

        # Playlists
        pl_copied = 0
        if self.playlists_dir and os.path.isdir(self.playlists_dir):
            pl_files = glob.glob(os.path.join(self.playlists_dir, "*.txt"))
            self._both(_t("mig_log_copying_playlists", count=len(pl_files)))
            for pf in pl_files:
                fname = os.path.basename(pf)
                dest = os.path.join(playlists_dir_target, fname)
                if not os.path.exists(dest):
                    shutil.copy2(pf, dest)
                pl_copied += 1
                current += 1
            self.progress.emit(current, total)
            self._both(_t("mig_log_playlists_done", count=pl_copied))

        # Notes
        notes_copied = 0
        if self.notes_dir and os.path.isdir(self.notes_dir):
            note_files = glob.glob(os.path.join(self.notes_dir, "*.txt"))
            self._both(_t("mig_log_copying_notes", count=len(note_files)))
            for nf in note_files:
                fname = os.path.basename(nf)
                dest = os.path.join(notes_dir_target, fname)
                if not os.path.exists(dest):
                    shutil.copy2(nf, dest)
                notes_copied += 1
                current += 1
            self.progress.emit(current, total)
            self._both(_t("mig_log_notes_done", count=notes_copied))

        # --- Phase 2: Datenbank schreiben ---

        db_path = os.path.join(self.target_dir, "callers_caddy.db")
        self._both(_t("mig_log_creating_db", path=db_path))
        writer = DbWriter(db_path)
        writer.create_tables()

        # Songs + Genre-Daten sammeln
        self._both(_t("mig_log_migrating_songs", count=len(raw_songs)))
        self._logger.section(_t("mig_log_migrating_songs", count=len(raw_songs)).strip())
        song_name_to_id = {}    # Fuer Historie-Matching
        song_genre_pairs = []   # [(song_id, genre_str), ...]
        songs_ok = 0
        songs_no_file = 0
        songs_with_lyrics = 0
        songs_with_loops = 0
        songs_with_bpm = 0
        songs_with_quality = 0
        songs_with_vocal = 0
        for raw in raw_songs:
            converted = Converter.convert_song(raw)
            if not converted["filename"]:
                name = str(raw.get("Name", "")).strip() or "?"
                self._step(MigrationLogger.WARNING, "record_skipped",
                           song_label=name)
                current += 1
                continue

            song_label = converted["title"] or converted["filename"]

            # BL-147: Gefundene Datei -> relativen Pfad (gegen Wurzel) als
            # Speicherform setzen. MDB liefert nur den Basename -> per Basename
            # in der rekursiven MP3-Sammlung nachschlagen.
            fkey = os.path.basename(converted["filename"]).lower()
            store_name = mp3_relname.get(fkey)
            if store_name:
                converted["filename"] = store_name
                if self.copy_mode:
                    mp3_exists = os.path.isfile(
                        os.path.join(music_dir, store_name.replace("/", os.sep)))
                else:
                    mp3_exists = os.path.isfile(mp3_files[fkey])
            else:
                # Datei in keinem Quellordner gefunden -> Blind-Eintrag (Basename)
                mp3_exists = False
            if mp3_exists:
                self._file_step(MigrationLogger.DONE, "mp3_linked",
                                song_label, detail=converted["filename"])
            else:
                songs_no_file += 1
                self._step(MigrationLogger.ERROR, "mp3_missing",
                           song_label, detail=converted["filename"])

            # Felder herausnehmen, die nicht in die songs-Tabelle gehoeren
            genre_str = converted.pop("genre", "")
            url_vocal = converted.pop("url_vocal", "")

            song_id = writer.insert_song(converted)
            if song_id > 0:
                self._file_step(MigrationLogger.DONE, "record",
                                song_label, detail=f"#{song_id}")
                # Statistik-Zaehler
                if converted["lyrics_file"]:
                    songs_with_lyrics += 1
                    # Lyrics laut MDB vorhanden — Datei pruefen
                    if os.path.isfile(os.path.join(
                            lyrics_dir_target, converted["lyrics_file"])):
                        self._file_step(MigrationLogger.DONE, "lyrics_match",
                                        song_label,
                                        detail=converted["lyrics_file"])
                    else:
                        self._step(MigrationLogger.ERROR, "lyrics_missing",
                                   song_label,
                                   detail=converted["lyrics_file"])
                if converted["loop_in"] > 0 or converted["loop_out"] > 0:
                    songs_with_loops += 1
                    self._file_step(
                        MigrationLogger.DONE, "loops", song_label,
                        detail=f"{converted['loop_in']:.1f}–"
                               f"{converted['loop_out']:.1f}s")
                if converted["base_bpm"] > 0:
                    songs_with_bpm += 1
                    self._file_step(MigrationLogger.DONE, "bpm", song_label,
                                    detail=f"{converted['base_bpm']:.1f}")
                if converted["quality"] > 0:
                    songs_with_quality += 1
                    self._file_step(MigrationLogger.DONE, "quality",
                                    song_label,
                                    detail=str(converted["quality"]))
                # Name-Mapping fuer Historie (case-insensitive)
                title = converted["title"].lower().strip()
                song_name_to_id[title] = song_id
                # Auch Originalname aus MDB
                orig_name = str(raw.get("Name", "")).lower().strip()
                if orig_name and orig_name != title:
                    song_name_to_id[orig_name] = song_id
                # Auch Dateiname ohne Extension (Historie referenziert oft so).
                # BL-147: filename kann jetzt ein relativer Pfad sein -> Basename nehmen.
                fname = converted["filename"]
                if fname:
                    fname_noext = os.path.splitext(
                        os.path.basename(fname))[0].lower().strip()
                    if fname_noext not in song_name_to_id:
                        song_name_to_id[fname_noext] = song_id
                # Genre merken
                if genre_str:
                    song_genre_pairs.append((song_id, genre_str))
                # BL-125: Vocal-Version als naechste freie music-Variante speichern
                if url_vocal:
                    writer.add_variant(song_id, "music", "Vocal-Version", url_vocal)
                    songs_with_vocal += 1
                    self._file_step(MigrationLogger.DONE, "vocal",
                                    song_label, detail=url_vocal)
                songs_ok += 1
            else:
                self._step(MigrationLogger.ERROR, "db_insert_failed",
                           song_label, detail=converted["filename"])

            current += 1
            if songs_ok % 50 == 0:
                self.progress.emit(current, total)

        self.progress.emit(current, total)
        self._both(_t("mig_log_songs_done", count=songs_ok))
        if songs_no_file > 0:
            self._both(_t("mig_log_songs_no_file", count=songs_no_file))
        self._both(_t("mig_log_songs_detail",
            lyrics=songs_with_lyrics, bpm=songs_with_bpm,
            loops=songs_with_loops, quality=songs_with_quality))
        if songs_with_vocal > 0:
            self._both(f"  {songs_with_vocal} Songs mit Vocal-Version migriert")

        # Genres
        genre_names = set(g for _, g in song_genre_pairs)
        genre_name_to_id = {}
        for gname in genre_names:
            gid = writer.insert_genre(gname)
            genre_name_to_id[gname] = gid
        # Song-Genre-Verknuepfungen
        for song_id, genre_str in song_genre_pairs:
            gid = genre_name_to_id.get(genre_str)
            if gid:
                writer.link_song_genre(song_id, gid)
        writer.commit()
        self._both(
            _t("mig_log_genres_done", genres=len(genre_names),
               links=len(song_genre_pairs))
        )

        # Gruppen → Lokationen
        self._both(_t("mig_log_migrating_locations", count=len(raw_groups)))
        self._logger.section(
            _t("mig_log_migrating_locations", count=len(raw_groups)).strip())
        group_name_to_id = {}
        for raw in raw_groups:
            name = str(raw.get("Name") or raw.get("name") or "").strip()
            if not name:
                current += 1
                continue
            loc_id = writer.insert_location(name)
            group_name_to_id[name.lower()] = loc_id
            self._file_step(MigrationLogger.DONE, "location", detail=name)
            current += 1
        self.progress.emit(current, total)
        self._both(_t("mig_log_locations_done", count=len(group_name_to_id)))

        # --- History-Based Reconstruction Fallback ---
        # Wenn Song-Tabelle unbrauchbar (access-parser kann erweiterte
        # Tabellen nicht parsen), rekonstruieren wir Songs und Lokationen
        # aus den Historie-Eintraegen.
        if songs_ok == 0 and raw_history:
            self._both(_t("mig_log_fallback_start"))
            self._logger.section(_t("mig_log_fallback_start").strip())
            unique_titles = {}   # {title_lower: title_original}
            unique_groups = {}   # {group_lower: group_original}
            for raw in raw_history:
                titel = str(raw.get("Titel", "") or "").strip()
                gruppe = str(raw.get("Gruppe", "") or "").strip()
                if titel:
                    key = titel.lower()
                    if key not in unique_titles:
                        unique_titles[key] = titel
                if gruppe:
                    key = gruppe.lower()
                    if key not in unique_groups:
                        unique_groups[key] = gruppe

            # Songs aus Historie-Titeln erstellen
            self._both(_t("mig_log_fallback_songs",
                          count=len(unique_titles)))
            fb_songs = 0
            for title_lower, title_orig in unique_titles.items():
                # Versuche passende MP3 zu finden
                # CC1 Historie referenziert oft den Songnamen ohne Extension
                filename = ""
                lyrics_file = ""
                for mp3_key in mp3_files:
                    mp3_name_noext = mp3_key.rsplit(".", 1)[0]
                    if mp3_name_noext == title_lower:
                        filename = os.path.basename(mp3_files[mp3_key])
                        break
                # Versuche Lyrics zu finden
                if lyrics_dir_target:
                    for ext in [".rtf", ".htm", ".html", ".txt", ".docx", ".pdf"]:
                        candidate = os.path.join(
                            lyrics_dir_target, title_orig + ext)
                        if os.path.isfile(candidate):
                            lyrics_file = title_orig + ext
                            break
                        # Case-insensitiv
                        candidate_lower = title_lower + ext
                        for lf in os.listdir(lyrics_dir_target):
                            if lf.lower() == candidate_lower:
                                lyrics_file = lf
                                break
                        if lyrics_file:
                            break

                # Filename: MP3 wenn gefunden, sonst Titel als Platzhalter
                # (wird spaeter vom User manuell zugeordnet)
                if not filename:
                    filename = title_orig

                song_data = {
                    "filename": filename,
                    "title": title_orig,
                    "artist": "",
                    "label": "",
                    "quality": 0,
                    "base_bpm": 0.0,
                    "standard_tempo": 1.0,
                    "pitch": 0.0,
                    "volume": 1.0,
                    "loop_in": 0.0,
                    "loop_out": 0.0,
                    "lyrics_file": lyrics_file,
                    "is_pattern": 1,
                    "is_singing": 1,
                }
                song_id = writer.insert_song(song_data)
                if song_id > 0:
                    song_name_to_id[title_lower] = song_id
                    fb_songs += 1
                    self._file_step(MigrationLogger.DONE, "record_fallback",
                                    song_label=title_orig)
                else:
                    self._step(MigrationLogger.ERROR, "db_insert_failed",
                               song_label=title_orig)
            writer.commit()
            self._both(_t("mig_log_fallback_songs_done",
                          count=fb_songs))

            # Lokationen aus Historie-Gruppen erstellen
            if not group_name_to_id:
                self._both(_t("mig_log_fallback_locations",
                              count=len(unique_groups)))
                for group_lower, group_orig in unique_groups.items():
                    loc_id = writer.insert_location(group_orig)
                    group_name_to_id[group_lower] = loc_id
                    self._file_step(MigrationLogger.DONE, "location",
                                    detail=group_orig)
                writer.commit()
                self._both(_t("mig_log_fallback_locations_done",
                              count=len(unique_groups)))

        # Historie
        self._both(_t("mig_log_migrating_history", count=len(raw_history)))
        self._logger.section(
            _t("mig_log_migrating_history", count=len(raw_history)).strip())
        history_entries = []
        no_song_match = 0
        no_group_match = 0
        for raw in raw_history:
            titel = str(raw.get("Titel") or raw.get("titel") or "").lower().strip()
            gruppe = str(raw.get("Gruppe") or raw.get("gruppe") or "").lower().strip()
            datum = str(raw.get("Datum") or raw.get("datum") or "").strip()

            # Song-Matching
            song_id = song_name_to_id.get(titel)
            if song_id is None:
                no_song_match += 1
                self._file_step(MigrationLogger.WARNING, "history_no_song",
                                detail=f"{titel} ({datum})")
                current += 1
                continue

            # Gruppen-Matching
            location_id = group_name_to_id.get(gruppe)
            if location_id is None:
                no_group_match += 1
                # Trotzdem eintragen (location_id = NULL)
                self._file_step(MigrationLogger.WARNING, "history_no_group",
                                detail=f"{titel} ({datum}): {gruppe}")

            # Datum formatieren (YYYY-MM-DD HH:MM:SS)
            played_at = datum[:19] if len(datum) >= 19 else datum

            history_entries.append((song_id, location_id, played_at))
            self._file_step(MigrationLogger.DONE, "history",
                            detail=f"{titel} ({played_at})")
            current += 1

            if len(history_entries) % 500 == 0:
                self.progress.emit(current, total)

        # Bulk-Insert
        if history_entries:
            writer.bulk_insert_history(history_entries)
        self.progress.emit(current, total)
        self._both(_t("mig_log_history_done", count=len(history_entries)))
        if no_song_match > 0:
            self._both(_t("mig_log_history_no_song", count=no_song_match))
        if no_group_match > 0:
            self._both(_t("mig_log_history_no_group", count=no_group_match))

        # Stats aufbauen
        self._both(_t("mig_log_building_stats"))
        writer.rebuild_stats()

        # Zusammenfassung
        vocal_line = (f"  davon {songs_with_vocal} mit Vocal-Version\n"
                      if songs_with_vocal > 0 else "")
        summary = (
            f"\n{'='*50}\n"
            f"{_t('mig_log_summary_title')}\n"
            f"{_t('mig_log_summary_songs', count=writer.get_song_count())}\n"
            f"{vocal_line}"
            f"{_t('mig_log_summary_song_detail', lyrics=songs_with_lyrics, bpm=songs_with_bpm, loops=songs_with_loops, quality=songs_with_quality)}\n"
            f"{_t('mig_log_summary_locations', count=writer.get_location_count())}\n"
            f"{_t('mig_log_summary_history', count=writer.get_history_count())}\n"
            f"{_t('mig_log_summary_mp3', count=mp3_copied)}\n"
            f"{_t('mig_log_summary_lyrics', count=lyrics_copied)}\n"
            f"{_t('mig_log_summary_playlists', count=pl_copied)}\n"
            f"{_t('mig_log_summary_notes', count=notes_copied)}\n"
            f"{_t('mig_log_summary_db', path=db_path)}\n"
            f"{'='*50}"
        )
        # BL-147: Verknuepfen-Modus -> Quellordner als Musik-Slots in die Ziel-INI
        if not self.copy_mode:
            _write_target_music_slots(self.target_dir, roots)
            self._both(_t("mig_log_linked_slots", count=min(len(roots), 4)))
        writer.close()
        self._logger.info(summary)
        self._finish(summary)


# ===========================================================================
# SqView Worker
# ===========================================================================

class SqViewWorker(_LoggingWorker):
    """Fuehrt die SqView-Migration im Hintergrund-Thread aus.

    Unterstuetzt Blind-Import: Songs werden auch ohne vorhandene MP3-Datei
    in die DB eingetragen. Der Dateiname dient als Platzhalter. Sobald der
    User die MP3 spaeter importiert, wird der bestehende Eintrag aktiviert.
    """

    SOURCE_NAME = "SqView"

    def __init__(self, sqview_db_path, music_dir, lyrics_dir, target_dir,
                 copy_mode=True, music_root=""):
        super().__init__()
        self.sqview_db_path = sqview_db_path
        self.music_dir = music_dir      # Kann leer sein → reiner Blind-Import
        self.lyrics_dir = lyrics_dir
        self.target_dir = target_dir
        self.copy_mode = copy_mode      # True=kopieren, False=verknuepfen (BL-147)
        # Wurzel fuer relative Pfade; Default = music_dir (SqView-Einzelwurzel)
        self.music_root = music_root or music_dir

    # ------------------------------------------------------------------
    # Hilfsmethoden
    # ------------------------------------------------------------------

    @staticmethod
    def _build_mp3_index(music_dir: str) -> dict:
        """Baut einen rekursiven Index aller MP3s: {filename_lower: [full_paths]}.

        BL-147: Liste statt Einzelwert — gleichnamige Dateien in verschiedenen
        Unterordnern gehen nicht mehr verloren. Jede Datei wird zusaetzlich unter
        ihrem bereinigten Namen (Apostroph-Escape [¤] vs. ') indiziert.
        """
        index = {}
        if not music_dir or not os.path.isdir(music_dir):
            return index
        for root, _dirs, files in os.walk(music_dir):
            for f in files:
                if f.lower().endswith('.mp3'):
                    full = os.path.join(root, f)
                    for key in {f.lower(), SqViewReader.clean_text(f).lower()}:
                        lst = index.setdefault(key, [])
                        if full not in lst:
                            lst.append(full)
        return index

    @staticmethod
    def _best_match(candidates: list, sqview_fullpath: str) -> str:
        """Waehlt bei mehreren gleichnamigen Dateien die mit dem laengsten
        gemeinsamen Pfad-Suffix zum alten SqView-Pfad (sonst die erste).

        So landen zwei gleichnamige SqView-Songs (unterschiedliche Quellpfade)
        auf unterschiedlichen Zieldateien statt zu kollidieren.
        """
        if not candidates:
            return ""
        if len(candidates) == 1:
            return candidates[0]
        sv = [p for p in os.path.normpath(sqview_fullpath).lower().split(os.sep) if p]
        best, best_score = candidates[0], -1
        for c in candidates:
            cp = [p for p in os.path.normpath(c).lower().split(os.sep) if p]
            score = 0
            for a, b in zip(reversed(sv), reversed(cp)):
                if a == b:
                    score += 1
                else:
                    break
            if score > best_score:
                best, best_score = c, score
        return best

    @staticmethod
    def _build_lyrics_index(lyrics_dir: str) -> dict:
        """Baut einen Index aller Lyrics-Dateien: {name_noext_lower: filename}.

        Jede Datei wird auch unter ihrem bereinigten Namen (Apostroph statt
        [¤]) indiziert, damit Titel-Matching unabhaengig vom Escape klappt.
        """
        index = {}
        if not lyrics_dir or not os.path.isdir(lyrics_dir):
            return index
        for f in os.listdir(lyrics_dir):
            if os.path.isfile(os.path.join(lyrics_dir, f)):
                noext = os.path.splitext(f)[0]
                for key in {noext.lower(), SqViewReader.clean_text(noext).lower()}:
                    if key not in index:
                        index[key] = f
        return index

    # ------------------------------------------------------------------
    # Haupt-Migration
    # ------------------------------------------------------------------

    def _do_migration(self):
        self._start_log(self.target_dir)

        # --- Phase 0: SqView-DB lesen ---
        self._both(_t("mig_sqv_log_reading"))
        reader = SqViewReader(self.sqview_db_path)
        all_songs = reader.read_all_song_paths()   # volle Bibliothek
        raw_track = reader.read_track()
        marriages = reader.read_marriages()        # explizite Song-Lyrics-Paare
        summary = reader.get_summary()
        self._both(_t("mig_sqv_log_summary",
            songs=summary["songs"], locations=summary["locations"],
            history=summary["history"], lyrics=summary["lyrics"]))
        if marriages:
            self._both(_t("mig_sqv_log_marriages", count=len(marriages)))

        blind_mode = not self.music_dir or not os.path.isdir(self.music_dir)
        if blind_mode:
            self._both("\n\u26a0 " + _t("mig_sqv_log_blind_mode"))

        # Zielverzeichnisse anlegen
        music_target = os.path.join(self.target_dir, "music")
        lyrics_target = os.path.join(self.target_dir, "lyrics")
        for d in [music_target, lyrics_target]:
            os.makedirs(d, exist_ok=True)

        # MP3-Index aufbauen (rekursiv durch alle Unterordner)
        mp3_index = self._build_mp3_index(self.music_dir)
        if mp3_index:
            self._both("  " + _t("mig_sqv_log_mp3_found", count=len(mp3_index)))

        # Lyrics-Index aufbauen
        lyrics_index = self._build_lyrics_index(self.lyrics_dir)
        if lyrics_index:
            self._both("  " + _t("mig_sqv_log_lyrics_found", count=len(lyrics_index)))

        total = len(all_songs) + len(raw_track) + len(lyrics_index)
        current = 0

        # --- Phase 1: Lyrics kopieren ---
        lyrics_copied = 0
        if lyrics_index:
            self._both(f"\n--- {_t('mig_sqv_sec_lyrics', count=len(lyrics_index))} ---")
            for orig_fname in lyrics_index.values():
                src = os.path.join(self.lyrics_dir, orig_fname)
                dest = os.path.join(lyrics_target, orig_fname)
                if os.path.isfile(src) and not os.path.exists(dest):
                    try:
                        shutil.copy2(src, dest)
                        lyrics_copied += 1
                    except Exception as e:
                        self._step(MigrationLogger.ERROR, "lyrics_copy_failed",
                                   detail=f"{orig_fname}: {e}")
                current += 1
            self.progress.emit(current, total)
            self._both("  \u2705 " + _t("mig_sqv_lyrics_copied", count=lyrics_copied))

        # --- Phase 2: Datenbank schreiben ---
        db_path = os.path.join(self.target_dir, "callers_caddy.db")
        self._both(f"\n--- {_t('mig_sqv_sec_db')} ---")
        self._both("  " + _t("mig_sqv_db_target", path=db_path))
        writer = DbWriter(db_path)
        writer.create_tables()

        # Songs
        self._both(f"\n--- {_t('mig_sqv_sec_songs', count=len(all_songs))} ---")
        self._logger.info("")
        song_path_to_id = {}   # {fullpath_lower | filename_lower: song_id}
        songs_ok = 0
        songs_blind = 0        # Eingetragen, aber ohne MP3-Datei
        songs_mp3_missing = 0  # Musik-Ordner angegeben, Datei trotzdem nicht da
        songs_with_mp3 = 0
        songs_with_loop = 0
        songs_with_pitch = 0
        songs_with_lyrics = 0
        songs_lyrics_marry = 0
        songs_patter = 0       # is_pattern gesetzt (inkl. P&S)
        songs_singing = 0      # is_singing gesetzt (inkl. P&S)
        songs_both = 0         # P&S
        mp3_copied = 0

        for raw in all_songs:
            fname = raw['filename']
            title = raw['title']
            fname_lower = fname.lower()
            song_label = f"{title}  [{fname}]"

            # MP3 suchen (Apostroph-Escape [¤]/' beidseitig pruefen).
            # BL-147: bei mehreren gleichnamigen Treffern per altem SqView-Pfad
            # disambiguieren; gespeichert wird der relative Pfad gegen die Wurzel.
            clean_fname = SqViewReader.clean_text(fname)
            candidates = (mp3_index.get(fname_lower)
                          or mp3_index.get(clean_fname.lower()) or [])
            src_mp3 = self._best_match(candidates, raw.get('fullpath', '')) \
                if candidates else ""
            store_fname = fname            # Default: roher DB-Name (Blind-Eintrag)
            if src_mp3:
                store_fname = _rel_to_first_root(src_mp3, [self.music_root])
                ok = True
                if self.copy_mode:
                    # Strukturerhaltend ins Ziel kopieren (Unterordner anlegen)
                    dest_mp3 = os.path.join(
                        music_target, store_fname.replace("/", os.sep))
                    try:
                        os.makedirs(os.path.dirname(dest_mp3), exist_ok=True)
                        if not os.path.exists(dest_mp3):
                            shutil.copy2(src_mp3, dest_mp3)
                            mp3_copied += 1
                    except Exception as e:
                        ok = False
                        self._step(MigrationLogger.ERROR, "mp3_copy_failed",
                                   song_label, detail=f"{store_fname}: {e}")
                if ok:
                    songs_with_mp3 += 1
                    self._file_step(MigrationLogger.DONE, "mp3_linked",
                                    song_label, detail=store_fname)
            elif blind_mode:
                # Bewusst ohne Musik-Ordner gestartet — kein Fehler
                songs_blind += 1
                self._file_step(MigrationLogger.WARNING, "mp3_blind",
                                song_label, detail=fname)
            else:
                # Laut SqView-DB vorhanden, aber nicht im Musik-Ordner gefunden
                songs_blind += 1
                songs_mp3_missing += 1
                self._step(MigrationLogger.ERROR, "mp3_missing",
                           song_label, detail=fname)

            # Lyrics: 1) explizite SqView-Zuordnung (marry-Tabelle),
            #         2) Namens-Heuristik als Fallback
            lyrics_file = ""
            marry_path = marriages.get(raw['fullpath'].lower())
            if marry_path:
                lyr_name = os.path.basename(marry_path)
                lyr_noext = os.path.splitext(lyr_name)[0].lower()
                if os.path.isfile(marry_path):
                    dest = os.path.join(lyrics_target, lyr_name)
                    try:
                        if not os.path.exists(dest):
                            shutil.copy2(marry_path, dest)
                            lyrics_copied += 1
                        lyrics_file = lyr_name
                        songs_lyrics_marry += 1
                        self._file_step(MigrationLogger.DONE, "lyrics_marry",
                                        song_label, detail=lyr_name)
                    except Exception as e:
                        self._step(MigrationLogger.ERROR, "lyrics_copy_failed",
                                   song_label, detail=f"{lyr_name}: {e}")
                elif (lyrics_index.get(lyr_noext)
                      or lyrics_index.get(SqViewReader.clean_text(lyr_noext))):
                    # Originalpfad existiert nicht mehr, aber gleichnamige
                    # Datei liegt im angegebenen Lyrics-Ordner (Apostroph egal)
                    lyrics_file = (lyrics_index.get(lyr_noext)
                                   or lyrics_index.get(
                                       SqViewReader.clean_text(lyr_noext)))
                    songs_lyrics_marry += 1
                    self._file_step(MigrationLogger.DONE, "lyrics_marry",
                                    song_label, detail=lyrics_file)
                else:
                    # Laut SqView-Zuordnung vorhanden, aber nicht auffindbar
                    self._step(MigrationLogger.ERROR, "lyrics_marry_missing",
                               song_label, detail=marry_path)
            if not lyrics_file and lyrics_index:
                lyrics_file = SqViewReader.match_lyrics(title, lyrics_index)
                if lyrics_file:
                    self._file_step(MigrationLogger.DONE, "lyrics_match",
                                    song_label, detail=lyrics_file)
            if not lyrics_file and raw['path_is_singing'] and not marry_path:
                self._file_step(MigrationLogger.WARNING, "lyrics_none",
                                song_label)
            if lyrics_file:
                songs_with_lyrics += 1

            # Song-Dict fuer DB-Insert
            has_loop = raw['loop_in'] > 0 or raw['loop_out'] > 0
            has_pitch = raw['pitch'] != 0
            if has_loop:
                songs_with_loop += 1
                self._file_step(
                    MigrationLogger.DONE, "loops", song_label,
                    detail=f"{raw['loop_in']:.1f}-{raw['loop_out']:.1f}s")
            if has_pitch:
                songs_with_pitch += 1
                self._file_step(MigrationLogger.DONE, "pitch", song_label,
                                detail=f"{raw['pitch']:+d}")

            # --- P/S/PS-Klassifizierung ---
            # Regel: Loop gesetzt -> Patter; Lyric vorhanden -> Singing;
            # Pfad nur als Indiz; ohne jedes Signal Default = Singing.
            # Treffen beide Signale zu, ist der Song automatisch P&S.
            has_lyric = bool(lyrics_file)
            is_pattern = 1 if (has_loop or raw['path_is_patter']) else 0
            is_singing = 1 if (has_lyric or raw['path_is_singing']) else 0
            if not is_pattern and not is_singing:
                is_singing = 1
            if is_pattern:
                songs_patter += 1
            if is_singing:
                songs_singing += 1
            if is_pattern and is_singing:
                songs_both += 1
            cat = ("P&S" if (is_pattern and is_singing)
                   else "P" if is_pattern else "S")
            self._file_step(MigrationLogger.DONE, "classified",
                            song_label, detail=cat)

            song_data = {
                "filename": store_fname,
                "title": title,
                "artist": "",
                "label": "",
                "quality": 0,
                "base_bpm": 0.0,
                "standard_tempo": 1.0,
                "pitch": float(raw['pitch']),
                "volume": 1.0,
                "loop_in": raw['loop_in'],
                "loop_out": raw['loop_out'],
                "lyrics_file": lyrics_file,
                "is_pattern": is_pattern,
                "is_singing": is_singing,
            }
            song_id = writer.insert_song(song_data)
            if song_id <= 0:
                self._step(MigrationLogger.ERROR, "db_insert_failed",
                           song_label, detail=fname)
                current += 1
                continue
            self._file_step(MigrationLogger.DONE, "record", song_label,
                            detail=f"#{song_id}")

            # Matching-Index fuer Historie aufbauen
            song_path_to_id[fname_lower] = song_id
            song_path_to_id[raw['fullpath'].lower()] = song_id
            songs_ok += 1

            current += 1
            if songs_ok % 50 == 0:
                self.progress.emit(current, total)

        writer.commit()
        self.progress.emit(current, total)
        self._both("\n  \u2705 " + _t("mig_sqv_songs_imported", count=songs_ok))
        self._both("     " + _t("mig_sqv_songs_ps", patter=songs_patter,
                                  singing=songs_singing, both=songs_both))
        if songs_with_mp3:
            self._both("     " + _t("mig_sqv_songs_mp3",
                                      count=songs_with_mp3, copied=mp3_copied))
        if songs_blind:
            self._both("     " + _t("mig_sqv_songs_blind", count=songs_blind))
        if songs_mp3_missing:
            self._both("     " + _t("mig_sqv_songs_mp3_missing",
                                      count=songs_mp3_missing))
        if songs_with_loop:
            self._both("     " + _t("mig_sqv_songs_loop", count=songs_with_loop))
        if songs_with_pitch:
            self._both("     " + _t("mig_sqv_songs_pitch", count=songs_with_pitch))
        if songs_with_lyrics:
            self._both("     " + _t("mig_sqv_songs_lyrics", count=songs_with_lyrics))
        if songs_lyrics_marry:
            self._both("     " + _t("mig_sqv_songs_lyrics_marry",
                                      count=songs_lyrics_marry))

        # --- Lokationen (aus track.name) ---
        location_names = set()
        for t in raw_track:
            name = str(t.get("name", "")).strip()
            if name:
                location_names.add(name)
        location_name_to_id = {}
        if location_names:
            self._both(f"\n--- {_t('mig_sqv_sec_locations', count=len(location_names))} ---")
            for name in sorted(location_names):
                loc_id = writer.insert_location(name)
                location_name_to_id[name.lower()] = loc_id
                self._file_step(MigrationLogger.DONE, "location",
                                detail=f"#{loc_id} {name}")
            self._both("\n  \u2705 " + _t("mig_sqv_locations_imported",
                                              count=len(location_name_to_id)))

        # --- Abspielhistorie ---
        self._both(f"\n--- {_t('mig_sqv_sec_history', count=len(raw_track))} ---")
        history_entries = []
        no_song_match = 0
        for t in raw_track:
            fullpath = str(t.get("fullpath", "")).lower()
            fname = os.path.basename(fullpath)
            dance_name = str(t.get("name", "")).strip()
            date_str = str(t.get("date", "")).strip()
            time_str = str(t.get("time", "")).strip()
            played_at = f"{date_str} {time_str}:00" if date_str else ""

            song_id = song_path_to_id.get(fullpath) or song_path_to_id.get(fname)
            if song_id is None:
                no_song_match += 1
                self._file_step(MigrationLogger.WARNING, "history_no_song",
                                detail=f"{fname} ({date_str} {time_str})")
                current += 1
                continue

            location_id = location_name_to_id.get(dance_name.lower())
            history_entries.append((song_id, location_id, played_at))
            self._file_step(MigrationLogger.DONE, "history",
                            detail=f"{fname} ({played_at})")
            current += 1

        if history_entries:
            writer.bulk_insert_history(history_entries)
        self.progress.emit(current, total)
        self._both("  \u2705 " + _t("mig_sqv_history_imported", count=len(history_entries)))
        if no_song_match > 0:
            self._both("  \u26a0 " + _t("mig_sqv_history_no_song", count=no_song_match))

        # Stats aufbauen
        writer.rebuild_stats()

        # Zusammenfassung
        blind_note = ("  \u26a0 " + _t("mig_sqv_summary_blind_note") + "\n"
                      if songs_blind else "")
        summary_text = (
            f"\n{'='*50}\n"
            f"{_t('mig_log_summary_title')}\n"
            + _t('mig_sqv_summary_songs', count=writer.get_song_count(),
                 blind=songs_blind) + "\n"
            + _t('mig_sqv_summary_ps', patter=songs_patter,
                 singing=songs_singing, both=songs_both) + "\n"
            f"{_t('mig_log_summary_locations', count=writer.get_location_count())}\n"
            f"{_t('mig_log_summary_history', count=writer.get_history_count())}\n"
            f"{_t('mig_log_summary_mp3', count=mp3_copied)}\n"
            f"{_t('mig_log_summary_lyrics', count=lyrics_copied)}\n"
            f"{_t('mig_log_summary_db', path=db_path)}\n"
            + blind_note
            + f"{'='*50}"
        )
        # BL-147: Verknuepfen-Modus -> Wurzel als Musik-Slot in die Ziel-INI
        if not self.copy_mode and self.music_root:
            _write_target_music_slots(self.target_dir, [self.music_root])
            self._both(_t("mig_log_linked_slots", count=1))
        writer.close()
        reader.close()
        self._logger.info(summary_text)
        self._finish(summary_text)


# ===========================================================================
# Hauptfenster
# ===========================================================================

class MigrationWindow(QWidget):
    """Standalone Migrations-GUI mit Quellsystem-Auswahl."""

    # Quellsysteme
    SOURCE_CC10 = "cc10"
    SOURCE_SQVIEW = "sqview"
    SOURCE_SDPLAYER = "sdplayer"

    def __init__(self, target_dir=None, lang=None):
        super().__init__()
        self.setMinimumWidth(700)
        self._worker = None
        self._log_path = None          # Pfad zum Detaillogfile des Laufs
        self._mdb_summary = None       # Cache fuer MDB-Zaehlung
        self._mdb_summary_path = None  # Zu welcher MDB gehoert der Cache?
        self._preset_target = target_dir  # Vom Installer uebergeben
        self._preset_lang = lang       # Vom Installer oder CLI uebergeben

        if self._preset_lang:
            # Sprache bereits gesetzt — direkt zur Haupt-UI
            self.setWindowTitle(_t("mig_window_title"))
            self._build_ui()
        else:
            # Sprachauswahl anzeigen
            self.setWindowTitle("Callers Caddy")
            self._build_lang_ui()

    def _build_lang_ui(self):
        """Sprachauswahl-Seite (hardcoded, spraechneutral)."""
        self._lang_layout = QVBoxLayout(self)
        self._lang_layout.setSpacing(10)

        lang_box = QGroupBox("Language / Sprache")
        lang_inner = QVBoxLayout(lang_box)

        info = QLabel("Please select your language.\nBitte waehlen Sie Ihre Sprache.\n言語を選択してください。")
        info.setWordWrap(True)
        info.setStyleSheet("font-size: 14px; margin-bottom: 12px;")
        lang_inner.addWidget(info)

        self._radio_en = QRadioButton("English")
        self._radio_en.setStyleSheet("font-weight: bold; font-size: 14px;")
        self._radio_en.setChecked(True)
        lang_inner.addWidget(self._radio_en)

        self._radio_de = QRadioButton("Deutsch")
        self._radio_de.setStyleSheet("font-weight: bold; font-size: 14px;")
        lang_inner.addWidget(self._radio_de)

        self._radio_ja = QRadioButton("日本語")
        self._radio_ja.setStyleSheet("font-weight: bold; font-size: 14px;")
        lang_inner.addWidget(self._radio_ja)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_continue = QPushButton("  Continue / Weiter  ")
        btn_continue.setStyleSheet(
            "QPushButton { background-color: #615f8b; color: white; "
            "font-weight: bold; padding: 8px 24px; font-size: 14px; }"
            "QPushButton:hover { background-color: #7a78a5; }"
        )
        btn_continue.clicked.connect(self._on_lang_selected)
        btn_row.addWidget(btn_continue)
        lang_inner.addLayout(btn_row)

        self._lang_layout.addWidget(lang_box)
        self._lang_layout.addStretch()

    def _on_lang_selected(self):
        """Sprache setzen und zur Haupt-UI wechseln."""
        if self._radio_en.isChecked():
            set_language("en")
        elif self._radio_ja.isChecked():
            set_language("ja")
        else:
            set_language("de")

        # Sprachauswahl-UI komplett entfernen
        self._clear_layout(self._lang_layout)
        QWidget().setLayout(self.layout())  # Altes Layout loesen

        self.setWindowTitle(_t("mig_window_title"))
        self._build_ui()

    @staticmethod
    def _clear_layout(layout):
        """Entfernt alle Widgets und Sub-Layouts rekursiv."""
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                MigrationWindow._clear_layout(item.layout())

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # ===== QUELLSYSTEM-AUSWAHL =====
        self._source_box = QGroupBox(_t("mig_source_group"))
        source_select_layout = QVBoxLayout(self._source_box)

        info = QLabel(_t("mig_source_question"))
        info.setWordWrap(True)
        info.setStyleSheet("font-size: 14px; margin-bottom: 8px;")
        source_select_layout.addWidget(info)

        self._radio_cc10 = QRadioButton(_t("mig_source_cc10"))
        self._radio_cc10.setStyleSheet("font-weight: bold; font-size: 13px;")
        self._radio_cc10.setChecked(True)
        source_select_layout.addWidget(self._radio_cc10)
        cc10_desc = QLabel("    " + _t("mig_source_cc10_desc"))
        cc10_desc.setStyleSheet("color: #aaa; margin-bottom: 6px;")
        source_select_layout.addWidget(cc10_desc)

        self._radio_sqview = QRadioButton(_t("mig_source_sqview"))
        self._radio_sqview.setStyleSheet("font-weight: bold; font-size: 13px;")
        source_select_layout.addWidget(self._radio_sqview)
        sqview_desc = QLabel("    " + _t("mig_source_sqview_desc"))
        sqview_desc.setStyleSheet("color: #e8a020; font-style: italic; margin-bottom: 6px;")
        source_select_layout.addWidget(sqview_desc)

        self._radio_sdplayer = QRadioButton(_t("mig_source_sdplayer"))
        self._radio_sdplayer.setStyleSheet("font-weight: bold; font-size: 13px;")
        source_select_layout.addWidget(self._radio_sdplayer)
        sdplayer_desc = QLabel("    " + _t("mig_coming_soon"))
        sdplayer_desc.setStyleSheet("color: #888; font-style: italic; margin-bottom: 6px;")
        source_select_layout.addWidget(sdplayer_desc)

        # Weiter-Button
        btn_row_source = QHBoxLayout()
        btn_row_source.addStretch()
        self._btn_next = QPushButton("  " + _t("mig_btn_next") + "  ")
        self._btn_next.setStyleSheet(
            "QPushButton { background-color: #615f8b; color: white; "
            "font-weight: bold; padding: 8px 24px; font-size: 14px; }"
            "QPushButton:hover { background-color: #7a78a5; }"
        )
        self._btn_next.clicked.connect(self._on_source_selected)
        btn_row_source.addWidget(self._btn_next)
        source_select_layout.addLayout(btn_row_source)

        layout.addWidget(self._source_box)

        # ===== STACKED WIDGET: Konfigurations-Seiten =====
        self._config_stack = QStackedWidget()
        self._config_stack.setVisible(False)

        # -- Seite 0: CC 1.0 Konfiguration --
        self._cc10_page = QWidget()
        cc10_layout = QVBoxLayout(self._cc10_page)
        cc10_layout.setContentsMargins(0, 0, 0, 0)

        # Zurueck-Button
        back_row = QHBoxLayout()
        self._btn_back = QPushButton(_t("mig_btn_back"))
        self._btn_back.setFixedWidth(80)
        self._btn_back.clicked.connect(self._on_back)
        back_row.addWidget(self._btn_back)
        back_row.addStretch()
        cc10_layout.addLayout(back_row)

        # Quelle (CC 1.0)
        source_box = QGroupBox(_t("mig_source_cc10_group"))
        source_layout = QGridLayout(source_box)

        self._fields = {}
        rows = [
            ("mdb", _t("mig_field_mdb"), self._browse_mdb),
            ("songs1", _t("mig_field_songs_n", n=1), self._make_browse_songs(0)),
            ("songs2", _t("mig_field_songs_n", n=2), self._make_browse_songs(1)),
            ("songs3", _t("mig_field_songs_n", n=3), self._make_browse_songs(2)),
            ("songs4", _t("mig_field_songs_n", n=4), self._make_browse_songs(3)),
            ("lyrics", _t("mig_field_lyrics"), self._browse_lyrics),
            ("playlists", _t("mig_field_playlists"), self._browse_playlists),
            ("notes", _t("mig_field_notes"), self._browse_notes),
        ]
        for i, (key, label_text, browse_fn) in enumerate(rows):
            label = QLabel(label_text)
            edit = QLineEdit()
            edit.setReadOnly(True)
            edit.textChanged.connect(self._validate)
            btn = QPushButton("...")
            btn.setFixedWidth(32)
            btn.clicked.connect(browse_fn)
            source_layout.addWidget(label, i, 0)
            source_layout.addWidget(edit, i, 1)
            source_layout.addWidget(btn, i, 2)
            self._fields[key] = edit

        cc10_layout.addWidget(source_box)

        # Ziel (CC 1.0)
        target_box = QGroupBox(_t("mig_target_group"))
        target_layout = QGridLayout(target_box)

        label = QLabel(_t("mig_target_folder"))
        self._target_edit = QLineEdit()
        self._target_edit.setReadOnly(True)
        self._target_edit.textChanged.connect(self._validate)
        btn = QPushButton("...")
        btn.setFixedWidth(32)
        btn.clicked.connect(self._browse_target)
        target_layout.addWidget(label, 0, 0)
        target_layout.addWidget(self._target_edit, 0, 1)
        target_layout.addWidget(btn, 0, 2)

        # Zielordner vorbelegen wenn vom Installer uebergeben
        if self._preset_target:
            self._target_edit.setText(self._preset_target)

        cc10_layout.addWidget(target_box)

        # Status
        self._status_label = QLabel(_t("mig_status_choose"))
        self._status_label.setWordWrap(True)
        self._status_label.setStyleSheet(
            "padding: 8px; background: #363636; border-radius: 4px;"
        )
        cc10_layout.addWidget(self._status_label)

        # Migrieren-Button
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        self._btn_open_log = QPushButton(_t("mig_btn_open_log"))
        self._btn_open_log.setEnabled(False)
        self._btn_open_log.clicked.connect(self._open_log_file)
        btn_row.addWidget(self._btn_open_log)

        self._btn_migrate = QPushButton(_t("mig_btn_migrate"))
        self._btn_migrate.setProperty("confirm", True)
        self._btn_migrate.setStyleSheet(
            "QPushButton { background-color: #555; color: #999; "
            "font-weight: bold; padding: 8px 24px; font-size: 14px; }"
        )
        self._btn_migrate.setEnabled(False)
        self._btn_migrate.clicked.connect(self._on_migrate)
        btn_row.addWidget(self._btn_migrate)

        cc10_layout.addLayout(btn_row)

        # Log
        self._log = QTextEdit()
        self._log.setReadOnly(True)
        self._log.setMinimumHeight(200)
        self._log.setStyleSheet("font-family: monospace; font-size: 12px;")
        cc10_layout.addWidget(self._log)

        # Fortschritt
        self._progress = QProgressBar()
        self._progress.setVisible(False)
        cc10_layout.addWidget(self._progress)

        self._config_stack.addWidget(self._cc10_page)  # Index 0

        # -- Seite 1: "Kommt demnaechst" Platzhalter --
        self._coming_soon_page = QWidget()
        cs_layout = QVBoxLayout(self._coming_soon_page)
        cs_layout.setContentsMargins(0, 0, 0, 0)

        cs_back_row = QHBoxLayout()
        cs_btn_back = QPushButton(_t("mig_btn_back"))
        cs_btn_back.setFixedWidth(80)
        cs_btn_back.clicked.connect(self._on_back)
        cs_back_row.addWidget(cs_btn_back)
        cs_back_row.addStretch()
        cs_layout.addLayout(cs_back_row)

        self._coming_soon_label = QLabel()
        self._coming_soon_label.setAlignment(Qt.AlignCenter)
        self._coming_soon_label.setStyleSheet(
            "font-size: 18px; color: #888; padding: 60px;"
        )
        self._coming_soon_label.setWordWrap(True)
        cs_layout.addWidget(self._coming_soon_label)
        cs_layout.addStretch()

        self._config_stack.addWidget(self._coming_soon_page)  # Index 1

        # -- Seite 2: SqView Konfiguration --
        self._sqview_page = QWidget()
        sqv_layout = QVBoxLayout(self._sqview_page)
        sqv_layout.setContentsMargins(0, 0, 0, 0)

        # Zurueck-Button
        sqv_back_row = QHBoxLayout()
        sqv_btn_back = QPushButton(_t("mig_btn_back"))
        sqv_btn_back.setFixedWidth(80)
        sqv_btn_back.clicked.connect(self._on_back)
        sqv_back_row.addWidget(sqv_btn_back)
        sqv_back_row.addStretch()
        sqv_layout.addLayout(sqv_back_row)

        # Beta-Warnung
        warn_label = QLabel(_t("mig_sqv_beta_warning"))
        warn_label.setWordWrap(True)
        warn_label.setStyleSheet(
            "padding: 10px; background: #5c3a00; color: #ffd966; "
            "border: 1px solid #e8a020; border-radius: 4px; font-weight: bold;"
        )
        sqv_layout.addWidget(warn_label)

        # Quelle (SqView)
        sqv_source_box = QGroupBox(_t("mig_sqv_source_group"))
        sqv_source_layout = QGridLayout(sqv_source_box)

        self._sqv_fields = {}
        sqv_rows = [
            ("sqview_folder", _t("mig_sqv_field_folder"), self._browse_sqview_folder),
            ("sqview_db",     _t("mig_sqv_field_db"),     self._browse_sqview_db),
            ("sqv_music",     _t("mig_sqv_field_music"),  self._browse_sqv_music),
            ("sqv_lyrics",    _t("mig_sqv_field_lyrics"), self._browse_sqv_lyrics),
        ]
        for i, (key, label_text, browse_fn) in enumerate(sqv_rows):
            label = QLabel(label_text)
            edit = QLineEdit()
            edit.setReadOnly(True)
            edit.textChanged.connect(self._sqv_validate)
            btn = QPushButton("...")
            btn.setFixedWidth(32)
            btn.clicked.connect(browse_fn)
            sqv_source_layout.addWidget(label, i, 0)
            sqv_source_layout.addWidget(edit, i, 1)
            sqv_source_layout.addWidget(btn, i, 2)
            self._sqv_fields[key] = edit

        sqv_layout.addWidget(sqv_source_box)

        # Ziel (SqView)
        sqv_target_box = QGroupBox(_t("mig_target_group"))
        sqv_target_layout = QGridLayout(sqv_target_box)
        label = QLabel(_t("mig_target_folder"))
        self._sqv_target_edit = QLineEdit()
        self._sqv_target_edit.setReadOnly(True)
        self._sqv_target_edit.textChanged.connect(self._sqv_validate)
        btn = QPushButton("...")
        btn.setFixedWidth(32)
        btn.clicked.connect(self._browse_sqv_target)
        sqv_target_layout.addWidget(label, 0, 0)
        sqv_target_layout.addWidget(self._sqv_target_edit, 0, 1)
        sqv_target_layout.addWidget(btn, 0, 2)
        if self._preset_target:
            self._sqv_target_edit.setText(self._preset_target)
        sqv_layout.addWidget(sqv_target_box)

        # Status
        self._sqv_status_label = QLabel(_t("mig_status_choose"))
        self._sqv_status_label.setWordWrap(True)
        self._sqv_status_label.setStyleSheet(
            "padding: 8px; background: #363636; border-radius: 4px;"
        )
        sqv_layout.addWidget(self._sqv_status_label)

        # Migrieren-Button
        sqv_btn_row = QHBoxLayout()
        sqv_btn_row.addStretch()
        self._sqv_btn_open_log = QPushButton(_t("mig_btn_open_log"))
        self._sqv_btn_open_log.setEnabled(False)
        self._sqv_btn_open_log.clicked.connect(self._open_log_file)
        sqv_btn_row.addWidget(self._sqv_btn_open_log)
        self._sqv_btn_migrate = QPushButton(_t("mig_btn_migrate"))
        self._sqv_btn_migrate.setStyleSheet(
            "QPushButton { background-color: #555; color: #999; "
            "font-weight: bold; padding: 8px 24px; font-size: 14px; }"
        )
        self._sqv_btn_migrate.setEnabled(False)
        self._sqv_btn_migrate.clicked.connect(self._on_sqv_migrate)
        sqv_btn_row.addWidget(self._sqv_btn_migrate)
        sqv_layout.addLayout(sqv_btn_row)

        # Log
        self._sqv_log = QTextEdit()
        self._sqv_log.setReadOnly(True)
        self._sqv_log.setMinimumHeight(200)
        self._sqv_log.setStyleSheet("font-family: monospace; font-size: 12px;")
        sqv_layout.addWidget(self._sqv_log)

        # Fortschritt
        self._sqv_progress = QProgressBar()
        self._sqv_progress.setVisible(False)
        sqv_layout.addWidget(self._sqv_progress)

        self._config_stack.addWidget(self._sqview_page)  # Index 2

        layout.addWidget(self._config_stack)

    # ---- Seitennavigation ----

    def _on_source_selected(self):
        """Wechselt zur Konfigurationsseite des gewaehlten Quellsystems."""
        self._source_box.setVisible(False)
        self._config_stack.setVisible(True)

        if self._radio_cc10.isChecked():
            self._config_stack.setCurrentIndex(0)
            self._validate()
        elif self._radio_sqview.isChecked():
            self._config_stack.setCurrentIndex(2)
            self._sqv_validate()
        elif self._radio_sdplayer.isChecked():
            self._coming_soon_label.setText(
                _t("mig_coming_soon_detail", source="SDPlayer")
            )
            self._config_stack.setCurrentIndex(1)

    def _on_back(self):
        """Zurueck zur Quellsystem-Auswahl."""
        self._config_stack.setVisible(False)
        self._source_box.setVisible(True)

    # ---- Browse-Dialoge ----

    def _browse_mdb(self):
        path, _ = QFileDialog.getOpenFileName(
            self, _t("mig_browse_mdb"), "",
            _t("mig_filter_mdb")
        )
        if path:
            self._fields["mdb"].setText(path)
            self._auto_detect_folders(path)

    def _auto_detect_folders(self, mdb_path):
        """Versucht Standard-Ordner relativ zur MDB zu erkennen.

        Liest auch die CC1-INI-Datei (gleicher Ordner wie MDB) aus, um die
        konfigurierten Song-Pfade (PATH1-PATH4) zu ermitteln.
        """
        base = os.path.dirname(mdb_path)

        # --- CC1-INI lesen: Song-Pfade aus [SONGS] Sektion ---
        ini_song_dirs = self._read_cc1_ini_paths(base)

        # Songs: INI-Pfade auf songs1..songs4 verteilen
        # Zuerst alle Songs-Felder leeren
        for k in ["songs1", "songs2", "songs3", "songs4"]:
            self._fields[k].setText("")

        if ini_song_dirs:
            for idx, path in enumerate(ini_song_dirs[:4]):
                self._fields[f"songs{idx + 1}"].setText(path)
        else:
            # Fallback: Standard-Ordner in songs1
            for p in [os.path.join(base, "Songs", "ok"),
                      os.path.join(base, "Songs")]:
                if os.path.isdir(p):
                    self._fields["songs1"].setText(p)
                    break

        # Andere Ordner: Standard-Erkennung
        other_candidates = {
            "lyrics": [
                os.path.join(base, "Lyric"),
                os.path.join(base, "Lyrics"),
            ],
            "playlists": [
                os.path.join(base, "Playlists"),
                os.path.join(base, "Playlist"),
            ],
            "notes": [
                os.path.join(base, "notes"),
                os.path.join(base, "Notes"),
            ],
        }
        for key, paths in other_candidates.items():
            for p in paths:
                if os.path.isdir(p):
                    self._fields[key].setText(p)
                    break

    @staticmethod
    def _read_cc1_ini_paths(mdb_dir):
        """Liest Song-Pfade aus der CC1-INI-Datei (parallel zur MDB).

        Die INI hat eine [SONGS]-Sektion mit PATH1..PATH4.
        Gibt eine Liste existierender, eindeutiger Verzeichnisse zurueck.
        """
        # INI-Datei finden (CallersCaddy.ini oder aehnlich)
        ini_path = None
        for fname in os.listdir(mdb_dir):
            if fname.lower().endswith(".ini"):
                ini_path = os.path.join(mdb_dir, fname)
                break
        if not ini_path:
            return []

        try:
            cfg = configparser.ConfigParser()
            cfg.read(ini_path, encoding="utf-8")
        except Exception:
            try:
                cfg = configparser.ConfigParser()
                cfg.read(ini_path, encoding="latin-1")
            except Exception:
                return []

        if not cfg.has_section("SONGS"):
            return []

        seen = set()
        result = []
        for key in ["PATH1", "PATH2", "PATH3", "PATH4"]:
            val = cfg.get("SONGS", key, fallback="").strip()
            if not val:
                continue
            # Relative Pfade (z.B. "../Songs") relativ zum MDB-Ordner aufloesen
            if not os.path.isabs(val):
                val = os.path.join(mdb_dir, val)
            # Normalisieren (Trailing Backslash, ../ etc. aufloesen)
            norm = os.path.normpath(val)
            if norm in seen:
                continue
            if os.path.isdir(norm):
                seen.add(norm)
                result.append(norm)
        return result

    def _make_browse_songs(self, idx):
        """Factory fuer Browse-Buttons der 4 Songs-Pfade."""
        def _browse():
            d = QFileDialog.getExistingDirectory(self, _t("mig_browse_songs"))
            if d:
                self._fields[f"songs{idx + 1}"].setText(d)
        return _browse

    def _browse_lyrics(self):
        d = QFileDialog.getExistingDirectory(self, _t("mig_browse_lyrics"))
        if d:
            self._fields["lyrics"].setText(d)

    def _browse_playlists(self):
        d = QFileDialog.getExistingDirectory(self, _t("mig_browse_playlists"))
        if d:
            self._fields["playlists"].setText(d)

    def _browse_notes(self):
        d = QFileDialog.getExistingDirectory(self, _t("mig_browse_notes"))
        if d:
            self._fields["notes"].setText(d)

    def _browse_target(self):
        d = QFileDialog.getExistingDirectory(self, _t("mig_browse_target"))
        if d:
            self._target_edit.setText(d)

    # ---- Validierung ----

    def _validate(self):
        """Prueft alle Felder und aktualisiert Status + Button."""
        if not hasattr(self, "_status_label"):
            return  # UI noch nicht fertig aufgebaut
        lines = []
        ok = True

        # MDB (gecacht — wird nur bei Pfadaenderung neu gelesen)
        mdb = self._fields["mdb"].text()
        if mdb and os.path.isfile(mdb):
            try:
                if mdb != self._mdb_summary_path:
                    reader = MdbReader(mdb)
                    self._mdb_summary = reader.get_summary()
                    self._mdb_summary_path = mdb
                summary = self._mdb_summary
                lines.append(_t("mig_status_db_ok",
                    songs=summary['songs'],
                    groups=summary['groups'],
                    history=summary['history']))
            except Exception as e:
                lines.append(_t("mig_status_db_error", error=e))
                ok = False
        else:
            lines.append(_t("mig_status_db_missing"))
            ok = False

        # Songs (4 separate Pfadfelder)
        valid_dirs = []
        for k in ["songs1", "songs2", "songs3", "songs4"]:
            p = self._fields[k].text().strip()
            if p and os.path.isdir(p):
                valid_dirs.append(p)
        if valid_dirs:
            # MP3s zaehlen (Duplikate vermeiden)
            seen = set()
            for d in valid_dirs:
                for mp3 in glob.glob(os.path.join(d, "*.mp3")):
                    seen.add(os.path.basename(mp3).lower())
            mp3_count = len(seen)
            if len(valid_dirs) > 1:
                lines.append(_t("mig_status_songs_multi",
                    count=mp3_count, dirs=len(valid_dirs)))
            else:
                lines.append(_t("mig_status_songs_ok", count=mp3_count))
        else:
            lines.append(_t("mig_status_songs_missing"))
            ok = False

        # Lyrics (optional)
        lyrics_dir = self._fields["lyrics"].text()
        if lyrics_dir and os.path.isdir(lyrics_dir):
            lcount = len(os.listdir(lyrics_dir))
            lines.append(_t("mig_status_lyrics_ok", count=lcount))
        else:
            lines.append(_t("mig_status_lyrics_optional"))

        # Playlists (optional)
        pl_dir = self._fields["playlists"].text()
        if pl_dir and os.path.isdir(pl_dir):
            pcount = len(glob.glob(os.path.join(pl_dir, "*.txt")))
            lines.append(_t("mig_status_playlists_ok", count=pcount))
        else:
            lines.append(_t("mig_status_playlists_optional"))

        # Notes (optional)
        notes_dir = self._fields["notes"].text()
        if notes_dir and os.path.isdir(notes_dir):
            ncount = len(glob.glob(os.path.join(notes_dir, "*.txt")))
            lines.append(_t("mig_status_notes_ok", count=ncount))
        else:
            lines.append(_t("mig_status_notes_optional"))

        # Ziel
        target = self._target_edit.text()
        if target and os.path.isdir(target):
            lines.append(_t("mig_status_target_ok", path=target))
        else:
            lines.append(_t("mig_status_target_missing"))
            ok = False

        self._status_label.setText("\n".join(lines))

        # Button-Zustand
        self._btn_migrate.setEnabled(ok)
        if ok:
            self._btn_migrate.setStyleSheet(
                "QPushButton { background-color: #22c55e; color: white; "
                "font-weight: bold; padding: 8px 24px; font-size: 14px; }"
                "QPushButton:hover { background-color: #16a34a; }"
            )
        else:
            self._btn_migrate.setStyleSheet(
                "QPushButton { background-color: #555; color: #999; "
                "font-weight: bold; padding: 8px 24px; font-size: 14px; }"
            )

    # ---- SqView: Browse-Dialoge ----

    def _browse_sqview_folder(self):
        d = QFileDialog.getExistingDirectory(
            self, _t("mig_sqv_browse_folder")
        )
        if d:
            self._sqv_fields["sqview_folder"].setText(d)
            self._sqv_auto_detect_from_folder(d)

    def _sqv_auto_detect_from_folder(self, folder_path):
        """Erkennt sqview.db, Musik- und Lyrics-Ordner aus dem SqView-Ordner."""
        # 1. sqview.db suchen
        db_path = os.path.join(folder_path, "sqview.db")
        if os.path.isfile(db_path):
            self._sqv_fields["sqview_db"].setText(db_path)
            # Musik/Lyrics aus DB-INI lesen (ueberschreibt Felder)
            self._sqv_auto_detect(db_path)
        # 2. MP3-Ordner: Fallback wenn DB-INI keine Pfade liefert
        if not self._sqv_fields["sqv_music"].text():
            for candidate in ["MP3", "mp3", "music", "Music"]:
                mp3_dir = os.path.join(folder_path, candidate)
                if os.path.isdir(mp3_dir):
                    self._sqv_fields["sqv_music"].setText(mp3_dir)
                    break
        # 3. Lyrics-Ordner: Fallback
        if not self._sqv_fields["sqv_lyrics"].text():
            for candidate in ["text", "Text", "lyrics", "Lyrics"]:
                txt_dir = os.path.join(folder_path, candidate)
                if os.path.isdir(txt_dir):
                    self._sqv_fields["sqv_lyrics"].setText(txt_dir)
                    break

    def _browse_sqview_db(self):
        path, _ = QFileDialog.getOpenFileName(
            self, _t("mig_sqv_browse_db"), "",
            _t("mig_sqv_filter_db")
        )
        if path:
            self._sqv_fields["sqview_db"].setText(path)
            self._sqv_auto_detect(path)

    def _sqv_auto_detect(self, db_path):
        """Erkennt Musik- und Lyrics-Ordner aus der SqView-DB (via INI)."""
        try:
            reader = SqViewReader(db_path)
            music_dirs = reader.get_music_dirs()
            lyrics_dir = reader.get_lyrics_dir()
            reader.close()

            if music_dirs:
                self._sqv_fields["sqv_music"].setText(music_dirs[0])
            if lyrics_dir and os.path.isdir(lyrics_dir):
                self._sqv_fields["sqv_lyrics"].setText(lyrics_dir)
            else:
                # Fallback: text/ neben der DB
                text_dir = os.path.join(os.path.dirname(db_path), "text")
                if os.path.isdir(text_dir):
                    self._sqv_fields["sqv_lyrics"].setText(text_dir)
        except Exception:
            pass

    def _browse_sqv_music(self):
        d = QFileDialog.getExistingDirectory(self, _t("mig_browse_songs"))
        if d:
            self._sqv_fields["sqv_music"].setText(d)

    def _browse_sqv_lyrics(self):
        d = QFileDialog.getExistingDirectory(self, _t("mig_browse_lyrics"))
        if d:
            self._sqv_fields["sqv_lyrics"].setText(d)

    def _browse_sqv_target(self):
        d = QFileDialog.getExistingDirectory(self, _t("mig_browse_target"))
        if d:
            self._sqv_target_edit.setText(d)

    # ---- SqView: Validierung ----

    def _sqv_validate(self):
        """Prueft SqView-Felder und aktualisiert Status + Button."""
        if not hasattr(self, "_sqv_status_label"):
            return
        lines = []
        ok = True

        # sqview.db
        db_path = self._sqv_fields["sqview_db"].text()
        if db_path and os.path.isfile(db_path):
            try:
                reader = SqViewReader(db_path)
                s = reader.get_summary()
                reader.close()
                lines.append(_t("mig_sqv_status_db_ok",
                    songs=s["songs"], locations=s["locations"],
                    history=s["history"], lyrics=s["lyrics"]))
            except Exception as e:
                lines.append(_t("mig_status_db_error", error=e))
                ok = False
        else:
            lines.append(_t("mig_sqv_status_db_missing"))
            ok = False

        # Musik-Ordner (optional — ohne MP3s wird Blind-Import durchgefuehrt)
        music_dir = self._sqv_fields["sqv_music"].text()
        if music_dir and os.path.isdir(music_dir):
            # Rekursiv zaehlen (SqView hat Unterordner patter/, singer/ etc.)
            mp3_count = sum(
                1 for root, _, files in os.walk(music_dir)
                for f in files if f.lower().endswith(".mp3")
            )
            lines.append(_t("mig_status_songs_ok", count=mp3_count))
        else:
            lines.append(
                "\u26a0 Kein Musik-Ordner \u2014 Blind-Import "
                "(MP3s spaeter per Import-Funktion nachlieferbar)"
            )

        # Lyrics (optional)
        lyrics_dir = self._sqv_fields["sqv_lyrics"].text()
        if lyrics_dir and os.path.isdir(lyrics_dir):
            lcount = len(os.listdir(lyrics_dir))
            lines.append(_t("mig_status_lyrics_ok", count=lcount))
        else:
            lines.append(_t("mig_status_lyrics_optional"))

        # Ziel
        target = self._sqv_target_edit.text()
        if target and os.path.isdir(target):
            lines.append(_t("mig_status_target_ok", path=target))
        else:
            lines.append(_t("mig_status_target_missing"))
            ok = False

        self._sqv_status_label.setText("\n".join(lines))

        self._sqv_btn_migrate.setEnabled(ok)
        if ok:
            self._sqv_btn_migrate.setStyleSheet(
                "QPushButton { background-color: #22c55e; color: white; "
                "font-weight: bold; padding: 8px 24px; font-size: 14px; }"
                "QPushButton:hover { background-color: #16a34a; }"
            )
        else:
            self._sqv_btn_migrate.setStyleSheet(
                "QPushButton { background-color: #555; color: #999; "
                "font-weight: bold; padding: 8px 24px; font-size: 14px; }"
            )

    # ---- SqView: Migration starten ----

    def _on_sqv_migrate(self):
        if self._worker and self._worker.isRunning():
            return

        reply = QMessageBox.question(
            self, _t("mig_confirm_title"),
            _t("mig_sqv_confirm_msg"),
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        # BL-147: Kopieren/Verknuepfen + Wurzelverzeichnis abfragen
        choice = self._ask_copy_and_root(self._sqv_fields["sqv_music"].text())
        if choice is None:
            return
        copy_mode, music_root = choice

        self._sqv_log.clear()
        self._sqv_progress.setVisible(True)
        self._sqv_progress.setValue(0)
        self._sqv_btn_migrate.setEnabled(False)

        self._worker = SqViewWorker(
            sqview_db_path=self._sqv_fields["sqview_db"].text(),
            music_dir=self._sqv_fields["sqv_music"].text(),
            lyrics_dir=self._sqv_fields["sqv_lyrics"].text(),
            target_dir=self._sqv_target_edit.text(),
            copy_mode=copy_mode,
            music_root=music_root,
        )
        self._worker.progress.connect(self._on_sqv_progress)
        self._worker.log_msg.connect(self._on_sqv_log)
        self._worker.log_file.connect(self._on_log_file)
        self._worker.finished_ok.connect(self._on_sqv_done_ok)
        self._worker.finished_err.connect(self._on_sqv_done_err)
        self._worker.start()

    def _on_sqv_progress(self, current, total):
        if total > 0:
            self._sqv_progress.setMaximum(total)
            self._sqv_progress.setValue(current)

    def _on_sqv_log(self, msg):
        self._sqv_log.append(msg)

    def _on_sqv_done_ok(self, summary):
        self._sqv_log.append(summary)
        self._sqv_progress.setValue(self._sqv_progress.maximum())
        self._sqv_btn_migrate.setEnabled(True)
        QMessageBox.information(self, _t("mig_done_title"), _t("mig_done_msg"))

    def _on_sqv_done_err(self, error_msg):
        self._sqv_log.append(f"\n\u274c {error_msg}")
        self._sqv_progress.setVisible(False)
        self._sqv_btn_migrate.setEnabled(True)
        QMessageBox.critical(self, _t("mig_error_title"), error_msg)

    # ---- Gemeinsame Abfrage: Kopieren/Verknuepfen + Wurzel (BL-147) ----

    def _ask_copy_and_root(self, default_root: str):
        """Fragt Kopieren vs. Verknuepfen und das Wurzelverzeichnis ab.

        Returns (copy_mode: bool, music_root: str) oder None bei Abbruch.
        """
        dlg = QMessageBox(self)
        dlg.setWindowTitle(_t("mig_copy_title"))
        dlg.setText(_t("mig_copy_text"))
        dlg.setIcon(QMessageBox.Question)
        btn_copy = dlg.addButton(_t("mig_copy_btn_copy"), QMessageBox.ActionRole)
        btn_link = dlg.addButton(_t("mig_copy_btn_link"), QMessageBox.ActionRole)
        dlg.addButton(QMessageBox.Cancel)
        dlg.setDefaultButton(btn_copy)
        dlg.exec()
        clicked = dlg.clickedButton()
        if clicked == btn_copy:
            copy_mode = True
        elif clicked == btn_link:
            copy_mode = False
        else:
            return None  # Abbruch

        # Wurzelverzeichnis waehlen (vorbefuellt mit dem ersten Quellordner)
        QMessageBox.information(self, _t("mig_root_title"), _t("mig_root_prompt"))
        start_dir = default_root if (default_root and os.path.isdir(default_root)) else ""
        music_root = QFileDialog.getExistingDirectory(
            self, _t("mig_root_title"), start_dir)
        if not music_root:
            # Auswahl abgebrochen -> auf Standard (erster Quellordner) zurueckfallen
            music_root = default_root
        return copy_mode, music_root

    # ---- CC 1.0: Migration starten ----

    def _on_migrate(self):
        if self._worker and self._worker.isRunning():
            return

        # Sicherheitsabfrage
        reply = QMessageBox.question(
            self, _t("mig_confirm_title"),
            _t("mig_confirm_msg"),
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        # Song-Pfade aus den 4 Feldern sammeln
        songs_dirs = []
        for k in ["songs1", "songs2", "songs3", "songs4"]:
            p = self._fields[k].text().strip()
            if p and os.path.isdir(p):
                songs_dirs.append(p)

        # BL-147: Kopieren/Verknuepfen + Wurzelverzeichnis abfragen
        choice = self._ask_copy_and_root(songs_dirs[0] if songs_dirs else "")
        if choice is None:
            return
        copy_mode, music_root = choice

        self._log.clear()
        self._progress.setVisible(True)
        self._progress.setValue(0)
        self._btn_migrate.setEnabled(False)

        self._worker = MigrationWorker(
            mdb_path=self._fields["mdb"].text(),
            songs_dirs=songs_dirs,
            lyrics_dir=self._fields["lyrics"].text(),
            playlists_dir=self._fields["playlists"].text(),
            notes_dir=self._fields["notes"].text(),
            target_dir=self._target_edit.text(),
            copy_mode=copy_mode,
            music_root=music_root,
        )
        self._worker.progress.connect(self._on_progress)
        self._worker.log_msg.connect(self._on_log)
        self._worker.log_file.connect(self._on_log_file)
        self._worker.finished_ok.connect(self._on_done_ok)
        self._worker.finished_err.connect(self._on_done_err)
        self._worker.start()

    # ---- Detaillog ----

    def _on_log_file(self, path):
        """Worker hat das Detaillogfile angelegt — Buttons aktivieren."""
        self._log_path = path
        self._btn_open_log.setEnabled(True)
        self._sqv_btn_open_log.setEnabled(True)

    def _open_log_file(self):
        if self._log_path and os.path.isfile(self._log_path):
            os.startfile(self._log_path)

    def _on_progress(self, current, total):
        if total > 0:
            self._progress.setMaximum(total)
            self._progress.setValue(current)

    def _on_log(self, msg):
        self._log.append(msg)

    def _on_done_ok(self, summary):
        self._log.append(summary)
        self._progress.setValue(self._progress.maximum())
        self._btn_migrate.setEnabled(True)
        QMessageBox.information(self, _t("mig_done_title"), _t("mig_done_msg"))

    def _on_done_err(self, error_msg):
        self._log.append(f"\n\u274c {error_msg}")
        self._progress.setVisible(False)
        self._btn_migrate.setEnabled(True)
        QMessageBox.critical(self, _t("mig_error_title"), error_msg)


# ===========================================================================

def main():
    app = QApplication(sys.argv)

    # Sprache aus Kommandozeile (--lang de|en) oder System-Locale
    lang = None
    target_dir = None
    args = sys.argv[1:]
    i = 0
    while i < len(args):
        if args[i] == "--lang" and i + 1 < len(args):
            lang = args[i + 1]
            i += 2
        elif not args[i].startswith("--"):
            target_dir = args[i]
            i += 1
        else:
            i += 1

    # Wenn --lang gesetzt, Sprache direkt setzen (ueberspringt Sprachauswahl)
    if lang:
        set_language(lang)

    # Dunkles Basis-Styling (standalone, ohne Skin-System)
    app.setStyleSheet("""
        QWidget {
            background-color: #2b2b2b;
            color: #f0f0f0;
            font-size: 13px;
        }
        QGroupBox {
            font-weight: bold;
            border: 1px solid #555;
            border-radius: 4px;
            margin-top: 12px;
            padding-top: 16px;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            left: 10px;
            padding: 0 4px;
        }
        QRadioButton::indicator {
            width: 16px;
            height: 16px;
            border: 2px solid #888;
            border-radius: 10px;
            background-color: #404040;
        }
        QRadioButton::indicator:checked {
            border: 2px solid #22c55e;
            background-color: #22c55e;
        }
        QRadioButton::indicator:hover {
            border: 2px solid #aaa;
        }
        QLineEdit {
            background-color: #404040;
            border: 1px solid #555;
            border-radius: 3px;
            padding: 4px;
        }
        QPushButton {
            background-color: #615f8b;
            color: #f7f7f7;
            border: none;
            border-radius: 3px;
            padding: 4px 12px;
        }
        QPushButton:hover {
            background-color: #7a78a5;
        }
        QPushButton:disabled {
            background-color: #444;
            color: #777;
        }
        QTextEdit {
            background-color: #1e1e1e;
            border: 1px solid #555;
            border-radius: 3px;
        }
        QProgressBar {
            border: 1px solid #555;
            border-radius: 3px;
            text-align: center;
            background-color: #404040;
        }
        QProgressBar::chunk {
            background-color: #22c55e;
            border-radius: 2px;
        }
    """)

    window = MigrationWindow(target_dir=target_dir, lang=lang)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
