"""Einstellungsdialog und Standardwerte (intern#189).

Der Dialog zeigt auch Einstellungen, die noch nicht in der INI stehen. Wer
nach einer Neuinstallation irgendeine andere Einstellung speichert, darf
diese Zeilen nicht mit ihrem Anzeigewert in die INI schreiben - so landete
display/statusbar_player=false in der INI und der Statusleisten-Player war
ab dem naechsten Start weg.
"""
import ast
import pathlib

from PySide6.QtCore import QSettings

from settings_dialog import SETTINGS_META, SettingsDialog

_SRC = pathlib.Path(__file__).resolve().parents[2] / "src"


def _dialog(tmp_path):
    ini = QSettings(str(tmp_path / "t.ini"), QSettings.IniFormat)
    dlg = SettingsDialog(None, ini)
    dlg._populate_groups_deferred()   # sonst erst per QTimer im Event-Loop
    return ini, dlg


def test_unveraenderter_dialog_schreibt_nichts(qapp, tmp_path):
    ini, dlg = _dialog(tmp_path)
    dlg._on_apply_btn()
    assert ini.allKeys() == []


def test_frische_ini_zeigt_statusleisten_player_an(qapp, tmp_path):
    _, dlg = _dialog(tmp_path)
    row = next(r for r in dlg._rows if r.full_key == "display/statusbar_player")
    assert row.widget.isChecked()


def _code_defaults() -> dict:
    """{key: {Standardwerte}} aus allen settings.value("key", default) in src/."""
    found = {}
    for path in _SRC.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), str(path))
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "value" and len(node.args) >= 2
                    and isinstance(node.args[0], ast.Constant)
                    and "/" in str(node.args[0].value)   # nur QSettings-Keys
                    and isinstance(node.args[1], ast.Constant)):
                found.setdefault(node.args[0].value, set()).add(
                    str(node.args[1].value).lower())
    return found


def _seeded_keys() -> set:
    """Keys, die immer in der INI stehen: _write_ini_defaults() oder die
    mitgelieferte INI. Ihr default im Dialog wird nie angezeigt."""
    tree = ast.parse((_SRC / "main.py").read_text(encoding="utf-8"))
    func = next(n for n in ast.walk(tree)
                if isinstance(n, ast.FunctionDef) and n.name == "_write_ini_defaults")
    keys = {k.value for n in ast.walk(func) if isinstance(n, ast.Dict)
            for k in n.keys if isinstance(k, ast.Constant)}
    ini = QSettings(str(_SRC.parent / "installer" / "callers_caddy_default.ini"),
                    QSettings.IniFormat)
    return keys | set(ini.allKeys())


def _norm(v) -> str:
    """100 == "100", 4.0 == "4" - Zahlen als Zahl vergleichen."""
    s = str(v).lower()
    try:
        return repr(float(s))
    except ValueError:
        return s


def test_jedes_feld_hat_den_standard_aus_dem_code():
    """Der Dialog muss ohne INI-Wert denselben Wert zeigen, den der Code
    annimmt - sonst zeigt er z.B. Zoom 50 %, obwohl 100 % gilt (intern#195)."""
    code = _code_defaults()
    seeded = _seeded_keys()
    wrong = []
    for key, meta in SETTINGS_META.items():
        # ponytail: sieht nur literale Defaults (settings.value("k", 100)); Lesestellen
        # mit Konstante, Keyword oder Helfer fallen durch. Erst mit einer Quelle fuer
        # Standardwerte (intern#146) laesst sich das vollstaendig pruefen.
        if key in seeded or key not in code:
            continue
        # Checkbox ohne default: aus. Sonst ohne default: leer.
        expected = meta.get("default", False if meta.get("widget") == "checkbox" else "")
        diff = {_norm(c) for c in code[key]} - {_norm(expected)}
        if diff:
            wrong.append(f"{key}: default {expected!r}, Code liest {sorted(diff)}")
    assert not wrong, "\n".join(wrong)


def test_statusleisten_player_schaltet_sofort_um(qapp, tmp_path):
    """Aus beim Start, im Dialog an - die Leiste erscheint ohne Neustart."""
    import main
    from PySide6.QtWidgets import QMainWindow

    win = QMainWindow()
    win._settings = QSettings(str(tmp_path / "t.ini"), QSettings.IniFormat)
    win.skin_mgr = None
    win._settings.setValue("display/statusbar_player", "false")
    main.P29MainWindow._setup_statusbar_player(win)
    bar = win._sb_player_bar
    assert not bar.isVisibleTo(win)

    win._settings.setValue("display/statusbar_player", "true")
    main.P29MainWindow._on_settings_applied(win, ["display/statusbar_player"])
    assert win.statusBar().isAncestorOf(bar)
    assert bar.isVisibleTo(win)

    win._settings.setValue("display/statusbar_player", "false")
    main.P29MainWindow._on_settings_applied(win, ["display/statusbar_player"])
    assert not bar.isVisibleTo(win)


def test_zoom_grenzen_im_dialog_wie_im_widget():
    """Dialog erlaubte 300 %, die Widgets nehmen hoechstens 200 % an: 250
    gespeichert, 200 angezeigt (intern#201)."""
    from notes_widget import NotesWidget
    from sequences_widget import SequencesWidget

    for key, widget in (("sequences/zoom_pct", SequencesWidget),
                        ("notes/zoom_pct", NotesWidget)):
        meta = SETTINGS_META[key]
        assert (meta["min"], meta["max"]) == (widget._ZOOM_MIN, widget._ZOOM_MAX), key
