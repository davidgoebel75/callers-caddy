"""Uebersetzungen im Einstellungen-Dialog.

Der Dialog zeigt jeden INI-Key als Zeile — auch neue, ohne dass jemand den
Dialog anfasst. Die Beschriftung sucht er zuerst unter
`setting_label_<sektion>_<key>` in translations.json, sonst nimmt er das
(meist deutsche) SETTINGS_META["label"], sonst den rohen Key. Fehlt die
Uebersetzung, sieht ein englischer Nutzer also Deutsch oder `auto_width`
(intern#124). Dasselbe gilt fuer `setting_tip_*` und fest verdrahtete
Combobox-Auswahlen.

Wichtig: `_t()` faellt fuer fehlende Sprachen still auf Deutsch zurueck. Der
Test prueft deshalb direkt in der Datei, dass de, en UND ja befuellt sind.

Ratsche wie in test_settings_reachable.py: neue Luecken lassen den Test
fallen, die vorgefundenen stehen namentlich unten. Wer eine schliesst, muss
sie aus der Baseline streichen — die Listen sollen schrumpfen.
"""
import ast
import json
import pathlib

import pytest

from settings_dialog import SETTINGS_META, _is_excluded_key
from test_settings_reachable import _is_excluded, _saat, _settings_calls

_REPO = pathlib.Path(__file__).resolve().parents[2]
_SRC = _REPO / "src"
_LANGS = ("de", "en", "ja")

# Sichtbare Keys ohne vollstaendiges setting_label_* (de/en/ja). Vorgefunden.
_LABEL_FEHLT_BEKANNT = set()

# SETTINGS_META-Eintraege mit festem "tooltip", aber ohne vollstaendiges
# setting_tip_* (de/en/ja). Vorgefunden.
_TIP_FEHLT_BEKANNT = set()

# Combobox-Keys, deren Auswahltexte bewusst NICHT uebersetzt werden.
_CHOICES_OHNE_I18N_ERLAUBT = {
    "display/language",   # Sprachen stehen in ihrer eigenen Sprache
}


def _translations() -> dict:
    return json.loads((_SRC / "translations.json").read_text(encoding="utf-8"))


def _fehlt(tr: dict, t_key: str) -> bool:
    entry = tr.get(t_key) or {}
    return not all(entry.get(lang) for lang in _LANGS)


def _sichtbare_keys() -> set:
    """SETTINGS_META, die ganze Saat (Default-INI, _write_ini_defaults) plus
    alle im Code gelesenen oder geschriebenen, gesaeten, nicht versteckten
    Keys. Die Saat zaehlt direkt: sie steht in der INI, auch wenn der Code sie
    nicht als Literal liest (paths/playlist_dir ueber _INI_KEYS). Geschriebene
    zaehlen mit: was per setValue in der INI landet, zeigt der Dialog auch
    dann, wenn es nur mit Default gelesen wird oder gar nicht."""
    written, prefixes = _settings_calls("setValue")
    saat = _saat()
    fixed = saat | written

    def gesaet(k):
        return k in fixed or any(k.startswith(p) for p in prefixes)

    gelesen, _ = _settings_calls("value")
    keys = set(SETTINGS_META) | {k for k in saat | gelesen | written
                                  if gesaet(k) and not _is_excluded(k)}
    return {k for k in keys if not _is_excluded_key(*k.split("/", 1))}


def _i18n_key(prefix: str, full_key: str) -> str:
    section, key = full_key.split("/", 1)
    return f"{prefix}_{section}_{key}"


def _ratsche(fehlend: set, baseline: set, was: str, name: str):
    neu = fehlend - baseline
    assert not neu, (
        f"{was} fehlt in translations.json (de/en/ja) - der Dialog zeigt "
        f"sonst Deutsch oder den rohen Key: " + ", ".join(sorted(neu)))
    behoben = baseline - fehlend
    assert not behoben, (
        f"Behoben, aber noch in der Baseline - bitte aus {name} streichen: "
        + ", ".join(sorted(behoben)))


def test_jeder_sichtbare_key_hat_ein_uebersetztes_label():
    tr = _translations()
    fehlend = {k for k in _sichtbare_keys()
               if _fehlt(tr, _i18n_key("setting_label", k))}
    _ratsche(fehlend, _LABEL_FEHLT_BEKANNT, "setting_label_*",
             "_LABEL_FEHLT_BEKANNT")


def test_jeder_meta_tooltip_ist_uebersetzt():
    tr = _translations()
    fehlend = {k for k, meta in SETTINGS_META.items()
               if meta.get("tooltip")
               and _fehlt(tr, _i18n_key("setting_tip", k))}
    _ratsche(fehlend, _TIP_FEHLT_BEKANNT, "setting_tip_*",
             "_TIP_FEHLT_BEKANNT")


def _zur_laufzeit_befuellte_comboboxen() -> set:
    """Keys, fuer die _build_widget eigene (uebersetzte) choices baut —
    erkannt an `self.full_key == "<key>"` in _build_widget."""
    tree = ast.parse((_SRC / "settings_dialog.py").read_text(encoding="utf-8"))
    build = next((n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)
                  and n.name == "_build_widget"), None)
    if build is None:
        pytest.fail("_build_widget() nicht gefunden — Scan anpassen.")
    keys = set()
    for node in ast.walk(build):
        if (isinstance(node, ast.Compare)
                and isinstance(node.left, ast.Attribute)
                and node.left.attr == "full_key"):
            keys |= {c.value for c in node.comparators
                     if isinstance(c, ast.Constant) and isinstance(c.value, str)}
    if not keys:
        pytest.fail("Keine full_key-Vergleiche gefunden — Scan anpassen.")
    return keys


def test_combobox_auswahl_wird_uebersetzt():
    dynamisch = _zur_laufzeit_befuellte_comboboxen()
    fest = {k for k, meta in SETTINGS_META.items()
            if meta.get("widget") == "combobox" and meta.get("choices")
            and k not in dynamisch and k not in _CHOICES_OHNE_I18N_ERLAUBT}
    assert not fest, (
        "Combobox mit fest verdrahteten Auswahltexten - in _build_widget per "
        "_t() uebersetzen (Muster lyrics/dynamic_mode): " + ", ".join(sorted(fest)))
