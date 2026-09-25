"""Erreichbarkeit der INI-Einstellungen im Einstellungen-Dialog.

Der Dialog baut seine Zeilen aus QSettings.childKeys() — er zeigt also nur,
was in der INI TATSAECHLICH steht. Ein Key, den der Code bloss mit Default
liest (`settings.value(key, "top")`) und nie schreibt, fehlt auf einer
frischen Installation in der INI und ist damit unsichtbar, egal wie schoen
sein SETTINGS_META-Eintrag ist. Genau so war notes/insert_position zuerst
eingebaut (intern#96).

Zwei Richtungen, beide als Ratsche mit Baseline: neue Verstoesse lassen den
Test fallen, die bekannten Altlasten stehen namentlich unten. Wer eine davon
behebt, muss sie aus der Baseline streichen — sonst faellt der Test ebenfalls.
Die Listen sollen schrumpfen, nicht wachsen.
"""
import ast
import configparser
import pathlib

import pytest

from settings_dialog import (SETTINGS_META, _EXCLUDED_KEYS, _EXCLUDED_SECTIONS,
                             _EXCLUDED_SUFFIX)

_REPO = pathlib.Path(__file__).resolve().parent.parent
_SRC = _REPO / "src"
_DEFAULT_INI = _REPO / "installer" / "callers_caddy_default.ini"

# Keys mit SETTINGS_META-Eintrag, die nie in der INI landen — der Dialog zeigt
# sie auf einer frischen Installation also nicht. Vorgefunden, nicht neu.
_UNGESAET_BEKANNT = {
    "audio/alert_sound_path",
    "audio/alert_volume",
    "display/countdown_enabled",
    "display/statusbar_player",
    "network/ceder_lookup_enabled",
    "playlist/patter_fill_type",
    "sequences/auto_sync_program",
    "sequences/only_program_default",
    "sort/default_mode",
}

# Keys, die der Dialog listet, sobald sie in der INI stehen, aber ohne
# SETTINGS_META — also mit rohem Key als Beschriftung und Textfeld statt
# passendem Bedienelement. Wer einen davon bewusst verstecken will, traegt ihn
# in _EXCLUDED_KEYS ein (statt ihn hier stehen zu lassen).
_OHNE_META_BEKANNT = {
    "lyrics/auto_width",
    "rules/streamdeck_seeded_v1",   # interner Marker, kein Nutzer-Schalter
    "sequences/universal_import_dir",
    "sort/random_tiebreaker",
}


def _settings_calls(attr: str):
    """Alle QSettings-Keys, die irgendwo in src/ als Literal auftauchen.

    Liefert (feste Keys, Praefixe aus f-Strings). Die Praefixe braucht es fuer
    Key-Familien wie paths/music_dir_{slot}, die zur Laufzeit entstehen.
    Der Filter auf "/" trennt QSettings von den vielen gleichnamigen
    Qt-Aufrufen (QSpinBox.setValue & Co.).
    """
    keys, prefixes = set(), set()
    for path in _SRC.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), str(path))
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == attr and node.args):
                continue
            arg = node.args[0]
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                if "/" in arg.value:
                    keys.add(arg.value)
            elif isinstance(arg, ast.JoinedStr) and arg.values:
                head = arg.values[0]
                if isinstance(head, ast.Constant) and "/" in str(head.value):
                    prefixes.add(head.value)
    return keys, prefixes


def _defaults_table() -> set:
    """Keys aus P29MainWindow._write_ini_defaults() — die kanonische Saat."""
    tree = ast.parse((_SRC / "main.py").read_text(encoding="utf-8"), "main.py")
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "_write_ini_defaults":
            return {k.value for sub in ast.walk(node) if isinstance(sub, ast.Dict)
                    for k in sub.keys
                    if isinstance(k, ast.Constant) and isinstance(k.value, str)}
    pytest.fail("_write_ini_defaults() nicht gefunden — Scan anpassen.")


def _default_ini_keys() -> set:
    cp = configparser.ConfigParser()
    cp.read(_DEFAULT_INI, encoding="utf-8")
    return {f"{sec}/{key}" for sec in cp.sections() for key in cp[sec]}


def _is_excluded(full_key: str) -> bool:
    section, _, key = full_key.partition("/")
    return (section in _EXCLUDED_SECTIONS
            or section.endswith(_EXCLUDED_SUFFIX)
            or key in _EXCLUDED_KEYS.get(section, set()))


@pytest.fixture(scope="module")
def gesaet() -> set:
    """Keys, die auf einer frischen Installation in der INI landen."""
    written, prefixes = _settings_calls("setValue")
    fixed = _defaults_table() | _default_ini_keys() | written

    class _Seeded(set):
        def __contains__(self, key):
            return (set.__contains__(self, key)
                    or any(key.startswith(p) for p in prefixes))

    return _Seeded(fixed)


def test_jeder_meta_eintrag_landet_auch_in_der_ini(gesaet):
    fehlend = {k for k in SETTINGS_META if k not in gesaet}
    neu = fehlend - _UNGESAET_BEKANNT
    assert not neu, (
        "SETTINGS_META-Eintrag ohne Saat - der Dialog zeigt die Zeile nie. "
        "Key in _write_ini_defaults() aufnehmen: " + ", ".join(sorted(neu)))
    behoben = _UNGESAET_BEKANNT - fehlend
    assert not behoben, (
        "Behoben, aber noch in der Baseline - bitte aus _UNGESAET_BEKANNT "
        "streichen: " + ", ".join(sorted(behoben)))


def test_jeder_sichtbare_ini_key_hat_eine_beschriftung(gesaet):
    gelesen, _ = _settings_calls("value")
    sichtbar = {k for k in gelesen if k in gesaet and not _is_excluded(k)}
    fehlend = sichtbar - set(SETTINGS_META)
    neu = fehlend - _OHNE_META_BEKANNT
    assert not neu, (
        "Key steht in der INI und im Dialog, hat aber kein SETTINGS_META - "
        "erscheint als rohes Textfeld. Entweder SETTINGS_META ergaenzen oder "
        "in _EXCLUDED_KEYS verstecken: " + ", ".join(sorted(neu)))
    behoben = _OHNE_META_BEKANNT - fehlend
    assert not behoben, (
        "Behoben, aber noch in der Baseline - bitte aus _OHNE_META_BEKANNT "
        "streichen: " + ", ".join(sorted(behoben)))
