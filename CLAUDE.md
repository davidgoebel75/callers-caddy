# Callers Caddy — Projektanweisungen

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
- **Release — Reihenfolge IMMER:**
  1. Auf `develop`: Versions-Bump + Changelog (siehe PFLICHT-DOPPELPACK), committen, pushen.
  2. Pull Request `develop` → `main` anlegen: `gh pr create --base main --head develop --title "Release 0.XX"`. Tests abwarten.
  3. Mergen mit **„Create a merge commit"** — NIE „Squash and merge", NIE „Rebase and merge". Sonst verliert Git die Verbindung zwischen `develop` und `main`, und der naechste Release-PR bringt alte Commits doppelt plus Konflikte.
  4. `main` holen (`git switch main && git pull`), bauen (siehe Build-Regel).
  5. Build pruefen: `python installer/check_release.py <alt> <neu>` (mit `CC_RELEASE_DIR` wie beim Build). Vergleicht ZIP-Groessen mit der Vorversion, sucht Nutzerdaten im Update-ZIP, gleicht Skins mit `main` ab und prueft die Version. Nur Code geaendert ⇒ ZIPs wachsen kaum (0.158→0.159: +0,1 MB).
  6. Nach Davids Test am gebauten Paket Tag setzen: `git tag -a 0.XX -m "Release 0.XX"` und `git push origin 0.XX` (Format wie `0.151`, ohne `v`).
- **Versions-Bump NIE erst auf `main`:** Dann fehlt er auf `develop`, und der naechste Release-PR kollidiert in `CHANGELOG.md`.
- Nach dem Release steht `main` einen Commit vor `develop` (der Merge-Commit) — normal, nichts zu tun.

## Versions-Bump — PFLICHT-DOPPELPACK

**Die Versionsnummer steht an ZWEI Stellen — beide gleichzeitig pflegen:**
1. `1_Source/src/main.py` → `__version__ = "0.XX"`  ← **`build.py` liest die Version VON HIER**
2. `CHANGELOG.md` → neuer Abschnitt oben

**Reihenfolge IMMER:** erst `main.py` aendern, dann `CHANGELOG.md` aendern, DANN bauen. Sonst baut `build.py` stillschweigend mit der alten Versionsnummer und alle ZIPs landen im falschen Ordner — das ist hier schon mehrfach passiert. Wenn unsicher: vor dem Build `grep __version__ 1_Source/src/main.py` und mit `CHANGELOG.md` oberstem Eintrag vergleichen.

## Build-Regel

**EXEs und ZIPs (build.py) IMMER erst nach Rueckfrage erstellen!** Der Build dauert ~1 Minute und ist oft ueberfluessig. Erst fragen: "Soll ich jetzt bauen?" — nicht automatisch nach Code-Aenderungen starten.

## Modularisierung — direkt beim Entwickeln (BL-201)

`main.py` wurde bewusst von ~29.000 auf ~7.300 Zeilen entschlackt: eigenstaendige Widgets/Dialoge/Worker liegen jetzt in Themenmodulen unter `src/` (`player_widget.py`, `songdata_widget.py`, `playlist_widget.py`, `sequences_widget.py`, `potential_widget.py`, `loopfinder_widget.py`, `lyrics_widget.py`, `break_photo_widget.py`, `reports_widget.py`, `dialogs_location_program.py`; geteilte Helfer/SVGs/Konstanten in `ui_helpers.py`, Perf in `perf.py`). In `main.py` bleiben nur `P29MainWindow` (Orchestrator), `main()` und Start-Glue.

**Regel fuer Neuentwicklung:** Neue Widgets, Dialoge, Worker oder groessere Hilfslogik NICHT in `main.py` schreiben, sondern gleich in ein passendes bestehendes Modul oder ein neues `*_widget.py` / `dialogs_*.py`. Faustregeln:
- Module bleiben **zirkelfrei**: kein `import main` zur Ladezeit. Braucht ein Modul etwas aus `main` (z. B. `__version__`), per Lazy-Import in der Funktion holen (Muster `_app_version()` in `potential_widget.py`).
- Von mehreren Modulen genutzte Helfer/Konstanten/SVGs → nach `ui_helpers.py` (Blatt-Modul, haengt nur an perf/i18n/PySide6).
- `main.py` importiert das Widget zurueck und verdrahtet es im Hauptfenster — wie die bestehenden `from *_widget import ...`-Zeilen.
- Beim Verschieben von Code **Decorator-Zeilen mitnehmen** (`@dataclass` etc.) — der AST-Startpunkt zeigt sonst auf `class`/`def`, nicht auf `@decorator`.
- Nach dem Aufteilen: `py_compile` + `pyflakes` (undefined = Fehler, unused imports trimmen), dann realer Import-Test.

## Ordnerstruktur (5-Stufen-Pipeline)

```
Callers-Caddy/
├── 1_Source/          Code (Single Source of Truth)
│   ├── src/           Python-Quellcode
│   ├── installer/     Build-Skripte (spec, clean_db, build.py)
│   └── docs/          Dokumentation + Backlog
├── 2_Test/            Testumgebung (DB, Songs, Lyrics, INI)
│   └── run_test.bat   Startet App im Dev-Modus (CWD = 2_Test/)
├── 3_Build/           PyInstaller-Workspace (wird bei Build geleert)
├── 4_Release/         Fertige ZIPs pro Version
│   └── X.XX/          Vollpaket + Update + Source ZIP
└── _archive/          Prototypen, alte Versionen (nicht aktiv)
```

## Entwicklungs-Workflow

- **Quellcode lebt in `1_Source/src/`** — Single Source of Truth
- **Testen**: `2_Test/run_test.bat` ausfuehren (startet main.py mit CWD = 2_Test/)
- **Bauen**: `cd 1_Source/installer && python build.py` — erzeugt EXEs in 3_Build/, ZIPs in 4_Release/
- **3 ZIP-Typen**: Vollpaket (Neuinstallation), Update (ohne DB/INI/User-Ordner), Source-Code
- Prototypen-Ordner in `_archive/` sind nicht mehr aktiv
- Nach Abnahme: CHANGELOG.md aktualisieren
- **Pre-Commit-Hook** (`.githooks/pre-commit`): Steckt `src/*.py` oder `src/*.json` im Commit, laufen `tests/settings/test_settings_i18n.py` und `tests/settings/test_settings_reachable.py` (fehlende Uebersetzungen bzw. `SETTINGS_META`-Eintraege); schlaegt einer fehl, bricht der Commit ab. Einmal pro Klon aktivieren: `git config core.hooksPath .githooks`. Nimmt `.venv` sonst `python` aus dem PATH. Notfall: `git commit --no-verify`.
- **Tests** (`tests/`, nach Fachthema gruppiert, `pytest.ini` im Stamm): `app/` Infrastruktur, Dialoge, Architektur-Regeln · `assignments/` Zuordnung, Figuren-Menge · `db/` DB-Schema, Update-Weg von Altständen · `lyrics/` Lyrics, Singing-Abschnitte, Heads/Sides · `playback/` Wiedergabe, Pausen-Uhr, Wartemusik · `sequences/` Sequenzen, Filter, Import · `settings/` INI, Einstellungsdialog, Skins · `songs/` Song-Katalog, Metadaten, ZIP-Import, Playlist. Neue Tests in den passenden Ordner, nicht flach nach `tests/`. Laufen aus dem Stamm, aus `tests/` und aus jedem Unterordner.

## Fallback-Sicherung (PFLICHT)

**VOR jeder riskanten Aenderung** (Audio-Engine, WSOLA, Kern-Logik) ein Backup anlegen:
- **Zielordner**: `1_Source/src/_fallback/`
- **Befehl**: `cp src/DATEI.py src/_fallback/DATEI.py.bak`
- **Restore**: `cp src/_fallback/DATEI.py.bak src/DATEI.py`
- Backup IMMER erstellen bevor Code geaendert wird — nicht erst nach dem Fehler
- Falls ein Test fehlschlaegt: sofort aus `_fallback/` wiederherstellen statt raten
- Zusaetzlich: Letztes stabiles Release liegt als ZIP in `4_Release/` (Code-ZIP)

## Zusammenarbeit — Debugging-Regel

**Erst fragen, dann suchen.** Bevor ich bei einem unklaren Bug lange im Code recherchiere:
- Kurz beschreiben, was ich nicht verstehe
- Den User um eine Beschreibung oder einen Screenshot bitten
- Beweis aus der Praxis (P0.62): 20 Minuten Code-Analyse vs. 2 Sekunden Screenshot — der Screenshot hat gewonnen

Gilt besonders fuer: UI-Bugs, Layout-Probleme, unerwartetes Verhalten das schwer aus dem Code abzulesen ist.

## Audio-Prioritaet — Eiserne Regel (TIC-0025, v0.80)

**Ein aktiver AudioStream MUSS IMMER absolute Prioritaet haben.** Er darf NIE von UI-Operationen ausgehungert werden. Diese Regel hat Vorrang vor allen anderen Architektur-Entscheidungen.

### Hintergrund

Python's GIL bedeutet: jede laengere Operation auf dem Main-Thread (UI-Timer, Event-Handler, Rule-Actions) blockiert den Audio-Callback, weil sounddevice's PortAudio-Callback ebenfalls den GIL braucht. Andere Audio-Programme (C/C++) haben dieses Problem nicht — bei uns muss die Architektur das aktiv kompensieren.

### Architektur-Garantien (NICHT brechen)

1. **`_feed_stretcher()` laeuft im dedizierten `AudioFeeder`-Daemon-Thread** (siehe `audio_engine.py`). NICHT vom UI-Timer aus aufrufen. Falls eine neue Stelle Feeding triggern muss: stattdessen sicherstellen, dass `playing/paused` korrekt gesetzt sind — der Feeder kuemmert sich selbst.
2. **`FEED_AHEAD_SECONDS = 5.0`** — Stretcher puffert 5 s vor. Diesen Wert NIE reduzieren ohne explizite Genehmigung. 5 s sind die Toleranzgrenze gegen Main-Thread-Blockaden, nicht eine willkuerlich grosse Zahl.
3. **State-Updates (`_feed_pos`, `audio_data`, `stretcher`) IMMER unter `self._lock`** in `AudioEngine`. Race-Conditions zwischen Feeder-Thread und Main-Thread sind sonst garantiert.

### Pflicht-Pattern fuer neue Rule-Aktionen / UI-Handler

Jede neue Aktion, die >5 ms auf dem Main-Thread kosten KOENNTE, muss eines dieser Muster verwenden:

| Kosten-Quelle | Pflicht-Pattern | Beispiel |
|---|---|---|
| Qt-Layout (`restoreState`, `restoreGeometry`, `setFloating`) | `QTimer.singleShot(0, lambda: self._foo_deferred(params))` | `_rule_layout_load`, `_rule_dual_view_toggle` |
| Blockierender C-Call (`winsound.Beep`, `time.sleep`, lange `subprocess`) | `threading.Thread(target=..., daemon=True).start()` | `_rule_system_ping` |
| Grosse Tabellen-Updates (>50 Zeilen) | Diff-basiert: `_row_by_id`-Dict, nur geaenderte Zellen schreiben | `SongListWidget.set_last_played_map` |
| DB-Heavy-Operationen (>20 ms) | `QThread` mit Signal-Completion (NIE direkt im Trigger) | `BpmWorker`, `LoopFinderWorker` |
| Periodische UI-Refreshes | Throttling, oder `QTimer.singleShot` zur Entkopplung | (siehe `_refresh_last_played`) |

### Diagnose-Werkzeuge

- **Rules-Aktions-Timing** (ab v0.78): `1_Source/src/rule_engine.py._execute_actions` misst jede Action und schreibt `[Xms]` in `rules/rules.log`. Alles ueber 5 ms ist verdaechtig, alles ueber 50 ms ist ein Bug.
- **Perf-Log** (`perf_log.txt`): Main-Thread-Operationen mit Timing. Suche nach Eintraegen > 50 ms.
- **der i5-6500 eines Users (2015)** ist unser Referenz-Worstcase. Aktionen die auf dem Desktop 30 ms kosten, kosten dort schnell 100+ ms.

### Wenn ein neuer Audio-Aussetzer-Bug auftritt

1. **Erst Rules-Log pruefen** (`rules/rules.log`): gibt es eine Action mit > 50 ms genau vor dem Aussetzer?
2. **Dann Perf-Log pruefen**: gibt es eine Main-Thread-Operation > 50 ms im Zeitfenster?
3. **Dann erst Audio-Engine anfassen** — die Engine selbst ist seit v0.80 robust. 99% aller Aussetzer-Ursachen liegen im Main-Thread, nicht in der Engine.

## Bekannte Qt-Fallen

- **QDockWidget-Features nach restoreState()**: Qt's `restoreState()` ueberschreibt die Dock-Features (Movable/Floatable/Closable). Nach JEDEM `restoreState()`-Aufruf MUSS `_reapply_dock_features()` aufgerufen werden. Ohne diesen Aufruf verlieren Docks ihre Dock-Faehigkeiten im kompilierten Build. Bug trat 3x auf — IMMER beachten!

- **setFloating(True) kostet ~90ms pro Aufruf (Windows)**: Der erste `setFloating(True)`-Aufruf auf einem QDockWidget, der einen nativen Window-Handle anlegt, kostet auf Windows ~90ms (Fenster-Manager-Overhead). Die Kosten sind einmalig und "wandern" ins naechste Bucket wenn man sie per QTimer deferriert — Gesamtzeit bleibt gleich. Lazy-Docks (Placeholder-Pattern) sollten `setFloating(True)` und `restoreGeometry()` trotzdem per `QTimer.singleShot(0, ...)` nach `show()` verschieben, aber NICHT erwarten, dass damit die Gesamtladezeit sinkt. Die Ursache wurde in P0.62 gruendlich analysiert (4 Test-Runs).

- **StyleSheet haengt `setFont()` aus — Schriftgroesse IMMER per `font-size` im StyleSheet setzen**: Hat ein Widget ein StyleSheet gesetzt (schon ein blosses `color: …` reicht), ignoriert Qt spaetere `setFont()`/`setPixelSize()`-Aufrufe stillschweigend — die Schrift bleibt auf Standardgroesse. Das kostet jedes Mal eine Debug-Schleife. **Regel:** Wenn ein Widget ein StyleSheet hat und die Schriftgroesse dynamisch/berechnet ist, die Groesse ins selbe StyleSheet schreiben (`f"color: {c}; font-size: {px}px;"`), NICHT ueber `setFont()`. `QFontMetrics` zum Ausmessen ist ok — nur das Anwenden muss ueber das StyleSheet laufen. Trat u.a. bei BL-189 auf (dynamischer Header im `SequenceViewWidget`).

## Projektsprache — CONTEXT.md

`CONTEXT.md` liegt im Projektstamm und ist das Glossar der Projektsprache:
Figuren, Programme, Sequenzen, Songs, Abend-Begriffe — je mit dem gewaehlten
Begriff und den Varianten, die bewusst vermieden werden (`_Avoid_`).

- **Vor dem Benennen lesen.** Klassen, DB-Felder, UI-Texte, Commit-, Issue- und
  PR-Titel benutzen den Begriff aus `CONTEXT.md`, nicht eine Variante aus dessen
  Avoid-Liste. Steht ein Begriff noch nicht drin, ist das ein Signal: entweder
  gibt es ihn im Projekt gar nicht, oder er fehlt im Glossar.
- **Neuer oder geschaerfter Begriff → sofort eintragen**, wie beim Changelog:
  solange er frisch ist, nicht erst vorm Release.
- **Glossar, kein Pflichtenheft.** Eine bis zwei Saetze je Begriff, keine
  Implementierungsdetails (keine Tabellen, keine Funktionsnamen, keine Ablaeufe).
- Die Datei bleibt im Projektstamm — dort suchen die Agenten-Werkzeuge sie.

## Subdokumente — wann was lesen

Die Details stehen in `1_Source/docs/`. **Vor jeder Arbeit den passenden Abschnitt lesen:**

| Dokument | Inhalt | Lesen wenn … |
|---|---|---|
| `12_erfahrungen.md` | Entwicklungsrichtlinien, Refactoring-Regeln, Fallstricke aus allen Prototypen | Refactoring, Architekturentscheidungen, unklares Verhalten, neue UI-Komponenten |
| `backlog.md` | Alle offenen Features und Bugs | Neue Aufgabe beginnen, pruefen ob Feature bereits erfasst ist |
| `07_datenmodell.md` | DB-Schema, Tabellenstruktur, Migrations-Historie | DB-Aenderungen, neue Felder, Abfragen |
| `11_tech_stack.md` | Abhaengigkeiten, Build-Details, Paketversionen | Build-Probleme, neue Bibliotheken einbinden |
| `05_ui_fenster_layout.md` | Dock-Struktur, Widget-Hierarchie, Layout-Entscheidungen | Neue Docks, Layout-Aenderungen, UI-Umstrukturierung |
| `17_theming_icons.md` | Zentrales Icon-Set (`src/images/`), Theme-Farb-Keys (`icon_color`/`icon_color_input`/`title_icon`), Recolor-Mechanik | Icons aendern/hinzufuegen, Theme-Farben, Skin-Arbeit |
| `01_audio_player.md` | Audio-Engine-Spezifikation, WSOLA, Loop-System | Aenderungen an der Audio-Pipeline |
| `00_projektuebersicht.md` | Scope, Zielgruppe, Projektziele | Neue Feature-Ideen einordnen |
| `perf_logs/INDEX.md` | Sammelordner fuer alle Startup-Perf-Logs (alle Maschinen). Neue Logs einfach als `.txt` in `1_Source/docs/perf_logs/` ablegen und Zeile in INDEX.md ergaenzen — keine Nummerierung noetig. | Performance-Vergleich, Regression pruefen, neue Messung archivieren |

## Uebersetzungen (i18n)

- Texte laufen ueber `_t("key")` aus `src/translations.json`, jeder Key mit `de`, `en` und `ja`. `_t()` faellt still auf Deutsch zurueck — eine fehlende Sprache faellt also erst dem englischen oder japanischen Nutzer auf.
- **Neuer INI-Schluessel → erscheint automatisch im Einstellungsdialog → `setting_label_<sektion>_<key>` + `setting_tip_<sektion>_<key>` in de/en/ja pflegen.** Combobox-Auswahltexte in `SETTINGS_META` in `_build_widget` per `_t()` uebersetzen (Muster `lyrics/dynamic_mode`). Test `tests/settings/test_settings_i18n.py` prueft das.

## Technische Konventionen

- Sprache im Code: Englisch (Variablen, Methoden), Deutsch (Kommentare, UI-Texte)
- **Song-Katalog** (`music-extended-data/music_extended_data.csv`, geladen über `song_catalog.py`): nicht von Hand editieren. Aktualisiert wird er per `tools/update_song_catalog.py`, das Davids Scraper-Update aufruft und als Auto-PR `chore/song-catalog-*` einreicht. Match-Verbesserungen gehören nach `song_match.py`.
- UI-Framework: PySide6 (Qt 6 Widgets), kein WebView
- DB: SQLite via built-in sqlite3
- Audio: Eigener Streaming-WSOLA (kein Rubber Band/SoundTouch)
- `app_dir`: Im Dev-Modus = `os.getcwd()` (2_Test/), im EXE-Modus = neben der EXE
- QTableWidget-Pattern (aus P27):
  ```python
  table.setUpdatesEnabled(False)
  table.setRowCount(0)
  table.setRowCount(n)
  for idx in range(n):
      table.setItem(idx, col, QTableWidgetItem(...))
  table.setUpdatesEnabled(True)
  ```
