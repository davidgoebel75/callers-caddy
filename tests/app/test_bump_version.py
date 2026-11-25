"""Tests fuer tools/bump_version.py — der Versions-Bump des Release-Workflows.

GUI-frei. Arbeitet auf einem Mini-Repo im tmp_path, nie auf dem echten.

Nummernschema ab 2.0: Major.Minor.Patch. Die Prototyp-Nummern 0.XX enden mit
0.162; ihr naechster Bump ist immer 2.0.0. Archiviert wird ab 2.0 pro
Minor-Linie (docs/changelog/2.0.md), die 0.XX-Versionen in Zehnerbloecken.
"""
import importlib.util
from pathlib import Path

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "bump_version", Path(__file__).resolve().parents[2] / "tools" / "bump_version.py"
)
bump_version = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(bump_version)


def _repo(tmp_path, unreleased="## (Unreleased — seit 2.0.15)\n\n### Verbesserungen\n- **Etwas.** Text.\n",
          released="## 2.0.15 — Alt (2026-09-15)\n\n- **Aeltestes.**\n"):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text('"""Doku."""\n\n__version__ = "2.0.14"\n\nimport sys\n', encoding="utf-8")
    (tmp_path / "CHANGELOG.md").write_text(
        f"# Changelog\n\n---\n\n{unreleased}\n{released}",
        encoding="utf-8",
    )
    return tmp_path


def _changelog(root):
    return (root / "CHANGELOG.md").read_text(encoding="utf-8")


# --- Nummern -----------------------------------------------------------------

def test_zaehlt_oberste_veroeffentlichte_version_hoch(tmp_path):
    root = _repo(tmp_path)
    assert bump_version.bump(title="Neu", date="2026-09-22", root=root) == "2.0.16"
    changelog = _changelog(root)
    assert "## 2.0.16 — Neu (2026-09-22)" in changelog
    assert "Unreleased" not in changelog
    # Beide Pflicht-Stellen, nicht nur der Changelog
    assert '__version__ = "2.0.16"' in (root / "src" / "main.py").read_text(encoding="utf-8")


@pytest.mark.parametrize("part, expected", [
    ("patch", "2.0.17"), ("minor", "2.1.0"), ("major", "3.0.0"),
])
def test_teil_bestimmt_die_stelle(part, expected):
    assert bump_version.next_version("## 2.0.16 — x (2026-12-01)", part) == expected


def test_patch_zaehlt_zweistellig_weiter():
    # 2.0.9 -> 2.0.10, kein Ueberlauf in die Minor-Stelle
    assert bump_version.next_version("## 2.0.9 — x (2026-12-01)") == "2.0.10"
    assert bump_version.next_version("## 2.9.0 — x (2026-12-01)", "minor") == "2.10.0"


@pytest.mark.parametrize("part", ["patch", "minor", "major"])
def test_nach_den_prototyp_nummern_kommt_2_0_0(part):
    assert bump_version.next_version("## 0.162 — x (2026-11-01)", part) == "2.0.0"


def test_unbekannter_teil_bricht_ab():
    with pytest.raises(SystemExit, match="unbekannter Teil"):
        bump_version.next_version("## 2.0.1 — x (2026-12-01)", "build")


def test_erzwungene_version_gewinnt(tmp_path):
    root = _repo(tmp_path)
    assert bump_version.bump(version="2.0.20", title="Sprung", date="2026-10-01", root=root) == "2.0.20"
    assert "## 2.0.20 — Sprung (2026-10-01)" in _changelog(root)


@pytest.mark.parametrize("version", ["2.0", "2", "1.5.0", "0.163", "2.0.1.3", "v2.0.16", "2.0.x"])
def test_unbekanntes_nummernformat_bricht_ab(tmp_path, version):
    # 1.x war die alte Version, neue 0.XX gibt es nicht mehr.
    root = _repo(tmp_path)
    before = _changelog(root)
    with pytest.raises(SystemExit, match="Nummernformat"):
        bump_version.bump(version=version, title="Launch", root=root)
    assert _changelog(root) == before


@pytest.mark.parametrize("version", ["2.0.15", "2.0.1", "2.0.9"])
def test_erzwungene_version_muss_steigen(tmp_path, version):
    # Tippfehler bei --version: ohne die Pruefung koennte die laufende Linie ausgelagert werden.
    root = _repo(tmp_path)
    before = _changelog(root)
    with pytest.raises(SystemExit, match="liegt nicht ueber"):
        bump_version.bump(version=version, root=root)
    assert _changelog(root) == before
    assert not (root / "docs" / "changelog").exists()


def test_cli_version_und_part_schliessen_sich_aus(tmp_path):
    with pytest.raises(SystemExit):
        bump_version.main(["--version", "2.1.0", "--part", "minor", "--check"])


# --- Uebergang 0.162 -> 2.0.0 -------------------------------------------------

def test_uebergang_lagert_den_letzten_prototyp_block_aus(tmp_path):
    root = _repo(tmp_path, unreleased="## (Unreleased — seit 0.162)\n\n- **Neu.**\n", released=(
        "## 0.162 — Zwei (2026-11-01)\n\n- **Zwei.**\n\n---\n\n"
        "## 0.160 — Null (2026-09-01)\n\n- **Null.**\n\n"
        "## Ältere Versionen\n\n- [0.150–0.159](docs/changelog/0.150-0.159.md)\n"
    ))
    older = root / "docs" / "changelog"
    older.mkdir(parents=True)
    (older / "0.150-0.159.md").write_text("# Alt\n", encoding="utf-8")
    assert bump_version.bump(title="Launch", date="2026-12-01", root=root) == "2.0.0"
    changelog = _changelog(root)
    assert "## 2.0.0 — Launch (2026-12-01)" in changelog
    assert "## 0.162" not in changelog and "## 0.160" not in changelog
    assert changelog.endswith(
        "## Ältere Versionen\n\n"
        "- [0.160–0.169](docs/changelog/0.160-0.169.md)\n"
        "- [0.150–0.159](docs/changelog/0.150-0.159.md)\n"
    )
    assert (older / "0.160-0.169.md").read_text(encoding="utf-8") == (
        "# Callers Caddy — Changelog 0.160–0.169\n\n"
        "## 0.162 — Zwei (2026-11-01)\n\n- **Zwei.**\n\n---\n\n"
        "## 0.160 — Null (2026-09-01)\n\n- **Null.**\n"
    )
    assert bump_version.next_version(changelog) == "2.0.1"


# --- Archiv pro Minor-Linie ----------------------------------------------------

def test_patch_in_der_laufenden_linie_lagert_nichts_aus(tmp_path):
    root = _repo(tmp_path, released=(
        "## 2.0.15 — Fuenfzehn (2026-09-15)\n\n- **15.**\n\n---\n\n"
        "## 2.0.0 — Launch (2026-08-01)\n\n- **0.**\n"
    ))
    assert bump_version.bump(root=root) == "2.0.16"
    changelog = _changelog(root)
    assert "## 2.0.15" in changelog and "## 2.0.0 — Launch" in changelog
    assert not (root / "docs" / "changelog").exists()


def test_neue_minor_linie_lagert_die_alte_aus(tmp_path):
    root = _repo(tmp_path, released=(
        "## 2.0.15 — Fuenfzehn (2026-09-15)\n\n- **15.**\n\n---\n\n"
        "## 2.0.0 — Launch (2026-08-01)\n\n- **0.**\n"
    ))
    assert bump_version.bump(part="minor", title="Taminations", date="2026-09-22", root=root) == "2.1.0"
    changelog = _changelog(root)
    archive = (root / "docs" / "changelog" / "2.0.md").read_text(encoding="utf-8")
    # Die neue Version bleibt stehen, damit der naechste Bump eine Nummer findet
    assert "## 2.1.0 — Taminations (2026-09-22)" in changelog
    assert bump_version.next_version(changelog) == "2.1.1"
    assert "## 2.0.15" not in changelog and "## 2.0.0" not in changelog
    assert changelog.endswith("## Ältere Versionen\n\n- [2.0.x](docs/changelog/2.0.md)\n")
    # Texte unveraendert, neueste zuerst
    assert archive == (
        "# Callers Caddy — Changelog 2.0.x\n\n"
        "## 2.0.15 — Fuenfzehn (2026-09-15)\n\n- **15.**\n\n---\n\n"
        "## 2.0.0 — Launch (2026-08-01)\n\n- **0.**\n"
    )


def test_verzeichnis_nennt_linien_vor_prototyp_bloecken(tmp_path):
    root = _repo(tmp_path, released="## 2.1.4 — Vier (2026-09-15)\n\n- **Vier.**\n")
    older = root / "docs" / "changelog"
    older.mkdir(parents=True)
    for name in ("0.90-0.99.md", "0.160-0.169.md", "0.00-0.09.md", "2.0.md"):
        (older / name).write_text("# Alt\n", encoding="utf-8")
    bump_version.bump(part="minor", root=root)
    assert _changelog(root).endswith(
        "- [2.1.x](docs/changelog/2.1.md)\n"
        "- [2.0.x](docs/changelog/2.0.md)\n"
        "- [0.160–0.169](docs/changelog/0.160-0.169.md)\n"
        "- [0.90–0.99](docs/changelog/0.90-0.99.md)\n"
        "- [0.00–0.09](docs/changelog/0.00-0.09.md)\n"
    )


def test_linien_sortieren_numerisch(tmp_path):
    root = _repo(tmp_path, released="## 2.10.0 — Zehn (2026-09-15)\n\n- **Zehn.**\n")
    older = root / "docs" / "changelog"
    older.mkdir(parents=True)
    (older / "2.9.md").write_text("# Alt\n", encoding="utf-8")
    bump_version.bump(part="minor", root=root)
    assert _changelog(root).endswith(
        "- [2.10.x](docs/changelog/2.10.md)\n- [2.9.x](docs/changelog/2.9.md)\n"
    )


def test_check_lagert_nichts_aus(tmp_path):
    root = _repo(tmp_path)
    before = _changelog(root)
    assert bump_version.bump(part="minor", write=False, root=root) == "2.1.0"
    assert _changelog(root) == before
    assert not (root / "docs" / "changelog").exists()


def test_leerer_unreleased_abschnitt_bricht_ab(tmp_path):
    root = _repo(tmp_path, unreleased="## (Unreleased — seit 2.0.15)\n")
    with pytest.raises(SystemExit):
        bump_version.bump(root=root)


def test_fehlender_unreleased_abschnitt_bricht_ab(tmp_path):
    root = _repo(tmp_path, unreleased="")
    with pytest.raises(SystemExit):
        bump_version.bump(root=root)


def test_check_schreibt_nichts(tmp_path):
    root = _repo(tmp_path)
    vorher = _changelog(root)
    assert bump_version.bump(title="Probe", write=False, root=root) == "2.0.16"
    assert _changelog(root) == vorher


def test_abbruch_nach_dem_auslagern_schreibt_kein_archiv(tmp_path):
    # Ohne __version__ in main.py bricht der Bump ab; ein schon geschriebenes Archiv
    # stuende beim zweiten Lauf doppelt da.
    root = _repo(tmp_path)
    (root / "src" / "main.py").write_text("import sys\n", encoding="utf-8")
    before = _changelog(root)
    with pytest.raises(SystemExit, match="__version__"):
        bump_version.bump(part="minor", root=root)
    assert _changelog(root) == before
    assert not (root / "docs" / "changelog").exists()


def test_archive_full_blocks_schreibt_nicht(tmp_path):
    changelog = (
        "# Changelog\n\n## 2.1.0 — Neu (2026-09-22)\n\n- **Neu.**\n\n"
        "## 2.0.3 — Drei (2026-09-15)\n\n- **Drei.**\n"
    )
    shortened, files = bump_version.archive_full_blocks(changelog, "2.1.0", tmp_path)
    assert "## 2.0.3" not in shortened
    assert list(files) == ["docs/changelog/2.0.md"]
    assert not (tmp_path / "docs").exists()


def test_neue_abschnitte_stehen_vor_den_archivierten(tmp_path):
    root = _repo(tmp_path, released="## 2.0.15 — Fuenfzehn (2026-09-15)\n\n- **15.**\n\n---\n")
    archive = root / "docs" / "changelog" / "2.0.md"
    archive.parent.mkdir(parents=True)
    archive.write_text(
        "# Callers Caddy — Changelog 2.0.x\n\n## 2.0.5 — Fuenf (2026-09-10)\n\n- **Fuenf.**\n",
        encoding="utf-8",
    )
    bump_version.bump(part="minor", root=root)
    # Trenner zwischen den Abschnitten bleibt, hinter dem letzten steht keiner
    assert archive.read_text(encoding="utf-8") == (
        "# Callers Caddy — Changelog 2.0.x\n\n"
        "## 2.0.15 — Fuenfzehn (2026-09-15)\n\n- **15.**\n\n---\n\n"
        "## 2.0.5 — Fuenf (2026-09-10)\n\n- **Fuenf.**\n"
    )


def test_archivdatei_mit_fremdem_kopf_bricht_ab(tmp_path):
    root = _repo(tmp_path)
    archive = root / "docs" / "changelog" / "2.0.md"
    archive.parent.mkdir(parents=True)
    archive.write_text("# Anderer Kopf\n\n## 2.0.5 — Fuenf (2026-09-10)\n", encoding="utf-8")
    before = _changelog(root)
    with pytest.raises(SystemExit, match="Kopf"):
        bump_version.bump(part="minor", root=root)
    assert _changelog(root) == before
    assert archive.read_text(encoding="utf-8").startswith("# Anderer Kopf")


def test_verzeichnis_ueberschrift_nur_als_ganze_zeile(tmp_path):
    # Steht der Text mitten in einem Eintrag, ist das kein Verzeichnis und bleibt stehen.
    root = _repo(tmp_path, released=(
        "## 2.0.15 — Alt (2026-09-01)\n\n- **Alt.** Siehe ## Ältere Versionen weiter unten.\n"
    ))
    bump_version.bump(root=root)
    assert "weiter unten." in _changelog(root)


def test_echtes_changelog_wird_zu_2_0_0(tmp_path):
    # Das Repo selbst: der naechste Bump muss 2.0.0 ergeben, ohne etwas zu schreiben.
    repo = Path(__file__).resolve().parents[2]
    if not (repo / "CHANGELOG.md").exists() or "## (Unreleased" not in _changelog(repo):
        pytest.skip("kein Unreleased-Abschnitt im echten Changelog")
    top = bump_version.RELEASED_RE.search(_changelog(repo)).group(1)
    if not bump_version.LEGACY_RE.fullmatch(top):
        pytest.skip(f"Umstellung schon erfolgt (oberste Version {top})")
    assert bump_version.bump(write=False, root=repo) == "2.0.0"
