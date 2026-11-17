# Callers-Caddy Performance-Benchmark

Unbeaufsichtigter Runner, der das **echte** Hauptfenster in-process hochfährt,
einen typischen Nutzer-Ablauf abspielt, jeden Schritt misst und die Zahlen als
**JSON** ablegt — damit sich Läufe (vorher/nachher, leere vs. volle DB) per
Skript vergleichen lassen.

Ersetzt die bisherige manuelle Code-Fummelei bei jedem Perf-Test.
Design/Doku: **Issue davidgoebel75/callers-caddy-intern#72**.

## Warum das nicht im ausgelieferten Code liegt

Alles hier unter `tools/` ist in `installer/build.py` als `EXCLUDE_DIR` geführt
und liegt außerhalb des gebauten `src/`. Der Benchmark landet also **weder im
EXE noch im Release-ZIP**. Im App-Code selbst gibt es nur minimale „Test-Nähte"
(stabile `objectName`s, vereinzelt ein Signal) — die gesamte Szenario- und
Auswertungslogik lebt hier extern.

## Aufruf

Mit demselben Python wie der Dev-Start (siehe `C:\Git\run-cc-dev.bat`):

```bash
python tools/benchmark/run_benchmark.py --db "C:\pfad\zur.db" --label "vor Fix X"
```

Danach vergleichen:

```bash
python tools/benchmark/compare.py results/vorher.json results/nachher.json
```

Gegen die **eingecheckte Baseline** vergleichen (in `baselines/`, env-bereinigt):

```bash
python tools/benchmark/compare.py baselines/baseline_v0.162.json results/<dein-lauf>.json
```

Aktuelle Baseline ist **v0.162** (Stand vor Release 2.0, Median aus 5 Läufen).
`baseline_v0.158.json` bleibt als ältere Vergleichsbasis liegen.

### Parameter

| Flag | Bedeutung |
|------|-----------|
| `--db PATH` | Zu testende DB. **Frei wählbar** → leere vs. volle DB vergleichbar. Ohne Angabe: leere DB. |
| `--label "…"` | Label des Laufs (landet im JSON, im Dateinamen und in der Vergleichstabelle). |
| `--repeat N` | Anzahl Durchläufe (Median-Auswertung folgt). |
| `--out DIR` | Ausgabeordner der JSON-Reports (Default: `results/`). |
| `--perf-log` | Zusätzlich das in-App `perf.py`-Log (`logs/perf/`) schreiben. |

## Wie die DB-Wahl ohne App-Änderung funktioniert

Callers Caddy leitet DB und INI aus dem **Arbeitsverzeichnis** ab
(`PathManager`: `<cwd>/callers_caddy.db`). Der Runner legt darum ein
Sandbox-cwd (`.sandbox/`) an, kopiert die gewünschte DB dort als
`callers_caddy.db` hinein und wechselt **vor** dem Import von `main.py` hinein.
Damit ist `--db` frei wählbar, und der Single-Instance-Lock (hängt ebenfalls am
cwd) kollidiert nicht mit einer echten laufenden Instanz.

## „Erstbevölkerung" der Sandbox = echte Einstellungen

Damit die Zahlen dem entsprechen, was im Alltag **gefühlt** erlebt wird, klont
der Runner die echte INI des Quellordners (Default: `callers_caddy.ini` neben
`--db`, überschreibbar mit `--settings`) — also Audio-Gerät, MMCSS, Feed-Ahead,
Skin, Layout usw. Einzige Anpassung: relative `[paths]` (Musik, Lyrics …) werden
absolut gegen den Quellordner aufgelöst, weil das Arbeitsverzeichnis wechselt.

> Play (Schritt 4) öffnet damit das **echte Audiogerät** und gibt kurz Ton aus.

**Headless-Ausnahmen:** Rein interaktive Modal-Dialoge lassen sich unbeaufsichtigt
nicht fahren. Daher setzt der Runner `feedback/enabled=false` (der Feedback-Dialog
beim Stop ist UX, kein Performance-Pfad) und hält einen Timer bereit, der
unerwartete Modal-/Popup-Dialoge (Tutorial, Bestätigungen …) automatisch
schließt. Ein Watchdog dumpt zudem den Stack, falls ein Schritt >60 s hängt.

## Szenario-Schritte

| # | Schritt | Status |
|---|---------|--------|
| 1 | App-Start (Teilphasen: QApplication, Import, Window-Init, Show) | ✅ v1 |
| 2 | Songliste: Suche je Referenz-Song | ✅ v1 |
| 3 | Song auswählen (Tu Es Foutu) → laden | ✅ v1 |
| 4 | Play (Play-Latenz bis `is_playing`) | ✅ v1 |
| 5 | Stop (bis `is_playing`=false) | ✅ v1 |
| 6 | Lokation wählen (`_set_current_location`, Dialog umgangen) | ✅ v1 |
| 7 | Sequenz-Widget aufbauen (`load_sequences`) | ✅ v1 |
| 8 | Sequenzen filtern (Contains) | ✅ v1 |
| 9 | Programm wechseln (`sequences_program_switch`) und Limit wechseln (`sequences_limit_switch`), je Durchlauf andere Auswahl → kein Cache-Treffer (intern#111). Bei einer Lokation mit nur 2 Bändern gibt es 2 Teilmengen — ab dem 3. Durchlauf misst `program_switch` dann den Cache, die neuen Werte stehen in `samples_ms` vorn | ✅ v1 |

**Singing-Block** (nach Schritt 8) mit dem voll gepflegten „Sounds Of Silence":

| Schritt | was | Status |
|---|---|---|
| `song_select_singing` | Auswahl → lädt Audio **+ Lyrics + SyncPoints** | ✅ v1 |
| `song_play_singing` / `song_stop_singing` | Play/Stop des Singing-Calls | ✅ v1 |
| `lyrics_dynamic_on` / `_off` | Dynamic-Lyrics (BL-173): Figuren-Text ↔ Sequenzen | ✅ v1 |

Dynamic-Lyrics braucht Lyrics+Sync+Figuren+Sequenzen; fehlt eine Voraussetzung,
steht der Grund in `meta.gating` und der Schritt ist `ok:false`. Dafür zeigt der
Runner die Daten-Verzeichnisse (`lyrics`, `playlists`, `import`) auf die echten
Quellordner, sofern sie existieren.

Mit `--repeat N` werden die interaktiven Schritte N-mal gefahren und je Schritt
der **Median** berichtet (`meta.samples_ms` listet die Einzelwerte); Schritt 1
(Start) bleibt einmalig, da der Prozess einmal hochfährt.

Jeder weitere Schritt wird inkrementell ergänzt; die dafür nötige CC-Naht wird
beim Bau im Issue #72 dokumentiert.

### Referenz-Songs

Feste, voll gepflegte Songs (Lyrics/Sync/Sequenzen), weit genug unten für eine
realistische Suche — in `TARGETS` (oben in `run_benchmark.py`) definiert:

| Typ | Titel | Suchbegriff | ~Treffer |
|-----|-------|-------------|----------|
| Patter | Tu Es Foutu | `tu` | ~12 |
| Singing | Sounds Of Silence | `sound` | ~3 |

Setzt eine DB voraus, die diese Songs enthält (Davids Bestand). Fehlt ein Song,
wird der Schritt als `ok:false` markiert und läuft weiter.

## Hinweis zu den Startup-Zahlen

Die Startup-Teilphasen misst der Runner selbst um den echten
`P29MainWindow`-Bau herum (er ruft bewusst nicht `main()` auf, um Lock/`sys.exit`
zu vermeiden). Die in-App `perf.py`-Session-Marken bleiben die Referenz für den
ausgelieferten Startpfad und lassen sich mit `--perf-log` zusätzlich mitschreiben.

### Doppelgänger-Prüfung beim Start (intern#106)

Teil von `startup_window_init`, zusätzlich einzeln ausgewiesen:

| Schritt | misst |
|---|---|
| `startup_repair106_check` | `find_pairs` — die Prüfung, die bei **jedem** Start läuft |
| `startup_repair106_total` | kompletter Aufruf inkl. Sicherung, Zusammenführen und Playlist-Umschreiben |

`meta` enthält Songs, Dateiprüfungen (Anzahl + Zeit) und gefundene Paare. Gemessen
wird ohne CC-Naht: der Runner umwickelt die Modul-Funktionen vor dem Fenster-Init.
Fehlt das Modul (älterer Stand), entfallen beide Schritte.

## JSON-Format

```json
{
  "run":  { "timestamp": "...", "cc_version": "...", "label": "vor Fix X", "db": "...", "repeat": 1 },
  "env":  { "os": "...", "python": "...", "cpu": "...", "cc_header": [ "..." ] },
  "steps": [
    { "name": "startup_total",   "ms": 2840.0, "ok": true },
    { "name": "songlist_search", "ms": 42.0,   "ok": true, "meta": { "query": "...", "treffer": 12 } }
  ]
}
```

`compare.py` matcht Schritte per `name` und zeigt Delta + % gegen die Baseline
(erster übergebener Report).

## Vorgehen und Learnings (Performancetest vor Release 2.0, 2026-11-17)

Bewährter Ablauf für den „üblichen Performancetest“ und was dabei aufgefallen ist.
Befunde: intern#46, intern#256; Fix: callers-caddy#178.

### Ablauf

1. **Hauptlauf:** `--repeat 5` gegen die 2_Test-DB, dann `compare.py` gegen die
   aktuelle Baseline **und** den letzten Lauf in `results/`.
2. **Ursachen suchen:** denselben Lauf unter cProfile fahren
   (`python -m cProfile -o bench.prof tools/benchmark/run_benchmark.py …`) und die
   Aufrufbäume der auffälligen Schritte auswerten. cProfile bremst hier kaum, weil
   die meiste Zeit in Qt/C liegt.
3. **Start aufschlüsseln:** `--perf-log` liefert die in-App-Marken
   (`.sandbox/logs/perf/`). Für den Fensteraufbau ist das die verlässliche Quelle.
4. **Alltag gegenprüfen:** die Perf-Logs aus `2_Test/logs/perf/` tabellieren
   (`__init__ GESAMT`, `Docks + Tutorials`, `Layout restore`). Sie zeigen, ob eine
   Benchmark-Abweichung auch im echten Start auftritt.
5. **Fix gezielt prüfen:** ein kleines Skript im Scratchpad, das `prepare_sandbox`,
   `boot` und `Bench` aus `run_benchmark.py` importiert und nur das betroffene
   Szenario fährt. Messgröße für Hänger: die **längste Lücke zwischen zwei
   `processEvents()`**. Immer mit Gegenprobe ohne Fix (`git stash`).

### Learnings

- **Nicht nur den Median lesen, auch `samples_ms`.** Der ~1-s-Hänger des
  Evening-Planner-Vorbaus war im Median von `lyrics_dynamic_on` (25 ms)
  unsichtbar. Er stand nur als Einzelwert (894 ms / 1089 ms) in den Samples.
- **Ausreißer an fester Position im Lauf → zeitgesteuerte Timer nach dem Start
  verdächtigen.** `QTimer.singleShot(3000, …)` fällt in irgendeinen Messschritt,
  der dann teuer aussieht, obwohl er selbst unschuldig ist.
- **Der erste Import schwerer Bibliotheken ist ein versteckter Hänger.**
  `numpy` + `scipy.signal`/`optimize` kosten beim ersten Mal ~1,2 s im
  GUI-Thread. Lokale Imports verschieben nur den Zeitpunkt. Vorbauten dürfen
  darum nie während der Wiedergabe laufen (`engine.is_playing()` prüfen).
- **cProfile ist bei PySide-Konstruktoren unzuverlässig.** `P29MainWindow.__init__`
  zeigte 49 ms bei gemessenen ~650 ms. Für den Start `--perf-log` nehmen.
- **Start wird nur einmal je Prozess gemessen.** Für Aussagen zum Start mindestens
  zwei Läufe vergleichen. Kaltstarts (erster Start des Tages) sind 2–3× langsamer,
  fast ganz in der Import-Phase. Das liegt an Datenträger/Virenscanner, nicht am Code.
- **Versteckte Docks hören trotzdem auf Signale.** `notes_widget.refresh` baut beim
  Lokationswechsel alle Zeilen neu, auch bei verstecktem Dock. Bei der Suche nach
  Kandidaten für Caching/Verzögern auf Signal-Handler versteckter Widgets achten,
  nicht nur auf den Aufbau beim Start.
- **Audiogerät vor dem Lauf prüfen.** „Stream-Init fehlgeschlagen … Fallback auf
  System-Standard“ im Log heißt: Gerät aus oder belegt. Dann misst Play gegen das
  falsche Gerät.
- **Die Sandbox klont die echte INI seit 2026-09-14** (auch für Baseline v0.158).
  Ein Unterschied in den Startzahlen lässt sich damit nicht erklären.
