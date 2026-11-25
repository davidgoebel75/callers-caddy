"""Choreo-Engine `tam_cli.exe` beschaffen (Square Flow, intern#247).

Die Engine liegt als Asset am Release ENGINE_TAG im Repo davidgoebel75/callers-caddy
(nicht in Git). Sie wird per `gh release download` in einen Zwischenspeicher geladen und
per SHA-256 geprueft; eine abweichende Datei bricht ab.

Neue Engine-Version: Release mit neuem Tag anlegen, ENGINE_TAG und ENGINE_SHA256 hier
anpassen, Gegenprobe mit tools/choreo_mapping_check.py.

Aufruf von Hand (fuer die Entwicklung):
  python installer/tam_engine.py          -> legt die Exe nach src/caddy/choreo/bin/
"""
import hashlib
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO = "davidgoebel75/callers-caddy"
ENGINE_TAG = "tam-cli-1.6.115"
ENGINE_FILE = "tam_cli.exe"
ENGINE_SHA256 = "2596190057ba5f81a6587dbd89fa514d664e0d60c9d579b1cf9106c3053ee596"

REPO_ROOT = Path(__file__).resolve().parent.parent
DEV_TARGET = REPO_ROOT / "src" / "caddy" / "choreo" / "bin" / ENGINE_FILE


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def fetch(cache_dir: Path) -> Path:
    """Gepruefte Engine im Zwischenspeicher; laedt sie bei Bedarf. Bricht bei Fehler ab."""
    target = cache_dir / ENGINE_TAG / ENGINE_FILE
    if target.exists() and sha256(target) == ENGINE_SHA256:
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        target.unlink()
    if shutil.which("gh") is None:
        sys.exit("FEHLER: gh (GitHub CLI) fehlt; die Choreo-Engine kann nicht geladen werden.")
    result = subprocess.run(["gh", "release", "download", ENGINE_TAG, "-R", REPO,
                             "-p", ENGINE_FILE, "-D", str(target.parent), "--clobber"])
    if result.returncode != 0 or not target.exists():
        sys.exit(f"FEHLER: Choreo-Engine {ENGINE_TAG} nicht geladen (gh-Fehler {result.returncode}).")
    got = sha256(target)
    if got != ENGINE_SHA256:
        target.unlink()
        sys.exit(f"FEHLER: Pruefsumme der Choreo-Engine stimmt nicht ({got}).")
    return target


def install(dest_dir: Path, cache_dir: Path) -> Path:
    """Engine nach dest_dir kopieren (im Build: <app>/choreo/)."""
    src = fetch(cache_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dst = dest_dir / ENGINE_FILE
    shutil.copy2(src, dst)
    return dst


if __name__ == "__main__":
    cache = Path(os.environ.get("CC_BUILD_DIR") or (REPO_ROOT.parent / "3_Build")) / "engine-cache"
    print(install(DEV_TARGET.parent, cache))
