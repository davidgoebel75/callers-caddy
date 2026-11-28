"""Logik-Module ohne Qt (intern#220, docs/adr/0001-fachpakete-in-src.md).

Ein Modul unter src/caddy/ mit `QT_FREE = True` darf PySide6 nirgends
importieren, auch nicht lazy in einer Funktion. Umgekehrt traegt jedes Modul
ohne PySide6-Import die Marke (ausser __init__.py), sonst prueft es niemand.
Gelesen wird per ast, ohne Import: ein Import wuerde PySide6 sonst schon laden.
"""
import ast
from pathlib import Path

CADDY = Path(__file__).resolve().parents[2] / "src" / "caddy"


def _is_marked(tree):
    return any(isinstance(n, ast.Assign)
               and any(getattr(t, "id", None) == "QT_FREE" for t in n.targets)
               and getattr(n.value, "value", None) is True
               for n in tree.body)


def _qt_import_lines(tree):
    lines = []
    for node in ast.walk(tree):
        names = ([a.name for a in node.names] if isinstance(node, ast.Import)
                 else [node.module or ""] if isinstance(node, ast.ImportFrom)
                 else [])
        if any(n.split(".")[0] == "PySide6" for n in names):
            lines.append(node.lineno)
    return lines


def _qt_free_violations(root):
    """(marked, violations, unmarked): markierte Module, markierte, die trotzdem
    Qt laden, und Module ohne Qt, denen die Marke fehlt."""
    marked, violations, unmarked = [], [], []
    for path in sorted(root.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        qt_lines = _qt_import_lines(tree)
        if _is_marked(tree):
            marked.append(path.name)
            violations += [f"{path.name}:{line}" for line in qt_lines]
        elif not qt_lines and path.name != "__init__.py":
            unmarked.append(path.name)
    return marked, violations, unmarked


def test_qt_freie_module_importieren_kein_pyside6():
    marked, violations, _unmarked = _qt_free_violations(CADDY)
    assert "break_clock.py" in marked
    assert violations == []


def test_modul_ohne_qt_traegt_die_marke():
    _marked, _violations, unmarked = _qt_free_violations(CADDY)
    assert unmarked == [], "QT_FREE = True ergaenzen"


def test_lazy_import_in_funktion_faellt_auf(tmp_path):
    (tmp_path / "logik.py").write_text(
        "QT_FREE = True\n\ndef f():\n    from PySide6.QtCore import QTimer\n",
        encoding="utf-8")
    (tmp_path / "widget.py").write_text("import PySide6\n", encoding="utf-8")
    assert _qt_free_violations(tmp_path) == (["logik.py"], ["logik.py:4"], [])


def test_fehlende_marke_faellt_auf(tmp_path):
    (tmp_path / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "logik.py").write_text("X = 1\n", encoding="utf-8")
    (tmp_path / "widget.py").write_text("import PySide6\n", encoding="utf-8")
    assert _qt_free_violations(tmp_path) == ([], [], ["logik.py"])
