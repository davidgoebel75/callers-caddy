#!/usr/bin/env python3
"""Versions-Bump fuer ein Release: schreibt die Nummer an beide Pflicht-Stellen.

Quelle der Wahrheit ist CHANGELOG.md, nicht main.py: die oberste bereits
veroeffentlichte Version gibt die naechste vor (0.159 -> 0.160), src/main.py
wird nachgezogen. Damit kann die Nummer dort nicht mehr hinterherhaengen --
genau das war bei 0.159 passiert.

Aufrufe:
    python tools/bump_version.py --title "Kurztitel"
    python tools/bump_version.py --version 2.0 --title "Launch"
    python tools/bump_version.py --check      # nur pruefen, nichts schreiben
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# "## (Unreleased — seit 0.159)" — der Sammler-Abschnitt aus CLAUDE.md.
UNRELEASED_RE = re.compile(r"^##\s*\(Unreleased[^\n]*\)[ \t]*$", re.M)
# "## 0.159 — Titel (2026-09-15)" — oberster Treffer = letztes Release.
RELEASED_RE = re.compile(r"^##\s+(\d+\.\d+)\b", re.M)
VERSION_RE = re.compile(r'^__version__\s*=\s*["\'][^"\']+["\']', re.M)


def next_version(changelog: str) -> str:
    """Zaehlt die oberste veroeffentlichte Version um eins hoch."""
    m = RELEASED_RE.search(changelog)
    if not m:
        raise SystemExit("FEHLER: keine veroeffentlichte '## 0.XX'-Version in CHANGELOG.md")
    major, minor = m.group(1).split(".", 1)
    # Stellenzahl beibehalten: 0.159 -> 0.160, nicht 0.16
    return f"{major}.{str(int(minor) + 1).zfill(len(minor))}"


def unreleased_section(changelog: str) -> tuple[re.Match, str]:
    """Liefert die Unreleased-Ueberschrift und ihren Rumpf bis zur naechsten '## '."""
    head = UNRELEASED_RE.search(changelog)
    if not head:
        raise SystemExit(
            "FEHLER: kein '## (Unreleased ...)'-Abschnitt in CHANGELOG.md — "
            "es gibt nichts zu releasen."
        )
    rest = changelog[head.end():]
    nxt = re.search(r"^##\s", rest, re.M)
    return head, rest[: nxt.start()] if nxt else rest


def bump(version: str = "", title: str = "", date: str = "", *, write: bool = True,
         root: Path = REPO_ROOT) -> str:
    """Setzt die Version in CHANGELOG.md und src/main.py. Gibt die Nummer zurueck."""
    changelog_path = root / "CHANGELOG.md"
    main_path = root / "src" / "main.py"
    changelog = changelog_path.read_text(encoding="utf-8")

    head, body = unreleased_section(changelog)
    if not re.search(r"^\s*[-*]\s+\S", body, re.M):
        raise SystemExit("FEHLER: der Unreleased-Abschnitt hat keine Eintraege — Abbruch.")

    version = version or next_version(changelog)
    date = date or dt.date.today().isoformat()
    heading = f"## {version} — {title} ({date})" if title else f"## {version} ({date})"
    changelog = changelog[: head.start()] + heading + changelog[head.end():]

    main_py = main_path.read_text(encoding="utf-8")
    if not VERSION_RE.search(main_py):
        raise SystemExit(f"FEHLER: __version__ nicht in {main_path} gefunden")
    main_py = VERSION_RE.sub(f'__version__ = "{version}"', main_py, count=1)

    if write:
        # newline="\n": das Repo ist durchgehend LF (siehe .gitattributes)
        with open(changelog_path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(changelog)
        with open(main_path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(main_py)
    return version


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--version", default="", help="Nummer erzwingen (leer = hochzaehlen)")
    ap.add_argument("--title", default="", help="Kurztitel fuer die Changelog-Ueberschrift")
    ap.add_argument("--date", default="", help="Datum JJJJ-MM-TT (leer = heute)")
    ap.add_argument("--check", action="store_true", help="nur pruefen, nichts schreiben")
    args = ap.parse_args(argv)

    version = bump(args.version, args.title, args.date, write=not args.check)
    print(f"{'wuerde setzen' if args.check else 'gesetzt'}: {version}")
    if out := os.environ.get("GITHUB_OUTPUT"):
        with open(out, "a", encoding="utf-8") as fh:
            fh.write(f"version={version}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
