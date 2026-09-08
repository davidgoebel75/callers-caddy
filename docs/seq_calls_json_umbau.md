# Sequenz-Datenmodell: Umstellung auf `calls_json` (Option C)

**Ziel:** Die harte Grenze von 15 Calls pro Sequenz (`field_1 … field_15`)
aufheben — zukunftssicher und **kompatibel mit bereits verteilten Callers-Caddy-
Versionen**.

## Problem (mit Zahlen)

- Speicher ist `sequences.field_1 … field_15` → harte Grenze **15 Calls**.
- Im Ceder-Scrape (Stand 2026-08-23): **549 von 10.018 Sequenzen (5,5 %) haben
  >15 Calls** (max 34). **Kein einziger Singing Call (Corner Progression)** ist
  betroffen — nur Patter-Typen (Static Set Resolve etc.). Singing bleibt also
  immer ≤15; das Problem betrifft die „freien Module".
- `import_to_db.py` schneidet bisher hart auf 15 ab (`calls[:15]`).

## Lösung (Option C)

- Neue Spalte `sequences.calls_json TEXT` = **volle Callliste** als JSON-Array
  (Source of Truth der neuen App).
- `field_1 … field_15` bleiben **für immer** als Rückwärts-Mirror der ersten 15
  Calls befüllt → alte App-Versionen zeigen die ersten 15, kein Crash
  (graceful degradation). **Das ist die Kompatibilitätsgarantie.**
- Neue App liest `calls_json`; Fallback auf `field_1..15`, falls NULL.
- Filter/Dubletten/Distinct über `json_each(calls_json)` (JSON1 ist verfügbar,
  SQLite 3.49).

### Kompatibilität (zwei Richtungen)

| Szenario | Verhalten | Bedingung |
|---|---|---|
| Neue App + alte DB | Migration ergänzt Spalte + Backfill | nur additive Migration |
| Alte App + neue/geteilte DB (>15) | liest erste 15, kein Crash | `field_1..15`-Mirror bleibt befüllt |

## Abnahmekriterien

1. **Korrektheit (Summenprobe):** `seq_invariants.py` muss vor/nach identische
   Werte liefern (Σ Calls, jede Callliste, alle drei Filter, Dubletten,
   Mapping-Aggregate). Deckt auch **Dynamic Lyrics** ab (liest über
   `get_sequence_calls`).
2. **Alle verknüpften Stellen:** enthält-Filter, „Limit bis", „nur"-Filter,
   Dynamic Lyrics.
3. **Performance:** `seq_bench.py` mit **mehreren Messreihen** (Median + CV%),
   verglichen an drei Punkten.

## Mess-Protokoll (drei Punkte)

| Punkt | Code | Sequenzen | Zweck |
|---|---|---|---|
| **T0** | alt (field_1..15) | 1.705 | Baseline |
| **T1** | neu (calls_json) | 1.705 | reiner Speicherart-Effekt |
| **T2** | neu | ~11.700 | Skalierung (nach +~10.000) |

Werkzeuge (`1_Source/tools/`):
- `seq_invariants.py --db … --out seq_baseline.json` / `--compare seq_baseline.json`
- `seq_bench.py --db … --series 5 --reps 7 --out bench_T0.json` / `--compare bench_T0.json`

Jede Messung: 5 unabhängige Reihen × 7 Wiederholungen, Ausgabe Median/Min/Max/CV%.

## Ergebnisse

### T0 — Baseline (alter Code, 1.705 Sequenzen, 2026-08-23)

**Korrektheit (`seq_baseline.json`):**

| Kennzahl | Wert |
|---|---:|
| seq_total | 1.705 |
| **calls_sum (Σ Calls)** | **15.029** |
| contains: entity_ids / Treffer | 330 / 12.814 |
| limit/only-Schwellen | 591 |
| Dubletten-Gruppen / zu löschen | 0 / 0 |
| ungemappt / distinct Call-Texte | 830 / 1.832 |
| per_seq_hash | `689f69f0…dffaf0` |

**Performance (5 Reihen × 7 Wdh., median / CV%):**

| Operation | median ms | CV% |
|---|---:|---:|
| contains_count (60×) | 183,0 | 1,2 |
| contains_page50 (60×) | 132,8 | 1,3 |
| get_sequence_calls (200×, Dynamic Lyrics) | 11,8 | 0,9 |
| limit_count (40×) | 0,78 | 3,5 |
| only_count (40×) | 0,40 | 9,3 |
| table_page50 | 0,30 | 6,5 |
| dup_count | 6,8 | 4,2 |
| unmapped_collect | 5,4 | 2,1 |
| distinct_calls_collect | 19,9 | 1,1 |

**Erkenntnis:** Der **enthält-Filter hat keinen Index** (Full-Scan mit
`EXISTS … IN (field_1..15)`, ~3 ms/Query bei 1.705 Zeilen, skaliert linear).
Das ist der Haupt-Watchpoint für T2. Falls `json_each` bei ~11.700 Sequenzen
einbricht → **Increment 1.5**: indizierte `sequence_calls`-Tabelle als
Filter-Index (`id IN (SELECT sequence_id FROM sequence_calls WHERE entity_id=?)`).

### T1 — nach Increment 1 (calls_json, 1.705 Sequenzen, 2026-08-23)

**Korrektheit:** `seq_invariants.py --compare seq_baseline.json` → **ALLE GLEICH ✓**
(calls_sum 15.029, per_seq_hash, contains/limit/only-Hashes, Dubletten,
Mapping-Aggregate — jede Kennzahl identisch). Der Speicherart-Wechsel ist damit
verhaltensgleich für den Alt-Bestand, inkl. Dynamic-Lyrics-Pfad und aller drei Filter.

**Performance (5 Reihen × 7 Wdh., Faktor gegen T0):**

| Operation | T0 ms | T1 ms | Faktor |
|---|---:|---:|---:|
| **contains_count** | 183,0 | **526,0** | **2,87× langsamer** ⚠ |
| **contains_page50** | 132,8 | **371,5** | **2,80× langsamer** ⚠ |
| get_sequence_calls (Dynamic Lyrics) | 11,8 | 12,0 | 1,02× (neutral) |
| limit_count | 0,78 | 0,78 | 1,01× |
| only_count | 0,40 | 0,37 | 0,93× |
| table_page50 | 0,30 | 0,30 | 0,99× |
| dup_count | 6,8 | 2,3 | **0,34× schneller** |
| unmapped_collect | 5,4 | 4,1 | 0,76× schneller |
| distinct_calls_collect | 19,9 | 16,3 | 0,82× schneller |

**Fazit:** Wie vorhergesagt — alle Aggregate/Dubletten werden **schneller**
(ein `calls_json` statt 15 Felder), aber der **enthält-Filter regressiert ~2,9×**,
weil `json_each(calls_json)` pro Zeile JSON parst und **keinen Index** hat. Bei
~11.700 Sequenzen (T2) multipliziert sich das mit dem ~7× Zeilenwachstum →
Handlungsbedarf. **→ löst Increment 1.5 aus** (indizierte `sequence_calls`-Tabelle
als enthält-Filter-Index).

### T1.5 — indizierte `sequence_calls` als enthält-Filter-Index (1.705 Sequenzen, 2026-08-23)

**Design:** Neue Tabelle `sequence_calls(sequence_id, position, call_text)` +
Index `idx_seqcalls_calltext`. Bewusst **ohne** `entity_id` (haengt von
`call_text_mappings` ab → sonst Index-Staleness bei Mapping-Aenderungen). Der
enthält-Filter joint zur Query-Zeit:
`id IN (SELECT sc.sequence_id FROM call_text_mappings m JOIN sequence_calls sc ON sc.call_text=m.call_text WHERE m.entity_id=?)`.
Index wird beim Oeffnen automatisch gebaut/repariert (`_ensure_sequence_calls_index`)
und bei insert/update/delete/split live nachgezogen; `rebuild_sequence_calls_index()`
fuer Massen-Importe.

**Korrektheit:** `seq_invariants --compare` → **ALLE GLEICH ✓** (unveraendert).

**Performance (Faktor gegen T0):**

| Operation | T0 ms | T1 (json_each) | T1.5 (Index) | T1.5 vs T0 |
|---|---:|---:|---:|---:|
| **contains_count** | 183,0 | 526,0 | **1,7** | **0,01× (100× schneller)** ✅ |
| **contains_page50** | 132,8 | 371,5 | **6,4** | **0,05× (20× schneller)** ✅ |
| dup_count | 6,8 | 2,3 | 2,5 | 0,36× |
| unmapped / distinct | 5,4 / 19,9 | – | 4,1 / 16,5 | 0,76× / 0,83× |
| get_sequence_calls / limit / only / table | – | – | ~gleich | ~1,0× |

**Fazit:** Der Index kehrt die Regression nicht nur um, sondern macht den
enthält-Filter **~100× schneller als das Original** (Index-Seek statt Full-Scan).
Alle anderen Operationen neutral oder schneller. Increment 1 + 1.5 sind damit
bei gleicher Sequenzzahl korrektheitsgleich **und** schneller.

### T2 — Skalierung auf 11.723 Sequenzen (2026-08-23)

Massen-Import der 10.018 gescrapten Ceder-Sequenzen in eine **Wegwerf-Kopie**
(`tools/t2_load.py`, echte 2_Test bleibt unangetastet). Ergebnis: 11.723
Sequenzen, davon **549 mit >15 Calls** (max 34).

**Performance (5 Reihen, Faktor gegen T0 bei 6,9× Zeilen):**

| Operation | T0 (1.705) | T2 (11.723) | Faktor | Bewertung |
|---|---:|---:|---:|---|
| **contains_count** | 183,0 | **50,7** | **0,28×** | Index skaliert — 3,6× schneller als Original trotz 7× Daten ✅ |
| **contains_page50** | 132,8 | **38,1** | 0,29× | ✅ |
| get_sequence_calls (Dyn. Lyrics) | 11,8 | 12,2 | 1,03× | unabhängig von Groesse ✅ |
| table_page50 | 0,30 | 0,29 | 0,97× | ✅ |
| limit_count | 0,78 | 2,79 | 3,59× | <3 ms, unkritisch |
| only_count | 0,40 | 1,07 | 2,65× | unkritisch |
| dup_count | 6,8 | 37,0 | 5,43× | Wartungs-Op, ~linear |
| unmapped_collect | 5,4 | 44,7 | 8,23× | Mapping-Admin-Op |
| distinct_calls_collect | 19,9 | 133,3 | 6,70× | Mapping-Admin-Op |

**>15-Korrektheit (Round-Trip):**
- Längste Sequenz (34 Calls): `get_sequence_calls` liefert alle 34 (nicht auf 15
  gekürzt); 34 Index-Zeilen ✓.
- Sequenz 4776 hat „L.A" (Allemande Left) an **Position 16** → enthält-Filter
  `entity=call_allemande_left` **findet sie** ✓. Die alte Mirror-Logik
  (`field_1..15`) enthält diesen Call NICHT — nur `calls_json`+Index finden ihn.

**Fazit T2:** Die **interaktiven Hotpaths** (enthält-Filter, Sequenz-Navigation,
Tabellen-Scroll) bleiben bei 7× Datenmenge schnell — der enthält-Filter ist dank
Index sogar schneller als im Original. Was ~linear mit der Gesamt-Call-Zahl
waechst, sind reine **Wartungs-/Admin-Aggregate** (Dubletten-Check,
Mapping-Sammlungen) bei 37–133 ms — nicht auf dem Live-Pfad, akzeptabel.
Bei Bedarf spaeter optimierbar (z. B. Distinct-Cache), aber kein Blocker.

### Increment 2 — UI-Caps entfernt + Importer produktiv (2026-08-23)

- **Editor** (`SequenceEditorDialog`): 15-Call-Rejection beim Speichern entfernt,
  Zaehler zeigt nur noch die Anzahl (kein rotes Limit). Freitext-Feld war schon
  zeilenbasiert — keine UI-Umbauten noetig.
- **Alle App-Import-Pfade** ohne `[:15]`-Truncation: `SequenceImportDialog`
  (JSON/CSDS/Freetext/MDB), `FreetextSequenceImportDialog`, und die
  `SequencesWidget.import_from_json/csds/freetext`. Volle Liste geht an
  `insert_sequence` (baut calls_json + Mirror).
- **Import-Dedup** (`_build_dupe_set`/`_fields_tuple`): auf `calls_json`-Schluessel
  umgestellt — zwei Sequenzen mit gleichen ersten 15, aber verschiedenen Calls
  >15 gelten nicht mehr faelschlich als Dublette. Headless verifiziert
  (20- und 17-Call-Sequenz: ungekuerzt geparst, Dedup-Keys verschieden).
- **Scraper-Importer** `import_to_db.py`: neues Dateimuster
  `type_*__level_*.json`, volle Liste, calls_json + Mirror, Typ-Kanonisierung,
  Index-Rebuild + max_to-Neuberechnung. Dry-run: 10.018 Sequenzen, 549 mit >15.
- **i18n**: `seq_editor_count_simple` (de/en/ja) ergaenzt.

## Gesamtergebnis

Increment 1 (calls_json + Mirror) + Increment 1.5 (indizierter enthält-Filter)
sind **korrektheitsgleich** zum Alt-Zustand (Summenprobe an jeder Stelle grün),
**schneller** bei gleicher Datenmenge und **skalieren** auf 11.700+ Sequenzen. Die
15-Call-Grenze ist aufgehoben; `field_1..15` bleibt als Rückwärts-Mirror für alte
App-Versionen erhalten. Increment 1 + 1.5 + 2 sind umgesetzt und verifiziert.

**Offen:** Smoke-Test in der laufenden App (Editor >15 speichern, Sequenz-Import,
Filter, Dynamic Lyrics), Versions-Bump + CHANGELOG + Build (nach Freigabe).
Optional: Massen-Import der Ceder-Sequenzen in die echte 2_Test (Entscheidung,
welche Typen integriert werden) — Daten liegen bereit.

