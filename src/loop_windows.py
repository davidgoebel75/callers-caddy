"""Suchfenster des Loop Finders: Preset + Songdauer -> absolute Sekunden (intern#207).

UI-frei, damit Loop Finder, Rule "Auto-Set Best Loop" und Potential
dieselbe Umrechnung nutzen (Architektur intern#146).

Ein Preset gibt die Fenster in einer von zwei Arten an (Feld ``mode``):

- ``"pct"`` (Standard, auch wenn ``mode`` fehlt): alle vier Werte in Prozent
  der Songdauer.
- ``"time"``: ``in_start``/``in_end`` in Sekunden ab Songbeginn,
  ``out_start``/``out_end`` in Sekunden vor Songende (positiv, also
  ``out_start`` > ``out_end``).
"""

import json
import os

MODE_PCT = "pct"
MODE_TIME = "time"
MODES = (MODE_PCT, MODE_TIME)

SINGING_PRESET_NAME = "Singing"
# Abwaertskompatibilitaet: alte Preset-Namen -> aktueller Name.
PRESET_ALIASES = {"Standard": SINGING_PRESET_NAME}

# Singing-Fenster (Prozent der Songdauer)
DEFAULT_IN_START = 7
DEFAULT_IN_END = 21
DEFAULT_OUT_START = 64
DEFAULT_OUT_END = 79

# Standardfenster im Zeitmodus (Sekunden ab Beginn / vor Ende). Gelten, wenn
# ohne bekannte Songdauer in den Zeitmodus gewechselt wird - Prozentwerte
# lassen sich dann nicht umrechnen (Review PR #132).
DEFAULT_TIME_IN_START = 20
DEFAULT_TIME_IN_END = 59
DEFAULT_TIME_OUT_START = 50
DEFAULT_TIME_OUT_END = 20

_KEYS = ("in_start", "in_end", "out_start", "out_end")


def default_values(mode: str) -> tuple:
    """Standardfenster (in_start, in_end, out_start, out_end) fuer einen Modus."""
    if mode == MODE_TIME:
        return (DEFAULT_TIME_IN_START, DEFAULT_TIME_IN_END,
                DEFAULT_TIME_OUT_START, DEFAULT_TIME_OUT_END)
    return (DEFAULT_IN_START, DEFAULT_IN_END, DEFAULT_OUT_START, DEFAULT_OUT_END)


def singing_preset() -> dict:
    """Das unveraenderbare Singing-Preset (feste Prozentwerte)."""
    return {
        "mode": MODE_PCT,
        "in_start": DEFAULT_IN_START,
        "in_end": DEFAULT_IN_END,
        "out_start": DEFAULT_OUT_START,
        "out_end": DEFAULT_OUT_END,
        "compare_beats": 16,
        "selection_strategy": "best_64",
    }


def preset_mode(preset: dict) -> str:
    """Art der Angabe eines Presets; ohne (gueltiges) ``mode`` = Prozent."""
    mode = str(preset.get("mode", MODE_PCT))
    return mode if mode in MODES else MODE_PCT


def load_preset_file(name: str, presets_dir) -> dict:
    """Laedt ein gespeichertes Preset per Name, sonst das Singing-Preset.

    Alte Namen (z.B. "Standard") werden auf den aktuellen Namen gemappt.
    Die dynamischen Optimize-Stufen kennt diese Funktion nicht, die haengen
    an den Marken des Songs und bleiben beim Aufrufer.
    """
    name = PRESET_ALIASES.get(name, name)
    if name == SINGING_PRESET_NAME or not presets_dir:
        return singing_preset()
    path = os.path.join(presets_dir, f"{name}.json")
    if os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            if isinstance(data, dict):
                return data
        except Exception:
            pass
    return singing_preset()


def resolve_windows(preset: dict, duration: float):
    """Preset + Songdauer -> (in_start, in_end, out_start, out_end) in Sekunden.

    Gibt ``None`` zurueck, wenn die Fenster nicht zur Songlaenge passen:
    ein Fenster ist leer oder ragt ueber Songbeginn/-ende hinaus, oder
    Loop-In reicht in Loop-Out hinein. Es wird bewusst nichts
    zurechtgebogen, die Analyse soll dann nicht laufen.
    """
    if not duration or duration <= 0:
        return None
    defaults = singing_preset()
    try:
        v = [float(preset.get(k, defaults[k])) for k in _KEYS]
    except (TypeError, ValueError):
        return None
    if preset_mode(preset) == MODE_TIME:
        in_s, in_e = v[0], v[1]
        out_s, out_e = duration - v[2], duration - v[3]
    else:
        in_s, in_e, out_s, out_e = (duration * p / 100.0 for p in v)
    if not (0.0 <= in_s < in_e <= out_s < out_e <= duration):
        return None
    return in_s, in_e, out_s, out_e


def pct_to_time(values, duration: float) -> tuple:
    """Prozentwerte -> Zeitwerte (ganze Sekunden, Loop-Out vor Ende)."""
    in_s, in_e, out_s, out_e = (duration * p / 100.0 for p in values)
    return (int(round(in_s)), int(round(in_e)),
            int(round(duration - out_s)), int(round(duration - out_e)))


def time_to_pct(values, duration: float) -> tuple:
    """Zeitwerte (Loop-Out vor Ende) -> ganze Prozent, begrenzt auf 0-100."""
    in_s, in_e, out_before_s, out_before_e = values
    secs = (in_s, in_e, duration - out_before_s, duration - out_before_e)
    return tuple(int(max(0, min(100, round(s / duration * 100.0)))) for s in secs)
