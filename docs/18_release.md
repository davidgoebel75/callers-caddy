# Release-Ablauf

Die harten Regeln (Versions-Bump-Doppelpack, Merge-Commit, Build nur nach Rueckfrage) stehen in `CLAUDE.md`. Hier der vollstaendige Ablauf.

## Reihenfolge IMMER

1. Auf `develop`: Versions-Bump + Changelog (siehe PFLICHT-DOPPELPACK in `CLAUDE.md`), committen, pushen.
2. Pull Request `develop` → `main` anlegen: `gh pr create --base main --head develop --title "Release 0.XX"`. Tests abwarten.
3. Mergen mit **„Create a merge commit"** — NIE „Squash and merge", NIE „Rebase and merge". Sonst verliert Git die Verbindung zwischen `develop` und `main`, und der naechste Release-PR bringt alte Commits doppelt plus Konflikte.
4. `main` holen (`git switch main && git pull`), bauen (siehe Build-Regel in `CLAUDE.md`).
5. Build pruefen: `python installer/check_release.py <alt> <neu>` (mit `CC_RELEASE_DIR` wie beim Build). Vergleicht ZIP-Groessen mit der Vorversion, sucht Nutzerdaten im Update-ZIP, gleicht Skins mit `main` ab und prueft die Version. Nur Code geaendert ⇒ ZIPs wachsen kaum (0.158→0.159: +0,1 MB).
6. Schema-Abbild der neuen Version ablegen: `python tests/db/test_schema.py 0.XX` → `tests/db/schemas/0.XX.sql` committen. Damit prueft jeder spaetere Testlauf das Update von diesem Stand aus (intern#145).
7. Nach Davids Test am gebauten Paket Tag setzen: `git tag -a 0.XX -m "Release 0.XX"` und `git push origin 0.XX` (Format wie `0.151`, ohne `v`).

## Hinweise

- **Versions-Bump NIE erst auf `main`:** Dann fehlt er auf `develop`, und der naechste Release-PR kollidiert in `CHANGELOG.md`.
- Nach dem Release steht `main` einen Commit vor `develop` (der Merge-Commit) — normal, nichts zu tun.
- Bauen, Ordner und ZIP-Typen: `CLAUDE.md`, Abschnitt „Ordner und Entwicklungs-Workflow".
