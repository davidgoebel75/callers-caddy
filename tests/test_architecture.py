"""Architektur-Regeln (intern#135, Teil von intern#146).

Zwei Regeln, damit neue Lecks zwischen Oberflaeche, Fachlogik und Datenbank
gar nicht erst entstehen:

1. Die Module in QT_FREE_MODULES importieren kein PySide6 — auch nicht in
   einer Funktion — und aus src/ nur andere Module dieser Liste. So faellt
   auch der Umweg ueber ui_helpers oder ein Widget auf.
2. Ausserhalb von song_db.py greift niemand auf ._conn zu. Gemeint ist die
   Verbindung von SongDatabase (db._conn); own_modules Verbindungen einer Klasse
   (self._conn, z. B. in migration/) zaehlen nicht.

Ratsche wie in test_settings_reachable.py: die heutigen Verstoesse gegen
Regel 2 stehen in _KNOWN_CONN_ACCESS. Wer eine Stelle behebt, muss ihren Zaehler
senken — sonst faellt der Test. Die Liste soll schrumpfen, nicht wachsen.
"""
import ast
import pathlib
from collections import Counter

_SRC = pathlib.Path(__file__).resolve().parent.parent / "src"

# Fachlogik und Infrastruktur ohne Qt. Ein neues Modul ohne Qt gehoert hier
# dazu, damit es so bleibt. Bewusst nicht dabei: perf (holt fuer den
# Crash-Header system_report nach, das Qt braucht) und tutorial_definitions
# (baut auf tutorial_engine auf, einem Qt-Overlay).
QT_FREE_MODULES = {
    "audio_engine", "bpm_detector", "button_grid", "call_selection",
    "ceder_lookup", "heads_sides", "i18n", "loop_finder", "mapping_io",
    "pitch_shifter", "rule_definitions", "rule_engine",
    "sequence_filter", "sequence_import", "sequence_mapper",
    "shortcode_parser", "singing_body_detect", "singing_sections",
    "skin_manager", "song_catalog", "song_db", "song_match",
    "subfolder_duplicate_repair", "time_stretcher", "zip_import",
}

# ._conn-Zugriffe ausserhalb von song_db.py, vorgefunden. Abbau: intern#138.
_KNOWN_CONN_ACCESS = {
    "call_selection.py": 1,
    "main.py": 1,
    "notes_widget.py": 1,
    "sequences_widget.py": 1,
    "stats_widget.py": 4,
}


def _parse(path: pathlib.Path) -> ast.AST:
    return ast.parse(path.read_text(encoding="utf-8"), str(path))


def _imports(tree: ast.AST):
    """Oberste Paketnamen aller Imports, auch der in Funktionen."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name.split(".")[0]
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            yield node.module.split(".")[0]


def test_qt_free_modules_stay_qt_free():
    own_modules = {p.stem for p in _SRC.glob("*.py")} | {
        p.name for p in _SRC.iterdir() if (p / "__init__.py").exists()}
    assert QT_FREE_MODULES <= own_modules, (
        f"unbekannte Module in QT_FREE_MODULES: {QT_FREE_MODULES - own_modules}")
    violations = []
    for name in sorted(QT_FREE_MODULES):
        for mod in _imports(_parse(_SRC / f"{name}.py")):
            if mod == "PySide6" or (mod in own_modules and mod not in QT_FREE_MODULES):
                violations.append(f"{name}.py importiert {mod}")
    assert not violations, "\n".join(violations)


def test_conn_only_in_song_db():
    found = Counter()
    for path in _SRC.rglob("*.py"):
        rel = path.relative_to(_SRC)
        if rel.parts[0] == "_fallback" or rel.name == "song_db.py":
            continue
        for node in ast.walk(_parse(path)):
            if (isinstance(node, ast.Attribute) and node.attr == "_conn"
                    and not (isinstance(node.value, ast.Name)
                             and node.value.id == "self")):
                found[rel.as_posix()] += 1
    assert dict(found) == _KNOWN_CONN_ACCESS, (
        f"._conn ausserhalb von song_db.py: {dict(found)}, erwartet "
        f"{_KNOWN_CONN_ACCESS}. Neue Abfragen gehoeren als Methode nach song_db; "
        f"behobene Stellen aus _KNOWN_CONN_ACCESS streichen.")
