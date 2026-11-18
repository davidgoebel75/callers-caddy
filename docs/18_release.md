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
8. Im Download-Bereich (Google Drive) einen Ordner mit der vollen Nummer anlegen (`2.0.16`) und die drei ZIPs hochladen. Die Update-Pruefung erkennt Ordner und Update-ZIP nur mit genau diesem Namen. Nur beim Release 2.0.0 zusaetzlich einmalig den Ordner `2.0` mit dem Inhalt von `4_Release/2.0/` anlegen (Bruecken-ZIP `Callers_Caddy_Update_2.0.zip`). Bei allen spaeteren Releases den Ordner `2.0` nicht anfassen.

## Hinweise

- **Versions-Bump NIE erst auf `main`:** Dann fehlt er auf `develop`, und der naechste Release-PR kollidiert in `CHANGELOG.md`.
- Nach dem Release steht `main` einen Commit vor `develop` (der Merge-Commit) — normal, nichts zu tun.
- **Bruecke fuer Installationen bis 0.162:** Deren Update-Pruefung kennt nur zweistellige Nummern und uebersieht Ordner wie `2.0.16`. Den Ordner `2.0` mit `Callers_Caddy_Update_2.0.zip` finden sie und melden „Version 2.0 verfuegbar“. Darin liegt fest die Update-ZIP von 2.0.0 unter diesem Namen (die ZIP enthaelt keinen Versionsordner, umbenennen reicht). Sie wird nie ersetzt: `build.py` legt `4_Release/2.0/` nur beim Build von genau 2.0.0 an, spaetere Builds lassen den Ordner unberuehrt. Ab 2.0.0 ueberspringt die Update-Pruefung den Ordner (`update_check._is_bridge`). Wer von 0.x kommt, landet also erst auf 2.0.0 und bekommt danach einen zweiten Update-Hinweis auf die neueste 2.x. Den Ordner `2.0` nie loeschen, solange es Nutzer mit 0.x gibt, und nie einen anderen zweistelligen 2.x-Ordner anlegen.
- Bauen, Ordner und ZIP-Typen: `CLAUDE.md`, Abschnitt „Ordner und Entwicklungs-Workflow".
- **Choreo-Engine (`tam_cli.exe`, intern#247):** `build.py` legt sie nach `choreo/` ins Paket. Sie kommt nicht aus Git, sondern vom Release-Asset `tam-cli-<version>` im Repo; geladen wird per `gh release download` (GitHub CLI angemeldet), geprueft per SHA-256 und zwischengespeichert unter `3_Build/engine-cache/`. Tag und Pruefsumme stehen in `installer/tam_engine.py`. Fuer die Entwicklung legt `python installer/tam_engine.py` die Exe nach `src/caddy/choreo/bin/`. ZIPs wachsen dadurch um ca. 5 MB.

## Updater testen

Der Download-Bereich ist live: was dort liegt, sehen alle Nutzer beim naechsten Start. Deshalb nie dort testen.

1. In Google Drive einen eigenen Ordner anlegen, der nirgends verlinkt ist, und „Jeder mit dem Link: Betrachter“ freigeben (optional mit Redirect, z. B. `callerscaddy.de/callers-caddy-test`).
2. Darin Versionsordner wie im echten Bereich anlegen, z. B. `2.0` (Bruecke), `2.0.0`, `2.0.1`. Die Erkennung haengt nur an Ordner- und Dateinamen, eine winzige Platzhalter-ZIP mit dem richtigen Namen (`Callers_Caddy_Update_2.0.1.zip`) reicht.
3. `python tools/update_check_probe.py <link> --as 0.162 2.0.0 2.0.1 --download`. Das Skript laesst die aktuelle Erkennung und die eingefrorene aus 0.162 gegen den Ordner laufen und fragt die erzeugten Links an.
4. Danach den Test-Ordner loeschen.

**In der echten App:** In der `callers_caddy.ini` der Installation unter `[update]` den Eintrag `url=<link>` setzen. Die App prueft dann diesen Ordner statt des Download-Bereichs. Update-Dialoge und „Ueber“ zeigen die abweichende Quelle an, damit der Eintrag nicht vergessen wird. Er uebersteht Updates, weil die Update-ZIP keine INI enthaelt: nach dem Test wieder loeschen. Leer, fehlend oder ohne `https://` gilt der Standard. Installationen bis 0.162 kennen den Eintrag nicht, fuer sie bleibt nur das Skript.

Erwartung (Stand 2.0.0-Umstieg, getestet 2026-11-16): 0.162 meldet „2.0“, 2.0.0 meldet „2.0.1“ und uebergeht die Bruecke, 2.0.1 meldet nichts; beide Links liefern die ZIP direkt.

Ausserdem vor dem ersten Release mit neuem Nummernschema oder neuem Qt: das Update-ZIP ueber eine frisch entpackte Vorversion entpacken und starten. Uebrig gebliebene Dateien der Vorversion (z. B. alte Qt-Plugins) bleiben dabei liegen und duerfen den Start nicht stoeren.
