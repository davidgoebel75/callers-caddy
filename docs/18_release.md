# Release-Ablauf

Die harten Regeln (Versions-Bump-Doppelpack, Merge-Commit, Build nur nach Rueckfrage) stehen in `CLAUDE.md`. Hier der vollstaendige Ablauf.

## Reihenfolge IMMER

1. Auf `develop`: Versions-Bump + Changelog (siehe „Versionsnummern" und PFLICHT-DOPPELPACK in `CLAUDE.md`), committen, pushen. Normal ist ein Patch (`python tools/bump_version.py --title "…"`), grosse neue Funktionen bekommen `--part minor`. Beginnt die neue Version eine Minor-Linie (2.1.0), legt `tools/bump_version.py` dabei `docs/changelog/2.0.md` an — die neue Datei mit committen (`git add CHANGELOG.md docs/changelog src/main.py`). Beim ersten Bump auf 2.0.0 entsteht so `docs/changelog/0.160-0.169.md`.
2. Pull Request `develop` → `main` anlegen: `gh pr create --base main --head develop --title "Release 2.0.X"`. Tests abwarten.
3. Mergen mit **„Create a merge commit"** — NIE „Squash and merge", NIE „Rebase and merge". Sonst verliert Git die Verbindung zwischen `develop` und `main`, und der naechste Release-PR bringt alte Commits doppelt plus Konflikte.
4. `main` holen (`git switch main && git pull`), bauen (siehe Build-Regel in `CLAUDE.md`).
5. Build pruefen: `python installer/check_release.py <alt> <neu>` (mit `CC_RELEASE_DIR` wie beim Build). Vergleicht ZIP-Groessen mit der Vorversion, sucht Nutzerdaten im Update-ZIP, gleicht Skins mit `main` ab und prueft die Version. Nur Code geaendert ⇒ ZIPs wachsen kaum (0.158→0.159: +0,1 MB).
6. Schema-Abbild der neuen Version ablegen: `python tests/db/test_schema.py 2.0.X` → `tests/db/schemas/2.0.X.sql` committen. Damit prueft jeder spaetere Testlauf das Update von diesem Stand aus (intern#145).
7. Nach Davids Test am gebauten Paket Tag setzen: `git tag -a 2.0.X -m "Release 2.0.X"` und `git push origin 2.0.X` (Format wie `2.0.16`, ohne `v`).
8. Im Download-Bereich (Google Drive) einen Ordner mit der vollen Nummer anlegen (`2.0.16`) und die drei ZIPs hochladen. Die Update-Pruefung erkennt Ordner und Update-ZIP nur mit genau diesem Namen.

## Hinweise

- **Versions-Bump NIE erst auf `main`:** Dann fehlt er auf `develop`, und der naechste Release-PR kollidiert in `CHANGELOG.md`.
- Nach dem Release steht `main` einen Commit vor `develop` (der Merge-Commit) — normal, nichts zu tun.
- **Umstieg 0.162 → 2.0.0:** Installationen bis 0.162 kennen nur zweistellige Nummern und sehen den Ordner `2.0.0` in ihrer Update-Pruefung nicht. Wer 0.162 oder aelter hat, laedt 2.0.0 einmal von Hand; ab 2.0.0 meldet die App jedes weitere Update selbst.
- Bauen, Ordner und ZIP-Typen: `CLAUDE.md`, Abschnitt „Ordner und Entwicklungs-Workflow".
