# Prototyp-Reihenfolge (risikogetrieben)

## Phase 1: Audio-Kern (HOCH-RISIKO) ✅
| Nr | Prototyp | Risiko | Status |
|----|----------|--------|--------|
| P1 | MP3 laden und stabil abspielen | Hoch | ✅ Abgenommen |
| P2 | Tempo live ändern | Hoch | ✅ Abgenommen |
| P3 | Pitch getrennt ändern | Hoch | ✅ Abgenommen |
| P4 | Tempo und Pitch gleichzeitig | Hoch | ✅ Abgenommen |
| P5 | Loop-In / Loop-Out | Hoch | ✅ Abgenommen |
| P6 | Loop plus Tempoänderung | Sehr hoch | ✅ Abgenommen |

## Phase 2: UI-Fenster-System (HOCH-RISIKO) ✅
| Nr | Prototyp | Risiko | Status |
|----|----------|--------|--------|
| P7 | Player plus zweites Fenster | Hoch | ✅ Abgenommen |
| P8 | Fenster über Player ein-/ausblenden | Hoch | (in P7 integriert) |
| P9 | Fenster verschieben und Grösse ändern | Mittel | (in P7 integriert) |
| P10 | Unterschiedliche Resize-Regeln | Hoch | (in P7 integriert) |
| P11 | Docking / magnetisches Verhalten | Hoch | (in P7 integriert) |
| P12 | Layout speichern und wiederherstellen | Mittel | (in P7 integriert) |

## Phase 3: Datenmodell und Persistenz ✅
| Nr | Prototyp | Risiko | Status |
|----|----------|--------|--------|
| P13 | Songmodell anlegen | Mittel | ✅ Abgenommen |
| P14 | Auto-Save | Mittel | ✅ Abgenommen |
| P15 | Relative Pfade / portable Struktur | Mittel | ✅ Abgenommen |

## Phase 4: Songverwaltung ✅
| Nr | Prototyp | Risiko | Status |
|----|----------|--------|--------|
| P16 | Songliste mit Suche | Mittel | ✅ Abgenommen |
| P17 | Heutiges Tempo | Mittel | ✅ Abgenommen |
| P18 | Pattern / Singing Modus | Mittel | ✅ Abgenommen |

## Phase 5: Kontexte und Historie ✅
| Nr | Prototyp | Risiko | Status |
|----|----------|--------|--------|
| P19 | Kontexte Club / Special | Mittel | ✅ Abgenommen |
| P20 | Abspielhistorie | Mittel | ✅ Abgenommen |

## Phase 6: Playlist (teilweise ✅)
| Nr | Prototyp | Risiko | Status |
|----|----------|--------|--------|
| P21 | Playlist Basis + Manager | Mittel | ✅ Abgenommen |
| P22 | Import-Workflow | Mittel | Offen |
| P23 | Crash-Recovery | Mittel | Offen |
| ~~P24~~ | ~~Playlist-Builder~~ | ~~Niedrig~~ | ✅ In P21 integriert |

### P21 Umfang (deutlich groesser als geplant)
P21 umfasst sowohl die Playlist-Basisfunktionalitaet als auch den Playlist-Builder (urspr. P24).
Implementierte Features:
- **PlaylistWidget** (schlank, Tab neben Songliste): Playlist-Anzeige, Reorder-Buttons, Laden/Speichern
- **PlaylistManagerWidget** (Zwei-Panel, eigenes Dock): Song-Pool mit Filter/Sort + Playlist-Spiegel
- **Transfer**: Doppelklick, Pfeil-Buttons, Drag & Drop
- **Sortierung**: Alphabetisch, Qualitaet, Zuletzt gespielt, Empfehlung
- **Filter**: Alle / Pattern / Singing
- **Speichern/Laden**: .txt-Dateien im playlist_dir
- **Auto-Advance**: Bei Song-Ende, Stop und Fade-Out → naechster Playlist-Song vorgeladen
- **Fade-Out**: Linearer Volume-Ramp (konfigurierbar via INI, Default 3s)
- **Confirm-Button**: Gruener Haken zum Schliessen des Managers

## Phase 7: Empfehlung und Extras
| Nr | Prototyp | Risiko | Status |
|----|----------|--------|--------|
| ~~P25~~ | ~~Empfehlungssystem~~ | ~~Mittel~~ | ✅ In P21 integriert (Sort: Empfehlung) |
| P26 | Lyrics-Anzeige | Niedrig | ✅ Abgenommen |
| P27 | Performance-Test | Mittel | ✅ Abgenommen |
| P28 | Sequenzen + Design-Menu + Audio-Fix | Niedrig | ✅ Abgenommen |

### P26 Umfang
- **LyricsWidget** (Dock 8, getabbt mit Song-Daten): QTextBrowser-basierte Lyrics-Anzeige
- **Formate**: HTML/HTM (nativ), RTF (via striprtf → Plaintext), TXT (direkt)
- **Smarte Farb-Bereinigung**: Hintergruende entfernt, dunkle Textfarben (black/windowtext) auf Theme-Farbe umgeschrieben, Sektionsfarben (lime, brown, purple, blue, green) beibehalten
- **Auto-Fit Font Size**: Wenn Lyrics auf eine Seite passen, wird Schrift automatisch vergroessert
- **Auto-Scroll**: Proportional zum Song-Fortschritt, wenn Text laenger als Viewport
- **Encoding-Fallback**: UTF-8 mit CP1252-Fallback fuer alte Windows-Dateien

### Zusaetzliche Verbesserungen in P26
- **Light Blue Skin**: Zweites Farbschema (helle Oberflaeche, blaue Akzente), konfigurierbar via INI (`display/skin`)
- **Muted-Farben**: Eigene Variablen `muted_bg`/`muted_text` fuer Disabled-Buttons, Read-Only-Felder, Hover-States (besserer Kontrast in beiden Skins)
- **Indicator-Farben**: `indicator_bg` (unselektiert) und `indicator_check` (selektiert, gruen) fuer RadioButtons und CheckBoxen
- **Loop-Save-Bugfix**: Snapshot-Mechanismus (`_snapshot_loop_values`) sichert Loop-Werte VOR engine.load(), verhindert Ueberschreiben durch neuen Song
- **Gemeinsame Datenordner**: music/, lyrics/, playlists/ auf `prototypes/`-Ebene (INI: `../music`), spart ~2.8 GB pro zusaetzlichem Prototyp

### P27 Umfang
Performance-Messung der UI-Tabellen und DB-Abfragen unter realistischer Last.

**Testmethodik:**
- Phase A = Baseline (518 Songs, 45 Lokationen, 4.825 History-Eintraege)
- Phase B = Stresstest (10.518 Songs, 145 Lokationen, 909.625 History-Eintraege)
- 10 Wiederholungen pro KPI mit Statistik (Mean, StdDev, Min, Max)
- Zufaellige Lokationswahl, alle 4 Sortier-Modi einzeln gemessen
- `_flush_qt()` (processEvents + gc.collect) zwischen Messreihen gegen Akkumulation
- Alle Einzelwerte in CSV exportiert (3 Bloecke: Statistik, Einzelwerte, Einzelmessungen)

**Gemessene KPIs:**
- `db_get_all` — Alle Songs aus DB laden
- `get_last_played_map` — LEFT JOIN fuer Zuletzt-Gespielt-Map
- `songliste_refresh` — Songliste komplett neu aufbauen
- `manager_refresh` — Playlist-Manager oeffnen und Pool befuellen
- `pool_*` — Pool-Tabelle mit 4 Sortierungen (alphabetisch, qualitaet, zuletzt_gespielt, empfehlung)
- `suchfilter_leer` / `suchfilter_text` — Suchfilter anwenden (alle / eingeschraenkt)
- `app_startup` — Programmstart bis GUI komplett
- `skin_laden` — Skin-Wechsel

**Erkenntnisse:**

1. **QTableWidget-Rebuild ist der Flaschenhals** — Skaliert ueberproportional (×40 bei 20× mehr Songs). DB-Abfragen skalieren linear und sind vernachlaessigbar (35ms bei 10k Songs).

2. **Alle 4 Sortier-Modi sind gleich schnell** — Die Sortierung selbst ist nicht das Problem, sondern das Befuellen der Tabelle mit QTableWidgetItems.

3. **`setUpdatesEnabled(False/True)` bringt nichts** — Repaint-Unterdrueckung hat keinen messbaren Effekt. Der Flaschenhals ist nicht das Zeichnen, sondern die Python↔C++ Bruecke (PySide6-Binding) bei der Item-Erzeugung.

4. **`setRowCount(n)` statt `insertRow()` bringt −40% bei der Pool-Tabelle** — Vorallokation vermeidet 10.000 einzelne Reallokierungen. Songliste (2 Spalten) profitiert weniger (−7%) als Pool (3 Spalten, −40%).

5. **`setRowCount(n)` OHNE vorheriges `setRowCount(0)` ist katastrophal** — Wenn die Tabelle bereits n Zeilen hat, ist `setRowCount(n)` ein No-Op. Das anschliessende `setItem()` ersetzt Items einzeln, was ×200 langsamer ist als Loeschen+Neuanlegen. Korrekte Reihenfolge: `setRowCount(0)` → `setRowCount(n)` → Schleife mit `setItem()`.

6. **Qt-Objekte muessen zwischen Messreihen explizit freigegeben werden** — Ohne `processEvents()` + `gc.collect()` akkumulieren QTableWidgetItems im Speicher und verursachen exponentielles Wachstum (0.98s → 10.78s ueber 10 Laeufe).

**Optimiertes Tabellen-Pattern (Ergebnis von P27):**
```python
table.setUpdatesEnabled(False)   # Repaint aus
table.setRowCount(0)             # Alte Items freigeben
table.setRowCount(n)             # Einmal vorallokieren
for idx in range(n):
    table.setItem(idx, col, QTableWidgetItem(...))
table.setUpdatesEnabled(True)    # Repaint ein (1x)
```

**Messergebnisse Phase B (10k Songs) — Vorher vs. Nachher:**

| KPI | Original | Optimiert | Verbesserung |
|-----|----------|-----------|-------------|
| pool_* (Ø 4 Modi) | 0.349s | 0.213s | −39% |
| manager_refresh | 0.271s | 0.215s | −21% |
| songliste_refresh | 0.187s | 0.175s | −7% |
| suchfilter_leer | 0.150s | 0.139s | −7% |
| db_get_all | 0.036s | 0.035s | ±0% |

**Moegliche weitere Optimierungen (nicht umgesetzt):**
- `QTableView` + `QAbstractTableModel` statt `QTableWidget` — groesster Hebel, aber groesster Umbau
- Lazy Loading / Virtual Scrolling — nur sichtbare Zeilen befuellen

### P28 Umfang
Sequenzen-Fenster: Anzeige und Filterung von 885 Singing-Call-Sequenzen aus Access-MDB.

**Features:**
- **SequencesWidget** (Dock 9, getabbt mit Lyrics): Dockbares Fenster fuer Sequenz-Anzeige
- **MDB-Import**: Liest Sequenzen-Tabelle (885 Eintraege, Feld1-Feld15) via `access-parser`
- **Cached Live-Mapping**: Rohdaten in DB, Teaching-Order-Zuordnung vorberechnet via Burleson-Vocabulary
- **Contains-Filter**: Autocomplete-Dropdown — zeige nur Sequenzen die bestimmten Call enthalten
- **Limit-Filter**: Programm-Dropdown — zeige nur Sequenzen bis zu einem Programm-Level
- **Lazy Loading**: 50er-Bloecke, Nachladen beim Scrollen
- **Detail-Dialog**: Klick auf Zeile zeigt alle Calls mit Programm-Tags
- **Remapping-Button** (Zahnrad): Teaching-Order-Zuordnung neu berechnen
- **Zoom [-/+]**: Schriftgroesse skalieren (wie LyricsWidget)

**Neue Module:**
- `sequence_mapper.py`: Mapping-Logik (Vocabulary + Teaching Order laden, Call-Texte resolven)
- `mdb_reader.py`: Erweitert um `read_sequences()` und `read_alle_figuren()`
- `song_db.py`: Erweitert um `sequences` und `sequence_calls` Tabellen

**Architektur:**
- Zwei-Schichten-Prinzip (wie Burleson-Projekt): Schicht 1 = Rohdaten (Call-Texte, unveraenderlich), Schicht 2 = Teaching-Order-Mapping (austauschbar)
- Vorberechnung + Remapping-Button: `max_teaching_order` wird gecacht, Remapping laedt Mapper neu und berechnet alles durch
- Programme sind flach (kein Hierarchie): Basic 1, Basic 2, Mainstream, Plus, A1, A2, C1, C2, C3a, C3b

## Phase 8: Release-Vorbereitung und Erweiterungen ✅
| Nr | Prototyp | Risiko | Status |
|----|----------|--------|--------|
| P29 | Release-Vorbereitung (Build-Pipeline, i18n, Ordnerstruktur) | Mittel | ✅ Abgenommen |
| P30 | BPM-Detection + Reports + Lyrics-Kontrast | Mittel | ✅ Abgenommen |
| P31 | Beat Snap Audition + Layout-Versionierung | Mittel | ✅ Abgenommen |
| P32 | Keyboard, Datei-Auswahl, Loop-Crossfade/-Offset | Mittel | ✅ Abgenommen |
| P33 | Potential-Widget, Menu-Umbau, 3-Spalten-Layout | Mittel | ✅ Abgenommen |
| P34 | Keyboard-Shortcuts (L/P), Elegant Gold Theme | Niedrig | ✅ Abgenommen |

### P29 Umfang
Release-Vorbereitung: Professionelle Build-Pipeline und Internationalisierung.

**Features:**
- **i18n-Modul** (`i18n.py`): JSON-basierte Uebersetzungen (Deutsch/Englisch), `_t()`-Funktion
- **5-Stufen-Ordnerstruktur**: 1_Source → 2_Test → 3_Build → 4_Release → _archive
- **Build-Pipeline** (`build.py`): PyInstaller-Spec + Clean-DB + ZIP-Erstellung (Vollpaket, Update, Source)
- **Clean-DB-Skript**: Entfernt User-Daten, behaelt Referenzdaten (Sequenzen, Teaching Order)
- **Migration-EXE**: Separater Access-Import als eigene EXE
- **Portable Pfade**: `app_dir` = neben EXE (nicht mehr Prototypen-Ordner)

### P30 Umfang
BPM-Erkennung, GEMA-Reports und Lyrics-Kontrast-Verbesserung.

**Features:**
- **Auto-BPM** (`bpm_detector.py`): Comb-Filter-Bank, Onset-Strength, Sub-Harmonik-Korrektur, 0.1 BPM Aufloesung
- **Reports-Widget**: Setlist/Musikfolgeliste mit TXT-Export, bidirektionale Lokation↔Datum-Filter
- **Lyrics-Kontrast**: WCAG-Luminanz-Pruefung, Word-HTML-Sanitizer (bgcolor, background, color)
- Default-Stylesheet-Update bei Skin-Wechsel und setHtml()
- BPM-Detection in QThread (nicht blockierend)

### P31 Umfang
Beat Snap Audition und Layout-Robustheit.

**Features:**
- **BeatSnapDialog** (`beat_snap_dialog.py`): Vorhoeren des Loop-Sprungs mit doppelter Waveform
- **WaveformWidget**: Minimale Waveform-Darstellung mit Cursor und Marker-Linie
- **Playback-Sample-Counter** (`_playback_sample`): Zaehlt tatsaechlich ausgegebene Audio-Samples im Callback
- **Engine-Loop-Deaktivierung**: `_loop_active = False` waehrend Audition verhindert Doppel-Sprung
- **Layout-Versionierung**: `_LAYOUT_VERSION` mit versioned `saveState()`/`restoreState()`
- Inkompatible Layout-States werden automatisch verworfen (kein korruptes Docking mehr)

**Siehe auch:** `docs/14_beat_snap_audition.md` — Detailliertes Versuchsprotokoll (6 Iterationen)

### P32 Umfang
Keyboard, Datei-Auswahl, Loop-Verbesserungen.
- Siehe Changelog 0.32

### P33 Umfang
Potential-Widget (Datenqualitaet), Lokation loeschen, Menu-Umbau, 3-Spalten-Default-Layout.
- Siehe Changelog 0.33

### P34 Umfang
Keyboard-Shortcuts und Elegant Gold Theme.

**Features:**
- **App-weite Keyboard-Shortcuts** (L / P): EventFilter auf QApplication-Ebene statt QShortcut
  - QShortcut mit ApplicationShortcut-Context wird von QTableWidget/QListWidget type-to-search verschluckt
  - Loesung: `QApplication.instance().installEventFilter(self)` auf MainWindow
  - Guard: `QApplication.activeModalWidget()` verhindert doppelte Dialoge
  - Guard: `_is_text_input_focused()` erkennt SpinBox/LineEdit und laesst Buchstaben durch
- **Fokus-Management**: Startup-Fokus auf Songliste, `activateWindow()` fuer floating Docks
- **Planner-Sort-Vorauswahl**: Empfehlung (Index 3) bei gesetzter Lokation, Qualitaet (Index 1) sonst
- **Elegant Gold Theme**: Komplettes Skin-Set (skin.json, skin.qss, 7 SVG-Icons)
  - Anthrazit-Basis (#1a1a1a) mit strahlendem Gold (#d4a017)
  - SVG-Icons mit theme-spezifischen Farben (schwarz fuer Pfeile/Dock-Buttons, dunkelbraun fuer Lupen)

## Phase 9: Weitere Features (offen)
| Nr | Prototyp | Risiko | Status |
|----|----------|--------|--------|
| P22 | Import-Workflow | Mittel | Offen |
| P23 | Crash-Recovery | Mittel | Offen |
