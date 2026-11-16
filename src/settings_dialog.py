"""
BL-129: Einstellungen-Fenster — generische INI-Ansicht und -Bearbeitung.

Liest die callers_caddy.ini ueber QSettings aus, rendert Tabs pro Sektion,
und schreibt Aenderungen zurueck. Unbekannte Keys fallen automatisch auf
generische Widgets zurueck — neue INI-Einstellungen erscheinen so ohne
Codeaenderungen.
"""

import os

try:
    import sounddevice as _sd
    _SD_AVAILABLE = True
except Exception:
    # NICHT nur ImportError: sounddevice wirft beim Laden der PortAudio-DLL einen
    # OSError (z.B. 0x7e auf Windows-on-ARM, TIC-0028). Faengt man nur ImportError,
    # reisst dieser OSError den App-Start hier im Import von settings_dialog ab,
    # bevor der Audio-Selbsttest aus main() den verstaendlichen Dialog zeigen kann.
    _sd = None
    _SD_AVAILABLE = False

from PySide6.QtCore import Qt, QDate, QTimer, QEvent, QPoint
from PySide6.QtWidgets import (
    QDialog, QWidget, QScrollArea, QFormLayout, QGroupBox,
    QLabel, QLineEdit, QCheckBox, QSpinBox, QDoubleSpinBox,
    QAbstractSpinBox, QDateEdit, QComboBox, QSlider,
    QPushButton, QHBoxLayout, QVBoxLayout,
    QDialogButtonBox, QMessageBox, QFileDialog, QSizePolicy,
    QFrame,
)
from PySide6.QtCore import QSettings

import program_selection
from i18n import _t


# ---------------------------------------------------------------------------
# Sektionen, die niemals angezeigt werden (Qt-Zustandsdaten, interne Flags)
# ---------------------------------------------------------------------------
_EXCLUDED_SECTIONS = {
    "General",
    "Tutorials",
    "custom-filter",
    "shortcuts",   # seit P37 ins Rules-System migriert, wird nicht mehr gelesen
    "crash",       # interner Merker: zuletzt gemeldetes Fehlerprotokoll
}

# Jede Sektion deren Name dieses Suffix hat wird ebenfalls ausgeblendet
_EXCLUDED_SUFFIX = "_dock"

# Keys, die in bestimmten Sektionen nicht angezeigt werden (intern)
_EXCLUDED_KEYS: dict[str, set] = {
    "sequences": {
        "mdb_path", "json_import_dir", "mapping_export_dir", "csds_import_dir",
    },
    "display": {"date_format"},  # eigener Toggle im Design-Menu
    "audio": set(),  # primary/secondary_device werden als device_combo angezeigt
}

# Keys in der rules-Sektion: nur sys_*_active-Muster anzeigen
_RULES_KEY_PATTERN = "sys_"

# ---------------------------------------------------------------------------
# Neustart-pflichtige Keys
# ---------------------------------------------------------------------------
_RESTART_KEYS = {
    # display/skin NICHT hier: wird via _on_settings_applied() live angewendet.
    "display/language",
    "debug/performance_logging",
    "audio/mmcss_priority",
    "audio/wasapi_exclusive",
    "audio/log_underflows",
    # Beide werden nur beim Aufbau des jeweiligen Widgets gelesen:
    "sort/default_mode",
    "sequences/only_program_default",
    "sequences/show_hidden_on_start",
}

# ---------------------------------------------------------------------------
# SETTINGS_META — Metadaten fuer bekannte Keys
# ---------------------------------------------------------------------------
# Struktur eines Eintrags:
#   "sektion/key": {
#       "label":        DE-Label (wird als Fallback benutzt wenn kein i18n-Key)
#       "label_key":    optionaler i18n-Key
#       "tooltip":      optionaler Tooltip-Text (DE)
#       "widget":       "checkbox" | "spinbox" | "doublespinbox" | "lineedit"
#                       | "combobox" | "dateedit" | "path"  (Override)
#       "choices":      Liste fuer ComboBox [(value, display), ...]
#       "min":          Minimalwert fuer SpinBox/DoubleSpinBox
#       "max":          Maximalwert
#       "step":         Schrittweite
#       "suffix":       Einheit-String fuer SpinBox (z.B. " ms")
#       "requires_restart": bool
#       "default":      Anzeigewert, solange der Key nicht in der INI steht
#   }
#
# Der Standardwert einer Einstellung steht an bis zu vier Stellen, die
# zusammenpassen muessen (Fehlerkette intern#189, #195, #198, #199):
#   1. die Lesestelle im Code: settings.value("sektion/key", <Standard>)
#   2. P29MainWindow._write_ini_defaults() in main.py (schreibt beim Start)
#      Fuer umgestellte Module (intern#144) gilt statt 1 und 2 das Verzeichnis
#      caddy/settings/ini_keys.py: Lesestelle ini_keys.get(..), Saat daraus.
#   3. installer/callers_caddy_default.ini (mitgelieferte INI)
#   4. "default" hier in SETTINGS_META (nur die Anzeige im Dialog)
# Abgleich: tests/settings/test_settings_defaults.py (1 gegen 4) und
# tests/settings/test_settings_reachable.py (jeder Key braucht 2 oder 3).
SETTINGS_META: dict[str, dict] = {
    # --- display ---
    "display/skin": {
        "label": "Skin / Theme",
        "widget": "combobox",
        "choices": [],          # wird zur Laufzeit befuellt
        "default": "default",
        "requires_restart": True,
    },
    "display/language": {
        "label": "Sprache / Language",
        "widget": "combobox",
        "choices": [("de", "Deutsch"), ("en", "English (US)"), ("ja", "日本語")],
        "requires_restart": True,
    },
    "display/statusbar_player": {
        "label": "Statusleisten-Player anzeigen",
        "widget": "checkbox",
        "default": True,
    },
    "display/countdown_enabled": {
        "label": "Start-Countdown anzeigen",
        "widget": "checkbox",
        "default": True,
        "tooltip": "Zählt vor dem Liedstart auf dem Beat herunter (benötigt BPM und gespeicherte Startzeit).",
    },
    # --- paths ---
    "paths/music_dir_1": {"label": "Musikordner 1",  "widget": "path"},
    "paths/music_dir_2": {"label": "Musikordner 2",  "widget": "path"},
    "paths/music_dir_3": {"label": "Musikordner 3",  "widget": "path"},
    "paths/music_dir_4": {"label": "Musikordner 4",  "widget": "path"},
    "paths/last_import_dir": {
        "label": "Letzter Import-Ordner",
        "widget": "path",
        "tooltip": "Wird beim Importieren als Startordner verwendet.",
    },
    "paths/lyrics_dir": {"label": "Lyrics-Ordner", "widget": "path"},
    "paths/playlist_dir": {
        "label": "Playlist-Ordner",
        "widget": "path",
        "tooltip": "Ordner, in dem Playlists gespeichert und geladen werden.",
    },
    # --- audio ---
    "audio/primary_device": {
        "label": "Primärer Ausgang",
        "widget": "device_combo",
        "tooltip": "Hauptausgang für Tänzer / PA-Anlage.",
    },
    "audio/secondary_device": {
        "label": "Sekundärer Ausgang (Audition)",
        "widget": "device_combo",
        "tooltip": "Kanal für Vorhören (Audition). Meist interner Lautsprecher oder Kopfhörer.",
    },
    "audio/secondary_volume": {
        "label": "Lautstärke Sekundärkanal",
        "widget": "spinbox",
        "min": 0, "max": 100, "step": 5, "suffix": " %",
        "tooltip": "Lautstärke beim Vorhören über den sekundären Kanal (0–100 %).",
    },
    "audio/min_volume": {
        "label": "Mindest-Lautstärke",
        "widget": "doublespinbox",
        "min": 0.0, "max": 1.0, "step": 0.05,
        "tooltip": "Live-Lautstärke kann nie unter diesen Wert sinken (0.0–1.0).",
    },
    "audio/mmcss_priority": {
        "label": "MMCSS-Priorität (Audio-Thread)",
        "widget": "checkbox",
        "default": True,
        "requires_restart": True,
        "tooltip": "Windows Multimedia Class Scheduler für Audio-Thread aktivieren. Bei Aussetzern deaktivieren.",
    },
    "audio/wasapi_exclusive": {
        "label": "WASAPI Exclusive Mode",
        "widget": "checkbox",
        "requires_restart": True,
        "tooltip": "Exklusiver Gerätezugriff — weniger Latenz, aber andere Apps verlieren Audio.",
    },
    "audio/log_underflows": {
        "label": "Audio-Underflows protokollieren",
        "widget": "checkbox",
        "default": True,
        "requires_restart": True,
    },
    # BL-137: Timer-Überzug-Sound — Datei wird in den laufenden Stream eingemischt
    "audio/alert_sound_path": {
        "label": "Hinweis-Sound (Timer-Überzug)",
        "widget": "file",
        "file_filter": "Audio (*.mp3 *.wav *.flac *.ogg *.m4a);;Alle Dateien (*.*)",
        "default": "",
        "tooltip": "Audiodatei, die beim Timer-Überzug statt des Pieps abgespielt wird. Leer = bisheriger Doppel-Piep.",
    },
    "audio/alert_volume": {
        "label": "Lautstärke Hinweis-Sound",
        "widget": "doublespinbox",
        "min": 0.0, "max": 2.0, "step": 0.05,
        "default": "1.0",
        "tooltip": "Lautstärke der Hinweis-Audiodatei (0.0 = stumm, 1.0 = Originalpegel, bis 2.0 möglich).",
    },
    # --- loop ---
    "loop/crossfade_ms": {
        "label": "Loop-Crossfade",
        "widget": "spinbox",
        "min": 0, "max": 500, "step": 1, "suffix": " ms",
        "tooltip": "Überblendzeit beim Loop-Übergang in Millisekunden.",
    },
    "loop/finder_window_mode": {
        "label": "Loop Finder: Suchfenster als",
        "widget": "combobox",
        "choices": [],          # zur Laufzeit (i18n) befuellt
        "default": "pct",
        "tooltip": ("Ob der Loop Finder die Suchfenster in Prozent der Songdauer "
                    "oder als Zeit angibt (Loop-In ab Songbeginn, Loop-Out vor "
                    "Songende). Umschalten im Loop Finder ändert diesen Wert mit."),
    },
    # --- player ---
    "player/timer_warn1": {
        "label": "Timer-Warnung 1",
        "widget": "spinbox",
        "min": 0, "max": 3600, "step": 10, "suffix": " s",
        "tooltip": "Nach X Sekunden Spieldauer färbt sich die Spieldauer-Anzeige in Warnfarbe 1.",
    },
    "player/timer_warn2": {
        "label": "Timer-Warnung 2",
        "widget": "spinbox",
        "min": 0, "max": 3600, "step": 10, "suffix": " s",
        "tooltip": "Nach X Sekunden Spieldauer färbt sich die Spieldauer-Anzeige in Warnfarbe 2.",
    },
    # --- playlist ---
    "playlist/start_date": {
        "label": "Saison-Startdatum",
        "widget": "dateedit",
        "tooltip": "Startdatum der aktuellen Saison für Statistiken.",
    },
    "playlist/fade_out_time": {
        "label": "Fade-Out-Dauer",
        "widget": "spinbox",
        "min": 0, "max": 30, "step": 1, "suffix": " s",
        "default": 3,
    },
    "playlist/patter_fill_type": {
        "label": "Patter-Füllung im Planner",
        "widget": "combobox",
        "choices": [],          # zur Laufzeit (i18n) befuellt
        "default": "infinite",
        "tooltip": ("Wie neu in den Planner aufgenommene Patter (manuell oder per "
                    "Auto-Fill) vorbelegt werden: endlos wiederholen oder auf die "
                    "Ziellänge des aktiven Tanzprogramms optimieren."),
    },
    # --- network ---
    "network/ceder_lookup_enabled": {
        "label": "Cue-Sheet-Suche auf ceder.net",
        "widget": "checkbox",
        "default": False,
        "tooltip": ("Blendet im Potenzial-Fenster den Tab „Lyrics ergänzen“ ein. "
                    "Greift auf einen fremden Server zu — nur mit Erlaubnis des "
                    "Betreibers nutzen. Geholte Cue Sheets sind für den eigenen "
                    "Gebrauch bestimmt und dürfen nicht weitergegeben werden."),
        "requires_restart": True,
    },
    # --- sort ---
    "sort/default_mode": {
        "label": "Lieblings-Sortierung",
        "widget": "combobox",
        "choices": [],          # wird zur Laufzeit befuellt (i18n)
        "default": 0,
        "tooltip": "Diese Sortierung ist beim App-Start in Songliste und Planner voreingestellt.",
        "requires_restart": True,
    },
    "sort/random_tiebreaker": {
        "label": "Gleichstand zufällig sortieren",
        "widget": "checkbox",
        "default": True,
        "tooltip": "Gleichstand-Gruppen zufällig sortieren (nur bei Qualität / Empfehlung). Gilt für Songliste, Planner und Evening Planner.",
    },
    # --- feedback ---
    "feedback/enabled": {
        "label": "Feedback-Dialog nach Songende",
        "widget": "checkbox",
        "tooltip": "Nach jedem Songende einen kurzen Bewertungs-Dialog anzeigen.",
    },
    # --- sequences ---
    "sequences/dance_programs": {
        "label": "Tanzprogramm(e)",
        "widget": "program_picker",
        "default": "",
        "tooltip": ("Session-weite Tanzprogramm-Auswahl (mehrere möglich). Steuert "
                    "den Sequenz-Filter; das oberste gewählte Programm liefert die "
                    "Ziel-Tanzdauer. Eine gewählte Lokation übernimmt ihre Programme."),
    },
    "sequences/zoom_pct": {
        "label": "Zoom",
        "widget": "spinbox",
        "min": 50, "max": 200, "step": 10, "suffix": " %",
        "default": 100,
    },
    "sequences/only_program_default": {
        "label": "\"Nur\"-Filter beim Start aktiv",
        "widget": "checkbox",
        "default": False,
        "tooltip": "Voreinstellung der \"Nur\"-Checkbox im Sequenzen-Fenster: nur Sequenzen, deren höchster Call im gewählten Programm liegt.",
        "requires_restart": True,
    },
    "sequences/show_hidden_on_start": {
        "label": "Ausgeblendete Sequenzen beim Start anzeigen",
        "widget": "checkbox",
        "default": False,
        "tooltip": ("Startet das Sequenzen-Fenster wie „Auch ausgeblendete Sequenzen anzeigen“: "
                    "Auch Sequenzen mit nicht zugeordneten Call-Texten (rot) erscheinen, die "
                    "Tanzprogramm-Wahl ist für die Liste ausgesetzt. Achtung: Darunter können Calls "
                    "aus anderen Programmen sein, und bei einer Programm-Änderung werden diese "
                    "Sequenzen nicht automatisch neu eingestuft. Ein Umschalten per Rechtsklick "
                    "gilt nur bis zum nächsten Start."),
        "requires_restart": True,
    },
    "sequences/auto_sync_program": {
        "label": "Filter automatisch auf Tanzprogramm setzen",
        "widget": "checkbox",
        "default": True,
        "tooltip": "Wenn das Tanzprogramm wechselt (Lokation oder Player), wird der Level-Filter im Sequenzen-Fenster automatisch angepasst.",
    },
    "sequences/universal_import_dir": {
        "label": "Letzter Sequenz-Import-Ordner",
        "widget": "path",
        "tooltip": "Wird beim Sequenz-Import als Startordner verwendet.",
    },
    # --- notes ---
    "notes/zoom_pct": {
        "label": "Zoom",
        "widget": "spinbox",
        "min": 50, "max": 200, "step": 10, "suffix": " %",
        "default": 100,
    },
    "notes/first_note_factor": {
        "label": "Erste-Notiz-Faktor",
        "widget": "doublespinbox",
        "min": 1.0, "max": 10.0, "step": 0.5,
        "default": 4.0,
        "tooltip": "Schriftgrössen-Faktor für die erste (oberste) offene Notiz.",
    },
    "notes/line_spacing_pct": {
        "label": "Zeilenabstand",
        "widget": "spinbox",
        "min": 100, "max": 200, "step": 10, "suffix": " %",
        "default": 100,
        "tooltip": "Abstand der Zeilen in mehrzeiligen Notizen. 100 % ist die normale Zeilenhöhe der Schrift.",
    },
    "notes/insert_position": {
        "label": "Neue Notizen einfügen",
        "widget": "combobox",
        "choices": [],          # zur Laufzeit (i18n) befuellt
        "default": "top",
        "tooltip": "Wo neue Notizen landen — auch beim Übernehmen aus Playlist und Abendplaner. „Mitte“ fügt über der obersten Trennlinie ein (ohne Trennlinie ganz unten). Der Umschalter im Notizen-Fenster ändert das nur für die laufende Sitzung.",
    },
    # --- lyrics ---
    "lyrics/zoom_pct": {
        "label": "Zoom",
        "widget": "spinbox",
        "min": 50, "max": 300, "step": 10, "suffix": " %",
        "default": 100,
    },
    "lyrics/auto_size": {
        "label": "Automatische Schriftgrösse",
        "widget": "checkbox",
        "default": True,
    },
    "lyrics/auto_width": {
        "label": "Automatische Breite",
        "widget": "checkbox",
        "default": False,
        "tooltip": ("Passt die Schriftgröße der Lyrics an die Fensterbreite an. "
                    "Schließt die automatische Schriftgröße aus – ist beides an, "
                    "gewinnt die Breite. Entspricht dem Button „Auto-Breite“ im "
                    "Lyrics-Fenster."),
    },
    "lyrics/dynamic_enabled": {
        "label": "Dynamic Lyrics aktiv",
        "widget": "checkbox",
        "default": False,
        "tooltip": "Blendet die im Sequence-View gewählte Choreografie in die "
                   "Figuren-Abschnitte ein. Lässt sich auch über den Button "
                   "im Lyric-Fenster umschalten.",
    },
    "lyrics/dynamic_mode": {
        "label": "Dynamic-Lyrics-Modus",
        "widget": "combobox",
        # choices werden zur Laufzeit i18n-uebersetzt (siehe _build_widget)
        "choices": [
            ("1", "Dieselbe Sequenz in alle 4 Figuren"),
            ("2", "Ab aktueller Sequenz durchblättern"),
        ],
        "default": "1",
        "tooltip": "Verteilung der im Sequence-View gewählten Sequenzen auf die "
                   "vier Figuren-Abschnitte, wenn Dynamic Lyrics aktiv ist.",
    },
    # intern#127: Heads/Sides in ausgewaehlten Figuren tauschen
    "lyrics/dynamic_invert_enabled": {
        "label": "Heads / Sides invertieren",
        "widget": "checkbox",
        "default": False,
        "tooltip": "Tauscht in den eingeblendeten Sequenzen Heads und Sides "
                   "(samt Couple-Nummern) in den Figuren der gewählten Art. "
                   "Wirkt nur zusammen mit Dynamic Lyrics. Entspricht dem "
                   "Spiegel-Button im Lyric-Fenster.",
    },
    "lyrics/dynamic_invert_mode": {
        "label": "Art der Invertierung",
        "widget": "combobox",
        # choices werden zur Laufzeit i18n-uebersetzt (siehe _build_widget)
        "choices": [
            ("HHSS", "HHSS – Figure 3 und 4 tauschen"),
            ("HSSH", "HSSH – Figure 2 und 3 tauschen"),
            ("HSHS", "HSHS – Figure 2 und 4 tauschen"),
        ],
        "default": "",
        "tooltip": "In welchen Figuren Heads und Sides getauscht werden.",
    },
    # intern#115: Timing-Parameter (ganze Sekunden, negativ = frueher)
    "lyrics/text_jump_offset": {
        "label": "Textsprung timen",
        "widget": "spinbox",
        "min": -10, "max": 10, "step": 1, "suffix": " s",
        "default": -4,
        "tooltip": "Verschiebt, wann der Auto-Scroll die Zeile eines "
                   "SyncPoints erreicht. Negativ = früher, empfohlen -4. "
                   "Im SyncPoint-Modus ohne Wirkung.",
    },
    "lyrics/dynamic_swap_offset": {
        "label": "Texttausch timen",
        "widget": "spinbox",
        "min": -10, "max": 10, "step": 1, "suffix": " s",
        "default": -4,
        "tooltip": "Verschiebt bei Dynamic Lyrics den Sequenzwechsel und den "
                   "Heads/Sides-Tausch. Negativ = früher, empfohlen -4.",
    },
    # intern#76: Leseposition und Lesebalken (Live-Orientierung)
    "lyrics/reading_position_pct": {
        "label": "Leseposition",
        "widget": "spinbox",
        "min": 0, "max": 100, "step": 5, "suffix": " %",
        "default": 30,
        "tooltip": "In welcher Höhe des Lyric-Fensters der gerade gesungene "
                   "Text steht: 0 % = ganz oben, 100 % = ganz unten.",
    },
    "lyrics/reading_band_enabled": {
        "label": "Lesebalken anzeigen",
        "widget": "checkbox",
        "default": True,
        "tooltip": "Hinterlegt den gerade gesungenen Text farbig, damit man "
                   "ihn nach einem Blick weg sofort wiederfindet.",
    },
    "lyrics/reading_band_height": {
        "label": "Lesebalken-Höhe",
        "widget": "spinbox",
        "min": 2, "max": 60, "step": 1, "suffix": " %",
        "default": 20,
        "tooltip": "Höhe des Lesebalkens in Prozent der Fensterhöhe.",
    },
    "lyrics/reading_band_opacity": {
        "label": "Lesebalken-Deckkraft",
        "widget": "spinbox",
        "min": 5, "max": 100, "step": 5, "suffix": " %",
        "default": 30,
        "tooltip": "Deckkraft des Lesebalkens. Die Farbe kommt aus dem Theme.",
    },
    # intern#148: In-Lesebalken Countdown
    "lyrics/reading_band_countdown": {
        "label": "In-Lesebalken Countdown",
        "widget": "checkbox",
        "default": True,
        "tooltip": "Zählt rechts im Lesebalken die Beats bis zum nächsten "
                   "Abschnittswechsel herunter.",
    },
    "lyrics/reading_band_countdown_beats": {
        "label": "In-Lesebalken Countdown: Vorlauf",
        "widget": "spinbox",
        "min": 2, "max": 16, "step": 1, "suffix": " Beats",
        "default": 8,
        "tooltip": "Ab wie vielen Beats vor dem Abschnittswechsel der "
                   "Countdown erscheint.",
    },
    # --- clock (intern#235) ---
    "clock/show_seconds": {
        "label": "Sekunden anzeigen",
        "widget": "checkbox",
        "default": False,
    },
    "clock/twelve_hour": {
        "label": "12-Stunden-Format (AM/PM)",
        "widget": "checkbox",
        "default": False,
    },
    "clock/show_date": {
        "label": "Datum anzeigen",
        "widget": "checkbox",
        "default": True,
    },
    # --- debug ---
    "debug/performance_logging": {
        "label": "Performance-Logging",
        "widget": "checkbox",
        "requires_restart": True,
        "tooltip": "Schreibt Main-Thread-Timings in perf_log.txt. Nur zur Fehlersuche.",
    },
}

# Benutzerfreundliche Sektions-Labels
_SECTION_LABELS = {
    "display":   "Anzeige",
    "paths":     "Pfade",
    "audio":     "Audio",
    "loop":      "Loop",
    "player":    "Player",
    "playlist":  "Playlist",
    "feedback":  "Feedback",
    "network":   "Netzwerk",
    "sort":      "Sortierung",
    "sequences": "Sequenzen",
    "notes":     "Notizen",
    "lyrics":    "Lyrics",
    "clock":     "Uhr",
    "debug":     "Debug",
    "rules":     "Rules (System)",
}


# ---------------------------------------------------------------------------
# Hilfs-Funktionen
# ---------------------------------------------------------------------------

def _is_excluded_section(name: str, settings: QSettings) -> bool:
    if name in _EXCLUDED_SECTIONS:
        return True
    if name.endswith(_EXCLUDED_SUFFIX):
        return True
    # Sektionen die nur Geometrie-Binaerdaten enthalten
    settings.beginGroup(name)
    keys = settings.childKeys()
    settings.endGroup()
    if keys == ["geometry"] or keys == ["geometry", "windowstate"] or keys == ["windowstate"]:
        return True
    return False


def _is_excluded_key(section: str, key: str) -> bool:
    if section == "rules" and not key.startswith(_RULES_KEY_PATTERN):
        return True
    excluded = _EXCLUDED_KEYS.get(section, set())
    return key in excluded


def _detect_widget_type(key: str, value: str) -> str:
    """Erkennt den Widget-Typ aus Key-Name und Wert-String."""
    if value.lower() in ("true", "false"):
        return "checkbox"
    if "_dir" in key or "_path" in key:
        return "path"
    try:
        int(value)
        return "spinbox"
    except ValueError:
        pass
    try:
        float(value)
        return "doublespinbox"
    except ValueError:
        pass
    return "lineedit"


# ---------------------------------------------------------------------------
# Lautstaerke-Vorschau: kurzer Ton auf dem Sekundaergeraet
# ---------------------------------------------------------------------------

def _play_ping(volume: float, device_idx):
    """Spielt einen kurzen 440-Hz-Ton auf dem angegebenen Geraet.

    Wird aufgerufen wenn der Nutzer den Sekundaerkanal-Lautstaerkeregler bewegt,
    damit er den ungefaehren Pegel einschaetzen kann.
    Laeuft im Daemon-Thread — blockiert den UI-Thread nicht.
    """
    if not _SD_AVAILABLE:
        return
    import threading

    def _worker():
        try:
            import numpy as np
            sr = 44100
            dur = 0.5
            t = np.linspace(0, dur, int(sr * dur), endpoint=False)
            envelope = np.exp(-8.0 * t)          # Schnelles Ausklingen
            wave = (np.sin(2 * np.pi * 440 * t) * envelope * float(volume)).astype(np.float32)
            stereo = np.column_stack([wave, wave])
            _sd.play(stereo, samplerate=sr, device=device_idx)
            _sd.wait()
        except Exception:
            pass  # Geraet nicht verfuegbar o.ae. → still ignorieren

    threading.Thread(target=_worker, daemon=True).start()


# ---------------------------------------------------------------------------
# Widget-Zeile: Label + Widget (+ optional Browse-Button)
# ---------------------------------------------------------------------------

class _SettingRow:
    """Kapselt Label, Widget und den aktuellen Wert fuer eine INI-Einstellung."""

    def __init__(self, section: str, key: str, raw_value: str, skin_mgr=None,
                 program_picker_cb=None, program_label_cb=None):
        self.section = section
        self.key = key
        self.full_key = f"{section}/{key}"

        meta = SETTINGS_META.get(self.full_key, {})
        widget_type = meta.get("widget") or _detect_widget_type(key, raw_value)
        # Meta auf der Row aufheben, damit _browse() Optionen wie file_filter
        # (BL-137: Audiodatei-Picker) lesen kann.
        self._meta = meta
        self._widget_type = widget_type
        # MS50: Callbacks fuer den "program_picker"-Zeilentyp (Anzeige + Picker).
        # Der eigentliche Auswahl-Dialog (_MultiProgramPickerDialog) lebt in main.py;
        # er wird per Callback hereingereicht, um Zirkelimporte zu vermeiden.
        self._program_picker_cb = program_picker_cb
        self._program_label_cb = program_label_cb
        self._program_ids = []

        # Label — erst i18n-Key versuchen, dann meta["label"], dann rohen Key
        t_key = f"setting_label_{section}_{key}"
        translated = _t(t_key)
        label_text = translated if translated != t_key else (meta.get("label") or key)
        self.label = QLabel(label_text + ":")
        self.label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        # Tooltip — ebenfalls i18n-faehig
        tip_key = f"setting_tip_{section}_{key}"
        tip_translated = _t(tip_key)
        tooltip = tip_translated if tip_translated != tip_key else meta.get("tooltip", "")
        if tooltip:
            self.label.setToolTip(tooltip)

        # Widget
        self.widget = self._build_widget(widget_type, raw_value, meta, skin_mgr)
        # intern#189: Ausgangswert ist, was das Widget zeigt, nicht der rohe
        # INI-Wert. Sonst gilt eine Zeile ohne INI-Wert ("" gegen "false")
        # als geaendert und wird beim Speichern ungefragt geschrieben.
        self.original = self.get_value()
        if tooltip and self.widget:
            self.widget.setToolTip(tooltip)

        # Browse-Button fuer Pfad- und Datei-Felder (BL-137: file)
        self.browse_btn = None
        if widget_type in ("path", "file"):
            self.browse_btn = QPushButton("…")
            self.browse_btn.setFixedWidth(30)
            self.browse_btn.clicked.connect(self._browse)

        # MS50: Picker-Button fuer den "program_picker"-Zeilentyp
        self.picker_btn = None
        if widget_type == "program_picker":
            btn_txt = _t("settings_program_pick_btn")
            self.picker_btn = QPushButton(
                btn_txt if btn_txt != "settings_program_pick_btn" else "…")
            self.picker_btn.clicked.connect(self._pick_programs)

    def _build_widget(self, widget_type: str, raw_value: str, meta: dict, skin_mgr) -> QWidget:
        if widget_type == "program_picker":
            # Nur-Anzeige der aktuell gewaehlten Programm-Codes; editiert wird ueber
            # den Picker-Button (self.picker_btn -> _pick_programs).
            self._program_ids = program_selection.parse_ids(raw_value)
            w = QLineEdit()
            w.setReadOnly(True)
            if self._program_label_cb:
                w.setText(self._program_label_cb(self._program_ids))
            w.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            return w

        if widget_type == "checkbox":
            w = QCheckBox()
            w.setChecked(raw_value.lower() == "true")
            return w

        if widget_type == "spinbox":
            w = QSpinBox()
            w.setMinimum(meta.get("min", 0))
            w.setMaximum(meta.get("max", 99999))
            w.setSingleStep(meta.get("step", 1))
            if meta.get("suffix"):
                w.setSuffix(meta["suffix"])
            try:
                w.setValue(int(raw_value))
            except (ValueError, TypeError):
                pass
            return w

        if widget_type == "doublespinbox":
            w = QDoubleSpinBox()
            w.setMinimum(meta.get("min", 0.0))
            w.setMaximum(meta.get("max", 9999.0))
            w.setSingleStep(meta.get("step", 0.1))
            w.setDecimals(2)
            if meta.get("suffix"):
                w.setSuffix(meta["suffix"])
            try:
                w.setValue(float(raw_value))
            except (ValueError, TypeError):
                pass
            return w

        if widget_type == "device_combo":
            w = QComboBox()
            w.addItem("System-Standard", "")
            if _SD_AVAILABLE:
                try:
                    devices = _sd.query_devices()
                    for i, dev in enumerate(devices):
                        if dev["max_output_channels"] > 0:
                            name = dev["name"]
                            try:
                                api = _sd.query_hostapis(dev["hostapi"])["name"]
                                short = api.replace("Windows ", "")
                                label = f"{name} ({short})"
                            except Exception:
                                label = f"{i}: {name}"
                            w.addItem(label, str(i))
                except Exception:
                    pass
            idx = w.findData(raw_value)
            if idx >= 0:
                w.setCurrentIndex(idx)
            # Expanding: Combo fuellt die verfuegbare Feldbreite und skaliert mit
            # dem Fenster. Der horizontale Scrollbar des QScrollArea ist AlwaysOff,
            # deshalb wirkt die Viewport-Breite als natuerliche Obergrenze.
            w.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            return w

        if widget_type == "combobox":
            w = QComboBox()
            choices = list(meta.get("choices", []))
            # Skin-Choices dynamisch
            if self.full_key == "display/skin" and skin_mgr is not None:
                choices = [(s, s) for s in skin_mgr.list_skins()]
            # Sortier-Choices dynamisch: die Beschriftungen kommen aus i18n,
            # die Werte sind die SORT_*-Konstanten der SongFilterBar.
            elif self.full_key == "sort/default_mode":
                choices = [(str(mode), _t(tkey)) for tkey, mode in (
                    ("sort_alphabetical",    0),
                    ("sort_quality",         1),
                    ("sort_last_played",     2),
                    ("sort_recommendation",  3),
                    ("sort_date_added",      4),
                    ("sort_random",          5),
                    ("sort_weighted_random", 6),
                )]
            elif self.full_key == "loop/finder_window_mode":
                choices = [
                    ("pct",  _t("lf_mode_pct_long")),
                    ("time", _t("lf_mode_time_long")),
                ]
            elif self.full_key == "playlist/patter_fill_type":
                choices = [
                    ("infinite", _t("patter_fill_infinite")),
                    ("target",   _t("patter_fill_target")),
                ]
            elif self.full_key == "lyrics/dynamic_mode":
                choices = [
                    ("1", _t("dynamic_mode_opt1")),
                    ("2", _t("dynamic_mode_opt2")),
                ]
            elif self.full_key == "lyrics/dynamic_invert_mode":
                choices = [(m, _t(f"dynamic_invert_opt_{m.lower()}"))
                           for m in ("HHSS", "HSSH", "HSHS")]
            elif self.full_key == "notes/insert_position":
                choices = [
                    ("top",    _t("note.btn_pos_top")),
                    ("middle", _t("note.btn_pos_middle")),
                    ("bottom", _t("note.btn_pos_bottom")),
                ]
            for val, display in choices:
                w.addItem(display, userData=val)
            # Aktuellen Wert vorauswaehlen
            idx = w.findData(raw_value)
            if idx >= 0:
                w.setCurrentIndex(idx)
            elif self.full_key == "lyrics/dynamic_invert_mode":
                # Noch keine Art gewaehlt: leer lassen statt still die erste
                # vorzuwaehlen, sonst speichert jedes OK ungefragt HHSS (intern#127)
                w.setCurrentIndex(-1)
            return w

        if widget_type == "dateedit":
            w = QDateEdit()
            w.setDisplayFormat("yyyy-MM-dd")
            w.setCalendarPopup(True)
            try:
                date = QDate.fromString(raw_value, "yyyy-MM-dd")
                if date.isValid():
                    w.setDate(date)
                else:
                    w.setDate(QDate.currentDate())
            except Exception:
                w.setDate(QDate.currentDate())
            return w

        # path + lineedit
        w = QLineEdit()
        w.setText(raw_value)
        return w

    def _browse(self):
        current = self.get_value()
        # BL-137: Datei-Picker wenn widget=file, sonst Ordner-Picker
        if self._widget_type == "file":
            start_dir = os.path.dirname(current) if current and os.path.isfile(current) else ""
            file_filter = self._meta.get("file_filter", "Alle Dateien (*.*)")
            chosen, _ = QFileDialog.getOpenFileName(
                None, f"Datei wählen — {self.key}", start_dir, file_filter,
            )
            if chosen:
                self.widget.setText(chosen)
            return
        start = current if os.path.isdir(current) else ""
        chosen = QFileDialog.getExistingDirectory(
            None, f"Ordner wählen — {self.key}", start
        )
        if chosen:
            self.widget.setText(chosen)

    def _pick_programs(self):
        """MS50: oeffnet den (aus main.py hereingereichten) Tanzprogramm-Picker."""
        if not self._program_picker_cb:
            return
        new_ids = self._program_picker_cb(self._program_ids, self.picker_btn)
        if new_ids is not None:
            self._program_ids = list(new_ids)
            if self._program_label_cb:
                self.widget.setText(self._program_label_cb(self._program_ids))

    def get_value(self) -> str:
        """Aktuellen Wert aus dem Widget als String."""
        if self._widget_type == "program_picker":
            return ",".join(str(i) for i in self._program_ids)
        w = self.widget
        if isinstance(w, QCheckBox):
            return "true" if w.isChecked() else "false"
        if isinstance(w, QSpinBox):
            return str(w.value())
        if isinstance(w, QDoubleSpinBox):
            return str(w.value())
        if isinstance(w, QComboBox):
            data = w.currentData()
            return str(data) if data is not None else w.currentText()
        if isinstance(w, QDateEdit):
            return w.date().toString("yyyy-MM-dd")
        if isinstance(w, QLineEdit):
            return w.text()
        return ""

    def is_changed(self) -> bool:
        return self.get_value() != self.original

    def layout_widget(self) -> QWidget:
        """Gibt den Container fuer das Formular-Layout zurueck (Widget + ggf. Zusatz-Btn)."""
        extra_btn = self.browse_btn or self.picker_btn
        if extra_btn is None:
            return self.widget
        container = QWidget()
        h = QHBoxLayout(container)
        h.setContentsMargins(0, 0, 0, 0)
        h.addWidget(self.widget)
        h.addWidget(extra_btn)
        return container


# ---------------------------------------------------------------------------
# Haupt-Dialog
# ---------------------------------------------------------------------------

class SettingsDialog(QDialog):
    """
    Generisches Einstellungen-Fenster.

    Laedt alle nicht-ausgeschlossenen INI-Sektionen und stellt sie als
    Gruppenfelder auf einer einzigen scrollbaren Seite dar.
    """

    def __init__(self, parent, settings: QSettings, skin_mgr=None, on_apply=None,
                 program_picker_cb=None, program_label_cb=None, focus_key=None):
        super().__init__(parent)
        self._settings = settings
        self._skin_mgr = skin_mgr
        self._on_apply = on_apply   # callable(changed_keys: list[str])
        # MS50: Callbacks fuer den "program_picker"-Zeilentyp (Anzeige + Auswahl)
        self._program_picker_cb = program_picker_cb
        self._program_label_cb = program_label_cb
        self._rows: list[_SettingRow] = []
        # intern#127: nach dem (deferten) Aufbau zu dieser Zeile springen
        self._focus_key = focus_key

        self.setWindowTitle(_t("settings_dialog_title"))
        self.setMinimumSize(560, 500)
        self.resize(660, 680)

        self._build_ui()

    def focus_row(self, full_key: str) -> bool:
        """Scrollt zur Zeile full_key (ins obere Drittel) und setzt den Fokus
        auf ihr Feld (z. B. vom Spiegel-Button im Lyrics-Fenster, intern#127).

        intern#133: Direkt nach dem deferten Aufbau hat die Scroll-Flaeche
        noch keine Hoehe (Scrollbereich 0), ein Sprung liefe ins Leere. Dann
        wird gescrollt, sobald der Scrollbereich steht (rangeChanged)."""
        row = next((r for r in self._rows if r.full_key == full_key), None)
        if row is None:
            return False
        bar = self._scroll.verticalScrollBar()
        inner = self._scroll.widget()

        def scroll_to_row():
            y = row.widget.mapTo(inner, QPoint(0, 0)).y()
            bar.setValue(y - self._scroll.viewport().height() // 3)

        def on_range(_min, maximum):
            if maximum > 0:
                bar.rangeChanged.disconnect(on_range)
                scroll_to_row()

        self._inner_layout.activate()   # Geometrie der frisch gebauten Zeilen
        if bar.maximum() > 0:
            scroll_to_row()
        else:
            bar.rangeChanged.connect(on_range)
        row.widget.setFocus()
        return True

    # ------------------------------------------------------------------
    # UI aufbauen
    # ------------------------------------------------------------------

    def _build_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 6)
        main_layout.setSpacing(6)

        # Scrollbereich der alle Gruppenfelder enthaelt.
        # AlwaysOff: kein horizontaler Scrollbar — die innere Widget-Breite wird
        # auf die Viewport-Breite begrenzt, Combos wachsen/schrumpfen mit dem Fenster.
        scroll = QScrollArea()
        self._scroll = scroll
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        inner = QWidget()
        self._inner_layout = QVBoxLayout(inner)
        self._inner_layout.setContentsMargins(4, 4, 4, 4)
        self._inner_layout.setSpacing(8)

        # Deferred: Widget-Aufbau erst im naechsten Event-Loop-Tick, damit
        # der Dialog sofort erscheint und der Main-Thread nicht blockiert.
        QTimer.singleShot(0, self._populate_groups_deferred)

        scroll.setWidget(inner)
        main_layout.addWidget(scroll)

        # Button-Leiste
        btn_box = QDialogButtonBox()
        ok_btn = btn_box.addButton(_t("settings_btn_ok"), QDialogButtonBox.ButtonRole.AcceptRole)
        cancel_btn = btn_box.addButton(_t("settings_btn_cancel"), QDialogButtonBox.ButtonRole.RejectRole)
        apply_btn = btn_box.addButton(_t("settings_btn_apply"), QDialogButtonBox.ButtonRole.ApplyRole)

        ok_btn.clicked.connect(self._on_ok)
        cancel_btn.clicked.connect(self.reject)
        apply_btn.clicked.connect(self._on_apply_btn)

        main_layout.addWidget(btn_box)

    def _populate_groups_deferred(self):
        """Wird per QTimer.singleShot(0) aufgerufen — haelt Main-Thread frei."""
        self._populate_groups()
        self._inner_layout.addStretch()
        if self._focus_key:
            # Erst wenn die Zeilen stehen; ein Takt spaeter hat das Layout Geometrie
            QTimer.singleShot(0, lambda k=self._focus_key: self.focus_row(k))
        self._wire_audition_preview()
        # Mausrad-Schutz auf Fenster-Ebene: alle SpinBoxes/Combos/Date/Slider
        # ignorieren Wheel-Events. Damit sind auch zukuenftige Felder
        # automatisch geschuetzt — keine Subklassen mehr noetig.
        for child in self.findChildren(QAbstractSpinBox):
            child.installEventFilter(self)
        for child in self.findChildren(QComboBox):
            child.installEventFilter(self)
        for child in self.findChildren(QSlider):
            child.installEventFilter(self)

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Wheel and isinstance(
                obj, (QAbstractSpinBox, QComboBox, QSlider)):
            event.ignore()
            return True
        return super().eventFilter(obj, event)

    def _wire_audition_preview(self):
        """Verbindet secondary_volume-Spinbox mit Ping auf dem Sekundaergeraet."""
        sec_dev_row = next((r for r in self._rows if r.full_key == "audio/secondary_device"), None)
        sec_vol_row = next((r for r in self._rows if r.full_key == "audio/secondary_volume"), None)
        if sec_vol_row is None or not isinstance(sec_vol_row.widget, QSpinBox):
            return

        def _on_vol_changed(value):
            dev_str = sec_dev_row.widget.currentData() if sec_dev_row else ""
            try:
                dev = int(dev_str) if dev_str else None
            except (ValueError, TypeError):
                dev = None
            _play_ping(value / 100.0, dev)

        sec_vol_row.widget.valueChanged.connect(_on_vol_changed)

    def _populate_groups(self):
        """Liest alle INI-Sektionen und baut ein QGroupBox pro Sektion."""
        top_groups = list(self._settings.childGroups())
        # Sektionen aus SETTINGS_META ergaenzen, die noch gar nicht in der INI
        # stehen (frische Installation) — sonst waeren ihre Keys unerreichbar.
        for full in SETTINGS_META:
            sec = full.split("/", 1)[0]
            if sec not in top_groups:
                top_groups.append(sec)
        sections = [s for s in top_groups if not _is_excluded_section(s, self._settings)]

        _ORDER = ["display", "paths", "audio", "loop", "player", "playlist",
                  "feedback", "sort", "sequences", "notes", "lyrics", "clock", "debug",
                  "rules"]
        ordered = [s for s in _ORDER if s in sections]
        rest = sorted(s for s in sections if s not in _ORDER)

        for section in ordered + rest:
            self._add_section_group(section)

    def _add_section_group(self, section: str):
        self._settings.beginGroup(section)
        keys = sorted(self._settings.childKeys())
        self._settings.endGroup()

        # Meta-Keys dieser Sektion ergaenzen, auch wenn sie noch nicht in der INI stehen.
        # Damit erscheinen neue Settings automatisch im Dialog, sobald sie in
        # SETTINGS_META eingetragen sind — ohne dass jemand vorher die INI editiert.
        meta_keys = [
            full.split("/", 1)[1]
            for full in SETTINGS_META
            if full.startswith(f"{section}/")
        ]
        for mk in meta_keys:
            if mk not in keys:
                keys.append(mk)
        keys = sorted(keys)

        keys = [k for k in keys if not _is_excluded_key(section, k)]
        if not keys:
            return

        t_section_key = f"setting_section_{section}"
        t_section = _t(t_section_key)
        title = t_section if t_section != t_section_key else _SECTION_LABELS.get(section, section.capitalize())
        group = QGroupBox(title)
        form = QFormLayout(group)
        form.setContentsMargins(10, 14, 10, 10)
        form.setSpacing(7)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)

        for key in keys:
            # Wenn INI keinen Wert hat, faellt der Default aus SETTINGS_META ein
            meta = SETTINGS_META.get(f"{section}/{key}", {})
            raw = str(self._settings.value(f"{section}/{key}", meta.get("default", "")))
            row = _SettingRow(section, key, raw, self._skin_mgr,
                              program_picker_cb=self._program_picker_cb,
                              program_label_cb=self._program_label_cb)
            self._rows.append(row)
            form.addRow(row.label, row.layout_widget())

        self._inner_layout.addWidget(group)

    # ------------------------------------------------------------------
    # Speichern / Apply
    # ------------------------------------------------------------------

    def _collect_changes(self) -> list[str]:
        """Gibt Liste der geaenderten full_keys zurueck."""
        return [r.full_key for r in self._rows if r.is_changed()]

    def _write_changes(self, changed_keys: list[str]):
        for row in self._rows:
            if row.full_key in changed_keys:
                self._settings.setValue(row.full_key, row.get_value())
                row.original = row.get_value()  # Reset zum neuen Wert
        self._settings.sync()

    def _check_restart_needed(self, changed_keys: list[str]) -> bool:
        return any(k in _RESTART_KEYS for k in changed_keys)

    def _enable_invert_on_first_mode(self):
        """intern#133: Wer zum ersten Mal eine Heads/Sides-Art waehlt, will sie
        benutzen -> Tausch mit einschalten. Ein spaeterer Artwechsel laesst
        An/Aus in Ruhe."""
        rows = {r.full_key: r for r in self._rows}
        mode = rows.get("lyrics/dynamic_invert_mode")
        enabled = rows.get("lyrics/dynamic_invert_enabled")
        if mode and enabled and not mode.original and mode.get_value():
            enabled.widget.setChecked(True)

    def _on_apply_btn(self):
        self._enable_invert_on_first_mode()
        changed = self._collect_changes()
        if not changed:
            return
        self._write_changes(changed)
        if self._on_apply:
            self._on_apply(changed)
        if self._check_restart_needed(changed):
            QMessageBox.information(
                self,
                _t("settings_restart_required_title"),
                _t("settings_restart_required_msg"),
            )

    def _on_ok(self):
        self._on_apply_btn()
        self.accept()
