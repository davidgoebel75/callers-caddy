#!/usr/bin/env python3
"""Prueft die Update-Erkennung gegen einen echten Drive-Ordner, ohne die App zu starten.

Laesst die aktuelle Erkennung (src/update_check.py) und die eingefrorene aus
0.162 (Git-Tag, so steckt sie in allen alten Installationen) gegen einen
Ordner laufen und zeigt, welches Update jede installierte Version melden wuerde.
Mit --download wird der erzeugte Link angefragt (Dateiname, Groesse, ZIP ja/nein).

Fuer Tests nie den echten Download-Bereich nehmen, sondern einen eigenen,
nirgends verlinkten Ordner (siehe docs/18_release.md, „Updater testen").

Aufruf:
    python tools/update_check_probe.py https://callerscaddy.de/callers-caddy-test
    python tools/update_check_probe.py <url> --as 0.162 2.0.0 2.0.1 --download
"""
from __future__ import annotations

import argparse
import importlib.util
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
OLD_TAG = "0.162"


def _load(name: str, path: Path, url: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.UPDATE_URL = url
    return mod


def _old_module(url: str, tmp: Path):
    src = subprocess.run(["git", "show", f"{OLD_TAG}:src/update_check.py"], cwd=REPO,
                         capture_output=True, text=True, encoding="utf-8", check=True).stdout
    path = tmp / "update_check_old.py"
    path.write_text(src, encoding="utf-8")
    return _load("update_check_old", path, url)


def _probe_download(link: str, agent: str) -> str:
    req = urllib.request.Request(link, headers={"User-Agent": agent})
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = resp.read()
        name = resp.headers.get("Content-Disposition", "")
    return f"{len(data):,} Bytes, ZIP={'ja' if data[:2] == b'PK' else 'NEIN'}, {name}"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("url", help="Drive-Ordner bzw. Redirect darauf")
    ap.add_argument("--as", dest="versions", nargs="+", default=["0.162", "2.0.0"],
                    help="installierte Versionen, die simuliert werden (0.x = alte Erkennung)")
    ap.add_argument("--download", action="store_true", help="gefundene Links auch anfragen")
    args = ap.parse_args(argv)

    sys.path.insert(0, str(REPO / "src"))
    new = _load("update_check_new", REPO / "src" / "update_check.py", args.url)
    with tempfile.TemporaryDirectory() as tmp:
        old = _old_module(args.url, Path(tmp))
        html = new._fetch(args.url)
        print(f"Ordner geladen ({len(html):,} Zeichen)")
        print(f"  alte Erkennung ({OLD_TAG}) sieht: {[v for _t, v, _i in old._list_version_folders(html)]}")
        print(f"  neue Erkennung sieht:        {[v for _t, v, _i in new._list_version_folders(html)]}")
        for version in args.versions:
            mod, label = (old, "alt") if version.startswith("0.") else (new, "neu")
            found = mod.find_latest_update(version)
            print(f"  installiert {version:7} ({label}) -> {found[0] if found else 'kein Update'}")
            if found and args.download:
                print(f"      Download: {_probe_download(found[1], new._USER_AGENT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
