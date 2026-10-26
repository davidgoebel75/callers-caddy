"""Verzeichnis der INI-Schluessel mit Standardwert (intern#144, Teil von #146).

`caddy/settings/ini_keys.py` ist die einzige Quelle fuer Standardwerte der
umgestellten Module und fuer die Saat von `_write_ini_defaults()`.
"""
import ast
import configparser
import pathlib

from PySide6.QtCore import QSettings

from caddy.settings import ini_keys
from settings_dialog import SETTINGS_META

_REPO = pathlib.Path(__file__).resolve().parents[2]
_SRC = _REPO / "src"
_DEFAULT_INI = _REPO / "installer" / "callers_caddy_default.ini"

# So sah das Dict in _write_ini_defaults() vor intern#144 aus (develop @ 5594fe4):
# Reihenfolge und Zeichenketten muessen Zeichen fuer Zeichen gleich bleiben.
_SAAT_VORHER = {
    "player/timer_warn1": "240",
    "player/timer_warn2": "300",
    "loop/crossfade_ms": "46",
    "loop/finder_window_mode": "pct",
    "debug/performance_logging": "false",
    "audio/min_volume": "0.0",
    "audio/mmcss_priority": "true",
    "audio/log_underflows": "true",
    "audio/wasapi_exclusive": "false",
    "audio/secondary_device": "",
    "audio/secondary_volume": "80",
    "feedback/enabled": "false",
    "notes/insert_position": "top",
    "notes/first_note_factor": "4.0",
    "lyrics/dynamic_invert_enabled": "false",
    "lyrics/dynamic_invert_mode": "",
    "lyrics/text_jump_offset": "-4",
    "lyrics/dynamic_swap_offset": "-4",
    "lyrics/reading_position_pct": "30",
    "lyrics/reading_band_enabled": "true",
    "lyrics/reading_band_height": "20",
    "lyrics/reading_band_opacity": "30",
    "lyrics/reading_band_countdown": "true",
    "lyrics/reading_band_countdown_beats": "8",
    "sequences/show_hidden_on_start": "false",
}


def _norm(v) -> str:
    s = str(v).lower()
    try:
        return repr(float(s))
    except ValueError:
        return s


def test_saat_ist_zeichen_fuer_zeichen_wie_vorher():
    assert list(ini_keys.seed_items().items()) == list(_SAAT_VORHER.items())
    assert ini_keys.seed_keys() == set(_SAAT_VORHER)


def test_typ_passt_zum_standardwert():
    for k, e in ini_keys.KEYS.items():
        assert type(e.default) is e.type, k


def test_schluessel_form_und_eindeutigkeit():
    for k, e in ini_keys.KEYS.items():
        assert e.key == k
        sektion, sep, name = k.partition("/")
        assert sep and sektion and name and "/" not in name, k


# Bekannte Abweichung (nicht vereinheitlicht, siehe abweichungen-fuer-david.md, #144):
# Dialog zeigt "1", der Code kennt "" = noch nicht gewaehlt (fragt beim ersten Mal).
_DIALOG_ABWEICHUNG = {"lyrics/dynamic_mode"}


def test_gemeinsame_schluessel_mit_dialog_gleicher_standard():
    for k, e in ini_keys.KEYS.items():
        meta = SETTINGS_META.get(k)
        if meta is None or k in _DIALOG_ABWEICHUNG:
            continue
        if "default" in meta:
            expected = meta["default"]
        elif meta.get("widget") == "checkbox":
            expected = False
        else:
            continue
        assert _norm(e.default) == _norm(expected), k


def test_gemeinsame_schluessel_mit_mitgelieferter_ini_gleicher_standard():
    cp = configparser.ConfigParser()
    cp.read(_DEFAULT_INI, encoding="utf-8")
    for sec in cp.sections():
        for name, raw in cp[sec].items():
            k = f"{sec}/{name}"
            if k in ini_keys.KEYS:
                assert _norm(ini_keys.default(k)) == _norm(raw), k


def test_literal_schluessel_im_code_stehen_im_verzeichnis():
    """Tippfehler-Schutz: ini_keys.get(.., "k") / ini_keys.default("k")."""
    unbekannt = []
    for path in _SRC.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), str(path))
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and isinstance(node.func.value, ast.Name)
                    and node.func.value.id == "ini_keys"
                    and node.func.attr in ("get", "default")):
                continue
            idx = 1 if node.func.attr == "get" else 0
            if len(node.args) > idx and isinstance(node.args[idx], ast.Constant):
                if node.args[idx].value not in ini_keys.KEYS:
                    unbekannt.append(f"{path.name}: {node.args[idx].value}")
    assert not unbekannt, unbekannt


def test_get_wie_settings_value(tmp_path):
    s = QSettings(str(tmp_path / "t.ini"), QSettings.IniFormat)
    assert ini_keys.get(s, "lyrics/text_jump_offset") == -4
    s.setValue("lyrics/text_jump_offset", "7")
    assert ini_keys.get(s, "lyrics/text_jump_offset") == "7"
    assert ini_keys.get(s, "lyrics/auto_size", type=bool) is True
    s.setValue("lyrics/auto_size", "false")
    assert ini_keys.get(s, "lyrics/auto_size", type=bool) is False


def test_pfade_slots_standard():
    assert [ini_keys.default(f"paths/music_dir_{i}") for i in (1, 2, 3, 4)] == [
        "music", "", "", ""]
    assert ini_keys.default("paths/import_dir") == "neu"
    assert ini_keys.default("paths/lyrics_dir") == "lyrics"
    assert ini_keys.default("paths/playlist_dir") == "playlists"


# ---- Charakterisierung der Piloten (Verhalten bleibt wie vor intern#144) ----

def _lyrics_stub(tmp_path, **werte):
    from types import SimpleNamespace
    s = QSettings(str(tmp_path / "t.ini"), QSettings.IniFormat)
    for k, v in werte.items():
        s.setValue(k.replace("__", "/"), v)
    return SimpleNamespace(_settings=s, _TIMING_OFFSET_LIMIT=10,
                           _TIMING_OFFSET_DEFAULT=-4, _reading_band=None,
                           _band_countdown=None)


def test_timing_fehlend_minus4_unlesbar_0(tmp_path):
    from lyrics_widget import LyricsWidget
    w = _lyrics_stub(tmp_path)
    LyricsWidget.reload_timing_settings(w)
    assert (w._text_jump_offset, w._dynamic_swap_offset) == (-4, -4)
    w = _lyrics_stub(tmp_path, lyrics__text_jump_offset="muell")
    LyricsWidget.reload_timing_settings(w)
    assert w._text_jump_offset == 0


def test_lesebalken_fehlend_und_unlesbar_standard(tmp_path):
    from lyrics_widget import LyricsWidget
    for w in (_lyrics_stub(tmp_path),
              _lyrics_stub(tmp_path, lyrics__reading_band_height="muell")):
        LyricsWidget.reload_reading_settings(w)
        assert w._reading_band_height_pct == 20
        assert w._reading_band_opacity_pct == 30
        assert w._SYNC_ANCHOR_VIEWPORT_FRAC == 0.3
        assert w._reading_band_enabled is True
        assert w._band_countdown_beats == 8


def test_pathmanager_leere_ini(tmp_path):
    from path_manager import PathManager
    pm = PathManager(QSettings(str(tmp_path / "t.ini"), QSettings.IniFormat))
    base = pm.app_dir
    import os
    assert pm.music_dir == os.path.normpath(os.path.join(base, "music"))
    assert pm.import_dir == os.path.normpath(os.path.join(base, "neu"))
    assert pm.lyrics_dir == os.path.normpath(os.path.join(base, "lyrics"))
    assert pm.playlist_dir == os.path.normpath(os.path.join(base, "playlists"))
    assert [pm.get_music_dir_raw(i) for i in (2, 3, 4)] == ["", "", ""]
    assert pm.find_free_music_slot() == 2


def test_seed_standard_ist_aus_und_nur_markierte_werden_gesaet():
    assert ini_keys.IniKey("a/b", str, "").seed is False
    assert "lyrics/dynamic_mode" not in ini_keys.seed_keys()
    assert ini_keys.default("lyrics/dynamic_mode") == ""
    assert "player/timer_warn1" in ini_keys.seed_keys()
