#!/usr/bin/env python3
"""Song-Katalog ins Repo schieben: Scraper-CSV pruefen, kopieren, PR oeffnen.

Quelle ist die Ausgabe des Scraper-Projekts (music-for-callers-scraper,
output/all_songs_merged.csv). Dessen update.py ruft dieses Skript nach jedem
Update auf (intern#126); man kann es aber auch von Hand starten.

Ablauf, wenn sich der Katalog geaendert hat:
  1. CSV pruefen: Spalten wie song_catalog.COLUMNS, nicht leer, nicht drastisch
     geschrumpft (Schutz vor einem kaputten Scrape).
  2. Branch chore/song-catalog-JJJJ-MM-TT von origin/develop anlegen.
  3. music-extended-data/music_extended_data.csv ersetzen, committen, pushen.
  4. Pull Request nach develop oeffnen (gh). Gemergt wird von Hand.
  5. Zurueck auf den vorherigen Branch.

Nie direkt auf develop/main. Bricht ab, wenn das Repo getrackte, nicht
committete Aenderungen hat (ungetrackte Dateien stoeren nicht).

Aufrufe:
    python tools/update_song_catalog.py --source <pfad/all_songs_merged.csv>
    python tools/update_song_catalog.py --dry-run      # nur pruefen + Diff zeigen
    python tools/update_song_catalog.py --no-pr        # Branch + Commit, kein Push/PR

Exit-Codes: 0 = ok/unveraendert, 1 = Pruefung fehlgeschlagen, 2 = Git/gh-Fehler.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
TARGET = REPO_ROOT / "music-extended-data" / "music_extended_data.csv"
DEFAULT_SOURCE = Path.home() / ".claude" / "Projekte" / "music-for-callers-scraper" \
    / "output" / "all_songs_merged.csv"
BASE_BRANCH = "develop"

sys.path.insert(0, str(REPO_ROOT / "src"))
from song_catalog import COLUMNS  # noqa: E402  (Spalten an einer Stelle)

# Neuer Katalog darf hoechstens so stark schrumpfen (sonst kaputter Scrape).
MIN_KEEP_RATIO = 0.95
# So viele neue/entfallene Songs werden im PR namentlich gelistet.
MAX_LISTED = 60


def _read(path: Path) -> tuple:
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        header = list(reader.fieldnames or [])
        rows = list(reader)
    return header, rows


def _key(row: dict) -> tuple:
    return (row.get("Song Title", "").strip(), row.get("Label Code", "").strip(),
            row.get("Number", "").strip())


def _fmt(key: tuple) -> str:
    title, code, num = key
    label = " ".join(x for x in (code, num) if x)
    return f"{title} ({label})" if label else title


def validate(source: Path) -> tuple:
    """(neue Zeilen, Fehlertext oder '')."""
    if not source.is_file():
        return [], f"Quelle nicht gefunden: {source}"
    header, rows = _read(source)
    if header != COLUMNS:
        return [], f"Unerwartete Spalten: {header} (erwartet {COLUMNS})"
    if not rows:
        return [], "Quelle ist leer"
    if TARGET.is_file():
        _h, old = _read(TARGET)
        if old and len(rows) < len(old) * MIN_KEEP_RATIO:
            return [], (f"Katalog geschrumpft: {len(rows)} statt {len(old)} Zeilen "
                        f"(< {MIN_KEEP_RATIO:.0%}) - Scrape pruefen, nichts uebernommen")
    return rows, ""


def diff(new_rows: list) -> tuple:
    old_keys = set()
    if TARGET.is_file():
        old_keys = {_key(r) for r in _read(TARGET)[1]}
    new_keys = {_key(r) for r in new_rows}
    return sorted(new_keys - old_keys), sorted(old_keys - new_keys)


def _git(*args, check=True) -> str:
    res = subprocess.run(["git", *args], cwd=REPO_ROOT, capture_output=True,
                         text=True, encoding="utf-8")
    if check and res.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {res.stderr.strip() or res.stdout.strip()}")
    return res.stdout.strip()


def _branch_name() -> str:
    base = f"chore/song-catalog-{dt.date.today().isoformat()}"
    existing = set(_git("branch", "--all", "--format=%(refname:short)").split())
    name, n = base, 2
    while name in existing or f"origin/{name}" in existing:
        name, n = f"{base}-{n}", n + 1
    return name


def _pr_body(added: list, removed: list, total: int) -> str:
    lines = [f"Automatische Aktualisierung des Song-Katalogs (intern#126), "
             f"{total} Songs: **+{len(added)}** neu, **-{len(removed)}** entfallen.", ""]
    for title, keys in (("Neu", added), ("Entfallen", removed)):
        if keys:
            lines.append(f"### {title}")
            lines += [f"- {_fmt(k)}" for k in keys[:MAX_LISTED]]
            if len(keys) > MAX_LISTED:
                lines.append(f"- … und {len(keys) - MAX_LISTED} weitere")
            lines.append("")
    lines.append("Erzeugt von `tools/update_song_catalog.py` "
                 "(aufgerufen vom Scraper-Update).")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-pr", action="store_true")
    args = ap.parse_args()

    rows, err = validate(args.source)
    if err:
        print(f"[Katalog] FEHLER: {err}")
        return 1
    # Inhalt vergleichen, nicht Bytes: der Scraper schreibt CRLF, das Repo LF
    if TARGET.is_file() and _read(TARGET)[1] == rows:
        print(f"[Katalog] Unveraendert ({len(rows)} Songs) - nichts zu tun.")
        return 0
    added, removed = diff(rows)
    summary = f"+{len(added)}/-{len(removed)}, {len(rows)} Songs"
    print(f"[Katalog] Aenderung: {summary}")
    for k in added[:10]:
        print(f"  + {_fmt(k)}")
    if args.dry_run:
        return 0

    try:
        if _git("status", "--porcelain", "--untracked-files=no"):
            print("[Katalog] ABBRUCH: CC-Repo hat nicht committete Aenderungen "
                  f"({REPO_ROOT}). Erst committen/stashen, dann erneut starten.")
            return 2
        start = _git("rev-parse", "--abbrev-ref", "HEAD")
        _git("fetch", "origin", BASE_BRANCH)
        branch = _branch_name()
        _git("switch", "-c", branch, f"origin/{BASE_BRANCH}")
        try:
            # Mit LF schreiben (.gitattributes: eol=lf), sonst meldet der
            # naechste Lauf / git status eine Scheinaenderung
            TARGET.write_bytes(args.source.read_bytes().replace(b"\r\n", b"\n"))
            _git("add", str(TARGET.relative_to(REPO_ROOT)))
            _git("commit", "-m", f"Chore(Katalog): Song-Katalog aktualisiert ({summary})",
                 "-m", "Automatisch per tools/update_song_catalog.py (intern#126).")
            if args.no_pr:
                print(f"[Katalog] Commit auf {branch} (ohne Push/PR).")
                return 0
            _git("push", "-u", "origin", branch)
            res = subprocess.run(
                ["gh", "pr", "create", "--base", BASE_BRANCH, "--head", branch,
                 "--title", f"Song-Katalog aktualisiert ({summary})",
                 "--body", _pr_body(added, removed, len(rows))],
                cwd=REPO_ROOT, capture_output=True, text=True, encoding="utf-8")
            if res.returncode != 0:
                print(f"[Katalog] Push ok, PR fehlgeschlagen: {res.stderr.strip()}")
                return 2
            print(f"[Katalog] PR: {res.stdout.strip()}")
        finally:
            _git("switch", start, check=False)
    except RuntimeError as e:
        print(f"[Katalog] Git-Fehler: {e}")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
