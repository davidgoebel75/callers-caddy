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

## Szenario-Schritte

| # | Schritt | Status |
|---|---------|--------|
| 1 | App-Start (Teilphasen: QApplication, Import, Window-Init, Show) | ✅ v1 |
| 2 | Songliste: Patter-Filter + Suche | ✅ v1 |
| 3 | Song auswählen (nicht ganz oben) | ⏳ folgt |
| 4 | Play (Play-Latenz) | ⏳ folgt |
| 5 | Stop | ⏳ folgt |
| 6 | Lokation wählen | ⏳ folgt |
| 7 | Sequenz-Widget aufbauen | ⏳ folgt |
| 8 | Sequenzen filtern | ⏳ folgt |

Jeder weitere Schritt wird inkrementell ergänzt; die dafür nötige CC-Naht wird
beim Bau im Issue #72 dokumentiert.

## Hinweis zu den Startup-Zahlen

Die Startup-Teilphasen misst der Runner selbst um den echten
`P29MainWindow`-Bau herum (er ruft bewusst nicht `main()` auf, um Lock/`sys.exit`
zu vermeiden). Die in-App `perf.py`-Session-Marken bleiben die Referenz für den
ausgelieferten Startpfad und lassen sich mit `--perf-log` zusätzlich mitschreiben.

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
