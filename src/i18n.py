"""
Internationalisierung (i18n) fuer Callers Caddy.
=================================================
Einfaches Dict-basiertes System mit JSON-Translations.

Verwendung:
    from i18n import _t, set_language, get_language, get_available_languages

    # Sprache setzen (einmal beim Start)
    set_language("en")

    # Text uebersetzen
    label = QLabel(_t("no_file_loaded"))
"""

import json
import os
import sys

# Aktuelle Sprache (Default: Deutsch)
_current_language = "de"

# Translations-Dict: {key: {lang: text}}
_translations: dict = {}


def _load_translations():
    """Laedt translations.json aus dem gleichen Verzeichnis."""
    global _translations
    # PyInstaller: translations.json liegt neben der EXE, nicht in _internal
    if getattr(sys, 'frozen', False):
        base_dir = os.path.dirname(sys.executable)
    else:
        base_dir = os.path.dirname(__file__)
    json_path = os.path.join(base_dir, "translations.json")
    if os.path.isfile(json_path):
        with open(json_path, "r", encoding="utf-8") as f:
            _translations = json.load(f)
    else:
        print(f"[i18n] translations.json nicht gefunden: {json_path}")
        _translations = {}


def set_language(lang: str):
    """Setzt die aktive Sprache (z.B. 'de', 'en')."""
    global _current_language
    _current_language = lang


def get_language() -> str:
    """Gibt die aktive Sprache zurueck."""
    return _current_language


def get_available_languages() -> list:
    """Gibt die verfuegbaren Sprachen als Liste zurueck."""
    return [("de", "Deutsch"), ("en", "English (US)"), ("ja", "日本語")]


def _t(key: str, **kwargs) -> str:
    """Uebersetzt einen Schluessel in die aktive Sprache.

    Args:
        key: Translations-Schluessel (z.B. "no_file_loaded")
        **kwargs: Platzhalter fuer format() (z.B. _t("songs_count", count=5))

    Returns:
        Uebersetzter Text. Fallback: Deutsch, dann Key selbst.
    """
    entry = _translations.get(key)
    if entry is None:
        # Key nicht gefunden — Key selbst zurueckgeben
        return key

    # Aktuelle Sprache versuchen, Fallback auf Deutsch
    text = entry.get(_current_language) or entry.get("de") or key

    # Platzhalter ersetzen
    if kwargs:
        try:
            text = text.format(**kwargs)
        except (KeyError, IndexError):
            pass  # Fehlende Platzhalter stillschweigend ignorieren

    return text


# Beim Import automatisch laden
_load_translations()
