#!/usr/bin/env python3
"""Versions-Bump fuer ein Release: schreibt die Nummer an beide Pflicht-Stellen.

Quelle der Wahrheit ist CHANGELOG.md, nicht main.py: die oberste bereits
veroeffentlichte Version gibt die naechste vor (0.159 -> 0.160), src/main.py
wird nachgezogen. Damit kann die Nummer dort nicht mehr hinterherhaengen --
genau das war bei 0.159 passiert.

CHANGELOG.md haelt nur "Unreleased" und den laufenden Zehnerblock (0.160 bis
0.169). Beginnt der Bump einen neuen Block (0.170), wandert der volle nach
docs/changelog/0.160-0.169.md (intern#203).

Aufrufe:
    python tools/bump_version.py --title "Kurztitel"
    python tools/bump_version.py --version 0.170 --title "Kurztitel"
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

ARCHIVE_DIR = "docs/changelog"
# Verzeichnis der Archivdateien am Ende von CHANGELOG.md, wird bei jedem Umzug neu geschrieben.
ARCHIVE_INDEX_HEADING = "## Ältere Versionen"
ARCHIVE_NAME_RE = re.compile(r"^0\.(\d+)-0\.\d+\.md$")


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


def block_start(version: str) -> int:
    """Anfang des Zehnerblocks einer Version: 0.161 -> 160, 0.07 -> 0."""
    m = re.fullmatch(r"0\.(\d+)", version)
    if not m:
        raise SystemExit(
            f"FEHLER: unbekanntes Nummernformat '{version}' — die Zehnerbloecke des "
            "Changelogs sind nur fuer 0.XX festgelegt. Erst die Benennung der "
            f"Archivdateien klaeren (intern#203), dann {Path(__file__).name} anpassen."
        )
    return int(m.group(1)) // 10 * 10


def block_label(start: int, sep: str = "-") -> str:
    """Name eines Zehnerblocks: 160 -> '0.160-0.169', 0 -> '0.00-0.09'."""
    return f"0.{start:02d}{sep}0.{start + 9:02d}"


def archive_full_blocks(changelog: str, current_version: str, root: Path = REPO_ROOT,
                        *, write: bool = True) -> tuple[str, list[str]]:
    """Lagert alle Abschnitte ausserhalb des laufenden Zehnerblocks aus.

    Gibt das gekuerzte Changelog und die geschriebenen Archivdateien zurueck.
    Die Abschnitte wandern unveraendert, neueste Version zuerst.
    """
    current = block_start(current_version)
    index = changelog.find(ARCHIVE_INDEX_HEADING)
    if index != -1:
        changelog = changelog[:index]
    # Vor jedem '## ' trennen: parts[0] ist der Dateikopf, danach je ein Abschnitt.
    parts = re.split(r"^(?=##\s)", changelog, flags=re.M)
    kept, moved = [parts[0]], {}
    for section in parts[1:]:
        m = RELEASED_RE.match(section)
        if m and block_start(m.group(1)) != current:
            moved.setdefault(block_start(m.group(1)), []).append(section)
        else:
            kept.append(section)

    archive_dir = root / ARCHIVE_DIR
    written = []
    for start, sections in moved.items():
        path = archive_dir / f"{block_label(start)}.md"
        head = f"# Callers Caddy — Changelog {block_label(start, '–')}\n\n"
        older = path.read_text(encoding="utf-8")[len(head):] if path.exists() else ""
        body = "".join(sections)
        if older and not body.endswith("\n\n"):
            body = body.rstrip("\n") + "\n\n"
        written.append(f"{ARCHIVE_DIR}/{path.name}")
        if write:
            archive_dir.mkdir(parents=True, exist_ok=True)
            with open(path, "w", encoding="utf-8", newline="\n") as fh:
                fh.write((head + body + older).rstrip("\n") + "\n")

    starts = {int(m.group(1)) for f in archive_dir.glob("*.md")
              if (m := ARCHIVE_NAME_RE.match(f.name))} | set(moved)
    result = "".join(kept).rstrip("\n") + "\n"
    if starts:
        links = "".join(f"- [{block_label(s, '–')}]({ARCHIVE_DIR}/{block_label(s)}.md)\n"
                        for s in sorted(starts, reverse=True))
        result += f"\n{ARCHIVE_INDEX_HEADING}\n\n{links}"
    return result, written


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
    # Erst umbenennen, dann auslagern: so bleibt die neue Version in CHANGELOG.md
    # stehen und next_version() findet beim naechsten Bump immer eine Nummer.
    changelog, archived = archive_full_blocks(changelog, version, root, write=write)

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
        for name in archived:
            print(f"ausgelagert: {name}")
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
