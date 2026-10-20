"""Architektur-Regeln (intern#135, Teil von intern#146).

Vier Regeln, damit neue Lecks zwischen Oberflaeche, Fachlogik und Datenbank
gar nicht erst entstehen:

1. Die Module in QT_FREE_MODULES importieren kein PySide6 — auch nicht in
   einer Funktion — und aus src/ nur andere Module dieser Liste. So faellt
   auch der Umweg ueber ui_helpers oder ein Widget auf. Ein Import aus dem
   Dach-Paket caddy zaehlt nur, wenn das Modul QT_FREE = True traegt.
2. Ausserhalb von song_db.py greift niemand auf ._conn zu. Gemeint ist die
   Verbindung von SongDatabase (db._conn); eigene Verbindungen einer Klasse
   (self._conn, z. B. in migration/) zaehlen nicht.
3. sqlite3 wird nur in song_db.py, song_db_schema.py, song_db_sequences.py,
   migration/ und tools/ importiert — auch nicht in einer Funktion. Wer sonst
   eine eigene Verbindung oeffnet, geht an song_db vorbei.
4. Sync-Point-Schluessel ("lyric_sync_...") und die Body-Laenge 448 entstehen nur in
   caddy/lyrics/sync_keys.py (intern#140). Alle anderen bauen sie damit.

Ratsche wie in test_settings_reachable.py: die heutigen Verstoesse gegen
Regel 2 und 3 stehen in _KNOWN_CONN_ACCESS bzw. _KNOWN_SQLITE_IMPORTS. Wer eine
Stelle behebt, muss ihren Zaehler senken — sonst faellt der Test. Die Listen
sollen schrumpfen, nicht wachsen.
"""
import ast
import pathlib
import re
from collections import Counter

_SRC = pathlib.Path(__file__).resolve().parents[2] / "src"

# Fachlogik und Infrastruktur ohne Qt. Ein neues Modul ohne Qt gehoert hier
# dazu, damit es so bleibt. Bewusst nicht dabei: perf (holt fuer den
# Crash-Header system_report nach, das Qt braucht) und tutorial_definitions
# (baut auf tutorial_engine auf, einem Qt-Overlay).
QT_FREE_MODULES = {
    "audio_favorites",
    "audio_engine", "bpm_detector", "button_grid", "call_selection",
    "ceder_lookup", "heads_sides", "i18n", "loop_finder", "loop_windows",
    "lyrics_files",
    "mapping_io",
    "pitch_shifter", "program_selection", "rule_definitions", "rule_engine",
    "sequence_filter", "sequence_import", "sequence_mapper",
    "reading_band_path",
    "shortcode_parser", "singing_body_detect", "singing_sections",
    "skin_manager", "song_catalog", "song_db", "song_types", "song_db_potential",
    "song_db_schema", "song_db_sequences", "song_match",
    "subfolder_duplicate_repair", "sync_point_lines", "time_stretcher",
    "zip_import",
}

# ._conn-Zugriffe ausserhalb von song_db.py, vorgefunden. Abbau: intern#138.
_KNOWN_CONN_ACCESS = {
}

# Hier darf sqlite3 importiert werden (Pfade relativ zu src/).
_SQLITE_ALLOWED = ("song_db.py", "song_db_schema.py", "song_db_sequences.py",
                   "migration/", "tools/")

# sqlite3-Importe ausserhalb davon, vorgefunden. Abbau: intern#139.
_KNOWN_SQLITE_IMPORTS = {
    "potential_widget.py": 6,
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


def _is_qt_free_caddy_module(module: str) -> bool:
    """`caddy.<paket>.<modul>` mit `QT_FREE = True` (Markierung prueft test_qt_free.py).
    caddy ist kein Freibrief: nur markierte Module zaehlen als Qt-frei."""
    path = _SRC.joinpath(*module.split(".")).with_suffix(".py")
    if not path.is_file():
        return False
    return any(isinstance(n, ast.Assign)
               and any(getattr(t, "id", None) == "QT_FREE" for t in n.targets)
               and getattr(n.value, "value", None) is True
               for n in _parse(path).body)


def _caddy_imports(tree: ast.AST):
    """Volle Modulnamen der Imports aus dem Dach-Paket caddy."""
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and not node.level \
                and node.module.split(".")[0] == "caddy":
            yield node.module
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] == "caddy":
                    yield alias.name


def test_qt_free_modules_stay_qt_free():
    own_modules = {p.stem for p in _SRC.glob("*.py")} | {
        p.name for p in _SRC.iterdir() if (p / "__init__.py").exists()}
    assert QT_FREE_MODULES <= own_modules, (
        f"unbekannte Module in QT_FREE_MODULES: {QT_FREE_MODULES - own_modules}")
    violations = []
    for name in sorted(QT_FREE_MODULES):
        tree = _parse(_SRC / f"{name}.py")
        for mod in _imports(tree):
            if mod == "caddy":
                continue    # unten genauer: nur QT_FREE-Module des Dachs
            if mod == "PySide6" or (mod in own_modules and mod not in QT_FREE_MODULES):
                violations.append(f"{name}.py importiert {mod}")
        for mod in _caddy_imports(tree):
            if not _is_qt_free_caddy_module(mod):
                violations.append(f"{name}.py importiert {mod} (nicht QT_FREE)")
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


def test_sqlite_only_in_song_db():
    found = Counter()
    for path in _SRC.rglob("*.py"):
        rel = path.relative_to(_SRC).as_posix()
        if rel.startswith("_fallback/") or rel.startswith(_SQLITE_ALLOWED):
            continue
        for mod in _imports(_parse(path)):
            if mod == "sqlite3":
                found[rel] += 1
    assert dict(found) == _KNOWN_SQLITE_IMPORTS, (
        f"sqlite3-Importe ausserhalb von song_db: {dict(found)}, erwartet "
        f"{_KNOWN_SQLITE_IMPORTS}. Abfragen gehoeren als Methode nach "
        f"song_db; behobene Stellen aus _KNOWN_SQLITE_IMPORTS streichen.")

_SYNC_KEYS = "caddy/lyrics/sync_keys.py"
# Schluessel-Fragmente (auch in SQL- und Regex-Texten): "lyric_sync_",\n# "lyric_sync_m1_l1_%", "lyric_sync_m{...}", "lyric_sync_m(\\d+)"; nicht
# die Uebersetzungs-Schluessel (lyric_sync_move_line, lyric_sync_detect_*).
_SYNC_KEY_LITERAL = re.compile(r"lyric_sync_(m(\d|\()|%|['\"]|$)")


def test_sync_keys_and_body_length_only_in_sync_keys():
    found = []
    for path in _SRC.rglob("*.py"):
        rel = path.relative_to(_SRC).as_posix()
        if rel.startswith("_fallback/") or rel == _SYNC_KEYS:
            continue
        tree = _parse(path)
        docstrings = {id(n.body[0].value) for n in ast.walk(tree)
                      if isinstance(n, (ast.Module, ast.ClassDef, ast.FunctionDef,
                                        ast.AsyncFunctionDef))
                      and n.body and isinstance(n.body[0], ast.Expr)}
        for node in ast.walk(tree):
            if not isinstance(node, ast.Constant) or id(node) in docstrings:
                continue
            if isinstance(node.value, str) and _SYNC_KEY_LITERAL.search(node.value):
                found.append(f"{rel}:{node.lineno} Schluessel {node.value!r}")
            # tools/ sind Experimente mit eigenen Konstanten, nicht Teil der App
            elif (node.value == 448 and type(node.value) is int
                    and not rel.startswith("tools/")):
                found.append(f"{rel}:{node.lineno} Body-Laenge 448")
    assert not found, (
        "Schluessel und Body-Laenge gehoeren nach caddy/lyrics/sync_keys.py "
        "(make_key, like_pattern, SINGING_BODY_BEATS):\n" + "\n".join(found))
