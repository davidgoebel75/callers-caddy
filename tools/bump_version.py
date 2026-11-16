#!/usr/bin/env python3
"""Versions-Bump fuer ein Release: schreibt die Nummer an beide Pflicht-Stellen.

Quelle der Wahrheit ist CHANGELOG.md, nicht main.py: die oberste bereits
veroeffentlichte Version gibt die naechste vor (2.0.16 -> 2.0.17), src/main.py
wird nachgezogen. Damit kann die Nummer dort nicht mehr hinterherhaengen --
genau das war bei 0.159 passiert.

Nummernschema ab 2.0 (Major.Minor.Patch):
    Major  nur bei grossen, umwaelzenden Umbauten (bleibt lange 2)
    Minor  grosse neue Funktionen, z. B. Taminations-Einbindung
    Patch  kleine Funktionen, Fehlerbehebungen, kleine Aenderungen (Standard)
Die Prototyp-Nummern 0.XX enden mit 0.162. Steht oben noch eine 0.XX, wird
der naechste Bump immer 2.0.0.

CHANGELOG.md haelt nur "Unreleased" und die laufende Minor-Linie (alle 2.0.x).
Beginnt der Bump eine neue Linie (2.1.0), wandert die alte nach
docs/changelog/2.0.md. Die Prototyp-Versionen liegen in Zehnerbloecken
(docs/changelog/0.160-0.169.md, intern#203).

Aufrufe:
    python tools/bump_version.py --title "Kurztitel"               # Patch
    python tools/bump_version.py --part minor --title "Kurztitel"  # 2.0.16 -> 2.1.0
    python tools/bump_version.py --version 2.1.0 --title "Kurztitel"
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
# "## 2.0.16 — Titel (2026-12-01)" oder "## 0.159 — ..." — oberster Treffer = letztes Release.
RELEASED_RE = re.compile(r"^##\s+(\d+\.\d+(?:\.\d+)?)\b", re.M)
# Prototyp-Nummern (bis 0.162) und das Schema ab 2.0.0.
LEGACY_RE = re.compile(r"0\.(\d+)")
SEMVER_RE = re.compile(r"([2-9]|[1-9]\d+)\.(\d+)\.(\d+)")
FIRST_RELEASE = "2.0.0"
PARTS = ("patch", "minor", "major")
VERSION_RE = re.compile(r'^__version__\s*=\s*["\'][^"\']+["\']', re.M)

ARCHIVE_DIR = "docs/changelog"
# Verzeichnis der Archivdateien am Ende von CHANGELOG.md, wird bei jedem Umzug neu geschrieben.
ARCHIVE_INDEX_HEADING = "## Ältere Versionen"
ARCHIVE_INDEX_RE = re.compile(rf"^{re.escape(ARCHIVE_INDEX_HEADING)}[ \t]*$", re.M)
ARCHIVE_LEGACY_NAME_RE = re.compile(r"^0\.(\d+)-0\.\d+\.md$")
ARCHIVE_LINE_NAME_RE = re.compile(r"^(\d+)\.(\d+)\.md$")


def check_format(version: str) -> str:
    """Prueft das Nummernformat: 0.XX (Prototyp) oder Major.Minor.Patch ab 2.0.0."""
    if LEGACY_RE.fullmatch(version) or SEMVER_RE.fullmatch(version):
        return version
    raise SystemExit(
        f"FEHLER: unbekanntes Nummernformat '{version}' -- erwartet wird "
        "Major.Minor.Patch ab 2.0.0, z. B. 2.0.16."
    )


def next_version(changelog: str, part: str = "patch") -> str:
    """Zaehlt die oberste veroeffentlichte Version hoch (Patch, Minor oder Major)."""
    if part not in PARTS:
        raise SystemExit(f"FEHLER: unbekannter Teil '{part}' -- erlaubt: {', '.join(PARTS)}")
    m = RELEASED_RE.search(changelog)
    if not m:
        raise SystemExit("FEHLER: keine veroeffentlichte Version ('## 2.0.0 ...') in CHANGELOG.md")
    top = check_format(m.group(1))
    if LEGACY_RE.fullmatch(top):
        return FIRST_RELEASE  # Ende der Prototyp-Nummern
    major, minor, patch = version_key(top)
    if part == "major":
        return f"{major + 1}.0.0"
    if part == "minor":
        return f"{major}.{minor + 1}.0"
    return f"{major}.{minor}.{patch + 1}"


def version_key(version: str) -> tuple[int, ...]:
    """Vergleichswert einer Nummer: '0.161' -> (0, 161), '2.0.16' -> (2, 0, 16)."""
    return tuple(int(part) for part in version.split("."))


def write_lf(path: Path, text: str) -> None:
    """Schreibt UTF-8 mit LF: das Repo ist durchgehend LF (siehe .gitattributes)."""
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


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
    """Anfang des Zehnerblocks einer Prototyp-Version: 0.161 -> 160, 0.07 -> 0."""
    m = LEGACY_RE.fullmatch(version)
    if not m:
        raise SystemExit(f"FEHLER: '{version}' ist keine Prototyp-Nummer 0.XX")
    return int(m.group(1)) // 10 * 10


def block_label(start: int, sep: str = "-") -> str:
    """Name eines Zehnerblocks: 160 -> '0.160-0.169', 0 -> '0.00-0.09'."""
    return f"0.{start:02d}{sep}0.{start + 9:02d}"


def group_of(version: str) -> tuple[int, int]:
    """Archiv-Gruppe einer Version: Zehnerblock bis 0.XX, Minor-Linie ab 2.0.0.

    0.161 -> (0, 160), 2.0.16 -> (2, 0). Die Schluessel sortieren richtig:
    jede Minor-Linie liegt ueber allen Prototyp-Bloecken.
    """
    check_format(version)
    if LEGACY_RE.fullmatch(version):
        return (0, block_start(version))
    major, minor, _patch = version_key(version)
    return (major, minor)


def group_name(group: tuple[int, int]) -> str:
    """Dateiname ohne .md: (0, 160) -> '0.160-0.169', (2, 0) -> '2.0'."""
    return block_label(group[1]) if group[0] == 0 else f"{group[0]}.{group[1]}"


def group_title(group: tuple[int, int]) -> str:
    """Anzeigename: (0, 160) -> '0.160–0.169', (2, 0) -> '2.0.x'."""
    return block_label(group[1], "–") if group[0] == 0 else f"{group[0]}.{group[1]}.x"


def archive_groups(archive_dir: Path) -> set[tuple[int, int]]:
    """Gruppen der schon vorhandenen Archivdateien."""
    out = set()
    for f in archive_dir.glob("*.md"):
        if m := ARCHIVE_LEGACY_NAME_RE.match(f.name):
            out.add((0, int(m.group(1))))
        elif m := ARCHIVE_LINE_NAME_RE.match(f.name):
            out.add((int(m.group(1)), int(m.group(2))))
    return out


def archive_full_blocks(changelog: str, current_version: str,
                        root: Path) -> tuple[str, dict[str, str]]:
    """Lagert alle Abschnitte ausserhalb der laufenden Gruppe aus.

    Gruppe = Minor-Linie ab 2.0.0 (docs/changelog/2.0.md), Zehnerblock bei den
    Prototyp-Nummern (docs/changelog/0.160-0.169.md).
    Schreibt nichts: gibt das gekuerzte Changelog und den neuen Inhalt je
    Archivdatei zurueck (Pfad relativ zu root). Die Abschnitte wandern
    unveraendert, neueste Version zuerst.
    """
    current = group_of(current_version)
    index_pos = ARCHIVE_INDEX_RE.search(changelog)
    if index_pos:
        changelog = changelog[:index_pos.start()]
    # Vor jedem '## ' trennen: parts[0] ist der Dateikopf, danach je ein Abschnitt.
    parts = re.split(r"^(?=##\s)", changelog, flags=re.M)
    kept, moved = [parts[0]], {}
    for section in parts[1:]:
        m = RELEASED_RE.match(section)
        if m and group_of(m.group(1)) != current:
            moved.setdefault(group_of(m.group(1)), []).append(section)
        else:
            kept.append(section)

    archive_dir = root / ARCHIVE_DIR
    files = {}
    for group, sections in moved.items():
        path = archive_dir / f"{group_name(group)}.md"
        head = f"# Callers Caddy — Changelog {group_title(group)}\n\n"
        older = ""
        if path.exists():
            existing = path.read_text(encoding="utf-8")
            if not existing.startswith(head):
                raise SystemExit(
                    f"FEHLER: {ARCHIVE_DIR}/{path.name} beginnt nicht mit dem erwarteten "
                    f"Kopf '{head.strip()}' -- Abbruch, damit nichts verloren geht."
                )
            older = existing[len(head):]
        body = "".join(sections)
        if older and not body.endswith("\n\n"):
            body = body.rstrip("\n") + "\n\n"
        # Der Trenner hinter dem letzten Abschnitt hat in der Archivdatei keinen Nachfolger.
        text = re.sub(r"\n+---\s*\Z", "", (head + body + older).rstrip("\n"))
        files[f"{ARCHIVE_DIR}/{path.name}"] = text + "\n"

    groups = archive_groups(archive_dir) | set(moved)
    result = "".join(kept).rstrip("\n") + "\n"
    if groups:
        links = "".join(f"- [{group_title(g)}]({ARCHIVE_DIR}/{group_name(g)}.md)\n"
                        for g in sorted(groups, reverse=True))
        result += f"\n{ARCHIVE_INDEX_HEADING}\n\n{links}"
    return result, files


def bump(version: str = "", title: str = "", date: str = "", *, part: str = "patch",
         write: bool = True, root: Path = REPO_ROOT) -> str:
    """Setzt die Version in CHANGELOG.md und src/main.py. Gibt die Nummer zurueck."""
    changelog_path = root / "CHANGELOG.md"
    main_path = root / "src" / "main.py"
    changelog = changelog_path.read_text(encoding="utf-8")

    head, body = unreleased_section(changelog)
    if not re.search(r"^\s*[-*]\s+\S", body, re.M):
        raise SystemExit("FEHLER: der Unreleased-Abschnitt hat keine Eintraege — Abbruch.")

    if version:
        # Nummernformat pruefen, bevor verglichen wird. Neue 0.XX gibt es nicht mehr.
        if not SEMVER_RE.fullmatch(check_format(version)):
            raise SystemExit(
                f"FEHLER: unbekanntes Nummernformat '{version}' -- die Prototyp-Nummern "
                "0.XX sind abgeschlossen, erwartet wird Major.Minor.Patch ab 2.0.0."
            )
        top = RELEASED_RE.search(changelog)
        # Ein Tippfehler (2.0.1 statt 2.0.17) wuerde sonst die laufende Linie auslagern.
        if top and version_key(version) <= version_key(top.group(1)):
            raise SystemExit(
                f"FEHLER: Version {version} liegt nicht ueber der obersten "
                f"veroeffentlichten {top.group(1)} -- Tippfehler bei --version?"
            )
    else:
        version = next_version(changelog, part)
    date = date or dt.date.today().isoformat()
    heading = f"## {version} — {title} ({date})" if title else f"## {version} ({date})"
    changelog = changelog[: head.start()] + heading + changelog[head.end():]
    # Erst umbenennen, dann auslagern: so bleibt die neue Version in CHANGELOG.md
    # stehen und next_version() findet beim naechsten Bump immer eine Nummer.
    changelog, archived = archive_full_blocks(changelog, version, root)

    main_py = main_path.read_text(encoding="utf-8")
    if not VERSION_RE.search(main_py):
        raise SystemExit(f"FEHLER: __version__ nicht in {main_path} gefunden")
    main_py = VERSION_RE.sub(f'__version__ = "{version}"', main_py, count=1)

    # Geschrieben wird erst, wenn alle Pruefungen durch sind: ein Abbruch laesst
    # kein Archiv ohne passendes CHANGELOG.md zurueck.
    if write:
        for name, text in archived.items():
            (root / name).parent.mkdir(parents=True, exist_ok=True)
            write_lf(root / name, text)
            print(f"ausgelagert: {name}")
        write_lf(changelog_path, changelog)
        write_lf(main_path, main_py)
    return version


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--version", default="", help="Nummer erzwingen (leer = hochzaehlen)")
    ap.add_argument("--part", default="patch", choices=PARTS,
                    help="was hochgezaehlt wird: patch (Standard), minor, major")
    ap.add_argument("--title", default="", help="Kurztitel fuer die Changelog-Ueberschrift")
    ap.add_argument("--date", default="", help="Datum JJJJ-MM-TT (leer = heute)")
    ap.add_argument("--check", action="store_true", help="nur pruefen, nichts schreiben")
    args = ap.parse_args(argv)
    if args.version and args.part != "patch":
        ap.error("--version und --part schliessen sich aus")

    version = bump(args.version, args.title, args.date, part=args.part, write=not args.check)
    print(f"{'wuerde setzen' if args.check else 'gesetzt'}: {version}")
    if out := os.environ.get("GITHUB_OUTPUT"):
        with open(out, "a", encoding="utf-8") as fh:
            fh.write(f"version={version}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
