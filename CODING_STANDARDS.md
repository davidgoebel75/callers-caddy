# Callers Caddy — Coding Standards

Regeln, die sich am Code pruefen lassen. **Vor dem Schreiben oder Aendern von Code lesen**, im Code-Review gezielt abhaken. Hintergrund und Herleitungen stehen in `docs/` (Verweise bei den Abschnitten).

## Sprache und Konventionen

- Sprache im Code: Englisch (Variablen, Methoden), Deutsch (Kommentare, UI-Texte)
- Begriffe aus `GLOSSARY.md` verwenden, nicht die Varianten aus dessen Avoid-Liste.
- **Song-Katalog** (`music-extended-data/music_extended_data.csv`, geladen über `song_catalog.py`): nicht von Hand editieren. Aktualisiert wird er per `tools/update_song_catalog.py`, das Davids Scraper-Update aufruft und als Auto-PR `chore/song-catalog-*` einreicht. Match-Verbesserungen gehören nach `song_match.py`.
- UI-Framework: PySide6 (Qt 6 Widgets), kein WebView
- DB: SQLite via built-in sqlite3
- Audio: Eigener Streaming-WSOLA (kein Rubber Band/SoundTouch)
- `app_dir`: Im Dev-Modus = `os.getcwd()` (2_Test/), im EXE-Modus = neben der EXE

## Modularisierung (BL-201)

`main.py` wurde bewusst von ~29.000 auf ~7.300 Zeilen entschlackt: eigenstaendige Widgets/Dialoge/Worker liegen jetzt in Themenmodulen unter `src/` (`player_widget.py`, `songdata_widget.py`, `playlist_widget.py`, `sequences_widget.py`, `potential_widget.py`, `loopfinder_widget.py`, `lyrics_widget.py`, `reports_widget.py`, `dialogs_location_program.py`; geteilte Helfer/SVGs/Konstanten in `ui_helpers.py`, Perf in `perf.py`). In `main.py` bleiben nur `P29MainWindow` (Orchestrator), `main()` und Start-Glue.

**Fachpakete (intern#220, `docs/adr/0001-fachpakete-in-src.md`):** Neue Module kommen in ein Fachpaket unter `src/caddy/` (Namen wie die Ordner in `tests/`; ein Thema ohne Testordner wie `camera/` bekommt ihn mit seinem ersten Test), bestehende ziehen erst um, wenn sie ohnehin angefasst werden. Erste Bewohner: `caddy/breaks/` (Pausen-Uhr), `caddy/camera/` (Foto) und `caddy/rules/` (Bedingungen und Aktionen der Regeln; `main.py` registriert nur). Import immer absolut (`from caddy.breaks.break_widget import BreakWidget`).
- Zustandslogik ohne Qt in ein eigenes Modul mit `QT_FREE = True` (Muster: Reducer `caddy/breaks/break_clock.py`, Widget ruft nur `reduce()`); `tests/app/test_qt_free.py` prueft, dass es nirgends PySide6 importiert. Ein Reducer nur bei wirklich verzwicktem Zustand, sonst einfacher Wert oder reine Funktion; nicht spuerbar langsamer werden, im Zweifel mit `tools/benchmark` messen (`docs/adr/0002-zustandslogik-als-reducer.md`).
- Beim Umzug alle Importe nachziehen, auch Lazy-Imports in Funktionen und `monkeypatch`-Strings in Tests (`git grep <altes_modul>`).

**Regel fuer Neuentwicklung:** Neue Widgets, Dialoge, Worker oder groessere Hilfslogik NICHT in `main.py` schreiben, sondern gleich in ein passendes bestehendes Modul oder ein neues `*_widget.py` / `dialogs_*.py`. Faustregeln:
- Module bleiben **zirkelfrei**: kein `import main` zur Ladezeit. Braucht ein Modul etwas aus `main` (z. B. `__version__`), per Lazy-Import in der Funktion holen (Muster `_app_version()` in `potential_widget.py`).
- Von mehreren Modulen genutzte Helfer/Konstanten/SVGs → nach `ui_helpers.py` (Blatt-Modul, haengt nur an perf/i18n/song_types/PySide6).
- DB-Methoden: `SongDatabase` in `song_db.py` erbt Themenbloecke aus Mixin-Modulen `song_db_*.py` (z. B. `song_db_potential.py`, intern#165). Neue Methoden in den passenden Block; Aufrufer nutzen immer nur `db.methode()`. Mixins haben kein eigenes `__init__`: Zustand, den sie brauchen (`self._conn`, `schema_problems`, Band-Cache), legt `SongDatabase.__init__` an. Mixins duerfen Methoden von `SongDatabase` aufrufen (z. B. `SchemaMixin` → `_insert_default_dance_programs()`). Konstanten aus `song_db` per Lazy-Import in der Methode holen.
- `main.py` importiert das Widget zurueck und verdrahtet es im Hauptfenster — wie die bestehenden `from *_widget import ...`-Zeilen.
- Beim Verschieben von Code **Decorator-Zeilen mitnehmen** (`@dataclass` etc.) — der AST-Startpunkt zeigt sonst auf `class`/`def`, nicht auf `@decorator`.
- Nach dem Aufteilen: `py_compile` + `pyflakes` (undefined = Fehler, unused imports trimmen), dann realer Import-Test.

## Auslieferung an Bestandsinstallationen

**Eine Aenderung an Daten oder Referenzen muss beim Update von selbst wirken.** Bestandskunden lesen keine Changelogs und klicken keinen Import an. Beim MS50-Umbau mussten Referenzdaten nachtraeglich von Hand importiert werden. Die meisten haben das nicht mitbekommen, es gab vermehrt Supportanfragen. Darum schon bei der Konzeption festlegen, wie die Loesung zu bestehenden DBs und INIs kommt, und eine Loesung bevorzugen, die im Code steckt:

- **Regel im Code** (z. B. Filterlogik) vor geaenderten Daten: wirkt ab der ersten Ausfuehrung, ohne Migration.
- **Neue Spalte:** nur ins `_CREATE_*`, `_add_missing_columns()` ergaenzt sie beim Start (`docs/12_erfahrungen.md`).
- **Daten-Korrektur:** idempotentes SQL in `_DATA_FIXES` (`song_db_schema.py`), laeuft bei jedem Start.
- **Referenzdaten (Calls, Programme, Teaching Order):** in `src/reference_calls.json` aendern und `REFERENCE_DATA_VERSION` erhoehen, `reseed_reference_data()` spielt sie beim naechsten Start ein. Eintraege, die nur im Code angelegt werden, loescht der Reseed.
- **Einmalige Heilung, die rechnen muss:** Start-Methode mit Flag in `app_meta` (Muster `_backfill_auto_mappings_once()`).
- **Neuer INI-Schluessel:** Standardwert im Code (`settings.value(key, default)`), kein Pflicht-Eintrag in der INI.

Braucht eine Loesung trotzdem einen Schritt des Anwenders (Import, Knopf), steht im Issue warum, und die App weist beim Start darauf hin. Ein Hinweis im Changelog allein reicht nicht. Tests fuer den Update-Weg von Altstaenden liegen in `tests/db/`.

## Audio-Prioritaet (TIC-0025, v0.80)

Die Eiserne Regel steht in `CLAUDE.md`, Herleitung und Diagnose in `docs/19_audio_prioritaet.md`.

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

## Bekannte Qt-Fallen

- **QDockWidget-Features nach restoreState()**: Qt's `restoreState()` ueberschreibt die Dock-Features (Movable/Floatable/Closable). Nach JEDEM `restoreState()`-Aufruf MUSS `_reapply_dock_features()` aufgerufen werden. Ohne diesen Aufruf verlieren Docks ihre Dock-Faehigkeiten im kompilierten Build. Bug trat 3x auf — IMMER beachten!

- **setFloating(True) kostet ~90ms pro Aufruf (Windows)**: Der erste `setFloating(True)`-Aufruf auf einem QDockWidget, der einen nativen Window-Handle anlegt, kostet auf Windows ~90ms (Fenster-Manager-Overhead). Die Kosten sind einmalig und "wandern" ins naechste Bucket wenn man sie per QTimer deferriert — Gesamtzeit bleibt gleich. Lazy-Docks (Placeholder-Pattern) sollten `setFloating(True)` und `restoreGeometry()` trotzdem per `QTimer.singleShot(0, ...)` nach `show()` verschieben, aber NICHT erwarten, dass damit die Gesamtladezeit sinkt. Die Ursache wurde in P0.62 gruendlich analysiert (4 Test-Runs).

- **StyleSheet haengt `setFont()` aus — Schriftgroesse IMMER per `font-size` im StyleSheet setzen**: Hat ein Widget ein StyleSheet gesetzt (schon ein blosses `color: …` reicht), ignoriert Qt spaetere `setFont()`/`setPixelSize()`-Aufrufe stillschweigend — die Schrift bleibt auf Standardgroesse. Das kostet jedes Mal eine Debug-Schleife. **Regel:** Wenn ein Widget ein StyleSheet hat und die Schriftgroesse dynamisch/berechnet ist, die Groesse ins selbe StyleSheet schreiben (`f"color: {c}; font-size: {px}px;"`), NICHT ueber `setFont()`. `QFontMetrics` zum Ausmessen ist ok — nur das Anwenden muss ueber das StyleSheet laufen. Trat u.a. bei BL-189 auf (dynamischer Header im `SequenceViewWidget`).

- **Event-Handler ueberschreiben (`mousePressEvent`, `mouseDoubleClickEvent`, `keyPressEvent` …) → `super()` aufrufen**: Qt fuehrt in seinem eigenen Handler Buch (gemerkter Klick-Index, Auswahl, Fokus). Faellt der Aufruf weg, stimmt dieser Zustand nicht mehr, und Folge-Events laufen falsch. Bei intern#213 loeste das Loslassen nach dem Doppelklick ein zweites `cellClicked` aus, das den gerade gestarteten Song neu lud und stoppte. Weglassen nur, wenn Qts Verhalten bewusst unterdrueckt werden soll, dann mit Kommentar.

- **QTableWidget-Pattern** (aus P27):
  ```python
  table.setUpdatesEnabled(False)
  table.setRowCount(0)
  table.setRowCount(n)
  for idx in range(n):
      table.setItem(idx, col, QTableWidgetItem(...))
  table.setUpdatesEnabled(True)
  ```

## Uebersetzungen (i18n)

- Texte laufen ueber `_t("key")` aus `src/translations.json`, jeder Key mit `de`, `en` und `ja`. `_t()` faellt still auf Deutsch zurueck — eine fehlende Sprache faellt also erst dem englischen oder japanischen Nutzer auf.
- Deutsche Texte, die der Nutzer sieht (`de` in `translations.json`, `CHANGELOG.md`), mit echten Umlauten und `ß` schreiben: „Größe“, „schließen“, nicht „Groesse“, „Grösse“ oder „schliessen“. Code, Kommentare und Commit-Messages bleiben ASCII.
- **Neuer INI-Schluessel → erscheint automatisch im Einstellungsdialog → `setting_label_<sektion>_<key>` + `setting_tip_<sektion>_<key>` in de/en/ja pflegen.** Combobox-Auswahltexte in `SETTINGS_META` in `_build_widget` per `_t()` uebersetzen (Muster `lyrics/dynamic_mode`). Test `tests/settings/test_settings_i18n.py` prueft das.

## Tests

Neue Tests in den passenden Fachordner unter `tests/`, nicht flach nach `tests/`: `app/` Infrastruktur, Dialoge, Architektur-Regeln · `assignments/` Zuordnung, Figuren-Menge · `db/` DB-Schema, Update-Weg von Altständen · `lyrics/` Lyrics, Singing-Abschnitte, Heads/Sides · `breaks/` Pausen-Uhr, Wartemusik · `playback/` Wiedergabe, Loop, Player · `rules/` Regeln (Trigger, Bedingungen, Aktionen) · `sequences/` Sequenzen, Filter, Import · `settings/` INI, Einstellungsdialog, Skins · `songs/` Song-Katalog, Metadaten, ZIP-Import, Playlist. Tests laufen aus dem Stamm, aus `tests/` und aus jedem Unterordner.

- **Widgets und Test-DBs gehen durch die Fixture `keep`** (`tests/conftest.py`), die sie am Testende abraeumt. Was liegen bleibt, sammelt ein spaeterer `gc.collect()` an zufaelliger Stelle ein, und die volle Suite stuerzt nur auf manchen Rechnern ab (PR #119). `tests/app/test_keep_regel.py` prueft `SongDatabase(...)` und `deleteLater()` mechanisch; Widgets bleiben Sache des Reviews.
- **Mutation Testing** (mutmut, lokal bei Bedarf) prueft, ob Tests ein Ergebnis wirklich pruefen statt es nur auszufuehren. Einrichtung, Ablauf und Windows-Fallen stehen in `setup.cfg`.
