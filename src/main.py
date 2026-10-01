"""Callers Caddy — Musik-Player fuer Square Dance Caller."""

__version__ = "0.159"

import sys
import os
import perf
from perf import perf_start, perf_log, perf_split

# --- Startup-Perf: fruehester Messpunkt (VOR den schweren Imports) -----------
# Erfasst die zwei bisher blinden Phasen VOR main():
#   1. Bootloader + Python-Init: Prozess-Erstellung -> dieser Punkt
#   2. Import-Phase: dieser Punkt -> main()-Start (schwere PySide6/Audio-Imports)
# Bewusst hier oben, noch vor dem PySide6-Import-Block, sonst waere die
# teuerste Phase (Qt/Audio-DLLs laden) selbst nicht messbar.
import time as _startup_time
_T_MODULE_TOP_PERF = _startup_time.perf_counter()
_T_MODULE_TOP_WALL = _startup_time.time()

_T_PROCESS_CREATE_EPOCH = perf.process_create_epoch()

import re
import json
import math
import shutil
import threading
import random
import struct
from time import monotonic
from datetime import date, datetime
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QHBoxLayout,
    QVBoxLayout,
    QPushButton,
    QLabel,
    QFileDialog,
    QDockWidget,
    QCheckBox,
    QListWidget,
    QTableWidget,
    QComboBox,
    QMessageBox,
    QDialog,
    QDialogButtonBox,
    QInputDialog,
    QAbstractItemView,
    QTextBrowser,
    QSizePolicy,
    QProgressDialog,
)
from PySide6.QtCore import Qt, QTimer, QSettings, QThread, Signal, QEvent, QObject, QRect
from PySide6.QtGui import QIcon, QKeySequence, QShortcut, QCursor

# --- Frühest möglicher Crash-Handler -----------------------------------------
# MUSS vor den lokalen Imports stehen (audio_engine/bpm_detector/loop_finder
# laden native Audio-DLLs). Schlägt einer dieser Imports fehl, war bisher KEIN
# Crash-Log möglich — der Absturz passiert schon hier beim Modul-Import, lange
# bevor main() den Handler installierte. Jetzt fängt der excepthook auch
# Import-Abstürze ab und schreibt ein Logfile. crash_handler ist reines stdlib
# (kein Qt nötig); setup() ist idempotent und wird in main() erneut aufgerufen.
import crash_handler as _crash_handler
_crash_handler.setup(
    os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.getcwd()
)

# --- Windows-on-ARM: PortAudio-Architektur korrigieren (TIC-0028, Ursache B) -
# Wir liefern nur die x64-PortAudio-DLL. Laeuft Callers Caddy als x64-Build unter
# der x64-Emulation von Windows-on-ARM (z.B. Parallels auf Apple Silicon), meldet
# platform.machine() via der Env-Var PROCESSOR_ARCHITEW6432 faelschlich 'ARM64'.
# sounddevice (0.5.x) sucht dann die nicht vorhandene libportaudioarm64.dll und
# stuerzt mit OSError 0x7e (ERROR_MOD_NOT_FOUND) ab. Entfernen wir die Var, faellt
# platform.machine() auf PROCESSOR_ARCHITECTURE ('AMD64') zurueck -> die gebundelte
# x64-DLL wird geladen und laeuft unter der Emulation. No-op auf nativem x64 (Var
# dort nicht gesetzt). MUSS vor dem ersten sounddevice-Import stehen (audio_engine
# und settings_dialog importieren sounddevice).
if sys.platform == "win32" \
        and os.environ.get("PROCESSOR_ARCHITEW6432", "").upper() == "ARM64" \
        and os.environ.get("PROCESSOR_ARCHITECTURE", "").upper() == "AMD64":
    os.environ.pop("PROCESSOR_ARCHITEW6432", None)

# --- Single-Instance-Guard — so FRUEH wie moeglich (VOR den schweren Imports) -
# Warum hier oben und nicht in main(): die teuren Imports (bpm_detector ~1.3s,
# audio_engine/PortAudio, numpy) laufen bereits beim Modul-Import, also VOR main().
# Frueher sass der Lock erst tief in main() — ein ungeduldiger zweiter Doppelklick
# ("dauert zu lange, klick nochmal") zahlte dadurch ~2.8s vollen Start, bevor er
# "laeuft bereits" merkte, und stahl der ersten Instanz CPU/Disk in ihrer
# kritischsten Startphase. An dieser Stelle sind nur stdlib + PySide6 (fuer
# QLockFile) geladen -> die zweite Instanz bricht in ~0.2s ab.
# Braucht KEIN QApplication (verifiziert: QLockFile + QStandardPaths.TempLocation
# funktionieren ohne). Meldung per nativer WinAPI-MessageBox, damit die zweite
# Instanz nicht mal QtWidgets/QApplication hochfahren muss.
_LOCK_FILE = None  # Modul-global: haelt den Lock ueber die gesamte Laufzeit

def _acquire_single_instance_lock():
    """Versucht den exklusiven Lock. Gibt das QLockFile zurueck (Erfolg) oder
    None, wenn bereits eine Instanz laeuft."""
    from PySide6.QtCore import QLockFile, QStandardPaths
    import hashlib
    # Lock-Datei NICHT ins Installationsverzeichnis: C:\Program Files\ ist fuer
    # normale Nutzer nicht schreibbar -> QLockFile meldete sonst faelschlich
    # "laeuft bereits". Stattdessen nutzer-schreibbares TEMP; der App-Verzeichnis-
    # Hash trennt zwei getrennte (portable) Installationen voneinander.
    lock_app_dir = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.getcwd()
    lock_tag = hashlib.md5(
        os.path.abspath(lock_app_dir).encode("utf-8", "replace")).hexdigest()[:8]
    lock_base = QStandardPaths.writableLocation(
        QStandardPaths.TempLocation) or lock_app_dir
    lock = QLockFile(os.path.join(lock_base, f"callers_caddy_{lock_tag}.lock"))
    # staleLockTime(0): KEIN zeitbasiertes Auto-Stehlen — die App laeuft im
    # Live-Betrieb stundenlang. Verwaiste Locks (nach Absturz/Reboot) raeumen wir
    # gezielt via removeStaleLockFile() weg (prueft, ob der Besitzer-Prozess noch
    # lebt), dann zweiter Sperrversuch.
    lock.setStaleLockTime(0)
    if not lock.tryLock(500):
        if not lock.removeStaleLockFile() or not lock.tryLock(500):
            return None
    return lock

def _warn_already_running_and_exit():
    """Zweite Instanz: Doppelklick-Kosten protokollieren, native Warnung, raus."""
    # Doppelklick-Messung: wie viel hat diese verschwendete 2. Instanz verbrannt?
    # (Sollte jetzt winzig sein — genau das wollten wir erreichen.)
    try:
        if _T_PROCESS_CREATE_EPOCH is not None:
            wasted_ms = (_startup_time.time() - _T_PROCESS_CREATE_EPOCH) * 1000.0
            base = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.getcwd()
            d = os.path.join(base, "logs", "perf")
            os.makedirs(d, exist_ok=True)
            ts = _startup_time.strftime("%H:%M:%S", _startup_time.localtime())
            with open(os.path.join(d, "second_instance.log"), "a", encoding="utf-8") as f:
                f.write(f"{ts} 2. Instanz (Doppelklick) verschwendet "
                        f"bis Lock-Erkennung: {wasted_ms:.0f}ms\n")
    except Exception:
        pass
    msg = "Callers Caddy läuft bereits.\n\nCallers Caddy is already running."
    try:
        import ctypes
        # MB_OK | MB_ICONWARNING | MB_SETFOREGROUND
        ctypes.windll.user32.MessageBoxW(0, msg, "Callers Caddy", 0x30 | 0x10000)
    except Exception:
        print(msg)
    sys.exit(0)

_LOCK_FILE = _acquire_single_instance_lock()
if _LOCK_FILE is None:
    _warn_already_running_and_exit()

from audio_engine import ALERT_IDLE_SR, AudioEngine
from system_report import generate_report
from song_db import SongDatabase, Song, Location
from path_manager import PathManager
from skin_manager import SkinManager
from settings_dialog import SettingsDialog
from i18n import _t, set_language, get_language, get_available_languages
from tutorial_engine import TutorialEngine
from tutorial_definitions import TUTORIALS
from notes_widget import NotesWidget
from stats_widget import StatsWidget
from evening_planner_widget import EveningPlannerWidget
import zip_import
import song_catalog
import song_match
from zip_import_dialog import ZipImportPreviewDialog, ask_split as ask_zip_split


# _ComboClickToOpen / install_combo_click_to_open -> sequences_widget.py (BL-201)




class _ZipAnalyzeWorker(QThread):
    """Entpackt + analysiert Label-ZIPs im Hintergrund (Audio-Prioritaet, eiserne Regel).

    Perf-Marken werden gesammelt und nach Fertigstellung im Main-Thread geloggt,
    damit keine Datei-Schreibzugriffe aus dem Worker noetig sind.
    """
    done = Signal(object, object)   # (AnalysisResult, marks: list[(label, seconds)])
    failed = Signal(str)

    def __init__(self, zip_paths, lists):
        super().__init__()
        self._zip_paths = zip_paths
        self._lists = lists

    def run(self):
        marks = []
        try:
            result = zip_import.analyze(
                self._zip_paths, lists=self._lists,
                perf_cb=lambda label, secs: marks.append((label, secs)),
            )
            self.done.emit(result, marks)
        except Exception as e:  # noqa: BLE001 — Fehler an UI melden
            self.failed.emit(str(e))


# --- Performance-/Startup-Logging: ausgelagert nach perf.py (BL-201) ---
# Aufrufe laufen ueber perf.* bzw. die oben importierten perf_start/log/split.


# --- Hilfsfunktionen ---

# --- Hilfsfunktionen + UI-Helfer: ausgelagert nach ui_helpers.py (BL-201) ---
from shortcut_policy import is_text_input, space_should_fire
from ui_helpers import (
    fmt_time,
    fmt_precise,
    parse_time_offset,
    show_loop_count_dialog,
    _make_icon,
    _SVG_MAGNET,
    _make_dock,
    _PlayBarrier,
    _WrapButtonBar,
    SectionBarWidget,
    _reco_days_since,
    _weighted_random_order,
    _style_date_cell,
    _UNRATED_QUALITY,
    opens_combo_popup,
    widen_combo_popup,
)


# ===========================================================================
# Lokation-Auswahl-Dialog
# ===========================================================================

# --- Lokation/Programm/Genre-Dialoge -> dialogs_location_program.py (BL-201, Stufe 12)
from dialogs_location_program import (
    LocationDialog, _DanceProgramManagerDialog, _MultiProgramPickerDialog,
    _GenreManagerDialog, _ImportGenreDialog, DeduplicationDialog,
)
# --- Call-Map Export/Import mit Konfliktklaerung (intern#79)
import mapping_io
from dialogs_mapping_conflict import run_mapping_import


# ===========================================================================
# Singing-Call-Abschnitte (7-Segment-Leiste)
# ===========================================================================



# ===========================================================================
# Start-Countdown-Overlay
# ===========================================================================

# --- Player-UI -> player_widget.py (BL-201, Stufe 6) -----------------------
# SectionBarWidget wanderte nach ui_helpers (auch von LoopFinder genutzt).
from player_widget import (
    PlayerWidget, LoopWidget, _StatusBarPlayerBar, _CountdownOverlay,
)


# ===========================================================================
# Status-Leiste — Miniatur-Abspielfortschritt (BL-128)
# ===========================================================================



# ===========================================================================
# Player-Modul
# ===========================================================================

# Transport-/Icon-SVGs + _make_icon -> ui_helpers.py (BL-201)


# _WrapButtonBar -> ui_helpers.py (BL-201)






# ===========================================================================
# Loop-Modul
# ===========================================================================





# ===========================================================================
# Song-Daten-Modul
# ===========================================================================

# --- Song-Daten/Filter/Liste -> songdata_widget.py (BL-201, Stufe 7) -------
# _reco_*/_weighted_random_order/_style_date_cell -> ui_helpers.py
from songdata_widget import BpmWorker, FeedbackDialog, SongDataWidget, SongListWidget




class SingingBodyWorker(QThread):
    """Worker-Thread fuer die automatische Singing-Body-Erkennung (Anfang/Ende).

    Laeuft off-main-thread wie BpmWorker/LoopFinderWorker (Audio-Prioritaet).
    Liefert das Ergebnis-dict von detect_singing_body per 'done'-Signal.
    """
    done = Signal(object)      # Ergebnis-dict
    error = Signal(str)

    def __init__(self, filepath: str, bpm_hint: float = None):
        super().__init__()
        self._filepath = filepath
        self._bpm_hint = bpm_hint

    def run(self):
        try:
            from singing_body_detect import detect_singing_body
            result = detect_singing_body(self._filepath, bpm_hint=self._bpm_hint)
            self.done.emit(result)
        except Exception as e:
            self.error.emit(str(e))










# ===========================================================================
# Songliste-Modul
# ===========================================================================





# _UNRATED_QUALITY -> ui_helpers.py (BL-201, Stufe 7)










# ===========================================================================
# Playlist-Modul (schlanke Ansicht — getabbt mit Songliste)
# ===========================================================================

# --- Playlist-UI -> playlist_widget.py (BL-201, Stufe 8) -------------------
from playlist_widget import (
    PlaylistWidget, PlaylistManagerWidget, PlaylistEntry,
)


# ===========================================================================
# Drag & Drop Tabellen-Subklassen
# ===========================================================================







# ===========================================================================
# Custom-Filter-Dialog (Playlisten als Whitelist)
# ===========================================================================



# ===========================================================================
# Playlist-Manager (Zwei-Panel — eigenes Dock)
# ===========================================================================



# ===========================================================================
# Sequenzen-Anzeige (NEU in P28)
# ===========================================================================


# --- Sequenzen-UI -> sequences_widget.py (BL-201, Stufe 4) ------------------
from sequences_widget import (
    SequenceViewWidget, SequencesWidget, SequenceEditorDialog,
    SequenceImportDialog, CallMappingDialog,
)




# ===========================================================================
# Deduplizierungs-Dialog
# ===========================================================================






















# ===========================================================================
# Lyrics-Anzeige (NEU in P26)
# ===========================================================================


# Lyric-Abschnitte + LyricsWidget -> lyrics_widget.py (BL-201, Stufe 3)
from lyrics_widget import LyricsWidget


# ===========================================================================
# Hauptfenster
# ===========================================================================

# _make_dock -> ui_helpers.py (BL-201)


# --- Reports-UI -> reports_widget.py (BL-201, Stufe 11) --------------------
from reports_widget import ReportsWidget


# --- Potential-/Song-Pool-UI -> potential_widget.py (BL-201, Stufe 5) ------
# (inkl. Bulk-Worker, Meta-Import/CSV-Match, Ceder-, Krabbelkiste- und
#  Beautify-Dialoge; _ReindexWorker bleibt hier in main.)
from potential_widget import PotentialWidget




















class _ReindexWorker(QThread):
    """BL-147: Indexiert alle Musik-Slots rekursiv und hebt Songs mit blossem
    Dateinamen auf den passenden relativen Pfad (kanonisch '/').

    First come first serve: Slots werden in Reihenfolge 1→N durchsucht; der
    relative Pfad wird gegen den ersten geeigneten Slot gebildet. Mehrere
    physische Dateien gleichen Namens mit UNTERSCHIEDLICHEM relativem Pfad
    sind mehrdeutig und werden NICHT automatisch zugeordnet (nie raten).
    """
    progress = Signal(str)                 # aktuell gescannter Slot-Pfad
    # updates: [(song_id, relpath)], ambiguous: [(song_id, basename, [relpaths])], still_missing: int
    finished = Signal(list, list, int)

    def __init__(self, songs, music_dirs, parent=None):
        """songs: list of (song_id, filename); music_dirs: Slots in Prioritaet."""
        super().__init__(parent)
        self._songs = songs
        self._music_dirs = music_dirs
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        import os as _os
        audio_exts = (".mp3", ".wav", ".flac", ".ogg", ".aiff", ".aif",
                      ".au", ".caf", ".w64")
        # 1) Index aufbauen: basename_lower -> set of relpath_posix
        #    Slots in Reihenfolge -> der erste Slot, der einen Treffer liefert,
        #    bestimmt den relativen Pfad (First come first serve).
        index = {}
        for base in self._music_dirs:
            if self._cancelled:
                return
            if not base or not _os.path.isdir(base):
                continue
            base_n = _os.path.normpath(base)
            self.progress.emit(base_n)
            for root, _dirs, files in _os.walk(base_n):
                for f in files:
                    if f.lower().endswith(audio_exts):
                        rel = _os.path.relpath(_os.path.join(root, f), base_n)
                        index.setdefault(f.lower(), {})[rel.replace("\\", "/")] = True
        # 2) Songs zuordnen
        updates = []
        ambiguous = []
        still_missing = 0
        for song_id, filename in self._songs:
            if self._cancelled:
                return
            # Songs mit bereits relativem Pfad ueberspringen — schon erledigt.
            if "/" in filename or "\\" in filename:
                continue
            distinct = sorted(index.get(filename.lower(), {}).keys())
            if not distinct:
                still_missing += 1
            elif len(distinct) == 1:
                rel = distinct[0]
                if rel != filename:    # nur echte Verbesserung (liegt im Unterordner)
                    updates.append((song_id, rel))
                # rel == filename: liegt bereits im Slot-Root -> nichts zu tun
            else:
                ambiguous.append((song_id, filename, distinct))
        self.finished.emit(updates, ambiguous, still_missing)


# Exportierbare Felder fuer Metadaten-Anreicherung (BL-114)
# (key, DE-Label, source_type)  source_type: 'songs_field' | 'property' | 'genre'






























_BASE_TITLE = f"Callers Caddy v{__version__}"
_VERSION = __version__

# Layout-Version: Hochzaehlen wenn sich die Dock-Zusammensetzung aendert
# (Docks hinzugefuegt/entfernt/umbenannt). Qt's restoreState() ignoriert
# dann den alten State statt das Docking-System zu korrumpieren.
# ---------------------------------------------------------------------------
# Loop Finder Widget
# ---------------------------------------------------------------------------

# --- Loop-Finder-UI -> loopfinder_widget.py (BL-201, Stufe 9) --------------
from loopfinder_widget import LoopFinderWidget, LoopFinderWorker






# ================================================================
#  Break-Timer — Pausen-Uhr (Countdown + Fortschrittsbalken)
# ================================================================

# --- Pause/Foto -> break_photo_widget.py (BL-201, Stufe 10) ----------------
from break_photo_widget import BreakWidget, PhotoWidget




# ================================================================
#  PhotoWidget (BL-041) — Kamera-Foto vom PilotSquare
# ================================================================



# Keyword-Mapping fuer automatische Genre-Vorschlaege beim Import
# Schluessel: Teilstring (lowercase) in Dateiname → Genre-Name in DB
_GENRE_IMPORT_KEYWORDS = {
    "christmas": "Christmas", "xmas": "Christmas",
    "halloween": "Halloween",
    "disco": "Disco",
    "gospel": "Gospel",
    "patriotic": "Patriotic",
    "summer": "Summer",
    "winter": "Winter",
    "holiday": "Holiday",
    "broadway": "Broadway",
    "cajun": "Cajun",
    "bluegrass": "Bluegrass",
    "irish": "Irish",
    "jazz": "Jazz",
    "blues": "Blues",
    "latin": "Latin",
    "motown": "Motown",
    "disney": "Disney",
    "valentine": "Love / Valentine",
    "calledms": "Called MS", "called ms": "Called MS",
    "calledplus": "Called Plus", "called plus": "Called Plus",
    "calleda1": "Called A1", "called a1": "Called A1",
    "calleda2": "Called A2", "called a2": "Called A2",
}






# ---------------------------------------------------------------------------
# BL-084 / BL-086: Lokation-Einstellungen (Tanzprogramm + temp. Tempo)
# ---------------------------------------------------------------------------



# BL-083: Tanzprogramm-Dialoge
# ---------------------------------------------------------------------------











# Historie: 1 = P30, 2 = P31, 3 = P33, 4 = P36 (dock_loop_finder)
_LAYOUT_VERSION = 6


# _PlayBarrier -> ui_helpers.py (BL-201)


class P29MainWindow(QMainWindow):
    """Sequenzen-Hauptfenster (basiert auf P27).

    Zusaetzlich zu P27:
      - Sequenzen-Widget (dockbar, getabbt mit Lyrics)
      - MDB-Import + Cached Live-Mapping
    """

    # Rule-Aktionen, die beim Play/Resume den hoerbaren Audio-Start
    # zurueckhalten muessen (Layout-GIL-Block bzw. asynchroner Worker).
    # Siehe _PlayBarrier / _orchestrate_play.
    _PLAY_GATE_ACTIONS = {
        "layout_load",             # restoreState (~75 ms, deferred)
        "dual_view",               # setFloating/setGeometry (synchron)
        "dual_view_toggle",        # saveState+restoreState (~105 ms, deferred)
        "dual_view_close",         # setFloating(False) (synchron)
        "sequenceview_maximize",   # setFloating/setGeometry (synchron)
        "auto_set_best_loop",      # Loop-Finder-Worker (asynchron)
    }

    # Media-/Fn-Tasten: kein event.text() verfuegbar, Abfang per key_code
    _MEDIA_KEY_TRIGGERS = {
        Qt.Key.Key_VolumeUp:          "key_volume_up",
        Qt.Key.Key_VolumeDown:        "key_volume_down",
        Qt.Key.Key_VolumeMute:        "key_volume_mute",
        Qt.Key.Key_MediaPlay:         "key_media_play",
        Qt.Key.Key_MediaStop:         "key_media_stop",
        Qt.Key.Key_MediaNext:         "key_media_next",
        Qt.Key.Key_MediaPrevious:     "key_media_prev",
        Qt.Key.Key_MonBrightnessUp:   "key_brightness_up",
        Qt.Key.Key_MonBrightnessDown: "key_brightness_down",
    }

    def __init__(self, skin_mgr: SkinManager = None):
        _t0 = perf_start()
        super().__init__()
        self.setWindowTitle(_BASE_TITLE)
        # Hoehe muss die Summe der vertikal gestapelten Dock-Mindesthoehen
        # aufnehmen (Player 350 + Loop 240 + Title-Bars + Menu + Status ~= 720),
        # sonst quetscht das MainWindow die unteren Player-Buttons ab (TIC-0014).
        self.setMinimumSize(1100, 720)

        # App-Icon setzen (Taskleiste + Titelleiste)
        icon_path = os.path.join(
            os.path.dirname(sys.executable) if getattr(sys, 'frozen', False)
            else os.getcwd(), "cc-logo.png"
        )
        if os.path.isfile(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        # Docking-Optionen: Tabs erlauben + verschachteltes Docking + Animation
        # AllowTabbedDocks: Fenster koennen als Registerkarten gestapelt werden
        #   (spaeter nuetzlich fuer Lyrics + Sequenzen im gleichen Bereich)
        # AllowNestedDocks: Fenster koennen innerhalb bestehender Bereiche
        #   verschachtelt werden (flexibleres Layout)
        self.setDockOptions(
            QMainWindow.AnimatedDocks
            | QMainWindow.AllowTabbedDocks
            | QMainWindow.AllowNestedDocks
        )

        # App-Verzeichnis (PyInstaller: neben EXE, Dev: CWD = 2_Test/)
        if getattr(sys, 'frozen', False):
            self._app_dir = os.path.dirname(sys.executable)
        else:
            self._app_dir = os.getcwd()

        # INI-Datei fuer Layout-Persistenz + Pfade
        ini_path = os.path.join(self._app_dir, "callers_caddy.ini")
        self._settings = QSettings(ini_path, QSettings.IniFormat)

        # MS50: session-globale Tanzprogramm-Wahl (Programm-IDs) aus INI laden.
        # Steuert den Sequenz-Filter; eine gewaehlte Lokation ueberschreibt sie.
        self._session_program_ids = self._parse_program_ids(
            self._settings.value("sequences/dance_programs", ""))

        # PathManager (zentrale Pfadverwaltung)
        self.paths = PathManager(self._settings)
        self.paths.ensure_directories()

        # SkinManager: Ressourcen (QSS/SVG) liegen neben main.py, nicht im CWD
        # Im EXE-Modus ist app_dir = neben der EXE (gleicher Pfad), kein Unterschied.
        if getattr(sys, 'frozen', False):
            _skin_res_dir = self._app_dir
        else:
            _skin_res_dir = os.path.dirname(os.path.abspath(__file__))
        self.skin_mgr = skin_mgr or SkinManager(_skin_res_dir)

        # Geteilte Audio-Engine
        self.engine = AudioEngine()

        # Song-Datenbank (Pfad aus PathManager)
        self.db = SongDatabase(self.paths.db_path)
        self.db.seed_default_genres()
        # intern#106: Doppelgaenger von Unterordner-Songs (Bug bis v0.158)
        # in ihr Original zurueckfuehren. Laeuft bei jedem Start (eine Abfrage),
        # damit auch Songs auf beim ersten Start nicht erreichbaren Laufwerken
        # spaeter noch repariert werden.
        from subfolder_duplicate_repair import repair_subfolder_duplicates
        repair_subfolder_duplicates(self.db, self.paths.find_song_file,
                                    self.paths.playlist_dir)
        # Mindest-Live-Volume aus INI laden
        min_vol = float(self._settings.value("audio/min_volume", 0.0))
        self.engine.set_min_volume(min_vol)
        _t1 = perf_split("  Paths + DB", _t0)

        # Aktuell geladener Song / Lokation
        self._current_song: Song = None
        self._current_location: Location = None

        # Datumsformat (de = DD.MM.YY, us = MM/DD/YY)
        self._date_format = self._settings.value("display/date_format", "de")

        # Minimales Central Widget
        placeholder = QWidget()
        placeholder.setMaximumSize(0, 0)
        self.setCentralWidget(placeholder)

        # --- Dock 1: Player ---
        _td0 = perf_start()
        self.player = PlayerWidget(self.engine, self.paths, skin_mgr=self.skin_mgr)
        self.player._db = self.db   # BL-083: DB-Zugriff fuer Tanzprogramm-Picker
        # Standard-Tanzprogramm MS vorbelegen
        for _pid, _code, *_ in self.db.get_all_dance_programs():
            if _code == "MS":
                self.player.set_dance_program(_pid, _code)
                break
        _td0b = perf_split("    Player: widget", _td0)
        # Variante C: kein on_before_load-Snapshot mehr noetig
        # (Live-Aenderungen werden sofort in DB persistiert).
        self.player.on_file_loaded = self._on_file_loaded
        self.player.on_tempo_changed = self._on_player_tempo_changed
        self.player.on_pitch_changed = self._on_player_pitch_changed
        self.player.on_location_clicked = self._on_location_button_clicked
        self.player.on_manager_clicked = self._on_manager_button_clicked
        self.player.on_lyrics_clicked = self._on_lyrics_button_clicked
        self.player.on_play_started = self._on_play_started
        self.player.on_resumed = self._on_play_resumed
        # Play-Gate: haelt Audio zurueck, bis Layout-/Loop-Aktionen fertig sind
        self._play_barrier = _PlayBarrier()
        self.player.on_play_orchestrate = self._orchestrate_play
        self.player.on_pause = self._on_player_pause
        self.player.on_manual_stop = self._on_manual_stop
        self.player.on_audition = self._on_player_audition
        self.player.on_exit_audition = self._on_player_exit_audition
        self.player.on_dance_program_changed = self._on_dance_program_changed  # BL-132
        # MS50: Player-Programm-Button oeffnet die session-globale Tanzprogramm-Wahl
        self.player.on_pick_programs = self._pick_session_programs
        self.player.on_break_clicked = self._on_open_break
        self.dock_player = _make_dock(
            self, _t("dock_player"), self.player, Qt.LeftDockWidgetArea
        )
        self.dock_player.setObjectName("dock_player")
        # Mindesthoehe/-breite: Player darf nicht gequetscht werden
        self.player.setMinimumHeight(380)
        self.dock_player.setMinimumWidth(340)

        _td1 = perf_split("    Player: make_dock", _td0b)
        # --- Dock 3: Song-Daten (erstellt, aber noch nicht platziert) ---
        self.song_data = SongDataWidget(self.db, self.paths)
        self.song_data.skin_mgr = self.skin_mgr  # BL-185: Icon-Tinting im Extended-Data-Dialog
        self.song_data.set_lang(get_language())
        self.song_data.on_song_saved = self._on_song_saved
        self.song_data.on_file_changed = self._on_song_file_changed
        self.song_data.on_song_deleted = self._on_song_deleted
        self.song_data.on_music_variant = self._on_song_file_changed
        self.song_data.on_lyric_variant = self._on_lyric_variant
        self.song_data.on_marker_jump = self._jump_to_time  # BL-185
        self.song_data.on_markers_changed = lambda: setattr(self, '_jm_sig', None)  # BL-185
        self.song_data.get_location_id = lambda: (
            self._current_location.id if self._current_location else None)
        self.song_data.on_add_note = lambda text: self._save_feedback_note(
            text, self._current_location.id if self._current_location else None)
        self._lyric_variant_filename = None  # aktive Lyric-Variante (None = Standard)
        self.dock_data = _make_dock(
            self, _t("dock_song_data"), self.song_data, Qt.RightDockWidgetArea
        )
        self.dock_data.setObjectName("dock_songdata")

        _td2 = perf_split("    SongData", _td1)
        # --- Dock 4: Songliste (Spalte 2, rechts neben Player) ---
        self.song_list = SongListWidget(
            self.db, pl_dir=self.paths.playlist_dir, settings=self._settings)
        self.song_list.on_song_selected = self._on_song_selected
        self.song_list.on_song_activated = self._on_song_activated
        self.song_list.on_song_delete_requested = self._on_song_delete_requested
        self.song_list.on_add_to_notes = self._notes_insert_song_shortcode
        self.song_list.on_add_to_playlist = self._add_song_to_playlist
        self.song_list.on_song_rating_changed = self._on_song_rating_changed
        self.dock_list = _make_dock(
            self, _t("dock_song_list"), self.song_list, Qt.RightDockWidgetArea
        )
        self.dock_list.setObjectName("dock_songlist")
        self.splitDockWidget(self.dock_player, self.dock_list, Qt.Horizontal)

        _td3 = perf_split("    SongList", _td2)
        # --- Dock 7: Lyrics (Spalte 3, rechts neben Songliste) ---
        self.lyrics_widget = LyricsWidget(self.paths, skin_mgr=self.skin_mgr, db=self.db)
        # BL-160: Im Sync-Modus Rules + History abschalten (Testlauf)
        self.lyrics_widget.on_sync_mode_changed = self._on_lyric_sync_mode
        # Automatische Body-Erkennung anfordern (laeuft im Worker-Thread)
        self.lyrics_widget.on_request_body_detect = self._on_request_body_detect
        # Neu gesetzte Sync-Marken → Start-Countdown-Cache invalidieren
        self.lyrics_widget.on_singing_marks_changed = self._on_singing_marks_changed
        # Gespeicherten Zoom wiederherstellen
        _lyrics_zoom_pct = int(self._settings.value("lyrics/zoom_pct", 100))
        _lyrics_auto_size = self._settings.value("lyrics/auto_size", True, type=bool)
        _lyrics_auto_width = self._settings.value("lyrics/auto_width", False, type=bool)
        # Exklusivitaet: Auto-Width gewinnt wenn beides gesetzt waere
        if _lyrics_auto_width:
            _lyrics_auto_size = False
        if _lyrics_zoom_pct != 100 or not _lyrics_auto_size or _lyrics_auto_width:
            self.lyrics_widget._btn_auto_size.setChecked(_lyrics_auto_size)
            self.lyrics_widget._btn_auto_width.setChecked(_lyrics_auto_width)
            _lz_size = self.lyrics_widget._base_font_size * _lyrics_zoom_pct / 100
            self.lyrics_widget._set_font_size(_lz_size)
            self.lyrics_widget._current_font_size = _lz_size
            self.lyrics_widget._update_zoom_label()
        self.dock_lyrics = _make_dock(
            self, _t("dock_lyrics"), self.lyrics_widget, Qt.RightDockWidgetArea
        )
        self.dock_lyrics.setObjectName("dock_lyrics")
        self.splitDockWidget(self.dock_list, self.dock_lyrics, Qt.Horizontal)

        _td4 = perf_split("    Lyrics", _td3)
        # --- Dock 2: Loop + NEU (unter Player in Spalte 1) ---
        self.loop_widget = LoopWidget(self.engine)
        self.loop_widget.on_new_clicked = self._on_new_song
        self.loop_widget.on_new_dropped = self._on_new_song_dropped  # BL-179
        self.loop_widget.on_set_marker = self._add_custom_marker  # BL-185
        self.dock_loop = _make_dock(
            self, _t("dock_loop"), self.loop_widget, Qt.LeftDockWidgetArea
        )
        self.dock_loop.setObjectName("dock_loop")
        # Mindesthoehe/-breite: Loop-Widget darf nicht gequetscht werden
        self.loop_widget.setMinimumHeight(190)
        self.dock_loop.setMinimumWidth(400)
        self.splitDockWidget(self.dock_player, self.dock_loop, Qt.Vertical)

        # Loop Active Checkbox vom LoopWidget in den Player verschieben
        chk = self.loop_widget.chk_loop
        chk.setParent(None)  # Aus altem Layout entfernen
        pl = self.player
        chk.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        pl._loop_active_grid.addWidget(chk, 0, 3, Qt.AlignCenter)

        # Find Loop Button mit Loop Finder verbinden
        self.loop_widget.btn_find_loop.clicked.connect(self._on_find_loop)

        _td5 = perf_split("    Loop", _td4)
        # --- Dock 5: Playlist (getabbt mit Songliste in Spalte 2) ---
        self.playlist_widget = PlaylistWidget(self.db, self.paths)
        self.playlist_widget.on_playlist_song_selected = self._on_playlist_song_selected
        self.playlist_widget.on_playlist_changed = self._on_playlist_data_changed
        self.playlist_widget.on_loop_count_edit = self._on_playlist_loop_count_edit
        self.playlist_widget.on_add_to_notes = self._notes_insert_song_shortcode
        self.playlist_widget.on_add_entries_to_notes = self._on_pl_export_to_notes
        self.playlist_widget.on_song_rating_changed = self._on_song_rating_changed
        self.dock_playlist = _make_dock(
            self, _t("dock_playlist"), self.playlist_widget, Qt.RightDockWidgetArea
        )
        self.dock_playlist.setObjectName("dock_playlist")
        self.tabifyDockWidget(self.dock_list, self.dock_playlist)
        self.dock_list.raise_()

        _td6 = perf_split("    Playlist", _td5)
        # --- Dock 6: Playlist-Manager (versteckt, ueber Menu oeffenbar) ---
        self.playlist_manager = PlaylistManagerWidget(
            self.db, self.playlist_widget, skin_mgr=self.skin_mgr, settings=self._settings)
        self.playlist_manager.get_target_duration = self._get_current_target_duration
        self.playlist_manager.on_confirm = self._on_manager_confirm
        self.dock_manager = _make_dock(
            self, _t("dock_planner"), self.playlist_manager, Qt.LeftDockWidgetArea
        )
        self.dock_manager.setObjectName("dock_manager")
        self.dock_manager.setAllowedAreas(Qt.NoDockWidgetArea)
        self.dock_manager.hide()
        self.dock_manager.visibilityChanged.connect(self._on_manager_visibility_changed)

        _td7 = perf_split("    Planner", _td6)
        # --- SongDaten + Sequenzen getabbt mit Lyrics (Spalte 3) ---
        self.tabifyDockWidget(self.dock_lyrics, self.dock_data)
        self.sequences_widget = SequencesWidget(self.db, skin_mgr=self.skin_mgr,
                                                settings=self._settings)
        _seq_zoom = int(self._settings.value("sequences/zoom_pct", 100))
        if _seq_zoom != 100:
            self.sequences_widget.set_zoom(_seq_zoom)
        # MS50: session-globale Tanzprogramm-Wahl auf Filter + Player-Button anwenden.
        # defer_seq_load: nur Baender setzen; das (kalt teure) Sequenzen-Laden macht
        # _init_sequences() erst nach window.show() -> nicht auf dem kritischen Pfad.
        self._apply_program_setting(defer_seq_load=True)
        self.dock_sequences = _make_dock(
            self, _t("dock_sequences"), self.sequences_widget, Qt.RightDockWidgetArea
        )
        self.dock_sequences.setObjectName("dock_sequences")
        self.tabifyDockWidget(self.dock_data, self.dock_sequences)
        self.dock_lyrics.raise_()   # Lyrics als Standard-Tab

        _td8 = perf_split("    SequencesWidget", _td7)

        # --- Dock: SequenzView (Detail-Ansicht, getabbt mit Sequences) ---
        self.sequence_view_widget = SequenceViewWidget(self.db, skin_mgr=self.skin_mgr)
        self.dock_sequence_view = _make_dock(
            self, _t("dock_sequence_view"), self.sequence_view_widget, Qt.RightDockWidgetArea
        )
        self.dock_sequence_view.setObjectName("dock_sequence_view")
        self.tabifyDockWidget(self.dock_sequences, self.dock_sequence_view)
        self.dock_sequence_view.hide()

        # SequencesWidget verbindet Klick auf Zeile mit SequenceViewWidget
        def _on_open_sequence_detail(seq_ids, current_idx):
            self.sequence_view_widget.set_sequence(self.db, seq_ids, current_idx)
            self.dock_sequence_view.setVisible(True)
            self.dock_sequence_view.raise_()
        self.sequences_widget.on_open_detail = _on_open_sequence_detail

        def _on_sequence_filter_changed():
            if not self.dock_sequence_view.isVisible():
                return
            seq_ids = self.sequences_widget.get_filtered_seq_ids()
            self.sequence_view_widget.set_sequence(self.db, seq_ids, 0)
        self.sequences_widget.on_filter_changed_detail = _on_sequence_filter_changed
        self.sequences_widget.on_add_to_notes = self._notes_insert_sequence_shortcode
        self.sequences_widget.on_add_filter_to_notes = self._notes_add_seq_with_filters
        self.sequences_widget.on_sequences_deleted = self._on_sequences_deleted
        self.sequences_widget.on_open_call_mapping = self._open_call_mapping
        self.sequence_view_widget.on_add_to_notes = self._notes_insert_sequence_shortcode
        self.sequence_view_widget.on_edit_sequence = self._on_sequence_editor
        self.sequence_view_widget.on_delete_sequence = self._on_sequence_view_delete
        # BL-173: Dynamic Lyrics — Schnittstelle zum Sequence-View (Quelle der
        # Wahrheit). Das Lyric-Widget spiegelt die dort aktuell gezeigte Sequenz;
        # bei Option 2 blaettert es dort an Figuren-Teil-Grenzen weiter.
        self.lyrics_widget.get_current_sequence_calls = \
            self.sequence_view_widget.current_calls
        self.lyrics_widget.advance_sequence_view = \
            self.sequence_view_widget.advance
        # BL-182: Dynamic-Start mischt auch die ERSTE Sequenz, wenn Shuffle an ist.
        self.lyrics_widget.randomize_start_sequence_view = \
            self.sequence_view_widget.random_start
        # intern#127: Spiegel-Button ohne gewaehlte Art -> Einstellungen dort oeffnen
        self.lyrics_widget.open_settings_at = \
            lambda key: self._show_settings_dialog(focus_key=key)
        self.sequence_view_widget.on_current_sequence_changed = \
            self.lyrics_widget.refresh_dynamic_from_sequence
        # Sequenzliste geaendert → Gating des Dynamic-Buttons neu bewerten.
        self.sequence_view_widget.on_sequences_changed = \
            self.lyrics_widget.update_dynamic_button_state
        # Gespeicherte Dynamic-Lyrics-Praeferenz (An/Aus + Modus) laden. Angewandt
        # wird beim ersten passenden Song (set_sync_identity → reapply).
        self.lyrics_widget.init_dynamic_preference()

        _td8b = perf_split("    SequenceViewWidget", _td8)
        # --- Dock 10: Reports (lazy — erst beim ersten Oeffnen erstellt) ---
        self.reports_widget = None  # Lazy
        self._reports_placeholder = QWidget()
        self.dock_reports = _make_dock(
            self, _t("dock_reports"), self._reports_placeholder, Qt.RightDockWidgetArea
        )
        self.dock_reports.setObjectName("dock_reports")
        self.dock_reports.hide()
        self.dock_reports.visibilityChanged.connect(self._on_reports_visibility)
        _td9 = perf_split("    Reports", _td8b)
        # --- Dock 11: Potential (lazy — erst beim ersten Oeffnen erstellt) ---
        self.potential_widget = None  # Lazy
        self._potential_placeholder = QWidget()
        self.dock_potential = _make_dock(
            self, _t("dock_potential"), self._potential_placeholder, Qt.RightDockWidgetArea
        )
        self.dock_potential.setObjectName("dock_potential")
        self.dock_potential.hide()
        self.dock_potential.visibilityChanged.connect(self._on_potential_visibility)

        _td10 = perf_split("    Potential", _td9)

        # --- Dock: Statistik (lazy — erst beim ersten Oeffnen erstellt) ---
        self.stats_widget = None  # Lazy
        self._stats_placeholder = QWidget()
        self.dock_stats = _make_dock(
            self, _t("dock_stats"), self._stats_placeholder, Qt.RightDockWidgetArea
        )
        self.dock_stats.setObjectName("dock_stats")
        self.dock_stats.hide()
        # Signal NACH hide() verbinden — verhindert unbeabsichtigtes lazy-init beim Start
        self.dock_stats.visibilityChanged.connect(self._on_stats_visibility)
        self.tabifyDockWidget(self.dock_reports, self.dock_stats)

        _td10s = perf_split("    Statistik", _td10)

        # --- Dock: Notizen (lazy — erst beim ersten Oeffnen erstellt) ---
        self.notes_widget = None  # Lazy
        self._notes_placeholder = QWidget()
        self._notes_location_id = None  # merkt sich die aktuelle Lokation bis zum Init
        self.dock_notes = _make_dock(
            self, _t("dock_notes"), self._notes_placeholder, Qt.RightDockWidgetArea
        )
        self.dock_notes.setObjectName("dock_notes")
        self.dock_notes.hide()
        self.dock_notes.visibilityChanged.connect(self._on_notes_visibility)

        _td10b = perf_split("    Notizen", _td10s)

        # --- Dock 12: Loop Finder (lazy — erst beim ersten Oeffnen erstellt) ---
        self.loop_finder = None  # Lazy init beim ersten Oeffnen
        self._loop_finder_placeholder = QWidget()
        self.dock_loop_finder = _make_dock(
            self, _t("dock_loop_finder"), self._loop_finder_placeholder, Qt.LeftDockWidgetArea
        )
        self.dock_loop_finder.setObjectName("dock_loop_finder")
        self.dock_loop_finder.setAllowedAreas(Qt.NoDockWidgetArea)
        self.dock_loop_finder.hide()
        # Signal NACH hide() verbinden — verhindert unbeabsichtigtes lazy-init beim Start
        self.dock_loop_finder.visibilityChanged.connect(self._on_loop_finder_visibility)
        # setFloating per Timer auf nach show() verschieben (Perf: ~90ms).
        # Position/Groesse kommen uniform aus windowState (kein Einzel-Geometry).
        def _setup_loop_finder_dock():
            self.dock_loop_finder.setFloating(True)
        QTimer.singleShot(0, _setup_loop_finder_dock)

        _td11 = perf_split("    LoopFinder", _td10b)
        # --- Dock 13: Photo (lazy — erst beim ersten Oeffnen erstellt) ---
        self.photo_widget = None
        self._photo_placeholder = QWidget()
        self.dock_photo = _make_dock(
            self, _t("dock_photo"), self._photo_placeholder, Qt.RightDockWidgetArea
        )
        self.dock_photo.setObjectName("dock_photo")
        self.dock_photo.setFloating(True)
        self.dock_photo.setAllowedAreas(Qt.NoDockWidgetArea)
        self.dock_photo.hide()
        self.dock_photo.visibilityChanged.connect(self._on_photo_visibility)

        _td12 = perf_split("    Photo", _td11)

        # --- Dock 14: Evening Planner (lazy — erst beim ersten Oeffnen erstellt) ---
        # Wie Photo/Reports/Stats: leerer Platzhalter beim Start, damit
        # restoreState() die Floating-Geometrie (Groesse + Position) sauber
        # wiederherstellt. Ein sofort gebautes Inhaltswidget mit
        # minimumSizeHint verhindert genau das.
        self.evening_planner = None
        self._ep_placeholder = QWidget()
        self._ep_location_id = None      # ausstehende Lokation bis Lazy-Init
        self._ep_planned_tips = 0        # ausstehende Tips-Zahl bis Lazy-Init
        # Floating-Geometrie der Tool-Fenster (objectName -> QRect): aus der
        # INI bzw. beim Schliessen vorgemerkt, angewandt beim naechsten
        # Sichtbarwerden (#121, siehe _on_float_dock_visible).
        self._pending_float_geom = {}
        self._float_geom_connected = False
        self.dock_evening_planner = _make_dock(
            self, _t("dock_evening_planner"), self._ep_placeholder, Qt.RightDockWidgetArea
        )
        self.dock_evening_planner.setObjectName("dock_evening_planner")
        self.dock_evening_planner.setFeatures(
            QDockWidget.DockWidgetMovable
            | QDockWidget.DockWidgetFloatable
            | QDockWidget.DockWidgetClosable)
        # Standard: freies Fenster (per Magnet andockbar, s. _DEFAULT_FREE_DOCKS)
        self.dock_evening_planner.setFloating(True)
        self.dock_evening_planner.setAllowedAreas(Qt.NoDockWidgetArea)
        self.dock_evening_planner.hide()
        self.dock_evening_planner.visibilityChanged.connect(
            self._on_evening_planner_visibility)

        _td13 = perf_split("    EveningPlanner", _td12)
        # --- Tutorial-Engine ---
        self.tutorial_engine = TutorialEngine(self, self._settings, self.skin_mgr)
        self.tutorial_engine.set_tutorials(TUTORIALS)
        self.tutorial_engine.register_widget("player", self.player)
        self.tutorial_engine.register_widget("song_list", self.song_list)
        self.tutorial_engine.register_widget("playlist", self.playlist_widget)
        self.tutorial_engine.register_widget("loop", self.loop_widget)
        self.tutorial_engine.register_widget("song_data", self.song_data)
        self.tutorial_engine.register_widget("playlist_manager", self.playlist_manager)
        self.tutorial_engine.register_widget("lyrics", self.lyrics_widget)
        self.tutorial_engine.register_widget("sequences", self.sequences_widget)
        # Reports + Potential sind lazy — Tutorial-Registrierung bei Erstellung
        # self.tutorial_engine.register_widget("reports", ...) → in _on_reports_visibility
        # self.tutorial_engine.register_widget("potential", ...) → in _on_potential_visibility
        # loop_finder ist lazy — Tutorial-Registrierung bei Erstellung
        # self.tutorial_engine.register_widget("loop_finder", ...) → in _init_loop_finder
        _t2 = perf_split("  Docks + Tutorials", _t1)

        # Engine-Callbacks
        self.engine.on_song_loaded = self._on_engine_song_loaded

        # Song-Ende-Erkennung: Timer-basiert statt Callback
        # (Audio-Thread Callbacks sind nicht zuverlaessig fuer GUI-Operationen)
        self._was_playing = False
        self._beat_snap_active = False  # Guard: Auto-Advance sperren bei Beat Snap
        self._suppress_play_log = False  # Guard: Audition/BeatSnap nicht in Historie
        self._in_audition = False       # Guard: Feedback-Dialog sperren bei Audition
        # Variante C: Snapshot-Mechanismus entfernt — Live-Aenderungen werden
        # direkt persistiert (kein Sammel-Save mehr beim Song-Wechsel).
        self._file_change_song_id = None  # Guard: Datei-Wechsel per Browse-Button
        self._pending_load = None  # (song_id, filepath): Laden eines bekannten Songs (intern#106)
        self._lyric_variant_filename = None  # aktive Lyric-Variante (None = Standard)

        # start_date (Fallback fuer "Tage seit letztem Abspielen")
        start_date_str = self._settings.value("playlist/start_date", "")
        if start_date_str:
            try:
                self._start_date = date.fromisoformat(start_date_str)
            except ValueError:
                self._start_date = date.today()
        else:
            self._start_date = date.today()
            self._settings.setValue("playlist/start_date", self._start_date.isoformat())

        # Loop-Crossfade-Dauer (Millisekunden, Default 46)
        xfade_ms = self._settings.value("loop/crossfade_ms", 46)
        try:
            self.engine.set_loop_crossfade_ms(max(0, float(xfade_ms)))
        except (ValueError, TypeError):
            self.engine.set_loop_crossfade_ms(46)

        # Loop-Offset: Kommt pro Song aus der DB (via apply_song_settings),
        # kein globaler INI-Wert mehr noetig.

        # Fade-Out-Dauer (Sekunden, Default 3)
        fade_time = self._settings.value("playlist/fade_out_time", 3)
        try:
            self.player._fade_duration = max(1.0, float(fade_time))
        except (ValueError, TypeError):
            self.player._fade_duration = 3.0

        # Spieldauer-Timer Warnschwellen (Sekunden)
        try:
            self.player._timer_warn1 = max(30, int(self._settings.value("player/timer_warn1", 240)))
        except (ValueError, TypeError):
            self.player._timer_warn1 = 240
        try:
            self.player._timer_warn2 = max(60, int(self._settings.value("player/timer_warn2", 300)))
        except (ValueError, TypeError):
            self.player._timer_warn2 = 300

        # INI-Defaults schreiben (damit User sie sehen und aendern kann)
        self._write_ini_defaults()

        # Timer
        self.timer = QTimer()
        self.timer.setInterval(50)
        self.timer.timeout.connect(self._update_all)
        self.timer.start()

        # Menue
        self._build_menu()
        _t2_menu = perf_split("    _build_menu", _t2)

        # Einzelbuchstaben-Shortcuts (L, P) via Event-Filter
        # QShortcut wird von QTableWidget/QListWidget geschluckt,
        # daher App-weiter Event-Filter der VOR den Widgets greift
        self._last_typing_ts = 0.0  # letzter Tastendruck in ein Textfeld (intern#101)
        QApplication.instance().installEventFilter(self)

        # Songliste + Playlist initial fuellen
        self.song_list.set_date_format(self._date_format)
        self.song_list.set_start_date(self._start_date)   # vor refresh(): erster Aufbau nutzt es schon
        self.song_list.refresh()
        _t2a = perf_split("    song_list.refresh", _t2_menu)
        self._refresh_last_played()
        _t2b = perf_split("    _refresh_last_played", _t2a)

        self.playlist_manager.set_date_format(self._date_format)
        self.playlist_manager.set_start_date(self._start_date)
        # Evening Planner: liest self._start_date beim Lazy-Init; nur nachziehen
        # wenn schon gebaut
        if self.evening_planner is not None:
            self.evening_planner.set_start_date(self._start_date)
        self.playlist_manager.refresh()

        _t3 = perf_split("    planner.refresh", _t2b)

        # Sequenzen: Mapper + Daten werden LAZY nach window.show() geladen
        # (main() ruft _init_sequences() per QTimer.singleShot(0, ...) auf) —
        # haelt den kalten Cover-Compute vom kritischen Startpfad fern.
        _t4 = perf_split("  Sequenzen (deferred)", _t3)

        # --- Rules Engine ---
        # WICHTIG: vor _restore_layout(). GRUNDSATZ (einheitlich fuer ALLE Docks):
        # Jeder Dock wird VOR restoreState() erzeugt und nimmt darueber an der
        # Wiederherstellung teil. Docks, die erst NACH restoreState() entstehen,
        # bekommen ihre angedockte Position nicht zuverlaessig zurueck. Der Stream
        # Deck, der Break-Dock UND der Rules-Dock haengen an der Engine, deshalb
        # wird sie hier — noch vor dem Layout-Restore — initialisiert.
        from rule_engine import RuleEngine
        from rule_definitions import register_v1_definitions, SYSTEM_RULES_DEFAULT
        self.rule_engine = RuleEngine(self._app_dir, settings=self._settings)
        register_v1_definitions(self.rule_engine)
        self.rule_engine.set_context_provider(self._get_rule_context)
        self._register_rule_conditions()
        self._register_rule_actions()
        self._ensure_system_rules_json()
        self.rule_engine.load()

        # --- Dock: Stream Deck (BL-168) — vollwertig andockbar ---
        from stream_deck_widget import StreamDeckWidget
        self.stream_deck_widget = StreamDeckWidget(
            self.rule_engine,
            skin_mgr=self.skin_mgr,
            execute_callback=self.rule_engine.execute_rule_manual,
            edit_callback=self._open_rules_dock,
        )
        # Deck aktualisiert sich, wenn Rules sich aendern (Nummer/Icon/Tooltip)
        self.rule_engine.add_rules_changed_listener(self.stream_deck_widget.refresh)
        self.dock_streamdeck = _make_dock(
            self, _t("dock_streamdeck"), self.stream_deck_widget,
            Qt.RightDockWidgetArea
        )
        self.dock_streamdeck.setObjectName("dock_streamdeck")
        # Default versteckt; restoreState() stellt den echten Zustand her.
        self.dock_streamdeck.hide()
        self._add_view_menu_entry(self.dock_streamdeck, _t("dock_streamdeck"))

        # --- Dock: Break (Pausen-Uhr) ---
        # Ebenfalls vor _restore_layout(), damit Position/Groesse/Sichtbarkeit
        # ueber windowState zuverlaessig wiederhergestellt werden.
        _tbreak = perf_start()
        self.break_widget = BreakWidget(self.skin_mgr)
        self.break_widget.on_play_last_song = self._on_break_play_last
        self.break_widget.on_stop_last_song = self._on_break_stop_last
        self.break_widget.on_break_started = self._on_break_started
        self.break_widget.on_break_finished = self._on_break_finished
        self._break_music_active = False
        self._break_music_timer = None
        self._break_with_music = False  # Art der letzten Pause (Condition break_type)
        # Zuletzt wirklich gestarteter Song dieser Sitzung (ohne Wartemusik,
        # Audition, Beat Snap) — Quelle fuer "Letzten Song spielen"
        self._last_logged_song_id = None
        # Vor der Wartemusik geladener Song — wird nach der Pause wieder geladen
        self._pre_break_song_id = None
        # Song, der gerade als Wartemusik laeuft (intern#130: ein manuelles Play
        # eines ANDEREN Songs beendet den Pausenzustand)
        self._break_music_song_id = None
        # Latch: unterdrueckt den Feedback-Dialog am Ende der Wartemusik. Wird in
        # _trigger_song_stopped einmalig gelesen und zurueckgesetzt (wie _in_audition).
        self._break_music_suppress_feedback = False
        self.dock_break = _make_dock(
            self, _t("dock_break"), self.break_widget, Qt.RightDockWidgetArea
        )
        self.dock_break.setObjectName("dock_break")
        self.dock_break.setAllowedAreas(Qt.NoDockWidgetArea)
        self.dock_break.setFloating(True)
        # _make_dock erzwingt 50x50 — echte Mindestgroesse aus den Kindern
        # wiederherstellen, sonst rutschen die Elemente beim Verkleinern ineinander.
        self.break_widget.enforce_min_size()
        self.dock_break.resize(240, 170)
        self.dock_break.hide()  # Default; restoreState() stellt echten Zustand her
        # Beim Oeffnen die Standard-Pausendauer der aktuellen Lokation uebernehmen
        self.dock_break.visibilityChanged.connect(self._on_break_visibility)
        self._add_view_menu_entry(self.dock_break, _t("dock_break"))
        perf_log("    Break dock", _tbreak)

        # --- Dock: Rules ---
        # Ebenfalls vor _restore_layout(), damit der Dock uniform am
        # windowState-Restore teilnimmt (keine Einzel-Geometrie mehr).
        from rule_widget import RulesWidget
        self.rules_widget = RulesWidget(
            self.rule_engine,
            dock_names_provider=self._dock_map,
            genre_names_provider=self.db.get_all_genres,
            preset_names_provider=self._get_loop_preset_names,
            layout_names_provider=self._get_layout_names,
            seqtype_names_provider=self.db.get_sequence_type_values,  # BL-181
            difficulty_names_provider=self.db.get_sequence_difficulty_values,  # BL-196
            tags_names_provider=self.db.get_sequence_tags_values,             # BL-197
            call_names_provider=self._rule_all_call_names,                    # BL-193/194
            program_choices_provider=self._rule_program_choices,             # BL-192
            skin_mgr=self.skin_mgr,
        )
        self.dock_rules = _make_dock(
            self, _t("dock_rules"), self.rules_widget, Qt.RightDockWidgetArea
        )
        self.dock_rules.setObjectName("dock_rules")
        self.dock_rules.setAllowedAreas(Qt.NoDockWidgetArea)
        # Rules ist nicht dockbar (nur freies Fenster). _make_dock setzt fuer die
        # Andockbarkeit eine Mini-Mindestgroesse (50x50) und ueberschreibt damit
        # die vom RulesWidget gewuenschte echte Mindestgroesse. Hier
        # wiederherstellen, sonst laesst sich das Fenster schmaler ziehen als sein
        # Inhalt und die Felder werden abgeschnitten.
        self.rules_widget.setMinimumSize(700, 400)
        self.dock_rules.setFloating(True)
        self.dock_rules.resize(900, 500)
        self.dock_rules.hide()
        self._add_view_menu_entry(self.dock_rules, _t("dock_rules"))
        self.tutorial_engine.register_widget("rules", self.rules_widget)

        # --- Dock: Jump Markers (BL-185, Teil 2) — vollwertig andockbar ---
        # Vor _restore_layout(), damit der Dock uniform am windowState-Restore
        # teilnimmt (Grundsatz: jeder Dock VOR restoreState() erzeugen).
        _tjm = perf_start()
        from jump_markers_widget import JumpMarkersWidget
        self.jump_markers_widget = JumpMarkersWidget(
            self.engine, self.db,
            skin_mgr=self.skin_mgr,
            jump_callback=self._jump_to_time,
            play_callback=self._jump_and_play,
            song_provider=lambda: self._current_song,
            perf_start=perf_start, perf_log=perf_log,
        )
        self.dock_jump_markers = _make_dock(
            self, _t("dock_jump_markers"), self.jump_markers_widget,
            Qt.RightDockWidgetArea
        )
        self.dock_jump_markers.setObjectName("dock_jump_markers")
        self.dock_jump_markers.hide()  # Default; restoreState() stellt echten Zustand her
        # Beim Sichtbarwerden neu aufbauen (Signatur invalidieren)
        self.dock_jump_markers.visibilityChanged.connect(
            lambda vis: setattr(self, '_jm_sig', None))
        self._add_view_menu_entry(self.dock_jump_markers, _t("dock_jump_markers"))
        perf_log("    JumpMarkers dock", _tjm)

        # --- Dock: To Call (BL-199) — vollwertig andockbar ---
        _ttc = perf_start()
        from to_call_widget import ToCallWidget
        self.to_call_widget = ToCallWidget(
            skin_mgr=self.skin_mgr,
            on_fill=self._open_tocall_fill,
            perf_start=perf_start, perf_log=perf_log,
        )
        self.dock_to_call = _make_dock(
            self, _t("dock_to_call"), self.to_call_widget,
            Qt.RightDockWidgetArea
        )
        self.dock_to_call.setObjectName("dock_to_call")
        self.dock_to_call.hide()
        self._add_view_menu_entry(self.dock_to_call, _t("dock_to_call"))
        perf_log("    ToCall dock", _ttc)

        # --- Dock: Pilot Square (BL-207) — vollwertig andockbar ---
        # Vor _restore_layout(), damit der Dock uniform am windowState-Restore
        # teilnimmt (Grundsatz: jeder Dock VOR restoreState() erzeugen).
        _tsq = perf_start()
        from pilot_square_widget import PilotSquareWidget
        self.pilot_square_widget = PilotSquareWidget(
            on_close=lambda: self.dock_pilot_square.hide()
        )
        self.pilot_square_widget.apply_skin(self.skin_mgr)
        self.dock_pilot_square = _make_dock(
            self, _t("dock_pilot_square"), self.pilot_square_widget,
            Qt.RightDockWidgetArea
        )
        self.dock_pilot_square.setObjectName("dock_pilot_square")
        self.dock_pilot_square.hide()
        self._add_view_menu_entry(self.dock_pilot_square, _t("dock_pilot_square"))
        perf_log("    PilotSquare dock", _tsq)

        # BL-204: Kontextmenue "Frei bewegen" fuer alle Dock-Titelleisten
        self._wire_dock_context_menus()
        # #121: Floating-Geometrie-Handler auch ohne gespeichertes Layout
        # (Erststart) verbinden, sonst merkt sich kein Dock seine Position
        # innerhalb der Sitzung. Idempotent.
        self._connect_float_geom_handlers()

        # Layout wiederherstellen
        self._restore_layout()
        # View-Menue-Haekchen nach dem Restore mit der tatsaechlichen
        # Sichtbarkeit abgleichen. restoreState() kann Docks sichtbar
        # herstellen (z. B. einen im Layout gespeicherten Loop Finder),
        # ohne dass toggleViewAction() das Haekchen zuverlaessig nachzieht
        # -> sichtbares Fenster, aber ungehaktes Menue. Deferrt, damit der
        # Abgleich NACH dem ebenfalls deferrten setFloating() der Tool-Docks
        # laeuft.
        QTimer.singleShot(0, self._sync_dock_view_actions)
        _t5 = perf_split("  Layout restore", _t4)

        # Auto-Save Layout alle 60 Sekunden (Safety-Net bei unerwartetem Beenden)
        self._layout_save_timer = QTimer()
        self._layout_save_timer.setInterval(60_000)
        self._layout_save_timer.timeout.connect(self._save_layout)
        self._layout_save_timer.start()

        # Fokus auf Songliste (verhindert dass SpinBox/Suchfeld
        # den Fokus hat und Shortcuts L/P blockiert)
        self.song_list.table.setFocus()
        perf_log("  __init__ GESAMT", _t0)

        # Pfade-Info beim Start
        info = self.paths.get_info()
        print(f"[P28] Pfade-Info:")
        for k, v in info.items():
            print(f"  {k}: {v}")

        # Shortcuts (nutzen rule_engine, daher nach Rules-Init)
        self._setup_shortcuts()

        # Statusleiste: Miniatur-Abspielfortschritt (BL-128) — vor Audio-Device-Combo einfuegen
        self._setup_statusbar_player()

        # Audio-Ausgabegeraet-Selector in Statusleiste (BL-126)
        self._setup_audio_device_selector()

        # Tutorial-System: Erstes Tutorial nach kurzem Delay anbieten
        QTimer.singleShot(1500, self.tutorial_engine.check_and_start)

        # Rules: app_started Trigger nach Init
        QTimer.singleShot(2000,
                          lambda: self.rule_engine.fire_trigger("app_started"))

        # BL-178: Start-Auto-Erkennung der Lokation (Vorschlag + Bestaetigung).
        # Deferred, damit Fenster/Sequenzen/Rules fertig sind und der Audio-Start
        # nicht belastet wird. Nach dem Tutorial-Delay, um Dialog-Stapelung zu meiden.
        QTimer.singleShot(2500, self._auto_detect_location_on_startup)

        # Evening Planner nach dem Start im Hintergrund vorbauen, damit das Dock
        # beim ersten Oeffnen sofort gefuellt ist (sonst blitzt ~2s lang das leere
        # Lazy-Platzhalter-Fenster auf). Bewusst spaet, nach den start-kritischen
        # Timern oben.
        QTimer.singleShot(3000, self._preload_evening_planner)

    # ---- Import-Workflow (P22) ----

    # Pattern: Buchstaben + optionales Leerzeichen + Ziffern + optionaler Suffix.
    # Suffix erlaubt Gross-/Kleinbuchstaben und Ziffern (z.B. 'RR 409F', 'RR 409h1').
    # Erkennt z.B.: BVR113, RYL818+, YRR 043a, RBS 1326, RR 409F, RR 409h1
    # (Spiegel von zip_import._LABEL_PATTERN — beide Stellen synchron halten.)
    _LABEL_PATTERN = re.compile(r'^[A-Za-z]+\s?\d+[A-Za-z0-9+]*$')

    @staticmethod
    def _parse_filename(basename: str) -> tuple:
        """Extrahiert Titel und Label aus dem Dateinamen.

        Unterstuetzt zwei Formate:
          TITEL-LABEL.mp3   z.B. 'Break My Stride-BVR113.mp3'
          LABEL-TITEL.mp3   z.B. 'BVR113-Break My Stride.mp3'

        Beispiele:
            'Break My Stride-BVR113.mp3'  → ('Break My Stride', 'BVR113')
            'RYL818-Ring Of Fire.mp3'     → ('Ring Of Fire', 'RYL818')
            'RingOfFire-RYL818+.mp3'      → ('RingOfFire', 'RYL818+')
            'A1005m.mp3'                  → ('A1005m', '')
            '10-20Hoedown.mp3'            → ('10-20Hoedown', '')

        Returns:
            (title, label) — label ist leer wenn das Muster nicht passt
        """
        name = os.path.splitext(basename)[0]
        if '-' not in name:
            return (name.strip(), '')

        pat = P29MainWindow._LABEL_PATTERN

        # Format 1: TITEL-LABEL (am letzten Bindestrich splitten)
        left, right = name.rsplit('-', 1)
        left = left.strip()
        right = right.strip()
        if right and pat.match(right):
            return (left, right)

        # Format 2: LABEL-TITEL (am ersten Bindestrich splitten)
        left2, right2 = name.split('-', 1)
        left2 = left2.strip()
        right2 = right2.strip()
        if left2 and pat.match(left2):
            return (right2, left2)

        # Kein Label-Match → ganzer Name als Titel
        return (name.strip(), '')

    _LYRICS_EXTENSIONS = ('.rtf', '.htm', '.html', '.txt', '.docx', '.pdf')

    def _build_lyrics_map(self, folder: str) -> dict:
        """Sammelt alle Lyrics-Dateien eines Ordners als {name_ohne_ext_lower: originalname}.

        Bei mehreren Dateien mit gleichem Namensstamm gewinnt das Format mit der
        hoeheren Prioritaet (Reihenfolge in _LYRICS_EXTENSIONS: rtf vor docx vor pdf).

        Zusaetzlich werden label-bereinigte Zweitschluessel erzeugt ('Song-RYL818'
        -> 'Song'), damit auch Lyrics-Dateien gefunden werden, die das Label tragen,
        die MP3 aber nicht. Exakte (rohe) Schluessel haben dabei immer Vorrang.
        """
        result: dict = {}        # roher key -> originalname (autoritativ)
        best_pr: dict = {}       # roher key -> Prioritaets-Index der Extension
        derived: dict = {}       # label-bereinigter key -> originalname (Fallback)
        derived_pr: dict = {}
        try:
            names = os.listdir(folder)
        except OSError:
            return result
        for fname in names:
            noext, ext = os.path.splitext(fname)
            ext_l = ext.lower()
            if ext_l not in self._LYRICS_EXTENSIONS:
                continue
            pr = self._LYRICS_EXTENSIONS.index(ext_l)
            key = noext.lower()
            if key not in best_pr or pr < best_pr[key]:
                result[key] = fname
                best_pr[key] = pr
            # Zweitschluessel ohne Label ('Song-RYL 818' -> 'Song')
            title, _label = self._parse_filename(noext)
            dkey = title.lower()
            if dkey != key and (dkey not in derived_pr or pr < derived_pr[dkey]):
                derived[dkey] = fname
                derived_pr[dkey] = pr
        # Label-bereinigte Schluessel nur fuellen, wo es keinen exakten Treffer gibt
        for dkey, fname in derived.items():
            result.setdefault(dkey, fname)
        return result

    def _find_and_import_lyrics(self, stem: str, source_dir: str) -> str:
        """Sucht eine passende Lyrics-Datei und kopiert sie ggf. in den Lyrics-Ordner.

        Das Matching ist tolerant (4-stufig, wie in der SqView-Migration): exakt,
        Label am Ende abschneiden, normalisiert, normalisiert + ohne Label. Damit
        werden Lyrics auch dann gefunden, wenn der Dateiname nicht exakt mit der
        MP3 uebereinstimmt (z.B. Label-Pakete: MP3 'Song - RYL 818', Lyrics 'Song').

        Sucht in dieser Reihenfolge:
          1. Im Quellordner der MP3 (source_dir) — wird kopiert wenn gefunden
          2. Im App-Lyrics-Ordner — bereits vorhanden, nur verknuepfen

        Args:
            stem:       Dateiname ohne Extension (z.B. 'Ring Of Fire-RYL818')
            source_dir: Ordner der importierten MP3

        Returns:
            Dateiname der Lyrics-Datei (nur Name, kein Pfad) oder ''
        """
        from migration.sqview_reader import SqViewReader

        lyrics_dir = self.paths.lyrics_dir

        # Such-Varianten: roher Stem + Titel ohne Label. _parse_filename erkennt
        # auch Label ohne umgebende Leerzeichen ('Song-RYL 818' -> 'Song'), was
        # der SqView-Matcher allein nicht abdeckt.
        queries = [stem]
        parsed_title, _label = self._parse_filename(stem)
        if parsed_title and parsed_title.lower() != stem.lower():
            queries.append(parsed_title)

        def _match(folder: str) -> str:
            fmap = self._build_lyrics_map(folder)
            for q in queries:
                hit = SqViewReader.match_lyrics(q, fmap)
                if hit:
                    return hit
            return ''

        # 1. Im Quellordner suchen (tolerant) und ggf. in lyrics/ kopieren
        if source_dir and os.path.isdir(source_dir):
            match = _match(source_dir)
            if match:
                src = os.path.join(source_dir, match)
                dest = os.path.join(lyrics_dir, match)
                if not os.path.exists(dest):
                    try:
                        shutil.copy2(src, dest)
                    except Exception as e:
                        print(f"[Import] Lyrics kopieren fehlgeschlagen: {e}")
                        match = ''
                if match:
                    return match

        # 2. Im Lyrics-Ordner selbst suchen (bereits vorhanden, nur verknuepfen)
        if os.path.isdir(lyrics_dir):
            match = _match(lyrics_dir)
            if match:
                return match

        return ''

    def _on_find_loop(self):
        """Find-Loop-Button: Zeigt das Loop-Finder-Dock an."""
        self.dock_loop_finder.show()
        self.dock_loop_finder.raise_()
        self.dock_loop_finder.activateWindow()

    def _on_open_break(self):
        """Kaffeetassen-Button im Player: Break-Widget (Pausen-Uhr) anzeigen."""
        self.dock_break.show()
        self.dock_break.raise_()
        self.dock_break.activateWindow()

    def _on_break_visibility(self, visible):
        """Beim Sichtbarwerden die Standard-Pausendauer der Lokation uebernehmen.

        Mechanik analog zur Patternlaenge: Wert der aktuellen Lokation, sonst
        Default (5 Min). Ein bereits laufender Countdown bleibt unangetastet.
        """
        if not visible:
            return
        loc = self._current_location
        minutes = (loc.effective_break_minutes if loc is not None
                   else Location.DEFAULT_BREAK_MINUTES)
        self.break_widget.apply_default_duration(minutes * 60)

    def _on_new_song(self):
        """NEU-Button: erst Quelle (Datei/Ordner/ZIP), dann Auswahl, dann Kopieren + Typ.

        Reihenfolge bewusst: Quelle zuerst. ZIP-Pakete springen direkt ins Preview
        (Typ/Kopieren werden dort geklaert). Bei Datei/Ordner kommen Kopieren und
        Songtyp erst NACH der Auswahl — der Typ ganz am Ende.
        """
        last_dir = str(self._settings.value(
            "paths/last_import_dir", os.path.expanduser("~")))
        if not os.path.isdir(last_dir):
            last_dir = os.path.expanduser("~")

        # 1) Quelle zuerst: Datei / Ordner / ZIP
        src_dlg = QMessageBox(self)
        src_dlg.setWindowTitle(_t("import_source_title"))
        src_dlg.setText(_t("import_source_text"))
        src_dlg.setIcon(QMessageBox.Question)
        btn_files = src_dlg.addButton(_t("import_source_files"), QMessageBox.ActionRole)
        btn_folder = src_dlg.addButton(_t("import_source_folder"), QMessageBox.ActionRole)
        btn_zip = src_dlg.addButton(_t("import_source_zip"), QMessageBox.ActionRole)
        src_dlg.addButton(QMessageBox.Cancel)
        src_dlg.setDefaultButton(btn_files)
        src_dlg.exec()
        src_clicked = src_dlg.clickedButton()

        # 1a) ZIP: direkt ins Preview, keine weiteren Vorab-Dialoge
        if src_clicked == btn_zip:
            zip_paths, _ = QFileDialog.getOpenFileNames(
                self, _t("dialog_import_zip"), last_dir, _t("filter_zip_files"))
            if zip_paths:
                # Letztes Import-Verzeichnis merken (der Datei-/Ordner-Pfad tut das
                # am Ende selbst; der ZIP-Pfad kehrt frueher zurueck und muss es hier
                # tun, sonst oeffnet der Dialog naechstes Mal wieder am falschen Ort).
                self._settings.setValue(
                    "paths/last_import_dir", os.path.dirname(zip_paths[0]))
                self._import_zip_packages(zip_paths)
            return

        # 1b) Datei-Auswahl (nur Audio — der Dialog filtert bereits auf Audio).
        if src_clicked == btn_files:
            filepaths, _ = QFileDialog.getOpenFileNames(
                self, _t("dialog_import_audio"), last_dir, _t("filter_audio_files"))
            if not filepaths:
                return
            # Ab hier gemeinsamer Ablauf: Kopieren? -> Songtyp? -> Import.
            self._import_audio_selection(filepaths, import_root="", offer_genre=False)
            return

        # 1c) Ordner-Auswahl: kann Audio UND/ODER ZIP-Pakete enthalten (BL-179).
        if src_clicked == btn_folder:
            folder = QFileDialog.getExistingDirectory(
                self, _t("dialog_import_folder"), last_dir)
            if not folder:
                return
            audio_files = self._collect_folder_audio(folder)
            zip_paths = self._collect_folder_zips(folder)
            if not audio_files and not zip_paths:
                QMessageBox.information(self, _t("import_source_title"),
                                        _t("import_folder_empty"))
                return
            self._dispatch_import(audio_files, zip_paths,
                                  import_root=folder, offer_genre=True)
            return

        return  # Abbruch

    # Audio-Endungen, die Ordner-Import und Drag&Drop (BL-179) akzeptieren.
    _IMPORT_AUDIO_EXTS = (".mp3", ".wav", ".flac", ".ogg", ".aiff", ".aif")

    def _collect_folder_audio(self, folder: str) -> list:
        """Sammelt alle Audiodateien unterhalb von `folder` (rekursiv, sortiert).

        Gemeinsamer Helfer fuer den Ordner-Import (NEU-Button) und den
        Drag&Drop-Import (BL-179) — dieselbe Endungsliste, dieselbe Reihenfolge.
        """
        found = []
        for root, _dirs, files in os.walk(folder):
            for f in files:
                if f.lower().endswith(self._IMPORT_AUDIO_EXTS):
                    found.append(os.path.join(root, f))
        found.sort()
        return found

    def _collect_folder_zips(self, folder: str) -> list:
        """Sammelt alle ZIP-Pakete unterhalb von `folder` (rekursiv, sortiert).

        Pendant zu `_collect_folder_audio` — damit ein Ordner-Import auch die
        enthaltenen ZIP-Label-Pakete findet (BL-179).
        """
        found = []
        for root, _dirs, files in os.walk(folder):
            for f in files:
                if f.lower().endswith(".zip"):
                    found.append(os.path.join(root, f))
        found.sort()
        return found

    def _dispatch_import(self, audio_files: list, zip_paths: list,
                         import_root: str = "", offer_genre: bool = False):
        """Entscheidet anhand der gefundenen Typen, was importiert wird, und ruft
        die bestehenden Prozeduren (BL-179).

        - Nur Audio  → `_import_audio_selection`
        - Nur ZIPs   → `_import_zip_packages`
        - Beides     → transparente Rueckfrage (Nur MP3 / Nur ZIPs / Beides),
                       danach der jeweils normale Ablauf.
        """
        if audio_files and zip_paths:
            mix_dlg = QMessageBox(self)
            mix_dlg.setWindowTitle(_t("import_mixed_title"))
            mix_dlg.setText(_t("import_mixed_text",
                               mp3=len(audio_files), zip=len(zip_paths)))
            mix_dlg.setIcon(QMessageBox.Question)
            btn_mp3 = mix_dlg.addButton(_t("import_mixed_mp3"), QMessageBox.ActionRole)
            btn_zip = mix_dlg.addButton(_t("import_mixed_zip"), QMessageBox.ActionRole)
            btn_both = mix_dlg.addButton(_t("import_mixed_both"), QMessageBox.ActionRole)
            mix_dlg.addButton(QMessageBox.Cancel)
            mix_dlg.setDefaultButton(btn_both)
            mix_dlg.exec()
            clicked = mix_dlg.clickedButton()
            if clicked == btn_mp3:
                zip_paths = []
            elif clicked == btn_zip:
                audio_files = []
            elif clicked == btn_both:
                pass
            else:
                return  # Abbruch

        # ZIP zuerst (eigener Preview-Flow), dann Audio (Kopieren/Typ/Genre).
        if zip_paths:
            self._settings.setValue(
                "paths/last_import_dir", os.path.dirname(zip_paths[0]))
            self._import_zip_packages(zip_paths)
        if audio_files:
            self._import_audio_selection(
                audio_files, import_root=import_root, offer_genre=offer_genre)
        if not zip_paths and not audio_files:
            QMessageBox.information(
                self, _t("import_source_title"), _t("import_drop_nothing"))

    def _on_new_song_dropped(self, paths: list):
        """Drag&Drop auf den NEU-Button (BL-179): die gedroppten Pfade bestimmen
        die Quelle, deshalb entfaellt gegenueber `_on_new_song` nur die
        Quellenauswahl. Der Rest laeuft ueber `_dispatch_import` und damit ueber
        dieselben Prozeduren wie der Button.

        Klassifiziert die Drops in ZIP-Pakete, Ordner und lose Audiodateien.
        Gedroppte Ordner werden rekursiv nach Audio UND ZIPs durchsucht; kommen
        am Ende beide Typen zusammen, fragt `_dispatch_import` transparent nach.
        """
        zip_paths, folders, loose = [], [], []
        for p in paths:
            if os.path.isdir(p):
                folders.append(p)
            elif p.lower().endswith(".zip"):
                zip_paths.append(p)
            elif p.lower().endswith(self._IMPORT_AUDIO_EXTS):
                loose.append(p)

        # Ordnerinhalte einsammeln (Audio + ZIP-Pakete).
        audio_files = list(loose)
        for folder in folders:
            audio_files.extend(self._collect_folder_audio(folder))
            zip_paths.extend(self._collect_folder_zips(folder))
        audio_files.sort()
        zip_paths.sort()

        # import_root nur setzen, wenn genau EIN Ordner (und keine losen Audio-
        # Dateien) gedroppt wurde — nur dann sind alle Audiopfade relativ dazu.
        import_root = folders[0] if (len(folders) == 1 and not loose) else ""
        # Genre-Dialog anbieten, sobald ein Ordner im Spiel ist (analog zum
        # Ordner-Import via Button, BL-184).
        self._dispatch_import(audio_files, zip_paths,
                              import_root=import_root, offer_genre=bool(folders))

    def _import_audio_selection(self, filepaths: list, import_root: str = "",
                                offer_genre: bool = False):
        """Gemeinsamer Import-Ablauf ab feststehender Quelle: Kopieren? -> Songtyp?
        -> (optional) Genre? -> Import.

        Wird vom NEU-Button (nach der Quellenauswahl in `_on_new_song`) und vom
        Drag&Drop auf den NEU-Button (BL-179 — die Quelle steht durch den Drop
        bereits fest, deshalb entfaellt dort nur die Quellenauswahl) genutzt.

        Args:
            filepaths:   Liste absoluter Audio-Dateipfade.
            import_root: Wurzelordner bei Ordner-Import (fuer relative Pfade).
            offer_genre: True = Genre-Zuweisungsdialog anbieten (Ordner-Import).
        """
        # 1) Kopieren oder am Ort belassen?
        copy_dlg = QMessageBox(self)
        copy_dlg.setWindowTitle(_t("import_copy_title"))
        copy_dlg.setText(_t("import_copy_text"))
        copy_dlg.setIcon(QMessageBox.Question)
        btn_copy = copy_dlg.addButton(_t("import_copy_btn"), QMessageBox.ActionRole)
        btn_leave = copy_dlg.addButton(_t("import_leave_btn"), QMessageBox.ActionRole)
        copy_dlg.addButton(QMessageBox.Cancel)
        copy_dlg.setDefaultButton(btn_copy)
        copy_dlg.exec()
        copy_clicked = copy_dlg.clickedButton()
        if copy_clicked == btn_copy:
            copy_mode = True
        elif copy_clicked == btn_leave:
            copy_mode = False
        else:
            return  # Abbruch

        # 2) Songtyp ganz am Ende (Pattern / Singing / Both)
        type_dlg = QMessageBox(self)
        type_dlg.setWindowTitle(_t("import_type_title"))
        type_dlg.setText(_t("import_type_text"))
        type_dlg.setIcon(QMessageBox.Question)
        btn_pattern = type_dlg.addButton(_t("import_type_pattern"), QMessageBox.ActionRole)
        btn_singing = type_dlg.addButton(_t("import_type_singing"), QMessageBox.ActionRole)
        btn_both = type_dlg.addButton(_t("import_type_both"), QMessageBox.ActionRole)
        type_dlg.addButton(QMessageBox.Cancel)
        type_dlg.setDefaultButton(btn_both)
        type_dlg.exec()
        type_clicked = type_dlg.clickedButton()
        if type_clicked == btn_pattern:
            self._import_is_pattern, self._import_is_singing = 1, 0
        elif type_clicked == btn_singing:
            self._import_is_pattern, self._import_is_singing = 0, 1
        elif type_clicked == btn_both:
            self._import_is_pattern, self._import_is_singing = 1, 1
        else:
            return  # Abbruch

        # 3) Genre-Zuweisung (BL-184) — nur beim ORDNER-Import. Der Nutzer
        # importiert typischerweise einen Ordner, dessen Lieder alle demselben
        # Genre angehoeren (z.B. "Recordings", "Elvis"). Die angehakten Genres
        # werden allen Songs des Imports additiv zugewiesen.
        import_genre_ids = None
        if offer_genre:
            genre_dlg = _ImportGenreDialog(self.db, self)
            if genre_dlg.exec() != QDialog.Accepted:
                return  # Abbruch
            import_genre_ids = genre_dlg.selected_genre_ids()

        # 4) Import
        self._import_files(filepaths, copy_mode=copy_mode,
                           import_root=import_root,
                           genre_ids=import_genre_ids)

    def _import_single_audio(self, filepath: str, copy_mode: bool,
                             is_pattern: int, is_singing: int,
                             auto_lyrics: bool = True,
                             genre_ids: list = None) -> dict:
        """Importiert EINE Audiodatei in die Bibliothek (gekapselter Kern).

        Wird vom normalen Import (_import_files) und vom ZIP-Import genutzt.
        - Speicherform (Basename bei copy, sonst relativer Pfad, BL-147)
        - Duplikat-Pruefung / Blind-Song-Aktivierung
        - Kopieren nach music/ (copy_mode) bzw. am Ort belassen
        - DB-Insert mit Titel/Label aus Dateiname
        - optional: gleichnamige Lyrics co-importieren (auto_lyrics)
        - Genre-Vorschlag aus Dateiname

        Returns: dict(song, store_name, dest, status) mit status in
                 'new' | 'blind' | 'dup'. Wirft bei Fehlern (Caller kapselt).
        """
        music_dir = self.paths.music_dir
        basename = os.path.basename(filepath)
        store_name = basename if copy_mode \
            else self.paths.to_relative_filename(filepath)

        # 1) Duplikat-Pruefung / Blind-Song-Aktivierung (BL-147)
        existing = self.db.get_by_filename(store_name)
        if not existing and store_name != basename:
            legacy = self.db.get_by_filename(basename)
            if legacy and not self.paths.find_song_file(legacy.filename):
                self.db.update_filename(legacy.id, store_name)
                existing = self.db.get_by_filename(store_name)
                print(f"[Import] Verwaisten Eintrag #{legacy.id} auf "
                      f"relativen Pfad gehoben: '{store_name}'")
        if existing:
            dest_path = os.path.join(music_dir, basename)
            if not os.path.exists(dest_path):
                if copy_mode:
                    shutil.copy2(filepath, dest_path)
                    print(f"[Import] Blind-Song aktiviert: #{existing.id} '{store_name}'")
                else:
                    dest_path = filepath
                    print(f"[Import] Blind-Song aktiviert (in-place): #{existing.id} '{store_name}'")
                return {"song": existing, "store_name": store_name,
                        "dest": dest_path, "status": "blind"}
            print(f"[Import] Uebersprungen (Duplikat): {store_name}")
            return {"song": existing, "store_name": store_name,
                    "dest": dest_path, "status": "dup"}

        # 2) Kopieren oder am Ort belassen
        if copy_mode:
            dest = os.path.join(music_dir, basename)
            if not os.path.exists(dest):
                shutil.copy2(filepath, dest)
                print(f"[Import] Kopiert: {basename}")
            else:
                print(f"[Import] Datei existiert bereits: {basename}")
        else:
            dest = filepath
            print(f"[Import] Am Ort belassen: {filepath}")

        # 3) Dateiname parsen + DB-Eintrag
        title, label = self._parse_filename(basename)
        # intern#126: sicherer Katalogtreffer -> Katalog-Schreibweise + Caller
        cat_entry = self._catalog_entry_for_import(basename, title, label)
        if cat_entry is not None:
            title = song_catalog.canonical_title(title, cat_entry.title)
            label = cat_entry.label_field
        song = Song(filename=store_name, title=title, label=label,
                    artist=cat_entry.caller if cat_entry else "",
                    is_pattern=is_pattern, is_singing=is_singing)
        song = self.db.insert(song)
        print(f"[Import] Neu: #{song.id} '{title}'"
              f"{f' [{label}]' if label else ''}")
        if cat_entry is not None:
            self._apply_catalog_metadata(song.id, cat_entry)

        # 3b) Lyrics-Co-Import (gleichnamig, tolerant) — beim ZIP abgeschaltet
        if auto_lyrics:
            lyrics_file = self._find_and_import_lyrics(
                stem=os.path.splitext(basename)[0],
                source_dir=os.path.dirname(filepath),
            )
            if lyrics_file:
                song.lyrics_file = lyrics_file
                self.db.update(song)
                print(f"[Import] Lyrics verknuepft: {lyrics_file}")

        # 3c) Genre-Vorschlaege aus Dateiname (Keyword-Matching)
        name_lower = os.path.splitext(basename)[0].lower()
        suggested_ids = []
        for keyword, genre_name in _GENRE_IMPORT_KEYWORDS.items():
            if keyword in name_lower:
                gid = self.db.get_genre_id_by_name(genre_name)
                if gid > 0 and gid not in suggested_ids:
                    suggested_ids.append(gid)
        if suggested_ids:
            # BL-040: additiv hinzufuegen statt set_genres_for_song(), damit das
            # in db.insert() gesetzte "NEW"-Genre nicht ueberschrieben wird.
            for gid in suggested_ids:
                self.db.add_song_genre(song.id, gid)
            print(f"[Import] Genre-Vorschlag: {suggested_ids}")

        # 3d) BL-184: Vom Ordner-Import-Dialog gewaehlte Genres additiv setzen.
        # genre_ids is None -> Dialog wurde nicht durchlaufen (Datei-Import),
        # nichts tun. Leere Liste -> Dialog lief, aber nichts angehakt (auch NEW
        # abgewaehlt) -> NEW wieder entfernen.
        if genre_ids is not None:
            for gid in genre_ids:
                self.db.add_song_genre(song.id, gid)
            new_id = self.db.get_genre_id_by_name("NEW")
            if new_id > 0 and new_id not in genre_ids:
                self.db.remove_song_genre(song.id, new_id)
            print(f"[Import] Genre-Zuweisung (BL-184): {genre_ids}")

        return {"song": song, "store_name": store_name,
                "dest": dest, "status": "new"}

    def _catalog_entry_for_import(self, basename: str, title: str, label: str):
        """intern#126: Katalogeintrag fuer eine neue Datei, nur bei "sicher".

        Der Katalog ist eine weitere Datenquelle fuer den vorhandenen Abgleich
        (song_match): bewertet wird der Dateiname in beiden Zerlegungen (Import-
        Parser und zip_import-Parser), der bessere Treffer zaehlt. Unterhalb von
        IMPORT_MIN_SCORE wird nichts uebernommen (Potential zeigt es an)."""
        try:
            catalog = song_catalog.get_catalog(self.paths.app_dir)
            if catalog is None:
                return None
            pn = song_match.parse_name(os.path.splitext(basename)[0])
            matches = [m for m in (catalog.identify(title, label),
                                   catalog.identify(pn.title, pn.label_full)) if m]
        except Exception as e:  # noqa: BLE001 — Import darf daran nie scheitern
            print(f"[Import] Katalog-Abgleich uebersprungen: {e}")
            return None
        best = max(matches, key=lambda m: m.score, default=None)
        if best is None or not best.is_sure:
            return None
        print(f"[Import] Katalog: '{best.entry.title}' [{best.entry.label_field}] "
              f"(Score {best.score})")
        return best.entry

    def _apply_catalog_metadata(self, song_id: int, entry):
        """Fuellt Original-Interpret, Erscheinungsjahr und bekannte Genres aus
        dem Katalog (neuer Song, Felder sind leer). Additiv, NEW bleibt."""
        try:
            if entry.original_artist:
                self.db.set_property(song_id, "original_artist", entry.original_artist)
            if entry.release_year:
                self.db.set_property(song_id, "release_year", entry.release_year)
            # Nur bekannte Genres, Gross-/Kleinschreibung egal (wie Potential)
            known = {name.lower(): gid for gid, name in self.db.get_all_genres()}
            for gname in entry.genres:
                gid = known.get(gname.lower())
                if gid:
                    self.db.add_song_genre(song_id, gid)
        except Exception as e:  # noqa: BLE001
            print(f"[Import] Katalog-Metadaten uebersprungen (#{song_id}): {e}")

    def _import_files(self, filepaths: list, copy_mode: bool = True,
                      import_root: str = "", genre_ids: list = None):
        """Importiert eine oder mehrere Audio-Dateien in die Datenbank.

        Args:
            filepaths:  Liste absoluter Dateipfade.
            copy_mode:  True  = Dateien ins music/-Verzeichnis kopieren (Standard).
                        False = Dateien am Ort belassen, nur DB-Eintrag anlegen.
                                Quellordner/Wurzel wird ggf. als freier Musikpfad-
                                Slot eingetragen; Songs werden RELATIV dazu gespeichert.
            import_root: Wurzelordner (bei Ordner-Import die gewaehlte Wurzel).
                        Leer = aus den Dateipfaden ableiten.

        - Duplikat-Pruefung (Dateiname/relativer Pfad bereits in DB)
        - Dateiname-Parsing (Titel + Label)
        - DB-Eintrag anlegen
        - Letzten importierten Song in den Player laden
        """
        imported = []
        skipped = []
        errors = []
        music_dir = self.paths.music_dir
        last_imported_path = None

        # BL-147: Bei "am Ort belassen" die Wurzel VOR dem Loop als Musik-Slot
        # registrieren, damit to_relative_filename() die relativen Pfade dagegen
        # bilden kann und find_song_file() sie spaeter wieder aufloest.
        if not copy_mode and filepaths:
            root = import_root or os.path.dirname(filepaths[0])
            if root and not self.paths.has_path_in_music_dirs(root):
                free_slot = self.paths.find_free_music_slot()
                if free_slot:
                    reply = QMessageBox.question(
                        self,
                        _t("import_add_path_title"),
                        _t("import_add_path_text", slot=free_slot, path=root),
                        QMessageBox.Yes | QMessageBox.No,
                        QMessageBox.Yes
                    )
                    if reply == QMessageBox.Yes:
                        self.paths.set_music_dir(root, slot=free_slot)
                        print(f"[Import] Wurzelpfad als Musikpfad {free_slot} eingetragen: {root}")
                else:
                    QMessageBox.information(
                        self,
                        _t("import_add_path_title"),
                        _t("import_slots_full")
                    )

        for filepath in filepaths:
            basename = os.path.basename(filepath)
            # Pro Datei gekapselt: defekte Dateien ueberspringen, nicht abbrechen.
            try:
                r = self._import_single_audio(
                    filepath, copy_mode,
                    getattr(self, '_import_is_pattern', 1),
                    getattr(self, '_import_is_singing', 1),
                    auto_lyrics=True,
                    genre_ids=genre_ids,
                )
                if r["status"] == "dup":
                    skipped.append(r["store_name"])
                else:
                    imported.append(r["store_name"])
                    last_imported_path = r["dest"]
            except Exception as e:
                errors.append(f"{basename}: {e}")
                print(f"[Import] Fehler: {basename} — {e}")
                continue

        # 5) Letztes Import-Verzeichnis merken
        if filepaths:
            import_dir = os.path.dirname(filepaths[0])
            self._settings.setValue("paths/last_import_dir", import_dir)

        # (5b entfaellt — Slot-Registrierung erfolgt jetzt VOR dem Loop, BL-147)

        # 6) Letzten importierten Song laden (fehlertolerant)
        if last_imported_path:
            try:
                self.player._load_file(last_imported_path)
            except Exception as e:
                errors.append(f"{os.path.basename(last_imported_path)}: Laden fehlgeschlagen ({e})")
                print(f"[Import] Laden fehlgeschlagen: {last_imported_path} — {e}")

        # 7) Songliste aktualisieren
        self.song_list.refresh()

        # 8) Song-List-Dock in den Vordergrund holen, damit neue Songs sichtbar sind
        if imported:
            try:
                self.dock_list.show()
                self.dock_list.raise_()
            except Exception:
                pass

        # 9) Zusammenfassung anzeigen
        lines = []
        if imported:
            lines.append(_t("import_songs_imported", count=len(imported)))
            lines.append("")
            lines.append(_t("import_result_hint_songlist"))
        if skipped:
            lines.append(_t("import_songs_skipped", count=len(skipped)))
        if errors:
            lines.append(_t("import_errors", count=len(errors)))
            lines.extend(f"  {e}" for e in errors)

        if lines:
            QMessageBox.information(
                self, _t("import_result_title"), "\n".join(lines)
            )

    # ---- ZIP-Label-Import (BL-157) ----

    def _zip_lists_path(self) -> str:
        """Pfad zu den user-pflegbaren Erkennungs-Listen (JSON).

        Enthaelt das Delta der vier Listen (Modifier/Labels/Beiwerk/Rollen).
        Eine alte zip_modifiers.json im selben Ordner wird beim Laden migriert.
        """
        return os.path.join(perf.app_dir(), "config", "zip_import_lists.json")

    def _audition_zip_play(self, path: str) -> str:
        """Probehören einer Datei aus dem ZIP-Preview — komplett "still".

        Wie das Loop-Finder-Vorhören: direkt ueber die Engine (NICHT player._on_play),
        damit weder Rules noch History-Tracking ausgeloest werden. Zusaetzlich werden
        die Rules waehrend des Probehörens suspendiert (gegen Timer-/Positions-Trigger)
        und das Play-Log unterdrueckt. Toggelt Pause/Resume bei gleicher Datei.
        Returns 'playing' oder 'paused'.
        """
        eng = self.player.engine
        # Gleiche Datei laeuft bereits -> Pause/Resume togglen (Engine-direkt)
        if getattr(self, "_zip_audition_path", None) == path and eng.is_playing():
            if eng.paused:
                eng.play()
                return "playing"
            eng.pause()
            return "paused"
        # Neue Datei: still laden + abspielen
        self._ensure_primary_channel()
        if not getattr(self, "_zip_audition_active", False):
            self.rule_engine.suspend("zip_audition")
            self._zip_audition_active = True
        self._suppress_play_log = True
        eng.load(path)
        self._zip_audition_path = path
        eng.play()
        return "playing"

    def _stop_zip_audition(self):
        """Probehören beenden (beim Schliessen des Preview-Dialogs).

        Stoppt die Engine und hebt Rules-Suspend + History-Suppress wieder auf.
        Idempotent: mehrfacher Aufruf ist unschaedlich.
        """
        if getattr(self, "_zip_audition_path", None):
            try:
                self.player.engine.stop()
            except Exception:
                pass
            self._zip_audition_path = None
        if getattr(self, "_zip_audition_active", False):
            try:
                self.rule_engine.resume("zip_audition")
            except Exception:
                pass
            self._zip_audition_active = False
            self._suppress_play_log = False

    def _import_zip_packages(self, zip_paths: list):
        """Startet die ZIP-Analyse im Hintergrund und zeigt danach den Preview."""
        lists = zip_import.load_lists(self._zip_lists_path())
        self._zip_progress = QProgressDialog(
            _t("zip_analyzing"), "", 0, 0, self)
        self._zip_progress.setWindowTitle(_t("import_result_title"))
        self._zip_progress.setCancelButton(None)
        self._zip_progress.setWindowModality(Qt.WindowModal)
        self._zip_progress.setMinimumDuration(0)
        self._zip_progress.show()

        worker = _ZipAnalyzeWorker(zip_paths, lists)
        self._zip_worker = worker  # Referenz halten, sonst GC
        worker.done.connect(lambda res, marks: self._on_zip_analyzed(res, marks, lists))
        worker.failed.connect(self._on_zip_analyze_failed)
        worker.start()

    def _on_zip_analyze_failed(self, msg: str):
        if getattr(self, "_zip_progress", None):
            self._zip_progress.close()
        QMessageBox.warning(self, _t("import_result_title"),
                            _t("zip_analyze_failed", error=msg))

    def _on_zip_analyzed(self, result, marks, lists):
        if getattr(self, "_zip_progress", None):
            self._zip_progress.close()
        # Perf-Marken jetzt im Main-Thread schreiben
        for label, secs in marks:
            perf_log(label, 0.0, secs)

        if not result.bundles:
            zip_import.cleanup(result)
            QMessageBox.information(self, _t("import_result_title"),
                                    _t("zip_no_songs"))
            return
        # Mehrere Songs in einem ZIP: erst nachfragen, nicht still teilen (intern#125)
        multi = result.multi_song_zips
        try:
            if multi:
                split = ask_zip_split(self, multi)
                if split is None:
                    return
                for g in multi:
                    g.use_split = split
                result.refresh_bundles()
            dlg = ZipImportPreviewDialog(
                result, lists, self._zip_lists_path(), self,
                audition_cb=self._audition_zip_play,
                dup_lookup=self._zip_dup_title)
            accepted = dlg.exec() == QDialog.Accepted
            self._stop_zip_audition()  # vor Commit/Cleanup Probehören stoppen
            if accepted:
                self._import_zip_bundles(result, dlg.get_decisions())
        finally:
            self._stop_zip_audition()
            zip_import.cleanup(result)

    def _import_zip_bundles(self, result, decisions: list):
        """Commit der im Preview bestaetigten Bundles in DB + Bibliothek."""
        t_start = perf_start()
        lyrics_dir = self.paths.lyrics_dir
        music_dir = self.paths.music_dir

        def _copy_into(src: str, target_dir: str) -> str:
            os.makedirs(target_dir, exist_ok=True)
            dest = os.path.join(target_dir, os.path.basename(src))
            # Namenskollision mit ANDERER Datei (Groesse weicht ab): eindeutigen
            # Namen waehlen statt still auf die fremde Datei zu verlinken.
            # Gleiche Groesse werten wir als identische Datei (Re-Import).
            if os.path.exists(dest) \
                    and os.path.getsize(dest) != os.path.getsize(src):
                root, ext = os.path.splitext(dest)
                k = 1
                while os.path.exists(dest) \
                        and os.path.getsize(dest) != os.path.getsize(src):
                    dest = f"{root}_{k}{ext}"
                    k += 1
            if not os.path.exists(dest):
                shutil.copy2(src, dest)
            return os.path.basename(dest)

        imported = 0
        skipped = []    # Dateinamen, die schon existierten (intern#125)
        not_attached = []   # Dateien eines Duplikats, die nicht angehaengt wurden
        attached = 0    # neue Spuren an vorhandene Songs gehaengt
        errors = []
        last_dest = None

        for d in decisions:
            audio = d.get("audio", [])
            if not audio:
                continue
            try:
                primary = audio[0]
                r = self._import_single_audio(
                    primary["path"], copy_mode=True,
                    is_pattern=d["is_pattern"], is_singing=d["is_singing"],
                    auto_lyrics=False,
                )
                song = r["song"]
                if song is None:
                    continue
                if r["status"] == "dup":
                    # Hauptspur existiert schon. Auf Wunsch (Preview) nur die
                    # Spuren anhaengen, die der Song noch nicht hat.
                    skipped.append(os.path.basename(primary["path"]))
                    # Lyrics haengt der Duplikat-Zweig nie an: nicht still verwerfen
                    not_attached.extend(os.path.basename(l["path"])
                                        for l in d.get("lyrics", []) if l["selected"])
                    if not d.get("attach_new"):
                        not_attached.extend(os.path.basename(a["path"]) for a in audio[1:])
                        continue
                    known = {os.path.basename(song.filename).lower()} | {
                        os.path.basename(f).lower()
                        for _i, _n, f in self.db.get_variants(song.id, "music")}
                    for a in audio[1:]:
                        name = os.path.basename(a["path"])
                        if name.lower() in known or self.db.get_by_filename(name):
                            skipped.append(name)
                            continue
                        fn = _copy_into(a["path"], music_dir)
                        self.db.add_variant(song.id, "music", a["label_text"], fn)
                        attached += 1
                    continue
                # Titel/Label aus dem Preview uebernehmen (User kann editiert haben)
                song.title = d["title"] or song.title
                song.label = d["label"]
                self.db.update(song)

                # Varianten-MP3s (ab Position 2)
                for a in audio[1:]:
                    fn = _copy_into(a["path"], music_dir)
                    self.db.add_variant(song.id, "music", a["label_text"], fn)

                # Primaere Lyrics
                primary_lyr = next(
                    (l for l in d.get("lyrics", [])
                     if l["selected"] and l["is_primary"]), None)
                if primary_lyr:
                    fn = _copy_into(primary_lyr["path"], lyrics_dir)
                    song.lyrics_file = fn
                    self.db.update(song)
                # Weitere Lyrics als Varianten
                for l in d.get("lyrics", []):
                    if not l["selected"] or l["is_primary"]:
                        continue
                    fn = _copy_into(l["path"], lyrics_dir)
                    self.db.add_variant(song.id, "lyric", l["label_text"], fn)

                imported += 1
                last_dest = r["dest"]
            except Exception as e:  # noqa: BLE001
                errors.append(str(e))
                print(f"[ZIP-Import] Fehler: {e}")
                continue

        perf_log("zip_import.commit", t_start)

        # Letzten Song laden, Liste aktualisieren
        if last_dest:
            try:
                self.player._load_file(last_dest)
            except Exception as e:
                print(f"[ZIP-Import] Laden fehlgeschlagen: {e}")
        self.song_list.refresh()
        if imported:
            try:
                self.dock_list.show()
                self.dock_list.raise_()
            except Exception:
                pass

        lines = []
        if imported:
            lines.append(_t("import_songs_imported", count=imported))
            lines.append("")
            lines.append(_t("import_result_hint_songlist"))
        if attached:
            lines.append(_t("zip_attached_tracks", count=attached))
        if skipped:
            lines.append(_t("import_songs_skipped", count=len(skipped)))
            lines.extend(_t("import_skipped_file", name=n) for n in skipped)
        if not_attached:
            lines.append(_t("zip_not_attached", count=len(not_attached)))
            lines.extend(f"  • {n}" for n in not_attached)
        if errors:
            lines.append(_t("import_errors", count=len(errors)))
            lines.extend(f"  {e}" for e in errors)
        if lines:
            QMessageBox.information(self, _t("import_result_title"),
                                    "\n".join(lines))

    def _zip_dup_title(self, filename: str):
        """ZIP-Preview (intern#125): Titel des vorhandenen Songs, wenn die Datei
        beim Import als Duplikat uebersprungen wuerde, sonst None. Gleiche
        Pruefung wie _import_single_audio im Kopiermodus (Speichername =
        Basename, Datei liegt schon im Musikordner)."""
        song = self.db.get_by_filename(filename)
        if song and os.path.exists(os.path.join(self.paths.music_dir, filename)):
            return song.title or filename
        return None

    # ---- Lokation-Auswahl ----

    def _on_location_button_clicked(self, location_id=None):
        """Oeffnet den Lokation-Auswahl-Dialog."""
        current_id = location_id if location_id else (
            self._current_location.id if self._current_location else None
        )
        dialog = LocationDialog(self.db, current_location_id=current_id, parent=self)
        # Tutorial beim ersten Oeffnen anzeigen (Timer laeuft innerhalb exec())
        if hasattr(self, 'tutorial_engine') and self.tutorial_engine:
            from tutorial_definitions import LOCATION_DIALOG_STEPS
            engine = self.tutorial_engine
            steps = LOCATION_DIALOG_STEPS
            QTimer.singleShot(300, lambda: engine.show_dialog_tutorial(
                dialog, "location_dialog", steps
            ))
        if dialog.exec() == QDialog.Accepted:
            location = dialog.get_selected_location()
            self._set_current_location(location)

    def _toggle_dock(self, dock, open_position="centered"):
        """Echtes Show/Hide-Toggle fuer ein Dock-Widget.

        - Nicht sichtbar: Als loses Fenster oeffnen. open_position steuert die
          Platzierung (#66): "centered" = ueber dem Hauptfenster zentrieren
          (bisheriges Verhalten); "last" = NICHT zentrieren, sodass die vom
          floatgeom-System gemerkte letzte Position greift.
        - Sichtbar, aber als hinterer Tab versteckt: In den Vordergrund holen.
        - Sichtbar und im Vordergrund (oder floating): Ausblenden.

        Instrumentierung 2026-05-25 (AR-014 / Aufgabe N): Jeder teure Qt-Schritt
        wird per perf_split einzeln gestempelt, damit wir auf schwacher Hardware
        (Celeron N3450) sehen, welcher Call die Aussetzer verursacht. Label nutzt
        objectName/windowTitle des Docks, damit Planner/Lyrics/etc. unterscheidbar
        sind.
        """
        name = dock.objectName() or dock.windowTitle() or "?"
        t0 = perf_start()
        if not dock.isVisible():
            # Als loses Fenster in der Mitte des Hauptfensters platzieren
            t = perf_split(f"_toggle_dock({name}): branch=open", t0)
            dock.setFloating(True)
            t = perf_split(f"_toggle_dock({name}): setFloating(True)", t)
            dock.show()
            t = perf_split(f"_toggle_dock({name}): show()", t)
            if open_position == "centered":
                self._center_float_dock(dock)
                perf_split(f"_toggle_dock({name}): move()", t)
            # "last": kein move() -> floatgeom-System stellt die letzte Position her
            perf_log(f"_toggle_dock({name}): TOTAL open", t0)
        elif not dock.isFloating() and dock.visibleRegion().isEmpty():
            # Sichtbar, aber als hinterer Tab im Stapel — nach vorne holen
            t = perf_split(f"_toggle_dock({name}): branch=raise", t0)
            dock.raise_()
            t = perf_split(f"_toggle_dock({name}): raise_()", t)
            dock.widget().setFocus()
            perf_split(f"_toggle_dock({name}): setFocus()", t)
            perf_log(f"_toggle_dock({name}): TOTAL raise", t0)
        else:
            # Vorne sichtbar oder floating — ausblenden
            t = perf_split(f"_toggle_dock({name}): branch=hide", t0)
            dock.hide()
            perf_split(f"_toggle_dock({name}): hide()", t)
            perf_log(f"_toggle_dock({name}): TOTAL hide", t0)

    def _on_manager_button_clicked(self):
        _t0 = perf_start()
        self._toggle_dock(self.dock_manager,
                          self._button_open_position(self.dock_manager))
        _t = perf_split("_on_manager_button_clicked: _toggle_dock", _t0)
        # Nur wenn der Planner jetzt sichtbar ist: Sortierung vorwaehlen und fokussieren
        if self.dock_manager.isVisible():
            # Hat der User eine Lieblings-Sortierung hinterlegt, hat die Vorrang:
            # die Filter-Bar hat sie beim Aufbau schon gesetzt, und ein erneutes
            # Ueberschreiben beim Dock-Oeffnen wuerde auch jede manuelle
            # Umstellung wieder wegwerfen. Ohne INI-Eintrag bleibt es beim
            # bisherigen Verhalten (Empfehlung bzw. Qualitaet).
            _fb = self.playlist_manager._filter_bar
            if not self._settings.contains("sort/default_mode"):
                # setCurrentIndex nur ueber findData: der Index haengt an der
                # Reihenfolge der Eintraege, der Modus an den SORT_*-Konstanten.
                _mode = (_fb.SORT_RECOMMENDATION if self._current_location
                         else _fb.SORT_QUALITY)
                _idx = _fb._combo_sort.findData(_mode)
                if _idx >= 0:
                    _fb._combo_sort.setCurrentIndex(_idx)
            perf_split("_on_manager_button_clicked: setCurrentIndex(sort)", _t)
            QTimer.singleShot(50, self._focus_planner_pool)
        perf_log("_on_manager_button_clicked: TOTAL", _t0)

    def _focus_planner_pool(self):
        """Setzt Fokus auf Pool-Tabelle und selektiert erste Zeile."""
        # Floating Dock braucht activateWindow() fuer Tastatur-Fokus
        if self.dock_manager.isFloating():
            self.dock_manager.activateWindow()
        t = self.playlist_manager._pool_table
        t.setFocus()
        if t.rowCount() > 0 and not t.currentItem():
            t.setCurrentCell(0, 0)

    def _on_lyrics_button_clicked(self):
        self._toggle_dock(self.dock_lyrics,
                          self._button_open_position(self.dock_lyrics))

    @staticmethod
    def _parse_program_ids(raw) -> list:
        """Kommagetrennte ID-Liste (INI-Wert 'sequences/dance_programs') -> [int, ...]."""
        out = []
        for part in str(raw or "").split(","):
            part = part.strip()
            if part:
                try:
                    out.append(int(part))
                except ValueError:
                    pass
        return out

    def _bands_for_program_ids(self, pids):
        """MS50: Programm-IDs -> Menge der Programm-Baender (Ganzzahl aus
        dance_programs.sequence_limit_to, z.B. 30.999999 -> 30). Leer/None -> None
        (= kein Programm-Filter, alle Sequenzen)."""
        if not pids:
            return None
        limits = {r[0]: r[5] for r in self.db.get_all_dance_programs()}
        bands = {int(limits[p]) for p in pids if limits.get(p) is not None}
        return bands or None

    def _location_program_ids(self, location):
        """Programm-IDs einer Lokation inkl. Legacy-Fallback auf dance_program_id."""
        if not location or getattr(location, "id", None) is None:
            return []
        ids = list(self.db.get_location_program_ids(location.id))
        if not ids and getattr(location, "dance_program_id", None) is not None:
            ids = [location.dance_program_id]
        return ids

    def _top_program(self, pids):
        """Oberstes (hoechstes Band) der gewaehlten Programme -> (program_id, code).
        Liefert die Basis fuer die Ziel-Tanzdauer. Leer -> (None, '')."""
        if not pids:
            return None, ""
        rows = {r[0]: r for r in self.db.get_all_dance_programs()}
        best = None  # (band, id, code)
        for p in pids:
            r = rows.get(p)
            if r is None:
                continue
            band = r[5] if len(r) > 5 and r[5] is not None else -1
            if best is None or band > best[0]:
                best = (band, p, r[1])
        if best is None:
            return None, ""
        return best[1], best[2]

    def _apply_program_setting(self, defer_seq_load=False):
        """MS50: session-globale Tanzprogramm-Wahl anwenden — Sequenz-Filter (Band-Menge)
        + aktives Programm fuer die Ziel-Tanzdauer (oberstes gewaehltes Programm).

        defer_seq_load=True (nur beim Startup): Baender setzen, aber das teure
        Sequenzen-Laden NICHT sofort ausloesen — das uebernimmt _init_sequences()
        nach window.show() (haelt den Cover-Compute vom kritischen Startpfad fern).
        """
        ids = self._session_program_ids
        if getattr(self, "sequences_widget", None) is not None:
            self.sequences_widget.set_program_bands(
                self._bands_for_program_ids(ids), defer_load=defer_seq_load)
        top_id, top_code = self._top_program(ids)
        self.player.set_dance_program(top_id, top_code)

    def _set_session_program_ids(self, ids, persist: bool = True):
        """Setzt die session-globale Tanzprogramm-Wahl, persistiert sie (INI) und
        wendet sie an. persist=False fuer rein transiente Aktualisierungen."""
        self._session_program_ids = list(ids or [])
        if persist:
            self._settings.setValue(
                "sequences/dance_programs",
                ",".join(str(i) for i in self._session_program_ids))
            self._settings.sync()
        self._apply_program_setting()

    def _program_codes_label(self, ids):
        """Anzeige-String der Programm-Codes fuer eine ID-Liste (fuer Settings-Fenster)."""
        if not ids:
            return _t("loc_settings_no_program")
        code_by_id = {r[0]: r[1] for r in self.db.get_all_dance_programs()}
        codes = [code_by_id.get(i) for i in ids]
        codes = [c for c in codes if c]
        return ", ".join(codes) if codes else _t("loc_settings_no_program")

    def _pick_session_programs(self):
        """Player-Button: session-globale Tanzprogramm-Wahl aendern (ohne Lokation)."""
        dlg = _MultiProgramPickerDialog(
            self.db, selected_ids=list(self._session_program_ids), parent=self)
        if dlg.exec() == QDialog.Accepted:
            self._set_session_program_ids(dlg.get_selected_ids())

    def _settings_pick_programs(self, current_ids, parent_widget=None):
        """Callback fuers Settings-Fenster: oeffnet den Picker, gibt neue IDs zurueck
        (oder None bei Abbruch). Persistenz/Anwendung macht das Settings-Fenster
        ueber den INI-Write + _on_settings_applied."""
        dlg = _MultiProgramPickerDialog(
            self.db, selected_ids=list(current_ids or []),
            parent=(parent_widget.window() if parent_widget is not None else self))
        if dlg.exec() == QDialog.Accepted:
            return dlg.get_selected_ids()
        return None

    def _set_current_location(self, location: Location):
        """Setzt die aktuelle Lokation und aktualisiert UI."""
        import crash_handler as _ch
        _ch.log_action(f"Lokation: {location.name if location else '—'}")
        self._current_location = location
        self.player.set_location(location)
        self._update_title()

        # MS50: Die Lokation "fuettert" die session-globale Tanzprogramm-Wahl.
        # Hat die Lokation Programme, uebernehmen sie das Setting (persistiert +
        # Filter + Ziel-Dauer via oberstem Programm). Hat sie keine, bleibt die
        # bisherige Session-Wahl erhalten (Tanzprogramm ist von der Lokation
        # entkoppelt und session-global).
        loc_ids = self._location_program_ids(location)
        if loc_ids:
            self._set_session_program_ids(loc_ids)

        # BL-144: Ziel-BPM hat Vorrang — sie wird pro Song gerechnet, nicht hier
        # fest gesetzt. Fuer den bereits geladenen Song sofort nachziehen.
        if location and location.has_target_bpm:
            self.player._apply_target_bpm()
            self.player._update_bpm_display()
        # BL-086: Temporaeres Tempo der Lokation uebernehmen
        elif location and location.temp_tempo is not None:
            self.player.spin_today_tempo.setValue(int(location.temp_tempo))
        self._refresh_last_played()
        # Geplante Tips-Anzahl an Planner und Evening Planner weitergeben
        planned = location.planned_tips if location else None
        self.playlist_manager.set_planned_tips(planned or 0)
        # Evening Planner: Tips-Zahl merken (Lazy-Init liefert sie nach)
        self._ep_planned_tips = planned or 0
        if self.evening_planner is not None:
            self.evening_planner.set_planned_tips(self._ep_planned_tips)

        # Notizen fuer neue Lokation laden (lazy: ID merken, Widget ggf. noch nicht erstellt)
        self._notes_location_id = location.id if location else None
        if self.notes_widget:
            self.notes_widget.refresh(self._notes_location_id)
        if location:
            # Caller-Workflow: Planner-Button rot → naechster Schritt
            self.player.set_planner_warning(True)
            print(f"[P21] Lokation gewaehlt: #{location.id} '{location.name}'")
        else:
            self.player.set_planner_warning(False)
            print(f"[P21] Keine Lokation gewaehlt")

    def _auto_detect_location_on_startup(self):
        """BL-178: Schlaegt beim Start anhand Wochentag/Uhrzeit eine passende
        Lokation vor (Vorschlag + Bestaetigung, nie stilles Setzen).

        - Genau ein bester Treffer -> Ja/Nein-Rueckfrage.
        - Mehrere Treffer -> Auswahlliste (bester vorausgewaehlt).
        - Kein Treffer -> nichts (bisheriges Verhalten, roter Lokation-Button).
        Laeuft nur, solange der Nutzer noch keine Lokation gewaehlt hat.
        """
        if self._current_location is not None:
            return
        try:
            matches = self.db.find_locations_for_datetime(datetime.now())
        except Exception as e:
            print(f"[BL-178] Auto-Erkennung uebersprungen: {e}")
            return
        if not matches:
            return
        weekday = datetime.now().isoweekday()

        def _today_start(loc):
            for (d, tf, _tt) in loc.schedule_list:
                if d == weekday:
                    return tf
            return ""
        if len(matches) == 1:
            loc = matches[0][0]
            reply = QMessageBox.question(
                self, _t("loc_autodetect_title"),
                _t("loc_autodetect_confirm", name=loc.name,
                   time=_today_start(loc)),
                QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
            if reply == QMessageBox.Yes:
                self._set_current_location(loc)
            return
        # Mehrere Treffer: Auswahl anbieten (bester zuerst vorausgewaehlt)
        names = [m[0].name for m in matches]
        choice, ok = QInputDialog.getItem(
            self, _t("loc_autodetect_title"),
            _t("loc_autodetect_pick"), names, 0, False)
        if ok and choice:
            for loc, _score in matches:
                if loc.name == choice:
                    self._set_current_location(loc)
                    break

    def _update_title(self):
        """Aktualisiert die Titelzeile mit Lokation-Info."""
        if self._current_location:
            self.setWindowTitle(f"{_BASE_TITLE}  @  {self._current_location.name}")
        else:
            self.setWindowTitle(_BASE_TITLE)

    # ---- Abspielhistorie ----

    def _pre_play_bookkeeping(self) -> bool:
        """Play-Buchhaltung, die VOR dem 'song_started'-Trigger laufen muss
        (u.a. reset_song_fired fuer once_per_song). Gibt False zurueck, wenn
        kein Song geladen ist. Reihenfolge identisch zum frueheren
        _on_play_started (nur ohne das Trigger-Feuern selbst)."""
        if not self._current_song or not self._current_song.id:
            return False
        # Vor dem Historie-Log und dem song_started-Trigger: beides soll fuer
        # den von Hand gestarteten Song wieder ganz normal laufen.
        self._end_break_on_manual_play()
        import crash_handler as _ch
        _ch.log_action(f"Play: {self._current_song.title or self._current_song.filename}")
        # Audition/Beat-Snap nicht in Historie loggen, aber Rules trotzdem feuern
        if not getattr(self, '_suppress_play_log', False):
            self._last_logged_song_id = self._current_song.id
            location_id = self._current_location.id if self._current_location else None
            # Historie-Log ist "best effort": ist die DB gerade gesperrt (z.B.
            # laufende Bulk-Worker), darf das NICHT das Abspielen verhindern.
            try:
                self.db.log_play(self._current_song.id, location_id)
            except Exception as e:  # noqa: BLE001 — Playback hat Vorrang
                print(f"[Play] Historie-Log uebersprungen (DB gesperrt?): {e}")
        self._refresh_last_played()
        # Now-Playing-Highlight in Songliste + Playlist auf den real
        # startenden Song setzen (folgt dem tatsaechlich laufenden Song).
        self.song_list.set_playing_song(self._current_song.id)
        self.playlist_widget.set_playing_song(self._current_song.id)
        self.rule_engine.reset_song_fired()
        self._last_play_timer_fire = 0
        return True

    def _on_play_started(self):
        """Fallback-Pfad (on_play_orchestrate nicht verdrahtet): Buchhaltung +
        Trigger in Alt-Reihenfolge."""
        if self._pre_play_bookkeeping():
            self.rule_engine.fire_trigger("song_started")

    def _on_play_resumed(self):
        """Fallback-Pfad: Resume-Trigger (keine Buchhaltung)."""
        self.rule_engine.fire_trigger("song_resumed")

    # ---- Play-Orchestrierung mit Rule-Gating (PlayBarrier) ----

    def _orchestrate_play(self, is_resume: bool):
        """Neuer Play-Pfad (von PlayerWidget ueber on_play_orchestrate).

        Feuert stream-gefaehrdende Rules ZUERST (waehrend Stille) und startet
        den hoerbaren Audio-Stream erst, wenn Layout-/Loop-Aktionen fertig
        gemeldet haben. Enthaelt die betroffene Rule keine solche Aktion, bleibt
        alles wie frueher: erst Audio, dann Trigger (null Latenz)."""
        if self._play_barrier.is_busy():
            return  # bereits ein Gate aktiv — Doppelklick ignorieren

        if is_resume:
            trigger = "song_resumed"
        else:
            trigger = "song_started"
            if not self._pre_play_bookkeeping():
                # Kein Song geladen → nur Audio, kein Trigger (Alt-Verhalten)
                self.player._do_play(is_resume)
                return

        gated = self.rule_engine.trigger_matches_any_action(
            trigger, self._PLAY_GATE_ACTIONS)

        if gated:
            # Trigger feuern (Layout/Loop starten) BEVOR Audio hoerbar wird.
            self._play_barrier.begin_collecting()
            self.rule_engine.fire_trigger(trigger)
            self._play_barrier.arm(
                lambda: self._start_audio_after_gate(is_resume, trigger, True))
        else:
            self._start_audio_after_gate(is_resume, trigger, False)

    def _start_audio_after_gate(self, is_resume: bool, trigger: str,
                                already_fired: bool):
        """Startet den hoerbaren Stream. Bei nicht-gated Play wird der Trigger
        hier — nach dem Start — gefeuert (Alt-Reihenfolge bleibt erhalten)."""
        self.player._do_play(is_resume)
        if not already_fired:
            self.rule_engine.fire_trigger(trigger)

    # BL-074 ----------------------------------------------------------------

    def _on_player_audition(self):
        """Schaltet auf sekundaeren Ausgang fuer Audition (Vorhören)."""
        sec_str = self._settings.value("audio/secondary_device", "")
        try:
            sec_dev = int(sec_str) if sec_str else None
        except (ValueError, TypeError):
            sec_dev = None
        try:
            sec_vol = int(self._settings.value("audio/secondary_volume", "80"))
        except (ValueError, TypeError):
            sec_vol = 80
        self._pre_audition_volume = self.player.slider_live_volume.value()
        self._pre_audition_device = self.engine._output_device  # Device vor dem Wechsel merken
        self.engine.set_output_device(sec_dev)
        # Lautstaerke auf Sekundaerkanal-Wert setzen (ohne Signal → direkt Engine)
        self.player.slider_live_volume.blockSignals(True)
        self.player.slider_live_volume.setValue(sec_vol)
        self.player.slider_live_volume.blockSignals(False)
        self.engine.set_live_volume(sec_vol / 100.0)
        self._suppress_play_log = True
        self._in_audition = True

    def _on_player_exit_audition(self):
        """Stellt primaeren Ausgang und Lautstaerke nach Audition wieder her."""
        # Gespeichertes Device nehmen (nicht neu aus INI lesen) — AudioEngine-Fallback-Cache
        # sorgt dafuer, dass kein erneuter WASAPI-Versuch fuer bekannte Problemgeraete laeuft.
        pri_dev = getattr(self, "_pre_audition_device", None)
        self.engine.set_output_device(pri_dev)
        prev_vol = getattr(self, "_pre_audition_volume", 100)
        self.player.slider_live_volume.blockSignals(True)
        self.player.slider_live_volume.setValue(prev_vol)
        self.player.slider_live_volume.blockSignals(False)
        self.engine.set_live_volume(prev_vol / 100.0)
        self._suppress_play_log = False

    def _on_dance_program_changed(self, code: str):
        """BL-132: Sequenz-Filter auf aktuelles Tanzprogramm setzen (opt-out via INI).

        Liest sequence_limit_to aus dance_programs und setzt den Combo-Filter
        per Teaching-Order-Wert (UserRole) — kein Textmatch noetig.
        """
        if not hasattr(self, "sequences_widget"):
            return
        for row in self.db.get_all_dance_programs():
            if row[1] == code:
                seq_limit_to = row[5] if len(row) > 5 else None
                # BL-190: Contains-Vorschlaege nach dem gewaehlten Programm ordnen
                # (unabhaengig vom Auto-Sync des Limit-Filters).
                self.sequences_widget.set_program_sort_to(seq_limit_to)
                # MS50: Programm-Filter laeuft jetzt ueber die Band-Menge der Lokation
                # (set_program_bands in _set_current_location). Das alte Schwellwert-
                # Auto-Sync entfaellt, sonst wuerde doppelt (und mit veraltetem
                # max_teaching_order) gefiltert. Der Limit-Combo bleibt als manueller
                # Zusatzfilter erhalten.
                break

    def _ensure_primary_channel(self):
        """Primaerkanal sicherstellen bevor irgendwo engine.play() direkt aufgerufen wird.

        Muss VOR jedem direkten engine.play()-Aufruf ausserhalb des Player-Widgets
        stehen, damit der Sekundaerkanal (Audition) nie versehentlich fuer andere
        Abspiel-Aktionen (Loop Finder, QE-Preview, ...) verwendet wird.
        """
        if self.player._audition_active:
            self.player._exit_audition()  # ruft _on_player_exit_audition() intern auf

    def _refresh_last_played(self):
        """Holt Zuletzt-Gespielt-Daten fuer die aktuelle Lokation und aktualisiert Songliste + Playlist."""
        _t0 = perf_start()
        location_id = self._current_location.id if self._current_location else None
        last_played_map = self.db.get_last_played_map(location_id)
        _t1 = perf_split("_refresh_last_played.db", _t0)
        self.song_list.set_last_played_map(last_played_map)
        _t2 = perf_split("_refresh_last_played.song_list", _t1)
        self.playlist_manager.set_last_played_map(last_played_map)
        _t3 = perf_split("_refresh_last_played.planner", _t2)
        # Evening Planner: Lokation merken (Lazy-Init liefert sie nach)
        self._ep_location_id = location_id
        if self.evening_planner is not None:
            self.evening_planner.set_location(location_id)
        perf_split("_refresh_last_played.evening_planner", _t3)

    # ---- Playlist / Auto-Advance ----

    def _apply_loop_settings_to_engine(self, entry):
        """BL-164: Reicht loop_count + Cut eines Playlist-Eintrags an die Engine.

        Zentral, damit Song-Laden UND nachtraegliche Dialog-Aenderung denselben
        Pfad nutzen. Der Cut greift in der Engine nur bei loop_count>=2; ohne Cut
        oder ohne BPM wird 0 gesetzt (identisch zum alten Loop-Verhalten).
        """
        self.engine.set_loop_count(entry.loop_count)
        bpm = entry.song.base_bpm or 0.0
        cut_beats = getattr(entry, 'loop_cut_beats', 0)
        self.engine.set_loop_cut_seconds(
            cut_beats * 60.0 / bpm if (cut_beats > 0 and bpm > 0) else 0)

    def _on_playlist_loop_count_edit(self, row):
        """Loop-Count-Dialog aus dem Playlist-Widget."""
        playlist = self.playlist_widget.get_playlist()
        if row < 0 or row >= len(playlist):
            return
        entry = playlist[row]
        result = show_loop_count_dialog(
            self, entry.song, self.paths,
            default_minutes=self._get_current_target_duration(),
            current_count=entry.loop_count,
            current_cut=entry.loop_cut_beats,
            current_target_min=entry.loop_target_min,
        )
        if result is not None:
            entry.loop_count, entry.loop_cut_beats, entry.loop_target_min = result
            self.playlist_widget.refresh_display()
            self.playlist_manager._refresh_playlist_mirror()
            # BL-164-Fix: Ist der bearbeitete Eintrag der aktuell geladene Song,
            # die Engine SOFORT synchronisieren — sonst greift die Aenderung erst
            # beim naechsten Laden und der Song spielt mit alter Einstellung weiter.
            cur = getattr(self, '_current_song', None)
            if cur is not None and cur.id == entry.song.id:
                self._apply_loop_settings_to_engine(entry)

    def _on_playlist_song_selected(self, entry: PlaylistEntry):
        """Wird aufgerufen wenn ein Song in der Playlist angeklickt wird -> vorladen."""
        import crash_handler as _ch
        _ch.log_action(f"Playlist-Song laden: {entry.song.title or entry.song.filename}")
        filepath = self.paths.find_song_file(entry.song.filename)
        if filepath:
            # Variante C+: dirty Tempo/Pitch des ALTEN Songs sichern.
            # _current_song wird erst in _on_file_loaded umgesetzt — daher hier flushen.
            self._flush_player_values()
            self._load_known_song(entry.song.id, filepath)
        else:
            QMessageBox.warning(
                self, _t("file_not_found_title"),
                _t("file_not_found_short", filename=entry.song.filename)
            )

    def _on_playlist_data_changed(self):
        """Wird aufgerufen wenn die Playlist-Daten im PlaylistWidget geaendert wurden.
        Aktualisiert den Playlist-Spiegel im Manager."""
        self.playlist_manager._refresh_playlist_mirror()

    def _on_manager_confirm(self):
        """Confirm-Button im Planner: Dock schliessen, Playlist fokussieren,
        erstes Lied aktivieren (Caller-Workflow)."""
        import crash_handler as _ch
        _ch.log_action("Planner: Confirm")
        self.player.set_planner_warning(False)
        self.dock_manager.close()
        # Erstes Lied in der Playlist aktivieren
        playlist = self.playlist_widget.get_playlist()
        if playlist:
            self.playlist_widget._on_pl_click(0, 0)

    def _on_notes_visibility(self, visible):
        """Lazy Init: Notizen-Widget beim ersten Oeffnen erstellen."""
        if visible and self.notes_widget is None:
            self.dock_notes.visibilityChanged.disconnect(self._on_notes_visibility)
            QTimer.singleShot(0, self._init_notes)

    def _init_notes(self):
        self.notes_widget = NotesWidget(self.db, app_dir=self.paths.app_dir)
        self.notes_widget.apply_skin(self.skin_mgr)
        # Gespeicherten Zoom wiederherstellen
        saved_zoom = int(self._settings.value("notes/zoom_pct", 100))
        if saved_zoom != 100:
            self.notes_widget.set_zoom(saved_zoom)
        # Vergroesserungsfaktor fuer oberste offene Notiz (Default 4.0)
        saved_factor = self._settings.value("notes/first_note_factor", 4.0)
        try:
            self.notes_widget.set_first_note_factor(float(saved_factor))
        except (TypeError, ValueError):
            pass
        # Default-Einfuegeposition neuer Notizen (Oben/Unten). Der Toggle in
        # der UI aendert das nur fuer die laufende Session, nicht die INI.
        # Der Default wird in _write_ini_defaults() gesaet.
        saved_insert_pos = str(self._settings.value("notes/insert_position", "top"))
        self.notes_widget.set_insert_position(saved_insert_pos)
        self.dock_notes.setWidget(self.notes_widget)
        # Aktuelle Lokation nachliefern, falls bereits gewaehlt
        if self._notes_location_id is not None:
            self.notes_widget.refresh(self._notes_location_id)
        # Shortcode-Ausfuehrung verdrahten
        self.notes_widget.on_shortcode_execute = self._shortcode_dispatch

    def _on_photo_visibility(self, visible):
        """Lazy Init: Photo-Widget beim ersten Oeffnen erstellen."""
        if visible and self.photo_widget is None:
            self.photo_widget = PhotoWidget()
            self.dock_photo.setWidget(self.photo_widget)

    def _on_evening_planner_visibility(self, visible):
        """Lazy Init: Evening-Planner-Widget beim ersten Oeffnen erstellen."""
        if visible and self.evening_planner is None:
            # Signal sofort trennen — setFloating/setWidget koennte sonst
            # re-entrant visibilityChanged ausloesen
            self.dock_evening_planner.visibilityChanged.disconnect(
                self._on_evening_planner_visibility)
            QTimer.singleShot(0, self._init_evening_planner)

    def _init_evening_planner(self):
        # Nur schweben lassen, wenn der Dock (Magnet) auf 'frei' steht —
        # eine angedockte Wahl des Nutzers bleibt erhalten.
        if self.dock_evening_planner.allowedAreas() == Qt.NoDockWidgetArea:
            self.dock_evening_planner.setFloating(True)
        self.evening_planner = EveningPlannerWidget(
            self.db, settings=self._settings, parent=self)
        self.evening_planner.apply_skin(self.skin_mgr)
        self.evening_planner.sig_export_to_playlist.connect(self._on_ep_export_to_playlist)
        self.evening_planner.sig_export_to_notes.connect(self._on_ep_export_to_notes)
        self.dock_evening_planner.setWidget(self.evening_planner)
        # Ausstehenden Zustand nachliefern (Start-Datum, Tips-Zahl, Lokation)
        if self._start_date is not None:
            self.evening_planner.set_start_date(self._start_date)
        if self._ep_planned_tips:
            self.evening_planner.set_planned_tips(self._ep_planned_tips)
        if self._ep_location_id is not None:
            self.evening_planner.set_location(self._ep_location_id)

    def _preload_evening_planner(self):
        """Baut den Evening Planner nach dem Start im Hintergrund vor, damit beim
        ersten Oeffnen kein leeres Platzhalter-Fenster kurz aufblitzt. No-op, wenn
        er durch frueheres Oeffnen bereits existiert."""
        if self.evening_planner is not None:
            return
        # Visibility-Handler trennen (wie im Lazy-Pfad), damit setFloating/
        # setWidget in _init_evening_planner kein re-entrantes visibilityChanged
        # ausloest.
        try:
            self.dock_evening_planner.visibilityChanged.disconnect(
                self._on_evening_planner_visibility)
        except (TypeError, RuntimeError):
            pass
        self._init_evening_planner()

    def _on_reports_visibility(self, visible):
        """Lazy Init: Reports-Widget beim ersten Oeffnen erstellen."""
        if visible and self.reports_widget is None:
            # Signal sofort trennen — setFloating(True) wuerde sonst re-entrant visibilityChanged ausloesen
            self.dock_reports.visibilityChanged.disconnect(self._on_reports_visibility)
            QTimer.singleShot(0, self._init_reports)

    def _init_reports(self):
        # Nur schweben lassen, wenn der Dock (Magnet) auf 'frei' steht —
        # eine angedockte Wahl des Nutzers bleibt erhalten.
        if self.dock_reports.allowedAreas() == Qt.NoDockWidgetArea:
            self.dock_reports.setFloating(True)
        self.reports_widget = ReportsWidget(self.db, paths=self.paths)
        self.reports_widget.set_date_format(self._date_format)
        self.dock_reports.setWidget(self.reports_widget)
        self.tutorial_engine.register_widget("reports", self.reports_widget)

    def _on_potential_visibility(self, visible):
        """Lazy Init: Potential-Widget beim ersten Oeffnen erstellen."""
        if visible and self.potential_widget is None:
            # Signal sofort trennen — setFloating(True) wuerde sonst re-entrant visibilityChanged ausloesen
            self.dock_potential.visibilityChanged.disconnect(self._on_potential_visibility)
            QTimer.singleShot(0, self._init_potential)
        elif visible and self.potential_widget is not None:
            self.potential_widget.refresh()

    def _init_potential(self):
        self.dock_potential.setFloating(True)
        self.potential_widget = PotentialWidget(
            self.db, paths=self.paths, settings=self._settings)
        self.potential_widget.on_navigate_song = self._on_potential_navigate_song
        self.potential_widget.on_navigate_sync = self._on_potential_navigate_sync
        self.potential_widget.on_navigate_beatsnap = self._on_potential_navigate_beatsnap
        self.potential_widget.on_navigate_location = self._on_location_button_clicked
        self.potential_widget.on_play_song = self._on_qe_play_song
        self.potential_widget.on_stop_song = self._on_qe_stop_song
        self.potential_widget.on_bulk_done = self._on_potential_bulk_done
        self.potential_widget.paths = self.paths
        self.dock_potential.setWidget(self.potential_widget)
        self.tutorial_engine.register_widget("potential", self.potential_widget)
        self.potential_widget.refresh()

    def _on_stats_visibility(self, visible):
        """Lazy Init: Stats-Widget beim ersten Oeffnen erstellen."""
        if visible and self.stats_widget is None:
            self.dock_stats.visibilityChanged.disconnect(self._on_stats_visibility)
            QTimer.singleShot(0, self._init_stats)
        elif visible and self.stats_widget is not None:
            self.stats_widget._refresh()

    def _init_stats(self):
        self.stats_widget = StatsWidget(self.db)
        self.stats_widget.on_navigate_song   = self._on_stats_navigate_song
        self.stats_widget.on_add_to_playlist = self._add_song_to_playlist
        self.stats_widget.on_add_to_notes    = self._notes_insert_song_shortcode
        self.stats_widget.on_song_rating_changed = self._on_song_rating_changed
        self.dock_stats.setWidget(self.stats_widget)

    def _on_stats_navigate_song(self, song_id):
        """Navigiert zum Song und bringt die Songliste in den Vordergrund."""
        self._on_song_selected(song_id)
        self.dock_list.raise_()

    def _on_manager_visibility_changed(self, visible):
        """Wenn der Playlist-Manager geschlossen wird (X-Button),
        Rules-Trigger feuern."""
        if visible:
            self.playlist_manager.load_permanent_filters()
        else:
            self.rule_engine.fire_trigger("manager_closed")

    def _focus_playlist(self):
        """Playlist-Tab in den Vordergrund holen (naechster Schritt im Caller-Workflow)."""
        self.dock_playlist.raise_()
        self.dock_playlist.widget().setFocus()

    def _on_manual_stop(self):
        """User hat manuell Stop gedrueckt — Trigger feuern.
        Auto-Advance wird jetzt ueber die Rule 'sys_stop_auto_advance' gesteuert."""
        self._was_playing = False
        self._trigger_song_stopped()

    def _save_feedback_note(self, text: str, loc_id):
        """Speichert eine Feedback-Notiz ans Ende der Notizliste der Lokation."""
        if not text or loc_id is None:
            return
        row = self.db._conn.execute(
            "SELECT MAX(sort_order) FROM notes WHERE location_id = ? AND status != 'deleted'",
            (loc_id,)).fetchone()
        bottom_order = (row[0] or 0) + 1
        self.db.add_note(text, loc_id, note_type="normal", sort_order=bottom_order)
        if self.notes_widget:
            self.notes_widget.refresh()

    def _on_song_rating_changed(self, song_id: int):
        """Nach Quality/ERR-Aenderung via Kontextmenue: Song-Daten-Dock synchronisieren,
        falls dort gerade derselbe Song angezeigt wird. DB ist bereits aktualisiert."""
        cur = getattr(self.song_data, '_current_song', None)
        if not cur or cur.id != song_id:
            return
        fresh = self.db.get_by_id(song_id)
        if fresh is None:
            return
        self.song_data._current_song = fresh
        self.song_data.spin_quality.blockSignals(True)
        self.song_data.spin_quality.setValue(fresh.quality or 0)
        self.song_data.spin_quality.blockSignals(False)
        self.song_data.combo_err.blockSignals(True)
        idx = self.song_data.combo_err.findData(fresh.err or 0)
        if idx >= 0:
            self.song_data.combo_err.setCurrentIndex(idx)
        self.song_data.combo_err.blockSignals(False)

    def _trigger_song_stopped(self):
        """Song-Ende verarbeiten: optional Feedback-Dialog zeigen, dann song_stopped feuern.

        Zentraler Abfangpunkt fuer beide Stopp-Pfade (natuerliches Ende + manueller Stop).
        Der modale Dialog blockiert den Main-Thread, sodass Auto-Advance erst danach laeuft.
        """
        # Start-Countdown bei Liedstop sofort wegnehmen. Das Overlay ist ein
        # StaysOnTop-Fenster; wuerde es passiv erst im 50ms-Tick verschwinden,
        # bliebe eine noch sichtbare Zahl VOR dem gleich folgenden (modalen)
        # Feedback-Dialog stehen.
        self._countdown_overlay.hide_overlay()
        feedback_on = (self._settings.value("feedback/enabled", False, type=bool)
                       and not getattr(self, '_feedback_suppressed_session', False))
        # _in_audition wird hier gelesen und sofort zurueckgesetzt — egal was vorher
        # passierte (_suppress_play_log koennte schon False sein, _in_audition nicht).
        in_audition = self._in_audition
        self._in_audition = False
        # Wartemusik-Latch: einmalig konsumieren -> Feedback-Dialog unterdruecken
        suppress_break_feedback = getattr(self, '_break_music_suppress_feedback', False)
        self._break_music_suppress_feedback = False
        # Wenn Audition aktiv war: Rules wieder aktivieren (gepaart mit dem
        # suspend() aus _on_loop_finder_audition). Wir tun das HIER und nicht
        # in _on_loop_finder_stop, weil dieser song_stopped-Trigger erst
        # NACH dem expliziten Stop vom Perf-Timer erkannt wird — bis dahin
        # soll der Trigger suspended bleiben.
        if in_audition and self.rule_engine.is_suspended:
            self.rule_engine.resume("loop_finder_audition")
        if (feedback_on and not in_audition and not suppress_break_feedback
                and getattr(self, '_current_song', None)):
            loc_id = self._current_location.id if self._current_location else None
            dlg = FeedbackDialog(self._current_song, self, location_id=loc_id)
            result = dlg.exec()
            # Session-Suppression wirkt unabhaengig von Accept/Cancel
            if dlg.suppress_session:
                self._feedback_suppressed_session = True
            if result == QDialog.Accepted:
                new_q = dlg.quality
                new_e = dlg.err
                if new_q != self._current_song.quality:
                    self.db.update_song_simple_field(
                        self._current_song.id, 'quality', new_q)
                    self._current_song.quality = new_q
                    self.song_data.spin_quality.blockSignals(True)
                    self.song_data.spin_quality.setValue(new_q)
                    self.song_data.spin_quality.blockSignals(False)
                if new_e != self._current_song.err:
                    self.db.update_song_simple_field(
                        self._current_song.id, 'err', new_e)
                    self._current_song.err = new_e
                    self.song_data.combo_err.blockSignals(True)
                    idx = self.song_data.combo_err.findData(new_e)
                    if idx >= 0:
                        self.song_data.combo_err.setCurrentIndex(idx)
                    self.song_data.combo_err.blockSignals(False)
                if dlg.note_text and loc_id is not None:
                    self._save_feedback_note(dlg.note_text, loc_id)
        if in_audition:
            # Im Audition-Modus (Loop-Finder-Audition, Player-Audition BL-074):
            # keine song_stopped-Rules feuern. Auto-Advance, Warn-Reset etc.
            # sollen beim Vorhoeren komplett ausbleiben.
            print("[Rules] song_stopped uebersprungen (Audition aktiv)")
            return
        self.rule_engine.fire_trigger("song_stopped")

    def _do_auto_advance(self):
        """Auto-Advance (Main-Thread): aktuellen Song als 'played' markieren,
        naechsten unbearbeiteten Song vorladen (nicht abspielen)."""
        # TIC-0026: Guard — DB koennte durch closeEvent bereits geschlossen sein
        if not self.db.is_open():
            return
        playlist = self.playlist_widget.get_playlist()
        if not playlist:
            return

        # Falls current_index nicht gesetzt: aktuellen Song in Playlist suchen
        ci = self.playlist_widget.get_current_index()
        if ci < 0 and self._current_song:
            for idx, entry in enumerate(playlist):
                if entry.song.id == self._current_song.id and not entry.played:
                    self.playlist_widget._current_index = idx
                    ci = idx
                    break

        if ci < 0:
            # Song nicht in Playlist → kein Auto-Advance
            return

        # Aktuellen Song als gespielt markieren
        self.playlist_widget.mark_current_played()

        # Naechsten unbearbeiteten Song suchen
        next_idx = self.playlist_widget.get_next_unplayed_index()
        if next_idx < 0:
            print("[P21] Playlist: Alle Songs abgespielt")
            return

        entry = self.playlist_widget.advance_to(next_idx)
        if entry:
            filepath = self.paths.find_song_file(entry.song.filename)
            if filepath:
                self._load_known_song(entry.song.id, filepath)
                print(f"[P21] Auto-Advance: #{next_idx + 1} '{entry.song.title}' vorgeladen")
            else:
                print(f"[P21] Auto-Advance: Datei nicht gefunden: {entry.song.filename}")

    # ---- Auto-Save ----

    def _flush_player_values(self):
        """Schreibt dirty Tempo/Pitch des AKTUELLEN _current_song in die DB.

        Wird aufgerufen:
          - vor jedem Song-Wechsel (Songliste, Playlist, QE, Drag&Drop)
          - im closeEvent
        Idempotent — wenn nichts dirty ist, passiert nichts.

        WICHTIG: muss VOR dem Umsetzen von _current_song laufen, sonst wuerde
        die Aenderung dem NEUEN Song zugeschrieben (Snapshot-Leak vermeiden).
        """
        self.player._flush_tempo()
        self.player._flush_pitch()

    def _save_current_song(self):
        """Kompatibilitaets-Wrapper. Variante C+ verwendet _flush_player_values."""
        self._flush_player_values()

    # ---- DB-Integration ----

    def _on_file_loaded(self, filepath):
        """Wird aufgerufen wenn eine MP3 geladen wurde."""
        # Datei-Wechsel (Browse-Button): Song per ID laden, nicht per basename
        file_change_id = getattr(self, '_file_change_song_id', None)
        self._file_change_song_id = None
        pending = self._pending_load
        self._pending_load = None

        if file_change_id:
            # Datei-Wechsel oder Musik-Variante fuer denselben Song — Lyric-Variante beibehalten
            song = self.db.get_by_id(file_change_id)
            print(f"[P32] Datei-Wechsel: Song #{song.id} '{song.title}' "
                  f"mit neuer Datei geladen")
        else:
            # Neuer Song — Lyric-Variante zuruecksetzen
            self._lyric_variant_filename = None
            # Variante C+: dirty Tempo/Pitch des ALTEN Songs noch sichern.
            # _current_song ist hier noch der ALTE Song — der Flush trifft den richtigen.
            self._flush_player_values()
            # intern#106: Aus Songliste/Playlist ist der Song bekannt -> per ID.
            # Sonst (Drag&Drop, Oeffnen) erst ueber den relativen Pfad suchen:
            # nur per Basename wuerde fuer Songs aus Unterordnern ein
            # Doppelgaenger mit Default-Werten angelegt.
            song = None
            if pending and pending[1] == filepath:
                song = self.db.get_by_id(pending[0])
            if song is None:
                song = self.db.get_or_create_for_file(
                    self.paths.to_relative_filename(filepath))

        self._current_song = song
        self._current_music_filename = os.path.basename(filepath)
        self._current_filepath = filepath     # aufgeloester Pfad fuer Body-Detektor
        self._countdown_singing_start = None  # Cache bei Song-Wechsel leeren

        if song.loop_out == 0.0:
            song.loop_out = self.engine.get_original_duration()

        self.player.apply_song_settings(song)
        self.player.set_title(song.title)
        # BL-138: Plattenlabel (z.B. "DGR 014") rechts über dem Status anzeigen
        self.player.set_label_info(song.label)

        self.loop_widget.apply_song_settings(song)
        self.loop_widget.set_song_info(filepath, bpm=song.base_bpm)

        if self.loop_finder is not None:
            self.loop_finder.set_song_info(filepath, bpm=song.base_bpm,
                                           loop_in=song.loop_in,
                                           loop_out=song.loop_out)

        self.song_data.load_song(song)

        if self._lyric_variant_filename:
            self.lyrics_widget.load_by_filename(self._lyric_variant_filename)
        else:
            self.lyrics_widget.load_song(song)
        self._push_lyrics_sync_identity(offer_copy=True)

        # Pattern-Songs: Loop standardmaessig aktivieren
        if song.is_pattern:
            self.engine.set_loop_active(True)
            self.loop_widget.chk_loop.setChecked(True)
        else:
            self.engine.set_loop_active(False)
            self.loop_widget.chk_loop.setChecked(False)

        # Loop-Count aus Playlist-Entry uebernehmen (falls vorhanden)
        pl_entry = self.playlist_widget.get_current_entry()
        if pl_entry and pl_entry.song.id == song.id:
            self._apply_loop_settings_to_engine(pl_entry)
        else:
            self.engine.set_loop_count(0)  # Endlos (Standard)
            self.engine.set_loop_cut_seconds(0)

        # Hinweis: "Zuletzt gespielt" wird NICHT beim Laden gesetzt, sondern
        # erst in _on_play_started() → _refresh_last_played(), wenn wirklich
        # abgespielt wird. Nur Selektieren/Laden zählt nicht als Play.
        print(f"[P21] Song geladen: #{song.id} '{song.title}' "
              f"({os.path.basename(filepath)})"
              f" [Loop={'AN' if song.is_pattern else 'AUS'}]")
        self.rule_engine.fire_trigger("song_changed")

    def _on_song_file_changed(self, filepath):
        """Callback: Neue Audio-Datei im Song-Daten-Widget gewaehlt — laden.

        Setzt _file_change_song_id damit _on_file_loaded den Song per ID
        laedt statt per basename (basename kann bei Unterordnern abweichen).
        """
        self._file_change_song_id = self._current_song.id
        self.player.load_from_list(filepath)

    def _load_known_song(self, song_id: int, filepath: str):
        """Laedt die Datei eines bekannten Songs; _on_file_loaded uebernimmt
        ihn dann per ID statt ihn ueber den Dateinamen zu suchen (intern#106)."""
        self._pending_load = (song_id, filepath)
        self.player.load_from_list(filepath)

    def _on_song_selected(self, song_id, offer_copy=True):
        """Song aus der Songliste laden — ueber PathManager suchen.

        offer_copy: ob nach dem Laden interaktiv angeboten wird, Sync-Punkte
        einer anderen Variante zu uebernehmen (nur relevant bei Singing-Lyrics).
        Bei manueller Auswahl True; automatische Lade-Aktionen (BL-181 Rule
        "Load Song") setzen False, damit kein modaler Dialog den Live-Betrieb
        blockiert.
        """
        song = self.db.get_by_id(song_id)
        if not song:
            return
        import crash_handler as _ch
        _ch.log_action(f"Song aus Liste: {song.title or song.filename}")

        # Song-Datei ueber PathManager suchen (portabel!)
        filepath = self.paths.find_song_file(song.filename)

        # Song-Daten immer sofort setzen — unabhaengig davon ob der
        # Player-Load gelingt. Sonst bleibt _current_song=None wenn die
        # MP3 nicht ladbar ist, und Loeschen/Bearbeiten sind blockiert.
        # Variante C+: dirty Tempo/Pitch des ALTEN Songs noch schnell flushen,
        # BEVOR _current_song auf den NEUEN umgesetzt wird.
        self._flush_player_values()
        self._current_song = song
        self._current_music_filename = song.filename
        self._lyric_variant_filename = None  # Varianten-Auswahl auf Standard zuruecksetzen
        self.song_data.load_song(song)
        self.lyrics_widget.load_song(song)
        self._push_lyrics_sync_identity(offer_copy=offer_copy)
        self.player.set_title(song.title)
        # BL-138: Plattenlabel (z.B. "DGR 014") rechts über dem Status anzeigen
        self.player.set_label_info(song.label)

        if filepath:
            self._load_known_song(song.id, filepath)
        else:
            self.statusBar().showMessage(
                _t("file_not_found_msg", filename=song.filename,
                   music_dir=self.paths.music_dir, app_dir=self.paths.app_dir),
                5000)

    def _on_song_activated(self, song_id):
        """Doppelklick in der Songliste: Song laden (falls noetig) und direkt
        abspielen. Der vorausgehende Einfachklick (cellClicked) hat den Song
        i.d.R. schon geladen; wir stellen sicher, dass der richtige Song
        geladen ist, und starten dann die Wiedergabe."""
        if not self._current_song or self._current_song.id != song_id:
            self._on_song_selected(song_id)
        # Nur starten, wenn tatsaechlich eine Datei geladen wurde.
        if self.player.engine.is_loaded():
            self.player._on_play()

    def _on_player_tempo_changed(self, tempo_factor):
        self.song_data.update_tempo(tempo_factor)

    def _on_player_pitch_changed(self, pitch_semitones):
        self.song_data.update_pitch(pitch_semitones)

    def _on_song_saved(self):
        self.song_list.refresh()
        self.playlist_manager.refresh()
        if self._current_song:
            self._current_song = self.db.get_by_id(self._current_song.id)
            # Lyric-Variante beibehalten falls aktiv, sonst Standard laden
            if self._lyric_variant_filename:
                self.lyrics_widget.load_by_filename(self._lyric_variant_filename)
            else:
                self.lyrics_widget.load_song(self._current_song)
            self._push_lyrics_sync_identity(offer_copy=False)
            # BPM-Anzeige im Player aktualisieren (z.B. nach Auto-BPM)
            self.player.apply_song_settings(self._current_song)

    def _on_potential_bulk_done(self):
        """Einmaliger Refresh nach einem Bulk-Lauf (Loop-Optimieren / Auto-Loop / BeatSnap).

        Laeuft genau EINMAL am Bulk-Ende auf dem Main-Thread. Frischt die
        Song-Liste auf und uebernimmt die neuen Loop-Werte des aktuell geladenen
        Songs in die Anzeige (Loop-Widget, Player-Marken, Song-Data, Loop-Finder),
        ohne das Audio neu zu laden.
        """
        self.song_list.refresh()
        if not self._current_song:
            return
        fresh = self.db.get_by_id(self._current_song.id)
        if not fresh:
            return
        self._current_song = fresh
        # Engine-Loop-Punkte + Anzeige des aktuellen Songs aktualisieren
        self.loop_widget.apply_song_settings(fresh)
        self.loop_widget.update_display()
        self.player.refresh_loop_markers()
        self.song_data.refresh_loop_values(fresh.loop_in, fresh.loop_out)
        if self.loop_finder is not None:
            self.loop_finder.update_existing_marks(fresh.loop_in, fresh.loop_out)

    def _on_lyric_variant(self, filename: str):
        """Lyric-Variante ausgewaehlt — Lyrics-Widget mit alternativer Datei laden."""
        self._lyric_variant_filename = filename if filename else None
        self.lyrics_widget.load_by_filename(filename)
        self._push_lyrics_sync_identity(offer_copy=True)

    # ---- BL-160: Lyrics-Sync-Identitaet (Song x Musik-Variante x Lyric-Variante) ----

    def _resolve_variant_slot(self, song_id, kind: str, name, primary) -> int:
        """Ermittelt den Variantenslot (1 = Primaer, 2+ = Variante) fuer eine
        Datei, indem ihr Basename gegen die Primaerdatei und die music_N_file/
        lyric_N_file-Eintraege verglichen wird."""
        if not name:
            return 1
        base = os.path.basename(name)
        if primary and os.path.basename(primary) == base:
            return 1
        import re as _re
        try:
            props = self.db.get_properties(song_id)
        except Exception:
            return 1
        for k, v in props.items():
            m = _re.match(rf'^{kind}_(\d+)_file$', k)
            if m and v and os.path.basename(v) == base:
                return int(m.group(1))
        return 1

    def _push_lyrics_sync_identity(self, offer_copy: bool = False):
        """Reicht die aktuelle (Song x Musik x Lyric)-Identitaet ans Lyrics-Widget
        weiter, damit dieses die passenden Sync-Punkte laedt."""
        song = self._current_song
        if not song:
            self.lyrics_widget.set_sync_identity(None, 1, 1)
            return
        music_name = getattr(self, '_current_music_filename', None) or song.filename
        lyric_name = self._lyric_variant_filename or song.lyrics_file
        ms = self._resolve_variant_slot(song.id, 'music', music_name, song.filename)
        ls = self._resolve_variant_slot(song.id, 'lyric', lyric_name, song.lyrics_file)
        self.lyrics_widget.set_sync_identity(song.id, ms, ls)
        if offer_copy:
            self.lyrics_widget.check_offer_copy_sync()

    def _on_lyric_sync_mode(self, active: bool):
        """Sync-Modus an/aus: Testlauf ohne Rules + ohne History-Logging
        (gleicher Mechanismus wie Audition/Loop-Finder)."""
        if active:
            self._suppress_play_log = True           # kein log_play in die Historie
            self.rule_engine.suspend("lyric_sync")   # Rules komplett aus (z.B. Auto-Advance)
        else:
            self._suppress_play_log = False
            self.rule_engine.resume("lyric_sync")    # genau ein resume() zum suspend()

    def _on_singing_marks_changed(self):
        """Sync-Marken wurden neu gesetzt → Start-Countdown-Cache leeren, damit
        er beim naechsten Tick den neuen singing_start aus der DB liest (sonst
        zaehlt er weiter zum alten Wert). Nur relevant fuer den aktuellen Song."""
        if getattr(self, "lyrics_widget", None) is None:
            return
        cur = getattr(self, "_current_song", None)
        if cur is not None and self.lyrics_widget._sync_song_id == cur.id:
            self._countdown_singing_start = None

    def _on_request_body_detect(self):
        """Startet die automatische Singing-Body-Erkennung im Worker-Thread.
        Ergebnis geht via apply_detected_body() zurueck an das Lyrics-Widget."""
        filepath = getattr(self, "_current_filepath", None)
        song = getattr(self, "_current_song", None)
        if not filepath or not os.path.isfile(filepath) or song is None:
            self.lyrics_widget.apply_detected_body(
                {"ok": False, "reason": _t("lyric_sync_detect_no_audio")})
            return
        # "Bitte warten"-Overlay wie beim Loop-Finder: signalisiert, dass die
        # Analyse laeuft, damit der Nutzer nicht weiterklickt.
        self._body_detect_overlay = QLabel(_t("lyric_sync_detecting"), self)
        self._body_detect_overlay.setAlignment(Qt.AlignCenter)
        self._body_detect_overlay.setStyleSheet(
            "background: rgba(0,0,0,180); color: white; font-size: 16px; "
            "font-weight: bold; padding: 20px 40px; border-radius: 8px;")
        self._body_detect_overlay.adjustSize()
        cx = (self.width() - self._body_detect_overlay.width()) // 2
        cy = (self.height() - self._body_detect_overlay.height()) // 2
        self._body_detect_overlay.move(cx, cy)
        self._body_detect_overlay.show()
        self._body_detect_overlay.raise_()

        bpm_hint = getattr(song, "base_bpm", None)
        self._body_worker = SingingBodyWorker(filepath, bpm_hint=bpm_hint)
        self._body_worker.done.connect(self._on_body_detect_done)
        self._body_worker.error.connect(self._on_body_detect_error)
        # TIC-0029: Referenz erst beim echten Thread-Ende freigeben.
        # Overlay zusaetzlich am Thread-Ende schliessen (Sicherheitsnetz).
        self._body_worker.finished.connect(self._dismiss_body_detect_overlay)
        self._body_worker.finished.connect(
            lambda: setattr(self, "_body_worker", None))
        self._body_worker.start()

    def _dismiss_body_detect_overlay(self):
        """Entfernt das 'Songblock wird erkannt'-Overlay (idempotent)."""
        overlay = getattr(self, "_body_detect_overlay", None)
        if overlay:
            overlay.deleteLater()
            self._body_detect_overlay = None

    def _on_body_detect_done(self, result):
        # Overlay schliessen BEVOR apply_detected_body ggf. einen modalen
        # Bestaetigungsdialog oeffnet — sonst haengt es dahinter.
        self._dismiss_body_detect_overlay()
        self.lyrics_widget.apply_detected_body(result)

    def _on_body_detect_error(self, msg):
        self._dismiss_body_detect_overlay()
        self.lyrics_widget.apply_detected_body({"ok": False, "reason": msg})

    def _add_song_to_playlist(self, song_id, mode: str = ""):
        """Song per Songlisten-Button oder Kontextmenü zur Playlist hinzufügen.
        mode='P'/'S' erzwingt den Typ (z.B. Slot-Rolle aus dem Evening Planner);
        ohne mode wird er aus den Song-Tags bestimmt."""
        song = self.db.get_by_id(song_id)
        if not song:
            return
        if mode not in ("P", "S"):
            mode = self.playlist_manager._determine_mode(song)
        self.playlist_widget.add_entry(PlaylistEntry(song=song, mode=mode))
        self.playlist_manager._refresh_playlist_mirror()

    def _on_ep_export_to_playlist(self, song_ids: list):
        """Evening Planner → Playlist: bestätigte Songs in Tip-Reihenfolge übernehmen.
        song_ids: Liste von (song_id, mode) Tupeln ('P'/'S') oder plain int
        (Rueckwaertskompatibilitaet)."""
        if not song_ids:
            QMessageBox.information(
                self,
                _t("ep_export_title"),
                _t("ep_export_none_hint"),
            )
            return
        for item in song_ids:
            if isinstance(item, tuple):
                song_id, mode = item
                self._add_song_to_playlist(song_id, mode=mode)
            else:
                self._add_song_to_playlist(item)
        n = len(song_ids)
        QMessageBox.information(
            self,
            _t("ep_export_title"),
            _t("ep_export_playlist_ok").format(n=n),
        )

    def _export_entries_to_notes(self, entries: list, title_key: str,
                                 empty_key: str = ""):
        """Gemeinsamer Kern fuer 'Songs zu Notizen uebernehmen' (Playlist UND
        Evening Planner): baut Shortcode-Texte in GENAU der uebergebenen
        Reihenfolge und reicht sie an notes_widget.add_notes() weiter, das
        die End-Reihenfolge sowie die Toggle-Position (Oben/Unten) anwendet.
        entries: Liste von (title, mode)-Tupeln ('P'/'S') oder plain str, in
        der gewuenschten Anzeige-Reihenfolge oben->unten — der Aufrufer darf
        NICHT selbst umkehren, sonst kollidiert das mit add_notes().
        Keine Vollzugsmeldung: Caller sollen bei der Uebergabe nicht extra
        die Maus fuer einen Bestaetigungsdialog brauchen, die Notiz ist
        ohnehin sofort sichtbar."""
        if not entries:
            if empty_key:
                QMessageBox.information(self, _t(title_key), _t(empty_key))
            return
        # Location EINMAL vorab prüfen — sonst zeigt der Loop den
        # "keine Lokation"-Dialog einmal pro Song (wirkt wie Endlosschleife).
        if not self._notes_require_location():
            return
        self._notes_ensure_init()
        self.dock_notes.setVisible(True)
        self.dock_notes.raise_()
        texts = []
        for item in entries:
            title, mode = item if isinstance(item, tuple) else (item, "")
            texts.append(self._song_shortcode_text(title, mode))
        self.notes_widget.add_notes(texts)

    def _on_ep_export_to_notes(self, entries: list):
        """Evening Planner → Notizen: bestätigte Songs als [load_song]-Shortcodes eintragen.
        entries: Liste von (title, mode) Tupeln ('P'/'S') oder plain str (Rueckwaertskompatibilitaet)."""
        self._export_entries_to_notes(entries, "ep_export_title", "ep_export_none_hint")

    def _on_pl_export_to_notes(self, entries: list):
        """Playlist → Notizen: markierte (oder alle) Songs als [load_song]-
        Shortcodes eintragen. entries: Liste von (title, mode)-Tupeln ('P'/'S')
        in Playlist-Reihenfolge."""
        self._export_entries_to_notes(entries, "pl_notes_export_title")

    def _on_song_delete_requested(self, song_id):
        """Entf-Taste in der Songliste: Loeschen ueber SongDataWidget."""
        song = self.db.get_by_id(song_id)
        if not song:
            return
        self.song_data.load_song(song)
        self.song_data._on_delete_song()

    def _on_song_deleted(self, song_id):
        """Callback nachdem ein Song geloescht wurde."""
        # Falls der geloeschte Song gerade geladen ist: Player stoppen
        if self._current_song and self._current_song.id == song_id:
            self.player._on_stop()
            self._current_song = None
        self.song_list.refresh()
        self.playlist_manager.refresh()
        if hasattr(self, 'potential_widget') and self.potential_widget:
            self.potential_widget.refresh()

    def _on_engine_song_loaded(self, filepath, duration):
        pass

    # ---- Potential: Navigation ----

    def _on_potential_navigate_song(self, song_id):
        """Navigiert zum Song und zeigt Song-Daten-Tab."""
        self._on_song_selected(song_id)
        self.dock_data.raise_()

    def _on_potential_navigate_sync(self, song_id):
        """Doppelklick aus 'Ohne Liedpunkte' / 'Ohne SyncPunkte': Song laden,
        Lyric-Widget in den Vordergrund holen und Maus + Fokus auf den Sync-Button
        setzen, damit der naechste Schritt (Sync-Modus) direkt griffbereit ist."""
        self._on_song_selected(song_id)
        self.dock_lyrics.raise_()
        btn = getattr(self.lyrics_widget, '_btn_sync', None)
        if btn is None:
            return

        def _place_cursor():
            btn.setFocus(Qt.OtherFocusReason)
            QCursor.setPos(btn.mapToGlobal(btn.rect().center()))
        # Erst nach Layout/Raise positionieren, sonst stimmt die globale Position nicht.
        QTimer.singleShot(0, _place_cursor)

    def _on_qe_play_song(self, song_id):
        """Laedt einen Song fuer das QE-Filler-Vorhören und spielt ihn ab."""
        song = self.db.get_by_id(song_id)
        if not song:
            return
        filepath = self.paths.find_song_file(song.filename)
        if not filepath:
            return
        # Variante C+: dirty Tempo/Pitch des ALTEN Songs vor dem Wechsel sichern.
        self._flush_player_values()
        self._current_song = song
        self._load_known_song(song.id, filepath)
        self._ensure_primary_channel()  # Primaerkanal sicherstellen vor QE-Preview
        QTimer.singleShot(150, lambda: self.player.engine.play()
                          if not self.player.engine.is_playing() else None)

    def _on_qe_stop_song(self):
        """Stoppt die laufende Wiedergabe (QE-Filler-Vorhören)."""
        self.player.engine.stop()

    # ---- Break: Wartemusik (zuletzt gespielter Song, ohne Historie) ----

    def _last_played_song_id(self):
        """Ermittelt die ID des zuletzt gespielten Songs.

        Zuerst der in dieser Sitzung zuletzt gestartete Song, dann die Historie
        der Lokation. Der geladene Song ist nur der letzte Ausweg: nach
        Auto-Advance ist das schon der NAECHSTE Playlist-Song (ohne Lokation
        ist die Historie leer, intern#110).
        """
        if getattr(self, "_last_logged_song_id", None):
            return self._last_logged_song_id
        location_id = self._current_location.id if self._current_location else None
        lpm = self.db.get_last_played_map(location_id)
        if lpm:
            # Wert = Zeitstempel-String (ISO-aehnlich) -> max = zuletzt gespielt
            return max(lpm, key=lambda k: lpm[k])
        if self._current_song:
            return self._current_song.id
        return None

    def _on_break_play_last(self, duration_seconds):
        """Spielt den zuletzt gespielten Song als Wartemusik fuer die Pausendauer.

        Kein Historie-Eintrag (Warteschleifen-Musik). Auto-Stop nach
        duration_seconds. Gibt True zurueck, wenn die Wiedergabe gestartet wurde.
        """
        _t0 = perf_start()
        song_id = self._last_played_song_id()
        if song_id is None:
            return False
        song = self.db.get_by_id(song_id)
        filepath = self.paths.find_song_file(song.filename) if song else None
        if not filepath:
            return False
        _t1 = perf_split("_on_break_play_last: lookup+find_file", _t0)
        self._flush_player_values()
        # Vorher geladenen Song merken (z.B. der per Auto-Advance vorgeladene
        # naechste Playlist-Song) — _on_break_stop_last laedt ihn wieder.
        prev = self._current_song
        self._pre_break_song_id = prev.id if prev and prev.id != song.id else None
        self._current_song = song
        self._break_music_song_id = song.id
        self._load_known_song(song.id, filepath)
        _t2 = perf_split("_on_break_play_last: load_from_list", _t1)
        self._ensure_primary_channel()
        perf_split("_on_break_play_last: ensure_primary_channel", _t2)
        self._suppress_play_log = True      # NICHT in die Historie
        # Kein Feedback-Dialog am Ende der Wartemusik (Latch, zurueckgesetzt in
        # _trigger_song_stopped oder _on_break_stop_last).
        self._break_music_suppress_feedback = True
        # Rules komplett sperren waehrend der Wartemusik (kein Auto-Advance etc.).
        # Nested-Counter: jedes suspend() braucht genau ein resume() (in _on_break_stop_last).
        self.rule_engine.suspend("break_music")
        self._break_music_active = True
        QTimer.singleShot(150, lambda: self.engine.play()
                          if not self.engine.is_playing() else None)
        # Auto-Stop nach Pausendauer
        if self._break_music_timer is not None:
            self._break_music_timer.stop()
        self._break_music_timer = QTimer(self)
        self._break_music_timer.setSingleShot(True)
        self._break_music_timer.timeout.connect(self._on_break_stop_last)
        self._break_music_timer.start(int(max(1.0, duration_seconds) * 1000))
        return True

    def _on_break_started(self, with_music: bool):
        """Pausen-Uhr frisch gestartet -> Trigger 'break_started' (intern#110).

        Deferred: kommt der Start aus einer Rule-Aktion (Start Break), laeuft
        fire_trigger noch und der Loop-Schutz wuerde den Trigger blocken.
        Die Wartemusik-Sperre gilt nicht fuer die Pausen-Trigger.
        """
        self._break_with_music = bool(with_music)
        QTimer.singleShot(0, lambda: self.rule_engine.fire_trigger(
            "break_started", bypass_suspend=("break_music",)))

    def _on_break_finished(self):
        """Countdown bei 0 -> Wartemusik beenden, dann 'break_finished' feuern.

        Wartemusik und Countdown laufen ueber getrennte Timer; der Stopp hier
        verhindert, dass die Folge-Rule (z.B. Auto-Advance -> Play) auf noch
        laufende Wartemusik trifft.
        """
        if self._break_music_active:
            self._on_break_stop_last()
        QTimer.singleShot(0, lambda: self.rule_engine.fire_trigger(
            "break_finished", bypass_suspend=("break_music",)))

    def _on_break_stop_last(self):
        """Stoppt die Wartemusik und stellt das Historie-Logging wieder her."""
        _t0 = perf_start()
        if self._break_music_active:
            self.engine.stop()
            # Das Ende der Wartemusik ist kein Songende: ohne diesen Reset
            # erkennt _update_all im naechsten Tick "Song-Ende" und feuert
            # song_stopped (dann schon ohne Sperre) -> Auto-Advance schaltet
            # weiter, mit break_finished -> Auto-Advance sogar doppelt
            # (intern#110).
            self._was_playing = False
            self._leave_break_music()
            self._restore_pre_break_song()
        else:
            self._leave_break_music()
        perf_log("_on_break_stop_last", _t0)

    def _end_break_on_manual_play(self):
        """Startet der Caller waehrend der Pause von Hand einen Song, ist das
        ein eindeutiges Signal: Die Pause ist vorbei (intern#130, Entscheidung
        David). Laeuft Wartemusik und startet ein ANDERER Song, wird der
        Pausenzustand verworfen (nichts stoppen, nichts nachladen). Eine
        laufende Pausen-Uhr wird zurueckgesetzt, auch ohne Wartemusik.
        'break_finished' feuert dabei NICHT: Die Pause ist abgebrochen, nicht
        abgelaufen, und eine Rule wie "Break Finished -> Play" wuerde sonst
        den gerade gestarteten Song ueberfahren.

        Vorhoeren und Testlaeufe (Audition, Loop-Finder, Sync-Modus,
        ZIP-Vorhoeren) zaehlen nicht als manuelles Play."""
        if getattr(self, "_in_audition", False) or (
                self._suppress_play_log and not self._break_music_active):
            return
        if self._break_music_active:
            if self._current_song.id == self._break_music_song_id:
                return      # Play auf die Wartemusik selbst (z. B. Fortsetzen)
            self._pre_break_song_id = None
            self._leave_break_music()
        if getattr(self, "break_widget", None) is not None:
            self.break_widget.end_break()

    def _leave_break_music(self):
        """Gemeinsamer Ausstieg aus der Wartemusik (Stopp oder manuelles Play):
        Auto-Stop-Timer weg, Historie-Log und Rules wieder frei, Button im
        Break-Widget zuruecksetzen. Stoppt selbst KEIN Audio."""
        if self._break_music_timer is not None:
            self._break_music_timer.stop()
            self._break_music_timer = None
        if self._break_music_active:
            # Der Feedback-Latch wird nicht mehr in _trigger_song_stopped
            # konsumiert, also hier loeschen.
            self._break_music_suppress_feedback = False
            self._suppress_play_log = False
            # Rules wieder freigeben (genau ein resume() zum suspend() in
            # _on_break_play_last)
            self.rule_engine.resume("break_music")
            self._break_music_active = False
            self._break_music_song_id = None
        if getattr(self, 'break_widget', None) is not None:
            self.break_widget.set_music_stopped()

    def _restore_pre_break_song(self):
        """Laedt nach der Wartemusik wieder den Song, der vor der Pause geladen
        war (intern#110). Ohne Abspielen; Laden ist synchron, eine Folge-Rule
        "Play" (z.B. auf Break Finished) spielt also diesen Song."""
        song_id, self._pre_break_song_id = self._pre_break_song_id, None
        if not song_id:
            return
        song = self.db.get_by_id(song_id)
        filepath = self.paths.find_song_file(song.filename) if song else None
        if not filepath:
            return
        self._flush_player_values()
        self._current_song = song
        self._load_known_song(song.id, filepath)

    def _on_potential_navigate_beatsnap(self, song_id):
        """Laedt den Song und oeffnet Beat Snap."""
        self._on_song_selected(song_id)
        # Beat Snap oeffnen (falls Loop-Widget den Button hat)
        if hasattr(self.loop_widget, '_on_beat_snap'):
            self.loop_widget._on_beat_snap()

    # ---- Loop Finder: Callbacks ----

    def _on_loop_finder_apply(self, loop_in, loop_out):
        """Uebernimmt Loop-Vorschlag in den aktuellen Song."""
        if not self._current_song:
            return
        # Loop-Werte in Engine setzen
        self.engine.set_loop_in(loop_in)
        self.engine.set_loop_out(loop_out)
        # Loop-Widget aktualisieren
        self.loop_widget.update_display()
        # Player-Loop-Marken (schwarze Balken) neu setzen — sonst bleiben sie
        # im pausierten Zustand auf den alten Stellen stehen
        self.player.refresh_loop_markers()
        # Loop-Finder-Marken (schwarze Balken) auf die neuen Stellen ziehen
        if self.loop_finder is not None:
            self.loop_finder.update_existing_marks(loop_in, loop_out)
        # Song-Data-Zahlenfelder (Loop-In/Out) nachziehen
        self.song_data.refresh_loop_values(loop_in, loop_out)
        # In DB speichern
        self._current_song.loop_in = loop_in
        self._current_song.loop_out = loop_out
        self.db.save_playback_settings(
            self._current_song.id, loop_in=loop_in, loop_out=loop_out
        )
        # Loop-Tab anzeigen
        self.dock_loop.raise_()
        print(f"[LoopFinder] Loop uebernommen: {loop_in:.1f}s - {loop_out:.1f}s")

    def _on_loop_finder_audition(self, loop_in, loop_out):
        """Audition: 5s vor loop_out starten, Loop aktiv, springt zu loop_in."""
        if not self._current_song:
            return
        self._ensure_primary_channel()  # Primaerkanal sicherstellen
        # Vorherige Loop-Werte merken fuer Restore nach Audition
        self._pre_audition_loop_in = self.engine.loop_in_seconds
        self._pre_audition_loop_out = self.engine.loop_out_seconds
        self._pre_audition_loop_active = self.loop_widget.chk_loop.isChecked()
        # Temporaer Loop-Werte setzen fuer Audition
        self.engine.set_loop_in(loop_in)
        self.engine.set_loop_out(loop_out)
        self.engine.set_loop_active(True)
        # 5 Sekunden vor Loop-Out starten
        preview_start = max(0, loop_out - 5.0)
        self.engine.seek(preview_start)
        self._suppress_play_log = True
        # Rules waehrend Loop-Finder-Audition ausschalten (z.B. Auto-Advance).
        # Nur einmal pro Audition-Session suspendieren — gepaart mit resume()
        # in _on_loop_finder_stop. Flag verhindert mehrfache suspend()-Aufrufe.
        if not getattr(self, "_in_audition", False):
            self.rule_engine.suspend("loop_finder_audition")
        self._in_audition = True
        self.engine.play()
        self.loop_widget.chk_loop.setChecked(True)
        self.loop_widget.update_display()
        print(f"[LoopFinder] Audition: Start {preview_start:.1f}s, "
              f"Loop {loop_in:.1f}s - {loop_out:.1f}s")

    def _init_loop_finder(self):
        """Erstellt den LoopFinder beim ersten Oeffnen (lazy init)."""
        if self.loop_finder is not None:
            return
        self.loop_finder = LoopFinderWidget()
        self.loop_finder._section_bar._skin_mgr = self.skin_mgr
        self.loop_finder._section_bar.update_colors()
        self.loop_finder._waveform.set_colors(self.skin_mgr)
        self.loop_finder.on_apply = self._on_loop_finder_apply
        self.loop_finder.on_audition = self._on_loop_finder_audition
        self.loop_finder.on_stop = self._on_loop_finder_stop
        self.loop_finder.set_presets_dir(self.paths.loop_presets_dir)
        self.dock_loop_finder.setWidget(self.loop_finder)
        # Song-Info nachreichen falls bereits ein Song geladen ist
        filepath = getattr(self.loop_widget, '_current_filepath', None)
        if filepath:
            song = self._current_song
            bpm = song.base_bpm if song else 0
            self.loop_finder.set_song_info(
                filepath, bpm=bpm,
                loop_in=song.loop_in if song else 0.0,
                loop_out=song.loop_out if song else 0.0)
            # Waveform + Sprungbereiche sofort anzeigen (sonst erst nach "Analysieren")
            self.loop_finder._ensure_waveform()
        self.tutorial_engine.register_widget("loop_finder", self.loop_finder)

    def _get_loop_preset_names(self):
        """Preset-Namen fuers Rules-Widget — unabhaengig vom Lazy-Init des Loop
        Finders. Frueher wurde [] geliefert, solange der Dock nie offen war →
        leere Preset-Combo bei der Auto-Loop-Aktion."""
        presets_dir = getattr(self.paths, 'loop_presets_dir', None)
        return LoopFinderWidget.list_preset_names(presets_dir)

    def _get_layout_names(self) -> list:
        """Gibt alle gespeicherten Layout-Namen zurueck (*.ini in skins/)."""
        skins_dir = self.skin_mgr.skins_dir
        if not os.path.isdir(skins_dir):
            return []
        names = []
        for fname in sorted(os.listdir(skins_dir)):
            if fname.lower().endswith(".ini"):
                names.append(fname[:-4])
        return names

    def _on_loop_finder_visibility(self, visible):
        """Beim ersten Oeffnen: Loop Finder erstellen (lazy). Beim Schliessen: Audition stoppen."""
        if visible:
            self._init_loop_finder()
            # Waveform anzeigen falls Song bereits geladen aber Waveform noch nicht gerendert
            if self.loop_finder and not self.loop_finder._waveform_loaded:
                self.loop_finder._ensure_waveform()
        else:
            if self.loop_finder is not None:
                self.loop_finder._stop_audition_timer()
            if self.engine.is_playing():
                self._on_loop_finder_stop()

    def _on_loop_finder_stop(self):
        """Stoppt Audition und stellt vorherige Loop-Werte wieder her."""
        self._suppress_play_log = False
        self._ensure_primary_channel()  # falls Player-Audition noch aktiv war
        self.engine.stop()
        # _in_audition NICHT hier zuruecksetzen — _trigger_song_stopped braucht das
        # Flag noch fuer (a) Feedback-Dialog-Skip und (b) Rule-Suspension (Auto-Advance
        # darf bei Audition-Ende nicht feuern). Resume des Rule-Suspends erfolgt
        # ebenfalls dort, damit der song_stopped-Trigger noch suspended ist.
        # Vorherige Loop-Werte zuruecksetzen
        pre_in = getattr(self, '_pre_audition_loop_in', None)
        pre_out = getattr(self, '_pre_audition_loop_out', None)
        pre_active = getattr(self, '_pre_audition_loop_active', False)
        if pre_in is not None:
            self.engine.set_loop_in(pre_in)
            self.engine.set_loop_out(pre_out)
            self.engine.set_loop_active(pre_active)
            self.loop_widget.chk_loop.setChecked(pre_active)
            self.loop_widget.update_display()
            self._pre_audition_loop_in = None
            self._pre_audition_loop_out = None

    # ---- Rules Engine Integration ----

    def _on_player_pause(self):
        """Callback: User hat Pause gedrueckt."""
        self.rule_engine.fire_trigger("song_paused")

    def _get_rule_context(self) -> dict:
        """Liefert den aktuellen App-Zustand fuer die Rules-Engine."""
        song = self._current_song
        loc = self._current_location
        has_lyrics = False
        if song and hasattr(song, 'lyrics_path') and song.lyrics_path:
            has_lyrics = True
        elif song and hasattr(song, 'lyrics_file') and song.lyrics_file:
            has_lyrics = True
        loop_set = False
        if song and hasattr(song, 'loop_in') and hasattr(song, 'loop_out'):
            orig_dur = self.engine.get_original_duration() if self.engine.is_loaded() else 0
            loop_set = (song.loop_in > 0.1 or
                        (song.loop_out > 0 and orig_dur > 0 and
                         abs(song.loop_out - orig_dur) > 0.5))
        bpm_set = bool(song and getattr(song, 'base_bpm', 0) > 0)
        # BL-205: Gesamtlaenge des geladenen Songs in Sekunden (0 = nichts geladen)
        song_length = self.engine.get_original_duration() if self.engine.is_loaded() else 0
        # Spieldauer in Sekunden
        play_elapsed = 0
        if self.player._play_start_time is not None:
            import time as _t2
            play_elapsed = _t2.time() - self.player._play_start_time

        return {
            "song_type_is_singing": bool(song and getattr(song, 'is_singing', False)),
            "song_type_is_patter": bool(song and getattr(song, 'is_pattern', False)),
            "lyrics_available": has_lyrics,
            "lyrics_not_available": not has_lyrics,
            "loop_set": loop_set,
            "loop_not_set": not loop_set,
            "bpm_set": bpm_set,
            "bpm_not_set": not bpm_set,
            "location_selected": loc is not None,
            "location_not_selected": loc is None,
            "play_elapsed_seconds": play_elapsed,
            "song_length_seconds": song_length,
            "break_with_music": getattr(self, "_break_with_music", False),
        }

    def _register_rule_conditions(self):
        """Registriert alle Condition-Evaluatoren.
        Signatur: fn(context: dict, params: dict) -> bool
        """
        re = self.rule_engine
        re.register_condition("song_type_is_singing",
                              lambda ctx, p: ctx.get("song_type_is_singing", False))
        re.register_condition("song_type_is_patter",
                              lambda ctx, p: ctx.get("song_type_is_patter", False))
        re.register_condition("lyrics_available",
                              lambda ctx, p: ctx.get("lyrics_available", False))
        re.register_condition("lyrics_not_available",
                              lambda ctx, p: ctx.get("lyrics_not_available", False))
        re.register_condition("loop_set",
                              lambda ctx, p: ctx.get("loop_set", False))
        re.register_condition("loop_not_set",
                              lambda ctx, p: ctx.get("loop_not_set", False))
        re.register_condition("bpm_set",
                              lambda ctx, p: ctx.get("bpm_set", False))
        re.register_condition("bpm_not_set",
                              lambda ctx, p: ctx.get("bpm_not_set", False))
        re.register_condition("location_selected",
                              lambda ctx, p: ctx.get("location_selected", False))
        re.register_condition("location_not_selected",
                              lambda ctx, p: ctx.get("location_not_selected", False))
        # Timer-Bedingung mit Minutenparameter
        re.register_condition("play_duration_above",
                              lambda ctx, p: ctx.get("play_elapsed_seconds", 0)
                              >= p.get("minutes", 5) * 60)
        # BL-205: Songlaenge über/unter Schwellwert (mm:ss)
        re.register_condition("song_length", self._eval_song_length)
        # intern#110: Art der letzten Pause (all / without_music / with_music)
        re.register_condition("break_type", self._eval_break_type)

    @staticmethod
    def _eval_break_type(ctx, p) -> bool:
        kind = p.get("kind", "all")
        if kind == "with_music":
            return bool(ctx.get("break_with_music", False))
        if kind == "without_music":
            return not ctx.get("break_with_music", False)
        return True

    @staticmethod
    def _eval_song_length(ctx, p) -> bool:
        """BL-205: Vergleicht die Gesamtlaenge des Songs gegen einen mm:ss-Wert.

        operator 'above' -> Song ist mindestens so lang (>=),
        operator 'below' -> Song ist kuerzer (<). Ohne geladenen Song (Laenge 0)
        oder bei ungueltiger Eingabe: nicht erfuellt.
        """
        length = ctx.get("song_length_seconds", 0) or 0
        if length <= 0:
            return False
        threshold = parse_time_offset(p.get("value", ""))
        if threshold is None:
            return False
        if p.get("operator", "above") == "below":
            return length < threshold
        return length >= threshold

    def _register_rule_actions(self):
        """Registriert alle V1-Action-Handler."""
        re = self.rule_engine
        re.register_action("dock_open", self._rule_dock_open)
        re.register_action("dock_close", self._rule_dock_close)
        re.register_action("dock_fullsize", self._rule_dock_fullsize)
        re.register_action("dock_custom_size", self._rule_dock_custom_size)
        re.register_action("dock_focus", self._rule_dock_focus)
        re.register_action("auto_scroll_start", self._rule_auto_scroll_start)
        re.register_action("auto_scroll_stop", self._rule_auto_scroll_stop)
        re.register_action("layout_load", self._rule_layout_load)
        re.register_action("log_message", self._rule_log_message)
        re.register_action("statusbar_message", self._rule_statusbar_message)
        # Transport-Aktionen
        re.register_action("play", self._rule_play)
        re.register_action("pause", self._rule_pause)
        re.register_action("stop", self._rule_stop)
        re.register_action("fade_out", self._rule_fade_out)
        re.register_action("play_pause_toggle", self._rule_play_pause_toggle)
        # Workflow-Aktionen
        re.register_action("auto_advance", self._rule_auto_advance)
        re.register_action("open_location_dialog", self._rule_open_location_dialog)
        re.register_action("toggle_manager", self._rule_toggle_manager)
        re.register_action("break_toggle", self._rule_break_toggle)
        re.register_action("start_break", self._rule_start_break)
        re.register_action("start_break_last_song", self._rule_start_break_last_song)
        # Timer/Warn-Aktionen
        re.register_action("play_sound", self._rule_play_sound)
        re.register_action("system_ping", self._rule_system_ping)
        re.register_action("warn_background", self._rule_warn_background)
        re.register_action("warn_background_reset", self._rule_warn_background_reset)
        # Tempo-Aktion
        re.register_action("tempo_change", self._rule_tempo_change)
        re.register_action("song_tempo_change", self._rule_song_tempo_change)
        re.register_action("pitch_change", self._rule_pitch_change)
        re.register_action("volume_change", self._rule_volume_change)
        re.register_action("live_volume_change", self._rule_live_volume_change)
        re.register_action("live_volume_set", self._rule_live_volume_set)
        re.register_action("auto_set_best_loop", self._rule_auto_set_best_loop)
        re.register_action("auto_detect_bpm",    self._rule_auto_detect_bpm)
        re.register_action("toggle_loop_active", self._rule_toggle_loop_active)
        re.register_action("goto_position", self._rule_goto_position)
        re.register_action("shift_position", self._rule_shift_position)
        re.register_action("create_jump_marker", self._rule_create_jump_marker)
        re.register_action("lyrics_auto_width", self._rule_lyrics_auto_width)
        # Foto-Aktionen
        re.register_action("photo_capture", self._rule_photo_capture)
        re.register_action("photo_show", self._rule_photo_show)
        # Genre-Aktionen
        re.register_action("genre_add", self._rule_genre_add)
        re.register_action("genre_remove", self._rule_genre_remove)
        # Notizen-Aktionen
        re.register_action("notes_tick_top", self._rule_notes_tick_top)
        # Dual-View-Aktionen
        re.register_action("dual_view",           self._rule_dual_view)
        re.register_action("dual_view_close",     self._rule_dual_view_close)
        re.register_action("dual_view_toggle",    self._rule_dual_view_toggle)
        re.register_action("sequenceview_focus",   self._rule_sequenceview_focus)
        re.register_action("sequenceview_maximize",self._rule_sequenceview_maximize)
        re.register_action("sequenceview_open",    self._rule_sequenceview_open)
        re.register_action("sequenceview_close",   self._rule_sequenceview_close)
        re.register_action("sequenceview_prev",    self._rule_sequenceview_prev)
        re.register_action("sequenceview_next",    self._rule_sequenceview_next)
        re.register_action("sequenceview_random",  self._rule_sequenceview_random)  # BL-182
        re.register_action("sequence_set_type",    self._rule_sequence_set_type)  # BL-181 A
        re.register_action("set_dance_program",    self._rule_set_dance_program)     # BL-192
        re.register_action("seqfilter_contains",   self._rule_seqfilter_contains)    # BL-193
        re.register_action("seqfilter_limit",      self._rule_seqfilter_limit)       # BL-194
        re.register_action("seqfilter_only",       self._rule_seqfilter_only)        # BL-195
        re.register_action("seqfilter_difficulty", self._rule_seqfilter_difficulty)  # BL-196
        re.register_action("seqfilter_tags",       self._rule_seqfilter_tags)        # BL-197
        re.register_action("dock_focus_cursor",    self._rule_dock_focus_cursor)     # BL-176
        re.register_action("load_song",            self._rule_load_song)          # BL-181 B

    # Docks, deren interner Kurzname historisch von der objectName-Ableitung
    # abweicht — als Alias erhalten, damit bestehende Regeln weiter funktionieren.
    _DOCK_NAME_ALIASES = {
        "dock_songlist": "song_list",
        "dock_songdata": "song_data",
    }

    def _dock_map(self) -> dict:
        """Mapping: Kurzname -> QDockWidget.

        Generisch: sammelt ALLE Docks des Fensters ueber ihre objectName
        ("dock_<name>" -> "<name>"). Neue Widgets erscheinen dadurch automatisch
        in den Regel-Aktionen (Dock oeffnen/schliessen) und am Stream Deck, ohne
        dass hier etwas ergaenzt werden muss. Zwei historische Docks behalten
        ihren alten Kurznamen (siehe _DOCK_NAME_ALIASES).
        """
        m: dict = {}
        for dock in self.findChildren(QDockWidget):
            obj = dock.objectName()
            if not obj:
                continue
            name = self._DOCK_NAME_ALIASES.get(obj)
            if name is None:
                name = obj[5:] if obj.startswith("dock_") else obj
            if name:
                m[name] = dock
        return m

    def _dock_shortname(self, dock) -> str:
        """Kehrt _dock_map um: QDockWidget -> Kurzname (wie in Regeln benutzt)."""
        for name, d in self._dock_map().items():
            if d is dock:
                return name
        return ""

    def _button_open_position(self, dock) -> str:
        """#66: Ein On-Screen-Button (Lyrics/Planner) erbt die Oeffnen-Position
        aus einer AKTIVEN 'dock_open'-Regel fuer genau dieses Dock. Gibt es keine
        solche Regel, bleibt es beim bisherigen Verhalten 'centered'. So wirkt der
        Schalter aus der Regelaktion auch auf den Button, ohne eigenen Speicher.
        """
        engine = getattr(self, "rule_engine", None)
        if engine is None:
            return "centered"
        name = self._dock_shortname(dock)
        if not name:
            return "centered"
        for rule in engine.get_merged_rules():
            if not rule.active:
                continue
            for action in rule.actions:
                if (action.type == "dock_open"
                        and action.params.get("dock_name") == name):
                    return action.params.get("open_position", "centered")
        return "centered"

    def _rule_dock_open(self, params: dict):
        dock = self._dock_map().get(params.get("dock_name", ""))
        if not dock:
            return
        # #66: "centered" -> als loses Fenster ueber dem Hauptfenster zentrieren;
        # "last" (Default fuer Alt-Regeln ohne Key) -> bisheriges Verhalten, nur
        # sichtbar machen und nach vorne holen (floatgeom haelt die Position).
        if params.get("open_position", "last") == "centered":
            self._toggle_dock_open_centered(dock)
        else:
            dock.setVisible(True)
            dock.raise_()

    def _toggle_dock_open_centered(self, dock):
        """Oeffnet ein Dock als zentriertes Floating-Fenster (gemeinsame Logik
        fuer _toggle_dock 'centered' und die Regelaktion dock_open 'centered')."""
        dock.setFloating(True)
        dock.show()
        self._center_float_dock(dock)
        dock.raise_()

    def _center_float_dock(self, dock):
        """Zentriert ein schwebendes Dock ueber dem Hauptfenster. Die beim
        show() gesetzte gemerkte Geometrie (#121) liefert dabei die Groesse."""
        main_geo = self.geometry()
        dock_size = dock.size()
        x = main_geo.x() + (main_geo.width() - dock_size.width()) // 2
        y = main_geo.y() + (main_geo.height() - dock_size.height()) // 2
        dock.move(x, y)

    def _rule_dock_close(self, params: dict):
        dock = self._dock_map().get(params.get("dock_name", ""))
        if dock:
            dock.setVisible(False)

    def _rule_break_toggle(self, params: dict):
        """Pausen-Uhr (Break-Widget) umschalten: sichtbar -> schliessen, sonst oeffnen."""
        if self.dock_break.isVisible():
            self.dock_break.hide()
        else:
            self.dock_break.show()
            self.dock_break.raise_()
            self.dock_break.activateWindow()

    def _rule_break_seconds(self, params: dict) -> float:
        """Pausendauer in Sekunden aus dem Rule-Parameter 'minutes'.

        0 (oder fehlend) -> Standard-Pausendauer der aktuellen Lokation (bzw.
        globaler Default), analog zum Verhalten beim Oeffnen der Pausen-Uhr.
        """
        try:
            minutes = float(params.get("minutes", 0) or 0)
        except (TypeError, ValueError):
            minutes = 0
        if minutes <= 0:
            loc = self._current_location
            minutes = (loc.effective_break_minutes if loc is not None
                       else Location.DEFAULT_BREAK_MINUTES)
        return max(1.0, minutes * 60.0)

    def _rule_start_break(self, params: dict):
        """Rule-Aktion 'Start Break': Pausen-Uhr oeffnen und Countdown starten."""
        self.dock_break.show()
        self.dock_break.raise_()
        self.break_widget.start_break(self._rule_break_seconds(params))

    def _rule_start_break_last_song(self, params: dict):
        """Rule-Aktion 'Start Break with last Song': Pausen-Uhr oeffnen,
        Countdown starten und den letzten Song als Wartemusik abspielen."""
        self.dock_break.show()
        self.dock_break.raise_()
        self.break_widget.start_break_with_last_song(self._rule_break_seconds(params))

    def _rule_dock_fullsize(self, params: dict):
        """Macht das Ziel-Dock als grosses schwebendes Fenster (~90% des Screens)."""
        target_name = params.get("dock_name", "")
        dock_map = self._dock_map()
        target = dock_map.get(target_name)
        if not target:
            return
        # Kompletten Window-State sichern fuer Restore
        self._pre_fullsize_state = {
            "window_state": self.saveState(_LAYOUT_VERSION),
            "geometry": self.saveGeometry(),
            "dock_name": target_name,  # Merken welches Dock fullsize ist
        }
        # Dock floating machen und auf ~90% des Screens vergroessern
        target.setVisible(True)
        target.setFloating(True)
        screen = self.screen()
        if screen:
            sg = screen.availableGeometry()
            w = int(sg.width() * 0.9)
            h = int(sg.height() * 0.9)
            x = sg.x() + (sg.width() - w) // 2
            y = sg.y() + (sg.height() - h) // 2
            target.setGeometry(x, y, w, h)
        target.raise_()
        target.activateWindow()

    def _rule_dock_custom_size(self, params: dict):
        """Wie 'Fullsize Widget', aber Groesse und Position frei per Prozent.

        width_pct/height_pct = Anteil der verfuegbaren Bildschirmflaeche.
        x_pct/y_pct = Platzierung im Restraum (Bildschirm minus Fenster):
        0 = buendig links/oben, 50 = zentriert, 100 = buendig rechts/unten.
        So bleibt das Fenster bei jeder Groesse voll sichtbar.
        """
        target_name = params.get("dock_name", "")
        dock_map = self._dock_map()
        target = dock_map.get(target_name)
        if not target:
            return

        def _pct(key, default):
            try:
                return max(0, min(100, int(params.get(key, default))))
            except (TypeError, ValueError):
                return default
        w_pct = max(5, _pct("width_pct", 90))
        h_pct = max(5, _pct("height_pct", 90))
        x_pct = _pct("x_pct", 50)
        y_pct = _pct("y_pct", 50)

        # Kompletten Window-State sichern fuer Restore (identisch zu Fullsize,
        # damit 'Layout default laden' das Dock korrekt zuruecksetzt)
        self._pre_fullsize_state = {
            "window_state": self.saveState(_LAYOUT_VERSION),
            "geometry": self.saveGeometry(),
            "dock_name": target_name,
        }
        target.setVisible(True)
        target.setFloating(True)
        screen = self.screen()
        if screen:
            sg = screen.availableGeometry()
            w = int(sg.width()  * w_pct / 100)
            h = int(sg.height() * h_pct / 100)
            x = sg.x() + int((sg.width()  - w) * x_pct / 100)
            y = sg.y() + int((sg.height() - h) * y_pct / 100)
            target.setGeometry(x, y, w, h)
        target.raise_()
        target.activateWindow()

    def _rule_dual_view(self, params: dict):
        """Zeigt zwei Docks nebeneinander als schwebende Fenster (~90 % Bildschirm)."""
        left_name  = params.get("dock_left",  "")
        right_name = params.get("dock_right", "")
        split_str  = params.get("split", "50:50")
        dock_map   = self._dock_map()
        left_dock  = dock_map.get(left_name)
        right_dock = dock_map.get(right_name)
        if not left_dock or not right_dock or left_dock is right_dock:
            return

        # Breitenverhaeltnis parsen (z.B. "33:67" -> 0.33 / 0.67)
        try:
            lp, rp = [int(x) for x in split_str.split(":")]
        except (ValueError, AttributeError):
            lp, rp = 50, 50
        total_pct = lp + rp or 100
        left_frac = lp / total_pct

        screen = self.screen()
        if not screen:
            return
        sg    = screen.availableGeometry()
        total_w = int(sg.width()  * 0.9)
        h       = int(sg.height() * 0.9)
        x0      = sg.x() + (sg.width()  - total_w) // 2
        y0      = sg.y() + (sg.height() - h)        // 2
        gap     = 4  # Pixel Abstand zwischen den beiden Fenstern

        left_w  = int(total_w * left_frac) - gap // 2
        right_w = total_w - left_w - gap

        left_dock.setVisible(True)
        left_dock.setFloating(True)
        left_dock.setGeometry(x0, y0, left_w, h)
        left_dock.raise_()
        left_dock.activateWindow()

        right_dock.setVisible(True)
        right_dock.setFloating(True)
        right_dock.setGeometry(x0 + left_w + gap, y0, right_w, h)
        right_dock.raise_()

        # Zustand merken fuer dual_view_close
        self._dual_view_active = (left_name, right_name)

    def _rule_dual_view_close(self, params: dict):
        """Schliesst die per dual_view geoeffneten Fenster und dockt sie zurueck."""
        dock_map = self._dock_map()
        names = getattr(self, '_dual_view_active', None)
        if names:
            for name in names:
                dock = dock_map.get(name)
                if dock:
                    dock.setFloating(False)
                    dock.setVisible(False)
            self._dual_view_active = None

    def _rule_dual_view_toggle(self, params: dict):
        """Toggle: erstes Ausloesen oeffnet Dual-View (Layout gesichert),
        zweites Ausloesen stellt das gespeicherte Layout wieder her.

        Deferred via QTimer.singleShot(0, ...) — restoreState/restoreGeometry
        blockieren den Main-Thread synchron (gleiches Muster wie layout_load).
        Trigger ist sofort durch, Arbeit landet im naechsten Event-Loop-Tick.
        Play-Gate: Token holen, damit ein startender Song erst nach dem
        Layout-Wechsel hoerbar wird (release im finally des _deferred).
        """
        token = self._play_barrier.add_token_if_collecting()
        QTimer.singleShot(
            0, lambda: self._rule_dual_view_toggle_deferred(params, token))

    def _rule_dual_view_toggle_deferred(self, params: dict, token=None):
        try:
            self._rule_dual_view_toggle_apply(params)
        finally:
            self._play_barrier.release(token)

    def _rule_dual_view_toggle_apply(self, params: dict):
        if getattr(self, '_dual_view_active', None):
            # --- Dual-View schliessen: Layout wiederherstellen ---
            state = getattr(self, '_pre_dual_view_state', None)
            dock_map = self._dock_map()
            # Floating-Docks zuerst explizit zuruecksetzen (Qt-Bug wie bei fullsize)
            for name in self._dual_view_active:
                dock = dock_map.get(name)
                if dock:
                    dock.setFloating(False)
                    dock.setVisible(True)
            if state:
                self.restoreGeometry(state["geometry"])
                self.restoreState(state["window_state"], _LAYOUT_VERSION)
                self._reapply_dock_features()
                self._pre_dual_view_state = None
            self._dual_view_active = None
            self.activateWindow()
            self.raise_()
        else:
            # --- Dual-View oeffnen: Layout sichern, dann aufbauen ---
            self._pre_dual_view_state = {
                "window_state": self.saveState(_LAYOUT_VERSION),
                "geometry":     self.saveGeometry(),
            }
            self._rule_dual_view(params)

    def _rule_dock_focus(self, params: dict):
        dock = self._dock_map().get(params.get("dock_name", ""))
        if dock:
            dock.setVisible(True)
            dock.raise_()
            if dock.widget():
                dock.activateWindow()
                dock.widget().setFocus()

    def _rule_dock_focus_cursor(self, params: dict):
        """BL-176: Wie Focus Widget, plus Mauszeiger in die Mitte des Widgets."""
        self._rule_dock_focus(params)
        dock = self._dock_map().get(params.get("dock_name", ""))
        if dock is None:
            return
        try:
            target = dock.widget() or dock
            QCursor.setPos(target.mapToGlobal(target.rect().center()))
        except Exception:
            pass

    def _rule_sequenceview_focus(self, params: dict):
        """Bringt das SequenzView-Dock in den Vordergrund."""
        if hasattr(self, 'dock_sequence_view'):
            self.dock_sequence_view.setVisible(True)
            self.dock_sequence_view.raise_()
            self.dock_sequence_view.activateWindow()

    def _rule_sequenceview_maximize(self, params: dict):
        """Macht das SequenzView-Dock als grosses schwebendes Fenster (~90% des Screens)."""
        if not hasattr(self, 'dock_sequence_view'):
            return
        dock = self.dock_sequence_view
        if not dock.isVisible():
            # Dock befuellen falls noch leer
            seq_ids = self.sequences_widget.get_filtered_seq_ids()
            if seq_ids:
                idx = self.sequences_widget.get_current_seq_idx()
                self.sequence_view_widget.set_sequence(self.db, seq_ids, idx)
        dock.setVisible(True)
        dock.setFloating(True)
        screen = self.screen()
        if screen:
            sg = screen.availableGeometry()
            w = int(sg.width() * 0.9)
            h = int(sg.height() * 0.9)
            x = sg.x() + (sg.width() - w) // 2
            y = sg.y() + (sg.height() - h) // 2
            dock.setGeometry(x, y, w, h)
        dock.raise_()
        dock.activateWindow()

    def _rule_sequenceview_open(self, params: dict):
        """Zeigt das SequenzView-Dock mit der aktuellen Sequenzauswahl."""
        if not hasattr(self, 'dock_sequence_view'):
            return
        seq_ids = self.sequences_widget.get_filtered_seq_ids()
        if seq_ids:
            idx = self.sequences_widget.get_current_seq_idx()
            self.sequence_view_widget.set_sequence(self.db, seq_ids, idx)
        self.dock_sequence_view.setVisible(True)
        self.dock_sequence_view.raise_()

    def _rule_sequenceview_close(self, params: dict):
        """Versteckt das SequenzView-Dock."""
        if hasattr(self, 'dock_sequence_view'):
            self.dock_sequence_view.setVisible(False)

    def _rule_sequenceview_prev(self, params: dict):
        if hasattr(self, 'sequence_view_widget'):
            self.sequence_view_widget._on_prev()

    def _rule_sequenceview_next(self, params: dict):
        if hasattr(self, 'sequence_view_widget'):
            self.sequence_view_widget._on_next()

    def _rule_sequenceview_random(self, params: dict):
        """BL-182: Springt zu einer zufaelligen passenden Sequenz — unabhaengig
        vom Wuerfel-Toggle, damit sich der Zufallssprung auch per Regel/
        Fernbedienung ausloesen laesst. Nutzt dieselbe "ohne Zuruecklegen"-
        Logik wie der Wuerfel-Modus (still erneuert bei erschoepftem Pool).

        Haelt sich an die aktuell eingestellten Filter: der Zufalls-Pool wird
        vor dem Zug frisch aus den gefilterten Sequenz-Ids gespiegelt (der
        Live-Sync greift nur bei sichtbarem Dock — hier erzwungen)."""
        if not hasattr(self, 'sequence_view_widget'):
            return
        if hasattr(self, 'sequences_widget'):
            self.sequence_view_widget.sync_pool(
                self.sequences_widget.get_filtered_seq_ids())
        self.sequence_view_widget._go_random()

    def _rule_sequence_set_type(self, params: dict):
        """BL-181 A: Schaltet den Type-Filter des Sequenzen-Widgets um.

        Hintergrund: beim Singing Call moechte der Caller die Singing-Call-
        Figuren sehen, beim Patter die Module und Get-Outs. Eine Rule kann so
        beim Typwechsel automatisch die passende Sequenz-Sicht einstellen.
        """
        if not hasattr(self, 'sequences_widget'):
            return
        seq_type = str(params.get("seq_type", "") or "")
        ok = self.sequences_widget.set_type_filter(seq_type)
        if not ok:
            # Typ nicht (mehr) vorhanden — sichtbar, aber ohne Crash.
            self.statusBar().showMessage(
                _t("rule_seqtype_not_found", seq_type=seq_type), 4000)

    # --- BL-192..197: Sequence-Filter / Tanzprogramm per Regel setzen ---

    def _rule_seqfilter_contains(self, params: dict):
        """BL-193: Setzt den Contains-Filter des Sequenzen-Widgets."""
        if hasattr(self, 'sequences_widget'):
            self.sequences_widget.rule_set_contains(
                str(params.get("call", "") or ""))

    def _rule_seqfilter_limit(self, params: dict):
        """BL-194: Setzt den Limit-Filter des Sequenzen-Widgets."""
        if hasattr(self, 'sequences_widget'):
            self.sequences_widget.rule_set_limit(
                str(params.get("call", "") or ""))

    def _rule_seqfilter_only(self, params: dict):
        """BL-195: Schaltet den "Nur"-Filter ein/aus."""
        if hasattr(self, 'sequences_widget'):
            state = str(params.get("state", "On")).strip().lower()
            on = state in ("on", "true", "1", "yes", "ein")
            self.sequences_widget.rule_set_only(on)

    def _rule_seqfilter_difficulty(self, params: dict):
        """BL-196: Setzt den Difficulty-Filter des Sequenzen-Widgets."""
        if hasattr(self, 'sequences_widget'):
            self.sequences_widget.rule_set_difficulty(
                str(params.get("difficulty", "") or ""))

    def _rule_seqfilter_tags(self, params: dict):
        """BL-197: Setzt den Tag-Filter des Sequenzen-Widgets."""
        if hasattr(self, 'sequences_widget'):
            self.sequences_widget.rule_set_tags(
                str(params.get("tag", "") or ""))

    def _rule_set_dance_program(self, params: dict):
        """BL-192: Setzt die aktive(n) Tanzprogramme (Mehrfachauswahl).

        Der Parameter ist eine komma-separierte Liste von dance_program-IDs.
        Ungueltige IDs werden verworfen; eine leere Liste schaltet die
        Programm-Wahl ab (alle Sequenzen sichtbar)."""
        raw = str(params.get("program_ids", "") or "")
        ids = []
        for part in raw.split(","):
            part = part.strip()
            if part.isdigit():
                ids.append(int(part))
        valid = {r[0] for r in self.db.get_all_dance_programs()}
        ids = [i for i in ids if i in valid]
        self._set_session_program_ids(ids)

    # --- Provider fuer die Rule-Editor-Dropdowns (BL-192..197) ---

    def _rule_all_call_names(self):
        """Alle Call-Namen (ohne Trenner) fuer Contains-/Limit-Dropdown."""
        from sequence_mapper import get_all_calls_sorted
        return [n for n, _eid, _to in get_all_calls_sorted(self.db)
                if not n.startswith("--")]

    def _rule_program_choices(self):
        """Tanzprogramme als [(id, label), ...] fuer die Mehrfachauswahl."""
        out = []
        for row in self.db.get_all_dance_programs():
            pid, code, label = row[0], row[1], row[2]
            out.append((pid, label or code))
        return out

    def _rule_load_song(self, params: dict):
        """BL-181 B: Waehlt einen Song nach Typ + Sortierung und laedt ihn (cue).

        "Recommendation" liefert deterministisch immer den besten Song; die
        Zufalls-Sortierungen ziehen bei jedem Aufruf neu und liefern daher
        wechselnde Songs. Der gewaehlte Song wird ueber den normalen
        Songlisten-Pfad geladen (kein Autoplay) und in der Liste selektiert.
        """
        if not hasattr(self, 'song_list'):
            return

        want_type = str(params.get("type", "Singing") or "Singing").lower()
        sort_label = str(params.get("sort", "Recommendation") or "Recommendation")

        # Songbestand + Score-Kontext aus der Songliste wiederverwenden, damit
        # die Empfehlung exakt der ist, die der Caller in der Liste sieht.
        songs = list(getattr(self.song_list, "_all_songs", []) or [])
        if not songs:
            songs = self.db.get_all()
        lpm = getattr(self.song_list, "_last_played_map", {}) or {}
        start_date = getattr(self.song_list, "_start_date", date.today())

        # Typ-Filter (Singing/Patter)
        if want_type.startswith("sing"):
            songs = [s for s in songs if s.is_singing]
        else:
            songs = [s for s in songs if s.is_pattern]
        if not songs:
            self.statusBar().showMessage(
                _t("rule_load_song_none", type=params.get("type", "")), 4000)
            return

        def _days(s):
            return _reco_days_since(s.id, lpm, start_date)

        # Sortierung waehlen. Fresh-Draw fuer die Zufallsmodi (kein Cache) →
        # jeder Ausloeser liefert eine neue Reihenfolge/Auswahl.
        label = sort_label.lower()
        if label.startswith("recommendation"):
            chosen = max(songs, key=lambda s: (s.quality * _days(s), random.random()))
        elif label.startswith("weighted"):
            def _weight(s):
                q = s.quality if s.quality > 0 else _UNRATED_QUALITY
                return max(1, q * _days(s) + 1)
            chosen = _weighted_random_order(
                songs, _weight, lambda _sid: random.random() or 1e-12)[0]
        elif label.startswith("random"):
            chosen = random.choice(songs)
        elif label.startswith("quality"):
            chosen = max(songs, key=lambda s: (s.quality, random.random()))
        elif label.startswith("last played"):
            chosen = max(songs, key=lambda s: (_days(s), random.random()))
        elif label.startswith("date added"):
            def _added_ord(s):
                try:
                    return date.fromisoformat(s.date_added[:10]).toordinal()
                except (ValueError, TypeError):
                    return start_date.toordinal()
            chosen = max(songs, key=lambda s: (_added_ord(s), random.random()))
        else:  # Alphabetical
            chosen = min(songs, key=lambda s: (s.title or s.filename).lower())

        # Songlisten-Typ-Filter an den gewaehlten Typ angleichen, damit der
        # geladene Song in der Liste sichtbar ist und selektiert werden kann.
        # Ohne das blendet ein abweichender Filter (z. B. Liste auf "Singing",
        # Action liefert "Patter") den Song aus — er wird zwar korrekt in den
        # Player geladen, aber die Selektion in der Liste greift ins Leere.
        try:
            fb = getattr(self.song_list, "_filter_bar", None)
            if fb is not None:
                fb.set_type_filter(2 if want_type.startswith("sing") else 1)
        except Exception:
            pass

        # Song laden (cue, kein Autoplay) ueber den normalen Songlisten-Pfad.
        # offer_copy=False: keine interaktiven Sync-Copy-Dialoge bei Singing —
        # eine Rule darf im Live-Betrieb nicht auf einen Klick warten.
        self._on_song_selected(chosen.id, offer_copy=False)
        # In der Songliste selektieren/sichtbar machen, falls dort dargestellt.
        try:
            row = getattr(self.song_list, "_row_by_id", {}).get(chosen.id)
            if row is not None:
                self.song_list.table.selectRow(row)
                self.song_list.table.scrollToItem(
                    self.song_list.table.item(row, 0),
                    QAbstractItemView.PositionAtCenter)
        except Exception:
            pass

    def _rule_auto_scroll_start(self, params: dict):
        if hasattr(self.lyrics_widget, '_btn_auto_scroll'):
            self.lyrics_widget._btn_auto_scroll.setChecked(True)

    def _rule_auto_scroll_stop(self, params: dict):
        if hasattr(self.lyrics_widget, '_btn_auto_scroll'):
            self.lyrics_widget._btn_auto_scroll.setChecked(False)

    def _rule_lyrics_auto_width(self, params: dict):
        # Aktiviert den persistenten Auto-Width-Modus; Toggle-Handler
        # uebernimmt Exklusivitaet mit Auto-Size und den initialen Fit.
        self.lyrics_widget._btn_auto_width.setChecked(True)

    def _rule_photo_capture(self, params: dict):
        """Foto aufnehmen. Startet Kamera falls noetig, schiesst Foto."""
        # Photo-Dock sichtbar machen (loest Lazy-Init aus)
        if not self.dock_photo.isVisible():
            self.dock_photo.setVisible(True)
            self.dock_photo.setFloating(True)
        # Warten bis Widget erstellt ist
        if self.photo_widget is None:
            return
        # Kamera starten falls noch nicht aktiv
        if not self.photo_widget._camera_active:
            self.photo_widget._on_toggle_camera()
            # Kurz warten bis Kamera bereit, dann aufnehmen
            QTimer.singleShot(500, self._rule_photo_do_capture)
        else:
            self._rule_photo_do_capture()

    def _rule_photo_do_capture(self):
        """Hilfsmethode: Foto tatsaechlich aufnehmen."""
        if self.photo_widget and self.photo_widget._camera_active:
            self.photo_widget._on_capture()

    def _rule_photo_show(self, params: dict):
        """Photo-Dock anzeigen und auf ~90% vergroessern."""
        # Dock sichtbar machen (loest Lazy-Init aus)
        if not self.dock_photo.isVisible():
            self.dock_photo.setVisible(True)
            self.dock_photo.setFloating(True)
        # Auf ~90% des Screens vergroessern
        screen = self.screen()
        if screen:
            sg = screen.availableGeometry()
            w = int(sg.width() * 0.9)
            h = int(sg.height() * 0.9)
            x = sg.x() + (sg.width() - w) // 2
            y = sg.y() + (sg.height() - h) // 2
            self.dock_photo.setGeometry(x, y, w, h)
        self.dock_photo.raise_()
        self.dock_photo.activateWindow()

    def _rule_genre_add(self, params: dict):
        """Fuegt dem aktuellen Song ein Genre hinzu (legt es ggf. neu an)."""
        if not self._current_song:
            return
        genre_name = params.get("genre_name", "").strip()
        if not genre_name:
            return
        gid = self.db.get_genre_id_by_name(genre_name)
        if gid < 0:
            gid = self.db.insert_genre(genre_name)
        if gid < 0:
            return
        current = [g[0] for g in self.db.get_genres_for_song(self._current_song.id)]
        if gid not in current:
            current.append(gid)
            self.db.set_genres_for_song(self._current_song.id, current)
            # Anzeige aktualisieren
            if self.song_data._current_song and \
                    self.song_data._current_song.id == self._current_song.id:
                genres = self.db.get_genres_for_song(self._current_song.id)
                self.song_data.label_genre.setText(
                    ", ".join(n for _, n in genres) or "\u2014")

    def _rule_genre_remove(self, params: dict):
        """Entfernt ein Genre vom aktuellen Song."""
        if not self._current_song:
            return
        genre_name = params.get("genre_name", "").strip()
        if not genre_name:
            return
        gid = self.db.get_genre_id_by_name(genre_name)
        if gid < 0:
            return
        current = [g[0] for g in self.db.get_genres_for_song(self._current_song.id)]
        if gid in current:
            current.remove(gid)
            self.db.set_genres_for_song(self._current_song.id, current)
            # Anzeige aktualisieren
            if self.song_data._current_song and \
                    self.song_data._current_song.id == self._current_song.id:
                genres = self.db.get_genres_for_song(self._current_song.id)
                self.song_data.label_genre.setText(
                    ", ".join(n for _, n in genres) or "\u2014")

    def _rule_notes_tick_top(self, params: dict):
        """Markiert die oberste offene Notiz der aktuellen Lokation als erledigt.
        Stumm ignorieren, wenn keine offene Notiz (oder Widget nicht initialisiert)."""
        if not getattr(self, "notes_widget", None):
            return
        self.notes_widget.tick_top_open_note()

    # ── Shortcode-Ausfuehrung ─────────────────────────────────────────────────

    def _shortcode_dispatch(self, action_id: str, params: dict):
        """Fuehrt einen Shortcode aus (ausgeloest durch Abharken einer Notiz)."""
        handler = {
            "load_song":     self._shortcode_load_song,
            "sequence_view": self._shortcode_sequence_view,
            "to_call":       self._shortcode_to_call,
        }.get(action_id)
        if handler:
            try:
                handler(params)
            except Exception as e:
                print(f"[Shortcode] Fehler bei [{action_id}]: {e}")

    def _shortcode_load_song(self, params: dict):
        title = params.get('_value') or params.get('title', '')
        if not title:
            return
        title_lower = title.lower()
        match = next(
            (s for s in self.db.get_all() if (s.title or s.filename).lower() == title_lower),
            None
        )
        if match:
            self._on_song_selected(match.id)

    def _shortcode_sequence_view(self, params: dict):
        seq_id = params.get('id')
        contains = params.get('contains')
        limit = params.get('limit')
        if contains is not None:
            self.sequences_widget.set_contains_filter(contains)
        if limit is not None:
            self.sequences_widget.set_limit_filter(limit)
        seq_ids = self.sequences_widget.get_filtered_seq_ids()
        idx = 0
        if seq_id is not None and seq_id in seq_ids:
            idx = seq_ids.index(seq_id)
        if seq_ids:
            self.sequence_view_widget.set_sequence(self.db, seq_ids, idx)
        if hasattr(self, 'dock_sequence_view'):
            self.dock_sequence_view.setVisible(True)
            self.dock_sequence_view.raise_()

    def _shortcode_to_call(self, params: dict):
        """BL-199: Fuellt das To-Call-Widget aus einem [to_call]-Shortcode.

        Formen: program="..." | program="..." except="..." | calls="...".
        """
        import call_selection as cs
        calls = cs.resolve_calls(
            self.db,
            program=params.get("program", "") or "",
            calls=params.get("calls"),
            except_names=params.get("except"),
        )
        if not calls:
            return
        self.to_call_widget.fill(calls)
        self.dock_to_call.setVisible(True)
        self.dock_to_call.raise_()

    def _open_tocall_fill(self):
        """Oeffnet den Fuellen-Dialog des To-Call-Widgets (BL-199)."""
        from to_call_widget import ToCallFillDialog
        progs = self.db.get_all_dance_programs()
        # Vorauswahl: hoechstes der gewaehlten Tanzprogramme (dieselbe Regel wie
        # der Programm-Button im Player) -- trifft den Normalfall am Clubabend.
        label_by_id = {r[0]: (r[2] or r[1]) for r in progs}
        top_id, _code = self._top_program(
            getattr(self, '_session_program_ids', []) or [])
        active_label = label_by_id.get(top_id, "")
        if not active_label and progs:
            active_label = progs[0][2] or progs[0][1]

        dlg = ToCallFillDialog(self.db, progs, active_label, self)
        if dlg.exec() != QDialog.Accepted:
            return
        selected = dlg.selected_calls()
        if dlg.action == "fill":
            self.to_call_widget.fill(selected)
            self.dock_to_call.setVisible(True)
            self.dock_to_call.raise_()
        elif dlg.action == "notes":
            import call_selection as cs
            from shortcode_parser import shortcode_text
            if not self._notes_require_location():
                return
            self._notes_ensure_init()
            params = cs.build_shortcode_params(
                dlg.program_label, dlg.all_names, [n for _, n in selected])
            self.notes_widget.add_note(shortcode_text("to_call", params))
            self.dock_notes.setVisible(True)
            self.dock_notes.raise_()

    def _notes_require_location(self) -> bool:
        """Prueft ob eine Lokation gewaehlt ist. Zeigt Warnung wenn nicht. True = OK."""
        if self._notes_location_id is not None:
            return True
        QMessageBox.warning(
            self,
            _t("notes_no_location_title"),
            _t("notes_no_location_msg"),
        )
        return False

    def _notes_ensure_init(self):
        """Stellt sicher dass notes_widget existiert — erzwingt Lazy-Init synchron falls noetig."""
        if self.notes_widget is None:
            self._init_notes()

    def _song_shortcode_text(self, song_title: str, mode: str = "") -> str:
        """Duenner Delegat auf shortcode_parser.song_shortcode_text (Modularisierung:
        die Serialisierung gehoert ins Shortcode-Modul, nicht ins MainWindow)."""
        from shortcode_parser import song_shortcode_text
        return song_shortcode_text(song_title, mode)

    def _notes_insert_song_shortcode(self, song_title: str, mode: str = ""):
        """Fuegt einen [load_song]-Shortcode in die Notizen ein."""
        if not self._notes_require_location():
            return
        self._notes_ensure_init()
        self.dock_notes.setVisible(True)
        self.dock_notes.raise_()
        self.notes_widget.add_note(self._song_shortcode_text(song_title, mode))

    def _notes_insert_sequence_shortcode(self, seq_id: int):
        if not self._notes_require_location():
            return
        self._notes_ensure_init()
        self.dock_notes.setVisible(True)
        self.dock_notes.raise_()
        from shortcode_parser import shortcode_text
        text = shortcode_text("sequence_view", {"id": seq_id})
        self.notes_widget.add_note(text)

    def _notes_add_current_song(self):
        song = getattr(self, '_current_song', None)
        if not song and hasattr(self, 'song_data') and self.song_data:
            song = getattr(self.song_data, '_current_song', None)
        if song:
            self._notes_insert_song_shortcode(song.title)

    def _notes_add_current_sequence(self):
        seq_ids = self.sequences_widget.get_filtered_seq_ids()
        if seq_ids:
            idx = self.sequences_widget.get_current_seq_idx()
            self._notes_insert_sequence_shortcode(seq_ids[idx])

    def _notes_add_seq_with_filters(self):
        """Fuegt sequence_view-Shortcode mit aktuellen Contains- und Limit-Filtern ein."""
        if not getattr(self, 'notes_widget', None):
            return
        from shortcode_parser import shortcode_text
        params = {}
        contains = self.sequences_widget.get_contains_filter_text()
        if contains:
            params['contains'] = contains
        limit = self.sequences_widget.get_limit_filter_text()
        if limit:
            params['limit'] = limit
        text = shortcode_text("sequence_view", params)
        self.notes_widget.add_note(text)
        self.dock_notes.setVisible(True)
        self.dock_notes.raise_()

    def _rule_layout_load(self, params: dict):
        # Deferred: restoreState blockiert ~75ms den Main-Thread (GIL).
        # Verschieben in naechsten Event-Loop-Tick damit Audio-Callback zuerst laeuft.
        # Play-Gate: Token holen, damit ein gerade startender Song erst nach dem
        # Layout-Wechsel hoerbar wird (release im finally des _deferred).
        token = self._play_barrier.add_token_if_collecting()
        QTimer.singleShot(0, lambda: self._rule_layout_load_deferred(params, token))

    def _rule_layout_load_deferred(self, params: dict, token=None):
        try:
            self._rule_layout_load_apply(params)
        finally:
            self._play_barrier.release(token)

    def _rule_layout_load_apply(self, params: dict):
        layout_name = params.get("layout_name", "default")
        if layout_name == "default":
            # Wenn vorher fullsize: gespeicherten Window-State wiederherstellen
            if hasattr(self, '_pre_fullsize_state') and self._pre_fullsize_state:
                state = self._pre_fullsize_state
                # Fullsize-Dock ZUERST explizit zuruecksetzen (Qt-Bug: restoreState
                # kann floating Docks nicht immer korrekt zurueck-docken)
                fs_dock_name = state.get("dock_name", "")
                if fs_dock_name:
                    fs_dock = self._dock_map().get(fs_dock_name)
                    if fs_dock:
                        fs_dock.setFloating(False)
                        fs_dock.setVisible(True)
                self.restoreGeometry(state["geometry"])
                self.restoreState(state["window_state"], _LAYOUT_VERSION)
                self._reapply_dock_features()
                self._pre_fullsize_state = {}
                # Fokus zurueck aufs Hauptfenster (sonst gehen Shortcuts verloren)
                self.activateWindow()
                self.raise_()
            # Kein fullsize aktiv — nichts tun (kein _reset_layout!)
        else:
            # Benanntes Layout laden
            layout_path = os.path.join(self._app_dir, "skins",
                                       f"{layout_name}.ini")
            if os.path.exists(layout_path):
                self._apply_layout_file(layout_path)

    def _rule_log_message(self, params: dict):
        msg = params.get("message", "")
        if msg:
            self.rule_engine._log("USER_LOG", msg)

    def _rule_statusbar_message(self, params: dict):
        msg = params.get("message", "")
        dur = int(params.get("duration_ms", 3000))
        if msg:
            self.statusBar().showMessage(msg, dur)

    # ---- Audio-Ausgabegeraet-Selector (BL-126) ----

    def _setup_audio_device_selector(self):
        """Fuegt eine ComboBox fuer die Audio-Ausgabe dauerhaft in die Statusleiste ein.

        AR-007/008: Hostapi wird mit angezeigt ("Speakers (WASAPI)"), damit der
        User direkt sieht welches Backend Windows nutzt — und kann mit der
        Exclusive-Checkbox den WASAPI-Shared-Glitch umgehen.
        """
        import sounddevice as sd
        from PySide6.QtWidgets import QCheckBox

        self._audio_device_combo = QComboBox()
        self._audio_device_combo.setToolTip(_t("audio_device_tooltip"))
        self._audio_device_combo.setMinimumWidth(160)
        self._audio_device_combo.setMaximumWidth(320)

        # Erster Eintrag: System-Standard
        self._audio_device_combo.addItem(_t("audio_device_default"), None)

        # Alle Output-Geraete auflisten — mit Hostapi-Anzeige
        try:
            devices = sd.query_devices()
            for i, dev in enumerate(devices):
                if dev['max_output_channels'] > 0:
                    name = dev['name']
                    try:
                        hostapi_name = sd.query_hostapis(dev['hostapi'])['name']
                        # Kurzformen fuer die Anzeige
                        short = (hostapi_name
                                 .replace("Windows ", "")
                                 .replace("MME", "MME"))
                        label = f"{name} ({short})"
                    except Exception:
                        label = f"{i}: {name}"
                    self._audio_device_combo.addItem(label, i)
        except Exception:
            pass  # sounddevice nicht verfuegbar oder keine Geraete

        # Gespeichertes Geraet aus INI wiederherstellen
        saved = self._settings.value("audio/primary_device", "")
        if saved:
            try:
                saved_idx = int(saved)
                combo_idx = self._audio_device_combo.findData(saved_idx)
                if combo_idx >= 0:
                    # blockSignals: kein on_changed beim initialen Setzen (Engine laeuft noch nicht)
                    self._audio_device_combo.blockSignals(True)
                    self._audio_device_combo.setCurrentIndex(combo_idx)
                    self._audio_device_combo.blockSignals(False)
                    self.engine.set_output_device(saved_idx)
            except (ValueError, TypeError):
                pass
        else:
            # Erststart (kein gespeichertes Device): bewusst vom Allgemeinsten zum
            # Speziellsten. Wir starten mit dem Windows-Standardwiedergabegeraet
            # (System-Standard, Combo-Index 0, Engine-Device = None) — dem "Standard-
            # Sound-Kanal", der praktisch immer hoerbar ist. Wenn es leiert/aussetzt,
            # kann der User ueber die Combo gezielt "tiefer" gehen (WDM-KS/WASAPI/
            # Exclusive).
            #
            # Frueher (AR-015) wurde hier per Hostapi-Prioritaet ein WDM-KS-Geraet
            # gewaehlt. Das griff aber oft den SPDIF-/Digitalausgang ab (erstes
            # WDM-KS-Geraet) => die App startete stumm. Daher entfernt.
            self._audio_device_combo.blockSignals(True)
            self._audio_device_combo.setCurrentIndex(0)  # 0 = System-Standard (None)
            self._audio_device_combo.blockSignals(False)
            # Engine bleibt auf System-Standard (Device=None). Nichts in die INI
            # schreiben, damit die erste bewusste User-Auswahl der erste gespeicherte
            # Wert ist (Erststart-Verhalten bleibt bis dahin "System-Standard").
            perf.perf_write(
                "[Diag] Erststart-Audio: System-Standard (Windows-Default, Device=None), "
                "keine Hostapi-Heuristik mehr (frueher AR-015 WDM-KS-first → SPDIF-Gefahr)."
            )

        self._audio_device_combo.currentIndexChanged.connect(
            self._on_audio_device_changed)
        self.statusBar().addPermanentWidget(self._audio_device_combo)

        # AR-008: Checkbox fuer WASAPI Exclusive Mode (umgeht Shared-Glitch)
        self._wasapi_exclusive_cb = QCheckBox("Exclusive")
        self._wasapi_exclusive_cb.setToolTip(
            "WASAPI Exclusive Mode aktivieren.\n\n"
            "Umgeht den Windows WASAPI Shared-Mode-Glitch "
            "(periodische Mini-Aussetzer ~220 Samples).\n\n"
            "Achtung: blockiert andere Audio-Programme systemweit "
            "(kein YouTube/Spotify nebenbei).\n"
            "Wirkt nur, wenn das gewaehlte Ausgabegeraet ein WASAPI-Geraet ist."
        )
        saved_excl = str(
            self._settings.value("audio/wasapi_exclusive", "false")).lower() == "true"
        self._wasapi_exclusive_cb.setChecked(saved_excl)
        if saved_excl:
            self.engine.set_wasapi_exclusive(True)
        self._wasapi_exclusive_cb.toggled.connect(self._on_wasapi_exclusive_toggled)
        self.statusBar().addPermanentWidget(self._wasapi_exclusive_cb)

    # ---- Statusleiste — Miniatur-Abspielfortschritt (BL-128) ----

    def _setup_statusbar_player(self):
        """Fuegt den Miniatur-Abspielfortschritt in die Statusleiste ein (BL-128).

        INI-Schluessel: display/statusbar_player  (Werte: true | false, Standard: true)
        """
        self._sb_player_bar = _StatusBarPlayerBar(skin_mgr=self.skin_mgr, parent=self)
        enabled_str = self._settings.value("display/statusbar_player", "true")
        enabled = str(enabled_str).lower() not in ("false", "0", "no")
        if enabled:
            # stretch=1: Leiste bekommt so viel Platz wie moeglich (links vom Audio-Device-Combo)
            self.statusBar().addPermanentWidget(self._sb_player_bar, 1)
        else:
            self._sb_player_bar.hide()
        # Start-Countdown-Overlay
        self._countdown_overlay = _CountdownOverlay(self)
        _cd_str = self._settings.value("display/countdown_enabled", "true")
        self._countdown_enabled = str(_cd_str).lower() not in ("false", "0", "no")
        self._countdown_singing_start = None  # Cache: wird bei Song-Wechsel gesetzt

    def _update_countdown(self, pos: float, is_playing: bool):
        """Aktualisiert das Start-Countdown-Overlay. Laeuft im 50ms-Tick."""
        if not getattr(self, "_countdown_enabled", False) or not is_playing:
            self._countdown_overlay.hide_overlay()
            return
        song = self._current_song
        if not song:
            self._countdown_overlay.hide_overlay()
            return
        bpm = self.player._base_bpm
        if bpm <= 0:
            self._countdown_overlay.hide_overlay()
            return
        # Singing-Start aus Cache oder DB lesen
        if self._countdown_singing_start is None:
            try:
                ms = self.lyrics_widget._sync_music_slot
                props = self.db.get_properties(song.id)
                ss = props.get(f"singing_start_m{ms}")
                self._countdown_singing_start = float(ss) if ss is not None else -1.0
            except Exception:
                self._countdown_singing_start = -1.0
        singing_start = self._countdown_singing_start
        if singing_start < 0 or pos >= singing_start:
            self._countdown_overlay.hide_overlay()
            return
        tempo_ratio = self.player.spin_tempo.value() / 100.0
        beat_dur = 60.0 / (bpm * tempo_ratio)
        beats_left = math.ceil((singing_start - pos) / beat_dur)
        display = beats_left - 2  # letzte 2 Beats still (kein Overlay)
        if display <= 0:
            self._countdown_overlay.hide_overlay()
            return
        self._countdown_overlay.show_beat(display)

    def _on_audio_device_changed(self, _index: int):
        """Wird aufgerufen wenn der Nutzer ein anderes Audio-Ausgabegeraet waehlt."""
        device_index = self._audio_device_combo.currentData()
        # AR-013/M (v0.88): Versuchs-Log. Endergebnis kommt aus [Diag] Stream gestartet,
        # Fallbacks aus den Diag-Zeilen in audio_engine._ensure_stream.
        perf.perf_write(
            f"[Diag] Audio-Device Wechsel angefordert: idx={device_index}, "
            f"combo_label='{self._audio_device_combo.currentText()}'"
        )
        self.engine.set_output_device(device_index)
        if device_index is None:
            self._settings.setValue("audio/primary_device", "")
        else:
            self._settings.setValue("audio/primary_device", str(device_index))
        self._settings.sync()

    def _on_wasapi_exclusive_toggled(self, checked: bool):
        """AR-008: WASAPI Exclusive Mode an/aus."""
        self.engine.set_wasapi_exclusive(checked)
        self._settings.setValue(
            "audio/wasapi_exclusive", "true" if checked else "false")
        self._settings.sync()

    def _rule_play(self, params: dict):
        # Deferred: _firing muss erst False werden, damit song_started nicht blockiert wird
        # btn_play bleibt immer enabled (Restart bei laufendem Song)
        QTimer.singleShot(0, lambda: self.player.btn_play.click())

    def _rule_pause(self, params: dict):
        QTimer.singleShot(0, lambda: self.player.btn_pause.click()
                          if self.player.btn_pause.isEnabled() else None)

    def _rule_stop(self, params: dict):
        QTimer.singleShot(0, lambda: self.player.btn_stop.click()
                          if self.player.btn_stop.isEnabled() else None)

    def _rule_fade_out(self, params: dict):
        QTimer.singleShot(0, lambda: self.player.btn_fade.click()
                          if self.player.btn_fade.isEnabled() else None)

    def _rule_play_pause_toggle(self, params: dict):
        def _toggle():
            if self.engine.is_playing():
                if self.player.btn_pause.isEnabled():
                    self.player.btn_pause.click()
            else:
                if self.player.btn_play.isEnabled():
                    self.player.btn_play.click()
        QTimer.singleShot(0, _toggle)

    def _rule_auto_advance(self, params: dict):
        # Deferred: Auto-Advance laedt neuen Song, der fire_trigger("song_changed")
        # ausloest — darf nicht innerhalb von fire_trigger("song_stopped") passieren
        QTimer.singleShot(0, self._do_auto_advance)

    def _rule_open_location_dialog(self, params: dict):
        self._on_location_button_clicked()

    def _rule_toggle_manager(self, params: dict):
        self._on_manager_button_clicked()

    def _rule_play_sound(self, params: dict):
        """BL-137: Rule-Aktion „Sound abspielen".

        Mischt die in `params['path']` angegebene Audiodatei in den laufenden
        Audio-Stream. Lautstärke per `params['volume']` (Default 1.0).
        Kein zweiter Stream — gleiches Gerät, gleicher Output wie der Song.

        Wenn kein Pfad gesetzt oder Datei fehlt: stille No-op (anders als
        system_ping, das auf den Doppel-Beep zurueckfaellt). So kann der User
        zwei getrennte Rule-Aktionen kombinieren wenn er beides will.
        """
        path = (params or {}).get("path", "") or ""
        try:
            volume = float((params or {}).get("volume", 1.0))
        except (TypeError, ValueError):
            volume = 1.0
        if not path or not os.path.isfile(path) or self.engine is None:
            if path:
                print(f"[BL-137] play_sound: Datei nicht gefunden: {path!r}")
            return
        try:
            samples = self._load_alert_sound(path)
            if samples is not None and len(samples) > 0:
                self.engine.play_alert(samples, volume=volume)
        except Exception as ex:
            print(f"[BL-137] play_sound fehlgeschlagen ({path}): {ex}")

    def _rule_system_ping(self, params: dict):
        """Hoerbarer Warn-Ton.

        BL-137: Wenn in den Einstellungen ein Pfad zu einer Audiodatei gesetzt
        ist (INI-Key `audio/alert_sound_path`), wird diese in den laufenden
        Audio-Stream EINGEMISCHT — gleicher Output-Stream, gleiches Geraet
        wie die Musik. Keine Beeinflussung des aktiven Songs (additiv mit
        Clip-Schutz). Optional: `params['sound']` als Pfad-Override aus der
        Rule (z.B. zwei Rules mit unterschiedlichen Sounds fuer Pattern/Singing).

        Fallback wenn kein Pfad gesetzt oder Datei fehlt: winsound.Beep
        (alter Doppel-Ping in Daemon-Thread).
        """
        # Pfad-Priorität: explizit in Rule-Params > globale Einstellung
        sound_path = (params or {}).get("sound", "") or ""
        if not sound_path:
            sound_path = str(self._settings.value("audio/alert_sound_path", "") or "")
        volume = float(self._settings.value("audio/alert_volume", 1.0))

        if sound_path and os.path.isfile(sound_path) and self.engine is not None:
            try:
                samples = self._load_alert_sound(sound_path)
                if samples is not None and len(samples) > 0:
                    self.engine.play_alert(samples, volume=volume)
                    return
            except Exception as ex:
                print(f"[BL-137] Alert-Sound konnte nicht abgespielt werden: {ex}")
                # Fallback: Beep

        # Fallback: bisheriger Doppel-Beep
        def _beep():
            try:
                import winsound
                winsound.Beep(880, 150)   # A5, 150ms
                winsound.Beep(1100, 150)  # ~C#6, 150ms
            except Exception:
                QApplication.beep()
        threading.Thread(target=_beep, daemon=True, name="SystemPing").start()

    def _load_alert_sound(self, path: str):
        """BL-137: Alert-Audiodatei in float32-Array laden, gecacht pro Pfad+mtime.

        Resample falls die Datei eine andere Sample-Rate als der Engine-Stream hat
        (sounddevice spielt ueber den gleichen Stream, also muss SR identisch sein).
        """
        if not hasattr(self, "_alert_cache"):
            self._alert_cache = {}  # path → (mtime, sr, ndarray)
        try:
            mtime = os.path.getmtime(path)
        except OSError:
            return None
        cached = self._alert_cache.get(path)
        # Ohne geladenen Song (Kaltstart) oeffnet play_alert den Stream mit
        # ALERT_IDLE_SR — dorthin resamplen.
        target_sr = (self.engine.sample_rate if self.engine else None) or ALERT_IDLE_SR
        if cached and cached[0] == mtime and cached[1] == target_sr:
            return cached[2]
        try:
            import soundfile as sf
            data, sr = sf.read(path, dtype="float32", always_2d=True)
        except Exception as ex:
            print(f"[BL-137] Alert-Datei nicht lesbar ({path}): {ex}")
            return None
        # Sample-Rate angleichen wenn nötig (einfaches Linear-Resampling — Alert-Sounds
        # sind kurz und nicht qualitätskritisch)
        if target_sr and sr != target_sr:
            try:
                from scipy.signal import resample_poly
                # Ganzzahliges Verhältnis approximieren
                from math import gcd
                g = gcd(int(target_sr), int(sr))
                up = int(target_sr) // g
                down = int(sr) // g
                data = resample_poly(data, up, down, axis=0).astype("float32")
            except Exception as ex:
                print(f"[BL-137] Alert-Resampling fehlgeschlagen ({sr} → {target_sr}): {ex}")
                return None
        self._alert_cache[path] = (mtime, target_sr, data)
        return data

    def _rule_warn_background(self, params: dict):
        """Spieldauer-Label auf Warnfarbe setzen."""
        level = int(params.get("level", 1))
        if level >= 2:
            bg = self.skin_mgr.color("warning", "#ef4444") \
                if self.skin_mgr else "#ef4444"
        else:
            bg = self.skin_mgr.color("timer_warn1", "#f59e0b") \
                if self.skin_mgr else "#f59e0b"
        bc = self.player._timer_border_color
        self.player.label_play_timer.setStyleSheet(
            f"font-size: 14px; font-family: monospace; font-weight: bold; "
            f"border: 1px solid {bc}; padding: 2px; "
            f"background-color: {bg}; color: white;")

    def _rule_warn_background_reset(self, params: dict):
        """Spieldauer-Label auf Normalzustand zuruecksetzen."""
        self.player._timer_warn_state = 0
        self.player._update_timer_style()

    def _rule_tempo_change(self, params: dict):
        """Heutiges Tempo um delta Prozentpunkte aendern (kein Song-Daten-Speichern)."""
        delta = int(params.get("delta", 2))
        current = self.player.spin_today_tempo.value()
        new_val = max(50, min(150, current + delta))
        self.player.spin_today_tempo.setValue(new_val)

    def _rule_song_tempo_change(self, params: dict):
        """Song-Tempo um delta Prozentpunkte aendern und persistent am Song speichern.

        Modifiziert den Song-Tempo-SpinBox im Player. Ueber die bestehende
        Callback-Kette (player.on_tempo_changed -> song_data.update_tempo ->
        _auto_save) wird der neue Wert automatisch in der Datenbank gespeichert.
        """
        if not self._current_song:
            return
        delta = int(params.get("delta", 2))
        current = self.player.spin_tempo.value()
        new_val = max(50, min(150, current + delta))
        self.player.spin_tempo.setValue(new_val)

    def _rule_pitch_change(self, params: dict):
        """Pitch um delta Halbtoene aendern."""
        delta = float(params.get("delta", 0.5))
        current = self.player.spin_pitch.value()
        new_val = max(-6.0, min(6.0, current + delta))
        self.player.spin_pitch.setValue(new_val)

    def _rule_volume_change(self, params: dict):
        """Song-Volume um delta aendern."""
        delta = float(params.get("delta", -0.05))
        current = self.song_data.spin_volume.value()
        new_val = max(0.0, min(1.0, current + delta))
        self.song_data.spin_volume.setValue(new_val)

    def _rule_live_volume_change(self, params: dict):
        """Live-Volume-Slider um delta (Prozentpunkte) aendern."""
        delta = int(params.get("delta", -10))
        current = self.player.slider_live_volume.value()
        new_val = max(0, min(100, current + delta))
        self.player.slider_live_volume.setValue(new_val)

    def _rule_live_volume_set(self, params: dict):
        """Live-Volume-Slider auf einen absoluten Wert (%) setzen (0–100)."""
        value = int(params.get("value", 100))
        self.player.slider_live_volume.setValue(max(0, min(100, value)))

    def _rule_toggle_loop_active(self, params: dict):
        """Loop Active Checkbox umschalten."""
        chk = self.loop_widget.chk_loop
        chk.setChecked(not chk.isChecked())

    def _rule_goto_position(self, params: dict):
        """Sprung zu einer Position (start, loop_in, loop_out, end) mit Crossfade."""
        if not self._current_song:
            return
        pos = params.get("position", "start")
        dur = self.engine.get_original_duration()
        if dur <= 0:
            return
        if pos == "start":
            target = 0.0
        elif pos == "loop_in":
            target = self.engine.loop_in_seconds
        elif pos == "loop_out":
            target = self.engine.loop_out_seconds
        elif pos == "end":
            target = max(0, dur - 0.5)
        else:
            return
        # Crossfade-Parameter fuer sanften Uebergang nutzen
        xfade_ms = float(self._settings.value("loop/crossfade_ms", 46))
        if xfade_ms > 0 and self.engine.playing:
            self.engine.seek_with_crossfade(target, xfade_ms)
        else:
            self.engine.seek(target)

    def _rule_shift_position(self, params: dict):
        """Relative Positionsverschiebung im Song (z.B. -0:20 = 20 s zurueck).

        Nutzen: per Rule-Button 'nochmal Zeit fuers Beenden' des Liedes
        gewinnen. Der Wert (mm:ss.cs mit optionalem Vorzeichen) wird zur
        aktuellen Wiedergabeposition addiert und auf [0, Songende] begrenzt.
        """
        if not self._current_song:
            return
        dur = self.engine.get_original_duration()
        if dur <= 0:
            return
        offset = parse_time_offset(params.get("offset", ""))
        if offset is None:
            return
        cur = self.engine.get_playback_position_seconds()
        target = cur + offset
        # Auf gueltigen Bereich begrenzen (nicht vor Anfang / nicht ueber Ende)
        target = max(0.0, min(target, max(0.0, dur - 0.5)))
        xfade_ms = float(self._settings.value("loop/crossfade_ms", 46))
        if xfade_ms > 0 and self.engine.playing:
            self.engine.seek_with_crossfade(target, xfade_ms)
        else:
            self.engine.seek(target)

    # ---- Custom-Jump-Marker (BL-185) ----

    def _jump_to_time(self, time_seconds: float):
        """Springt an eine absolute Zeit (Sekunden), mit sanftem Crossfade.

        Genutzt von den Marker-Buttons in Song Data. Grenzen werden defensiv
        geklemmt, damit ein Marker knapp am Dateiende nicht in die Stille springt.
        """
        if not self._current_song:
            return
        dur = self.engine.get_original_duration()
        if dur <= 0:
            return
        target = max(0.0, min(float(time_seconds), max(0.0, dur - 0.05)))
        xfade_ms = float(self._settings.value("loop/crossfade_ms", 46))
        if xfade_ms > 0 and self.engine.playing:
            self.engine.seek_with_crossfade(target, xfade_ms)
        else:
            self.engine.seek(target)

    def _jump_and_play(self, time_seconds: float):
        """Doppelklick auf einen Sprung-Button (intern#100): hinspringen und
        abspielen. Laeuft der Song schon, nichts tun: Der erste Klick des
        Doppelklicks ist bereits gesprungen, ein zweiter Sprung wuerde das
        Stueck nach dem Marker doppelt spielen (und _on_play() von vorne
        starten). Gestoppt/pausiert: normaler Play-Weg (Rules,
        Spieldauer-Timer wie beim Play-Button bzw. Resume)."""
        eng = self.player.engine
        if eng.is_playing():
            return
        if eng.is_loaded() and not eng.is_paused():
            # Start aus dem Stopp: play() verwirft die ersten Samples als
            # Warmup -> um genau diese Strecke frueher ansetzen, damit der
            # Marker selbst als Erstes zu hoeren ist.
            self._jump_to_time(
                max(0.0, time_seconds - eng.play_warmup_song_seconds()))
            self.player._on_play()
            return
        self._jump_to_time(time_seconds)
        if eng.is_loaded() and not eng.is_playing():
            self.player._on_play()

    def _add_custom_marker(self):
        """Set-Marker-Button: legt an der aktuellen Abspielposition einen Marker an.

        Fragt sofort nach einer Beschriftung (vorbefuellt mit dem Zeitstempel).
        """
        if not self._current_song:
            return
        pos = self.engine.get_playback_position_seconds()
        default_caption = fmt_time(pos)
        caption, ok = QInputDialog.getText(
            self, _t("marker_add_title"),
            _t("marker_add_prompt", time=fmt_precise(pos)),
            text=default_caption)
        if not ok:
            return
        self.db.add_marker(self._current_song.id, pos, caption.strip())
        # Marker-Zeile in Song Data sofort aktualisieren
        if hasattr(self, 'song_data'):
            self.song_data._refresh_markers(self._current_song)
        # Jump-Markers-Widget beim naechsten Tick neu aufbauen
        self._jm_sig = None

    def _rule_create_jump_marker(self, params: dict):
        """Rule-Aktion: Custom-Jump-Marker an der aktuellen Abspielposition.

        Feuert nur bei LAUFENDER Wiedergabe (engine.playing). Anders als der
        manuelle Set-Marker-Button fragt diese Aktion NICHT nach einer
        Beschriftung — sie nimmt automatisch die aktuelle Position als mm:ss.
        Liegt bereits ein Marker naeher als 1 s an dieser Position, wird kein
        zweiter gesetzt (Nah-Duplikat-Schutz, z.B. Button zweimal gedrueckt).
        """
        if not self._current_song or not self.engine.playing:
            return
        pos = self.engine.get_playback_position_seconds()
        # Nah-Duplikate ueberspringen
        try:
            for _idx, t, _caption in self.db.get_markers(self._current_song.id):
                if abs(float(t) - pos) < 1.0:
                    return
        except Exception:
            pass
        self.db.add_marker(self._current_song.id, pos, fmt_time(pos))
        # Marker-Zeile in Song Data sofort aktualisieren
        if hasattr(self, 'song_data'):
            self.song_data._refresh_markers(self._current_song)
        # Jump-Markers-Widget beim naechsten Tick neu aufbauen
        self._jm_sig = None

    def _rule_auto_set_best_loop(self, params: dict):
        """Analysiert den aktuellen Song und setzt den besten Loop gemaess Preset."""
        if not self._current_song:
            return
        if getattr(self, '_auto_loop_worker', None) is not None:
            return  # Analyse laeuft bereits (z.B. schnelles Durchsteppen)
        # Loop Finder bei Bedarf initialisieren (lazy)
        self._init_loop_finder()
        filepath = self.loop_finder._filepath
        if not filepath:
            return
        bpm = self._current_song.base_bpm if self._current_song.base_bpm > 0 else None
        dur = self.engine.get_original_duration()
        if dur <= 0:
            return

        # Preset-Parameter laden
        preset_name = params.get("preset", self.loop_finder.SINGING_PRESET_NAME)
        preset_data = self.loop_finder._load_preset(str(preset_name))
        in_start_pct = int(preset_data.get("in_start", self.loop_finder._DEFAULT_IN_START))
        in_end_pct = int(preset_data.get("in_end", self.loop_finder._DEFAULT_IN_END))
        out_start_pct = int(preset_data.get("out_start", self.loop_finder._DEFAULT_OUT_START))
        out_end_pct = int(preset_data.get("out_end", self.loop_finder._DEFAULT_OUT_END))
        compare_beats = int(preset_data.get("compare_beats", 16))
        self._auto_loop_strategy = str(preset_data.get("selection_strategy", "best_64"))

        # "Bitte warten"-Hinweis anzeigen (verschwindet automatisch)
        self._auto_loop_overlay = QLabel(_t("auto_loop_wait"), self)
        self._auto_loop_overlay.setAlignment(Qt.AlignCenter)
        self._auto_loop_overlay.setStyleSheet(
            "background: rgba(0,0,0,180); color: white; font-size: 16px; "
            "font-weight: bold; padding: 20px 40px; border-radius: 8px;")
        self._auto_loop_overlay.adjustSize()
        # Zentriert im Hauptfenster positionieren
        cx = (self.width() - self._auto_loop_overlay.width()) // 2
        cy = (self.height() - self._auto_loop_overlay.height()) // 2
        self._auto_loop_overlay.move(cx, cy)
        self._auto_loop_overlay.show()
        self._auto_loop_overlay.raise_()

        # Play-Gate: Token holen — startet gleichzeitig ein Song, wartet der
        # hoerbare Audio-Start, bis der Loop-Finder fertig ist (Loop ist dann
        # garantiert gesetzt, bevor der Song laeuft). Release am Thread-Ende,
        # NACH _on_auto_loop_done (done wird vor finished zugestellt).
        gate_token = self._play_barrier.add_token_if_collecting()
        worker = LoopFinderWorker(
            filepath, bpm=bpm, compare_beats=compare_beats,
            in_start=dur * in_start_pct / 100,
            in_end=dur * in_end_pct / 100,
            out_start=dur * out_start_pct / 100,
            out_end=dur * out_end_pct / 100)
        worker.done.connect(self._on_auto_loop_done)
        worker.error.connect(self._on_auto_loop_error)
        # TIC-0029: Referenz erst beim ECHTEN Thread-Ende freigeben (nicht im
        # fachlichen Callback) — sonst zerstoert der GC das QThread waehrend es laeuft.
        worker.finished.connect(lambda: self._release_worker('_auto_loop_worker'))
        worker.finished.connect(lambda: self._play_barrier.release(gate_token))
        self._auto_loop_worker = worker
        worker.start()

    def _release_worker(self, attr: str):
        """Gibt einen QThread-Worker erst nach echtem Thread-Ende sicher frei (TIC-0029).

        An QThread.finished gebunden — zu diesem Zeitpunkt ist run() garantiert
        zurueckgekehrt. Erst dann darf die letzte Python-Referenz fallen und das
        C++-Objekt via deleteLater abgeraeumt werden.
        """
        w = getattr(self, attr, None)
        setattr(self, attr, None)
        if w is not None:
            w.deleteLater()

    def _on_auto_loop_error(self, msg):
        """Callback: Auto-Loop-Analyse fehlgeschlagen."""
        print(f"[AutoLoop] Fehler: {msg}")
        self._dismiss_auto_loop_overlay()

    def _dismiss_auto_loop_overlay(self):
        """Entfernt das 'Bitte warten'-Overlay."""
        overlay = getattr(self, '_auto_loop_overlay', None)
        if overlay:
            overlay.deleteLater()
            self._auto_loop_overlay = None

    def _rule_auto_detect_bpm(self, params: dict):
        """Startet BPM-Erkennung im Hintergrund fuer den aktuell geladenen Song."""
        if not self._current_song:
            return
        filepath = self.paths.find_song_file(self._current_song.filename) if self.paths else None
        if not filepath or not os.path.isfile(filepath):
            return
        if getattr(self, '_rule_bpm_worker', None) is not None:
            return  # Erkennung laeuft bereits
        self._rule_bpm_overlay = QLabel(_t("auto_bpm_wait"), self)
        self._rule_bpm_overlay.setAlignment(Qt.AlignCenter)
        self._rule_bpm_overlay.setStyleSheet(
            "background: rgba(0,0,0,180); color: white; font-size: 16px; "
            "font-weight: bold; padding: 20px 40px; border-radius: 8px;")
        self._rule_bpm_overlay.adjustSize()
        cx = (self.width()  - self._rule_bpm_overlay.width())  // 2
        cy = (self.height() - self._rule_bpm_overlay.height()) // 2
        self._rule_bpm_overlay.move(cx, cy)
        self._rule_bpm_overlay.show()
        self._rule_bpm_overlay.raise_()
        worker = BpmWorker(filepath)
        worker.done.connect(self._on_rule_bpm_result)
        worker.error.connect(self._on_rule_bpm_error)
        # TIC-0029: Referenz erst beim echten Thread-Ende freigeben.
        worker.finished.connect(lambda: self._release_worker('_rule_bpm_worker'))
        self._rule_bpm_worker = worker
        worker.start()

    def _dismiss_rule_bpm_overlay(self):
        overlay = getattr(self, '_rule_bpm_overlay', None)
        if overlay:
            overlay.deleteLater()
            self._rule_bpm_overlay = None

    def _on_rule_bpm_result(self, bpm: float):
        """Callback: BPM erkannt — Song und DB aktualisieren."""
        # TIC-0029: Referenz-Freigabe via _release_worker am echten Thread-Ende.
        self._dismiss_rule_bpm_overlay()
        if not self._current_song:
            return
        self._current_song.base_bpm = bpm
        self.db.update(self._current_song)
        if hasattr(self, 'song_data') and self.song_data:
            self.song_data.spin_bpm.setValue(bpm)
        print(f"[AutoBPM] Erkannt: {bpm:.1f} BPM")

    def _on_rule_bpm_error(self, msg: str):
        """Callback: BPM-Erkennung fehlgeschlagen."""
        self._dismiss_rule_bpm_overlay()
        print(f"[AutoBPM] Fehler: {msg}")

    def _on_auto_loop_done(self, candidates):
        """Callback: Auto-Loop-Analyse fertig — besten Loop gemaess Strategie setzen."""
        from loop_finder import apply_selection_strategy
        # TIC-0029: Worker-Referenz NICHT hier nullen — das uebernimmt _release_worker
        # am echten QThread.finished.
        self._dismiss_auto_loop_overlay()
        if not candidates:
            return
        strategy = getattr(self, '_auto_loop_strategy', 'best_64')
        chosen = apply_selection_strategy(candidates, strategy)
        if chosen:
            self._apply_loop_values(chosen.loop_in, chosen.loop_out)

    def _apply_loop_values(self, loop_in: float, loop_out: float):
        """Setzt Loop-Werte in Engine + DB (UI-unabhaengig)."""
        if not self._current_song:
            return
        self.engine.set_loop_in(loop_in)
        self.engine.set_loop_out(loop_out)
        self._current_song.loop_in = loop_in
        self._current_song.loop_out = loop_out
        self.db.save_playback_settings(
            self._current_song.id, loop_in=loop_in, loop_out=loop_out)
        self.loop_widget.update_display()
        self.song_data.spin_loop_in.setValue(loop_in)
        self.song_data.spin_loop_out.setValue(loop_out)

    def _ensure_system_rules_json(self):
        """Kopiert rules_system.json nach rules/ falls nicht vorhanden."""
        import shutil
        rules_dir = os.path.join(self._app_dir, "rules")
        os.makedirs(rules_dir, exist_ok=True)
        target = os.path.join(rules_dir, "rules_system.json")
        if not os.path.exists(target):
            # Quelle: neben main.py (Dev) oder neben EXE (Frozen)
            if getattr(sys, 'frozen', False):
                src = os.path.join(os.path.dirname(sys.executable),
                                   "rules_system.json")
            else:
                src = os.path.join(os.path.dirname(__file__),
                                   "rules_system.json")
            if os.path.exists(src):
                shutil.copy2(src, target)
            else:
                # Fallback: aus rule_definitions erzeugen
                from rule_definitions import SYSTEM_RULES_DEFAULT
                with open(target, "w", encoding="utf-8") as f:
                    json.dump(SYSTEM_RULES_DEFAULT, f, indent=2,
                              ensure_ascii=False)

    # ---- Menu ----

    def _build_menu(self):
        menu_bar = self.menuBar()

        # App-Menu (erster Eintrag)
        app_menu = menu_bar.addMenu(_t("menu_app"))
        quit_action = app_menu.addAction(_t("menu_quit"))
        quit_action.triggered.connect(self.close)

        # Ansicht-Menu
        view_menu = menu_bar.addMenu(_t("menu_view"))
        self._view_menu = view_menu
        # dock -> Magnet-Button (Andock-Umschalter je Menuezeile, BL-204)
        self._view_magnets = {}
        for dock, text in [
            (self.dock_player, _t("dock_player")),
            (self.dock_loop, _t("dock_loop")),
            (self.dock_loop_finder, _t("dock_loop_finder")),
            (self.dock_data, _t("dock_song_data")),
            (self.dock_list, _t("dock_song_list")),
            (self.dock_playlist, _t("dock_playlist")),
            (self.dock_manager, _t("dock_planner")),
            (self.dock_lyrics, _t("dock_lyrics")),
            (self.dock_sequences, _t("dock_sequences")),
            (self.dock_reports, _t("dock_reports")),
            (self.dock_potential, _t("dock_potential")),
            (self.dock_stats, _t("dock_stats")),
            (self.dock_photo, _t("dock_photo")),
            (self.dock_notes, _t("dock_notes")),
            (self.dock_evening_planner, _t("dock_evening_planner")),
        ]:
            self._add_view_menu_entry(dock, text)

        # Einstellungen-Menu (ehemals Design)
        settings_menu = menu_bar.addMenu(_t("menu_design"))
        general_settings_action = settings_menu.addAction(_t("menu_general_settings"))
        general_settings_action.setShortcut("Ctrl+,")
        general_settings_action.triggered.connect(self._show_settings_dialog)
        settings_menu.addSeparator()
        load_layout_action = settings_menu.addAction(_t("menu_load_layout"))
        load_layout_action.triggered.connect(self._load_layout_from_file)
        save_layout_action = settings_menu.addAction(_t("menu_save_layout"))
        save_layout_action.triggered.connect(self._save_layout_to_file)
        reset_action = settings_menu.addAction(_t("menu_reset_layout"))
        reset_action.triggered.connect(self._reset_layout)
        settings_menu.addSeparator()
        skin_action = settings_menu.addAction(_t("menu_load_skin"))
        skin_action.triggered.connect(self._load_skin)
        settings_menu.addSeparator()
        # Datumsformat (verschoben aus Ansicht)
        self._date_format_action = settings_menu.addAction(self._date_format_label())
        self._date_format_action.triggered.connect(self._toggle_date_format)
        # Sprache (verschoben aus Info)
        lang_menu = settings_menu.addMenu(_t("menu_language"))
        for code, label in get_available_languages():
            action = lang_menu.addAction(label)
            action.setCheckable(True)
            action.setChecked(code == get_language())
            action.triggered.connect(lambda checked, c=code: self._change_language(c))

        # Datenbank-Menu
        db_menu = menu_bar.addMenu(_t("menu_database"))
        info_action = db_menu.addAction(_t("menu_db_info"))
        info_action.triggered.connect(self._show_db_info)
        manage_genres_action = db_menu.addAction(_t("menu_manage_genres"))
        manage_genres_action.triggered.connect(self._manage_genres)
        manage_programs_action = db_menu.addAction(_t("menu_manage_programs"))
        manage_programs_action.triggered.connect(self._manage_dance_programs)

        # Sequenzen-Menu
        seq_menu = menu_bar.addMenu(_t("menu_sequences"))
        editor_action = seq_menu.addAction(_t("menu_sequence_editor"))
        # WICHTIG: triggered uebergibt einen 'checked'-Bool — nicht als seq_id
        # durchreichen, sonst oeffnet der Editor faelschlich im Bearbeiten-Modus.
        editor_action.triggered.connect(lambda: self._on_sequence_editor())
        seq_menu.addSeparator()
        universal_import_action = seq_menu.addAction(
            _t("menu_import_sequences_universal"))
        universal_import_action.triggered.connect(
            self._on_import_sequences_universal)
        # Alte Einzel-Import-Menueeintraege (MDB/JSON/CSDS/Freitext) wurden
        # zugunsten des Universal-Imports entfernt (BL-098). Die zugrunde
        # liegenden Methoden bleiben fuer eine Uebergangszeit erhalten —
        # endgueltige Entfernung ab 2026-08-01 (siehe Backlog BL-135).
        export_json_action = seq_menu.addAction(_t("menu_export_sequences_json"))
        export_json_action.triggered.connect(self._on_export_sequences_json)
        seq_menu.addSeparator()
        dedup_action = seq_menu.addAction(_t("menu_deduplication"))
        dedup_action.triggered.connect(self._on_deduplication)
        seq_menu.addSeparator()
        call_mapping_action = seq_menu.addAction(_t("menu_call_mapping"))
        call_mapping_action.triggered.connect(self._on_call_mapping)
        mapping_export_action = seq_menu.addAction(_t("menu_mapping_export"))
        mapping_export_action.triggered.connect(self._on_mapping_export)
        mapping_import_action = seq_menu.addAction(_t("menu_mapping_import"))
        mapping_import_action.triggered.connect(self._on_mapping_import)

        # Lokation-Menu
        location_menu = menu_bar.addMenu(_t("menu_location"))
        select_location = location_menu.addAction(_t("menu_select_location"))
        select_location.triggered.connect(self._on_location_button_clicked)

        # Pfade-Menu
        paths_menu = menu_bar.addMenu(_t("menu_paths"))

        show_paths_action = paths_menu.addAction(_t("menu_show_paths"))
        show_paths_action.triggered.connect(self._show_paths_info)

        paths_menu.addSeparator()

        set_music_action = paths_menu.addAction(_t("menu_change_music_dir"))
        set_music_action.triggered.connect(self._manage_music_dirs)

        set_import_action = paths_menu.addAction(_t("menu_change_import_dir"))
        set_import_action.triggered.connect(self._change_import_dir)

        set_lyrics_action = paths_menu.addAction(_t("menu_change_lyrics_dir"))
        set_lyrics_action.triggered.connect(self._change_lyrics_dir)

        paths_menu.addSeparator()

        reindex_action = paths_menu.addAction(_t("menu_reindex_paths"))
        reindex_action.triggered.connect(self._reindex_music_library)

        # --- Tutorials ---
        tutorial_menu = menu_bar.addMenu(_t("menu_tutorials"))
        tutorial_menu.aboutToShow.connect(self._build_tutorial_menu)
        self._tutorial_menu = tutorial_menu

        # --- Info ---
        info_menu = menu_bar.addMenu(_t("menu_info"))
        about_action = info_menu.addAction(_t("menu_about"))
        about_action.triggered.connect(self._show_about)

        report_action = info_menu.addAction(_t("menu_system_report"))
        report_action.triggered.connect(self._create_system_report)

        diagnose_action = info_menu.addAction("Diagnose-Center…")
        diagnose_action.triggered.connect(self._open_diagnose_center)

        info_menu.addSeparator()
        update_action = info_menu.addAction(_t("menu_check_updates"))
        update_action.triggered.connect(self._check_for_updates_manual)

    def _check_for_updates_manual(self):
        """Manuelle Update-Pruefung aus dem Info-Menue (mit Rueckmeldung).

        Der UpdateChecker wird normalerweise in main() nach window.show()
        erzeugt; falls das (z. B. Import-Fehler) nicht geschah, hier nachholen.
        """
        checker = getattr(self, "_update_checker", None)
        if checker is None:
            try:
                import update_check
                checker = update_check.UpdateChecker(self, __version__)
                self._update_checker = checker
            except Exception:
                return
        checker.check_now()


    # --- Tutorial-Aktionen ---

    def _build_tutorial_menu(self):
        """Baut das Tutorial-Menu dynamisch mit Haekchen fuer erledigte."""
        menu = self._tutorial_menu
        menu.clear()

        reset_action = menu.addAction(_t("tutorial.menu_reset_all"))
        reset_action.triggered.connect(self._on_tutorial_reset_all)
        complete_action = menu.addAction(_t("tutorial.menu_complete_all"))
        complete_action.triggered.connect(self._on_tutorial_complete_all)
        menu.addSeparator()

        # Eintraege in Prioritaets-Reihenfolge — Dialog-Tutorials einsortiert
        # (widget_id, label, handler_name)
        entries = []
        for tut in TUTORIALS:
            entries.append((tut.widget_id, _t(f"tutorial.menu_start_{tut.widget_id}"), None))
            # Lokationen-Dialog direkt nach Player einfuegen
            if tut.widget_id == "player":
                entries.append(("location_dialog", _t("tutorial.menu_start_location_dialog"),
                                "_on_tutorial_start_location"))
            # Beat Snap direkt nach Loop Finder einfuegen
            if tut.widget_id == "loop_finder":
                entries.append(("beat_snap", _t("tutorial.menu_start_beat_snap"),
                                "_on_tutorial_start_beat_snap"))

        for wid, label, handler in entries:
            status = self.tutorial_engine.get_status(wid)
            prefix = "\u2713  " if status == "completed" else "    "
            action = menu.addAction(f"{prefix}{label}")
            if handler:
                action.triggered.connect(getattr(self, handler))
            else:
                action.triggered.connect(
                    lambda checked, w=wid: self._on_tutorial_start(w)
                )

    def _on_tutorial_reset_all(self):
        """Setzt alle Tutorial-Status zurueck und startet erneut."""
        self.tutorial_engine.reset_all()
        self.tutorial_engine.check_and_start()

    def _on_tutorial_complete_all(self):
        """Markiert alle Tutorials als abgeschlossen."""
        self.tutorial_engine.complete_all()

    def _on_tutorial_start(self, widget_id: str):
        """Startet ein bestimmtes Tutorial direkt (Menu hat Vorrang)."""
        self.tutorial_engine.start_specific(widget_id)

    def _on_tutorial_start_location(self):
        """Startet das Lokationen-Tutorial direkt (oeffnet den Dialog)."""
        # Laufendes Tutorial beenden
        if self.tutorial_engine._active_tutorial:
            self.tutorial_engine._close_overlay()
            self.tutorial_engine._active_tutorial = None
        self.tutorial_engine._paused_for_session = False
        self.tutorial_engine.reset_one("location_dialog")
        self._on_location_button_clicked()

    def _on_tutorial_start_beat_snap(self):
        """Startet das Beat-Snap-Tutorial direkt (oeffnet den Dialog)."""
        # Laufendes Tutorial beenden
        if self.tutorial_engine._active_tutorial:
            self.tutorial_engine._close_overlay()
            self.tutorial_engine._active_tutorial = None
        self.tutorial_engine._paused_for_session = False
        self.tutorial_engine.reset_one("beat_snap")
        self.tutorial_engine._open_beat_snap_with_tutorial()

    def _change_language(self, lang_code: str):
        """Sprache aendern — wird erst nach Neustart wirksam."""
        self._settings.setValue("display/language", lang_code)
        QMessageBox.information(
            self, _t("language_restart_title"),
            _t("language_restart_msg")
        )

    def _show_about(self):
        QMessageBox.about(
            self, _t("about_title"),
            _t("about_text", version=_VERSION)
        )

    def _open_diagnose_center(self):
        """Oeffnet das Diagnose-Center (Strang 3)."""
        try:
            from diagnose_center import DiagnoseCenterDialog
            dlg = DiagnoseCenterDialog(self._app_dir, parent=self)
            dlg.exec()
        except Exception as e:
            QMessageBox.warning(
                self, "Diagnose-Center",
                f"Konnte Diagnose-Center nicht oeffnen: {e}")

    def _create_system_report(self):
        """Erstellt einen System-Report und zeigt den Pfad an."""
        try:
            path = generate_report(_VERSION, self._app_dir, progress_parent=self)
            QMessageBox.information(
                self, _t("system_report_title"),
                _t("system_report_done", path=path)
            )
            # Datei im Explorer markieren
            os.startfile(os.path.dirname(path))
        except Exception as e:
            QMessageBox.warning(
                self, _t("system_report_title"),
                _t("system_report_error", error=str(e))
            )

    def _show_db_info(self):
        count = self.db.count()
        location_count = len(self.db.get_all_locations())
        seq_count = self.db.get_sequence_count()
        QMessageBox.information(
            self, _t("db_info_title"),
            _t("db_info_text", path=self.db.db_path, songs=count,
               locations=location_count, sequences=seq_count)
        )

    def _manage_genres(self):
        """Oeffnet den Genre-Manager-Dialog."""
        dlg = _GenreManagerDialog(self.db, parent=self)
        dlg.exec()
        # Songlist und Planner nach Aenderungen aktualisieren
        self.playlist_manager.refresh_genres()
        self.playlist_manager.refresh()
        if self.song_data.isVisible() and self.song_data._current_song:
            genres = self.db.get_genres_for_song(self.song_data._current_song.id)
            genre_text = ", ".join(name for _, name in genres) if genres else "\u2014"
            self.song_data.label_genre.setText(genre_text)

    def _manage_dance_programs(self):
        """Oeffnet den Tanzprogramm-Manager-Dialog."""
        dlg = _DanceProgramManagerDialog(self.db, parent=self)
        dlg.exec()

    def _get_current_target_duration(self) -> float:
        """BL-085: Gibt target_duration_min des aktiven Tanzprogramms zurueck (Fallback 7.0)."""
        # TIC-0026: Guard — DB koennte durch closeEvent bereits geschlossen sein
        if not self.db.is_open():
            return 7.0
        pid = getattr(self.player, '_dance_program_id', None)
        if pid is None:
            return 7.0
        for row in self.db.get_all_dance_programs():
            if row[0] == pid:
                return float(row[4])
        return 7.0

    # ---- Sequenzen ----

    def _init_sequences(self):
        """Initialisiert Sequenzen-Widget beim Startup."""
        _ts0 = perf_start()
        count = self.db.get_sequence_count()
        if count > 0:
            self.sequences_widget.load_sequences()
            _ts1 = perf_split(f"    _init_sequences.load_sequences ({count})", _ts0)
            print(f"[P28] {count} Sequenzen geladen")
            # SequenceView mit erster Sequenz vorbefuellen (Dock ist noch versteckt)
            seq_ids = self.sequences_widget.get_filtered_seq_ids()
            if seq_ids:
                self.sequence_view_widget.set_sequence(self.db, seq_ids, 0)
            perf_split("    _init_sequences.sequence_view prefill", _ts1)

    def _on_export_sequences_json(self):
        """Menue: Alle Sequenzen als JSON-Datei exportieren (gleiche Struktur wie Import)."""
        import json as _json
        rows = self.db.get_all_sequences_for_export()
        if not rows:
            QMessageBox.information(
                self, _t("seq_export_title"), _t("seq_export_empty")
            )
            return
        last_dir = str(self._settings.value("sequences/json_import_dir", ""))
        if not last_dir or not os.path.isdir(last_dir):
            last_dir = os.path.expanduser("~")
        path, _ = QFileDialog.getSaveFileName(
            self, _t("seq_export_title"), last_dir,
            "JSON-Dateien (*.json)"
        )
        if not path:
            return
        if not path.lower().endswith(".json"):
            path += ".json"
        self._settings.setValue("sequences/json_import_dir",
                                os.path.dirname(path))
        with open(path, "w", encoding="utf-8") as f:
            _json.dump(rows, f, ensure_ascii=False, indent=2)
        QMessageBox.information(
            self, _t("seq_export_title"),
            _t("seq_export_ok", count=len(rows))
        )

    def _on_sequence_view_delete(self, seq_id: int):
        """SequenceView hat 'Löschen' gedrueckt — Rueckfrage hat dort schon
        stattgefunden, hier wird endgueltig geloescht und alle Anzeigen
        aktualisiert."""
        deleted = self.db.delete_sequences([seq_id])
        print(f"[Sequenzen] {deleted} via SequenceView geloescht: {seq_id}")
        self.sequences_widget._populate_dropdowns()
        self.sequences_widget.load_sequences()
        self.sequence_view_widget.remove_id_after_delete(seq_id)

    def _on_sequences_deleted(self, seq_ids: list):
        """SequencesWidget hat geloescht — SequenceView informieren, damit
        es zur naechsten / vorherigen Sequenz wechselt (oder leer wird).
        """
        for sid in seq_ids:
            self.sequence_view_widget.remove_id_after_delete(sid)

    def _on_sequence_editor(self, seq_id: int = None):
        """Menue/Button: Sequenz-Editor oeffnen (Neuanlage oder Bearbeiten)."""
        # Defensive: bool (z.B. aus einem Signal-'checked') ist KEINE gueltige id
        if not isinstance(seq_id, int) or isinstance(seq_id, bool):
            seq_id = None

        def _after_save(saved_id, was_new):
            # max_teaching_order neu berechnen + Tabelle/Dropdowns aktualisieren
            self.sequences_widget._do_remapping()
            if was_new:
                # Filter zuruecksetzen, damit die neue Sequenz garantiert sichtbar
                # ist, dann markieren + im SequenzView oeffnen
                self.sequences_widget.reset_filters()
                self.sequences_widget.select_sequence(saved_id)
            else:
                seq_ids = self.sequences_widget.get_filtered_seq_ids()
                if seq_ids:
                    idx = self.sequences_widget.get_current_seq_idx()
                    self.sequence_view_widget.set_sequence(self.db, seq_ids, idx)

        dlg = SequenceEditorDialog(self.db, self, seq_id=seq_id,
                                   on_saved=_after_save)
        dlg.exec()
        self.dock_sequences.raise_()

    def _on_deduplication(self):
        """Menue: Duplikate-Dialog oeffnen."""
        dlg = DeduplicationDialog(self.db, self)
        dlg.exec()
        if dlg.deleted_count() > 0:
            self.sequences_widget.load_sequences()

    def _on_call_mapping(self):
        """Menue: Call-Mapping-Dialog oeffnen."""
        self._open_call_mapping()

    def _open_call_mapping(self, focus_texts=None):
        """Call-Mapping-Dialog oeffnen; focus_texts filtert ihn beim Start auf
        diese Call-Texte (intern#119, Rechtsklick auf eine rote Sequenz)."""
        if self.db.get_teaching_order_count() == 0:
            QMessageBox.warning(
                self, _t("call_mapping_title"),
                _t("call_mapping_no_to_calls")
            )
            return
        # Kein "alles gemappt"-Abbruch mehr: auch dann gibt es Vorschlaege zum
        # Ergaenzen/Aendern ("Optimieren", intern#97).
        dlg = CallMappingDialog(self.db, self, focus_texts=focus_texts)
        if dlg.exec() == QDialog.Accepted:
            # Remapping anstossen damit max_teaching_order aktualisiert wird
            self.sequences_widget._do_remapping()
        elif dlg.wrote_assignments:
            # "Optimieren" (intern#97) hat schon geschrieben und die Baender
            # nachgerechnet -> bei Abbrechen nur die Sequenzansicht neu laden,
            # nicht noch einmal rechnen (~120 ms auf dem Main-Thread).
            self.sequences_widget.load_sequences()

    def _on_mapping_export(self):
        """Menue: Call-Maps als JSON exportieren (v2 mit Header, intern#79)."""
        import json as _json
        data = mapping_io.build_export(self.db)
        if not data["mappings"]:
            QMessageBox.information(
                self, _t("mapping_export_title"), _t("mapping_export_empty")
            )
            return
        last_dir = str(self._settings.value("sequences/mapping_export_dir", ""))
        path, _ = QFileDialog.getSaveFileName(
            self, _t("mapping_export_title"), last_dir,
            "JSON-Dateien (*.json)"
        )
        if not path:
            return
        if not path.lower().endswith(".json"):
            path += ".json"
        self._settings.setValue("sequences/mapping_export_dir",
                                str(os.path.dirname(path)))
        with open(path, "w", encoding="utf-8") as f:
            _json.dump(data, f, ensure_ascii=False, indent=2)
        QMessageBox.information(
            self, _t("mapping_export_title"),
            _t("mapping_export_ok", count=len(data["mappings"]))
        )

    def _on_mapping_import(self):
        """Menue: Call-Maps importieren (v1 + v2), Konflikte klaeren lassen
        (intern#79). Ablauf in dialogs_mapping_conflict.run_mapping_import."""
        import json as _json
        last_dir = str(self._settings.value("sequences/mapping_export_dir", ""))
        path, _ = QFileDialog.getOpenFileName(
            self, _t("mapping_import_title"), last_dir,
            "JSON-Dateien (*.json)"
        )
        if not path:
            return
        self._settings.setValue("sequences/mapping_export_dir",
                                str(os.path.dirname(path)))
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = _json.load(f)
            res = run_mapping_import(self, self.db, data)
        except mapping_io.CallMapFormatError as e:
            QMessageBox.warning(
                self, _t("mapping_import_title"),
                _t("mapping_import_error", msg=_t(e.key, **e.params))
            )
            return
        except Exception as e:
            QMessageBox.warning(
                self, _t("mapping_import_title"),
                _t("mapping_import_error", msg=str(e))
            )
            return
        if res is None:
            return   # Konfliktklaerung abgebrochen: nichts geschrieben
        if res["written"]:
            # Remapping anstossen damit max_teaching_order aktualisiert wird
            self.sequences_widget._do_remapping()
        lines = [_t("mapping_import_summary", new=res["new"],
                    identical=res["identical"], kept=res["kept"],
                    taken=res["taken"], custom=res["custom"])]
        if res["unknown_figures"]:
            lines.append(_t("mapping_import_unknown",
                            figures=", ".join(res["unknown_figures"]),
                            skipped=len(res["skipped"])))
        QMessageBox.information(self, _t("mapping_import_title"),
                                "\n\n".join(lines))

    def _on_import_sequences_universal(self):
        """Universeller Sequenz-Import (BL-098): erkennt MDB/JSON/CSDS/Freitext."""
        dlg = SequenceImportDialog(self.db, self._settings, parent=self)
        if dlg.exec() != QDialog.Accepted:
            return
        inserted, skipped = dlg.get_summary()
        # Tabelle + Dropdowns aktualisieren
        self.sequences_widget._populate_dropdowns()
        self.sequences_widget.load_sequences()
        self.dock_sequences.raise_()
        QMessageBox.information(
            self, _t("seq_import_title"),
            _t("seq_import_done", inserted=inserted, dupes=skipped)
        )

    def _show_paths_info(self):
        """Zeigt alle konfigurierten Pfade an."""
        info = self.paths.get_info()
        lines = []
        for key, value in info.items():
            lines.append(f"{key}: {value}")
        QMessageBox.information(
            self, _t("paths_info_title"),
            "\n".join(lines)
        )

    def _manage_music_dirs(self):
        """Oeffnet einen Dialog zum Verwalten der bis zu 4 Musik-Pfad-Slots."""
        from PySide6.QtWidgets import (
            QDialog, QVBoxLayout, QHBoxLayout, QLabel,
            QLineEdit, QPushButton, QDialogButtonBox, QSizePolicy
        )
        from path_manager import MUSIC_DIR_SLOTS

        dlg = QDialog(self)
        dlg.setWindowTitle(_t("music_dirs_title"))
        dlg.setMinimumWidth(560)

        main_layout = QVBoxLayout(dlg)
        main_layout.setSpacing(8)

        line_edits = []

        for slot in range(1, MUSIC_DIR_SLOTS + 1):
            if slot == 1:
                label_text = _t("music_dirs_slot1_label")
            else:
                label_text = _t("music_dirs_slot_label", slot=slot)

            label = QLabel(label_text)
            main_layout.addWidget(label)

            row = QHBoxLayout()
            row.setSpacing(4)

            edit = QLineEdit()
            edit.setReadOnly(True)
            edit.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            current_path = self.paths.get_music_dir_raw(slot)
            edit.setText(current_path)
            row.addWidget(edit)

            btn_browse = QPushButton(_t("music_dirs_browse"))
            btn_browse.setObjectName("fileBtn")
            btn_browse.setFixedWidth(36)
            btn_browse.setToolTip(_t("music_dirs_dialog_title", slot=slot))

            def _make_browse(s, ed):
                def _browse():
                    start = ed.text() or self.paths.app_dir
                    chosen = QFileDialog.getExistingDirectory(
                        dlg, _t("music_dirs_dialog_title", slot=s), start
                    )
                    if chosen:
                        ed.setText(chosen)
                return _browse

            btn_browse.clicked.connect(_make_browse(slot, edit))
            row.addWidget(btn_browse)

            if slot > 1:
                btn_clear = QPushButton(_t("music_dirs_clear"))
                btn_clear.setFixedWidth(60)

                def _make_clear(ed):
                    def _clear():
                        ed.clear()
                    return _clear

                btn_clear.clicked.connect(_make_clear(edit))
                row.addWidget(btn_clear)

            main_layout.addLayout(row)
            line_edits.append(edit)

        main_layout.addSpacing(8)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        main_layout.addWidget(buttons)

        if dlg.exec() == QDialog.Accepted:
            for slot, edit in enumerate(line_edits, start=1):
                self.paths.set_music_dir(edit.text().strip(), slot=slot)
            QMessageBox.information(
                self, _t("music_dirs_title"), _t("music_dirs_saved")
            )

    def _change_import_dir(self):
        """Aendert das Import-Verzeichnis per Dialog."""
        current = self.paths.import_dir
        new_dir = QFileDialog.getExistingDirectory(
            self, _t("dialog_import_dir"), current
        )
        if new_dir:
            self.paths.set_import_dir(new_dir)
            QMessageBox.information(
                self, _t("import_dir_title"),
                _t("import_dir_msg", path=new_dir)
            )

    def _change_lyrics_dir(self):
        """Aendert das Lyrics-Verzeichnis per Dialog."""
        current = self.paths.lyrics_dir
        new_dir = QFileDialog.getExistingDirectory(
            self, _t("dialog_lyrics_dir"), current
        )
        if new_dir:
            self.paths.set_lyrics_dir(new_dir)
            QMessageBox.information(
                self, _t("lyrics_dir_title"),
                _t("lyrics_dir_msg", path=new_dir)
            )

    # ---- Musikbibliothek re-indexieren (BL-147) ----

    def _reindex_music_library(self):
        """Durchsucht alle Musik-Slots rekursiv und hebt Songs, deren Datei in
        einem Unterordner liegt, auf den passenden relativen Pfad.

        Audio-Prioritaet: Der rekursive Scan laeuft in einem QThread-Worker,
        nie auf dem Main-Thread.
        """
        if not self.paths or not self.paths.music_dirs:
            QMessageBox.information(
                self, _t("menu_reindex_paths"), _t("reindex_no_slots"))
            return
        reply = QMessageBox.question(
            self, _t("menu_reindex_paths"), _t("reindex_intro_text"),
            QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
        if reply != QMessageBox.Yes:
            return
        songs = [(s.id, s.filename) for s in self.db.get_all()]
        music_dirs = self.paths.music_dirs
        self._reindex_progress = QProgressDialog(
            _t("reindex_scanning"), None, 0, 0, self)
        self._reindex_progress.setWindowTitle(_t("menu_reindex_paths"))
        self._reindex_progress.setWindowModality(Qt.WindowModal)
        self._reindex_progress.setMinimumDuration(0)
        self._reindex_progress.setCancelButton(None)
        self._reindex_progress.show()
        self._reindex_worker = _ReindexWorker(songs, music_dirs)
        self._reindex_worker.progress.connect(
            lambda p: self._reindex_progress.setLabelText(
                _t("reindex_scanning") + "\n" + p))
        self._reindex_worker.finished.connect(self._on_reindex_done)
        self._reindex_worker.start()

    def _on_reindex_done(self, updates, ambiguous, still_missing):
        """Wendet die vom Worker gefundenen relativen Pfade an und zeigt Report."""
        if getattr(self, "_reindex_progress", None):
            self._reindex_progress.close()
            self._reindex_progress = None
        applied = 0
        conflicts = 0
        for song_id, rel in updates:
            err = self.db.update_filename(song_id, rel)
            if err:
                conflicts += 1
                print(f"[Reindex] Konflikt #{song_id} -> '{rel}': {err}")
            else:
                applied += 1
                print(f"[Reindex] #{song_id} -> '{rel}'")
        if applied:
            try:
                self.song_list.refresh()
            except Exception:
                pass
        QMessageBox.information(
            self, _t("reindex_done_title"),
            _t("reindex_done_text", updated=applied, ambiguous=len(ambiguous),
               missing=still_missing, conflicts=conflicts))

    # ---- Datumsformat ----

    def _date_format_label(self):
        """Gibt den Menuetext fuer den aktuellen Datumsformat-Toggle zurueck."""
        if self._date_format == "de":
            return _t("menu_date_format_de_to_us")
        else:
            return _t("menu_date_format_us_to_de")

    def _toggle_date_format(self):
        """Wechselt zwischen deutschem und US-Datumsformat."""
        if self._date_format == "de":
            self._date_format = "us"
        else:
            self._date_format = "de"
        self._settings.setValue("display/date_format", self._date_format)
        self.song_list.set_date_format(self._date_format)
        self.playlist_manager.set_date_format(self._date_format)
        if self.reports_widget:
            self.reports_widget.set_date_format(self._date_format)
        self._refresh_last_played()
        self._date_format_action.setText(self._date_format_label())
        print(f"[P21] Datumsformat gewechselt auf: {self._date_format}")

    # ---- Layout-Persistenz ----

    def _layout_path(self) -> str:
        """Pfad zur layout.ini im app_dir (2_Test/ oder neben EXE), pro Skin."""
        return os.path.join(self._app_dir, "skins",
                            self.skin_mgr.current_skin, "layout.ini")

    def _raised_tab_docknames(self) -> list:
        """Liefert die objectNames der jeweils vordersten Docks aller Tab-Gruppen.

        Uniform fuer ALLE Docks (auch kuenftige): Qt's restoreState() stellt die
        Tab-Gruppen und Positionen wieder her, vergisst aber zuverlaessig, WELCHER
        Tab vorne lag. Das speichern/restaurieren wir hier separat ueber die
        Fenstertitel (eindeutig) -> objectName.
        """
        from PySide6.QtWidgets import QTabBar
        names = []
        title_to_dock = {d.windowTitle(): d
                         for d in self.findChildren(QDockWidget)}
        for tb in self.findChildren(QTabBar):
            if tb.count() == 0:
                continue
            d = title_to_dock.get(tb.tabText(tb.currentIndex()))
            if d is not None and d.objectName():
                names.append(d.objectName())
        return names

    def _restore_raised_tabs(self, names=None):
        """Bringt die vorderen Tabs (pro Gruppe) wieder nach vorne.

        names: Liste von objectNames; None = aus der Haupt-INI lesen.
        Beim Start muss dies NACH show() laufen — vorher ignoriert Qt raise_()
        auf noch nicht sichtbare Docks (daher QTimer.singleShot(0, ...)).
        """
        if names is None:
            names = self._settings.value("raisedTabs", []) or []
        if isinstance(names, str):
            names = [names]
        for name in names:
            d = self.findChild(QDockWidget, name)
            if d is not None and not d.isFloating():
                d.raise_()

    # Frei schwebende Tool-Fenster (kein Teil des angedockten Haupt-Layouts).
    # Ihre Floating-Geometrie MUSS separat gesichert werden: saveState()
    # erfasst die Geometrie eines beim Beenden geschlossenen (hidden)
    # Floating-Docks NICHT (per Zwei-Prozess-Test verifiziert). windowState
    # bleibt Quelle für Position-im-Dockbereich, Sichtbarkeit und Tabs.
    _FLOAT_TOOL_DOCK_ATTRS = (
        "dock_manager", "dock_loop_finder", "dock_photo", "dock_evening_planner",
        "dock_break", "dock_rules", "dock_reports", "dock_potential", "dock_stats",
        "dock_lyrics",  # #66: letzte Floating-Position auch ueber Neustart halten
        "dock_to_call",  # #121: frei schwebend oft fast bildschirmfuellend
    )

    def _floating_tool_docks(self):
        return [d for d in (getattr(self, a, None) for a in self._FLOAT_TOOL_DOCK_ATTRS)
                if d is not None]

    def _save_float_geoms(self, settings):
        """Floating-Geometrie jedes Tool-Fensters explizit sichern.

        #121: als QRect unter floatrect/<name> (per setGeometry wiederher-
        gestellt, ohne Versatz). Die alten floatgeom-Bytes werden entfernt.
        Ein noch vorgemerkter Wert (Dock in dieser Sitzung nie gezeigt) hat
        Vorrang vor geometry(), die dann nur Qt-Defaults enthielte.

        Angedockte Docks behalten ihre letzte Floating-Position: vorgemerkt
        oder aus der App-INI (floatrect, sonst einmalig aus alten floatgeom-
        Bytes umgerechnet). floatgeom wird erst entfernt, NACHDEM floatrect
        geschrieben ist — sonst liefe der Fallback bei jedem Start erneut
        bzw. ginge die Position verloren. Unlesbare Bytes bleiben stehen."""
        for dock in self._floating_tool_docks():
            name = dock.objectName()
            if not name:
                continue
            if dock.isFloating():
                rect = self._pending_float_geom.get(name) or dock.geometry()
            else:
                # Quelle ist immer die App-INI, nicht das Ziel: beim Layout-
                # Export ist settings eine neue oder alte fremde Datei.
                rect = (self._pending_float_geom.get(name)
                        or self._read_float_rect(self._settings, name))
            if rect is None:
                continue
            settings.setValue(f"floatrect/{name}", rect)
            settings.remove(f"floatgeom/{name}")

    # QWidget.saveGeometry(): Magic, Major/Minor (uint16), dann frameGeometry
    # und normalGeometry als je 4 x int32 (x1, y1, x2, y2), big-endian.
    _SAVED_GEOMETRY_MAGIC = 0x1D9D0CB
    _SAVED_GEOMETRY_HEAD = struct.Struct(">IHH8i")

    @staticmethod
    def _rect_from_saved_geometry(data):
        """Liest aus alten floatgeom-Bytes (QWidget.saveGeometry) das Client-
        Rechteck (normalGeometry). Nur Fallback fuer INIs von vor #121;
        None, wenn das Format nicht passt.

        Bewusst per struct statt QDataStream: QDataStream(QByteArray(data))
        haelt das temporaere QByteArray nicht am Leben und liest dann
        freigegebenen Speicher (Muell-Rechteck, Absturz beim Start, #121)."""
        head = P29MainWindow._SAVED_GEOMETRY_HEAD
        try:
            raw = bytes(data)
            if len(raw) < head.size:
                return None
            (magic, _major, _minor, _fx1, _fy1, _fx2, _fy2,
             x1, y1, x2, y2) = head.unpack_from(raw)
        except (TypeError, ValueError, struct.error):
            return None
        if magic != P29MainWindow._SAVED_GEOMETRY_MAGIC:
            return None
        # Unsinnige Werte (kaputte Bytes) nicht als Position uebernehmen
        if any(abs(v) > 100000 for v in (x1, y1, x2, y2)):
            return None
        normal = QRect(x1, y1, x2 - x1 + 1, y2 - y1 + 1)
        return normal if normal.isValid() else None

    def _read_float_rect(self, settings, name):
        """floatrect/<name> (QRect); sonst Fallback auf alte floatgeom-Bytes."""
        rect = settings.value(f"floatrect/{name}")
        if isinstance(rect, QRect) and rect.isValid():
            return rect
        legacy = settings.value(f"floatgeom/{name}")
        return (self._rect_from_saved_geometry(legacy)
                if legacy is not None else None)

    def _restore_float_geoms(self, settings):
        """Gespeicherte Floating-Geometrie vormerken und anwenden.

        Werte vormerken; bereits sichtbare Docks sofort setzen, versteckte
        beim naechsten Sichtbarwerden via visibilityChanged.
        """
        for dock in self._floating_tool_docks():
            name = dock.objectName()
            if name:
                rect = self._read_float_rect(settings, name)
                if rect is not None:
                    self._pending_float_geom[name] = rect
        self._connect_float_geom_handlers()
        for dock in self._floating_tool_docks():
            name = dock.objectName()
            if dock.isVisible() and name in self._pending_float_geom:
                self._apply_float_rect(dock, self._pending_float_geom.pop(name))

    def _connect_float_geom_handlers(self):
        """Verbindet visibilityChanged jedes Tool-Docks — einmalig."""
        if self._float_geom_connected:
            return
        self._float_geom_connected = True
        for dock in self._floating_tool_docks():
            dock.visibilityChanged.connect(
                lambda visible, d=dock: self._on_float_dock_visible(d, visible))

    def _on_float_dock_visible(self, dock, visible):
        """Merkt die Floating-Geometrie beim Verstecken vor und setzt sie beim
        naechsten Sichtbarwerden wieder (#121).

        Vorgemerkt wird nur, wenn das Dock selbst ein schwebendes Fenster ist.
        Beim Andocken/Abdocken feuert das Verstecken, solange das Dock noch
        angedockt ist (isFloating() False); ein angedockter Tab, der nach
        hinten rutscht, ist ebenfalls nicht schwebend. Minimieren des
        Hauptfensters loest kein visibilityChanged aus.
        """
        name = dock.objectName()
        if not visible:
            if name and dock.isFloating():
                self._pending_float_geom[name] = dock.geometry()
            return
        rect = self._pending_float_geom.pop(name, None)
        if rect is not None:
            self._apply_float_rect(dock, rect)

    @staticmethod
    def _apply_float_rect(dock, rect):
        """Setzt eine Floating-Geometrie per setGeometry().

        Bewusst nicht restoreGeometry(): das schiebt ein Fenster mit Titel-
        leiste am oberen Bildschirmrand nach unten (gemessen bis ~30 px).
        Schwebt das Dock schon, SOFORT setzen — wer direkt danach selbst
        positioniert (Zentrieren, Fullsize, Dual View), behaelt so das letzte
        Wort. Sonst einen Tick spaeter (Lazy-Docks schalten setFloating(True)
        erst deferred); ist es dann angedockt, nichts anfassen."""
        if dock.isFloating():
            dock.setGeometry(rect)
        else:
            QTimer.singleShot(
                0, lambda: dock.isFloating() and dock.setGeometry(rect))

    def _save_layout(self):
        """Speichert Layout in die INI (automatisch bei Programmende)."""
        self._settings.setValue("geometry", self.saveGeometry())
        self._settings.setValue("windowState", self.saveState(_LAYOUT_VERSION))
        # Uniform: vordersten Tab jeder Gruppe merken (restoreState vergisst ihn)
        self._settings.setValue("raisedTabs", self._raised_tab_docknames())
        # Zoom-Einstellungen
        self._settings.setValue("sequences/zoom_pct",
                                self.sequences_widget._zoom_pct)
        lyrics_zoom_pct = int(round(
            self.lyrics_widget._current_font_size
            / self.lyrics_widget._base_font_size * 100))
        self._settings.setValue("lyrics/zoom_pct", lyrics_zoom_pct)
        self._settings.setValue("lyrics/auto_size",
                                self.lyrics_widget._auto_size_enabled)
        self._settings.setValue("lyrics/auto_width",
                                self.lyrics_widget._auto_width_enabled)
        if self.notes_widget:
            self._settings.setValue("notes/zoom_pct",
                                    self.notes_widget._zoom_pct)
            self._settings.setValue("notes/first_note_factor",
                                    self.notes_widget._first_note_factor)
        self._save_float_geoms(self._settings)
        self._settings.sync()
        status = self._settings.status()
        if status != QSettings.NoError:
            print(f"[Layout] FEHLER beim Speichern: Status={status}, "
                  f"Pfad={self._settings.fileName()}")
        else:
            print(f"[Layout] In INI gespeichert: {self._settings.fileName()}")

    def _save_layout_to_file(self):
        """Speichert Layout als INI-Datei (mit frei waehlbarem Namen)."""
        start_dir = self.skin_mgr.skins_dir
        filepath, _ = QFileDialog.getSaveFileName(
            self, _t("dialog_layout_save"), start_dir,
            _t("filter_layout_files")
        )
        if not filepath:
            return
        if not filepath.endswith(".ini"):
            filepath += ".ini"
        s = QSettings(filepath, QSettings.IniFormat)
        s.setValue("geometry", self.saveGeometry())
        s.setValue("windowState", self.saveState(_LAYOUT_VERSION))
        s.setValue("raisedTabs", self._raised_tab_docknames())
        self._save_float_geoms(s)
        s.sync()
        print(f"[Layout] Gespeichert: {filepath}")

    def _load_layout_from_file(self):
        """Laedt Layout aus einer Datei (Dialog startet im Skins-Ordner)."""
        start_dir = self.skin_mgr.skins_dir
        filepath, _ = QFileDialog.getOpenFileName(
            self, _t("dialog_layout_load"), start_dir,
            _t("filter_layout_load")
        )
        if not filepath:
            return
        self._apply_layout_file(filepath)

    def _apply_layout_file(self, path: str) -> bool:
        """Wendet eine layout.ini Datei an.

        WICHTIG: Ruft _reapply_dock_features() nach restoreState() auf.
        """
        if not os.path.isfile(path):
            print(f"[Layout] Datei nicht gefunden: {path}")
            return False
        s = QSettings(path, QSettings.IniFormat)
        geometry = s.value("geometry")
        state = s.value("windowState")
        # #121: Vorgemerkte Floating-Positionen verwerfen — VOR restoreState
        # (sonst setzt ein dabei eingeblendetes Dock seine alte Position) und
        # DANACH (restoreState versteckt schwebende Docks -> visibilityChanged
        # merkt deren aktuelle Position neu vor). Massgeblich ist die Datei.
        self._pending_float_geom.clear()
        if geometry is not None:
            self.restoreGeometry(geometry)
        if state is not None:
            if not self.restoreState(state, _LAYOUT_VERSION):
                print(f"[Layout] Version stimmt nicht, State ignoriert: {path}")
                return False
        self._pending_float_geom.clear()
        print(f"[Layout] Geladen: {path}")
        self._reapply_dock_features()
        self._restore_float_geoms(s)
        # Uniform: aktiven Tab je Gruppe aus der Layout-Datei wiederherstellen
        self._restore_raised_tabs(s.value("raisedTabs", []) or [])
        return True

    # ---- INI-Defaults ----

    def _write_ini_defaults(self):
        """Schreibt Default-Werte in die INI, wenn sie noch nicht existieren."""
        # [shortcuts]-Sektion entfernen — seit P37 ins Rules-System migriert,
        # wird nicht mehr gelesen. Bereinigung laeuft einmalig pro Installation.
        self._settings.beginGroup("shortcuts")
        obsolete_keys = self._settings.childKeys()
        self._settings.endGroup()
        if obsolete_keys:
            self._settings.remove("shortcuts")

        # BL-074: audio/output_device → audio/primary_device (einmalige Migration)
        old_dev = self._settings.value("audio/output_device")
        if old_dev is not None and self._settings.value("audio/primary_device") is None:
            self._settings.setValue("audio/primary_device", old_dev)
        if old_dev is not None:
            self._settings.remove("audio/output_device")

        defaults = {
            "player/timer_warn1": "240",
            "player/timer_warn2": "300",
            "loop/crossfade_ms": "46",
            "debug/performance_logging": "false",
            "audio/min_volume": "0.0",
            # Anti-Ruckler-Schalter (siehe docs/anti_ruckler_backlog.md, AR-009/010).
            # Default an — bei vermutetem Schaden via INI deaktivierbar ohne Neuversion.
            "audio/mmcss_priority": "true",
            "audio/log_underflows": "true",
            # AR-008: WASAPI Exclusive Mode (Default off — User-Opt-in via Checkbox)
            "audio/wasapi_exclusive": "false",
            # BL-074: Sekundaerkanal fuer Audition
            "audio/secondary_device": "",   # leer = System-Standard
            "audio/secondary_volume": "80",
            # BL-119: Feedback-Dialog nach Songende (true/false)
            "feedback/enabled": "false",
            # intern#96: Einfuegeposition neuer Notizen (top/bottom)
            "notes/insert_position": "top",
            # intern#127: Heads/Sides invertieren. Art leer = noch nicht gewaehlt
            # (der Spiegel-Button fuehrt dann zuerst in die Einstellungen).
            "lyrics/dynamic_invert_enabled": "false",
            "lyrics/dynamic_invert_mode": "",
            # intern#115: Timing-Parameter (Sekunden, negativ = frueher)
            "lyrics/text_jump_offset": "-4",
            "lyrics/dynamic_swap_offset": "-4",
            # intern#76: Leseposition (% von oben) und Lesebalken
            "lyrics/reading_position_pct": "30",
            "lyrics/reading_band_enabled": "true",
            "lyrics/reading_band_height": "20",
            "lyrics/reading_band_opacity": "30",
        }
        for key, value in defaults.items():
            if self._settings.value(key) is None:
                self._settings.setValue(key, value)
        self._settings.sync()

    # ---- Einstellungen-Dialog (BL-129) ----

    def _show_settings_dialog(self, focus_key=None):
        dlg = SettingsDialog(
            self,
            self._settings,
            skin_mgr=self.skin_mgr,
            on_apply=self._on_settings_applied,
            program_picker_cb=self._settings_pick_programs,
            program_label_cb=self._program_codes_label,
            focus_key=focus_key,
        )
        dlg.exec()

    def _on_settings_applied(self, changed_keys: list):
        """Live-Apply soweit moeglich nach Einstellungs-Aenderungen."""
        for key in changed_keys:
            val = str(self._settings.value(key, ""))

            if key == "display/skin":
                self._apply_skin(val)

            elif key == "audio/primary_device":
                try:
                    dev = int(val) if val else None
                    self.engine.set_output_device(dev)
                    combo_idx = self._audio_device_combo.findData(dev)
                    if combo_idx >= 0:
                        self._audio_device_combo.blockSignals(True)
                        self._audio_device_combo.setCurrentIndex(combo_idx)
                        self._audio_device_combo.blockSignals(False)
                except Exception:
                    pass

            elif key == "audio/min_volume":
                try:
                    self.engine.set_min_volume(float(val))
                except Exception:
                    pass

            elif key == "loop/crossfade_ms":
                try:
                    self.engine.set_loop_crossfade_ms(int(val))
                except Exception:
                    pass

            elif key == "display/statusbar_player":
                enabled = val.lower() == "true"
                if hasattr(self, "_statusbar_player"):
                    self._statusbar_player.setVisible(enabled)

            elif key == "display/countdown_enabled":
                self._countdown_enabled = val.lower() not in ("false", "0", "no")
                if not self._countdown_enabled and hasattr(self, "_countdown_overlay"):
                    self._countdown_overlay.hide_overlay()

            elif key == "sequences/zoom_pct":
                try:
                    zoom = int(val)
                    if hasattr(self, "sequences_widget"):
                        self.sequences_widget.set_zoom(zoom)
                except Exception:
                    pass

            elif key == "sequences/dance_programs":
                # MS50: session-globale Tanzprogramm-Wahl aus dem Settings-Fenster.
                # INI ist bereits geschrieben -> nur uebernehmen (kein Re-Persist).
                self._session_program_ids = self._parse_program_ids(val)
                self._apply_program_setting()

            elif key == "lyrics/zoom_pct":
                try:
                    zoom = int(val)
                    if hasattr(self, "lyrics_widget"):
                        self.lyrics_widget.set_zoom(zoom)
                except Exception:
                    pass

            elif key == "lyrics/dynamic_enabled":
                if hasattr(self, "lyrics_widget"):
                    self.lyrics_widget.set_dynamic_wanted(
                        val.lower() in ("true", "1", "yes"))

            elif key == "lyrics/dynamic_mode":
                if hasattr(self, "lyrics_widget"):
                    self.lyrics_widget.set_dynamic_mode_live(val)

            elif key in ("lyrics/dynamic_invert_enabled",
                         "lyrics/dynamic_invert_mode"):
                if hasattr(self, "lyrics_widget"):
                    self.lyrics_widget.reload_invert_settings()

            elif key in ("lyrics/text_jump_offset",
                         "lyrics/dynamic_swap_offset"):
                if hasattr(self, "lyrics_widget"):
                    self.lyrics_widget.reload_timing_settings()

            elif key in ("lyrics/reading_position_pct",
                         "lyrics/reading_band_enabled",
                         "lyrics/reading_band_height",
                         "lyrics/reading_band_opacity"):
                if hasattr(self, "lyrics_widget"):
                    self.lyrics_widget.reload_reading_settings()

            elif key == "notes/zoom_pct":
                try:
                    zoom = int(val)
                    if self.notes_widget is not None:
                        self.notes_widget.set_zoom(zoom)
                except Exception:
                    pass

            elif key == "feedback/enabled":
                pass  # wird beim naechsten Songende frisch aus INI gelesen

            elif key.startswith("paths/music_dir_"):
                # PathManager liest die INI bei jedem Zugriff live — der neue Pfad
                # ist sofort aktiv (frueher stand hier ein toter Aufruf auf ein
                # nicht existentes self.path_manager.reload()). Songliste neu
                # aufbauen, damit die "Datei gefunden?"-Markierungen stimmen.
                try:
                    self.song_list.refresh()
                except Exception:
                    pass

    # ---- Shortcuts ----

    def _setup_shortcuts(self):
        """Tastatur-Shortcuts registrieren — feuern Rules-Trigger."""
        # F1-F12: QKeySequence("F1") etc. funktioniert zuverlaessig
        _KEY_TRIGGERS_STR = {
            "F1":  "key_f1",  "F2":  "key_f2",  "F3":  "key_f3",  "F4":  "key_f4",
            "F5":  "key_f5",  "F6":  "key_f6",  "F7":  "key_f7",  "F8":  "key_f8",
            "F9":  "key_f9",  "F10": "key_f10", "F11": "key_f11", "F12": "key_f12",
        }
        for key_str, trigger in _KEY_TRIGGERS_STR.items():
            shortcut = QShortcut(QKeySequence(key_str), self)
            shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)
            shortcut.setAutoRepeat(False)  # intern#101: gehaltene Taste feuert einmal
            shortcut.activated.connect(
                lambda t=trigger: self.rule_engine.fire_trigger(t))

        # F13-F24 werden im EventFilter abgefangen (QKeySequence parst diese nicht)

        # Space laeuft im eventFilter (intern#101): ein QShortcut verliert gegen
        # jedes Textfeld, die Leertaste muss bei laufender Musik aber gewinnen.

    def _is_text_input_focused(self) -> bool:
        """Prueft, ob ein Widget Fokus hat, in das gerade TEXT getippt wird.

        Nur echte Texteingabe sperrt Buchstaben-Hotkeys (C-1, #68): QLineEdit,
        QPlainTextEdit, QTextEdit, Spinboxen und EDITIERBARE Comboboxen. Tabellen,
        Listen und das read-only Lyrics-Fenster (QTextBrowser) sperren NICHT mehr —
        dort soll eine belegte Taste die Regel ausloesen statt Type-to-Search.
        Nicht belegte Tasten fallen weiterhin durch: der eventFilter feuert nur,
        wenn der Trigger registriert ist, sonst bekommt das Widget die Taste.
        """
        return is_text_input(QApplication.focusWidget())

    def _fire_hotkey(self, trigger_name: str, event) -> bool:
        """Loest den Trigger aus und schluckt die Taste.

        Gehaltene Taste (Auto-Repeat) feuert nur beim ersten Druck, die
        Wiederholungen werden trotzdem geschluckt — sonst liefen sie ins
        Fokus-Widget, z.B. als Leerzeichen ins Suchfeld (intern#101).
        """
        if not event.isAutoRepeat():
            self.rule_engine.fire_trigger(trigger_name)
        return True

    def eventFilter(self, obj, event):
        """App-weiter Event-Filter fuer Tasten-Shortcuts (dynamisch aus rule_engine).

        QShortcut wird von QTableWidget/QListWidget fuer Type-to-Search
        geschluckt. Der Event-Filter greift VOR dem Widget.

        Unterstützt alle dynamisch registrierten Tasten-Trigger (key_a, key_b, ..., key_z, key_0, etc.)

        Priorität: Text-Input/List-Search > Modal-Dialog > Tasten-Trigger
        Ausnahme Leertaste bei laufender Musik: siehe shortcut_policy (intern#101).
        """
        # Schutz gegen PySide6/shiboken-Marshalling bei app-weiten Event-Filtern:
        # Qt liefert in bestimmten Layout-Situationen ein QWidgetItem (QLayoutItem,
        # KEIN QObject) als watched. super().eventFilter() wirft darauf einen
        # TypeError -> App-Crash. Unerwartete Typen einfach nicht filtern.
        if not isinstance(obj, QObject):
            return False
        # Aufklappliste jeder Combobox breit genug fuer ihren Inhalt, egal wie
        # schmal das Control ist. Klick/Taste kommt hier VOR showPopup() an.
        if isinstance(obj, QComboBox) and opens_combo_popup(event):
            widen_combo_popup(obj)
        if event.type() == QEvent.KeyPress:
            text_focus = self._is_text_input_focused()
            modal_open = QApplication.activeModalWidget() is not None

            # #70: Escape gibt den Fokus aus einem Textfeld frei -> zurueck in den
            # Hotkey-Modus. Nur wenn wirklich ein Textfeld Fokus hat und KEIN
            # modaler Dialog offen ist (dort schliesst Esc weiter den Dialog).
            if event.key() == Qt.Key_Escape and not modal_open and text_focus:
                w = QApplication.focusWidget()
                if w is not None:
                    w.clearFocus()
                    return True

            # intern#101: Leertaste = Safety-Taste fuer Play/Pause. Bei laufender
            # Musik gewinnt sie gegen Textfelder und Dialoge — nur nicht, solange
            # jemand gerade tippt (shortcut_policy). Nur ohne Modifier, wie der
            # fruehere QShortcut("Space").
            if (event.key() == Qt.Key_Space
                    and event.modifiers() == Qt.NoModifier
                    and space_should_fire(
                        text_input_focused=text_focus,
                        # Pause zaehlt wie Laufen: Space muss auch wieder starten.
                        playing=self.engine.is_playing() or self.engine.is_paused(),
                        modal_open=modal_open,
                        typing_age_s=monotonic() - self._last_typing_ts)):
                return self._fire_hotkey("key_space", event)
            # Jede Taste, die ins Textfeld geht, zaehlt als Tippen — auch Strg+V,
            # AltGr-Zeichen und Nummernblock. Erst NACH der Leertasten-Entscheidung
            # setzen, sonst sperrt ein Space-Druck den naechsten.
            if text_focus:
                self._last_typing_ts = monotonic()

            # #68: Buchstaben-Hotkeys sollen unabhaengig von Gross-/Kleinschreibung
            # feuern — Shift zusaetzlich zu NoModifier zulassen (event.text().lower()
            # normalisiert den Trigger-Namen, sodass L wie l wirkt). Ctrl/Alt bleiben
            # ausgeschlossen, damit echte Shortcuts nicht abgefangen werden.
            if event.modifiers() in (Qt.NoModifier, Qt.ShiftModifier):
                key_code = event.key()

                # F13-F24: haben keinen event.text() — direkt ueber key_code abfangen
                if Qt.Key_F13 <= key_code <= Qt.Key_F24:
                    fn = key_code - Qt.Key_F1 + 1
                    trigger_name = f"key_f{fn}"
                    if trigger_name in self.rule_engine.registry.triggers:
                        if modal_open:
                            return False
                        return self._fire_hotkey(trigger_name, event)

                # Media-/Fn-Tasten (Volume, Media Play usw.). Bewusst OHNE
                # Auto-Repeat-Sperre: Lauter/Leiser gedrueckt halten soll die
                # Lautstaerke weiter veraendern (intern#101).
                trigger_name = self._MEDIA_KEY_TRIGGERS.get(key_code)
                if trigger_name and trigger_name in self.rule_engine.registry.triggers:
                    if modal_open:
                        return False
                    self.rule_engine.fire_trigger(trigger_name)
                    return True

                # Buchstaben/Ziffern-Trigger (z.B. "key_l", "key_p")
                key = event.text().lower()
                trigger_name = f"key_{key}"
                if trigger_name in self.rule_engine.registry.triggers:
                    if text_focus or modal_open:
                        return False
                    return self._fire_hotkey(trigger_name, event)
        return super().eventFilter(obj, event)

    def _restore_layout(self):
        """Stellt Layout aus der Haupt-INI wieder her.

        WICHTIG: Nach restoreState() MUSS _reapply_dock_features() aufgerufen
        werden, da Qt die Dock-Features (Movable/Floatable/Closable) beim
        Wiederherstellen ueberschreibt. Ohne diesen Aufruf verlieren Docks
        ihre Dock-Faehigkeiten (bekanntes Qt-Problem, 3x aufgetreten).

        Skin-Layout-Dateien werden NICHT automatisch geladen —
        nur manuell ueber Design > Layout laden.
        So bleibt das Layout beim Skin-Wechsel erhalten.

        restoreState() bekommt _LAYOUT_VERSION: Aendert sich die
        Dock-Zusammensetzung, wird die Version hochgezaehlt und
        der alte (inkompatible) State automatisch ignoriert.
        """
        geometry = self._settings.value("geometry")
        state = self._settings.value("windowState")
        if geometry is None and state is None:
            print("[Layout] Kein gespeichertes Layout, verwende Default")
            return
        # Floating-Geometrie VOR restoreState vormerken + Handler verbinden,
        # damit auch als sichtbar wiederhergestellte Tool-Fenster sie erhalten
        # (visibilityChanged feuert bereits waehrend restoreState).
        self._restore_float_geoms(self._settings)
        if geometry is not None:
            self.restoreGeometry(geometry)
        if state is not None:
            if not self.restoreState(state, _LAYOUT_VERSION):
                # Alter State mit anderer Dock-Zusammensetzung — ignorieren
                print(f"[Layout] Inkompatible Layout-Version in INI, "
                      f"verwende Default (erwartet: v{_LAYOUT_VERSION})")
                return
        print(f"[Layout] Wiederhergestellt aus: {self._settings.fileName()}")
        self._reapply_dock_features()
        # Uniform: vordersten Tab jeder Gruppe wiederherstellen (restoreState
        # stellt Gruppen/Positionen her, vergisst aber den aktiven Tab).
        # NACH show() deferrieren — vorher greift raise_() nicht.
        QTimer.singleShot(0, self._restore_raised_tabs)

    def _reapply_dock_features(self):
        """Setzt Dock-Features nach restoreState() nochmals — Qt ueberschreibt sie sonst."""
        features = (QDockWidget.DockWidgetMovable
                    | QDockWidget.DockWidgetFloatable
                    | QDockWidget.DockWidgetClosable)
        for dock in self.findChildren(QDockWidget):
            dock.setFeatures(features)
        # Evening Planner ist nicht dockbar — falls ein alter gespeicherter
        # Layout-Zustand ihn angedockt restauriert hat: Floating erzwingen
        if not self.dock_evening_planner.isFloating():
            self.dock_evening_planner.setFloating(True)
        # BL-204: gespeicherten "Frei bewegen"-Zustand erneut anwenden
        # (allowedAreas ist nicht Teil von saveState/restoreState).
        self._apply_saved_dock_free()
        # Mindesthoehen nach restoreState() erneut erzwingen
        self.player.setMinimumHeight(380)
        self.loop_widget.setMinimumHeight(190)

    # BL-204: Docks, die bewusst NICHT andockbar sind (immer frei schwebend).
    # Fuer sie ist der "Frei bewegen"-Umschalter fix an (angehakt + deaktiviert),
    # damit die Titelleisten-Menues einheitlich bleiben, ohne diese bewusst
    # nicht-dockbaren Fenster zu brechen.
    # Docks, die OHNE gespeicherte Wahl frei schweben (frueher fix nicht
    # dockbar). Per Magnet/Kontextmenue jetzt wie alle anderen umschaltbar.
    _DEFAULT_FREE_DOCKS = frozenset({
        "dock_manager", "dock_loop_finder", "dock_photo",
        "dock_evening_planner", "dock_break", "dock_rules", "dock_reports",
    })

    @staticmethod
    def _all_dock_areas():
        return (Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea
                | Qt.TopDockWidgetArea | Qt.BottomDockWidgetArea)

    def _wire_dock_context_menus(self):
        """Haengt an jede Dock-Titelleiste ein Kontextmenue 'Frei bewegen'.

        Standardkonform ueber Qt.CustomContextMenu — KEINE eigene Titelleiste.
        customContextMenuRequested feuert bei Rechtsklick auf die (native)
        Titelleiste; ein y-Guard im Handler haelt das Menue vom Dock-Inhalt fern.
        Uniform fuer ALLE Docks (auch kuenftige), da ueber findChildren gesetzt.

        Der Rueckweg (aus 'frei' wieder andocken) laeuft ueber das Magnet-Icon in
        der jeweiligen Zeile des Ansicht-Menues (siehe _add_view_menu_entry) — ein
        frei schwebendes Dock ist ein natives Fenster mit Windows-Leiste, dort
        greift Qt's Titelleisten-Rechtsklick nicht.
        """
        for dock in self.findChildren(QDockWidget):
            dock.setContextMenuPolicy(Qt.CustomContextMenu)
            dock.customContextMenuRequested.connect(
                lambda pos, d=dock: self._on_dock_context_menu(d, pos))

    def _on_dock_context_menu(self, dock, pos):
        """Zeigt bei Rechtsklick auf die Dock-Titelleiste das 'Frei bewegen'-Menue."""
        # y-Guard: nur oberhalb des Inhalts-Widgets (= Titelleiste/Rahmen),
        # damit der Rechtsklick im Inhalt weiterhin dessen eigenes Menue erhaelt.
        content = dock.widget()
        if content is not None and pos.y() > content.geometry().top():
            return
        from PySide6.QtWidgets import QMenu
        menu = QMenu(dock)
        act = menu.addAction(_t("dock_ctx_free_move"))
        act.setCheckable(True)
        act.setChecked(dock.allowedAreas() == Qt.NoDockWidgetArea)
        act.toggled.connect(lambda free, d=dock: self._set_dock_free(d, free))
        menu.exec(dock.mapToGlobal(pos))

    def _set_dock_free(self, dock, free):
        """Schaltet einen Dock zwischen 'frei schwebend' und 'andockbar' um.

        free=True : kein Andocken (NoDockWidgetArea), sofort schwebend.
        free=False: alle vier Andockbereiche wieder erlaubt UND zurueck angedockt
                    (setFloating(False)) — sonst bliebe es eine Einbahnstrasse.
        Zustand pro Dock in der INI gemerkt und Layout gesichert.
        """
        if free:
            dock.setAllowedAreas(Qt.NoDockWidgetArea)
            if not dock.isFloating():
                dock.setFloating(True)
        else:
            dock.setAllowedAreas(self._all_dock_areas())
            if dock.isFloating():
                dock.setFloating(False)
        name = dock.objectName()
        if name:
            self._settings.setValue(f"dockfree/{name}", free)
        self._refresh_view_magnet(dock)
        # Position/Floating gleich mitsichern (nicht erst beim 60s-Autosave).
        if hasattr(self, "_layout_save_timer"):
            self._save_layout()

    def _apply_saved_dock_free(self):
        """Wendet den gespeicherten 'Frei bewegen'-Zustand auf alle Docks an.
        Ohne gespeicherte Wahl gilt fuer _DEFAULT_FREE_DOCKS 'frei', sonst
        'andockbar'."""
        for dock in self.findChildren(QDockWidget):
            name = dock.objectName()
            if not name:
                continue
            free = self._settings.value(
                f"dockfree/{name}", name in self._DEFAULT_FREE_DOCKS, type=bool)
            dock.setAllowedAreas(
                Qt.NoDockWidgetArea if free else self._all_dock_areas())
            self._refresh_view_magnet(dock)

    # ---- BL-204: Andock-Umschalter (Magnet) je Zeile im Ansicht-Menue ----

    def _add_view_menu_entry(self, dock, text):
        """Fuegt dem Ansicht-Menue eine Zeile fuer einen Dock hinzu: links die
        (unveraenderte) Sichtbarkeits-Umschaltung, rechtsbuendig ein Magnet-Icon
        zum Umschalten angedockt <-> frei. Der Magnet zeigt den Snap-Zustand:
        angedockt = kraeftige Textfarbe, frei = dezent.

        Die Zeilen werden alphabetisch nach dem (uebersetzten) Text einsortiert,
        egal wann ein Dock angelegt wird (intern#117)."""
        from PySide6.QtWidgets import (
            QWidget, QHBoxLayout, QCheckBox, QToolButton, QWidgetAction)
        from PySide6.QtCore import QSize, QCollator, QLocale
        row = QWidget(self._view_menu)
        lay = QHBoxLayout(row)
        lay.setContentsMargins(8, 2, 8, 2)
        lay.setSpacing(14)
        # Sichtbarkeit: dieselbe toggleViewAction wie bisher, nur als Checkbox
        # gespiegelt (Haekchen bleibt via _sync_dock_view_actions in Takt).
        act = dock.toggleViewAction()
        act.setText(text)
        chk = QCheckBox(text, row)
        chk.setChecked(act.isChecked())
        chk.clicked.connect(lambda checked, d=dock: d.setVisible(checked))
        act.toggled.connect(chk.setChecked)
        magnet = QToolButton(row)
        magnet.setAutoRaise(True)
        magnet.setFocusPolicy(Qt.NoFocus)
        magnet.setCursor(Qt.PointingHandCursor)
        magnet.setIconSize(QSize(16, 16))
        magnet.clicked.connect(lambda _=False, d=dock: self._toggle_dock_snap(d))
        lay.addWidget(chk)
        lay.addStretch(1)
        lay.addWidget(magnet)
        wa = QWidgetAction(self._view_menu)
        wa.setDefaultWidget(row)
        wa.setData(text)
        collator = QCollator(QLocale())
        collator.setCaseSensitivity(Qt.CaseInsensitive)
        before = next((a for a in self._view_menu.actions()
                       if collator.compare(text, a.data() or "") < 0), None)
        if before is None:
            self._view_menu.addAction(wa)
        else:
            self._view_menu.insertAction(before, wa)
        self._view_magnets[dock] = magnet
        self._refresh_view_magnet(dock)

    def _toggle_dock_snap(self, dock):
        """Magnet-Klick: angedockt -> frei, frei -> wieder angedockt."""
        free_now = dock.allowedAreas() == Qt.NoDockWidgetArea
        self._set_dock_free(dock, not free_now)

    def _refresh_view_magnet(self, dock):
        """Aktualisiert Farbe/Tooltip/Aktivierung des Magneten je nach Snap-Zustand.
        Angedockt/gesnappt -> kontrastreiche Textfarbe (haftet); frei -> dezent."""
        magnet = getattr(self, "_view_magnets", {}).get(dock)
        if magnet is None:
            return
        free = dock.allowedAreas() == Qt.NoDockWidgetArea
        # Angedockt = aktiv/"haftet" -> Theme-Akzentfarbe (auffaellig, passend zum
        # Skin). Frei = inaktiv -> dezenter, kontrastarmer Ton.
        if getattr(self, "skin_mgr", None) is not None:
            if free:
                color = self.skin_mgr.color(
                    "muted_text", self.skin_mgr.color("text_dim", "#999999"))
            else:
                color = self.skin_mgr.color(
                    "selection_bg", self.skin_mgr.color("text", "#0067c0"))
        else:
            color = "#999999" if free else "#0067c0"
        magnet.setIcon(_make_icon(_SVG_MAGNET, color))
        magnet.setToolTip(
            _t("dock_undock_tooltip") if free else _t("dock_ctx_free_move"))

    def _refresh_all_view_magnets(self):
        for dock in getattr(self, "_view_magnets", {}):
            self._refresh_view_magnet(dock)

    def _sync_dock_view_actions(self):
        """Gleicht die View-Menue-Haekchen mit der echten Dock-Sichtbarkeit ab.

        Invariante: ein sichtbares Dock hat im View-Menue ein Haekchen, ein
        verstecktes keines. Beim Start kann restoreState() die Sichtbarkeit
        setzen, ohne dass toggleViewAction() das Haekchen mitzieht (Qt-Timing
        mit hidden-Placeholder + deferrtem setFloating) -> Divergenz.

        setChecked() aktualisiert nur die Anzeige und ruft KEIN _q_toggleView
        auf (Qt verbindet den Dock an triggered(), nicht an toggled()), aendert
        also die Dock-Sichtbarkeit nicht. Generisch fuer ALLE Docks, damit die
        einheitliche Layout-Persistenz unberuehrt bleibt (keine Sonderregel)."""
        for dock in self.findChildren(QDockWidget):
            action = dock.toggleViewAction()
            visible = dock.isVisible()
            if action.isChecked() != visible:
                action.setChecked(visible)

    def _open_rules_dock(self):
        """Oeffnet das Rules-Fenster (Zahnrad-Button im Stream Deck)."""
        self.dock_rules.setFloating(True)
        self.dock_rules.setVisible(True)
        self.dock_rules.raise_()
        self.dock_rules.activateWindow()

    def _reset_layout(self):
        self._settings.remove("geometry")
        self._settings.remove("windowState")
        self._settings.remove("raisedTabs")
        # Fullsize-State zuruecksetzen
        self._pre_fullsize_state = {}
        # Alle Haupt-Docks sichtbar machen und andocken
        for dock in [self.dock_player, self.dock_loop,
                     self.dock_data, self.dock_list, self.dock_playlist,
                     self.dock_lyrics, self.dock_sequences]:
            dock.setFloating(False)
            dock.setVisible(True)
        # Schritt 1: Player als Anker (Spalte 1)
        self.addDockWidget(Qt.LeftDockWidgetArea, self.dock_player)
        # Schritt 2: Songliste rechts vom Player (Spalte 2)
        self.addDockWidget(Qt.RightDockWidgetArea, self.dock_list)
        self.splitDockWidget(self.dock_player, self.dock_list, Qt.Horizontal)
        # Schritt 3: Lyrics rechts von Songliste (Spalte 3)
        self.addDockWidget(Qt.RightDockWidgetArea, self.dock_lyrics)
        self.splitDockWidget(self.dock_list, self.dock_lyrics, Qt.Horizontal)
        # Schritt 4: Loop unter Player (Spalte 1 vertikal teilen)
        self.addDockWidget(Qt.LeftDockWidgetArea, self.dock_loop)
        self.splitDockWidget(self.dock_player, self.dock_loop, Qt.Vertical)
        # Loop Finder: floating + hidden (nicht dockbar)
        self.dock_loop_finder.setFloating(True)
        self.dock_loop_finder.hide()
        # Schritt 5: Playlist getabbt mit Songliste (Spalte 2)
        self.addDockWidget(Qt.RightDockWidgetArea, self.dock_playlist)
        self.tabifyDockWidget(self.dock_list, self.dock_playlist)
        self.dock_list.raise_()
        # Schritt 6: SongDaten + Sequenzen getabbt mit Lyrics (Spalte 3)
        self.addDockWidget(Qt.RightDockWidgetArea, self.dock_data)
        self.tabifyDockWidget(self.dock_lyrics, self.dock_data)
        self.addDockWidget(Qt.RightDockWidgetArea, self.dock_sequences)
        self.tabifyDockWidget(self.dock_data, self.dock_sequences)
        self.dock_lyrics.raise_()
        # Versteckte Fenster
        self.dock_manager.hide()
        self.dock_reports.setFloating(True)
        self.dock_reports.hide()
        self.dock_potential.setFloating(True)
        self.dock_potential.hide()
        self.dock_photo.setFloating(True)
        self.dock_photo.hide()
        self.dock_rules.setFloating(True)
        self.dock_rules.hide()
        self.dock_evening_planner.setFloating(True)
        self.dock_evening_planner.hide()
        self.resize(1100, 650)
        print("[Layout] Auf Default zurueckgesetzt")

    # ---- Skin-Wechsel ----

    def _load_skin(self):
        """Zeigt verfuegbare Skins und wechselt den aktiven Skin."""
        from PySide6.QtWidgets import QInputDialog
        skins = self.skin_mgr.list_skins()
        if not skins:
            return
        current = self.skin_mgr.current_skin
        current_idx = skins.index(current) if current in skins else 0
        skin_name, ok = QInputDialog.getItem(
            self, _t("dialog_skin_title"), _t("dialog_skin_prompt"), skins, current_idx, False
        )
        if not ok or skin_name == current:
            return
        self._apply_skin(skin_name)

    def _apply_skin(self, skin_name: str) -> bool:
        """Wendet einen Skin live an (Stylesheet + alle skin-abhaengigen Widgets).

        Gemeinsamer Pfad fuer den Menue-Wechsel (_load_skin) und den
        Einstellungsdialog (_on_settings_applied) — kein Neustart noetig.
        Gibt True zurueck, wenn der Skin geladen werden konnte.
        """
        if self.skin_mgr.load(skin_name):
            QApplication.instance().setStyleSheet(self.skin_mgr.get_stylesheet())
            self._settings.setValue("display/skin", skin_name)
            # Skin-abhaengige Widgets aktualisieren
            self.player.update_skin()
            self.playlist_manager.update_skin(self.skin_mgr)
            if self.loop_finder is not None:
                self.loop_finder._section_bar.update_colors()
                self.loop_finder._waveform.set_colors(self.skin_mgr)
            # Lyrics neu sanitisieren (Theme-abhaengige Kontrastanpassung)
            if self._current_song:
                if self._lyric_variant_filename:
                    self.lyrics_widget.load_by_filename(self._lyric_variant_filename)
                else:
                    self.lyrics_widget.load_song(self._current_song)
            # Notizen-Widget (lazy — ggf. noch nicht erstellt)
            if self.notes_widget:
                self.notes_widget.apply_skin(self.skin_mgr)
            if self.evening_planner is not None:
                self.evening_planner.apply_skin(self.skin_mgr)
            if getattr(self, "pilot_square_widget", None) is not None:
                self.pilot_square_widget.apply_skin(self.skin_mgr)
            # Break-Pausen-Uhr (Dock + ggf. Overlay)
            self.break_widget.set_skin(self.skin_mgr)
            # Stream Deck: Icons mit neuen Theme-Farben neu einfaerben
            if hasattr(self, 'stream_deck_widget'):
                self.stream_deck_widget.apply_skin(self.skin_mgr)
            # Jump-Markers-Widget: Button-Farben neu setzen (BL-185)
            if hasattr(self, 'jump_markers_widget'):
                self.jump_markers_widget.apply_skin(self.skin_mgr)
            # To-Call-Widget: Kachel-/Button-Farben neu setzen (BL-199)
            if hasattr(self, 'to_call_widget'):
                self.to_call_widget.apply_skin(self.skin_mgr)
            # Statusleisten-Player: Skin-Referenz erneuern und neu zeichnen
            self._sb_player_bar._skin_mgr = self.skin_mgr
            self._sb_player_bar.update()
            # Tutorial-Overlay mit neuen Farben neu zeichnen
            self.tutorial_engine.refresh_overlay()
            # BL-204: Magnet-Icons im Ansicht-Menue neu einfaerben (Snap-Zustand)
            self._refresh_all_view_magnets()
            print(f"[Skin] Gewechselt auf '{skin_name}'")
            return True
        return False

    # ---- Update / Close ----

    def _update_all(self):
        # Audio-Buffer-Diagnostik alle 5s ausgeben (Konsole)
        import time as _t_diag
        # AR-F: Hauptthread-Stall-Detektor — der 50ms-Timer schlaegt verspaetet,
        # wenn der UI-Thread blockiert war. Loggen wir die Stalls, koennen wir
        # sie zeitlich mit Underflow-Events korrelieren (gleiche Wallclock-Stempel).
        _now_mono = _t_diag.monotonic()
        _last_tick = getattr(self, '_last_tick_mono', 0.0)
        if _last_tick > 0 and perf.is_enabled():
            gap_ms = (_now_mono - _last_tick) * 1000.0
            # Erwartetes Intervall = 50ms. Schwelle 100ms (Aufgabe J, 2026-05-25):
            # 150ms war zu hoch — Underflows auf dem System eines Users traten teilweise
            # ohne sichtbaren Stall auf, vermutlich weil Blocks 100-150ms unter dem
            # Cutoff lagen. 100ms ist sicher ueber dem normalen Scheduling-Jitter
            # (~80-100ms) und faengt die Callback-blockierenden Blocks zuverlaessig.
            # Nur loggen wenn ein Song laeuft — sonst sind Windows-Modal-Loops
            # (Title-Bar-Drag, Resize-Drag) reine False Positives. Der Detektor
            # existiert nur zur Korrelation mit Audio-Underflows (AR-F).
            if gap_ms > 100.0 and self.engine.is_playing():
                # Letzter [Perf]-Event vor dem Stall — gibt den Verdaechtigen.
                extra = ""
                _last_label, _last_mono = perf.get_last_perf()
                if _last_label and _last_mono > 0:
                    ago_ms = (_now_mono - _last_mono) * 1000.0
                    extra = (f" (letzter [Perf]-Event vor {ago_ms:.0f}ms: "
                             f"{_last_label})")
                perf.perf_write(
                    f"[Diag] Main-Thread blockiert: {gap_ms:.0f}ms "
                    f"(erwartet 50ms){extra}"
                )
                # Sentinel-Statistik fuer Diagnose-Center (Test G)
                perf.record_stall(gap_ms)
        self._last_tick_mono = _now_mono
        if not hasattr(self, '_last_diag_print'):
            self._last_diag_print = 0.0
        now_diag = _now_mono
        if self.engine.is_playing() and (now_diag - self._last_diag_print) >= 5.0:
            self._last_diag_print = now_diag
            d = self.engine.get_audio_diag()
            buf    = d["buf_ms"]
            min10s = d["min10s"]
            xruns  = d["xruns"]
            # Startup-Artefakt: History noch leer (erste Callbacks noch nicht gefeuert)
            if d["history_len"] >= 5 and perf.is_enabled():
                # Neue xRuns seit letztem Sample erkennen → das ist der echte hoerbare Aussetzer.
                # min10s=0 ohne neuen xRun ist meist nur ein Stretcher-Flush bei Tempo/Pitch-
                # Aenderung (Pre-Roll faengt es ab, PortAudio merkt nichts) — harmlos.
                prev_xruns = getattr(self, '_last_diag_xruns', 0)
                new_xruns = xruns - prev_xruns
                self._last_diag_xruns = xruns
                if new_xruns > 0:
                    warn = f" ⚠ XRUN (+{new_xruns} echter Aussetzer)"
                elif min10s < 50:
                    warn = " △ Buffer-Dip (vermutl. Stretcher-Flush, harmlos)"
                elif min10s < 120:
                    warn = " △ niedrig"
                else:
                    warn = ""
                perf.perf_write(f"[AudioBuf] jetzt={buf:.0f}ms  min10s={min10s:.0f}ms  xRuns={xruns}{warn}")
                # AR-020 Stretcher-Stats: zeigt Fix A (passthrough) + Fix C (lock_hold) in Aktion
                stats = self.engine.get_and_reset_stretcher_stats()
                if stats and stats['hops_total'] > 0:
                    t = stats['hops_total']
                    p = stats['hops_passthrough']
                    c = stats['hops_correlation']
                    pct = (p * 100 / t) if t else 0
                    perf.perf_write(
                        f"[Diag] Stretcher-Stats: hops={t} "
                        f"passthrough={p} ({pct:.0f}%) correlation={c} "
                        f"lock_hold_ms avg={stats['lock_hold_ms_avg']:.2f} "
                        f"max={stats['lock_hold_ms_max']:.2f}"
                    )

        # Song-Ende erkennen: war playing, jetzt nicht mehr (nicht pausiert)
        is_playing = self.engine.is_playing()
        # TIC-0026: Stream-Recovery bei Audio-Device-Disconnect (z.B. USB-Soundkarte, HDMI)
        if is_playing:
            self.engine.ensure_stream_alive()
        if self._was_playing and not is_playing and not self.engine.is_paused():
            if self._beat_snap_active:
                print("[P21] Song-Ende ignoriert (Beat Snap aktiv)")
            else:
                print(f"[P21] Song-Ende erkannt! is_playing={is_playing}, paused={self.engine.is_paused()}")
                self._was_playing = False
                # intern#122: Nach Songende/Fade-Ende wie bei Stop auf Anfang
                # (bzw. Loop-In) zurueckspulen. Stream bleibt offen (TIC-0025).
                # VOR song_stopped, damit Auto-Advance danach den naechsten
                # Song laedt und nicht vom Zurueckspulen ueberholt wird.
                # Position 0 = gerade neu geladen (load() setzt playing=False):
                # nicht anfassen, sonst stuende ein Pattern-Song auf Loop-In.
                if self.engine.get_playback_position_seconds() > 0:
                    self.engine.stop()
                self._trigger_song_stopped()
        self._was_playing = is_playing

        self.player.update_display()
        self.loop_widget.update_display()

        # BL-185: Jump-Markers-Widget nur bei sichtbarem Dock aktualisieren und
        # nur, wenn sich Song, Loop-Punkte oder Dauer geaendert haben (kein
        # staendiger Neuaufbau, kein DB-Read pro Tick). Zusaetzlich gedrosselt:
        # der Check laeuft nur jeden 5. Tick (~250ms) — CLAUDE.md-Regel
        # "Periodische UI-Refreshes -> Throttling". Fuer den Nutzer nicht
        # wahrnehmbar (Loop erscheint <=0,25s spaeter im Widget).
        self._jm_tick = (getattr(self, '_jm_tick', 0) + 1) % 5
        jm = getattr(self, 'jump_markers_widget', None)
        if self._jm_tick == 0 and jm is not None and self.dock_jump_markers.isVisible():
            sid = self._current_song.id if self._current_song else None
            sig = (sid,
                   round(self.engine.loop_in_seconds or 0.0, 3),
                   round(self.engine.loop_out_seconds or 0.0, 3),
                   round(self.engine.get_original_duration() or 0.0, 3))
            if sig != getattr(self, '_jm_sig', None):
                self._jm_sig = sig
                jm.refresh()

        # Statusleisten-Player aktualisieren (BL-128)
        if self._sb_player_bar.isVisible():
            _orig = self.engine.get_original_duration()
            if _orig > 0:
                _pos = self.engine.get_position_seconds()
                # Loop-Marker nur zeigen wenn Loop tatsaechlich aktiv ist —
                # engine.loop_in_seconds enthaelt sonst den gespeicherten DB-Wert
                # aller Songs die je einen Loop hatten (immer >0, irreführend).
                if self.engine._loop_active:
                    _li_r = self.engine.loop_in_seconds  / _orig
                    _lo_r = self.engine.loop_out_seconds / _orig
                else:
                    _li_r, _lo_r = 0.0, 1.0
                # Liedstart/-ende aus DB lesen (gespeichert durch Auto-Sync BL-161)
                _ss_r = _se_r = -1.0
                _song = self._current_song
                if _song and self.db:
                    try:
                        _ms = self.lyrics_widget._sync_music_slot
                        _props = self.db.get_properties(_song.id)
                        _ss = _props.get(f"singing_start_m{_ms}")
                        _se = _props.get(f"singing_end_m{_ms}")
                        if _ss is not None and _se is not None:
                            _ss_r = float(_ss) / _orig
                            _se_r = float(_se) / _orig
                    except Exception:
                        pass
                self._sb_player_bar.update_state(
                    _pos / _orig, _li_r, _lo_r, has_song=True,
                    sing_start=_ss_r, sing_end=_se_r)
            else:
                self._sb_player_bar.update_state(0.0, 0.0, 1.0, has_song=False)

        # Lyrics Auto-Scroll (proportional zum Song-Fortschritt)
        if is_playing:
            pos = self.engine.get_position_seconds()
            dur = self.engine.get_original_duration()
            if dur > 0:
                self.lyrics_widget.update_scroll(pos, dur)

            # Play Timer fuer Rules (alle 10 Sekunden)
            import time as _t2
            now = _t2.time()
            if not hasattr(self, '_last_play_timer_fire'):
                self._last_play_timer_fire = 0
            if (now - self._last_play_timer_fire) >= 10:
                self._last_play_timer_fire = now
                self.rule_engine.fire_trigger("play_timer")

        # Start-Countdown-Overlay
        _cd_pos = self.engine.get_position_seconds() if is_playing else 0.0
        self._update_countdown(_cd_pos, is_playing)

    def _crash_context(self) -> dict:
        """Liefert Kontext-Infos fuer den Crash-Handler."""
        song = getattr(self, '_current_song', None)
        loc  = getattr(self, '_current_location', None)
        return {
            "song":     (song.title or song.filename) if song else "—",
            "location": loc.name if loc else "—",
        }

    def closeEvent(self, event):
        # Update-Timer ZUERST stoppen — verhindert dass _update_all oder
        # noch ausstehende QTimer.singleShot-Callbacks nach db.close() auf
        # die DB zugreifen (TIC-0026: Cannot operate on a closed database)
        self.timer.stop()
        # Layout speichern (vor engine.shutdown, das blockieren kann)
        self._save_layout()
        self._save_current_song()
        self.rule_engine.close()
        self.engine.shutdown()
        self.db.close()
        event.accept()


def _show_language_dialog() -> str:
    """Zeigt beim Erststart einen Sprachauswahl-Dialog.

    Returns:
        Sprachcode ('de' oder 'en').
    """
    QApplication.restoreOverrideCursor()
    QApplication.setOverrideCursor(Qt.ArrowCursor)
    dlg = QDialog()
    dlg.setWindowTitle("Callers Caddy")
    dlg.setFixedSize(420, 140)
    layout = QVBoxLayout(dlg)
    layout.setSpacing(16)

    lbl = QLabel("Please select your language:\nBitte waehlen Sie Ihre Sprache:\n言語を選択してください:")
    lbl.setAlignment(Qt.AlignCenter)
    lbl.setStyleSheet("font-size: 14px;")
    layout.addWidget(lbl)

    btn_layout = QHBoxLayout()
    btn_en = QPushButton("Start in English")
    btn_en.setMinimumHeight(36)
    btn_de = QPushButton("In Deutsch starten")
    btn_de.setMinimumHeight(36)
    btn_ja = QPushButton("日本語で開始")
    btn_ja.setMinimumHeight(36)
    btn_layout.addWidget(btn_en)
    btn_layout.addWidget(btn_de)
    btn_layout.addWidget(btn_ja)
    layout.addLayout(btn_layout)

    chosen = ["de"]  # Mutable default
    btn_en.clicked.connect(lambda: (chosen.__setitem__(0, "en"), dlg.accept()))
    btn_de.clicked.connect(lambda: (chosen.__setitem__(0, "de"), dlg.accept()))
    btn_ja.clicked.connect(lambda: (chosen.__setitem__(0, "ja"), dlg.accept()))

    dlg.exec()
    QApplication.restoreOverrideCursor()
    return chosen[0]


def _show_crash_log_notice(parent, crash_logs: list, settings):
    """Zeigt einen Hinweis-Dialog wenn neue Crash-Logs vorhanden sind.

    Merkt sich den neuesten gezeigten Log in der INI (LAST_NOTIFIED_KEY),
    damit beim naechsten Start nur neu hinzugekommene Logs gemeldet werden."""
    count = len(crash_logs)
    newest = crash_logs[0]
    settings.setValue(_crash_handler.LAST_NOTIFIED_KEY, os.path.basename(newest))
    settings.sync()
    msg = QMessageBox(parent)
    msg.setWindowTitle(_t("crash_notice_title"))
    msg.setIcon(QMessageBox.Information)
    msg.setText(_t("crash_notice_text", count=count))
    msg.setInformativeText(os.path.basename(newest))
    btn_show = msg.addButton(_t("crash_notice_btn_show"), QMessageBox.ActionRole)
    btn_folder = msg.addButton(_t("crash_notice_btn_folder"), QMessageBox.ActionRole)
    msg.addButton(_t("crash_notice_btn_dismiss"), QMessageBox.RejectRole)
    msg.exec()
    clicked = msg.clickedButton()
    if clicked == btn_show:
        try:
            os.startfile(newest)
        except Exception:
            QMessageBox.information(
                parent, _t("crash_notice_title"),
                _t("crash_notice_path", path=newest)
            )
    elif clicked == btn_folder:
        folder = os.path.dirname(newest)
        try:
            # Datei im Explorer markiert oeffnen; Fallback: nur den Ordner
            os.startfile(folder)
        except Exception:
            QMessageBox.information(
                parent, _t("crash_notice_title"),
                _t("crash_notice_path", path=folder)
            )


def main():
    # Startup-Timer immer aktiv (perf_log erst nach INI-Lesung steuerbar)
    _t_start = _startup_time.perf_counter()

    # Herkunfts-Nachweis (BL-201): macht sofort sichtbar, AUS WELCHEM Verzeichnis
    # der laufende Code stammt — so faellt geladener Alt-/Fremd-Code sofort auf.
    print(f"[Main] Callers Caddy v{__version__} — Code aus: "
          f"{os.path.dirname(os.path.abspath(__file__))}")

    # Windows: Eigene AppUserModelID setzen, damit die Taskleiste
    # das App-Icon statt des Python-Icons anzeigt
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "sinnstiften.callerscaddy")
    except Exception:
        pass

    # Crash-Handler so frueh wie moeglich aktivieren (app_dir noch nicht bekannt,
    # wird nach der frozen-Pruefung nochmal korrekt gesetzt)
    import crash_handler as _crash_handler

    app = QApplication(sys.argv)

    # --- Audio-Backend-Selbsttest -----------------------------------------
    # sounddevice/soundfile laden native DLLs (PortAudio/libsndfile). Schlaegt
    # das fehl (Virenscanner blockiert die DLL, ZIP nicht entsperrt), starten
    # wir NICHT mit einem rohen Python-Traceback durch, sondern zeigen einen
    # verstaendlichen Dialog mit Loesungsweg. Der Import selbst ist in
    # audio_engine.py abgesichert; hier kommt der erste Zeitpunkt, an dem ein
    # Qt-Dialog ueberhaupt moeglich ist.
    import audio_engine as _ae_check
    if not _ae_check.audio_backend_available():
        # Diagnose-Log schreiben (DLL vorhanden? Groesse? lesbar? volle
        # Fehlerkette) — das trennt "Quarantaene" von "blockiert", was der
        # Windows-Fehler 0x7e selbst nicht verraet. Liegt in logs/crashes/.
        try:
            _crash_handler.write_report(
                "Audio-Backend (PortAudio/libsndfile) nicht ladbar",
                _ae_check.collect_audio_diagnostics(),
            )
        except Exception:
            pass
        from PySide6.QtWidgets import QMessageBox
        _audio_title, _audio_msg = _ae_check.format_audio_import_error()
        QMessageBox.critical(None, _audio_title, _audio_msg)
        sys.exit(1)

    # --- Single Instance Lock ---
    # Wird jetzt bereits am MODUL-ANFANG geholt (_acquire_single_instance_lock,
    # gehalten in _LOCK_FILE) — VOR den schweren Imports. Dadurch bricht ein
    # ungeduldiger zweiter Doppelklick in ~0.2s ab statt nach ~2.8s. Hier ist
    # daher nichts mehr zu tun: kaeme main() ueberhaupt so weit, haelt diese
    # Instanz den Lock bereits.

    # Wait-Cursor waehrend des Starts
    app.setOverrideCursor(Qt.WaitCursor)

    _t_app = _startup_time.perf_counter()

    # Skin laden und global anwenden
    # Skin-Name aus INI lesen (Default: "default")
    # PyInstaller: neben EXE, Dev: CWD = 2_Test/
    if getattr(sys, 'frozen', False):
        app_dir = os.path.dirname(sys.executable)
    else:
        app_dir = os.getcwd()

    # Crash-Handler initialisieren (app_dir jetzt bekannt)
    _crash_logger = _crash_handler.setup(app_dir)

    ini_path = os.path.join(app_dir, "callers_caddy.ini")
    settings = QSettings(ini_path, QSettings.IniFormat)
    skin_name = str(settings.value("display/skin", "default"))

    # Sprache aus INI laden — beim Erststart Auswahl-Dialog anzeigen
    lang = settings.value("display/language")
    if lang is None:
        lang = _show_language_dialog()
        settings.setValue("display/language", lang)
        settings.sync()
    else:
        lang = str(lang)
    set_language(lang)

    # Performance-Logging aus INI (Default: aus)
    _perf_enabled = str(settings.value("debug/performance_logging", "false")).lower() == "true"
    # L2 (AR-015): gespeichertes Device fuer Perf-Header (beide Latenzen anzeigen)
    try:
        _saved_dev = settings.value("audio/primary_device", "")
        _perf_dev_idx = int(_saved_dev) if _saved_dev else None
    except (ValueError, TypeError):
        _perf_dev_idx = None
    perf.configure(_perf_enabled, device_index=_perf_dev_idx, version=__version__)
    if _perf_enabled:
        perf.open_perf_file()

    # Anti-Ruckler-Schalter (siehe docs/anti_ruckler_backlog.md)
    # Default: an — wer ein Problem damit hat, kann via INI deaktivieren.
    import audio_engine as _ae
    _ae.MMCSS_ENABLED = str(
        settings.value("audio/mmcss_priority", "true")).lower() == "true"
    _ae.LOG_UNDERFLOWS = str(
        settings.value("audio/log_underflows", "true")).lower() == "true"
    # [Diag]-Zeilen der Audio-Engine ins gestempelte perf_log umleiten
    if perf.is_enabled():
        _ae.set_diag_logger(perf.perf_write)

    # Ab hier greifen perf_log/perf_split
    perf_log("QApplication + Lock", _t_start, _t_app)

    # --- Bisher blinde Phasen VOR main() (die "gefuehlte" Wartezeit) ---------
    # _T_MODULE_TOP_* wurde ganz oben erfasst, noch vor den schweren Imports.
    # Import-Phase (Modul-Top -> main-Start): perf_counter-Delta, exakt.
    # Bootloader+Init (Prozess-Erstellung -> Modul-Top): Wallclock, da die
    # Prozess-Erstellungszeit als Unix-Epoch vorliegt.
    if perf.is_enabled():
        _import_ms = (_t_start - _T_MODULE_TOP_PERF) * 1000.0
        if _T_PROCESS_CREATE_EPOCH is not None:
            _boot_ms = (_T_MODULE_TOP_WALL - _T_PROCESS_CREATE_EPOCH) * 1000.0
            perf.perf_write(f"[Perf] Bootloader + Python-Init (Prozessstart -> Modul-Top): {_boot_ms:.0f}ms")
        perf.perf_write(f"[Perf] Import-Phase (Modul-Top -> main): {_import_ms:.0f}ms")

    skin_mgr = SkinManager(app_dir)
    if skin_mgr.load(skin_name):
        app.setStyleSheet(skin_mgr.get_stylesheet())
        print(f"[Main] Skin '{skin_mgr.current_skin}' geladen")
    elif skin_name != "default" and skin_mgr.load("default"):
        app.setStyleSheet(skin_mgr.get_stylesheet())
        print(f"[Main] Skin '{skin_name}' nicht gefunden, "
              f"Fallback auf 'default'")
    else:
        print("[Main] Kein Skin gefunden, verwende System-Standard")

    _t_skin = perf_split("Skin + Sprache", _t_app)

    window = P29MainWindow(skin_mgr=skin_mgr)

    _t_window = perf_split("MainWindow.__init__", _t_skin)

    window.show()

    # Sequenzen erst NACH dem Sichtbarwerden laden (Perf): der erste Cover-Compute
    # (kalt ~275ms, nur beim ersten Start nach Datenaenderung dank persistentem
    # Cache) blockiert so nicht mehr das Erscheinen des Fensters. singleShot(0)
    # feuert in der ersten Event-Loop-Runde, direkt nach dem ersten Paint.
    QTimer.singleShot(0, window._init_sequences)

    # Crash-Handler: Kontext-Provider registrieren (jetzt kennt er das Window)
    _crash_logger.set_context_provider(window._crash_context)

    # Wait-Cursor zuruecksetzen
    app.restoreOverrideCursor()

    perf_split("window.show()", _t_window)
    perf_log("GESAMT bis show (nur main-Rumpf)", _t_start)

    # Echte gefuehlte Wartezeit: Prozessstart -> Fenster sichtbar. Schliesst
    # Bootloader + Import-Phase mit ein (das, was der Nutzer als "ewig" erlebt).
    if perf.is_enabled() and _T_PROCESS_CREATE_EPOCH is not None:
        _visible_total_ms = (_startup_time.time() - _T_PROCESS_CREATE_EPOCH) * 1000.0
        perf.perf_write(f"[Perf] === GESAMT ab Prozessstart bis SICHTBAR: {_visible_total_ms:.0f}ms ===")

    # Neue Crash-Logs seit dem letzten Hinweis pruefen und Hinweis anzeigen
    crash_logs = _crash_handler.CrashLogger.find_crash_logs(
        app_dir, newer_than=str(settings.value(_crash_handler.LAST_NOTIFIED_KEY, "") or ""))
    if crash_logs:
        QTimer.singleShot(
            800, lambda: _show_crash_log_notice(window, crash_logs, settings))

    # Song-Katalog vorladen (~90 ms, auf dem i5 mehr): der erste Import soll
    # nicht auf dem Main-Thread parsen (intern#126).
    QTimer.singleShot(1000, lambda: threading.Thread(
        target=song_catalog.get_catalog, args=(window.paths.app_dir,),
        daemon=True, name="SongCatalogPreload").start())

    # Update-Pruefung im Hintergrund (scheitert lautlos bei Offline/Fehler).
    # Verzoegert, damit sie nicht mit dem Start konkurriert.
    try:
        import update_check
        window._update_checker = update_check.UpdateChecker(window, __version__)
        QTimer.singleShot(1500, window._update_checker.start)
    except Exception:
        pass

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
