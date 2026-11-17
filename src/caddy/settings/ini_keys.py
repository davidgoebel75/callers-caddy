"""Verzeichnis aller (bisher umgestellten) INI-Schluessel mit Standardwert.

Einzige Quelle fuer den Standardwert eines Schluessels und fuer die Saat, die
`_write_ini_defaults()` beim Start in die INI schreibt (intern#144, Teil von
#146). Neuer INI-Schluessel: hier eintragen, `seed=True` nur, wenn er beim Start
in die INI geschrieben werden soll (sonst zeigt der Einstellungsdialog ihn nicht).

Bewusst kein eigenes Parsen: `get()` reicht an `settings.value()` durch, jede
Lesestelle behaelt ihre Umwandlung (`int(..)`, `type=bool`, `try/except`).
Qt-frei: `settings` ist jedes Objekt mit `.value(key, default, **kw)`.

Noch nicht erfasst: Schluessel in den uebrigen Modulen (siehe Plan intern#144),
Familien wie `rules/<id>_*`, `floatrect/..`, `dockfree/..`.
"""
from dataclasses import dataclass

QT_FREE = True


@dataclass(frozen=True)
class IniKey:
    key: str            # "lyrics/reading_band_height"
    type: type          # bool | int | float | str
    default: object     # typisiert, wie ihn der Code uebergibt
    seed: bool = False  # True = _write_ini_defaults() schreibt ihn beim Start


# Schluessel, die mehrere Module brauchen (intern#235)
CLOCK_SHOW_SECONDS = "clock/show_seconds"
CLOCK_TWELVE_HOUR = "clock/twelve_hour"
CLOCK_SHOW_DATE = "clock/show_date"
# intern#247: Square Flow (Choreo-Engine)
SQUARE_FLOW_ENABLED = "square_flow/enabled"
SQUARE_FLOW_FRAME_RATE = "square_flow/frame_rate"
SQUARE_FLOW_SAVING_MODE = "square_flow/saving_mode"


def _k(key, typ, default, seed=False):
    return IniKey(key, typ, default, seed)


# Reihenfolge der seed=True-Eintraege = Reihenfolge der geschriebenen INI.
_ENTRIES = (
    _k("player/timer_warn1", int, 240, True),
    _k("player/timer_warn2", int, 300, True),
    _k("loop/crossfade_ms", int, 46, True),
    # intern#207: Suchfenster des Loop Finders in Prozent oder Zeit
    _k("loop/finder_window_mode", str, "pct", True),
    _k("debug/performance_logging", bool, False, True),
    _k("audio/min_volume", float, 0.0, True),
    # Anti-Ruckler-Schalter (docs/anti_ruckler_backlog.md, AR-009/010): Standard an
    _k("audio/mmcss_priority", bool, True, True),
    _k("audio/log_underflows", bool, True, True),
    # AR-008: WASAPI Exclusive Mode (User-Opt-in)
    _k("audio/wasapi_exclusive", bool, False, True),
    # BL-074: Sekundaerkanal fuer Audition, leer = System-Standard
    _k("audio/secondary_device", str, "", True),
    _k("audio/secondary_volume", int, 80, True),
    # BL-119: Feedback-Dialog nach Songende
    _k("feedback/enabled", bool, False, True),
    # intern#96: Einfuegeposition neuer Notizen (top/bottom)
    _k("notes/insert_position", str, "top", True),
    # intern#198
    _k("notes/first_note_factor", float, 4.0, True),
    # intern#246: Zeilenabstand der Notizen, 100 = echte Zeilenhoehe
    _k("notes/line_spacing_pct", int, 100, True),
    # intern#127: Heads/Sides invertieren. Art leer = noch nicht gewaehlt
    _k("lyrics/dynamic_invert_enabled", bool, False, True),
    _k("lyrics/dynamic_invert_mode", str, "", True),
    # intern#115: Timing-Parameter (Sekunden, negativ = frueher)
    _k("lyrics/text_jump_offset", int, -4, True),
    _k("lyrics/dynamic_swap_offset", int, -4, True),
    # intern#76: Leseposition (% von oben) und Lesebalken
    _k("lyrics/reading_position_pct", int, 30, True),
    _k("lyrics/reading_band_enabled", bool, True, True),
    _k("lyrics/reading_band_height", int, 20, True),
    _k("lyrics/reading_band_opacity", int, 30, True),
    # intern#148: In-Lesebalken Countdown (Beats bis zum Abschnittswechsel)
    _k("lyrics/reading_band_countdown", bool, True, True),
    _k("lyrics/reading_band_countdown_beats", int, 8, True),
    # intern#205: Startwert "Auch ausgeblendete Sequenzen anzeigen"
    _k("sequences/show_hidden_on_start", bool, False, True),
    # intern#235: Uhr-Dock, eigene Sektion [clock] (Rechtsklick + Dialog)
    _k(CLOCK_SHOW_SECONDS, bool, False, True),
    _k(CLOCK_TWELVE_HOUR, bool, False, True),
    _k(CLOCK_SHOW_DATE, bool, True, True),
    # intern#247: Square Flow, standardmaessig aus (ohne Freigabe wird nichts geladen)
    _k(SQUARE_FLOW_ENABLED, bool, False, True),
    _k(SQUARE_FLOW_FRAME_RATE, int, 25, True),
    _k(SQUARE_FLOW_SAVING_MODE, bool, False, True),
    # --- ohne Saat ---
    _k("lyrics/dynamic_enabled", bool, False),
    _k("lyrics/dynamic_mode", str, ""),
    _k("lyrics/auto_size", bool, True),
    _k("lyrics/auto_width", bool, False),
    _k("lyrics/zoom_pct", int, 100),
    # Pfade relativ zum App-Verzeichnis; Slots 2..4 leer = nicht genutzt
    _k("paths/music_dir_1", str, "music"),
    _k("paths/music_dir_2", str, ""),
    _k("paths/music_dir_3", str, ""),
    _k("paths/music_dir_4", str, ""),
    _k("paths/import_dir", str, "neu"),
    _k("paths/lyrics_dir", str, "lyrics"),
    _k("paths/playlist_dir", str, "playlists"),
)

KEYS = {e.key: e for e in _ENTRIES}
assert len(KEYS) == len(_ENTRIES), "doppelter INI-Schluessel"


def get(settings, key, **kw):
    """Wie `settings.value(key, <Standard aus dem Verzeichnis>, **kw)`."""
    return settings.value(key, KEYS[key].default, **kw)


def default(key):
    return KEYS[key].default


def _text(value):
    return str(value).lower() if isinstance(value, bool) else str(value)


def seed_items():
    """{key: Textform} der seed=True-Eintraege, in Verzeichnis-Reihenfolge."""
    return {e.key: _text(e.default) for e in _ENTRIES if e.seed}


def seed_keys():
    return {e.key for e in _ENTRIES if e.seed}
