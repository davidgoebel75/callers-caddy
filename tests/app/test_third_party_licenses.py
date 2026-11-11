"""Lizenzen in der Auslieferung (intern#248).

`LICENSE` im Stamm traegt die GPLv2-Lizenz von Callers Caddy,
`installer/licenses/THIRD_PARTY.txt` listet jede mitgelieferte Fremdkomponente
mit ihrer Lizenzdatei. Faellt eine Zeile in `installer/requirements.txt` neu
dazu, muss sie dort nachgetragen werden; dieser Test erinnert daran.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
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


def test_every_requirement_listed():
    overview = OVERVIEW.read_text(encoding="utf-8").lower()
    missing = [n for n in _requirement_names() if n.lower() not in overview]
    assert not missing, f"In THIRD_PARTY.txt nachtragen: {missing}"


def test_referenced_license_files_exist():
    referenced = set(re.findall(r"(?<![/\w.-])[\w.-]+\.txt\b", OVERVIEW.read_text(encoding="utf-8")))
    referenced.discard("THIRD_PARTY.txt")
    assert referenced, "THIRD_PARTY.txt verweist auf keine Lizenzdatei"
    missing = sorted(f for f in referenced if not (LICENSES / f).is_file())
    assert not missing, f"Lizenzdatei fehlt in installer/licenses/: {missing}"
