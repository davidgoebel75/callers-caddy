# Callers Caddy — Projektanweisungen

**Wer Code schreibt oder aendert, liest vorher `CODING_STANDARDS.md`** (pruefbare Regeln: Sprache, Modularisierung, Audio-Pflichtmuster, Qt-Fallen, i18n, Tests). Das Code-Review prueft gegen dieselbe Datei.

## Changelog-Pflicht

`CHANGELOG.md` liegt im Projektstamm. **Jede Aenderung wird dokumentiert, solange sie frisch ist** — nicht erst vorm Release (dann weiss man die Details nicht mehr). Ablauf in zwei Stufen:

**1. Sofort beim Feature/Fix (Sammler-Abschnitt):**
- Ganz oben steht ein Abschnitt `## (Unreleased — seit 0.XX)` als **Sammler fuer noch nicht veroeffentlichte Aenderungen**. Fehlt er (weil gerade frisch gebaut wurde), beim naechsten Feature neu anlegen.
- Neue/verbesserte Features und relevante Bugfixes/Perf als Bullet Points **direkt nach dem Merge** dort eintragen. **Noch KEINE Versionsnummer, KEIN Datum** — das bleibt dem Build vorbehalten (eine Sammelversion pro Build, keine neue Nummer pro Feature).
- Endnutzer-orientiert formulieren, Sprache: **Deutsch**.

**2. Beim Release (Sammelversion + Versions-Bump) — auf `develop`, VOR dem Release-PR:**
- Aus `(Unreleased)` wird die fertige Version: Ueberschrift auf `## 0.XX — <Kurztitel> (YYYY-MM-DD)` setzen (neueste Version zuerst).
- Versionsnummer: `0.XX` (XX = Prototyp-Nummer, zweistellig). Ab offiziellem Launch: `2.0+` (1.x war die alte Version).
- Siehe „Versions-Bump — PFLICHT-DOPPELPACK" und „Branches und Release".

## Branches und Release

`develop` ist Default-Branch und Sammelstelle fuer alles Fertige. `main` enthaelt nur veroeffentlichte Staende.

- **Neue Arbeit:** Branch immer frisch von `develop` abzweigen, Pull Request nach `develop`.
- **Auf `main` wird nie direkt committet.** Aenderungen kommen dort nur ueber den Release-PR an.
- **Release-PR `develop` → `main` mergen mit „Create a merge commit"** — NIE „Squash and merge", NIE „Rebase and merge". Sonst verliert Git die Verbindung zwischen `develop` und `main`, und der naechste Release-PR bringt alte Commits doppelt plus Konflikte.
- **Versions-Bump NIE erst auf `main`:** Dann fehlt er auf `develop`, und der naechste Release-PR kollidiert in `CHANGELOG.md`.
- **Vollstaendiger Release-Ablauf** (7 Schritte inkl. Build-Pruefung, Schema-Abbild, Tag): `docs/18_release.md` — vor jedem Release lesen.

## Versions-Bump — PFLICHT-DOPPELPACK

**Die Versionsnummer steht an ZWEI Stellen — beide gleichzeitig pflegen:**
1. `src/main.py` → `__version__ = "0.XX"`  ← **`build.py` liest die Version VON HIER**
2. `CHANGELOG.md` → neuer Abschnitt oben

**Reihenfolge IMMER:** erst `main.py` aendern, dann `CHANGELOG.md` aendern, DANN bauen. Sonst baut `build.py` stillschweigend mit der alten Versionsnummer und alle ZIPs landen im falschen Ordner — das ist hier schon mehrfach passiert. Wenn unsicher: vor dem Build `grep __version__ src/main.py` und mit `CHANGELOG.md` oberstem Eintrag vergleichen.

## Build-Regel

**EXEs und ZIPs (build.py) IMMER erst nach Rueckfrage erstellen!** Der Build dauert ~1 Minute und ist oft ueberfluessig. Erst fragen: "Soll ich jetzt bauen?" — nicht automatisch nach Code-Aenderungen starten.

## Ordner und Entwicklungs-Workflow

- **Quellcode lebt im Git-Klon** (`src/`, `installer/`, `docs/`, `tests/`, `tools/`) — Single Source of Truth
- **`2_Test/`, `3_Build/`, `4_Release/` liegen pro Rechner ausserhalb des Repos:** `2_Test/` = Testumgebung ohne Code (DB, INI, Songs, Skins), CWD beim Dev-Start. `3_Build/` = PyInstaller-Workspace, `4_Release/` = fertige ZIPs pro Version (`X.XX/`). `build.py` nimmt sie aus `CC_BUILD_DIR` und `CC_RELEASE_DIR`, ohne diese Variablen neben dem Klon.
- **Bauen**: `cd installer && python build.py` — erzeugt EXEs in 3_Build/, ZIPs in 4_Release/
- **3 ZIP-Typen**: Vollpaket (Neuinstallation), Update (ohne DB/INI/User-Ordner), Source-Code
- **Pre-Commit-Hook** (`.githooks/pre-commit`): Steckt `src/*.py` oder `src/*.json` im Commit, laufen `pyflakes` (falls in der venv), `tests/settings/test_settings_i18n.py`, `tests/settings/test_settings_reachable.py` (fehlende Uebersetzungen bzw. `SETTINGS_META`-Eintraege) und `tests/db/test_schema.py` (Update-Weg der DB von allen bekannten Altstaenden); schlaegt einer fehl, bricht der Commit ab. Einmal pro Klon aktivieren: `git config core.hooksPath .githooks`. Nimmt `.venv` sonst `python` aus dem PATH. Notfall: `git commit --no-verify`.
- **Tests** (`tests/`, nach Fachthema gruppiert, `pytest.ini` im Stamm): Ordnerliste in `CODING_STANDARDS.md`.

## Zusammenarbeit — Debugging-Regel

**Erst fragen, dann suchen.** Bevor ich bei einem unklaren Bug lange im Code recherchiere:
- Kurz beschreiben, was ich nicht verstehe
- Den User um eine Beschreibung oder einen Screenshot bitten
- Beweis aus der Praxis (P0.62): 20 Minuten Code-Analyse vs. 2 Sekunden Screenshot — der Screenshot hat gewonnen

Gilt besonders fuer: UI-Bugs, Layout-Probleme, unerwartetes Verhalten das schwer aus dem Code abzulesen ist.

## Audio-Prioritaet — Eiserne Regel (TIC-0025, v0.80)

**Ein aktiver AudioStream MUSS IMMER absolute Prioritaet haben.** Er darf NIE von UI-Operationen ausgehungert werden. Diese Regel hat Vorrang vor allen anderen Architektur-Entscheidungen. Jede Aktion, die >5 ms auf dem Main-Thread kosten KOENNTE, muss eines der Pflicht-Pattern verwenden.

- Architektur-Garantien und Pflicht-Pattern-Tabelle: `CODING_STANDARDS.md`, Abschnitt „Audio-Prioritaet".
- Herleitung (GIL), Diagnose-Werkzeuge und Vorgehen bei Aussetzern: `docs/19_audio_prioritaet.md`.

## Projektsprache — GLOSSARY.md

`GLOSSARY.md` liegt im Projektstamm und ist das Glossar der Projektsprache:
Figuren, Programme, Sequenzen, Songs, Abend-Begriffe — je mit dem gewaehlten
Begriff und den Varianten, die bewusst vermieden werden (`_Avoid_`).

- **Vor dem Benennen lesen.** Klassen, DB-Felder, UI-Texte, Commit-, Issue- und
  PR-Titel benutzen den Begriff aus `GLOSSARY.md`, nicht eine Variante aus dessen
  Avoid-Liste. Steht ein Begriff noch nicht drin, ist das ein Signal: entweder
  gibt es ihn im Projekt gar nicht, oder er fehlt im Glossar.
- **Neuer oder geschaerfter Begriff → sofort eintragen**, wie beim Changelog:
  solange er frisch ist, nicht erst vorm Release.
- **Glossar, kein Pflichtenheft.** Eine bis zwei Saetze je Begriff, keine
  Implementierungsdetails (keine Tabellen, keine Funktionsnamen, keine Ablaeufe).
- Die Datei bleibt im Projektstamm — dort suchen die Agenten-Werkzeuge sie.

## Subdokumente — wann was lesen

| Dokument | Inhalt | Lesen wenn … |
|---|---|---|
| `CODING_STANDARDS.md` | Pruefbare Regeln fuer Code | Vor jedem Schreiben oder Aendern von Code, im Code-Review |
| `docs/18_release.md` | Release-Ablauf in 7 Schritten, Bauen, ZIP-Typen | Release vorbereiten, bauen |
| `docs/19_audio_prioritaet.md` | Herleitung der Audio-Regel, Diagnose-Werkzeuge | Audio-Aussetzer, Main-Thread-Performance |
| `docs/12_erfahrungen.md` | Entwicklungsrichtlinien, Refactoring-Regeln, Fallstricke aus allen Prototypen | Refactoring, Architekturentscheidungen, unklares Verhalten, neue UI-Komponenten |
| `docs/07_datenmodell.md` | DB-Schema, Tabellenstruktur, Migrations-Historie | DB-Aenderungen, neue Felder, Abfragen |
| `docs/11_tech_stack.md` | Abhaengigkeiten, Build-Details, Paketversionen | Build-Probleme, neue Bibliotheken einbinden |
| `docs/05_ui_fenster_layout.md` | Dock-Struktur, Widget-Hierarchie, Layout-Entscheidungen | Neue Docks, Layout-Aenderungen, UI-Umstrukturierung |
| `docs/17_theming_icons.md` | Zentrales Icon-Set (`src/images/`), Theme-Farb-Keys (`icon_color`/`icon_color_input`/`title_icon`), Recolor-Mechanik | Icons aendern/hinzufuegen, Theme-Farben, Skin-Arbeit |
| `docs/01_audio_player.md` | Audio-Engine-Spezifikation, WSOLA, Loop-System | Aenderungen an der Audio-Pipeline |
| `docs/00_projektuebersicht.md` | Scope, Zielgruppe, Projektziele | Neue Feature-Ideen einordnen |
