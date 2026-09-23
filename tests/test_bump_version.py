"""Tests fuer tools/bump_version.py — der Versions-Bump des Release-Workflows.

GUI-frei. Arbeitet auf einem Mini-Repo im tmp_path, nie auf dem echten.
"""
import importlib.util
from pathlib import Path

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "bump_version", Path(__file__).resolve().parent.parent / "tools" / "bump_version.py"
)
bump_version = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(bump_version)


def _repo(tmp_path, unreleased="## (Unreleased — seit 0.159)\n\n### Verbesserungen\n- **Etwas.** Text.\n"):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text('"""Doku."""\n\n__version__ = "0.158"\n\nimport sys\n', encoding="utf-8")
    (tmp_path / "CHANGELOG.md").write_text(
        f"# Changelog\n\n---\n\n{unreleased}\n## 0.159 — Alt (2026-09-15)\n\n- **Aeltestes.**\n",
        encoding="utf-8",
    )
    return tmp_path


def test_zaehlt_oberste_veroeffentlichte_version_hoch(tmp_path):
    root = _repo(tmp_path)
    assert bump_version.bump(title="Neu", date="2026-09-22", root=root) == "0.160"
    changelog = (root / "CHANGELOG.md").read_text(encoding="utf-8")
    assert "## 0.160 — Neu (2026-09-22)" in changelog
    assert "Unreleased" not in changelog
    # Beide Pflicht-Stellen, nicht nur der Changelog
    assert '__version__ = "0.160"' in (root / "src" / "main.py").read_text(encoding="utf-8")


def test_stellenzahl_bleibt_erhalten():
    # 0.159 -> 0.160, nicht 0.16
    assert bump_version.next_version("## 0.159 — x (2026-09-15)") == "0.160"
    assert bump_version.next_version("## 0.99 — x (2026-01-01)") == "0.100"


def test_erzwungene_version_gewinnt(tmp_path):
    root = _repo(tmp_path)
    assert bump_version.bump(version="2.0", title="Launch", date="2026-10-01", root=root) == "2.0"
    assert "## 2.0 — Launch (2026-10-01)" in (root / "CHANGELOG.md").read_text(encoding="utf-8")


def test_leerer_unreleased_abschnitt_bricht_ab(tmp_path):
    root = _repo(tmp_path, unreleased="## (Unreleased — seit 0.159)\n")
    with pytest.raises(SystemExit):
        bump_version.bump(root=root)


def test_fehlender_unreleased_abschnitt_bricht_ab(tmp_path):
    root = _repo(tmp_path, unreleased="")
    with pytest.raises(SystemExit):
        bump_version.bump(root=root)


def test_check_schreibt_nichts(tmp_path):
    root = _repo(tmp_path)
    vorher = (root / "CHANGELOG.md").read_text(encoding="utf-8")
    assert bump_version.bump(title="Probe", write=False, root=root) == "0.160"
    assert (root / "CHANGELOG.md").read_text(encoding="utf-8") == vorher
