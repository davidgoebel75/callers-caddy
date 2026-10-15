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
    # Wie die Bloecke ab 2.0 heissen, ist offen (intern#203), bis dahin kein stilles Raten.
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


@pytest.mark.parametrize("version", ["0.16", "0.5", "0.155", "0.161"])
def test_erzwungene_version_muss_steigen(tmp_path, version):
    # Tippfehler bei --version: ohne die Pruefung wuerde der laufende Block ausgelagert.
    root = _repo(tmp_path, unreleased="## (Unreleased — seit 0.161)\n\n- **Etwas.**\n", released=(
        "## 0.161 — Eins (2026-09-15)\n\n- **Eins.**\n\n---\n\n"
        "## 0.160 — Null (2026-09-01)\n\n- **Null.**\n"
    ))
    before = (root / "CHANGELOG.md").read_text(encoding="utf-8")
    with pytest.raises(SystemExit, match="liegt nicht ueber"):
        bump_version.bump(version=version, root=root)
    assert (root / "CHANGELOG.md").read_text(encoding="utf-8") == before
    assert not (root / "docs" / "changelog").exists()


def test_abbruch_nach_dem_auslagern_schreibt_kein_archiv(tmp_path):
    # Ohne __version__ in main.py bricht der Bump ab; ein schon geschriebenes Archiv
    # stuende beim zweiten Lauf doppelt da.
    root = _repo(tmp_path, released="## 0.169 — Neun (2026-09-15)\n\n- **Neun.**\n")
    (root / "src" / "main.py").write_text("import sys\n", encoding="utf-8")
    before = (root / "CHANGELOG.md").read_text(encoding="utf-8")
    with pytest.raises(SystemExit, match="__version__"):
        bump_version.bump(root=root)
    assert (root / "CHANGELOG.md").read_text(encoding="utf-8") == before
    assert not (root / "docs" / "changelog").exists()


def test_archive_full_blocks_schreibt_nicht(tmp_path):
    changelog = (
        "# Changelog\n\n## 0.170 — Neu (2026-09-22)\n\n- **Neu.**\n\n"
        "## 0.169 — Neun (2026-09-15)\n\n- **Neun.**\n"
    )
    shortened, files = bump_version.archive_full_blocks(changelog, "0.170", tmp_path)
    assert "## 0.169" not in shortened
    assert list(files) == ["docs/changelog/0.160-0.169.md"]
    assert not (tmp_path / "docs").exists()


def test_neue_abschnitte_stehen_vor_den_archivierten(tmp_path):
    root = _repo(tmp_path, released="## 0.169 — Neun (2026-09-15)\n\n- **Neun.**\n\n---\n")
    archive = root / "docs" / "changelog" / "0.160-0.169.md"
    archive.parent.mkdir(parents=True)
    archive.write_text(
        "# Callers Caddy — Changelog 0.160–0.169\n\n## 0.165 — Fuenf (2026-09-10)\n\n- **Fuenf.**\n",
        encoding="utf-8",
    )
    bump_version.bump(root=root)
    # Trenner zwischen den Abschnitten bleibt, hinter dem letzten steht keiner
    assert archive.read_text(encoding="utf-8") == (
        "# Callers Caddy — Changelog 0.160–0.169\n\n"
        "## 0.169 — Neun (2026-09-15)\n\n- **Neun.**\n\n---\n\n"
        "## 0.165 — Fuenf (2026-09-10)\n\n- **Fuenf.**\n"
    )


def test_archivdatei_endet_ohne_trenner(tmp_path):
    root = _repo(tmp_path, released="## 0.169 — Neun (2026-09-15)\n\n- **Neun.**\n\n---\n")
    bump_version.bump(root=root)
    archive = (root / "docs" / "changelog" / "0.160-0.169.md").read_text(encoding="utf-8")
    assert archive.endswith("- **Neun.**\n")


def test_archivdatei_mit_fremdem_kopf_bricht_ab(tmp_path):
    root = _repo(tmp_path, released="## 0.169 — Neun (2026-09-15)\n\n- **Neun.**\n")
    archive = root / "docs" / "changelog" / "0.160-0.169.md"
    archive.parent.mkdir(parents=True)
    archive.write_text("# Anderer Kopf\n\n## 0.165 — Fuenf (2026-09-10)\n", encoding="utf-8")
    before = (root / "CHANGELOG.md").read_text(encoding="utf-8")
    with pytest.raises(SystemExit, match="Kopf"):
        bump_version.bump(root=root)
    assert (root / "CHANGELOG.md").read_text(encoding="utf-8") == before
    assert archive.read_text(encoding="utf-8").startswith("# Anderer Kopf")


def test_verzeichnis_ueberschrift_nur_als_ganze_zeile(tmp_path):
    # Steht der Text mitten in einem Eintrag, ist das kein Verzeichnis und bleibt stehen.
    root = _repo(tmp_path, released=(
        "## 0.160 — Null (2026-09-01)\n\n- **Null.** Siehe ## Ältere Versionen weiter unten.\n"
    ))
    bump_version.bump(root=root)
    assert "weiter unten." in (root / "CHANGELOG.md").read_text(encoding="utf-8")
