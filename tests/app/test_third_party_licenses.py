"""Lizenzen in der Auslieferung (intern#248).

`LICENSE` im Stamm traegt die GPLv2-Lizenz von Callers Caddy,
`installer/licenses/THIRD_PARTY.txt` listet jede mitgelieferte Fremdkomponente
mit ihrer Lizenzdatei. Faellt eine Zeile in `installer/requirements.txt` neu
dazu, muss sie dort nachgetragen werden; dieser Test erinnert daran.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "installer"))
LICENSES = ROOT / "installer" / "licenses"
OVERVIEW = LICENSES / "THIRD_PARTY.txt"


def _requirement_names():
    lines = (ROOT / "installer" / "requirements.txt").read_text(encoding="utf-8").splitlines()
    return [re.split(r"[<>=!~\[; ]", ln.strip(), 1)[0]
            for ln in lines if ln.strip() and not ln.lstrip().startswith("#")]


def test_license_is_gplv2():
    text = (ROOT / "LICENSE").read_text(encoding="utf-8")
    assert "GNU GENERAL PUBLIC LICENSE" in text
    assert "Version 2, June 1991" in text


def _component_column():
    """Erste Spalte der Tabelle in THIRD_PARTY.txt (Zeilen nach der ----Linie)."""
    rows = OVERVIEW.read_text(encoding="utf-8").split("\n---", 1)[1].split("\n\n", 1)[0]
    return " ".join(re.split(r" {2,}", r)[0] for r in rows.splitlines()[1:]).lower()


def test_every_requirement_listed():
    components = _component_column()
    missing = [n for n in _requirement_names() if n.lower() not in components]
    assert not missing, f"In THIRD_PARTY.txt nachtragen: {missing}"


def test_referenced_license_files_exist():
    referenced = set(re.findall(r"(?<![/\w.-])[\w.-]+\.txt\b", OVERVIEW.read_text(encoding="utf-8")))
    referenced.discard("THIRD_PARTY.txt")
    assert referenced, "THIRD_PARTY.txt verweist auf keine Lizenzdatei"
    missing = sorted(f for f in referenced if not (LICENSES / f).is_file())
    assert not missing, f"Lizenzdatei fehlt in installer/licenses/: {missing}"


def test_choreo_engine_listed_with_source():
    """Die mitgelieferte tam_cli.exe (GPL-3.0) braucht Eintrag und Quellcode-Link
    zum ausgelieferten Stand; ein neuer ENGINE_TAG muss hier nachgezogen werden (intern#262)."""
    from tam_engine import ENGINE_FILE, ENGINE_TAG
    text = OVERVIEW.read_text(encoding="utf-8")
    assert ENGINE_FILE in text
    assert f"Engine version: {ENGINE_TAG}" in text
    assert f"tam-headless/tree/{ENGINE_TAG}" in text
