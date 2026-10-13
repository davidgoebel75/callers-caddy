"""Tests fuer tools/bump_version.py — der Versions-Bump des Release-Workflows.

GUI-frei. Arbeitet auf einem Mini-Repo im tmp_path, nie auf dem echten.
"""
import importlib.util
from pathlib import Path

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "bump_version", Path(__file__).resolve().parents[2] / "tools" / "bump_version.py"
)
bump_version = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(bump_version)


def _repo(tmp_path, unreleased="## (Unreleased — seit 0.159)\n\n### Verbesserungen\n- **Etwas.** Text.\n",
          released="## 0.159 — Alt (2026-09-15)\n\n- **Aeltestes.**\n"):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text('"""Doku."""\n\n__version__ = "0.158"\n\nimport sys\n', encoding="utf-8")
    (tmp_path / "CHANGELOG.md").write_text(
        f"# Changelog\n\n---\n\n{unreleased}\n{released}",
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
    assert bump_version.bump(version="0.165", title="Sprung", date="2026-10-01", root=root) == "0.165"
    assert "## 0.165 — Sprung (2026-10-01)" in (root / "CHANGELOG.md").read_text(encoding="utf-8")


def test_unbekanntes_nummernformat_bricht_ab(tmp_path):
    # Wie die Bloecke ab 2.0 heissen, ist offen (intern#203) — bis dahin kein stilles Raten.
    root = _repo(tmp_path)
    before = (root / "CHANGELOG.md").read_text(encoding="utf-8")
    with pytest.raises(SystemExit, match="Nummernformat"):
        bump_version.bump(version="2.0", title="Launch", root=root)
    assert (root / "CHANGELOG.md").read_text(encoding="utf-8") == before


def test_bump_im_laufenden_block_lagert_nichts_aus(tmp_path):
    root = _repo(tmp_path, released="## 0.160 — Alt (2026-09-15)\n\n- **Aeltestes.**\n")
    assert bump_version.bump(root=root) == "0.161"
    assert "## 0.160 — Alt" in (root / "CHANGELOG.md").read_text(encoding="utf-8")
    assert not (root / "docs" / "changelog").exists()


def test_neuer_block_lagert_den_vollen_aus(tmp_path):
    root = _repo(tmp_path, released=(
        "## 0.169 — Neun (2026-09-15)\n\n- **Neun.**\n\n---\n\n"
        "## 0.160 — Null (2026-09-01)\n\n- **Null.**\n"
    ))
    assert bump_version.bump(title="Neu", date="2026-09-22", root=root) == "0.170"
    changelog = (root / "CHANGELOG.md").read_text(encoding="utf-8")
    archive = (root / "docs" / "changelog" / "0.160-0.169.md").read_text(encoding="utf-8")
    # Die neue Version bleibt stehen, damit der naechste Bump eine Nummer findet
    assert "## 0.170 — Neu (2026-09-22)" in changelog
    assert bump_version.next_version(changelog) == "0.171"
    assert "## 0.169" not in changelog and "## 0.160" not in changelog
    assert changelog.endswith(
        "## Ältere Versionen\n\n- [0.160–0.169](docs/changelog/0.160-0.169.md)\n"
    )
    # Texte unveraendert, neueste zuerst
    assert archive == (
        "# Callers Caddy — Changelog 0.160–0.169\n\n"
        "## 0.169 — Neun (2026-09-15)\n\n- **Neun.**\n\n---\n\n"
        "## 0.160 — Null (2026-09-01)\n\n- **Null.**\n"
    )


def test_verzeichnis_nennt_alle_archivdateien(tmp_path):
    root = _repo(tmp_path, released="## 0.169 — Neun (2026-09-15)\n\n- **Neun.**\n")
    older = root / "docs" / "changelog"
    older.mkdir(parents=True)
    (older / "0.90-0.99.md").write_text("# Alt\n", encoding="utf-8")
    (older / "0.00-0.09.md").write_text("# Alt\n", encoding="utf-8")
    bump_version.bump(root=root)
    assert (root / "CHANGELOG.md").read_text(encoding="utf-8").endswith(
        "- [0.160–0.169](docs/changelog/0.160-0.169.md)\n"
        "- [0.90–0.99](docs/changelog/0.90-0.99.md)\n"
        "- [0.00–0.09](docs/changelog/0.00-0.09.md)\n"
    )


def test_check_lagert_nichts_aus(tmp_path):
    root = _repo(tmp_path, released="## 0.169 — Neun (2026-09-15)\n\n- **Neun.**\n")
    before = (root / "CHANGELOG.md").read_text(encoding="utf-8")
    assert bump_version.bump(write=False, root=root) == "0.170"
    assert (root / "CHANGELOG.md").read_text(encoding="utf-8") == before
    assert not (root / "docs" / "changelog").exists()


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
