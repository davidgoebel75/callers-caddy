"""SkinManager: fehlende skin.json-Schluessel kommen aus dem default-Skin (intern#107)."""
import json
import os
import re

from skin_manager import SkinManager

SRC_SKINS = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "src", "skins")


def _write_skin(root, name, colors, qss, font_size=None):
    d = root / "skins" / name
    d.mkdir(parents=True)
    data = {"colors": colors}
    if font_size:
        data["font_size"] = font_size
    (d / "skin.json").write_text(json.dumps(data), encoding="utf-8")
    (d / "skin.qss").write_text(qss, encoding="utf-8")


def test_fehlender_schluessel_kommt_aus_default(tmp_path):
    _write_skin(tmp_path, "default", {"a": "#111111", "b": "#222222"}, "", "14px")
    _write_skin(tmp_path, "alt", {"a": "#aaaaaa"}, "X{color:{{a}};border:{{b}};}")
    mgr = SkinManager(str(tmp_path))
    assert mgr.load("alt")
    assert mgr.get_stylesheet() == "X{color:#aaaaaa;border:#222222;}"
    assert mgr.color("b") == "#222222"
    assert mgr.font_size == "14px"


def test_eigener_wert_schlaegt_default(tmp_path):
    _write_skin(tmp_path, "default", {"a": "#111111"}, "")
    _write_skin(tmp_path, "alt", {"a": "#aaaaaa"}, "{{a}}", "12px")
    mgr = SkinManager(str(tmp_path))
    assert mgr.load("alt")
    assert mgr.get_stylesheet() == "#aaaaaa"
    assert mgr.font_size == "12px"


def test_ohne_default_skin_kein_absturz(tmp_path):
    _write_skin(tmp_path, "alt", {"a": "#aaaaaa"}, "{{a}}")
    mgr = SkinManager(str(tmp_path))
    assert mgr.load("alt")
    assert mgr.get_stylesheet() == "#aaaaaa"


def test_mitgelieferte_skins_haben_alle_qss_platzhalter():
    """Jeder mitgelieferte Skin loest seine skin.qss vollstaendig auf."""
    mgr = SkinManager(os.path.dirname(SRC_SKINS))
    for name in mgr.list_skins():
        assert mgr.load(name), name
        rest = re.findall(r"\{\{\w+\}\}", mgr.get_stylesheet())
        assert not rest, f"{name}: {rest}"
        # Mitgelieferte Skins setzen success_text selbst (nicht nur via Fallback)
        with open(os.path.join(SRC_SKINS, name, "skin.json"), encoding="utf-8") as f:
            assert "success_text" in json.load(f)["colors"], name
