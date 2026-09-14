# F6.22 Sequenzen-Fenster

## Zweck
Dockbares Fenster zur Anzeige und Filterung von Singing-Call-Sequenzen.
Caller koennen ihre gesammelten Choreographie-Sequenzen nach enthaltenen Calls
und nach Programm-Level filtern, um passende Sequenzen fuer den aktuellen
Tanzabend zu finden.

## Datenquellen

### Sequenzen (aus Access-Migration)
Quelle: `caller.mdb` → Tabelle **Sequenzen** (885 Eintraege)
- Feld1–Feld15: Je ein Call-Name pro Feld (Text, einige Felder NULL)
- Level: Programmstufe als Text ("MS", "Plus", etc.)
- Skill: Schwierigkeitsgrad (meist NULL)

Verwandte MDB-Tabellen:
- **AlleFiguren** (1.026): Figurenliste mit Aliasen (fuer Mapping-Unterstuetzung)
- **AuswahlFiguren** (176): Vorselektierte Figuren
- **Order** (885): Figur-Referenzen parallel zu Sequenzen
- **Figur** (1.019): Figuren mit Sortierung

### Programmlisten und Teaching Order (aus Burleson-Projekt)
Die Programm-Zuordnungen in der MDB sind veraltet. Aktuelle Quelle ist
das separate Burleson-Projekt:

**Vocabulary** (Entity-Definitionen):
- `data/vocabulary/basic_calls.json`
- `data/vocabulary/mainstream_new_calls.json`
- `data/vocabulary/plus_calls.json`
- `data/vocabulary/advanced_calls.json`

**Teaching Order** (Programm-Zuordnung + Reihenfolge):
- `mappings/teaching_order_basic.json`
- `mappings/teaching_order_mainstream.json`
- `mappings/teaching_order_plus.json`
- `mappings/teaching_order_advanced.json`
- `mappings/teaching_order_challenge.json`

**Nummerierungssystem** (PP.XXXXXX):
| PP | Programm |
|----|----------|
| 10 | Basic 1 |
| 20 | Basic 2 |
| 30 | Mainstream |
| 40 | Plus |
| 50 | A1 |
| 60 | A2 |
| 70 | C1 |
| 80 | C2 |
| 90 | C3a |
| 100 | C3b |

## Architektur: Cached Live-Mapping

### Zwei-Schichten-Prinzip (wie Burleson-Projekt)
- **Schicht 1 (statisch)**: Sequenz-Rohdaten — die Call-Texte aus Feld1–Feld15,
  unveraendert in der SQLite-DB gespeichert
- **Schicht 2 (austauschbar)**: Teaching-Order-Mapping — welcher Call gehoert zu
  welchem Programm, mit welcher Nummer

### Vorberechnung + Remapping-Button
- Beim **Import** (Migration) und beim **Remapping** wird fuer jede Sequenz berechnet:
  - Jeder Call-Text → `entity_id` (Lookup gegen Vocabulary)
  - Jede `entity_id` → `teaching_order` (Lookup gegen Teaching-Order-Dateien)
  - `max_teaching_order` der Sequenz = hoechste TO aller enthaltenen Calls
- Die Ergebnisse werden in der DB **gecacht** (schnelle SQL-Filter)
- Ein unauffaelliger **Remapping-Button** (kleines Zahnrad oder Kontextmenue)
  loest die Neuberechnung aus — fuer den Fall, dass die Teaching-Order-Dateien
  aktualisiert wurden (z.B. nach Callerlab-Aenderungen)

### Vorteile dieses Ansatzes
- **Schneller Start**: Vorberechnete max_teaching_order liegt in der DB,
  Filter geht per SQL-Index
- **Single Source of Truth**: Die Teaching-Order-Dateien sind die einzige Quelle,
  die DB ist nur Cache
- **Einfaches Update**: Teaching-Order-Datei aendern → Remapping-Button klicken → fertig
- **Architektonisch konsistent**: Gleiches Prinzip wie play_history → song_location_stats

## Datenmodell (SQLite)

### Tabelle: sequences
| Spalte | Typ | Beschreibung |
|--------|-----|-------------|
| id | INTEGER PK | Auto-Increment |
| field_1 – field_15 | TEXT | Call-Texte (Original aus MDB, NULL wenn leer) |
| level_original | TEXT | Original-Level aus MDB ("MS", "Plus", etc.) |
| max_teaching_order | REAL | Vorberechnete hoechste TO aller Calls (Cache) |

### Tabelle: sequence_calls (aufgeloeste Calls pro Sequenz)
| Spalte | Typ | Beschreibung |
|--------|-----|-------------|
| id | INTEGER PK | Auto-Increment |
| sequence_id | INTEGER FK | → sequences.id |
| position | INTEGER | 1–15 (Feld-Position in der Sequenz) |
| call_text | TEXT | Original-Text aus MDB |
| entity_id | TEXT | Aufgeloeste Entity-ID (NULL wenn unbekannt) |
| teaching_order | REAL | Teaching-Order-Nummer (NULL wenn unbekannt) |

### Indizes
- `sequence_calls(entity_id)` — fuer Contains-Filter
- `sequences(max_teaching_order)` — fuer Limit-Filter

## Filter

### 1. Contains-Filter ("Enthält")
- Dropdown/Autocomplete mit allen bekannten Calls (aus Teaching-Order-Dateien)
- Auswahl filtert: Zeige nur Sequenzen, die diesen Call mindestens einmal enthalten
- SQL: `WHERE id IN (SELECT sequence_id FROM sequence_calls WHERE entity_id = ?)`

### 2. Limit-Filter ("Beschränkt auf")
- Dropdown mit Programm-Stufen und einzelnen Calls, sortiert nach Teaching Order
- Enthaelt virtuelle Trennzeilen ("--- Basic 1 ---", "--- Mainstream ---", etc.)
- Auswahl filtert: Zeige nur Sequenzen, deren ALLE Calls ≤ dem gewaehlten Level liegen
- SQL: `WHERE max_teaching_order <= ?`
- Sequenzen mit unerkannten Calls (entity_id = NULL) werden bei aktivem Limit-Filter
  ausgeblendet (konservativ: unbekannt koennte zu hoch sein)

### Kombination
Beide Filter sind UND-verknuepft. Beispiel:
- Contains = "Swing Thru" + Limit = "Plus"
- → Zeige alle Sequenzen, die Swing Thru enthalten UND nur aus Basic/MS/Plus-Calls bestehen

## UI-Konzept

### Fenster-Layout
```
┌──────────────────────────────────────────────┐
│  Sequenzen                     [-][+] 100% [⚙]│
├──────────────────────────────────────────────┤
│  Enthält:  [_____________________▾]          │
│  Limit:    [_____________________▾]          │
├──────────────────────────────────────────────┤
│  # │ Sequenz                        │ Level  │
│ ---|-------------------------------|--------|
│  1 │ Heads Square Thru → Swing ...  │ MS     │
│  2 │ Heads Lead Right → Veer Le...  │ MS     │
│  3 │ Heads Touch 1/4 → Walk & ...   │ Plus   │
│  ... (Lazy Loading)                          │
│ 42 │ Heads Pass the Ocean → Ext...  │ Plus   │
├──────────────────────────────────────────────┤
│  42 von 885 Sequenzen                        │
└──────────────────────────────────────────────┘
```

### Elemente
- **Zoom-Buttons** [-][+] mit Prozentanzeige: Schriftgroesse der Sequenz-Tabelle
  skalieren (Design wie Lyrics-Widget, SVG-Icons zoom-in/zoom-out)
- **Zahnrad-Button** [⚙] oben rechts: Remapping ausloesen (unauffaellig)
- **Enthält-Dropdown**: Autocomplete-Eingabe mit Call-Liste
- **Limit-Dropdown**: Programm-Stufen mit Teaching-Order-Eintraegen
- **Sequenz-Tabelle**: Lazy Loading (blockweises Nachladen beim Scrollen)
- **Sequenz-Darstellung**: Calls als lesbare Folge (Feld1 → Feld2 → ... → FeldN),
  abgeschnitten mit Ellipsis wenn zu lang
- **Level-Spalte**: Berechnetes Programm-Level der Sequenz (aus max_teaching_order)
- **Statuszeile**: "X von Y Sequenzen" (Filteranzeige)

### Lazy Loading
- Initiales Laden: Erste ~50 Sequenzen
- Beim Scrollen ans Ende: Naechsten Block nachladen (50er-Schritte)
- Bei Filterwechsel: Zurueck auf Block 1
- SQL: `LIMIT ? OFFSET ?`

### Interaktion
- Klick auf Sequenz: Aufklappen/Detail-Ansicht mit allen Calls untereinander,
  jeweils mit Programm-Zuordnung (farblich oder als Tag)
- Doppelklick: Optional spaeter fuer Sequenz-Editor (Backlog)

## Mapping-Prozess (Remapping)

### Ablauf
1. Teaching-Order-Dateien aus dem Burleson-Projekt laden
2. Keyword-Index aufbauen (Call-Name → entity_id, case-insensitive)
3. AlleFiguren aus MDB als zusaetzliche Alias-Quelle nutzen
4. Fuer jede Sequenz: Feld1–Feld15 gegen den Index matchen
5. Ergebnisse in `sequence_calls` schreiben
6. `max_teaching_order` pro Sequenz berechnen und in `sequences` cachen
7. Nicht erkannte Calls markieren (entity_id = NULL)

### Umgang mit unerkannten Calls
- Werden in der Detail-Ansicht speziell markiert (z.B. kursiv, anderer Hintergrund)
- Sequenzen mit unerkannten Calls sind im Contains-Filter weiterhin findbar
  (ueber die erkannten Calls)
- Im Limit-Filter werden sie konservativ ausgeblendet
- Statistik nach Remapping: "X von Y Calls erkannt (Z%)"

## Abgrenzung

### In diesem Prototyp
- Sequenz-Anzeige mit zwei Filtern
- Lazy Loading
- Import aus MDB
- Remapping-Funktion
- Cached Live-Mapping-Architektur

### Spaeter (Backlog)
- **Sequenz-Editor**: Neue Sequenzen erstellen, bestehende bearbeiten
- **Sequenz-Bewertung**: Qualitaets-/Schwierigkeitsrating pro Sequenz
- **Sequenz-Verknuepfung**: Sequenz einem Song zuordnen
- **Export**: Sequenzen als Text/PDF exportieren

## Bezug zu anderen Modulen
- **Migration** (06_migration.md): Sequenzen-Import ist Teil der Phase-2-Migration
- **Burleson-Projekt**: Liefert Vocabulary und Teaching Order (externe Abhaengigkeit)
- **Lyrics-Widget**: Design-Vorbild fuer Toolbar (Zoom +/- mit SVG-Icons und
  Prozentanzeige). Kein Auto-Scroll und kein Auto-Size (nicht sinnvoll bei Tabelle).
  Sequenzen und Lyrics bilden einen Widget-Stapel (Tabbed Docking) —
  siehe auch 05_ui_fenster_layout.md F6.17 Tabbed Docking
