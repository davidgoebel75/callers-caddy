"""Logik-Module ohne Qt (intern#220, docs/adr/0001-fachpakete-in-src.md).

Ein Modul unter src/caddy/ mit `QT_FREE = True` darf PySide6 nirgends
importieren, auch nicht lazy in einer Funktion. Gelesen wird per ast, ohne
Import: ein Import wuerde PySide6 sonst schon laden.
"""
import ast
from pathlib import Path

CADDY = Path(__file__).resolve().parents[2] / "src" / "caddy"


def _qt_free_violations(root):
    """(marked, violations): markierte Module und die, die trotzdem Qt laden."""
    marked, violations = [], []
    for path in sorted(root.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        if not any(isinstance(n, ast.Assign)
                   and any(getattr(t, "id", None) == "QT_FREE" for t in n.targets)
                   and getattr(n.value, "value", None) is True
                   for n in tree.body):
            continue
        marked.append(path.name)
        for node in ast.walk(tree):
            names = ([a.name for a in node.names] if isinstance(node, ast.Import)
                     else [node.module or ""] if isinstance(node, ast.ImportFrom)
                     else [])
            if any(n.split(".")[0] == "PySide6" for n in names):
                violations.append(f"{path.name}:{node.lineno}")
    return marked, violations


def test_qt_freie_module_importieren_kein_pyside6():
    marked, violations = _qt_free_violations(CADDY)
    assert "break_clock.py" in marked
    assert violations == []


def test_lazy_import_in_funktion_faellt_auf(tmp_path):
    (tmp_path / "logik.py").write_text(
        "QT_FREE = True\n\ndef f():\n    from PySide6.QtCore import QTimer\n",
        encoding="utf-8")
    (tmp_path / "widget.py").write_text("import PySide6\n", encoding="utf-8")
    assert _qt_free_violations(tmp_path) == (["logik.py"], ["logik.py:4"])
