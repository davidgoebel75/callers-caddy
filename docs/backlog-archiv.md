# Backlog-Archiv Callers Caddy

> **Archiv.** Erledigte und entfallene Backlog-Eintraege. Nur Nachschlagewerk — aktive Punkte stehen in `backlog.md`. BL-Nummern bleiben eindeutig ueber beide Dateien.

_Ausgelagert am 2026-07-23._

---

### BL-184: Genre-Zuweisung beim Import (Ordner-Taxonomie mitnehmen)
**Status:** ERLEDIGT (v0.141, gebaut 2026-08-31; Kernfunktion von David abgenommen)
**Quelle:** David (2026-08-23)
**Beschreibung:** Beim Import neuer Lieder soll der Nutzer selbst ein oder mehrere Genres wählen können, die den neuen Liedern zugewiesen werden — damit eine bereits in Ordnern organisierte Taxonomie direkt beim Import mitgenommen wird, statt Genres später einzeln nachzupflegen.
**Umsetzung (v0.141):** `_ImportGenreDialog` (in `main.py`) erscheint nach der Ordnerwahl beim Ordner-Import: Häkchenliste aller vorhandenen Genres (ohne `CHECK:`-Marker), die angehakten werden allen Songs des Imports additiv zugewiesen (via `genre_ids` in `_import_files`). Freitextfeld zum on-the-fly-Anlegen eines neuen Genres mit case-insensitiver Dup-Prüfung (vorhandenes wird nur angehakt statt dupliziert). Das System-Genre „NEW" ist eingeblendet und vorangehakt; Abwählen entfernt es beim Import. n:m Song↔Genre bestand bereits im Datenmodell. Der reine Einzeldatei-Import bleibt unverändert (kein Genre-Dialog).
**Bewusst nicht umgesetzt (bei Bedarf neuer Eintrag):** automatischer Genre-Vorschlag aus dem Ordnernamen des Quellpfads (bzw. Unterordner-Ebenen als mehrere Genres); pro-Song-Differenzierung (aktuell nur Batch pauschal auf den ganzen Import).
**Verwandt:** BL-021 (Metadaten-/Label-Erkennung), BL-179 (Drag & Drop startet Import), BL-012 (Bulk-Import), BL-040 (Genre „NEW").
**Aufwand:** Klein bis Mittel

---

### BL-179: Drag & Drop von MP3/ZIP ins Neue-Songs-Widget startet Import
**Status:** ERLEDIGT (v0.146, gebaut 2026-09-03; Grundfall MP3/ZIP/Ordner von David getestet & i.O.)
**Quelle:** David (2026-08-16)
**Beschreibung:** Im „Neue Songs"-Widget gibt es den Button „Songs importieren". Zusätzlich sollen MP3- oder ZIP-Dateien per Drag & Drop direkt auf den Button gezogen werden können — der Drop startet denselben normalen Import-Prozess wie der Button, nur ohne vorgeschaltete Quellenauswahl.
**Umsetzung (v0.146):** Drop-Ziel ist der NEU-Button selbst (nicht das ganze Dock). `_ImportDropButton` (QPushButton + `setAcceptDrops` / `dragEnterEvent` / `dropEvent`, gestricheltes Drop-Highlight) im `LoopWidget`, Callback `on_new_dropped` → `MainWindow._on_new_song_dropped`. Es entfällt gegenüber dem Klick nur die Quellenauswahl; Kopieren/Songtyp/Genre bleiben. Gemeinsame Prozeduren (kein Parallelweg): `_dispatch_import` (Typ-Weiche + Misch-Rückfrage „Nur MP3 / Nur ZIPs / Beides"), `_import_audio_selection` (aus `_on_new_song` extrahiert), `_collect_folder_audio` + `_collect_folder_zips`, ZIP via `_import_zip_packages`. Ordner-Import (Button UND Drop) findet jetzt auch enthaltene ZIP-Pakete; enthält ein Drop/Ordner beide Typen, fragt der Dialog transparent nach. Gemischte Mehrfach-Drops werden getrennt abgearbeitet. Neue Translations `import_drop_nothing`, `import_mixed_*` (de/en/ja).
**Abgrenzung:** BL-066 behandelt Drag & Drop zum *Verknüpfen* auf Song-Datensätze bzw. Songliste. Hier ging es um den *Import-Einstieg* über den NEU-Button inkl. ZIP-Pakete.
**Verwandt:** BL-066 (D&D MP3/Lyrics-Verknüpfung), BL-157 (ZIP-Import von Label-Paketen), BL-012 (Bulk-Import), BL-184 (Genre-Zuweisung beim Import).
**Aufwand:** Klein bis Mittel

---

### BL-189 — Sequenz-Detail: Header mit Sequenz-Typ und Schwierigkeit
**Status:** ERLEDIGT (im Code umgesetzt; per Code-Review verifiziert 2026-08-30)

**Quelle:** Nutzerfeedback Thomas (2026-08-27).

**Problem:** In der Sequenz-Detail-Ansicht (`SequenceViewWidget`) wurden nur die Calls angezeigt. Ohne aktiven Filter im Sequenzen-Widget war Sequenz-Typ und Schwierigkeit der gezeigten Sequenz nicht sofort erkennbar.

**Umsetzung:** Header-Zeile `self._lbl_header` (QLabel, zentriert) oberhalb des `QTextEdit` in `SequenceViewWidget._build_ui()`; gefuellt in `_update_content()` mit Typ + Schwierigkeit; dynamische Schriftgroesse via `_recalc_header_font`. Siehe auch CLAUDE.md („StyleSheet haengt setFont() aus" — trat bei diesem Header auf).
**Aufwand:** Klein

---

### BL-168: StreamDeck-Widget — wichtige Rules als Button-Leiste
**Status:** ERLEDIGT (im Code umgesetzt; per Code-Review verifiziert 2026-08-30)
**Quelle:** David, 2026-07-18

**Beschreibung:** Widget, das ausgewaehlte Rules als grosse Buttons anzeigt — nachgebaute StreamDeck-Oberflaeche / persoenliche Werkzeugleiste fuer eigene Shortcuts.

**Umsetzung:** Eigene Datei `stream_deck_widget.py` (`StreamDeckWidget`): Rules mit `button_number > 0` erscheinen als quadratische, dynamisch angeordnete Kacheln; Klick fuehrt die Rule manuell aus (Trigger uebersprungen, Conditions greifen). In `main.py` instanziiert und als Dock eingebunden. DB-Feld `button_number` am Rules-Datensatz.
**Aufwand:** Mittel

---

### BL-191 — Sequenzen: freier Tag/Kategorie je Sequenz + Filter
**Status:** ERLEDIGT (2026-08-27, gebaut in 0.138, von David abgenommen)

**Quelle:** Nutzerfeedback Thomas (2026-08-27).

**Wunsch:** Zusaetzlich zu Typ und Schwierigkeit soll jede Sequenz einen frei vergebbaren **Tag** (Kategorie) bekommen — z. B. „Once and a half", „Asymmetrische Choreo", „One the x Hand" — und dieser Tag soll im Sequenzen-Widget als Filter nutzbar sein.

**Design-Entscheidungen (mit David, 2026-08-27):**
- Feldname **„Tags"** (nicht „Notizen" — der Begriff ist im Editor bereits anderweitig belegt; nicht „Kategorie").
- **Ein Freitextfeld pro Sequenz** mit **Auto-Vervollstaendigung** ueber bereits genutzte Tags → verhindert leicht abweichende Schreibvarianten.
- **Filter = exakter Match:** leer = alle Sequenzen; gewaehlter Tag = nur Sequenzen mit genau diesem Tag; „x" leert den Filter wieder.

**Umsetzung:**
- `song_db.py`: neue Spalte `sequences.tags TEXT NOT NULL DEFAULT ''` (additive Migration wie `source`; alte App-Versionen lesen die DB weiter). Durchgereicht in `insert_sequence`, `update_sequence`, `get_sequence_raw`. Neue `get_sequence_tags_values()` (DISTINCT, alphabetisch, `COLLATE NOCASE`). `tags_filter` (exakt) in `_build_sequence_where` + `get_filtered_sequences` / `get_filtered_count` / `get_filtered_sequence_ids`.
- `SequenceEditorDialog`: drittes editierbares Combo „Tags" unter Difficulty, vorbefuellt mit `get_sequence_tags_values()`. Laden/Speichern. Buttons auf `autoDefault=False` gesetzt — sonst loeste Enter im Combo faelschlich den „+ Neu"-Verwerfen-Dialog aus.
- `SequencesWidget`: neuer Filter in Filterzeile 2 als Suchfeld mit Substring-Vorschlaegen + „x" (`_setup_search_combo`, wie der Enthält-Filter), Match selbst exakt. Populate in `_populate_dropdowns()` (behaelt die aktive Auswahl bei), in `reset_filters()` ergaenzt.
- i18n de/en/ja: `label_tags`, `tooltip_tags`, `tags_all`, `seq_editor_tags_tooltip`.

**Verwandt:** BL-189 (Sequenz-Detail-Header), BL-190 (Seq-Filter Substring + x).
**Aufwand:** Klein

---

### BL-190: Sequenzen-Filter — Contains/Limit als Suchfeld mit Substring-Vorschlägen + Clear
**Status:** ERLEDIGT (2026-08-27, von David abgenommen)
**Quelle:** Nutzerfeedback Thomas (2026-08-27)

**Ziel:** Die beiden Filterfelder **Contains** („Enthält") und **Limit** im `SequencesWidget` als echte Suchfelder — Tippen liefert eine **Substring**-Vorschlagsliste (nicht nur Wortanfang), sortiert nach dem gewählten Tanzprogramm, plus Clear-Button (x) zum schnellen Zurücksetzen ohne Hochscrollen.

**Umsetzung (`main.py`):**
- Neuer Helper `_setup_search_combo()`: setzt bei beiden Combos `completer().setFilterMode(Qt.MatchContains)` + `setCaseSensitivity(Qt.CaseInsensitive)` und `lineEdit().setClearButtonEnabled(True)`.
- `_combo_limit` jetzt editierbar (`setEditable(True)`, `NoInsert`) inkl. `install_combo_click_to_open`.
- `_on_search_combo_cleared()`: bei geleertem Text → `setCurrentIndex(0)` (Filter entfällt sauber, kein -1).
- Programm-Sortierung: `_rebuild_contains_items()` ordnet Calls mit `teaching_order ≤ Programm-Grenze` nach vorn (stabile Sortierung, TO-Reihenfolge bleibt), Rest danach; aktuelle Auswahl bleibt über `entity_id` erhalten. `_populate_dropdowns()` ruft es auf.
- `set_program_sort_to()` zieht die Programm-Grenze (`dance_programs.sequence_limit_to`) über den bestehenden `_on_dance_program_changed`-Pfad durch — unabhängig vom Limit-Auto-Sync (BL-132).
- Keine neuen i18n-Texte nötig. Fallback-Backup `_fallback/main.py.bak_bl190_seqfilter_*`.

**Ausgeliefert mit:** v0.138.

---

### BL-187: Rule-Aktion „Custom Size Widget" — frei positionierbares Floating-Fenster
**Status:** ERLEDIGT (2026-08-27, von David abgenommen)
**Quelle:** David (2026-08-27)

**Ziel:** Parallele Aktion zu „Fullsize Widget" (`dock_fullsize`), bei der der Nutzer Breite, Höhe sowie X-/Y-Position frei per Prozentwert festlegt — statt der fest verdrahteten 90 % + Zentrierung.

**Umsetzung:**
- Neue Aktion `dock_custom_size` („Custom Size Widget"), Gruppe „Layout & Docks", in `rule_definitions.py`.
- Params (alle `int`, gerendert als Spinbox): `dock_name` (dock_choice), `width_pct` (5–100, Default 90), `height_pct` (5–100, Default 90), `x_pct` (0–100, Default 50), `y_pct` (0–100, Default 50).
- Handler `_rule_dock_custom_size` in `main.py`, vollständige Kopie von `_rule_dock_fullsize` inkl. `_pre_fullsize_state` (Restore über „Layout default laden" funktioniert identisch).
- **X/Y-Semantik = Platzierung im Restraum** (Bildschirm minus Fenster): 0 = bündig links/oben, 50 = zentriert, 100 = bündig rechts/unten → Fenster bleibt bei jeder Größe voll sichtbar.
- Interner Rules-Name bleibt englisch (i18n-Konvention); alte Aktion `dock_fullsize` unangetastet, bestehende Rules brechen nicht.

---

## Nutzerfeedback (Erstnutzer, 2026-03-13)

### BL-002: Keyboard — ENTER zum Auswaehlen von Songs
**Status:** ERLEDIGT (P32)
**Quelle:** Erstnutzer-Feedback
**Beschreibung:** Songs fuer die Playlist sollen auch per ENTER-Taste auswaehlbar sein, nicht nur per Mausklick. Nutzer arbeitet ohne Maus (reiner Tastatur-Nutzer).
**Aufwand:** Klein

### BL-003: F-Tasten-Steuerung unzuverlaessig
**Status:** ERLEDIGT (P32)
**Quelle:** Erstnutzer-Feedback
**Beschreibung:** Die F-Tasten-Shortcuts haben kurz funktioniert, dann nicht mehr. Nutzer hat eine USB-Funk-Fernbedienung, die F-Tasten sendet — wichtig fuer Live-Betrieb.
**Ursache:** `QShortcut` mit Default-Context `WindowShortcut` greift nicht bei abgedockten (floating) QDockWidgets.
**Loesung:** Alle Shortcuts auf `Qt.ShortcutContext.ApplicationShortcut` umgestellt.
**Aufwand:** Klein

### BL-004: Light-Skin — Lyrics schlecht lesbar
**Status:** ERLEDIGT (P30)
**Quelle:** Erstnutzer-Feedback
**Beschreibung:** Einige Lyrics sind im Light-Skin nicht lesbar (Kontrastproblem, vermutlich dunkle Schrift auf hellem Hintergrund bei Lyrics mit eigener Farbgebung).
**Aufwand:** Klein

### BL-005: Lyrics — RTF/HTML-Formatierung anzeigen
**Status:** ERLEDIGT (P30)
**Quelle:** Erstnutzer-Feedback + eigene Beobachtung
**Beschreibung:** Im alten CC waren Textstellen farblich hervorgehoben (Hintergrundfarben). Diese Formatierung aus RTF- und HTML-Lyrics-Dateien wird aktuell weder migriert noch angezeigt. Ziel: Hintergrund-Markierungen aus RTF und HTML weiterhin darstellen.
**Aufwand:** Mittel (RTF-Parsing + HTML-Rendering im Lyrics-Widget)

### BL-006: Win11-Skin ausliefern
**Status:** ERLEDIGT (2026-03-13)
**Quelle:** Erstnutzer-Feedback (mag Dark-Skin nicht)
**Beschreibung:** Nutzer bevorzugt helles, natives Windows-Look. Win11-Skin erstellt und ausgeliefert.

---

## Versionierung (aus docs/08_versionierung.md)

### BL-007: Lyrics-Fenster mit Auto-Scroll
**Status:** ERLEDIGT (P26)
**Quelle:** Versionierung V2

### BL-008: Notizen-Widget
**Status:** ERLEDIGT (v0.53)
**Quelle:** Versionierung V2
**Abhaengigkeit:** Voraussetzung fuer BL-078 (Classes/Teaching Orders)
**Beschreibung:**
Ein eigenes, andockbares Notizen-Widget (QDockWidget) fuer kurze Aufgaben und Erinnerungen. Kann als Dock oder Standalone-Fenster verwendet werden.

**Kernfunktionen:**
- Zwei Bereiche: **Offen** (oben) + **Erledigt** (unten)
- Jede Notiz hat eine Checkbox bzw. Haken-Icon:
  - Offene Notiz: leere Checkbox — Klick → erledigt, wird oben in Erledigt-Liste eingefuegt
  - Erledigte Notiz: gruener Haken — Klick → reaktiviert, wird oben in Offen-Liste eingefuegt
- **Drag & Drop**: Notizen koennen per Maus in der Reihenfolge verschoben werden — innerhalb der Offen-Liste, innerhalb der Erledigt-Liste, und auch zwischen den beiden Listen (entspricht manuell erledigen/reaktivieren). `sort_order` wird beim Drop persistiert.
- **Lokations-Bindung**: Jede Notiz gehoert zu einer Lokation. Die Liste zeigt immer nur Notizen der aktuell gewaehlten Lokation. Beispiel: "Beim naechsten Clubabend Cast Off 3/4 wiederholen."
- **Trennzeilen**: Visuelle Tagesabgrenzungen (fuer Import aus BL-078), die automatisch verschwinden wenn alle Notizen darueber erledigt sind. Trennzeilen koennen ebenfalls per D&D verschoben werden.
- **"Alle erledigen"**: Alle offenen Notizen der aktuellen Lokation auf erledigt setzen
- **Papierkorb**: Erledigte Notizen koennen geloescht werden — erledigte Notizen bleiben aber standardmaessig erhalten (fuer spaetere Auswertung, z.B. wie viele Figuren an einem Class-Abend gelernt wurden)
- Neue Notiz per Eingabefeld oder Button hinzufuegen
- **Mehrfachauswahl + JSON-Export (Speichern)**: Notizen koennen markiert (Mehrfachauswahl) und als neutrale JSON-Datei gespeichert werden (ohne Lokations-Bindung). Dient als einfache Vorlage fuer spaetere Wiederverwendung oder als Basis fuer den Class Designer (BL-078).
- **JSON-Import (Laden)**: Gespeicherte JSON-Datei laden und als Notizen + Trennzeilen in die aktuelle Lokation einfuegen. Import ist idempotent (prueft per `source_ref`).
- Toolbar oder Buttonleiste im Widget mit: **[+ Notiz]** | **[Laden]** | **[Speichern]** | **[Alle erledigen]** | **[Papierkorb]**

**Datenhaltung:**
- SQLite-Tabelle `notes` (id, text, status [open/done/deleted], location_id, sort_order, note_type [normal/separator], created_at, done_at, source [manual/import], source_ref)
- Status `done` = archiviert, nicht geloescht (fuer Auswertung)
- Status `deleted` = Papierkorb (echtes Loeschen)

**JSON-Export-Format (neutral, ohne Lokation):**
```json
[
  {"text": "Swing Thru teachen", "type": "new"},
  {"text": "Trade wiederholen", "type": "repeat"},
  {"text": "---", "type": "separator", "label": "Abend 2"},
  {"text": "Cast Off 3/4 teachen", "type": "new"}
]
```

**Aufwand:** Mittel

### BL-009: Pattern-Dauer-Warnung
**Status:** ERLEDIGT
**Quelle:** Versionierung V2
**Beschreibung:** Warnung wenn Pattern-Teil eines Songs zu lang/kurz laeuft.

### BL-010: GEMA-Export
**Status:** ERLEDIGT (P47 — Reports-Fenster)
**Quelle:** Versionierung V2
**Beschreibung:** Export der Abspielhistorie — abgedeckt durch das Reports-Fenster.

### BL-011: Migration SquareView
**Status:** ERLEDIGT (v0.48)
**Quelle:** Versionierung V2
**Beschreibung:** Import von Daten aus SquareView (zweites gaengiges Caller-Programm). Testdaten von Caller-Kollegen erwartet.
**Loesung:** Vollstaendige SqView-Migration in v0.48 — Ordner-Auswahl, Blind-Import, rekursiver MP3-Index, Lyrics-Matching (4-stufige Regex-Strategie), Loop/Pitch-Uebernahme, Abspielhistorie. Weitergefuehrt in v0.39 (Beta) und v0.48 (produktionsreif).

---

## Songverwaltung (aus docs/02_songverwaltung.md)

### BL-012: Bulk-Import
**Status:** ERLEDIGT — Mehrfachauswahl im Datei-Dialog sowie Ordner-Import bereits implementiert.

---

## UI / Layout (aus docs/05_ui_fenster_layout.md + docs/12_erfahrungen.md)

### BL-013: Mehrere Layouts
**Status:** ERLEDIGT (P28)
**Quelle:** Docs
**Beschreibung:** Mehrere benannte Layouts speichern und laden (z.B. "Live.ini", "Workshop.ini").

### BL-014: Icon-Buttons im Player statt Menu
**Status:** ERLEDIGT (Redesign)
**Quelle:** docs/12_erfahrungen.md
**Beschreibung:** Ein-/Ausblenden von Dock-Modulen ueber Icon-Buttons im Player statt ueber Menu.

---

## Sequenzen (aus docs/13_sequenzen.md)

### BL-015: Sequenz-Editor
**Status:** ERLEDIGT (v0.90)
**Quelle:** Docs
**Beschreibung:** Neue Sequenzen erstellen, bestehende bearbeiten.
**Loesung:** `SequenceEditorDialog` (modal). Kopfbereich mit Typ (**Pflichtfeld**) + Schwierigkeit (optional; editierbare Dropdowns, mit vorhandenen DB-Werten vorbefuellt), darunter ein mehrzeiliges Eingabefeld fuer die Calls — **ein Call pro Zeile** (Grundlage fuers Mapping). Buttons: „+ Neu", „Speichern", „Auf Duplikate pruefen" (prueft die aktuelle Eingabe gegen die DB via `find_sequence_by_fields`), „Schliessen". Limit 15 Calls (DB-Schema field_1..15) wird live angezeigt und beim Speichern erzwungen. Nach dem Speichern: `recompute_sequence_max_to()` → Level wird automatisch aus den Calls berechnet. Erreichbar ueber Menue „Sequenzen → Sequenz-Editor..." und ueber den ✎-Button im SequenzView (Bearbeiten der angezeigten Sequenz). Neue DB-Methoden: `get_sequence_raw`, `update_sequence`, `find_sequence_by_fields`.

**Erweiterungen (v0.90):**
- **Live-Mapping-Markierung:** Jede Zeile, deren Call-Text bereits gemappt ist, wird gruen hinterlegt (`_MappingHighlighter` + Cache, DB via neue Methode `get_entity_for_call_text`).
- **Doppelklick auf nicht gemappte Zeile** oeffnet `CallMapPickerDialog` — schlanker Einzel-Picker mit durchsuchbarer Call-Auswahl, vorausgewaehlt per `CallMatcher`-Vorschlag; speichert via `set_call_text_mapping(mapped_by='manual')`, danach wird die Zeile automatisch gruen. Funktioniert auch vor dem Speichern der Sequenz.
- **Sichtbarkeits-Fix:** Nach Neuanlage werden die Sequenzlisten-Filter zurueckgesetzt (`reset_filters`) und die neue Sequenz markiert + im SequenzView geoeffnet (`select_sequence`). Behebt das Problem, dass eine neue Sequenz durch den Default-Typ-Filter „Singer (Corner progression)" sofort wieder ausgeblendet wurde.

### BL-018: Sequenz-Export
**Status:** ERLEDIGT (v0.63 — JSON)
**Quelle:** Docs
**Beschreibung:** Sequenzen als Text/PDF exportieren.
**Loesung:** JSON-Export in v0.63 — exportiert alle Sequenzen im selben Format wie der JSON-Import erwartet (id, calls, level, seq_type, difficulty). Exportierte Datei kann direkt per „Sequenzen importieren (JSON)" wieder eingelesen werden. PDF-Export bleibt als optionale Erweiterung offen.

---

## Spaetere Versionen (aus docs/08_versionierung.md)

### BL-019: Statistikfunktionen
**Status:** ERLEDIGT (v0.65)
**Quelle:** Versionierung "Spaeter"
**Beschreibung:** Neues Dock „Statistik" (lazy init, tabbiert mit Reports).
- Filter: Lokation (Alle / einzelne), Typ (Beide/Pattern/Singing), Zeitraum (Alle Zeit / 5J / 1J / 3M / 1M)
- 3 Spalten: TOP (meistgespielt), FLOP (wenigstgespielt), Nie gespielt — alle Songs scrollbar, kein Limit
- Doppelklick auf Song → springt zur Songliste
- Histogramm (volle Breite): Bin 0 fest für nie gespielt, 9 logarithmische Bins für count≥1
- Farbgradient Blau→Orange-Rot (kalt→heiß), Balken-Tooltips mit bis zu 5 Beispiel-Songs
- Übersetzungen DE/EN vollständig

### BL-020: Weitere Hotkeys
**Status:** ENTFAELLT — zusammengeführt in BL-064
**Quelle:** Versionierung "Spaeter"

### BL-022: Erweiterte Foto-Funktionen
**Status:** ENTFAELLT — durch BL-041 abgedeckt (Webcam-Foto vom PilotSquare, P41)
**Quelle:** Versionierung "Spaeter"
**Beschreibung:** Foto-Modul fuer Club-Bilder etc.

---

## Audio-Formate (P31+)

### BL-023: Song-Datensatz — Datei-Auswahlbutton
**Status:** ERLEDIGT (P32)
**Quelle:** Nutzerfeedback (2026-03-16)
**Beschreibung:** In den Song-Daten (Bearbeiten-Dialog) einen Button einfuegen, ueber den eine Songdatei ausgewaehlt werden kann, solange sie im Music-Ordner liegt. Damit kann ein Song-Datensatz nachtraeglich mit einer anderen Datei verknuepft werden.
**Loesung:** "..."-Button neben Dateiname, `update_filename()` in SongDB mit UNIQUE-Check, Kopie-Dialog bei Konflikten.
**Aufwand:** Klein

### BL-024: Erweiterte Audio-Format-Unterstuetzung
**Status:** ERLEDIGT (P32)
**Quelle:** Nutzerfeedback (2026-03-16)
**Beschreibung:** Alle Dateiauswahl-Dialoge fuer Songs (Laden, Import, Bulk-Import) akzeptieren derzeit nur MP3. Die Auswahl soll auf alle von libsndfile unterstuetzten Formate erweitert werden: WAV, FLAC, OGG, AIFF, AU, CAF, W64, MP3. Dateifilter im Dialog entsprechend anpassen.
**Aufwand:** Klein

### BL-025: Loop-Crossfade
**Status:** ERLEDIGT (P32)
**Quelle:** Eigene Entwicklung (2026-03-18)
**Beschreibung:** Nahtloser Loop-Uebergang durch Crossfade statt hartem Schnitt. Eliminiert WSOLA-Artefakte am Loop-Punkt. Budget-basierter Mechanismus im Audio-Callback, konfigurierbare Crossfade-Dauer via INI.
**Aufwand:** Gross

### BL-026: Loop-Offset pro Song
**Status:** ERLEDIGT (P32)
**Quelle:** Eigene Entwicklung (2026-03-18)
**Beschreibung:** Automatische Offset-Messung via FFT-Kreuzkorrelation im Bass-Bereich (<200Hz). Findet den optimalen Versatz zwischen Loop-Ende und Loop-Anfang. Offset pro Song in DB gespeichert, manuell korrigierbar. Auto-Messung bei Beat Snap und Loop-Test.
**Aufwand:** Gross

### BL-027: Potential-Widget (Datenqualitaet)
**Status:** ERLEDIGT (P33, erweitert v0.44+)
**Quelle:** Eigene Entwicklung (2026-03-18)
**Beschreibung:** Dashboard zur Identifikation von Datenqualitaetsproblemen. 5 Checks (Singing ohne Lyrics, Pattern ohne Loop, Loop ohne BeatSnap, leere Lokationen, verwaiste Historie). Navigation per Doppelklick, Ignorieren-Funktion, Batch-Bereinigung.
**Erweiterung (2026-05-07):** 2 neue Checks: "Ohne MP3" (Songs deren Datei nicht gefunden wird) und "Ohne Qualitaet" (Songs mit quality=0). Beide mit Doppelklick-Navigation zur Songliste und Ignorieren-Funktion.
**Aufwand:** Mittel

### BL-028: Lokation loeschen mit Historie-Option
**Status:** ERLEDIGT (P33)
**Quelle:** Nutzerfeedback (2026-03-18)
**Beschreibung:** Loesch-Button im Lokations-Dialog war wirkungslos (Foreign Key Constraint). Jetzt mit Bestaetigungsdialog und Checkbox "Historiendaten ebenfalls loeschen".
**Aufwand:** Klein

### BL-029: App-weite Keyboard-Shortcuts (L / P)
**Status:** ERLEDIGT (P34)
**Quelle:** Eigene Entwicklung (2026-03-19)
**Beschreibung:** Einzelne Buchstaben-Shortcuts (L=Lokation, P=Planner) app-weit, funktionieren auch bei fokussierten Tabellen/Listen. EventFilter statt QShortcut noetig wegen type-to-search in QTableWidget. Planner-Sortierung wird automatisch vorausgewaehlt.
**Aufwand:** Mittel

### BL-030: Elegant Gold Theme
**Status:** ERLEDIGT (P34)
**Quelle:** Eigene Entwicklung (2026-03-19)
**Beschreibung:** Neues Theme mit Anthrazit-Basis und strahlendem Gold. Komplettes Skin-Set (skin.json, skin.qss, 7 SVG-Icons). Arrow-SVGs als filled-polygon (nicht stroke) fuer korrekte Darstellung in SpinBox-Pfeilen.
**Aufwand:** Mittel

---

## Nutzerfeedback (ein User, 2026-03-22)

### BL-031: Song direkt neu starten (ohne Stop/Start)
**Status:** ERLEDIGT (P41)
**Quelle:** ein User
**Beschreibung:** Song soll per einzelnem Befehl sofort von vorne beginnen, ohne erst Stop und dann Start druecken zu muessen.
**Aufwand:** Klein

### BL-032: Import inkl. aller Unterordner
**Status:** ERLEDIGT (P43)
**Quelle:** ein User
**Beschreibung:** Beim Import sollen Unterordner rekursiv durchsucht werden, nicht nur die oberste Ebene.
**Loesung:** Neuer Zwischendialog "Importquelle" mit Auswahl "Einzelne Dateien" / "Ordner (inkl. Unterordner)". Bei Ordner-Auswahl wird via `os.walk()` rekursiv nach .mp3/.wav/.flac/.ogg/.aiff/.aif gesucht.
**Aufwand:** Klein

### BL-033: Songvorschlag (Pattern / Singing)
**Status:** ERLEDIGT (v0.85)
**Quelle:** ein User
**Beschreibung:** Per Taste (z.B. "V" wie Vorschlag) soll ein Fenster mit X Vorschlaegen erscheinen (konfigurierbare Anzahl). Getrennt fuer Pattern und Singing. Mehrere Vorschlaege koennen in die Playlist uebernommen werden.
**Loesung:** Abgedeckt durch Auto-Fill im Planner (Empfehlungssortierung, P/S-Filter, direkte Playlist-Uebernahme) und Evening Planner.
**Aufwand:** Mittel

### BL-034: Massenaenderung Singing/Pattern
**Status:** ERLEDIGT (P41)
**Quelle:** ein User
**Beschreibung:** Mehrere Songs gleichzeitig als Singing oder Pattern markieren. Z.B. alle "SQR XXX" selektieren und auf Singing aendern, alle "SQR 9XX" auf Pattern. Wichtig fuer Import aus SqView, wo die Unterscheidung nur ueber Verzeichnisse laeuft.
**Aufwand:** Mittel

### BL-035: Qualitaetsbewertung nach Abspielen
**Status:** ERLEDIGT (v0.82 / BL-119)
**Quelle:** ein User
**Beschreibung:** Nach dem Abspielen eines Songs Abfrage der Qualitaet (1-9), wenn noch nicht bewertet. Alternativ ueber einen Button "Qualitaet" ausloesbar.
**Aufwand:** Mittel

### BL-036: Eigene Tasten in Rules belegen
**Status:** ENTFAELLT — zusammengeführt in BL-064
**Quelle:** ein User

### BL-037: Lyrics-Fenster maximiert mit angedocktem Player (Singing Call)
**Status:** ERLEDIGT (via Rules + dual_view)
**Quelle:** ein User
**Beschreibung:** Layout-Variante fuer Singing Calls: Lyrics-Fenster maximiert, Play-Fenster angedockt.
**Aufwand:** Klein (ueber Layout-System loesbar)

### BL-039: Songs aus Datenbank loeschen
**Status:** ERLEDIGT (P41)
**Quelle:** ein User
**Beschreibung:** Songs einzeln oder mehrfach aus der Datenbank entfernen koennen. Mit Warn-Nachfrage und Option, die Historiendaten (play_history, song_location_stats) zum Song direkt mit aufzuraeumen. Analog zur Lokation-Loesch-Funktion (BL-028).
**Aufwand:** Klein

### BL-040: Neue Imports als Liste anzeigen (nach Datum)
**Status:** ERLEDIGT (v0.108, 2026-06-24)
**Quelle:** ein User
**Beschreibung:** Uebersicht der zuletzt importierten Songs, sortiert nach Import-Datum. Damit sieht man sofort, was neu dazugekommen ist.
**Loesung:** Statt einer separaten Datums-Liste wird das bestehende Genre-System genutzt: Jeder neu angelegte Song erhaelt automatisch das Genre **"NEW"** (zentral in `SongDatabase.insert()`, additiv via `add_song_genre()` — ueberschreibt keine spaeteren Genres). Erfasst alle produktiven Wege (Import, ZIP-Import, "Neu"-Button, `get_or_create` beim Laden unbekannter MP3); die Migration umgeht `insert()` und taggt Altbestand bewusst nicht. Der Import-Keyword-Block setzt Genre-Vorschlaege jetzt additiv statt ersetzend. Caller filtern auf "NEW" und entfernen das Tag pro Song, wenn der Song eingearbeitet ist.
**Aufwand:** Klein

---

## Eigene Ideen / Erweiterungen

### BL-041: Foto vom PilotSquare mit Webcam
**Status:** ERLEDIGT (P41)
**Quelle:** David
**Beschreibung:** Per Webcam ein Foto vom PilotSquare (Tanzgruppe) schiessen und im Programm anzeigen lassen. Zuordnung zum aktuellen Event/Lokation.
**Aufwand:** Mittel

### BL-042: Loop-Anzahl / Zeitgesteuerter Loop
**Status:** ERLEDIGT (P40)
**Quelle:** David
**Beschreibung:** Neben dem bisherigen Endlos-Loop (Standard, bleibt erhalten) eine neue Funktion: Der Caller legt eine gewuenschte Pattern-Dauer fest (z.B. 7 Minuten). Callers Caddy berechnet die noetige Anzahl Loops:
- **Formel:** Gewuenschte Laufzeit = Dauer vor Loop-In + N × Loop-Dauer + Dauer nach Loop-Out
- **Anzeige:** Zwei Optionen (ein Loop mehr / ein Loop weniger) mit resultierender Gesamtdauer
- **UI:** Loop-Anzahl wird im Player oben links neben der Song-Dauer angezeigt
- **Playlist/Planner:** Neue Spalte fuer Loop-Anzahl, Caller kann pro Song die gewuenschte Laufzeit festlegen
- **Architektur:** Als eigenstaendige Funktion aufsetzen, damit spaeter auch als Rules-Aktion einbindbar
- Der Endlos-Loop bleibt Standard in Playlist und Planner
**Aufwand:** Gross

### BL-043: RTF-Lyrics — Word-Binaerdaten als sichtbare Zeichen
**Status:** ERLEDIGT (P41)
**Quelle:** Claus (Nutzerfeedback, 2026-03-26)
**Beschreibung:** Word-RTF-Dateien enthalten diverse `{\*\...}`-Bloecke (themedata, datastore, colorschememapping, xmlnstbl, latentstyles, wgrffmtfilter, rsidtbl) mit Hex-Dumps, OLE-Objekten und XML. Qt rendert deren Inhalt als sichtbare Zeichen im Lyrics-Fenster. Bei "ACHY BREAKY HEART.rtf" waren 48% der Datei Word-Muell.
**Loesung:** Neue Methode `_strip_rtf_binary_groups()` mit Whitelist-Ansatz: Alle `{\*\...}`-Gruppen die NICHT auf einer Whitelist stehen (fonttbl, colortbl, stylesheet etc.) werden vor dem Parsen entfernt. In RTF bedeutet `\*` "ignorable destination" — der Ansatz ist standardkonform und zukunftssicher.
**Aufwand:** Klein

### BL-044: Rule-Aktion "GoTo" (Sprung zu Position)
**Status:** ERLEDIGT (P42)
**Quelle:** David
**Beschreibung:** Neue Regel-Aktion "GoTo" mit Parameter-Auswahl: Anfang, Loop-In, Loop-Out, Ende. Der Song springt zur gewaehlten Position. Nuetzlich fuer automatisierte Workflows (z.B. nach Pause zurueck zum Loop-In springen).
**Aufwand:** Klein

### BL-045: Rule-Aktion "Toggle Loop Active"
**Status:** ERLEDIGT (P42)
**Quelle:** David
**Beschreibung:** Neue Regel-Aktion zum Umschalten von Loop Active/Inactive. Ermoeglicht regelbasierte Loop-Steuerung (z.B. Loop aktivieren bei Pattern, deaktivieren bei Singing).
**Aufwand:** Klein

### BL-046: Loop Finder — Benutzerdefinierte Parameter-Presets
**Status:** ERLEDIGT (P47)
**Quelle:** David (Nutzerfeedback von Callern)
**Beschreibung:** Caller moechten eigene Loop-Finder-Parameter-Sets definieren und speichern. Aktuell gibt es nur einen Standard-Parametersatz, der manuell geaendert werden kann.
- **Speichern/Laden**: Button "Speichern" und "Laden" (oder ComboBox) fuer benannte Presets
- **Persistenz**: Presets in INI oder DB speichern (z.B. "Tight Loop", "Long Phrase", "Minimal")
- **Rules-Integration**: Die Aktion "Auto-Set Best Loop" bekommt einen neuen Parameter fuer das Preset, damit regelbasiert verschiedene Suchstrategien genutzt werden koennen
- **Default**: Bisheriger Standard bleibt als "Default"-Preset erhalten
**Aufwand:** Mittel

### BL-047: CC1-Migration — Erweiterte MDB-Tabellen (access-parser Workaround)
**Status:** ERLEDIGT (P41)
**Quelle:** Ralf Bender (Nutzerfeedback, 2026-03-26)
**Beschreibung:** Ralf hatte seine CC1-Datenbank (callerv2.mdb) um 13 eigene Spalten erweitert (Year, Composer, Interpret etc.). Die access-parser-Library hat drei Bugs bei solchen Tabellen:
1. Off-by-One in null_table Boundary-Check (`>` statt `>=`) → IndexError
2. `_parse_row()` nicht transaktional → Row-Count-Mismatch (Fixed-Length vs. Dynamic-Length)
3. Primary-Key-Lookup referenziert geloeschte column_ids → KeyError
Zusaetzlich: Tabellenname "Gruppen" statt "gruppen" (Case-Sensitivity).
**Loesung:**
- 3 Monkey-Patches fuer access-parser (null_table, parse_row, get_table_columns)
- Case-insensitiver Tabellennamen-Fallback
- Offizielle Spalten-Whitelist (nur CC1-Standard-Spalten uebernehmen)
- **History-Based Reconstruction Fallback**: Wenn Dynamic-Length-Felder unlesbar sind (Song-Name/URL_Music = None), werden Songs und Lokationen aus den Historie-Eintraegen rekonstruiert. Ergebnis bei Ralf: 1527 Songs, 17 Lokationen, 26719 Historie — alles korrekt verknuepft.
- Case-insensitives Feld-Matching im Migration-Worker (Titel/titel, Gruppe/gruppe)
**Aufwand:** Gross (Root-Cause-Analyse + Library-Patches + Fallback-Logik)

---

## Nutzerfeedback (David, 2026-03-28)

### BL-048: Rule-Aktion "Volume +/-"
**Status:** ERLEDIGT (bereits vorhanden seit P34)
**Quelle:** David
**Beschreibung:** Neue Regel-Aktion zum Erhoehen oder Verringern der Lautstaerke. Die Distanz (Schrittweite) ist ueber einen Parameter einstellbar. Der geaenderte Volume-Wert wird pro Song in der Datenbank gespeichert, damit er beim naechsten Abspielen wiederhergestellt wird.
**Hinweis:** War bereits als `volume_change` Action implementiert (Delta-Parameter, DB-Save via SpinBox).
**Aufwand:** Mittel

### BL-049: Planner — Playlist komplett loeschen
**Status:** ERLEDIGT (P42)
**Quelle:** David
**Beschreibung:** Im Planner einen Button mit einem dicken X oberhalb des Bestaetigungs-Buttons. Damit wird die gesamte Playlist geloescht. Mit Rueckfrage-Dialog vor dem Loeschen.
**Aufwand:** Klein

### BL-050: Mehrere Suchpfade fuer Musik-Dateien
**Status:** ERLEDIGT (P46)
**Quelle:** David
**Beschreibung:** 4 definierbare Suchpfade fuer Musik-Dateien, gespeichert in der INI-Datei. Beim Abspielen wird zuerst in Pfad 1 gesucht, dann Pfad 2 usw. Auswirkungen auf Import, Dateiauswahl und Migration muessen geprueft werden.
**Hinweis:** Plan vor Umsetzung besprechen (Auswirkungen auf Import etc.)
**Aufwand:** Mittel

### BL-051: Song-Daten anzeigen auch ohne MP3
**Status:** ERLEDIGT (P42)
**Quelle:** David
**Prioritaet:** Hoch
**Beschreibung:** Song-Datensatz soll auch dann angezeigt werden, wenn keine zugehoerige MP3-Datei gefunden wurde. Der Nutzer kann dann manuell eine Datei verlinken oder sich die Migrationsdaten ansehen. Aktuell werden Songs ohne Datei moeglicherweise nicht vollstaendig dargestellt.
**Aufwand:** Klein

### BL-052: App-Menu mit "Beenden"
**Status:** ERLEDIGT (P42)
**Quelle:** David
**Beschreibung:** Neuer erster Menu-Eintrag "App" mit dem Unterpunkt "Beenden". Aktuell kann die App nur ueber das X geschlossen werden — das ist schlechter Stil.
**Aufwand:** Klein

---

## Nutzerfeedback (ein User, 2026-03-28)

### BL-053: Pattern-Laenge pro Gruppe/Abend (Erweiterung BL-042)
**Status:** ERLEDIGT (v0.55 — via BL-085 Planner + Tanzprogramm)
**Quelle:** ein User
**Beschreibung:** Die Pattern-Dauer soll pro Gruppe/Abend definierbar sein (z.B. MS-Abend = 9 Min, A1 = 12 Min). Die Loop-Anzahl und Ende-Marke (im Takt) werden beim Start des Patterns dynamisch berechnet. Die Startmarke bleibt immer gleich. ein User hat den Algorithmus aus dem alten CC und liefert ihn nach.
**Bezug:** Erweitert BL-042 (Loop-Count), das die Grundfunktion bereits implementiert hat (P40).
**Aufwand:** Mittel

### BL-054: Songvorschlag — Qualitaetsfilter und Historie (Erweiterung BL-033)
**Status:** ERLEDIGT (v0.85)
**Quelle:** ein User
**Beschreibung:** Erweiterung des Songvorschlags (BL-033): Qualitaetsfilter (z.B. "alles ab Qualitaet 7"), bereits gespielte Songs mit Datum anzeigen, Uebernahme in Playlist. Getrennt fuer Pattern und Singing.
**Loesung:** Vollstaendig im Planner abgedeckt: Qualitaetssortierung, Empfehlungssortierung (Qualitaet × Spielabstand), Datumsanzeige, P/S-Filter, Playlist-Transfer.
**Bezug:** Ergaenzt BL-033 um konkrete Filterkriterien.
**Aufwand:** Mittel

## Nutzerfeedback (Mike Blane, 2026-03-30)

### BL-058: Erststart-Sprachabfrage (Deutsch / English)
**Status:** ERLEDIGT (P43)
**Quelle:** Mike Blane (First Impressions)
**Beschreibung:** Beim allerersten Start (keine Sprache in INI gesetzt) soll ein einfacher Dialog erscheinen: "Deutsch? English?" mit zwei Buttons. Ein nicht-deutschsprachiger Nutzer findet "Einstellungen → Sprache" nicht. Alternative: Sprach-Flaggen wie auf der Website.
**Umsetzung:** INI-Feld `display/language` nicht vorbelegen. Wenn leer → Sprachauswahl-Dialog vor dem Hauptfenster anzeigen.
**Aufwand:** Klein

### BL-059: Tabs oben statt unten (englische UI-Konvention)
**Status:** ENTFAELLT (2026-04-04)
**Quelle:** Mike Blane (First Impressions)
**Beschreibung:** Die Tabs (Song List / Lyrics / Song Data / Sequences) befinden sich unterhalb des Inhalts. In englischsprachigen Apps sind Tabs ueblicherweise oben. Der Tester hat nicht sofort erkannt, dass die Tabs den darueberliegenden Inhalt steuern.
**Entscheidung:** Abgelehnt. Die Tabs bleiben unten — diese Anordnung war bereits im alten Callers Caddy (1.x) so und ist bewusste Designentscheidung. Bestandsnutzer erwarten das Verhalten.

### BL-060: Aktiver Tab besser unterscheidbar (Song List / Sequences)
**Status:** ERLEDIGT (P43)
**Quelle:** Mike Blane (First Impressions)
**Beschreibung:** Die Tabs "Song List" und "Sequences" sehen beide grau aus. Der aktive Tab muss sich farblich deutlicher abheben. Betrifft alle Themes.
**Loesung:** `QTabBar::tab:selected` mit `font-weight: bold` in allen vier Skins (elegant war bereits bold). Win11 zusaetzlich mit 3px statt 2px Border + expliziter Background-Farbe. Default mit Top-Border 2px + Bold.
**Aufwand:** Klein

### BL-061: Tour — Tab-Wechsel visuell hervorheben
**Status:** ENTFAELLT (2026-04-07)
**Quelle:** Mike Blane (First Impressions)
**Entscheidung:** Abgelehnt vom User.

### BL-062: Nach Song-Import Hinweis wo Songs erscheinen
**Status:** ERLEDIGT (P43)
**Quelle:** Mike Blane (First Impressions)
**Beschreibung:** Nach dem Import ueber "Import new songs" war nicht klar, wo die Songs in der Songliste auftauchen. Ein kurzer Hinweis-Toast oder automatischer Wechsel zum Song-List-Tab waere hilfreich.
**Loesung:** Nach erfolgreichem Import wird `dock_list.raise_()` aufgerufen (Song-List-Tab kommt in den Vordergrund). Zusaetzlich eine neue Zeile in der Import-Zusammenfassung: "Die neuen Songs wurden der Songliste hinzugefuegt."
**Aufwand:** Klein

---

## Bugs / Performance

### BL-057: Performance-Probleme beim Systemstart (Laptop)
**Status:** ERLEDIGT (P44/P45)
**Quelle:** David
**Loesung:** Lazy-Initialisierung der Tutorials umgesetzt. Startzeit auf dem Laptop von ~1889ms auf akzeptables Niveau reduziert. Weitere Optimierung nicht mehr sinnvoll (3x-Faktor ist Hardware-bedingt, kein Bug).

---

## Nutzerfeedback (David, 2026-04-04)

### BL-063: Genre-Verwaltung mit Master-Liste
**Status:** ERLEDIGT (P45)
**Quelle:** David
**Loesung:** Many-to-Many (song_genres), 65 Default-Genres, Genre-Manager-Dialog (Anlegen/Umbenennen/Loeschen+Reassign), Song-Datensatz mit Checkbox-Dialog, Import-Keyword-Matching, Rules-Aktionen genre_add/genre_remove mit genre_choice-Dropdown.

### BL-064: Frei belegbare Tastenkuerzel (Rules + App-Navigation)
**Status:** ERLEDIGT (v0.50)
**Quelle:** ein User, David
**Beschreibung:** Einheitliches Konzept für benutzerdefinierte Tastenkürzel in der gesamten App:
1. **Rule-Trigger**: In der Rule Engine beliebige Tasten (inkl. Buchstaben) als Auslöser vergeben — z.B. "F" = Fade starten, "N" = nächster Song.
2. **Modul-Navigation**: Feste App-Shortcuts für Modul-Wechsel (z.B. S=Song Data, R=Rules, Q=Sequences, I=Loop Finder).
3. **Konfliktlösung**: Buchstaben-Shortcuts dürfen nur feuern, wenn kein Eingabefeld (QLineEdit, QTextEdit, QSpinBox) den Fokus hat. Listen mit type-to-search (QTableWidget, QListWidget) gelten als neutral — Buchstabe feuert NICHT wenn die Liste den Fokus hat und der Buchstabe als Suchzeichen interpretiert werden könnte. Explizite Fokus-Prüfung im App-weiten EventFilter (wie bereits bei L/P umgesetzt, BL-029).
**Umsetzung:**
- Konfigurationsdialog: Taste → Aktion (Rule-Trigger oder Modul-Shortcut)
- EventFilter erweitern um Fokus-Kontext-Prüfung
- Kollisions-Check beim Belegen (bereits belegte Tasten warnen)
- Doku in Shortcuts-Hilfe
**Aufwand:** Mittel

### BL-065: Import/Migration — Fehlertolerant bei defekten MP3s
**Status:** ERLEDIGT (P43)
**Quelle:** David
**Beschreibung:** Aktuell bricht Import bzw. Migration ab, wenn eine MP3-Datei defekt oder unlesbar ist (Header-Fehler, Truncation, falsches Format). Stattdessen: Datei ueberspringen, Fehler protokollieren, am Ende Report mit Liste der uebersprungenen Dateien anzeigen. Verarbeitung der restlichen Dateien laeuft ununterbrochen weiter.
**Umsetzung:**
- `try/except` um Einzeldatei-Verarbeitung
- Fehlerliste sammeln (Dateiname, Fehlermeldung)
- Abschluss-Dialog mit Report ("3 Dateien uebersprungen: ...")
- Optional: Report als TXT exportieren
**Aufwand:** Klein
**Bewertung:** Hoher Nutzwert bei wenig Aufwand — Quickwin. Besonders wichtig fuer Migration grosser Alt-Bestaende (siehe BL-047 Ralf Bender).

### BL-073: Abendplanung — kompletter Tanzabend als Vorschlag
**Status:** ERLEDIGT (Evening Planner, laufende Weiterentwicklung)
**Quelle:** David
**Beschreibung:** Assistent schlägt auf Knopfdruck eine vollständige Abendstruktur vor (Anzahl Pattern, Singing Calls, Pausen, Abschluss). Konfigurierbar: Abendlänge, Pausenanzahl, Verhältnis Pattern/Singing, Programm-Level. Vorschlag wird als Playlist übernommen oder manuell angepasst.
**Loesung:** Evening Planner umgesetzt. Noch nicht perfekt, aber funktionsfaehig — ongoing improvement.
**Aufwand:** Groß

### BL-074: Lieder vorhören über zweiten Audio-Ausgang
**Status:** ERLEDIGT (v0.89)
**Quelle:** David
**Beschreibung:** Während ein Song über den Haupt-Ausgang (PA/Anlage) läuft, soll der Caller einzelne Songs über einen zweiten Ausgang (internen Laptop-Lautsprecher oder Kopfhörer) vorhören können — ohne Unterbrechung des laufenden Songs.

**Neues Design (v0.85):**
- Audio-Gerät-ComboBox aus der Statusleiste entfernen (BL-126 rückgängig)
- Stattdessen: neues **Audio-Output-Fenster** (eigenes Dock oder Dialog)
  - Auswahl „Haupt-Ausgang" (Kabel zur Anlage): Gerät + Kanal konfigurierbar
  - Auswahl „Vorhören" (interner Lautsprecher / Kopfhörer): Gerät + Kanal konfigurierbar
  - Einstellungen werden gespeichert (INI)
- Im Player: neuer kleiner **„Vorhören"-Button** neben dem Laden-Button
  - Lädt den ausgewählten Song auf den zweiten Audio-Stream (ohne den laufenden Haupt-Stream zu unterbrechen)

**Technisch:** Zweiter separater AudioEngine-Stream auf dem konfigurierten Preview-Gerät.
**Aufwand:** Groß (zweiter Audio-Stream, Audio-Output-Fenster)

### BL-076: Pause-Countdown
**Status:** ERLEDIGT
**Quelle:** David
**Beschreibung:** Sichtbarer Countdown-Timer für Tanzpausen. Caller definiert Pausenlänge, Timer läuft sichtbar im UI herunter. Optional: akustisches Signal kurz vor Ende der Pause. Hilft dem Caller, Pausen zuverlässig einzuhalten ohne auf die Uhr schauen zu müssen.
**Aufwand:** Klein

### BL-067: Crossfade auch beim Beat Snap
**Status:** ERLEDIGT (P47)
**Quelle:** David
**Loesung:** Toggle-Button "CrossFade" im Beat-Snap-Dialog zwischen Snap und Vorhören. Default OFF, wird bei Drag automatisch zurückgesetzt. Bei aktivem Toggle: Vorhören nutzt `seek_with_crossfade()` mit der konfigurierten Engine-Crossfade-Dauer — identisches Verhalten wie im normalen Betrieb.

### BL-070: Mindest-Lautstaerke-Boden + Live-Lautstaerke
**Status:** ERLEDIGT (P46)
**Quelle:** Jack Kirchgatter
**Beschreibung:** Jack hat ein physisches Geraet am Mikrofon, mit dem er die Ausgangslautstaerke des Songs live regeln kann (z.B. um die Musik leiser zu machen waehrend er dem Saal etwas erklaert). Dafuer braucht es zwei Erweiterungen:
1. **Live-Lautstaerke** (Session-Wert): Zusaetzlich zur bestehenden Song-Lautstaerke (persistent, pro Song in DB) ein zweites Lautstaerke-Konzept fuer die laufende Session. Aendert sich im Betrieb, wird nicht gespeichert. Wird z.B. ueber eine Rules-Aktion oder ein Hardware-Signal gesteuert.
2. **Mindest-Lautstaerke (INI-Setting)**: `audio/min_volume` (z.B. 0.20 = 20%). Die Live-Lautstaerke kann nie unter diesen Wert sinken — sicherheitshalber damit die Musik nicht komplett wegfaellt. Einstellbar in den Einstellungen oder direkt in der INI.
**Technische Implikation:** Derzeit gibt es nur `song.volume` (persistent). Gebraucht wird ein zweiter Layer: `current_live_volume` (fluechtiger Faktor, Standard 1.0), der mit `song.volume` multipliziert wird. Clamp nach unten auf `min_volume`. Die Unterscheidung "Song-Lautstaerke vs. Live-Lautstaerke" muss in der Audio-Engine beruecksichtigt werden.
**Aufwand:** Mittel

### BL-068: Mindestbreite fuer Player- und Loop-Widget
**Status:** ERLEDIGT (P44)
**Quelle:** David
**Beschreibung:** Player-Widget und Loop-Widget koennen per Maus so schmal gezogen werden, dass Bedienelemente unleserlich oder nicht mehr bedienbar sind. Mindestbreite fuer beide Docks festlegen.
**Loesung:** setMinimumWidth() in _build_ui() beider Klassen.
**Aufwand:** Klein

### BL-069: Rules — Aktionen per Drag&Drop umordnen
**Status:** ERLEDIGT (P45)
**Quelle:** David
**Beschreibung:** Reihenfolge der Aktionen in einer Rule war nur durch Loeschen und Neuanlegen aenderbar.
**Loesung:** `_ActionDragHandle` (≡-Label) an jeder Aktion-Zeile ganz links. `mouseMoveEvent` → `_on_action_drag()` verschiebt Widget live im QVBoxLayout. Bugfix: `_on_action_type_changed` verwendete falschen Index nach Handle-Einfuegung.
**Aufwand:** Klein

---

### BL-077: Dual-Ansicht (zwei Widgets nebeneinander)
**Status:** ERLEDIGT (v0.56)
**Quelle:** David
**Beschreibung:**
Moeglichkeit, zwei beliebige Widgets gleichzeitig in einer geteilten Ansicht zu sehen — entweder als echtes SplitWidget oder als zwei Docks, die je ~50% der Fensterbreite einnehmen.

**Anwendungsfaelle:**
- Singing Call: Lyrics (links) + Notizen (rechts)
- Pattern: Sequenzen (links) + Foto (rechts)
- Class-Abend: Teaching-Plan/Notizen (links) + Foto oder Sequenzen (rechts)

**Breitenaufteilung (flexibel, konfigurierbar):**
- Gesamtbreite: 90 % des Bildschirms (analog zum bestehenden 90%-Maximierungs-Code)
- Aufteilung konfigurierbar, typische Varianten: 50/50, 1/3 + 2/3, 2/3 + 1/3
- Die Aufteilung soll als Parameter der Regel-Aktion mitgegeben werden koennen (s.u.)

**Optionen zur Umsetzung (noch offen):**
1. **Split-Modus per Menue/Button**: Zwei Docks werden nebeneinander auf je ~50% gezogen (automatisch via `splitDockWidget`)
2. **Dediziertes SplitContainer-Dock**: Ein Dock mit eingebettetem QSplitter, in das man per Dropdown zwei beliebige Widget-Inhalte laden kann
3. **Layout-Preset**: Vordefiniertes Layout "Dual-Modus" in den gespeicherten Layouts (analog zu bestehenden Layout-Presets)

**Regel-Aktion (neu):**
- Neue Aktion z.B. `dual_view` mit Parametern: linkes Widget, rechtes Widget, Breitenverhaeltnis (z.B. `50:50`, `33:67`, `67:33`)
- Ermoeglicht das Oeffnen einer bestimmten Kombination per Tastaturkuerzel oder Trigger zur Laufzeit

**Aufwand:** Mittel

---

## Nutzerfeedback (David, 2026-04-19)

### BL-079: Notizen-Widget — Erste Notiz hervorgehoben (Checklisten-Modus)
**Status:** ERLEDIGT (v0.53)
**Quelle:** David
**Beschreibung:** Notizen eignen sich hervorragend als Checkliste für Classes oder Clubabende. Den Caller interessiert im Live-Betrieb primär die **nächste Aufgabe** — diese sollte daher aus der Ferne gut lesbar sein.
**Umsetzung:**
- Erste (oberste) Notiz der „Offen"-Liste deutlich grösser darstellen (z.B. 1,5–2× Schriftgrösse)
- Optional: Als Umschalt-Option (Toggle-Button oder Einstellung), damit die normale Ansicht erhalten bleiben kann für Nutzer, die den Effekt nicht wollen
- Persistenz des Toggle-Zustands in der INI (analog zu Zoom in BL-051)
- Darstellung beim Abhaken/Umsortieren konsistent halten (neue erste Notiz rutscht ins grosse Layout)
**Aufwand:** Klein

### BL-080: Rules-Aktion — Oberste Notiz als erledigt markieren
**Status:** ERLEDIGT (v0.53)
**Quelle:** David
**Beschreibung:** Ergänzend zu BL-079: Caller soll im Live-Betrieb die aktuelle (oberste) Aufgabe **per Tastendruck oder Mikro-Knopf** abhaken können. Die nächste Aufgabe rutscht dann automatisch nach oben (und wird durch BL-079 wieder gross dargestellt). Dadurch wird das Notizen-Widget zum freihändigen Checklisten-Tool.
**Umsetzung:**
- Neue Rules-Aktion `notes_tick_top` (oder ähnlich benannt): markiert die erste Notiz der „Offen"-Liste als erledigt
- Integration in die bestehende Rule-Engine — Trigger kann beliebige Taste sein (BL-064) oder MIDI/USB-Knopf-Event
- Kein Effekt, falls „Offen"-Liste leer — stumm ignorieren
- Optional: Akustisches/visuelles Feedback (kurzer Pling oder Blink), damit der Caller im Live-Betrieb mitbekommt, dass das Hakensetzen funktioniert hat
**Abhaengigkeit:** BL-064 (Rules-Trigger für beliebige Tasten), sinnvoll kombiniert mit BL-079
**Aufwand:** Klein

---

## Neue Anforderungen (David, 2026-04-22)

### BL-083: Tanzprogramm-Anzeige im Player mit konfigurierbaren Programm-Levels
**Status:** ERLEDIGT (v0.54)
**Quelle:** David
**Beschreibung:** Neue Anzeige im Player fuer das aktuell eingestellte Tanzprogramm-Level. Der Caller sieht auf einen Blick, fuer welches Programm er gerade callt, und kann es per Klick schnell wechseln.
**UI:**
- Neues Label/Button im Player (neben der Song-Dauer) zeigt das aktuelle Kuerzel: z.B. `MS`, `PL`, `A1`, `A2`, `C1`, `C2`, `C3A`
- Klick auf den Button oeffnet einen Auswahldialog mit allen konfigurierten Programmen als Schaltflaechen (analog zu einem Schnellauswahl-Grid)
- Optional: Kuerzel mit Class-Prefix (z.B. `Class MS`, `Class A1`) fuer Class-Abende — der Prefix ist konfigurierbar
**Datenhaltung:**
- Neue DB-Tabelle `dance_programs` (id, code TEXT, label TEXT, sort_order INT, has_class_variant BOOL)
- Default-Eintraege: MS, PL, A1, A2, C1, C2, C3A
- Verwaltungsdialog in den Einstellungen: Programme anlegen, umbenennen, sortieren, loeschen
- Pro Programm: gewuenschte Patternlaenge in Minuten (Standard: 7 Min.) — Grundlage fuer BL-053/BL-085
**Weiteres:**
- Das aktuell eingestellte Programm wird in der INI oder Session gespeichert (kein DB-Save noetig, da Sitzungswert)
- Grundlage fuer BL-084 (Lokation mit Tanzprogramm) und BL-085 (Planner nutzt Patternlaenge)
**Aufwand:** Mittel

---

### BL-084: Lokation mit Tanzprogramm-Zuweisung
**Status:** ERLEDIGT (v0.54)
**Quelle:** David
**Abhaengigkeit:** BL-083 (Tanzprogramm-Tabelle und Auswahldialog muessen vorher existieren)
**Beschreibung:** Jede Lokation erhaelt eine Zuweisung zu einem Tanzprogramm-Level. Beim Auswaehlen einer Lokation wird das hinterlegte Programm automatisch im Player eingestellt.
**Umsetzung:**
- Neues Feld `dance_program_id` (FK → dance_programs) in der Tabelle `locations`
- Im Lokations-Bearbeitungsdialog: Auswahl-Button mit den gleichen Programmkuerzeln wie in BL-083 (wiederverwendeter Dialog)
- Beim Laden einer Lokation: `dance_program_id` auslesen und den Player-Anzeiger (BL-083) entsprechend setzen
- Kein Pflichtfeld — Lokationen ohne Zuweisung behalten das zuletzt gesetzte Programm
**Aufwand:** Klein (aufbauend auf BL-083)

---

### BL-085: Planner — Gewuenschte Patternlaenge aus Tanzprogramm uebernehmen
**Status:** ERLEDIGT (v0.55)
**Quelle:** David
**Bezug:** Praezisiert und ergaenzt BL-053 (Pattern-Laenge pro Gruppe/Abend, ein User) — BL-053 bleibt als uebergeordnete Anforderung bestehen
**Abhaengigkeit:** BL-083 (Tanzprogramm mit Patternlaenge-Feld)
**Beschreibung:** Im Planner wird die gewuenschte Patternlaenge (Ziel-Minuten) aus dem aktuell eingestellten Tanzprogramm (BL-083) als Standardwert fuer die Loop-Anzahl-Berechnung verwendet.
**Umsetzung:**
- Planner liest `target_duration_min` aus `dance_programs` fuer das aktuelle Programm
- Dieser Wert wird als Ziel in die Loop-Anzahl-Formel eingesetzt (Basis: BL-042)
- Manuelle Ueberschreibung im Planner weiterhin moeglich (pro Song oder global)
- Wenn kein Tanzprogramm gesetzt: Fallback auf bisherigen Standardwert (7 Min.)
**Aufwand:** Klein (Datenbankabfrage + Planner-Berechnung anpassen)

---

### BL-086: Temporaeres Tempo pro Lokation
**Status:** ERLEDIGT (v0.54)
**Quelle:** David
**Beschreibung:** Pro Lokation kann ein temporaeres Tempo (Tempobremse) gespeichert werden. Beim Auswaehlen der Lokation wird dieser Wert automatisch in das Feld "Temporaeres Tempo" im Player uebernommen. Praktisch fuer langsame Gruppen (Classes, Anfaenger), bei denen der Caller immer eine bestimmte Tempobremse braucht.
**Umsetzung:**
- Neues Feld `temp_tempo` (REAL, nullable) in der Tabelle `locations`
- Im Lokations-Bearbeitungsdialog: Eingabefeld fuer temporaeres Tempo (z.B. SpinBox, Wertebereich wie im Player)
- Beim Laden einer Lokation: Wenn `temp_tempo` gesetzt → Player-Feld "Temporaeres Tempo" automatisch befuellen
- Kein Pflichtfeld — `NULL` bedeutet: temporaeres Tempo wird nicht veraendert
**Aufwand:** Klein

---

### BL-088: Song aus Songliste schnell zur Playlist hinzufuegen
**Status:** ERLEDIGT
**Quelle:** David
**Loesung:** Button „Zur Playlist" in der Songliste (unten rechts) sowie Kontextmenue-Eintrag per Rechtsklick. Der → -Pfeil-Key wurde nicht umgesetzt (war optionale Option C, kein Kernziel).

---

### BL-087: Mehrere Lyric-URLs pro Song mit Tanzprogramm-Filter
**Status:** ERLEDIGT (v0.83)
**Quelle:** David
**Hinweis:** Anforderung wird zunaechst in der Caller-Community diskutiert, bevor sie umgesetzt wird. Voraussichtlich besonders nuetzlich fuer Einsteiger-Caller, die programm-spezifische Lyric-Varianten benoetigen.
**Beschreibung:** Pro Song koennen mehrere Lyric-URLs oder Lyric-Dateien gespeichert werden, jeweils mit einem Tanzprogramm-Level als Filter. Je nach aktuell eingestelltem Tanzprogramm (BL-083) wird automatisch das passende Lyric angezeigt.
**Anwendungsfall:** Ein Singing Call existiert in einer MS-Version und einer A1-Version (unterschiedliche Lyric-Texte). Der Caller stellt das Programm ein — Callers Caddy laedt das passende Lyric.
**Umsetzung:**
- Neue DB-Tabelle `song_lyrics` (id, song_id FK, dance_program_id FK nullable, url TEXT, sort_order INT)
- Bestehende einzelne Lyric-URL in `songs` bleibt als Fallback (kein Breaking Change)
- Im Song-Datensatz: Liste der Lyric-Eintraege mit Programm-Zuweisung, editierbar
- Beim Lyrics-Laden: Suche nach Eintrag mit passendem `dance_program_id`; falls nicht vorhanden → Fallback auf Standard-URL
- Abhaengigkeit: BL-083 (Tanzprogramm-Auswahl im Player)
**Aufwand:** Mittel

---

### BL-089: SequenzView — Navigation zwischen gefilterten Sequenzen ohne Dialog zu verlassen
**Status:** ERLEDIGT (v0.57)
**Quelle:** David
**Beschreibung:** In der Sequenz-Detailansicht (wird beim Klick auf eine Sequenz in der Sequenzliste geoeffnet, zeigt die Sequenz isoliert und etwas groesser) werden zwei neue Navigations-Buttons eingefuehrt: **„<"** (vorherige Sequenz) und **„>"** (naechste Sequenz). Die Buttons erscheinen in einer eigenen Zeile oberhalb des bestehenden Close-Buttons. Die Navigation bezieht sich auf die aktuell gefilterte Sequenzliste — der Caller kann so zügig durch alle passenden Sequenzen blaettern, ohne den Dialog zu schliessen und neu zu oeffnen.
**Umsetzung:**
- Dialog erhaelt eine Referenz auf die gefilterte Sequenzliste und den aktuellen Index
- „<" / „>" laden die vorherige/naechste Sequenz aus der Liste direkt in die bestehende Ansicht (kein Dialog-Neustart)
- Am Anfang/Ende der Liste werden „<" / „>" entsprechend deaktiviert (disabled)
- Optional: Anzeige „3 / 12" (Position in der gefilterten Liste)
**Aufwand:** Klein

---

### BL-090: SequenzView — Frei vergroesserbares Fenster mit mitwachsender Schrift
**Status:** ERLEDIGT (v0.57)
**Quelle:** David
**Beschreibung:** Das Sequenz-Detailfenster (SequenzView) soll frei in der Groesse veraenderbar sein. Die Textdarstellung der Sequenz (Calls, Formatierung) soll dabei dynamisch mitwachsen — Schriftgroesse und ggf. Fettung passen sich an die verfuegbare Fensterflaeche an, sodass die Sequenz das gesamte Fenster fuellt. Ziel: Der Caller kann das Fenster waehrend des Callens gross aufziehen und die Sequenz auch aus einigen Metern Abstand noch lesen.
**Umsetzung:**
- Fenster als `QDialog` oder `QWidget` mit `setSizeGripEnabled(True)` / freier Resize-Moeglichkeit
- Bei `resizeEvent`: Schriftgroesse neu berechnen (verfuegbare Hoehe / Anzahl Zeilen, begrenzt nach oben)
- Alternativ: `QTextEdit` im ReadOnly-Modus mit automatischer Schriftgroessen-Anpassung ueber `fitInView`-Aehnliches Verfahren
- Bezug: Es gibt bereits Code fuer 90%-Maximierung — pruefen ob dieser wiederverwendet werden kann
**Abhaengigkeit:** BL-089 (Navigation in SequenzView)
**Aufwand:** Mittel

---

### BL-091: Regel-Aktionen fuer SequenzView (Fokus, Maximieren, Navigation)
**Status:** ERLEDIGT (v0.57)
**Quelle:** David
**Beschreibung:** Das Regel-/Trigger-System erhaelt neue Aktionen, die das SequenzView-Fenster steuern:
- **`sequenzview_focus`**: Bringt das SequenzView-Fenster in den Vordergrund (Fokus holen)
- **`sequenzview_maximize`**: Maximiert das SequenzView-Fenster auf 90 % des Bildschirms (Wiederverwendung des bestehenden 90%-Codes)
- **`sequenzview_prev`**: Blaettert zur vorherigen Sequenz in der gefilterten Liste (entspricht „<"-Button aus BL-089)
- **`sequenzview_next`**: Blaettert zur naechsten Sequenz in der gefilterten Liste (entspricht „>"-Button aus BL-089)
Diese Aktionen ermoeglichen es, den SequenzView per Tastaturkuerzel, Timer oder externem Trigger zu steuern — nuetzlich z.B. um waehrend des Callens haendsfrei durch Sequenzen zu navigieren.
**Abhaengigkeit:** BL-089, BL-090
**Aufwand:** Klein (sofern BL-089/090 umgesetzt sind)

---

### BL-093: Shortcodes in Notizen
**Status:** ERLEDIGT (v0.59)
**Quelle:** David
**Beschreibung:** Notizen koennen Shortcodes enthalten, die beim Abharken ausgefuehrt werden. Syntax: `[load_song "Titel"]`, `[sequence_view id=42 contains="Swing Thru" limit="MS"]`. Umkehrweg: Context-Menus in Songliste, Playlist und Sequenz-Uebersicht sowie ← Buttons im Notiz-Widget fuer schnelles Einfuegen.
**Umsetzung:**
- Neues Modul `shortcode_parser.py` mit `parse_shortcodes()` und `shortcode_text()`
- `notes_widget.py`: `on_shortcode_execute`-Callback, `add_note()`-API, ← Lied / ← Sequenz Buttons
- Context-Menus auf Songliste, Playlist, Sequenz-Tabelle ("Zu Notizen hinzufuegen")
- `P29MainWindow._shortcode_dispatch()` routet zu `_shortcode_load_song()` / `_shortcode_sequence_view()`
- `SequencesWidget.set_contains_filter()` und `set_limit_filter()` fuer programmatischen Filterzugriff
**Aufwand:** Mittel

---

## Nutzerfeedback (ein User, 2026-04-30)

### BL-094: Per-Song-Overrides fuer regelbasiertes Verhalten (Song Properties)
**Status:** ERLEDIGT (2026-05-11)
**Quelle:** ein User (Autoscroll-Anlass), David (Architektur-Entscheidung)
**Beschreibung:** Songs sollen einzelne Verhaltensweisen ueberschreiben koennen, die sonst global oder per Rule gesteuert werden. Erster konkreter Anwendungsfall: Autoscroll ist standardmaessig aktiv, aber ein bestimmter Song (z.B. GP-Song mit langen Producer-Credits am Ende) soll Autoscroll dauerhaft deaktiviert haben — ohne die globale Einstellung zu aendern.

**Architektur-Entscheidung: Option A — Generische Song-Properties-Tabelle**
Neue DB-Tabelle `song_properties (song_id FK, key TEXT, value TEXT, PRIMARY KEY (song_id, key))`. Kein Eingriff in die bestehende `songs`-Tabelle — externe Erweiterung, kein Schema-Umbau.

Beispiel-Eintraege:
- `(42, "autoscroll", "off")` → Autoscroll fuer Song 42 deaktiviert
- `(42, "key", "value")` → beliebig erweiterbar fuer kuenftige Features

**Ablauf im Code:**
- Beim Laden eines Songs: `song_properties` fuer die `song_id` laden und cachen
- Jeder Feature-Code (Autoscroll, kuenftig weitere) prueft zuerst ob eine Song-Property vorliegt; falls ja: Override, sonst: Standardverhalten / Rule-Ergebnis
- Im Song-Datensatz-Dialog: neuer Bereich „Erweiterte Einstellungen" mit den gesetzten Properties (editierbar)

**Vorteil:** Kein Schema-Change fuer jeden neuen Anwendungsfall. Bestehende Strukturen bleiben unangetastet.
**Aufwand:** Mittel (DB-Tabelle + Lade-/Cache-Mechanismus + erster Anwendungsfall Autoscroll + UI im Song-Datensatz)

**⚠️ Abhaengigkeit BL-109 (Lyrics-Abschnitts-Springen):** BL-109 benoetigt pro Song konfigurierbare Daten: Intro-Laenge und Keyword-Overrides fuer Abschnittsnamen (weil jeder Caller seine Lyrics anders aufbaut). Das sind klassische Song-Properties. BL-094 muss implementiert sein — oder zumindest sein Datenbankschema beschlossen sein — bevor BL-109 angegangen wird, damit BL-109 dieselbe Infrastruktur nutzen kann und keine eigene Parallel-Loesung entsteht. **Beide Tickets vor Umsetzung gemeinsam planen.**

### BL-095: Auto-BPM — Regel "kein BPM → automatisch ermitteln" + Batch-Analyse + Import-Option
**Status:** ERLEDIGT (v0.69)
**Quelle:** ein User (2026-04-30, ergaenzt 2026-05-01)
**Beschreibung:** Mehrere verwandte Erweiterungen zur BPM-Automatisierung:
1. **Regel-Aktion** (autochange-Trigger): "Wenn kein BPM gesetzt → automatisch ermitteln, sonst nichts tun" — analog zur bestehenden Auto-Loop-Logik. Dadurch verbessert sich die Songdaten-Qualitaet automatisch im Live-Betrieb.
2. **Batch-Analyse aller bestehenden Songs**: Stundenlanger Hintergrundlauf ueber ALLE Songs ohne BPM-Wert (nicht nur neue Imports). Start manuell per Button, Fortschrittsanzeige, abbrechbar. ein User hat 2000+ Songs ohne BPM — Einzelklick pro Song ist unrealistisch.
3. **Import-Option**: Beim Import einzelner Songs Wahl anbieten: Auto-BPM durchfuehren? Auto-Loop durchfuehren? (Checkboxen im Import-Dialog). Laeuft im Hintergrund, blockiert den Import nicht.
**Bezug:** Voraussetzung: TIC-0016 (Bug: Auto-BPM-Klick funktioniert nicht) muss erst geloest sein
**Aufwand:** Mittel

### BL-096: Statistik — Vorschlagsbutton, letztes Spieldatum, Lokationsfilter-Uebernahme
**Status:** ERLEDIGT (v0.85)
**Quelle:** ein User (ergaenzt 2026-05-03)
**Beschreibung:** Erweiterungen fuer das Statistik-Dock: Vorschlagsbutton, Spieldatum, Lokationsfilter-Vorauswahl, Playlist-Transfer.
**Loesung:** Alle genannten Punkte sind ueber bestehende Features abgedeckt (Statistik-Dock mit Lokationsfilter, Rechtsklick-Kontextmenue fuer Playlist-Transfer via BL-102).
**Bezug:** Erweitert BL-019 (Statistikfunktionen, v0.65), BL-102 (Song per Rechtsklick in Playlist)
**Aufwand:** Mittel

### BL-097: Planner — Gespeicherte Playliste in linken Bereich laden
**Status:** ERLEDIGT (v0.75)
**Quelle:** ein User
**Beschreibung:** Im Planner soll der linke Bereich (Song-Auswahl) eine gespeicherte Playliste laden koennen. Anwendungsfall: ein User erstellt eine Vorselektion von 50 Songs fuer eine Veranstaltung ("Special 123"), speichert sie als Playliste, und laedt sie im Planner links. Rechts wird dann die aktive Session-Selektion ("Special_123_OK") geladen. So hat er Planung und aktive Auswahl nebeneinander ohne doppelten Aufwand.
**Loesung:** "Custom"-Button in der Filter-Zeile oeffnet Dialog mit 4 festen Slots. Jeder Slot kann eine Playlist-TXT laden (gleiches Format wie normaler Playlist-Load). Nach Uebernehmen erscheint extra Zeile mit Checkboxen — Song-Pool zeigt nur Schnittmenge der aktivierten Playlisten. Filter ist session-only.
**Aufwand:** Mittel

### BL-098: Sequenzen — Freitext-Import mit Trenner, Level und Kategorie (inkl. Ceder.net)
**Status:** ERLEDIGT (v0.95, 2026-06-01)
**Loesung:**
- Freitext-Parser unterstuetzt 3 Standard-Formate (Komma in einer Zeile / Calls untereinander mit Leerzeile als Trenner / dito mit `,;`-Endung) plus Ceder-Web-Header (`ID=<num>`) als Trenner.
- Universeller Sequenz-Import-Dialog (`SequenceImportDialog`) deckt MDB/JSON/CSDS/Freitext ueber eine Oberflaeche ab. Auto-Detection per Endung + Inhalts-Sniff, manueller Format-Override moeglich.
- Vorschau zeigt die ersten 3 Sequenzen mit aufgeloeste Typ/Schwierigkeit.
- Quellen-Schalter pro Meta-Feld: Bulk (Wert aus Dialog) oder "Aus Datei" (nur aktiv wenn das Format pro Sequenz Werte liefert — JSON/CSDS). Fallback auf Bulk wenn Datei kein Wert hat.
- Duplikat-Erkennung (Default AN) ueber 15-Felder-Tupel-Set, blockt sowohl DB-Dubletten als auch In-File-Dubletten.
- Menue: Sequenzen → "Sequenzen importieren..." (alte Einzeleintraege bleiben vorerst stehen).
- Frei konfigurierbares Custom-Trennzeichen noch offen (Ceder.net und Standard-Formate werden bereits erkannt).
**Quelle:** ein User (ergaenzt 2026-05-03)
**Beschreibung:** Import von Sequenzen/Getouts/Gimmicks/Ideen aus beliebigen Textdateien. Der Nutzer definiert ein Trennzeichen, und alles zwischen zwei Trennern wird als ein Datensatz importiert.

**Kernidee (ein User, 2026-05-03):** "Ich moechte eine Textdatei einfach in die Datenbank als Datensaetze importieren."
- Trennzeichen frei konfigurierbar: z.B. `---`, `-`, ein bestimmtes Wort oder eine Leerzeile
- Import-Dialog: Nutzer waehlt Textdatei, gibt Trennzeichen an, waehlt Level (MS / Plus / A1 / A2 / leer) und Kategorie (Freitext, z.B. "A2 – Singing", "Zero Box Getout", "MS Workshop-Ideen", "SD-Witze")
- Vorschau: zeigt wie viele Datensaetze gefunden wurden und die ersten 3 zur Kontrolle
- Jeder Abschnitt zwischen Trennern wird als ein Sequenz-Datensatz in der DB gespeichert
- Kategorien sind voellig frei — nicht nur Getouts, auch: Gimmicks, Witze, Workshop-Ideen, Sprueche

**Beispiel-Anwendungsfall Ceder.net:**
- Nutzer kopiert A2-Singings von ceder.net (https://www.ceder.net/choreodb/) in eine Textdatei
- Trennzeichen: das Wort "Mainstream" (trennt Abschnitte im Ceder-Export)
- Kategorie: "A2 – Singing", Level: A2
- Ergebnis: jeder Abschnitt wird als eigene Sequenz in CC importiert

**Beispiel-Anwendungsfall Gimmicks (ein User, 2026-05-03):**
- Nutzer traegt in einem Texteditor Ideen zusammen:
  `Ideen zu Walk & Dodge, 6 by 2, ... (Trenner) Ideen zu Swing Thru, ... (Trenner) Ideen zu Zoom, ...`
- Kategorie: "MS Workshop-Ideen", Level: MS
- Ergebnis: 3 Datensaetze mit je einem Themenblock

**Weitere freie Kategorien denkbar:** SD-Witze, lustige Sprueche, Plus Zero Box Getouts, Zero Line Getouts — jede beliebige Sammlung die der Caller fuer den Live-Einsatz braucht.

**Urspruengliche Anforderung (unveraendert):**
- Navigation durch Sequenzen per Knopfdruck, aktuelle als "gemacht" markieren
- Vorwaerts/Rueckwaerts per Tastatur zum Auswaehlen von Get-Outs / Workshop-Themen
- Filterung nach Level: nur Sequenzen anzeigen, die zum aktuell eingestellten Tanzprogramm passen

**Bezug:** Erweitert BL-015 (Sequenz-Editor), BL-016 (Sequenz-Bewertung)
**Aufwand:** Gross

---

### BL-104: Virtueller Musik-/Lyrik-Pfad — zentrale Multi-Pfad-Auflösung
**Status:** ERLEDIGT (v0.69)
**Quelle:** David (2026-05-02) — Meldungen, dass einzelne Funktionen alternative Musikpfade nicht finden
**Prioritaet:** Hoch — TIC-0023 bestätigt, dass der Fehler beim Endnutzer auftritt
**Beschreibung:** Derzeit sucht jede Funktion, die eine Song-Datei oder Lyrik-Datei benötigt, selbst in den konfigurierten Alternativpfaden (Musikordner 1–4, Lyrik-Ordner). Das führt dazu, dass manche Funktionen einzelne Pfade übersehen.

**Ziel:** Eine einzige zentrale Auflösungsstelle, die einen "virtuellen Dateipfad" liefert. Alle anderen Stellen im Code fragen nur noch dort an — niemand sucht selbst.

**Architektur-Idee:**
- `resolve_song_file(filename) -> str | None` — durchsucht alle konfigurierten Musikordner, gibt den ersten gefundenen absoluten Pfad zurück
- `resolve_lyric_file(filename) -> str | None` — analog für Lyrik-Ordner
- Beide Funktionen zentral (z.B. in einem `path_resolver.py` oder als Methoden auf einem bestehenden Manager)
- Alle Aufrufer ersetzen ihre eigene Pfad-Suche durch einen einzigen Aufruf dieser Funktion
- Konfiguration (welche Ordner in welcher Reihenfolge) bleibt an einer Stelle (INI/Settings)

**Betroffene Stellen (zu identifizieren bei Umsetzung):**
- Song laden (Player)
- Loop-Finder
- Lyrics-Dock
- Planner / Loop-Count-Dialog
- Statistik / Reports
- Jede weitere Stelle die `find_song_file()` oder ähnliches selbst implementiert

**Aufwand:** Mittel (Suche nach allen betroffenen Stellen + Refactoring)

---

### BL-103: Crash-Handler — automatisches Logfile bei Absturz
**Status:** ERLEDIGT (erweitert 2026-05-07)
**Quelle:** ein User (2026-05-01) — 3 ungeklaerte Abstuerze (TIC-0022)
**Prioritaet:** Hoch — ohne Logs sind Abstuerze nicht analysierbar
**Beschreibung:** Einen globalen Crash-Handler etablieren, der bei einem unerwarteten Absturz automatisch ein Logfile schreibt, bevor die App beendet wird.

**Inhalt des Logfiles:**
- Zeitstempel des Absturzes (ISO-Format)
- Exception-Typ, Meldung und vollstaendiger Stacktrace (`traceback.format_exc()`)
- Letzte N Benutzeraktionen / Events (Ring-Buffer, z.B. 20 Eintraege) — "Was passierte kurz vorher?"
- Aktive Lokation, aktuell geladener Song, aktiver Dock/Tab

**Technische Umsetzung (Python/PySide6):**
- `sys.excepthook` ueberschreiben → faengt alle unbehandelten Exceptions ab
- `qInstallMessageHandler` → faengt Qt-eigene Critical/Fatal-Meldungen ab, schreibt sofort Logfile (2026-05-07 umgesetzt)
- Logfile-Pfad: `app_dir/crash_YYYYMMDD_HHMMSS.log` (je Absturz eine eigene Datei)
- Ring-Buffer fuer Benutzeraktionen: zentrales Logging-Modul, das wichtige Events eintraegt (Song laden, Regel feuern, Dock-Wechsel etc.)
- Beim naechsten App-Start: wenn Crash-Logs vorhanden → Hinweis anzeigen mit Option "Log anzeigen / an Entwickler senden"

**Aufwand:** Mittel

---

### BL-102: Statistik-Dock — Song per Rechtsklick in Notizen oder Playlist übernehmen
**Status:** ERLEDIGT (v0.67)
**Quelle:** ein User (2026-05-01)
**Bezug:** BL-019 (Statistikfunktionen), BL-093 (Shortcodes in Notizen), BL-088 (Song schnell zur Playlist)
**Beschreibung:** In den Statistik-Listen (TOP / FLOP / Nie gespielt) soll ein Song per Rechtsklick-Kontextmenü oder Button direkt weiterverwendet werden können:
- **"Zur Playlist hinzufügen"** → Song landet in der aktuellen Playlist (analog BL-088)
- **"Zu Notizen hinzufügen"** → fügt einen `[load_song "Titel"]`-Shortcode als neue Notiz ein (analog BL-093)
Das Kontextmenü ist die primäre Interaktion; ein Button als ergänzende Option.
**Aufwand:** Klein

---

### BL-101: Songliste — Filter Singing / Pattern
**Status:** ERLEDIGT (v0.85)
**Quelle:** ein User (2026-05-01)
**Beschreibung:** In der Songliste einen Typ-Filter analog zum Planner einbauen: Alle / Pattern / Singing. Damit kann der Caller die Songliste schnell auf einen Typ einschraenken, ohne in der Suche einen Begriff eintippen zu muessen.
**Aufwand:** Klein

---

### BL-100: Loop-End automatisch aus Ziel-Patternlänge berechnen
**Status:** ENTFAELLT
**Quelle:** ein User (2026-05-01)
**Bezug:** BL-099 (Planner mit Tanzprogramm), BL-085 (Patternlänge aus Tanzprogramm), BL-046 (Loop-Finder-Presets)
**Beschreibung:** Beim Laden eines Pattern-Songs (aus dem Planner oder Player) soll der Loop-Endpunkt automatisch so berechnet werden, dass die gewuenschte Patternlaenge (aus dem Tanzprogramm-Standard) moeglichst exakt erreicht wird — ohne manuellen Eingriff.

**Algorithmus (2 Schritte):**

Gegeben:
- `T` = Ziel-Patternlaenge (z.B. 600 Sek = 10 min), aus Tanzprogramm-Standard
- `L_in` = Loop-Start (bereits am Song gesetzt)
- `S` = Songlaenge
- `tail` = Restlaufzeit-Annahme (konfigurierbar, Standard: 20 Sek) — Zeit von Loop_End bis Songschluss

Schritt 1 — Anzahl Loops schaetzen (Naeherung mit x ≈ S - L_in):
```
N = ceil((T - L_in) / (S - L_in))
```

Schritt 2 — idealen Loop_End berechnen:
```
x = (T - L_in - tail) / N
Loop_End = L_in + x
```

Probe: `L_in + N*x + tail = L_in + (T - L_in - tail) + tail = T` ✓

**Dann:** Loop-Finder sucht im Bereich um den berechneten Loop_End-Wert nach einem musikalisch guten Schnittplatz (BL-046 Presets). Abweichung von der Ziel-Patternlaenge: wenige Sekunden.

**Sonderfall:** Kein Loop_Start gesetzt → Berechnung nicht moeglich, Fallback auf Standard-Loops oder manuelle Eingabe.
**Sonderfall:** Kein Level / keine Ziel-Patternlaenge → kein automatischer Eingriff.

**Konfigurierbar:** `tail`-Annahme (Standard 20 Sek) in den Einstellungen oder pro Song ueberschreibbar.

**UX — Loopanzahl automatisch setzen:** Die berechnete Loopanzahl N wird direkt im Player gesetzt, ohne Auswahldialog. Kein manuelles Auswaehlen zwischen N und N+1. Der Caller kann den Wert danach bei Bedarf manuell anpassen. Ziel: Null Klicks im Normalfall.

**Aufwand:** Mittel
**Entfaellt-Begruendung:** Der Ansatz macht in der Praxis keinen Sinn — die Ziel-Patternlaenge ergibt sich aus Loop-Anzahl × Loop-Dauer, nicht umgekehrt. Der Loop-End-Punkt wird manuell via Beat Snap gesetzt; eine automatische Berechnung wuerde den musikalischen Schnittpunkt ignorieren.

---

### BL-105: Playlist — Songs in Unterordnern nicht auffindbar
**Status:** ERLEDIGT (v0.85)
**Quelle:** ein User (2026-05-03)
**Prioritaet:** Hoch — tritt im Live-Betrieb auf, Song laesst sich nicht spielen
**Beschreibung:** Songs, deren Datei sich in einem Unterordner des Musikverzeichnisses befindet (z.B. `music/Singing Calls/songtitel.mp3`), werden in der Playlist nicht korrekt gefunden und koennen nicht abgespielt werden. In der normalen Songliste funktioniert es (vermutlich weil dort der vollstaendige relative Pfad inkl. Unterordner gespeichert ist).

**Unterschied zu BL-104:** BL-104 betrifft mehrere konfigurierte Musik-Slots (Ordner 1–4). Dieses Ticket betrifft Unterordner *innerhalb* eines einzelnen Musikordners — also wenn `filename` in der DB z.B. `Unterordner/song.mp3` statt nur `song.mp3` lautet.

**Analyse (2026-05-07):**
- Sowohl Songliste als auch Playlist nutzen `find_song_file()` — kein Unterschied im Codepfad.
- Import speichert immer nur `os.path.basename(filepath)` als `filename` in der DB.
- Bei "Am Ort belassen"-Import: Die Slot-Add-Logik (main.py ~9138) bietet den Quellordner als neuen Musik-Slot an. Damit findet `find_song_file("song.mp3")` die Datei ueber diesen Slot. **Dieser Fall funktioniert.**
- Getestetes Szenario (Import aus Unterordner + Songliste + Playlist): **funktioniert korrekt.**
- Der genaue Fehler-Trigger bei einem User ist noch unklar. Wahrscheinlichste Kandidaten:
  1. Datei wurde **nach dem Import manuell** in einen Unterordner verschoben — DB hat `song.mp3`, Datei liegt in `music/Singing Calls/song.mp3`, kein Slot fuer den Unterordner.
  2. **Migration aus CC1** — alter CC hatte Songs in Unterordnern, Migrationscode uebernimmt Pfad nicht korrekt.
  3. Unterordner liegt **innerhalb eines bereits registrierten Slots** — `has_path_in_music_dirs` findet den uebergeordneten Ordner, kein neuer Slot wird angeboten, Basename reicht nicht.

**Naechster Schritt:** einen User fragen, wie die Songs in den Unterordner gekommen sind (Import, Migration oder manuell verschoben).

**Erwartetes Verhalten:** Songs in Unterordnern sollen genauso spielbar sein wie Songs im Root des Musikordners.

**Aufwand:** Klein bis Mittel (abhaengig von Fehler-Ursache)

---

### BL-106: Planner — Suchfunktion wie in der Songliste
**Status:** ERLEDIGT (v0.46)
**Quelle:** ein User (2026-05-03)
**Beschreibung:** Im Planner-Fenster fehlt eine Suchfunktion fuer die Song-Auswahl-Liste (linker Bereich). ein User moechte dort Songs nach Titel oder Interpret suchen koennen — identisch zur Suchfunktion in der normalen Songliste bzw. Playlist.

**Anwendungsfall:** Bei 2000+ Songs ist scrollen durch die vollstaendige Liste im Planner unpraktisch. Eine Suchzeile (live-filternd, wie in der Songliste) wuerde erlauben, gezielt nach einem Song zu suchen und ihn per Klick in die Planner-Selektion zu uebernehmen.

**Umsetzung-Idee:** Suchzeile analog zur bestehenden Implementierung in der Songliste — Eingabe filtert die Liste sofort (kein Bestaetigungs-Button noetig). Platzierung: oberhalb der Song-Liste im linken Planner-Bereich.

**Aufwand:** Klein

---

### BL-110: Potential — Prüfung auf fehlende Qualitätsbewertung
**Status:** ERLEDIGT
**Quelle:** David (2026-05-07)
**Beschreibung:** Das Potential-Widget soll eine weitere Datenqualitäts-Prüfung erhalten: Songs ohne Qualitätsbewertung (Feld `quality = 0`). Diese Songs erscheinen im Planner bei Sortierung nach Qualität ganz unten und werden damit faktisch nie vorgeschlagen. Die Prüfung soll — analog zu den bestehenden Checks — die betroffenen Songs auflisten und eine Batch-Bereinigung ermöglichen (z.B. direkt in den Song-Datensatz springen).
**Aufwand:** Klein (neuer Check analog zu bestehenden Potential-Prüfungen)

---

### BL-111: Song-Datensatz — Feld ERR (Emotional Response Rate)
**Status:** ERLEDIGT (v0.46)
**Quelle:** David (2026-05-07)
**Bezug:** BL-073 (Abendplanung — kompletter Tanzabend als Vorschlag)
**Beschreibung:** Neues Feld `err` (Emotional Response Rate) in der Songs-Tabelle. Gibt die emotionale Wirkung eines Songs auf die Tänzer an. Wird später als Planungsparameter für BL-073 (perfekter Clubabend) und BL-112 (Auto-Fill) benötigt, um die emotionale Kurve eines Abends zu steuern.

**Wertebereich:** 4 feste Stufen (0 = nicht bewertet):
- **1 — Höhepunkt**: Song reißt mit, maximale Energie
- **2 — Vorbereitung**: Song baut Spannung auf
- **3 — Baseline**: Normaler Abend-Song, neutrale Energie
- **4 — Beruhigung**: Song nimmt Tempo raus, beruhigt

**Umsetzung:** Neues INTEGER-Feld `err` (Default 0 = nicht bewertet) in der DB-Migration + Anzeige/Eingabe im Song-Datensatz als Dropdown oder Radiobuttons mit den vier Bezeichnungen.
**Aufwand:** Klein

---

### BL-112: Planner — Auto-Fill Button
**Status:** ERLEDIGT (v0.46)
**Quelle:** David (2026-05-07)
**Bezug:** BL-073 (Abendplanung als Grossprojekt), BL-111 (ERR-Feld)
**Beschreibung:** Kleinerer Zwischenschritt zu BL-073: Ein Button "Auto-Fill" im Planner füllt die Playlist automatisch anhand weniger Parameter. Der Algo nutzt den bereits eingestellten Filter und die Sortierung des Song-Pools (typischerweise "Empfehlung") und nimmt immer die jeweils obersten verfügbaren Songs.

**Parameter-Dialog:**
1. **Anzahl Tipps** (= Tanzrunden, Zahl)
2. **Strategie** (Auswahl):
   - Strategie 1 — Pattern + Singing abwechselnd
   - Strategie 2 — Singings nur am Anfang und Ende
   - Strategie 3 — Nur Pattern
   - Strategie 4 — Nur Singing

**Algorithmus (N = Anzahl Tipps):**
- **Strategie 1:** Je Tipp: oberster Pattern + oberster Singing → 2×N Songs gesamt.
- **Strategie 2:** Tipp 1: oberster Pattern + oberster Singing. Tipps 2 bis N−1: je oberster Pattern. Tipp N: oberster Pattern + oberster Singing → N+2 Songs gesamt.
- **Strategie 3:** Die N obersten Pattern aus dem Pool → N Songs.
- **Strategie 4:** Die N obersten Singings aus dem Pool → N Songs.

"Oberster" bedeutet: erster noch nicht in der Playlist enthaltener Song aus dem gefilterten/sortierten Pool.
**Aufwand:** Mittel

---

### BL-092: SequenzView als echtes QDockWidget (kein Dialog)
**Status:** ERLEDIGT (v0.58)
**Quelle:** David
**Beschreibung:** Die Sequenz-Detail-Ansicht soll kein temporaerer Popup-Dialog mehr sein, sondern ein vollwertiges `QDockWidget` (`dock_sequenz_view`), das wie alle anderen Docks behandelt wird: dockbar, tabbbar, per `dual_view` nutzbar, per `dock_fullsize` maximierbar, Layout-Save/Restore-faehig. Klick auf eine Zeile in der Sequenzuebersicht aktualisiert das Dock und bringt es in den Vordergrund. Die Regel-Aktionen `sequenzview_*` steuern nun das Dock direkt.
**Umsetzung:**
- `SequenzViewWidget(QWidget)` erstellt als saubere Klasse mit `set_sequence(db, seq_ids, idx)` + Navigation
- `dock_sequenz_view` angelegt als `QDockWidget`, getabbt mit `dock_sequences`
- `_dock_map()` um `"sequenz_view"` erweitert (sofort in allen dock-Aktionen nutzbar)
- `SequencesWidget.on_open_detail`-Callback verbindet Tabellenklick mit dem Dock
- `_SequenzDetailDialog`, `open_detail_nonmodal`, `_active_detail_dlg` entfernt
**Aufwand:** Mittel

---

### BL-113: Planner / Evening Planner — Zufallsreihenfolge bei gleichen Scores
**Status:** ERLEDIGT (v0.85)
**Quelle:** David (2026-05-08)
**Bezug:** BL-112 (Auto-Fill), BL-073 (Evening Planner)

**Problem:** Wenn mehrere Songs denselben Empfehlungs-Score haben (z.B. alle ohne Play-Daten starten mit Score 0), werden sie immer in identischer Reihenfolge angezeigt (DB-Reihenfolge oder alphabetisch). Das führt dazu, dass beim ersten Starten ohne Play-Daten immer dieselben Songs empfohlen werden, und in der Statistik taucht der erste Song einer Gleichstands-Gruppe künstlich als „stärkstes" Lied auf.

**Gewünschtes Verhalten:**
- Innerhalb einer Score-Gruppe (gleiches Ranking) werden Songs in zufälliger Reihenfolge aufgelistet.
- Gilt für: Empfehlungsspalte im Planner-Pool, Auto-Fill (BL-112), später Evening Planner (BL-073).
- Die Zufälligkeit soll pro Session-Start neu gewürfelt werden (kein persistenter Seed), damit jeder Start variiert.

**Umsetzung (Vorschlag):**
- Beim Sortieren nach Score: Gruppen gleicher Score-Werte intern mit `random.shuffle()` permutieren.
- Alternativ: Tiebreaker-Spalte `random_order REAL` pro Session berechnen (`UPDATE ... SET random_order = random()`), dann sekundär nach `random_order` sortieren.
- Einfachste Variante: im Python-Sortierschritt `key=(score, random.random())` — funktioniert, solange die Liste nicht mehrfach neu sortiert wird.
**Aufwand:** Klein

---

### BL-115: Potential — Prüfung auf fehlenden ERR-Wert
**Status:** ERLEDIGT (v0.73)
**Quelle:** David (2026-05-09)
**Beschreibung:** Neuer Check im Potential-Widget: Songs bei denen `err = 0` (Default, nicht gesetzt). Doppelklick navigiert direkt zum Song.

---

### BL-116: Potential — Prüfung auf fehlendes Genre
**Status:** ERLEDIGT (v0.73)
**Quelle:** David (2026-05-09)
**Beschreibung:** Neuer Check im Potential-Widget: Songs ohne Genre-Zuweisung (kein Eintrag in `song_genres`). Doppelklick navigiert direkt zum Song.

---

### BL-117: Potential — Prüfung auf inkompatibles Dateiformat
**Status:** ERLEDIGT (v0.73)
**Quelle:** Claus Warnecke / David (2026-05-10)
**Beschreibung:** Neuer Check im Potential-Widget: Testet ob Audiodateien vom internen Decoder (soundfile/libsndfile) gelesen werden können. Erkennt MP3s mit nicht-standardkonformen Frames (ffmpeg-only). Läuft mit Zeitschätzung: 5 Sample-Dateien werden gemessen, Gesamtzeit hochgerechnet, User bestätigt vor dem vollständigen Check. QThread-basiert, abbrechbar. Doppelklick navigiert zum Song; Ignorieren-Funktion vorhanden.

---

### BL-114: Song-Datenpflege — KI-gestützter JSON-Import/Export für fehlende Metadaten
**Status:** ERLEDIGT (v0.73 Grundfunktion, v0.83 erweitert um Quality + ERR)
**Quelle:** David (2026-05-08)
**Bezug:** BL-110 (Potential-Widget), Music-for-Callers-Scrape

**Problem:** Viele Songs haben unvollständige Metadaten (Genre, Erscheinungsjahr, Original Artist u.a.). Manuelles Nachpflegen ist aufwändig; Batch-Bereinigung via KI wäre effizienter.

**Gewünschtes Verhalten (3-Schritt-Workflow):**

1. **Export:** Ein Menüpunkt oder Button (z.B. im Potential-Widget oder Extras-Menü) exportiert alle Songs mit mindestens einem fehlenden Feld als JSON-Datei. Felder sind konfigurierbar, typisch: `genre`, `year`, `original_artist`. Nur die fehlenden Felder werden mitexportiert (kein vollständiger Dump), damit das KI-Prompt klein bleibt. Format-Beispiel:
   ```json
   [
     {"id": 42, "title": "Rock Bottom", "filename": "rock_bottom.mp3", "missing": ["genre", "year"]},
     {"id": 71, "title": "La Bamba", "filename": "la_bamba.mp3", "missing": ["original_artist"]}
   ]
   ```

2. **KI-Anreicherung (außerhalb der App):** Der User übergibt die JSON-Datei einem KI-Prompt (z.B. Claude, ChatGPT). Der Prompt sucht die fehlenden Felder im Netz / aus Trainingsdaten und gibt ein angereichertes JSON zurück, in dem nur die vorher leeren Felder befüllt sind. Vorhandene Werte werden nicht überschrieben.

3. **Import:** Ein Import-Dialog liest das angereicherte JSON ein und trägt **nur die Felder ein, die vorher leer waren** (leere DB-Felder werden befüllt, bestehende Werte bleiben unberührt). Vor dem Eintragen: Preview-Tabelle zeigen (Song | Feld | Neuer Wert | Checkbox). Nutzer kann einzelne Einträge abwählen.

**Erweiterbarkeit:**
- Gleiches System nutzbar für Abgleich mit Music-for-Callers-Scrape-Daten (statt KI: Scrape-JSON als Quelle).
- Felder-Liste erweiterbar (z.B. `bpm`, `quality`, `err`), aber mit Vorsicht (Zahlenfelder brauchen Validierung).

**Umsetzung:**
- Export: SQL-Query mit `WHERE genre IS NULL OR genre = '' OR year = 0 OR ...`, Ausgabe via `json.dump`.
- Import: JSON einlesen, Song per `id` aus DB holen, nur leere Felder überschreiben, Transaktion.
- UI: Export-Button im Potential-Widget (neuer Check „Fehlende Metadaten") + separater Import-Dialog.
- KI-Prompt-Template als Textdatei mitliefern (z.B. `tools/enrich_metadata_prompt.txt`).
**Aufwand:** Mittel

---

### BL-119: Song-Bewertung — Feedback-Mechanismus nach dem Abspielen
**Status:** ERLEDIGT (v0.82 Grundfunktion, v0.83 Notizfeld ergänzt)
**Quelle:** Eigene Idee (2026-05-14)
**Beschreibung:** Optionaler modaler Dialog nach jedem Songende (natürliches Ende + Fadeout + manueller Stop). Aktivierbar per INI-Setting `feedback/enabled = true` (Standard: false).

**Umsetzung:**
- `FeedbackDialog`: Quality-Buttons 0–10 (links=schlechteste), ERR-Buttons 0/4/3/2/1 (links=schwächste Reaktion, rechts=stärkster Höhepunkt)
- Aktuell eingestellter Wert ist per `setCheckable` hervorgehoben
- Esc / Abbrechen schließt ohne Speichern
- "Übernehmen" speichert nur geänderte Felder via `update_song_simple_field`
- Widget-Update (spin_quality, combo_err) mit `blockSignals` — kein doppeltes Speichern
- Auto-Advance blockiert sich automatisch (modaler Dialog = Main-Thread blockiert)
- Zentraler Abfangpunkt: `_trigger_song_stopped()` ersetzt beide `fire_trigger("song_stopped")`-Aufrufe
- Bezug: BL-110 (Potential Quality), BL-111 (ERR), BL-115 (Potential ERR)
**Aufwand:** Mittel

---

### BL-120: Song-Daten — Export/Import auf alle Felder ausweiten
**Status:** ERLEDIGT (v0.83) — Quality, ERR, Genre, Original Artist, Erscheinungsjahr alle exportierbar/importierbar. Import-Modi (nur leere / alle / Konflikte) als mögliche Erweiterung offen gelassen.
**Quelle:** Eigene Idee (2026-05-14)
**Beschreibung:** Der bisherige JSON-Export/Import (BL-114) ist auf Original-Artist und Erscheinungsjahr beschränkt. Es soll auf alle relevanten Metadatenfelder ausgeweitet werden: Quality, ERR, Genre, sowie alle weiteren befüllbaren Felder.

**Export:**
- Vor dem Export werden die zu exportierenden Felder per Checkbox ausgewählt (z. B. Quality, ERR, Genre, Original Artist, Erscheinungsjahr)
- Nur nicht-leere Werte werden exportiert (kein Überschreiben mit Leerfeldern beim Reimport)

**Import:**
- Drei Modi auswählbar:
  1. **Nur leere Felder füllen** — vorhandene Daten bleiben unverändert, nur fehlende werden ergänzt
  2. **Alle Daten übernehmen** — gelieferte Felder werden ohne Rückfrage überschrieben
  3. **Konflikte einzeln bestätigen** — bei jedem Datensatz, bei dem sich ein Feld unterscheidet, wird der Konflikt angezeigt (alt vs. neu) und der Nutzer entscheidet per Klick
- Bezug: BL-114 (KI-gestützter JSON-Import/Export)
**Aufwand:** Mittel bis groß

---

### BL-121: Songliste und Planner — gemeinsamer Filter-/Sortier-Header
**Status:** ERLEDIGT (v0.85)
**Quelle:** David (2026-05-15)
**Beschreibung:** Die Songliste soll denselben Filter- und Sortierbereich im Kopf bekommen wie der Planner. Aktuell hat die Songliste nur ein einfaches Suchfeld; der Planner hat zusätzlich Dropdowns für Filter (z.B. Typ, Programm-Level, Qualität) und Sortierung.

**Ziel:** Beide Widgets nutzen denselben wiederverwendbaren Header-Bereich. Der Inhalt und das Aussehen des Kopfbereichs werden an einer zentralen Stelle definiert — kein doppelter Code.

**Umsetzungsidee:**
- Neues Widget `SongFilterBar` (oder ähnlich) als eigenständige Komponente, das alle Filter- und Sortier-Elemente enthält
- `SongFilterBar` wird sowohl in `SongListWidget` als auch in `PlannerWidget` (und ggf. weiteren Widgets) eingebettet
- Filter-State (aktuelle Auswahl) wird von der `SongFilterBar` nach außen gemeldet (Signal), das übergeordnete Widget wendet den Filter auf seinen Datensatz an
- Welche konkreten Filter/Sortierungen der Planner aktuell hat, muss beim Umsetzen ermittelt werden (als Ausgangsbasis für die gemeinsame Komponente)

**Abgrenzung:** Nur der Kopf-/Filterbereich wird geteilt — die Tabelleninhalte bleiben in ihren jeweiligen Widgets (Songliste zeigt alle Songs, Planner zeigt Playlist-Einträge).
**Aufwand:** Mittel

---

### BL-122: Extended Data — Alternative MP3s und Lyrics verknüpfen mit Auswahl beim Laden

**Status:** ERLEDIGT (v0.83)
**Quelle:** David (2026-05-19)

**Beschreibung:**
Im Extended-Data-Bereich eines Songs soll man zusätzliche MP3-Dateien und Lyrics-Dateien als Alternativen hinterlegen können (und perspektivisch weitere Typen). Jeder Eintrag besteht aus zwei Feldern:
- **Dateiname/Pfad** der alternativen Datei
- **Beschreibungstext** (kurze Bezeichnung der Variante, z.B. "Singalong-Version", "Lyrics für Anfänger")

**Verhalten beim Laden eines Songs:**
Wenn ein Song selektiert wird, bei dem in Extended Data alternative MP3s oder Lyrics hinterlegt sind, erscheint eine Auswahl-Abfrage bevor der Song geladen wird. Die Abfrage zeigt:
- Die Einheiten gruppenweise (z.B. Gruppe "Song", Gruppe "Lyrics")
- Jede Option mit ihrer Nummer und Beschreibung
- Vorauswahl ist immer das Hauptelement aus den regulären Song-Daten (also keine Änderung des Standardverhaltens, wenn man einfach bestätigt)
- Auswahl per Zifferntasten für schnelle Bedienung im Live-Betrieb

**Ziel:** Schnelle, tastaturgesteuerte Auswahl im Live-Betrieb — der Caller kann z.B. spontan eine andere Tonart oder eine alternative Lyrics-Datei wählen, ohne die Song-Stammdaten zu ändern.

**Datenhaltung:**
- Neue SQLite-Tabelle `song_extended_files` (id, song_id, file_type [mp3/lyrics/...], file_path, label, sort_order)
- Oder als JSON-Feld in einer Extended-Data-Tabelle, falls eine solche bereits existiert

**Abgrenzung:**
- Die Stammdaten (primäre MP3, primäre Lyrics) bleiben unverändert in der Songs-Tabelle
- Die Alternativen sind rein situativ — sie ändern keine Stammdaten
- Der Dialog erscheint nur, wenn mindestens eine Alternative vorhanden ist (kein Dialog = kein Mehraufwand für Songs ohne Alternativen)

**Aufwand:** Mittel

---

### BL-125: CC1-Migration — Zweiten Musikpfad als Alternative MP3 übernehmen

**Status:** ERLEDIGT (v0.84)
**Quelle:** David (2026-05-21)
**Abhaengigkeit:** BL-122 (Alternative MP3s in `song_extended_files`) — muss umgesetzt sein ✓

**Hintergrund:**
In der CC1-Datenbank (callerv2.mdb) war pro Song ein zweiter Musikpfad vorgesehen (Feldname voraussichtlich `URL_Music2` o.Ä.). Dieser wurde in der Praxis häufig genutzt, um eine Vocal-Version desselben Songs abzulegen. Die bisherige CC1→CC2-Migration (BL-047) hat dieses Feld ignoriert.

**Ziel:**
Beim CC1-Migrations-Durchlauf den zweiten Musikpfad, sofern befüllt, automatisch als Alternative MP3 in die neue `song_extended_files`-Tabelle importieren — mit dem Label „Vocal-Version" (oder dem originalen Feldinhalt, falls CC1 einen Beschreibungstext gespeichert hat).

**CC1-Feld:** `URL_Vocal` (in `Song`-Tabelle) — verifiziert via `caller.mdb`
**Datenlage:** 125 von 520 Songs haben `URL_Vocal` befüllt (z.B. `SD234V.mp3`, `DWN104v.mp3` — Namenskonvention: `v`-Suffix für Vocal-Version).

**Umsetzung:**
- `migration.py` / `migration_worker.py`: Nach dem Anlegen des Song-Datensatzes prüfen, ob `URL_Vocal` befüllt ist
- Falls ja: Eintrag in `song_extended_files` (file_type=`mp3`, file_path=aufgelöster Pfad, label=`Vocal-Version`, sort_order=1)
- Pfad-Auflösung analog zur primären MP3 (relative Pfade, alle Suchpfade aus INI berücksichtigen)
- In der Migrations-Zusammenfassung am Ende ausweisen: „X Songs mit Vocal-Version migriert"

**Aufwand:** Klein (BL-122 hat die Infrastruktur bereits gebaut)

---

### BL-124: Lokation — Geplante Anzahl Tips als Vorgabe

**Status:** ERLEDIGT (v0.83)
**Quelle:** David (2026-05-21)

**Beschreibung:**
In den Lokations-Einstellungen (`_LocationSettingsDialog`) gibt es ein neues Feld „Geplante Anzahl Tips". Der eingetragene Wert wird automatisch an zwei Stellen übernommen, sobald die Lokation gewechselt wird:
- **Autofill-Dialog im Planner-Manager**: Füllt den Spin-Box „Anzahl Tips" vor
- **Evening Planner**: Setzt den Spin-Box „Geplante Tips" auf den Lokations-Wert

Der Nutzer kann den Wert in beiden Dialogen noch manuell überschreiben. DB-Feld: `locations.planned_tips INTEGER`.

**Aufwand:** Klein

---

### BL-127: Kontextmenü — Quality und ERR per ±1 anpassen

**Status:** ERLEDIGT (v0.89)
**Quelle:** David (2026-05-22)
**Bezug:** BL-102 (Rechtsklick-Kontextmenü), BL-111 (ERR-Feld), BL-119 (Song-Bewertung)

**Beschreibung:**
An allen Stellen in der App, wo Songs in einer Liste auftauchen, soll das Rechtsklick-Kontextmenü zwei neue Einträge bekommen:
- **„Qualität +1"** / **„Qualität −1"** — erhöht/senkt `quality` um 1 (Bereich 0–10, Clamp)
- **„ERR +1"** / **„ERR −1"** — erhöht/senkt `err` um 1 (Bereich 0–4, Clamp)

**Betroffene Stellen** (überall, wo Songs per Rechtsklick angesteuert werden können):
- Songliste (`SongListWidget`)
- Planner / Song-Pool (`PlaylistManagerWidget`)
- Playlist (`PlaylistWidget`)
- Statistik-Dock
- Ggf. weitere Stellen

**Umsetzung:** Zentrales `_song_context_actions(song_id)` / Helper-Methode analog zum bestehenden Pattern für „Zur Playlist" / „Zu Notizen" (BL-102/BL-088). Jede Liste ruft denselben zentralen Handler auf — kein doppelter Code.

**Aufwand:** Klein

---

### BL-128: Statusleiste — Miniatur-Abspielfortschritt mit Loop-Marks und Singing-Call-Sektionen

**Status:** ERLEDIGT (v0.85)
**Quelle:** David (2026-05-22)
**Bezug:** Player-Fortschrittsbalken, Loop-Marks, Singing-Call-Struktur (7 Blöcke)

**Beschreibung:**
Fenster wie Lyrics oder Sequenzen liegen oft im Vordergrund und verdecken den Player-Fortschrittsbalken (inkl. Loop-Marks und die 7 Singing-Call-Sektionen). Lösung: dieselbe Abspielanzeige zusätzlich in der **Statusleiste** einbauen.

**Anforderungen:**
- Miniatur-Fortschrittsbalken in der Statusleiste — läuft 1:1 synchron mit dem Player ✓
- Zeigt **Loop-In / Loop-Out-Marks** (analog zum Player) ✓
- Zeigt die **7 Sektionen eines Singing Calls** (Opener, Figure 1–4, Break, Closer) farblich wie im Player ✓
- Farben und Darstellung identisch mit dem bestehenden Player-Balken ✓
- Breite: nimmt den verfügbaren Platz in der Statusleiste ein (zwischen Geräteanzeige links und ggf. weiteren Elementen rechts) ✓
- Kein extra Klick nötig — immer sichtbar solange ein Song geladen ist ✓
- Ein-/ausschaltbar per INI: `display/statusbar_player = true/false` ✓

**Aufwand:** Mittel

---

### BL-126: Audio-Ausgabegerät in der Statusleiste wählen

**Status:** ERLEDIGT (v0.84)
**Quelle:** Claus Warnecke / David (2026-05-22)

**Beschreibung:**
Neue ComboBox dauerhaft in der rechten Statusleiste zum Wählen des Audio-Ausgabegeräts. Zeigt alle verfügbaren Ausgabegeräte des Systems (gefiltert auf `max_output_channels > 0`). Erster Eintrag immer „System-Standard" (bisheriges Verhalten). Gerätewechsel funktioniert auch während laufender Wiedergabe — der Stream wird sofort umgeschaltet. Auswahl wird in INI (`audio/output_device`) gespeichert und beim nächsten Start wiederhergestellt. Fallback auf System-Standard wenn das gespeicherte Gerät nicht verfügbar ist.

**Aufwand:** Klein

---

### BL-129: Einstellungen-Fenster — generische INI-Ansicht und -Bearbeitung

**Status:** ERLEDIGT (v0.88)
**Quelle:** David (2026-05-23)

**Beschreibung:**
Ein neues Einstellungen-Fenster (`QDialog` oder `QDockWidget`) liest die INI-Datei generisch aus, stellt alle Sektionen und Schlüssel übersichtlich dar und erlaubt die Bearbeitung direkt im Fenster. Keine hardcodierten Formularfelder pro Einstellung — stattdessen liest der Dialog die INI-Sektionen programmatisch und rendert für jeden Wert das passende Eingabe-Widget.

**Motivation:** Bisher müssen Einstellungen (Audio, Pfade, Shortcuts, Feedback-Modus, Skin usw.) direkt in der INI-Datei mit einem Texteditor bearbeitet werden. Ein Einstellungen-Fenster ist nutzerfreundlicher und verhindert Tippfehler.

**Ausgeschlossene Sektionen (reine Fenster-/Qt-Zustands-Daten, kein Nutzerwert):**
- `[General]` — `geometry`, `windowState` (QMainWindow-Zustand)
- `[rules_dock]`, `[loop_finder_dock]` und alle `*_dock`-Sektionen mit `geometry`-Key
- `[Tutorials]` — interne Abschluss-Flags (completed/not completed), kein Nutzerwert

**Eingeschlossene Sektionen mit ihren Schlüsseln (Stand 0.85):**

| Sektion | Schlüssel | Widget |
|---|---|---|
| `display` | `skin`, `language` | ComboBox (bekannte Werte) |
| `display` | `statusbar_player` | Checkbox |
| `paths` | `music_dir_1` … `music_dir_4` | LineEdit + Ordner-Button |
| `paths` | `last_import_dir` | LineEdit (read-only oder editierbar) |
| `audio` | `min_volume` | DoubleSpinBox (0.0–1.0) |
| `audio` | `output_device` | LineEdit |
| `loop` | `crossfade_ms` | SpinBox (ms) |
| `player` | `timer_warn1`, `timer_warn2` | SpinBox (Sekunden) |
| `shortcuts` | `play`, `pause`, `stop`, `fade_out`, `play_stop_toggle` | LineEdit (Tastenkürzel) |
| `playlist` | `start_date` | DateEdit |
| `feedback` | `enabled` | Checkbox |
| `sequences` | `zoom_pct` | SpinBox (%) |
| `notes` | `zoom_pct`, `first_note_factor` | SpinBox |
| `lyrics` | `zoom_pct` | SpinBox (%) |
| `lyrics` | `auto_size` | Checkbox |
| `debug` | `performance_logging` | Checkbox |
| `rules` | alle `sys_sys_*_active`-Keys | Checkbox |

**Generischer Mechanismus:**
Der Dialog iteriert über alle INI-Sektionen (außer Ausschlussliste). Für jeden Key wird der Wert-Typ erkannt:
- `true` / `false` → `QCheckBox`
- Ganzzahl → `QSpinBox`
- Dezimalzahl → `QDoubleSpinBox`
- Pfad-Key (enthält `_dir` oder `_path`) → `QLineEdit` + Ordner-auswählen-Button
- Alles andere → `QLineEdit`

Eine optionale Registrierungstabelle (`SETTINGS_META`) kann für bekannte Keys Labels, Tooltips, Wertebereiche und Widget-Typen überschreiben (z.B. `skin` → ComboBox mit bekannten Skin-Namen). Unbekannte Keys fallen automatisch auf den generischen Typ zurück — das stellt sicher, dass neue INI-Einstellungen automatisch im Fenster erscheinen, ohne Codeänderungen.

**UI-Aufbau:**
- Tabs oder zusammenklappbare Gruppen, eine pro INI-Sektion
- Buttons: `OK` (speichern + schließen), `Abbrechen`, `Übernehmen` (speichern ohne schließen)
- Öffnen per: Menü `App → Einstellungen…` (Shortcut: `Strg+,`)
- Schreibt Änderungen direkt in die INI; App liest betroffene Werte danach neu ein (soweit ohne Neustart möglich)

**Nicht-Ziel:**
- Kein Einstellungen-Fenster für DB-Tabellen (Tanzprogramme, Lokationen, Genres) — diese haben eigene Dialoge
- Kein Live-Preview für Skin-Wechsel (Neustart-Hinweis reicht)
- Kein verschachteltes Editor-Framework — einfacher Tab-Dialog genügt

**Aufwand:** Mittel

---

### BL-132: Sequenzen — Filter automatisch auf aktuelles Tanzprogramm setzen

**Status:** ERLEDIGT (v0.89)
**Quelle:** David (2026-05-27)
**Bezug:** BL-083 (Tanzprogramm-Anzeige im Player), BL-084 (Lokation mit Tanzprogramm), BL-089 (SequenzView Navigation)

**Beschreibung:**
Wenn das Tanzprogramm wechselt — egal ob durch Auswahl einer Lokation (die ein Programm hinterlegt hat) oder durch manuellen Wechsel im Player — soll der Level-Filter im Sequenzen-Fenster automatisch auf das neue Programm gesetzt werden. Beispiel: Tanzprogramm wechselt auf MS → Sequenz-Limiter springt auf „Mainstream". Wechsel auf A2 → Limiter springt auf „A2".

**Verhalten:**
- Trigger: **beide** — Lokation laden (wenn Lokation ein Tanzprogramm hat) UND manueller Programmwechsel im Player
- Wenn der User den Filter danach manuell ändert: beim nächsten Programmwechsel wird er **wieder überschrieben** (Programm hat immer Vorrang)
- **Opt-out**: Verhalten ist standardmäßig **aktiv**; kann in den Einstellungen deaktiviert werden (`sequences/auto_sync_program = true/false`)

**Umsetzung:**
- Wo das Tanzprogramm gesetzt wird (Player-Wechsel + Lokations-Laden), zusätzlich `sequences_widget.set_limit_filter(program_code)` aufrufen — wenn INI-Setting aktiv
- `set_limit_filter()` existiert bereits (BL-093 / Shortcode-Dispatch)
- INI-Setting `sequences/auto_sync_program` (default `true`)

**Aufwand:** Klein


---

### BL-136: Sequenzen — Löschen aus Sequenz-Fenster und SequenzView
**Status:** ERLEDIGT (v0.95, 2026-06-01)
**Quelle:** David (2026-06-01)

**Loesung:**
- DB-Methode `delete_sequences(ids: list)` in `song_db.py` — endgueltig, kein Papierkorb (Sequenzen werden von keiner anderen Tabelle ueber FK referenziert).
- **SequencesWidget** (Sequenz-Fenster mit Tabelle):
  - Selection-Mode auf `ExtendedSelection` (Multi-Select via Strg/Shift).
  - Rechtsklick im Kontextmenue: "Diese Sequenz loeschen" bzw. "{N} markierte Sequenzen loeschen".
  - "Loeschen"-Button unter der Tabelle (rechts, neben Statuszeile), aktiv nur wenn mind. eine Zeile selektiert.
- **SequenceViewWidget** (Detail-Ansicht): neuer "Loeschen"-Button in der Nav-Leiste, loescht die aktuell angezeigte Sequenz. Nach Loeschen springt die Anzeige auf die naechste Sequenz in der gefilterten Liste (sonst auf die vorherige, sonst leere Anzeige mit deaktivierten Buttons).
- Beide Wege fragen vor dem Loeschen per `QMessageBox.question` zurueck (Singular/Plural je nach Anzahl).
- Callbacks: `SequencesWidget.on_sequences_deleted`, `SequenceViewWidget.on_delete_sequence`, `SequenceViewWidget.remove_id_after_delete()` synchronisieren beide Sichten.

### BL-137: Timer-Überzug — eigene Audiodatei statt Piep
**Status:** ERLEDIGT (v0.97, 2026-06-03)
**Quelle:** David (2026-06-03), beim Caller-Kollegen gesehen

**Beschreibung:**
Beim Überschreiten der Pattern-/Singing-Timer-Zeit soll statt (oder zusätzlich zu) dem aktuellen Piep eine vom Nutzer hinterlegte MP3/WAV-Datei mitspielen. Beim Caller-Kollegen war es ein Esel-Geräusch — das ist witzig, hörbar deutlich und kann pro Caller individuell sein.

**Anforderungen:**
- Im Einstellungen-Dialog (BL-129) Pfad zur Audiodatei wählbar machen — z.B. Sektion „Hinweis-Sounds".
- Default: aktueller Piep (winsound.Beep oder die bisherige Lösung) bleibt aktiv, wenn kein Pfad gesetzt ist.
- Beim Überschreiten: Datei wird im laufenden Audio-Callback **in den Song hineingemischt** — gleicher Stream, gleiches Ausgabegerät. Kein zweiter Stream, damit der Hinweis garantiert über dieselben Lautsprecher kommt wie die Musik.
- Lautstärke der Hinweis-Datei eigenständig einstellbar (Slider im Einstellungen-Dialog).
- Optional: getrennte Dateien für Pattern-Überzug vs. Singing-Überzug (zwei Pfade).
- Mehrfach-Auslösung verhindern: nicht bei jedem Tick erneut starten, sondern einmal pro Überzug-Eintritt.

**Aufwand:** Klein bis Mittel. Audio-Abspiel-Infrastruktur ist bereits da (sounddevice + soundfile). Hauptarbeit: Settings-UI und Mehrfach-Trigger verhindern.

**Abhängigkeit:** Keine harte. Sauberer wenn BL-129 (Einstellungen-Dialog) bereits den passenden Sektions-Platz hat.

### BL-138: Player — Label und Label-Nummer als Sekundär-Info anzeigen
**Status:** ERLEDIGT (v0.97, 2026-06-03)
**Quelle:** David (2026-06-03)

**Beschreibung:**
Im Player-Widget unter der primären Statuszeile zusätzlich Label und Label-Nummer des aktuellen Songs anzeigen. Nicht primär wichtig, aber wenn ein Caller-Kollege fragt „welches Label war das?" soll die Information ohne Umweg über die Song-Daten greifbar sein.

**Anforderungen:**
- Position: direkt unter der bisherigen Statusinfo im Player-Card-Bereich.
- Schriftgröße und -attribute identisch zur Statuszeile (gleiche QSS-Klasse).
- Format-Vorschlag: „<Label> — <Label-Nummer>" (Trenner verhandelbar). Bei fehlendem Label/Nummer wird die Zeile ausgeblendet (kein leerer Platz).
- Aktualisierung bei Song-Wechsel im selben Refresh-Pfad wie die bisherigen Player-Felder.

**Aufwand:** Klein. QLabel hinzufügen, in `Player._refresh_from_song()` (oder äquivalent) befüllen, im Skin per QSS stylen.

**Abhängigkeit:** Keine.

**Aufwand:** Klein

### BL-144: Lokation — Ziel-Tempo in BPM (automatische Stretch-Berechnung pro Song)
**Status:** ERLEDIGT (v0.124, 2026-07-19 — GUI-Test durch David bestätigt; Build ausstehend)
**Quelle:** David (2026-06-14)
**Beschreibung:** Pro Lokation soll alternativ zur bestehenden Prozent-Einstellung ein **Ziel-Tempo in BPM** hinterlegbar sein. Ist dieser Eintrag aktiviert, wird für **jeden Song individuell** die lokale Tempo-Anpassung (Stretch-%) so berechnet, dass am Ausgang immer das gewünschte Ziel-Tempo herauskommt — unabhängig vom Original-BPM des Songs. Das ist eine Variante der bereits existierenden Prozent-Einstellung pro Lokation.

**Eindeutigkeit (wichtig):**
- Neues Feld in `locations` zusätzlich zum bestehenden Prozent-Feld.
- Es darf **immer nur EINES von beiden** gefüllt sein (Prozent ODER Ziel-BPM). Damit bleibt eindeutig, was das Programm tun soll. UI muss das gegenseitige Ausschließen erzwingen (z.B. eines leert das andere bzw. Radio-Auswahl).

**Offene Punkte bei Umsetzung:**
- Voraussetzung ist ein bekannter BPM-Wert pro Song. Verhalten definieren, wenn ein Song **kein BPM** hat (überspringen / Auto-BPM anstoßen → vgl. BL-095 / keine Anpassung). 
- Stretch-Faktor = Ziel-BPM / Song-BPM; Begrenzung auf den zulässigen Tempo-Bereich des Players prüfen.

**Verwandt:** BL-086 (temporäres Festtempo pro Lokation, erledigt — anderer Mechanismus), BL-095 (Auto-BPM-Ermittlung), bestehende Prozent-Einstellung pro Lokation.
**Aufwand:** Mittel (DB-Feld, UI mit Exklusiv-Logik, Stretch-Berechnung beim Songladen, BPM-Fallback)

**Entscheidungen (David, 2026-07-18):**
- **Bezug = Ist-BPM:** gerechnet wird gegen `base_bpm × Song-Tempo`, nicht gegen die rohe Song-BPM. Song-eigene Tempo-Abweichungen werden dadurch überschrieben — dafür laufen alle Songs hörbar auf derselben BPM.
- **Gilt für alle Songs** (Patter und Singing). Der Caller kann danach manuell am „heutigen Tempo" abweichen (Hot Hash schneller, Workshop langsamer); die Abweichung gilt für den laufenden Song und wird beim nächsten Songwechsel neu gerechnet.
- **Ohne BPM am Song:** Tempo bleibt bei 100 %, kein Auto-BPM (zu langsam im Live-Betrieb). Anzeige macht es sichtbar.
- **Ziel unerreichbar:** auf 50/150 % kappen und die BPM-Anzeige in Warnfarbe markieren — kein Dialog.
- **Umschaltung über Radio-Buttons statt Wert-Exklusivität (korrigiert 2026-07-18):** Der erste Ansatz („Feld gefüllt → anderes ausgegraut") war eine Sackgasse — Lokationen mit Alt-Tempo ≠ 100 % (z.B. 103 %) konnten nie auf Ziel-BPM umgestellt werden. Stattdessen entscheidet ein Radio-Paar, **beide Zahlenwerte bleiben gespeichert**. Der Caller kann also 103 % und 128 BPM hinterlegt haben und nur umschalten, ohne einen Wert neu eintippen zu müssen.

**Umsetzung (2026-07-18):**
- **DB** (`song_db.py`): zwei Migrationen — `target_bpm REAL` und `tempo_mode TEXT` (`'percent'`|`'bpm'`; NULL wird als `'percent'` gelesen, deshalb kein Daten-Update für den Altbestand nötig). `Location` bekommt `target_bpm`, `tempo_mode`, Property `effective_tempo_mode` und `has_target_bpm` (greift nur bei Modus `bpm` UND vorhandener Zahl). `get_all_locations()` und `update_location_settings()` erweitert; letztere speichert **beide** Zahlenwerte unverändert.
- **Lokations-Dialog** (`main.py`, `_LocationSettingsDialog`): Radio-Paar in einer `QButtonGroup` vor den beiden Feldern; `_sync_tempo_fields()` graut das Feld des nicht gewählten Modus aus — gesteuert vom Radio, nicht vom Zahlenwert. `get_values()` liefert `target_bpm` und `tempo_mode` als 5. und 6. Rückgabewert.
- **Rechnung** (`PlayerWidget._apply_target_bpm`): `heutiges Tempo = Ziel-BPM / (base_bpm × Song-Tempo)`, gerundet auf ganze Prozent, aufgerufen beim Songladen direkt nach `_base_bpm`. Kappung auf den SpinBox-Bereich mit Merker `_target_bpm_missed`.
- **Anzeige** (`_update_bpm_display` + `_set_bpm_warning`): bei nicht erreichtem Ziel Warnfarbe aus dem Skin (`skin_mgr.color("warning")`) plus erklärender Tooltip; ohne BPM am Song erscheint „—".
- **Lokationswechsel**: Ziel-BPM hat Vorrang vor dem BL-086-Zweig und wird für den bereits geladenen Song sofort nachgezogen.
- **i18n** DE/EN/JA für Label, beide Tooltips und drei Statusmeldungen.

**Getestet (2026-07-18):** Migration einer Kopie der Test-DB (41 Lokationen unverändert, beide Spalten ergänzt, `tempo_mode` durchgehend NULL → Altbestand läuft weiter auf Prozent); Umschalten in beide Richtungen ohne Wertverlust; Modus `bpm` ohne BPM-Zahl fällt korrekt auf Prozent zurück; Dialog offscreen inkl. des ursprünglich fehlgeschlagenen Falls (Lokation mit 103 % lässt sich auf Ziel-BPM umstellen); Rechnung gegen Beispielwerte (120→128 BPM = 107 %, 136→128 = 94 %, unerreichbare Ziele korrekt gekappt).
**Offen:** Live-GUI-Test durch David (echter Songwechsel im Player, Warnfarbe im jeweiligen Skin). Rundung auf ganze Prozent bedeutet je nach Song bis zu ±0,5 BPM Restabweichung — Grenze der SpinBox, nicht der Rechnung.

---

### BL-146: Lyrics — DOCX und PDF als Lyric-Dateien unterstützen
**Status:** ERLEDIGT (2026-07-18; implementiert 2026-06-16)
**Quelle:** Userin-Feedback (2026-06-14, über Facebook-Caller-Gruppe)
**Entscheidung (David, 2026-06-16):** DOCX/PDF sind **reine Anzeige**. Bei Edit-Versuch wird angeboten, eine bearbeitbare HTML-Kopie anzulegen (gleicher Migrationspfad wie RTF/TXT — Original bleibt unverändert). Damit ist die offene Frage (Textübernahme vs. Formatierung) beantwortet.
**Umsetzung (2026-06-16):**
- DOCX: eigener Mini-Parser (zipfile + xml.etree → HTML, Fett/Kursiv/Unterstrichen + Schrift-/Hintergrundfarben via `w:color`/`w:highlight`/`w:shd`). KEINE neue Abhängigkeit. `LyricsWidget._docx_to_html`/`_load_docx`.
- PDF: Textextraktion via **pypdf** (schlank, ~2 MB, 0 Transitiv-Deps; pdfminer.six verworfen wegen ~21 MB Build-Zuwachs). Lazy-Import in `_load_pdf` → 0 ms Startup. Reine Textanzeige (`<pre>`), keine Farbtreue. Bei pdfminer-Umstieg später nur Loader + requirements tauschen.
- **PDF bleibt bewusst Klartext (David, 2026-06-16):** Geprüft an AAA.pdf — Highlights sind KEINE PDF-Annotationen, sondern gezeichnete Füll-Rechtecke im Content-Stream; pypdf liefert die nicht. Schriftgrößen/Fett wären via pypdf-Visitor mit Mühe machbar, aber ohne Highlights und mit fragilem Layout-Nachbau → schlechtes ROI, verworfen. Volle PDF-Treue bräuchte pdfplumber (~22 MB, kein AGPL) oder PyMuPDF (~35 MB, AGPL). Falls später viele Beschwerden: pdfplumber erwägen. PDF ist die „Schnell-Ansicht des Call-Texts"; für Formatierung/Markierungen DOCX/RTF/HTML nutzen oder per Editier-Angebot in HTML umwandeln.
- Edit-Angebot: `_offer_convert_display_to_html` / `_convert_display_to_html` (neue .html daneben, DB `lyrics_file` umgezogen).
- Endungen `.docx`/`.pdf` ergänzt in `LyricsWidget._SUPPORTED_*`, `_LYRICS_EXTENSIONS` (Auto-Import), Migration (migrate.py:707), Datei-Dialog-Filter.
- Build: `pypdf>=4.0` in requirements.txt + Spec-hiddenimports.
**Beschreibung:** Aktuell werden Lyrics als RTF und HTML (und Text) unterstützt. Eine Userin möchte zusätzlich **.docx (Word)** und **.pdf** als Lyric-Dateien verknüpfen und anzeigen können.

**Umsetzung (Idee):**
- DOCX: Text + Basisformatierung (Absätze, Fett/Kursiv, ggf. Hintergrund-/Schriftfarbe für Tag-/Break-Markierungen) extrahieren und im Lyrics-Dock rendern. Mögliche Wege: `python-docx` (reine Textebene + einfache Runs) oder Konvertierung nach HTML/RTF, das die bestehende Anzeige bereits beherrscht.
- PDF: vermutlich nur Text-Extraktion bzw. Seitenanzeige; Formatierungstreue geringer als bei DOCX. Klären, ob reine Textanzeige reicht oder eingebettete Seitendarstellung gewünscht ist.
- Datei-Erkennung in die Lyric-Verknüpfung/Auflösung aufnehmen (Endungen `.docx`, `.pdf`), inkl. Migration und virtueller Pfadauflösung (BL-104).
- Neue Abhängigkeiten gegen Build-Größe abwägen (vgl. tech_stack).

**Offene Frage:** Reicht reine Textübernahme, oder ist die farbliche Hervorhebung (wie bei RTF/HTML, vgl. BL-005) auch bei DOCX gewünscht? Beim Zoom-Termin mit der Userin gleich mitklären.
**Verwandt:** BL-005 (RTF/HTML-Formatierung anzeigen, erledigt), BL-043 (RTF-Lyrics-Sonderfall), BL-087 (mehrere Lyric-URLs pro Song).
**Aufwand:** Mittel (DOCX-Parsing) bis Groß (wenn PDF-Seitenrendering + Formatierungstreue gefordert)

---

### BL-147: Relative Pfade im File-Feld — eine Wurzel-Musikbibliothek statt vieler Slots
**Status:** ERLEDIGT (v0.104)
**Quelle:** David (2026-06-15)
**Prioritaet:** Hoch
**Umsetzung (2026-06-15):** Plan `goofy-noodling-patterson.md`. PathManager-Helfer
`to_relative_filename`/`to_relative_lyric_filename` (relpath gegen Slots 1→4,
First-come-first-serve, POSIX-`/`), `find_song_file` haertet Separatoren; alle 4
File-Picker vereinheitlicht; Import speichert im In-place-Modus relative Pfade mit
Basename-Dedup-Fallback (nur verwaiste Eintraege werden gehoben); Separator-
Migration in `song_db._migrate`; Re-Index-Werkzeug (`_ReindexWorker`, Menue Pfade)
ueber alle Slots. Logik per Integrationstest (PathManager + SQLite-Migration)
verifiziert; GUI-Durchklick (`run_test.bat`) noch offen.
**Migrations-Tool (2026-06-15):** Auch ins `migration.exe` gezogen — Abfrage
Kopieren/Verknüpfen + Wurzelverzeichnis, relative Pfade in beiden Quellen
(CC1 rekursiv, SqView mit Kollisionsfix), Ziel-INI-Slots im Verknüpfen-Modus.
Helfer/INI-Writer per Test verifiziert (vgl. BL-145). GUI-Durchklick offen.
**Beschreibung:** Es gibt Caller, die ihre Musikdateien über sehr viele Verzeichnisse verteilt ablegen. Die aktuell 4 Musik-Slots (BL-050) reichen dafür nicht aus, und beliebig viele Slots zu definieren ist keine gute Lösung. Stattdessen: Der `file`-Eintrag eines Songs in der DB soll künftig **einen relativen Pfad** enthalten dürfen (z.B. `Singing Calls/Country/song.mp3`), nicht mehr nur den nackten Dateinamen. Der Nutzer wählt **einen Wurzelpfad** seiner Musikbibliothek; das Programm durchsucht diesen rekursiv und speichert jeden gefundenen Song **relativ zum Wurzelverzeichnis**. Beim Abspielen werden — wie heute schon — Pfad und Dateiname zusammengesetzt.

**Gute Nachricht aus der Code-Analyse:** Die **Lese-Seite funktioniert größtenteils bereits.** `PathManager.find_song_file()` ([path_manager.py:177](../src/path_manager.py)) macht `os.path.join(music_dir, filename)` — ein `filename` mit Unterordner-Anteil löst damit korrekt auf. BL-105 hat das bereits bestätigt („In der normalen Songliste funktioniert es, weil dort der vollständige relative Pfad inkl. Unterordner gespeichert ist"). Der eigentliche **Engpass ist die Schreib-Seite**: Der Import speichert heute immer nur `os.path.basename(filepath)` (main.py ~15270). Damit geht der Unterordner-Anteil verloren.

**Kern der Umsetzung:**
1. **Wurzelpfad-Auswahl + Rekursiv-Scan**: Neue UI/INI-Einstellung „Wurzel der Musikbibliothek". Beim Import/Re-Index wird per `os.walk()` rekursiv gesucht (Mechanik existiert bereits aus BL-032) und pro Song `os.path.relpath(filepath, wurzel)` als `filename` gespeichert — **statt** `os.path.basename()`.
2. **Separator-Normalisierung**: Relative Pfade **immer mit `/`** (POSIX) speichern, beim Auflösen normalisieren. Backslashes in der DB sind nicht portabel (USB-Stick, anderer Rechner) — widerspräche der Portabilitäts-Philosophie des PathManager (relative Pfade, Laufwerksbuchstaben-unabhängig).
3. **Keine Schema-Änderung nötig**: `songs.filename` ist bereits `TEXT`. Es ändert sich nur der *Inhalt* (Basename → relativer Pfad), nicht die Spalte.
4. **Misch-Betrieb (Pflicht)**: Bestandsdaten (nackte Basenames) und neue relative Pfade müssen **gleichzeitig** funktionieren. Der Resolver kann beides (Join funktioniert in beiden Fällen). Keine erzwungene Neu-Migration.

**Impact-Analyse — was vorab geprüft / angepasst werden muss (damit alle Funktionen weiter laufen):**

- **Dedup / UNIQUE-Constraint** (`get_by_filename`, [song_db.py:635](../src/song_db.py); `update_filename`, [song_db.py:616](../src/song_db.py)): Heute ist `filename` UNIQUE auf Basename-Ebene. Mit relativen Pfaden wird derselbe Basename in zwei Unterordnern zu **zwei verschiedenen Schlüsseln** — das ist gewollt (echte Duplikate werden unterscheidbar). **Aber**: Ein bereits als `song.mp3` migrierter Song und derselbe Song als `Sub/song.mp3` gelten dann als verschieden → potenzielle Doppel-Einträge. Dedup-Strategie definieren (z.B. beim Re-Index per Basename-Fallback matchen statt neu anlegen).
- **„…"-Datei-Picker im Song-Datensatz** (BL-023): Beschränkt die Auswahl auf den Musikordner und speichert via `update_filename`. Muss künftig den **relativen Pfad zur Wurzel** berechnen statt nur den Basename.
- **Potential-Widget „Ohne MP3"** (BL-027, [main.py](../src/main.py)): Nutzt `find_song_file()`. Läuft weiter, sobald relative Pfade auflösen — und findet sogar Songs, die heute fälschlich als „ohne MP3" markiert werden, weil der Unterordner fehlte. **Kein Bruch, eher Verbesserung** — aber explizit gegentesten (war der ausdrückliche Wunsch).
- **Multi-Slot-Zusammenspiel** (BL-050 / BL-104): `find_song_file` probiert Slot 1→4, jeweils `join(slot, filename)`. Relative Pfade + Multi-Slot komponieren sauber. **Designfrage klären:** Ist der relative Pfad relativ zu **einer** gewählten Wurzel, oder wird er gegen **jeden** Slot probiert? Empfehlung: gegen jeden Slot probieren (robust, deckt verschobene Bibliotheken ab). Die „Wurzel" ist dann faktisch ein (großer) Slot, dessen Unterbaum vollständig indexiert wird.
- **Playlist-Persistenz** (`.playlist`-Dateien, Fallbacks `get_by_title`/`get_by_filename` an [main.py:3722](../src/main.py), 4611, 4836): Referenzieren `filename`. Künftig steht dort der relative Pfad — Lade-Logik und Fallback-Matching prüfen.
- **Varianten** (`music_2_file` etc. in `song_properties`, [song_db.py:697](../src/song_db.py)): Speichern ebenfalls Dateinamen → für Konsistenz dieselbe Relpath-Behandlung.
- **Anzeige**: Der Song-Datensatz zeigt `song.filename` direkt an ([main.py:3035](../src/main.py)). Mit relativem Pfad würde dort der ganze Unterpfad stehen — entscheiden: kompakt nur Basename anzeigen, vollständigen relativen Pfad als Tooltip/Detail.
- **Migration (CC1 / SqView)**: SqView-Migration hat bereits einen rekursiven MP3-Index (BL-011). Migrationen sollten den relativen Pfad zur gewählten Wurzel speichern können; Bestands-Migrationen mit Basename bleiben über die Slot-Auflösung gültig.

**Offene Designentscheidungen (vor Umsetzung mit David klären):**
- A) Relpath relativ zu **einer** Wurzel oder gegen **alle** Slots aufgelöst? (Empfehlung: gegen alle Slots.)
- B) Separator: POSIX `/` in DB (Empfehlung) — bestätigen.
- C) Dedup-Strategie Basename ↔ Relpath beim Re-Index.
- D) Optionales Einmal-Werkzeug „Bestehende Songs auf relative Pfade re-indexieren" (gegen gewählte Wurzel) anbieten — ja/nein?

**Verwandt:** BL-050 (4 Musik-Slots, erledigt), BL-104 (zentrale Multi-Pfad-Auflösung, erledigt), BL-105 (Songs in Unterordnern — bestätigt, dass relative Pfade beim Auflösen bereits funktionieren), BL-032 (rekursiver Import via `os.walk`, erledigt), BL-145 (Migration nur verknüpfen + rekursiv suchen), BL-001/BL-125 (mehrere Musikpfade in der Migration).
**Aufwand:** Mittel bis Groß (Schreib-Seite: Wurzel-Auswahl + Relpath-Speicherung + Dedup; plus Anpassung Picker/Anzeige/Varianten/Playlist-Fallbacks und Gegentest aller Auflöse-Stellen)

---

### BL-148: Bulk-Delete großer Songmengen über mehrfach sortierbare Liste
**Status:** ERLEDIGT (v0.104, 2026-06-17 — GUI-Test (Filter + Löschen) bestätigt, EXEs + ZIPs gebaut)
**Quelle:** David (2026-06-17)
**Umsetzung (2026-06-17):** Neuer Reiter „Massen-Löschen" im Potential-Widget (`PotentialWidget._build_bulk_delete_tab`/`_load_bulk_table`). 7 sortierbare Spalten (Typ P/S/PS · Hinzugefügt=`date_added` · Titel · Label · Genre[1] · ERR · Quality), `ExtendedSelection` (Shift/Strg/Strg+A), Lazy-Load erst beim Tab-Öffnen. Eine Sicherheits-Nachfrage; Historie nur abgefragt wenn vorhanden (Default Nein, FK-OFF lässt verwaiste Historie stehen). Löschen im `_BulkDeleteWorker` (Eiserne Regel), chunk-fest (SQLite-Var-Grenze) in einer Transaktion. DB: `get_all_songs_for_bulk`, `count_songs_with_history`, `bulk_delete_on_connection`(staticmethod)/`bulk_delete_songs`. Perf-Messpunkte (DB-Query/Genre-Map/Tabellenaufbau/Delete) bei aktivem Perflog. Übersetzungen DE/EN ergänzt.
**Beschreibung:** Es kommt vor, dass versehentlich eine große Menge Songs in die Datenbank geladen wurde (z.B. ein falscher Ordner beim Import, eine fehlerhafte Migration). Gesucht ist ein Werkzeug, um eine **große Menge an Songs auf einen Schlag aus der Datenbank zu entfernen** — ohne Einzel-Rückfrage pro Song. Stattdessen: **einmal** den kompletten Bulk-Delete bestätigen (eine Sicherheits-Nachfrage mit Anzahl), danach wird ohne weitere Zwischenfragen gelöscht.

**Kernanforderung — mehrfach sortierbare Auswahl-Liste:**
Eigenes Fenster/Dialog mit einer Tabelle aller (bzw. gefilterter) Songs, deren Spalten **alle sortierbar** sind (Klick auf Spaltenkopf, idealerweise mehrstufig / Sekundärsortierung). So kann der Nutzer die irrtümlich geladenen Songs schnell zusammenführen (z.B. nach Aufnahmedatum/Import sortieren, um den falschen Schwung zu isolieren).

**Massenselektion der Zeilen (Pflicht):**
- **Strg+Klick** = einzelne Zeilen zur Auswahl hinzufügen/entfernen (diskontinuierlich).
- **Shift+Klick** = zusammenhängenden Bereich von der zuletzt geklickten bis zur aktuellen Zeile markieren.
- Kombination aus beidem möglich (mehrere Bereiche + Einzelzeilen).
- Zusätzlich **Strg+A** („Alle in Ansicht markieren"). Wichtig: Bezieht sich immer auf die **aktuell sichtbare/gefilterte und sortierte** Ansicht.
- Technisch: `QTableWidget`/`QTableView` mit `setSelectionMode(ExtendedSelection)` und `setSelectionBehavior(SelectRows)` — Shift/Strg-Verhalten kommt damit nativ.

**Spalten:**
- **Pattern / Singing / PS** (Typ-Kennung)
- **Aufnahmedatum** (bzw. Import-/Anlagedatum — klären, welches Datum gemeint ist; vgl. BL-040)
- **Titel**
- **Label**
- **Genre**
- **ERR** (Fehler-/Problem-Markierung, z.B. „ohne MP3", „ohne Qualität" — vgl. Potential-Checks BL-027)
- **Quality**

**Ablauf:**
1. Fenster öffnen → Liste füllen (ggf. mit Vorfilter, z.B. „nur letzter Import" / Datum).
2. Sortieren nach beliebiger Spalte, Mehrfachauswahl der zu löschenden Songs.
3. **Eine** Bestätigungs-Nachfrage: „X Songs wirklich aus der Datenbank löschen?" — mit Option, die Historiendaten (play_history, song_location_stats) gleich mit aufzuräumen (analog BL-039 / BL-028).
4. Löschen läuft ohne weitere Einzel-Rückfragen durch.

**Hinweise zur Umsetzung:**
- Baut auf BL-039 (Songs einzeln/mehrfach löschen, erledigt P41) auf — hier geht es um den **Massen-Workflow mit komfortabler Selektion** statt Einzelmarkierung in der normalen Songliste.
- Performance: Löschen großer Mengen als **eine** Transaktion bündeln; bei sehr vielen Songs ggf. in QThread auslagern (Eiserne Regel — Main-Thread nicht blockieren, falls ein Song läuft).
- Sicherheit: Da kein Einzel-Undo gewünscht ist, vor dem Löschen Anzahl + ggf. Auflistung deutlich anzeigen. Optional: vorheriges DB-Backup anbieten.
- **ERR-Spalte** sinnvollerweise aus den vorhandenen Potential-Checks (BL-027: „Ohne MP3", „Ohne Qualität") speisen.

**Verwandt:** BL-039 (Songs aus DB löschen, einzeln/mehrfach — erledigt), BL-040 (Neue Imports als Liste nach Datum — offen, gleiche Sortier-/Datums-Idee), BL-027 (Potential-Widget Datenqualität / ERR-Quelle), BL-028 (Lösch-Option inkl. Historie), BL-034 (Massenänderung Singing/Pattern — ähnliches Mehrfachauswahl-Muster).
**Aufwand:** Mittel

### BL-149: Sprachvariante Japanisch
**Status:** ERLEDIGT (v0.105) — Japanisch als dritte UI-Sprache vollständig integriert (~1.460 Texte, Erststart-Auswahl + Sprach-Menü, Calls bleiben englisch). Empfohlen bleibt optional ein Review durch einen japanischsprachigen Caller vor breiter Vermarktung.
**Quelle:** David (2026-06-17)
**Beschreibung:** Eine dritte UI-Sprache **Japanisch (ja)** zusätzlich zu Deutsch und Englisch. Square Dance ist in Japan stark verbreitet — eine japanische Oberfläche würde den Caller-Markt dort erschließen.

**Technische Machbarkeit (geprüft 2026-06-17):**
- Das i18n-System (`src/i18n.py` + `src/translations.json`) ist sprach-agnostisch aufgebaut: jeder der 1464 Keys ist ein Dict `{"de": ..., "en": ...}`. Eine dritte Sprache wird durch Hinzufügen von `"ja": ...` pro Eintrag ergänzt — **keine Code-Änderung an der Übersetzungs-Mechanik nötig**.
- Anzupassen: `get_available_languages()` in `i18n.py` um `("ja", "日本語")` erweitern; der Erststart-Sprachdialog (BL-058) und das Sprach-Dropdown in den Einstellungen müssen den dritten Eintrag anzeigen.
- **Darstellung in den Widgets:** PySide6/Qt rendert Unicode inkl. CJK problemlos, solange eine Schrift mit japanischen Glyphen verfügbar ist. Unter Windows 11 sind „Yu Gothic UI" / „Meiryo" gebündelt, und Qt fällt für fehlende Glyphen automatisch darauf zurück. Die App erzwingt global keine Latin-only-Schrift (meist `QFont()`-Default, vereinzelt `monospace`/Consolas für Zahlen-/Diagnose-Anzeigen). **Risiko:** An den Stellen mit fest gesetztem `Consolas`/`monospace` (z.B. Beat-Snap-Infozeilen, Diagnose-Center) könnten japanische Zeichen als Tofu-Kästchen erscheinen → vor Release prüfen und ggf. auf systemeigene Fallback-Schrift umstellen.
- **Übersetzungsweg:** Die deutschen/englischen Strings können maschinell ins Japanische übersetzt werden (Claude kann Deutsch→Japanisch). Wegen Fachvokabular (Square-Dance-Calls, Caller-Begriffe) und kurzer UI-Labels (Platz/Truncation) ist ein **Review durch einen japanischsprachigen Caller** dringend empfohlen, bevor ausgeliefert wird. Calls (Allemande, Swing Thru …) bleiben in Japan üblicherweise englisch — nicht übersetzen.

**Offene Punkte / Aufwand-Treiber:**
- 1464 Keys übersetzen (maschinell vorbefüllbar, danach fachliches Lektorat).
- Schrift-Fallback an den `monospace`-Stellen verifizieren.
- Lange deutsche Komposita vs. kompakte japanische Labels — Layout an wenigen Stellen prüfen.
**Verwandt:** BL-058 (Erststart-Sprachabfrage), BL-123 (tote Translation-Keys aufräumen — vor der Übersetzung sinnvoll, spart Arbeit).
**Aufwand:** Mittel (Mechanik trivial, Masse + Lektorat treiben den Aufwand)

## Nutzerfeedback (Facebook-Umfrage „Cuesheets & Co", 2026-06-23)
Sammlung aus einer Facebook-Umfrage unter Callern. Mehrfachwünsche wurden aufgetrennt, Dubletten gegen bestehende BLs geprüft und verlinkt.

### BL-157: ZIP-Import von Label-Paketen (Songs + Lyrics automatisch einrichten)
**Status:** ERLEDIGT (2026-07-18; erste Version v0.107, Erweiterung v0.108)
**Quelle:** Facebook-Umfrage (2026-06-23)
**Umsetzung (v0.107):** Quelle „ZIP-Paket" im Import; GUI-freier Analyzer `zip_import.py` (gemeinsamer Basename → Haupt-MP3 ohne Modifier + Varianten + Lyrics, label-agnostisch) + Vorschau-Dialog `zip_import_dialog.py` (Drag&Drop-Reihenfolge, An-/Abwahl + editierbare Bezeichnungen für Musik UND Lyrics, editierbare Abkürzungs-Tabelle `zip_modifiers.json`). Commit über wiederverwendeten `_import_single_audio` + `add_variant`. Hintergrund-Thread + Perf-Marken, i18n DE/EN/JA. Getestet an GP-509-Paket.

**Erweiterung (v0.108) — Vollständigkeitscheck + pflegbare Wissensbasis:**
- **Gruppierung pro ZIP** statt nach Basename: alle Audios eines Pakets landen in der Song-Area, alle Lyrics in der Lyric-Area, alles andere mit Begründung in einer „Sonstige"-Sektion. Behebt das Auseinanderfallen in mehrere „Songs", wenn Varianten/Originale abweichende Basenamen haben (z.B. `original …`, `WM 002v`).
- **Vollständigkeitscheck:** jede entpackte Datei ist garantiert zugeordnet ODER gelistet; Bilanz „N Dateien — M zugeordnet, K sonstige" oben im Preview (`AnalysisResult.total_files/assigned_count/is_complete`).
- **Vier pflegbare Listen** (`zip_import_lists.json`): Modifier, Label-Verzeichnis, Beiwerk-/Ignorier-Muster, Rollen-Keywords. Architektur: Standard-Einträge im Code (`DEFAULT_*`), User-Datei nur Delta (`entries` + `removed`-Tombstones); Merge bei Laden mit User-Vorrang → Updates liefern neue Standards, ohne User-Einträge zu überschreiben. `ManagedList`/`ImportLists` + `load_lists`/`save_lists`. Alte `zip_modifiers.json` wird automatisch migriert.
- **Ein Pflege-Dialog** `ImportListsDialog` (4 Reiter, generalisierter Tabellen-Editor) + „Liste importieren" (additiver Merge für Kollegen-Austausch) + „auf Standard zurücksetzen". Ersetzt den alten Modifier-Editor.
- **Modifier an drei Orten erkannt** (jeweils nur bei bekanntem Token): Klammer `(V)`, am Label-Suffix `002v`, freies Wort am Ende `VJ`. Flip-Side-Suffixe (`509a`) und normale Titelwörter bleiben unangetastet.
- **Standard-Songtyp im Preview = Singing** (Label-Pakete sind meist Singing Calls).
- Getestet an WM-002 (Born To Hand Jive) und RYL-164 (I Cant Fight This Feeling), beide importierbar.
**Offen:** `.doc` (altes Word-Binärformat) wird nicht unterstützt (nur `.docx`) — bewusst, landet sichtbar in „Sonstige". Default-Label-Liste ist Starter (Community-/User-Pflege). Mehrere *verschiedene* Songs in EINEM ZIP würden zusammen in eine Song-Area fallen (Annahme 1 ZIP = 1 Song).
**Beschreibung:** Labels liefern oft ZIP-Pakete mit Songs (gepitched oder mit Harmony) und Lyrics in verschiedenen Formaten aus. Der Caller möchte ein ZIP einfach in einen Import-Ordner legen, und CC holt sich alles heraus und richtet es automatisch ein.
**Teilschritte:**
- ZIP automatisch entpacken (überwachter Import-/Drop-Ordner)
- Audiodateien importieren (inkl. gepitchte/Harmony-Varianten — ggf. als alternative MP3s, vgl. BL-122/BL-125)
- Lyrics in den verschiedenen Formaten erkennen und automatisch dem passenden Song zuordnen (Matching, vgl. SqView-Lyrics-Matching BL-011/BL-055)
- Fehlertolerant gegenüber defekten/unerwarteten Dateien (vgl. BL-065)
**Verwandt:** BL-012 (Bulk-Import), BL-032 (rekursiver Import), BL-021 (Label-/Metadaten-Erkennung), BL-122/BL-125 (alternative MP3s), BL-146 (DOCX/PDF-Lyrics).
**Aufwand:** Groß

### BL-160: Cuesheet-Scroll-Synchronisation über Zwischen-Sync-Punkte
**Status:** ERLEDIGT (2026-06-25, getestet; in 0.109 gebaut & released)
**Quelle:** Facebook-Umfrage (2026-06-23)
**Beschreibung:** Automatisch scrollende Cuesheets laufen selten wirklich synchron zur Musik. Lösung: der Caller setzt **Zwischen-Sync-Punkte**, die eine Textzeile fest an eine Liedposition koppeln. Zwischen zwei Ankern interpoliert der Scroll, an den Ankern wird wieder eingefangen — so bleibt die Anzeige über den ganzen Song synchron.
**Abgrenzung/Bezug:** Erweitert das Cuesheet-Widget (BL-150) um Sync-Anker; eng verwandt mit BL-109 (BPM-synchronisiertes Abschnitts-Springen in Lyrics) — die dort entwickelte Anker-/Positions-Logik sollte wiederverwendet statt dupliziert werden. Auch relevant für Auto-Scroll allgemein (BL-007).
**Verwandt:** BL-150 (Cuesheet-Widget), BL-109 (Lyrics-Sync), BL-007 (Auto-Scroll).
**Aufwand:** Mittel
**Lösung (2026-06-25):** Im bestehenden Lyrics-Widget umgesetzt (kein separates Fenster).
- **Sync-Modus** über neuen Toolbar-Button „Sync". Während das Lied läuft, klickt der Caller in die Textzeile, an der die Musik gerade steht → Anker (Songzeit ↔ Block-Index). Mehrere Anker → `update_scroll()` interpoliert stückweise linear zwischen ihnen statt stumpf linear; Randsegmente clampen zu impliziten Endpunkten (Anfang→0, Ende→Max), keine Extrapolation. Ohne Anker bleibt das alte lineare Verhalten unverändert.
- **Inline-Marker:** Im Sync-Modus werden die Zeitstempel (`⟨m:ss⟩`) mit Hintergrundfarbe in die Ankerzeilen eingeblendet — nicht persistent, nur Anzeige.
- **Bearbeiten:** Rechtsklick auf Marker → Zeit per mm:ss-Eingabe setzen, „Zeit = aktuelle Wiedergabe" (neu fangen), in andere Textzeile verschieben, löschen.
- **Speicherung:** `song_properties`-Keys `lyric_sync_m<musikSlot>_l<lyricSlot>_<index>` = `"<sek>|<block>"`. Eindeutig pro (Musik-Variante × Lyric-Variante), weil MP3-Intro-Länge und Lyric-Format (PDF≠HTML) die Punkte verschieben. Beim Laden einer Variante ohne eigene Punkte, wenn eine andere Variante welche hat: Angebot, sie zu kopieren.
- **Granularität:** Zeilen-/Block-genau (stabil gegen Zoom/Auto-Size; Pixel wären instabil). Anker werden im Scroll-Hotpath aus dem Cache gelesen (kein DB-Zugriff pro Tick → Audio-Priorität gewahrt).

### BL-163: Potential-Fenster — Reiter „Ohne Liedpunkte" & „Ohne SyncPunkte"
**Status:** ERLEDIGT (2026-06-30, v0.112; UI-Test bestätigt 2026-07-18)
**Quelle:** David (2026-06-30)
**Beschreibung:** Zwei neue Reiter im Potential-Fenster, direkt hinter „Ohne Lyrics", die den Caller-Workflow nach dem Lyrics-Import fortführen (Lyrics → Liedpunkte → Sync-Punkte):
- **„Ohne Liedpunkte":** Singing Calls (mit Lyrics) ohne gesetzten Liedstart UND -ende. Datenquelle: song_properties `singing_start_m<slot>` / `singing_end_m<slot>` (ein Song gilt versorgt, wenn für irgendeine Variante BEIDE existieren).
- **„Ohne SyncPunkte":** Singing Calls (mit Lyrics) ohne einen einzigen Sync-Anker (song_properties Prefix `lyric_sync_`).
- **Doppelklick:** lädt den Song, holt das Lyrics-Fenster nach vorn und setzt **Maus + Fokus auf den Sync-Button** (neue Navigation `on_navigate_sync` → `_on_potential_navigate_sync`).
- Aussehen/Funktion analog „Ohne Lyrics": Anzahl-Badge im Reiter, „Ignorieren"-Funktion.
**Designentscheidung:** Bewusst nur Songs MIT Lyrics gelistet — ohne Lyrics lassen sich Lied-/Sync-Punkte gar nicht setzen; solche Songs stehen weiterhin unter „Ohne Lyrics" (saubere Pipeline statt Doppel-Listung).
**Umsetzung:** `song_db.py` (`potential_singing_no_song_points`, `potential_singing_no_sync_points`, beide in `potential_count`-Map); `main.py` `PotentialWidget` (`_CHECKS`, `_load_check`, Doppelklick-Routing, `on_navigate_sync`); `translations.json` 4 Keys DE/EN/JA. An Test-DB verifiziert (292 Singing+Lyrics → 288 ohne Liedpunkte, 287 ohne Sync).
**Nebenbefund (geklärt, kein Bug):** Tempo-Änderung invalidiert Sync-/Liedpunkte NICHT — Position (`get_position_seconds`) und Dauer (`get_original_duration`) liegen beide in Quell-Zeit (tempo-invariant). In der Praxis bei +23 % bestätigt.
**Mitgeliefert (v0.112):** Win11-Theme — SpinBox-Auf/Ab-Buttons dauerhaft sichtbar (vorher nur bei Hover; weißer Pfeil war auf weißem Feld unsichtbar). Default = `button_hover`, Hover = `button_pressed`. Skin in `1_Source` + `2_Test` gespiegelt.
**Verwandt:** BL-160 (Sync-Punkte), BL-161/Auto-Sync (Liedstart/-ende), Potential-Dashboard (Tab „Ohne Lyrics").
**Aufwand:** Mittel (umgesetzt)

### BL-164: Patter-Länge automatisch treffen — verkürzter Loop-Durchlauf in 64-Beat-Schritten
**Status:** ERLEDIGT (2026-07-18; implementiert 2026-07-04) — verifiziert am Beispiel „10-20 Hoedown": Ziel 5,0 min → geliefert 4:53 (−7 s).
**Nicht umgesetzt (bewusst, ggf. später als eigener Eintrag):** Null-Klick-Automatik (Cut automatisch aus Programm-Ziellänge beim Laden, ohne Dialog).
**Umsetzung (v0.113+):** `calc_loop_cut()` + `LOOP_CUT_TOLERANCE_S` (main.py, neben `calc_loop_count`); 4. Radio-Option im Loop-Count-Dialog (vorselektiert, nur wenn keine ganzzahlige Variante in Toleranz; Raster 64/32 Beats, der nähere gewinnt); `PlaylistEntry.loop_cut_beats` + `loop_target_min` (nur Speicher/Playlist-Datei als `N:CUT`-Token, NICHT in DB — Ziellänge variiert pro Lokation, Entscheidung David); Engine `set_loop_cut_seconds()` + verkürzter ERSTER Durchlauf im Feeder (`audio_engine._feed_stretcher`, dreifach gegated: cut>0, done==0, target>=2 — Pfad ohne Cut byte-identisch zu vorher; Crossfade hängt an `effective_loop_out` und greift automatisch am vorgezogenen Punkt); Dialog→Engine-Sofort-Sync via `_apply_loop_settings_to_engine()` (Fix: vorher griff die Wahl erst beim nächsten Song-Laden); `✂`-Indikator in Playlist-Loop-Spalte; Dauer-Spalte rechnet Cut ein; Dialog stellt letzte Wahl wieder her.
**Nebenbefund (offen, kosmetisch):** Positions-Slider hüpft beim Überqueren von `loop_in` (~0:30) einmal minimal rückwärts — Anzeige-Logik, unabhängig vom Cut, vermutlich auch beim alten Endlos-Loop.
**Ursprünglicher Planungsstand (vor Umsetzung):**
**Quelle:** David (2026-06-30), aus Diskussion; ursprünglicher Wunsch ein User (vgl. BL-053, BL-100)
**Bezug:** BL-042 (Loop-Count, Grundfunktion), BL-053 (Patter-Länge pro Gruppe/Abend — erledigt), BL-085 (Patternlänge aus Tanzprogramm), BL-099 (Tanzprogramm pro Song), BL-084 (Lokation mit Tanzprogramm), BL-025 (Loop-Crossfade — trägt die Schnittkante), BL-026 (Loop-Offset). **Nimmt das Anliegen von BL-100 (ENTFÄLLT) neu auf** — ohne den verworfenen Ansatz „Loop-End verschieben".

**Problem:** Ein einzelner Loop N× wiederholt lässt die Gesamtdauer nur in Stufen von *einer Loop-Länge* zu. Ziel: **vollautomatisch auf ±~20 s an die gewünschte Patter-Länge** (ein User: „möglichst wenig kümmern", entspannt bei Abwechslung).

**Datenlage (analysiert 2026-07-03 an David's Test-DB, 173 Pattern-Songs mit Loop):** Die Loops sind groß, nicht klein — das kippt die ursprüngliche Annahme (~30-s-Loops, N=10–17):
- Songlänge Median **223 s**, Loop-Länge Median **150 s (320 Beats)**, **Loop/Song-Verhältnis Median 0,67** — der Loop *ist* der tanzbare Mittelteil.
- Aufbau typisch: Intro ~30 s (`loop_in`) → Loop-Body ~150 s → Tail ~41 s.
- Wiederholungen real nur **N≈2–4** (7 min → 2–3×, 12 min → ~4×). Damit ist die N-Granularität = eine volle Loop-Länge (~150 s) → riesiges Loch; ein Loop allein trifft ±20 s nur bei ~1 %.

**Finales Konzept (on-the-fly, kein Loop-Finder nötig):** Der große Loop `LI → LO` bleibt exakt wie heute. Für die Feinjustierung wird **ein** Durchlauf um `k·64` Beats verkürzt — der Rücksprung erfolgt schon bei `LO − k·64` zurück nach `LI` (das bewährte, unveränderte Rücksprung-Ziel):
```
… LI → LO → LI          (volle Durchläufe, identisch zu heute)
   LI → (LO−k·64) → LI   (der eine gekürzte Rücksprung)
   LI → LO → Tail        (Ausstiegs-Kante LO→Tail bleibt unangetastet — der bewährte Übergang)
```
- **Nur die Rücksprung-Kante wandert**, die musikalisch heikelste **Ausstiegs-Kante `LO→Tail` nie**. Ziel des Rücksprungs bleibt immer `LI`.
- **64 Beats = ganze Phrasen** → Downbeat/Rhythmus bleibt sauber; die harmonische Kante glättet der **vorhandene Crossfade** (BL-025). Bewusst hingenommen, dass musikalisch nicht immer alles exakt gleich ist (David).
- **On-the-fly:** gebraucht wird nur das **Beat-Grid** (liegt im `_beat_grid_cache`) für die Rasterpunkte `LO−64, LO−128, …` und ein `k` per Arithmetik. Kein `find_loop_candidates`-Lauf, kein Feature-Cache, keine Zusatz-Suche.

**Trefferquote (an den echten Daten gerechnet, ±20 s):**
- **64-Beat-Raster** (Fehler ≤ 32 Beats ≈ 15 s): **98 %** der Songs → Default.
- **32-Beat-Raster** (Fehler ≤ 16 Beats ≈ 7,5 s): **100 %** → Fallback für die letzten 2 %.
- **Ein einziger Cut reicht** bei 100 % für ±20 s. Abwechslungsregel („max 2× hintereinander") wird kaum gebraucht, weil ein 2,5-min-Block ohnehin nur 2–4× läuft; für mehr Abwechslung müsste man den Loop-*Body* unterteilen (die Songs haben keine zweite gleichwertige Stelle — der Loop ist der tanzbare Teil).

**Verworfene Zwischenstufe (Historie):** Ältere Idee war eine *separate kleine Zusatz-Schleife hinter `LO`* (`small_out = LO + k`) mit „Schnapp-Punkte"-Liste + Feature-Cache im Loop-Finder. Durch die Datenlage überflüssig: Der große Loop ist lang genug, dass die Feinjustierung ein Teilstück von *ihm selbst* ist → viel einfacher, on-the-fly, ohne Finder.

**Engine-Implikation:** Kein zweites Loop-Segment nötig. Nur: **ein Durchlauf bekommt einen temporär vorgezogenen Loop-Out** (`LO−k·64`). Sehr nah am bestehenden Loop-Code. Trotzdem Audio-Callback: Fallback sichern, State unter `self._lock`, `FEED_AHEAD_SECONDS` nicht antasten (eiserne Audio-Regel). Kleiner Rest-Haken: am `LO−k·64` fehlt die `loop_offset_ms`-Feinjustierung von `LO` — generischer Crossfade sollte reichen, an 1–2 Songs hörprüfen.

**GUI-Verortung (offen, zu entscheiden — 3 Ebenen):**
1. **Ziel-Patter-Länge (T):** existiert am Tanzprogramm (`_get_current_target_duration` → `target_duration_min`), pro Lokation indirekt über deren Programm. Optional: Lokations-Override (kleines Feld), falls gleiche Stufe / andere Clubdauer.
2. **Modus-Schalter „Endlos ↔ Auf Ziellänge":** naheliegend im `LoopWidget` (dock_loop, wo schon `chk_loop` „Loop aktiv" sitzt) — ein zweiter Zustand statt/neben Endlos. Wenn aktiv, greift die Berechnung beim Laden jedes Pattern-Songs automatisch.
3. **Anzeige + Override:** getroffene Länge im Player-`label_loop_count` (z. B. „≈ 7:12 / Ziel 7:00"); manuelles Feintuning im bestehenden `show_loop_count_dialog` (dort `k`/N überschreibbar). Default vollautomatisch (ein User), Override für Power-User.

**Aufwand:** Mittel — Cut-Arithmetik + „ein Durchlauf mit vorgezogenem Loop-Out" in der Engine + GUI-Schalter/Anzeige. Deutlich kleiner als die verworfene Finder-Variante.

---

## Nutzerfeedback (David, 2026-07-18)

### BL-166: STRG + Mausrad zum Zoomen in allen Widgets mit Zoom-Funktion
**Status:** ERLEDIGT (2026-07-18)
**Quelle:** David, 2026-07-18
**Beschreibung:** Ueberall, wo es bereits eine Zoom-Funktion zum Vergroessern/Verkleinern der Anzeige gibt, soll zusaetzlich `STRG + Mausrad` zoomen.
**Umsetzung:** Neues Modul `zoom_wheel.py` mit `install_ctrl_wheel_zoom(target, zoom_in, zoom_out)` — Event-Filter auf Widget *und* Viewport (QAbstractScrollArea stellt Wheel-Events am Viewport zu). Ruft ausschliesslich die bestehenden Zoom-Callables auf; Schrittweite, Grenzen und Label bleiben Sache des Widgets. Teil-Rasten werden aufaddiert (stufenlose Raeder/Touchpads). Event wird verbraucht, damit weder zusaetzlich gescrollt noch der eingebaute QTextBrowser-Zoom ausgeloest wird.
**Fundstellen (6):** SequencesWidget (Tabelle), LyricsWidget (QTextBrowser), NotesWidget (beide Listen), ClassDesigner (Figurenliste), Evening Planner (Kurven-Canvas), Beat-Snap-Dialog (beide Wellenformen).
**Aufwand:** Klein bis Mittel (abhaengig von der Anzahl der Fundstellen)

### BL-170: Sortierung „gestapelter Zufall" (gewichtete Zufallsauswahl)
**Status:** ERLEDIGT (2026-07-18)
**Quelle:** David, 2026-07-18
**Beschreibung:** Echte Zufallssortierung — bevorzugt aber als *gewichteter* Zufall (Roulette-Wheel-Selection): Die Scores aller Lieder werden summiert, eine Zufallszahl innerhalb dieses Summenbereichs gezogen und von vorne kumulativ aufaddiert, bis die Zahl erreicht ist; dieses Lied kommt dran.
**Wirkung:** Lieder mit besserer Qualitaet und groesserem Abstand (Tage seit zuletzt gespielt) kommen wahrscheinlicher an die Reihe — schlecht bewertete Lieder behalten aber eine Restchance.
**Score-Quelle:** der bestehende Empfehlungs-Score (`quality x Tage-seit-gespielt`).
**Umsetzung:** Zwei neue Modi in `SongFilterBar` — `SORT_RANDOM` (Gleichverteilung) und `SORT_WEIGHTED_RANDOM`. Beide sitzen in `filter_and_sort()`, dadurch greifen sie in Songliste, Playlist-Manager UND beim Magischen Button (`_on_auto_fill` konsumiert dieselbe Funktion von oben nach unten).
**Algorithmus:** `_weighted_random_order()` nach Efraimidis/Spirakis — Schluessel `-ln(u)/w`, einmal sortieren. Verteilungsgleich zum von Hand beschriebenen kumulativen Verfahren (an 40 000 Ziehungen gegen eine Referenzimplementierung geprueft), aber O(n log n) statt O(n^2).
**Gewicht:** `Score + 1`, damit Score 0 nicht Wahrscheinlichkeit 0 bedeutet. Unbewertete Songs (`quality = 0` = "nicht bewertet", nicht "schlecht") rechnen HIER mit `_UNRATED_QUALITY = 5` — ohne das kamen sie nie dran und konnten deshalb auch nie bewertet werden (gemessen: Median-Platz 524 von 526). Heute gespielte Songs behalten bewusst Gewicht 1.
**Stabilitaet:** Ziehung pro Song in `self._sort_draw` gecacht, damit Tippen im Suchfeld nicht neu wuerfelt. Neu gemischt beim Programmstart und beim Umschalten auf einen der beiden Modi.
**Perf-Marken:** `[Perf] SongFilterBar.sort_random` / `sort_weighted_random`. Gemessen bei 526 Songs: 1 ms fuer den gesamten `filter_and_sort`; die Sortierung selbst skaliert auf 3,7 ms bei 10 000 Songs.
**NICHT betroffen:** Der Evening Planner hat mit `SongScorer.candidates` ein eigenes Auswahlsystem (Ziel-ERR + Ungarischer Algorithmus) und haengt nicht an der Sortier-Auswahl.
**Ergaenzung:** Beim „Magischer Button"-Fuellen soll diese Sortierung genutzt werden, wenn sie ausgewaehlt ist.
**Aufwand:** Mittel

### BL-172: „Mach alles SCHÖN"-Button im Potential-Widget
**Status:** ERLEDIGT (0.127)
**Quelle:** David, 2026-07-18
**Beschreibung:** Im Potential-Widget gibt es bereits mehrere Bulk-Funktionen, die Luecken fuellen. Ganz unten auf der Home-Seite von Potential soll ein Button alle diese „Heilungsfunktionen" nacheinander ausfuehren.
**Umsetzung:** Vorab Warnung, dass der Lauf sehr lange dauern kann. **Keine** Zeitabschaetzung. Feedback ueber einen Fortschrittsbalken, der halbwegs alle Aspekte mit einem ToDo abbildet — bewusst nicht-linear, weil die Einzelaktionen unterschiedlich lange brauchen.
**Loesung (0.127):** Button „✨ Mach alles schön" unten auf der Uebersichtsseite. Auswahl-Dialog (`_BeautifyDialog`) mit Aktion + gefundener Fallzahl; auffuellende Aktionen vorausgewaehlt, die zwei destruktiven (leere Lokationen, verwaiste Historie) bewusst nicht angehakt, 0-Faelle deaktiviert. Orchestrator (`_beautify_run`/`_beautify_next`) verkettet die bestehenden Bulk-Worker (BPM, Auto-Loop, BeatSnap, Singing-Start, Sync-Punkte) sequenziell ohne Einzel-Rueckfragen; nur die offenen Faelle, nicht die „ALLE"-Varianten. Nicht-lineare ToDo-Fortschrittsanzeige (`_BeautifyProgressDialog`), abbrechbar, Abschluss-Report pro Aktion. Meta/Quality-Filler und Loop-Optimieren bewusst ausgeschlossen (interaktiv bzw. reine ALLE-Variante).
**Aufwand:** Mittel

## Nutzerfeedback (ein User, 2026-07-22)

### BL-177: Zwei neue Rules für die Pausen-/Break-Funktion
**Status:** ERLEDIGT
**Quelle:** ein User
**Beschreibung:** Zwei neue Rule-Aktionen rund um die Break-/Pausenfunktion anlegen:
- **„Start Break"** — startet die Pause.
- **„Start Break with last Song"** — startet die Pause mit dem letzten Song.

Bei beiden soll die **Pausendauer als Parameter** mitgegeben werden können (wie lange die Pause dauert).
**Lösung:** Zwei neue Actions `start_break` und `start_break_last_song` (Gruppe „Layout & Docks", neben `break_toggle`). Öffnen die Pausen-Uhr und starten den Countdown; die zweite spielt zusätzlich den letzten Song als Wartemusik (nutzt denselben Pfad wie der Play-Last-Button). Parameter `minutes` (0–60, Default 5); `minutes = 0` → Standard-Pausendauer der aktuellen Lokation. Neue Public-Methoden `BreakWidget.start_break()` / `start_break_with_last_song()`.
**Aufwand:** Mittel


---

## Eigene Ideen / Erweiterungen (nachtraeglich ausgelagert)

### BL-165: Singing-Body-Erkennung per Ausgleichungsrechnung global optimieren
**Status:** ENTFAELLT / ERLEDIGT (2026-07-06)
**Quelle:** David (2026-07-06)
**Ausgelagert am:** 2026-07-23

**Urspruengliche Idee:** Statt Einzelfall-Tuning der Singing-Body-Erkennung (`singing_body_detect.py`) eine **Ausgleichungsrechnung (Least-Squares-Adjustment)** ueber die ~50 Gehoer-Marken rechnen: funktionales Modell (Parameter `calib_offset`, Kamm-Gewichte `novz`/`crashz`/`stepz`/`bassz`, Novelty-Fenster `K`, Downbeat-Snap) → Residuen (Detektor-Start minus Ohr-Marke in Beats) → global beste Parameter per kleinster Fehlerquadratsumme. Ausloeser war der Fehlerfall *Achy Breaky Heart* (+3,1 s / ~6-7 Beats zu spaet).

**Ergebnis — Ausgleichungs-Ansatz WIDERLEGT (noch am 2026-07-06 durchgezogen, Davids Verdacht bestaetigt):**
Die Fehler zerfallen in drei Klassen:
1. konstanter Bias ≈ −2,6 Beats → ein **Median-Offset**, kein L2-Problem
2. diskrete, **bidirektionale Fehl-Locks** (±8/13/21/27/36 Beats bei 11 Songs) → falsche Phase UND Sektion, keine sauberen ±64-Aliase
3. ±1 Beat Restrauschen

Gauss-Markov / Least-Squares ist nur auf Klasse (3) legitim — und die ist ohnehin schon klein. Es gibt nichts Kontinuierliches zu schaetzen; das Problem ist **diskrete Mehrdeutigkeit**, kein Rausch-Ausgleich. Auch die begleitende Content-Hypothese (Abschnitts-Inhalte vergleichen: Chroma, Timbre, rohe RMS-Huellkurve, Key-Change) wurde in ALLEN Varianten falsifiziert — keine schlaegt netto den bestehenden „8-Zinken-Kamm".

**Was stattdessen umgesetzt wurde (das Positive):** Ein **Konfidenz-Gate ueber Methoden-Uneinigkeit** — `disagree` = Spannweite der Picks aus {Kamm, coh_tim, contrast_tim}. Alle 11 Fehl-Locks hatten `disagree ≥ 19`, keiner darunter → saubere Trennlinie. Ergebnis: **64 % der Songs (41/64) automatisch und fehlerfrei**, alle 11 Ausreisser sauber geflaggt. In die App integriert (`AMBIGUITY_THRESHOLD=18`, Warndialog „Mehrdeutige Stelle … bitte pruefen"). Details im Experiment-Log `tools/experiment_out/content_run1..4_*.txt`.

**Aufwand (war veranschlagt):** Gross — hat sich als nicht sinnvoll erwiesen (falsches Werkzeug fuer ein diskretes Problem).
---

## Nutzerfeedback (ein User, 2026-05-02) — nachtraeglich ausgelagert

### BL-109: Lyrics — BPM-synchronisiertes Abschnitts-Springen (Singing Call Struktur)
**Status:** ERLEDIGT (in anderer BL-Idee realisiert)
**Quelle:** ein User (2026-05-02)
**Ausgelagert am:** 2026-07-23

**Ergebnis (David 2026-07-23):** Diese Aufgabe wurde bereits im Rahmen einer anderen BL-Idee (Auto-Sync / Singing-Call-Abschnittserkennung) umgesetzt. Die dafuer geplante Infrastruktur existiert im Code: Abschnitts-Parser mit konfigurierbaren Keyword-Listen (`singing_sections.py`, `DEFAULT_SECTIONS`/`classify_heading`), persistierte Abschnitt→Zeilen-Zuordnung pro Song+Slot (`_lyric_sections`, `lyric_sections_l{slot}_{name}` in `song_properties`), gespeicherte `singing_start_m{slot}`/`singing_end_m{slot}` + `base_bpm`, sowie die BPM→Beat-Rechnung im laufenden Song. Kein eigener Umsetzungsbedarf mehr.

**Urspruengliche Idee (zur Nachvollziehbarkeit):** Der Auto-Scroll sollte nicht mehr kontinuierlich laufen, sondern an die starre Singing-Call-Struktur (Intro·Opener·Figure·Figure·MiddleBreak·Figure·Figure·Closer·Tag) koppeln. Da jeder Abschnitt exakt 64 Beats dauert (`64/BPM*60`) und die BPM bekannt ist, laesst sich berechnen, wann welcher Abschnitt beginnt; die App springt zur passenden Textzeile (Abschnitts-Keywords werden im Text gesucht). Kein Wort-fuer-Wort-Karaoke — nur Sprung zum Abschnittsanfang, Rest per Autoscroll. Intro-Laenge + Keyword-Overrides waren pro Song konfigurierbar geplant (Bezug BL-094/BL-118).

**Bezug:** BL-094 (Song-Properties), BL-095 (Auto-BPM), BL-118 (Song-Properties als Speicher fuer Lyrics-Konfig — pruefen, ob damit ebenfalls hinfaellig).
**Aufwand (war veranschlagt):** Mittel
---

## Eigene Ideen / Erweiterungen (nachtraeglich ausgelagert)

### BL-118: Song-Properties als Speicher fuer Lyrics-Konfiguration (Erweiterung BL-094)
**Status:** ERLEDIGT / ENTFAELLT (durch andere Loesung gegenstandslos)
**Quelle:** David (2026-05-11)
**Ausgelagert am:** 2026-07-23

**Warum archiviert (David 2026-07-23):** BL-118 war ausschliesslich Zulieferer fuer BL-109 (BPM-synchronisiertes Abschnitts-Springen). BL-109 wurde auf einem ANDEREN Weg realisiert (siehe BL-109 im Archiv) — damit entfaellt der Zweck von BL-118. Die urspruenglich geplanten Keys wurden nie angelegt: `SONG_PROPERTY_KEYS` in `song_db.py` enthaelt (Stand 2026-07-23) nur `original_artist` + `release_year`, KEINE `lyrics_intro_duration` / `lyrics_section_keywords`.

**Wie es STATTDESSEN geloest wurde (der Grund, warum BL-118 unnoetig ist):**
BL-118 wollte pro Song *Rohzutaten zum Nachrechnen* speichern — Intro-Laenge + Keyword-Overrides — damit die App zur Laufzeit erst die Abschnitts-Keywords im Text sucht und dann per BPM die Sprungzeitpunkte berechnet. Die tatsaechliche Loesung dreht das um und speichert direkt das FERTIGE Ergebnis:
- **Abschnitt→Zeilen-Zuordnung wird einmalig ermittelt und persistiert**, nicht bei jedem Abspielen neu aus Keywords abgeleitet. Parser `singing_sections.py` (`DEFAULT_SECTIONS`/`classify_heading`) liefert die Abschnitte; das Ergebnis liegt als `_lyric_sections` (dict Abschnitt→(Zeile0,Zeile1)) und wird als `song_properties`-Keys `lyric_sections_l{slot}_{name}` gespeichert (pro Musik-Variante/Slot).
- **Zeit-Anker kommen aus echten Marken statt aus geratener Intro-Laenge:** `singing_start_m{slot}` / `singing_end_m{slot}` (aus Auto-Sync / manuellem Sync) + `base_bpm`. Body ist starr 448 Beats → die Abschnittszeitpunkte ergeben sich aus Start + BPM (bzw. Start..Ende gesiebtelt).
- **Keyword-Overrides pro Song sind damit ueberfluessig:** Weil die konkreten Zeilenbereiche je Song gespeichert werden, muss die App nicht mehr wissen, ob ein Song `Figure` oder `Fig1` verwendet — die Zuordnung wurde beim Erstellen schon aufgeloest. Global konfigurierbare Keyword-Listen (Datei-basiert, `load_sections`/`save_sections`) bleiben als Wissensbasis bestehen; ein per-Song-JSON-Override in `song_properties` wird nicht gebraucht.

**Fazit:** Der generische Key/Value-Ansatz von BL-094 wird fuer die Lyrics-Sektionen genutzt — aber mit dem berechneten Endergebnis (`lyric_sections_*`) statt mit den Roh-Parametern (`lyrics_intro_duration` / `lyrics_section_keywords`). Damit ist BL-118 in seiner urspruenglichen Form erledigt.

**Bezug:** BL-094 (song_properties — genutzt, nur mit anderen Keys), BL-109 (archiviert), BL-095 (Auto-BPM), BL-161 (Text→Teile-Zuordnung).
**Aufwand (war veranschlagt):** Klein
---

## Facebook-Umfrage (2026-06-23) — nachtraeglich ausgelagert

### BL-158: Intro-/Outro-Beat-Anzeige mit Beat-Countdown
**Status:** ERLEDIGT (Kernnutzen gedeckt; Outro-Countdown + statische Beatzahl bewusst verworfen)
**Quelle:** Facebook-Umfrage (2026-06-23)
**Ausgelagert am:** 2026-07-23

**Warum erledigt (David 2026-07-23):** Seit den SyncPoints liefern Start- UND Endpunkt des Liedes (manuell oder auto erkannt) die noetige Datengrundlage; der Intro-Countdown bis zum Gesangseinsatz ist als Feature vorhanden. Der Kernnutzen der Umfrage-Idee (Caller sieht seinen Vorlauf) ist damit gedeckt.

**Was umgesetzt ist (Phase 2, Intro-Seite):** Waehrend des Abspielens zeigt das Vollbild-`_CountdownOverlay` (`main.py`, Klasse `_CountdownOverlay` + `_update_countdown`) einen live mitlaufenden **Beat-Countdown bis `singing_start`** — also herunterzaehlen bis zum Gesangseinsatz. Grundlage: `singing_start_m{slot}` (aus Auto-Sync oder manuellem Sync) + `base_bpm`, inkl. Tempo-Korrektur (`spin_tempo`). Schaltbar per INI `display/countdown_enabled` (Default true). Die letzten 2 Beats bleiben bewusst still (kein Overlay).

**Bewusst NICHT umgesetzt / verworfen (David-Entscheidung 2026-07-23):**
- **Outro-Countdown:** Das Overlay endet bei `pos >= singing_start`; ein Countdown fuers Outro (von `singing_end` bis Songende) wird nicht gebaut, obwohl `singing_end` als Datum vorlaege.
- **Statische Beat-*Anzahl*-Anzeige (Phase 1):** Eine vorab-Anzeige „Intro = X Beats / Outro = Y Beats" als Zahl wird nicht gebaut — der live Countdown deckt den praktischen Bedarf.

**Verwandt:** BL-128 (Miniatur-Abspielfortschritt mit Sektionen), BL-042 (Loop-Count), BL-076 (Pause-Countdown), BL-095/BL-026 (BPM/Beat-Grid).
**Aufwand (war veranschlagt):** Mittel
---

## Nutzerfeedback (David, 2026-07-18) — nachtraeglich ausgelagert

### BL-171: Lyrics-Sync-Modus — Buttons für Songstart ±1 Sekunde
**Status:** ERLEDIGT (v0.128, 2026-07-23; smoke-getestet von David)
**Quelle:** David, 2026-07-18
**Ausgelagert am:** 2026-07-23

**Beschreibung:** Bei aktivem Sync-Modus im Lyrics-Fenster links neben den Zoom-Buttons zwei zusaetzliche Buttons `−1 s` / `+1 s`, die den Songstart nach vorne/hinten verschieben. Bedingung war: dieselbe Funktion wie das bestehende Rechtsklick-Kontextmenue („Alle verschieben") ansprechen — keine Redundanz.

**Umsetzung (v0.128):**
- Die bisher inline im Kontextmenue liegende Verschiebe-Logik wurde in die wiederverwendbare Methode `LyricsWidget._shift_all_anchors(delta)` extrahiert (main.py). Sie verschiebt alle `_sync_anchors` um delta (nie < 0), ruft `_shift_song_end(delta)` und `_persist_sync_anchors()`; letzteres koppelt via `_couple_song_start_to_anchor()` den Songstart an den fruehesten Anker — Start, alle SyncPoints und Ende wandern gemeinsam.
- Kontextmenue-Zweig `shift_all` ruft jetzt dieselbe Methode → keine Redundanz (Bedingung erfuellt).
- Zwei neue Toolbar-Buttons `_btn_sync_shift_earlier` / `_btn_sync_shift_later` links neben den Zoom-Buttons, rufen `_shift_all_anchors(∓1.0)`. Sichtbarkeit an den Sync-Modus gekoppelt (Toggle in `_on_sync_toggled`, nur sichtbar wenn `_sync_mode` aktiv — „Sync Mode 2" war ein Tippfehler, gemeint war schlicht der aktive Sync-Modus).
- i18n additiv (de/en/ja): `btn_sync_shift_earlier`, `btn_sync_shift_later`, `tooltip_sync_shift_earlier`, `tooltip_sync_shift_later`.
- Backups: `_fallback/{main,translations}.*.bak_bl171_shiftbuttons_20260723`.

**Nebenbefund (nicht angefasst):** Im Code existieren aeltere `# BL-171`-Kommentare, die sich auf den Abschnittsstreifen (Section-Overlay) beziehen, nicht auf diese Buttons — Alt-Fehletikettierung. Bei Gelegenheit umbenennen.

**Aufwand (war veranschlagt):** Klein

### BL-173: Dynamic Lyrics — Sequenzen on the fly in die Lyrics einblenden
**Status:** ERLEDIGT (v0.132, 2026-07-29; gebaut + von David iterativ getestet)
**Quelle:** David, 2026-07-18
**Ausgelagert am:** 2026-07-29

**Ursprüngliche Idee:** Lyrics liegen pro Lied vor, getrennt davon die Sequenzen. In die Schablone der Lyrics-Datei sollen auf Wunsch die Sequenzen aus dem Sequenz-Widget eingeblendet und die dort vorhandenen Figuren-Abschnitte ueberblendet werden. Bedingung: Lyric-Dateien werden **nicht** veraendert (nur Laufzeit-Anzeige). Ausblick: Choreo-Themen eines ganzen Abends festlegen (Schnittstelle Evening Planner).

**Umsetzung (v0.132):**
- Toggle „Dynamic Lyrics" im Lyric-Fenster, rechts neben den Auto-Buttons. Ersetzt den Text der Figuren-Abschnitte (figure1..4) temporaer durch die im Sequence-View gezeigte Sequenz. Datei bleibt unberuehrt: Dokument-Klon aus dem PRISTINE Original (kein Reload), Revert stellt Original wieder her.
- **Sequence-View ist Quelle der Wahrheit**, das Lyric-Feld spiegelt. Bei Option 2 blaettert Callers Caddy an jeder Figuren-Teil-Grenze im Sequence-View weiter (`advance()`), das Lyric folgt via `refresh_dynamic_from_sequence`. Nutzer-Navigation im Sequence-View (prev/next) wird ebenfalls gespiegelt (Vorbereitung fuers spaetere Remote-Blaettern durch den Nutzer).
- Zwei Modi (Einmal-Dialog beim ersten Aktivieren): 1 = dieselbe Sequenz in alle 4 Figuren, 2 = ab aktueller Sequenz durchblaettern (Stopp nach dem letzten Figuren-Teil). Figuren-Teil-Startzeiten aus den SyncPoints abgeleitet (Anker auf Block-Startzeile == key[0]; Ende-Anker ignoriert). Blaettern + Render deferred via `QTimer.singleShot` (audio-sicher, TIC-0025).
- SyncPoints bleiben gueltig und werden auf die neue Zeilenaufteilung nachgefuehrt (Timing identisch). Die „FIGURE"-Ueberschrift (Blockkopf l0) bleibt stehen — ersetzt wird erst ab der Folgezeile (l0+1..l1). Eingefuegter Text ohne Hintergrund-/Highlight-Marker (`clearBackground`).
- Persistenz: An/Aus-Wunsch (`lyrics/dynamic_enabled`) + Modus (`lyrics/dynamic_mode`) in der App-INI; beim Start wiederhergestellt und beim ersten passenden Song angewandt. Auch in Settings/Lyrics einstellbar (Checkbox + Combobox), vollstaendig i18n (de/en/ja). Dynamic bleibt ueber Songwechsel aktiv.
- Gating: Button ausgegraut ohne Lyric / SyncPoints / Figuren / Sequenz und im Sync-/Edit-Modus (Tooltip nennt Grund).

**Offen / v2:** Zoom-Aenderung mitten in Dynamic geht beim naechsten Teilwechsel verloren; rein manueller (nicht-Auto) Sync kann <4 Figuren-Teile liefern (degradiert sauber); Opener/Middle/Closer bewusst NICHT getauscht; Remote-Blaettern durch den Nutzer; Anbindung Evening Planner.

**Abhaengigkeit (war):** BL-174 (Sequenzen-Historie) — offen.
**Aufwand (war veranschlagt):** Gross

---

### BL-181: Zwei neue Rule-Aktionen — Sequenz-Type umstellen + Song laden
**Status:** ERLEDIGT (v0.133, 2026-08-16; gebaut + von David getestet)
**Quelle:** David (2026-08-16)
**Ausgelagert am:** 2026-08-16

**Idee:** Zwei neue Rule-Aktionen. A) Sequenz-Type umschalten (Parameter = Ziel-Type), damit beim Singing Call die Singing-Call-Figuren und beim Patter die Module/Get-Outs erscheinen. B) „Song laden" mit Parametern Type (Singing/Patter) + Sortierung; deterministische Sortierungen wie Empfehlung liefern immer den Besten, Zufallssortierungen wie Balanced Roulette jedes Mal einen anderen.

**Umsetzung (v0.133):**
- **A** `sequence_set_type` (Gruppe „Sequence View"): Parameter `seq_type` als Dropdown der vorhandenen DB-Typwerte (`get_sequence_type_values`, neuer Rule-Param-Typ `seqtype_choice` in `rule_widget.py` + Provider `seqtype_names_provider`). Handler `_rule_sequence_set_type` ruft `SequencesWidget.set_type_filter(text)` → schaltet das Type-Dropdown um, Tabelle lädt neu. Unbekannter Typ → Statusbar-Hinweis, Filter unverändert.
- **B** `load_song` (Gruppe **„Transport"**, nach Nutzer-Feedback von „Workflow" umgehängt): Parameter `type` (Singing/Patter) + `sort` (voller Songlisten-Satz: Recommendation, Weighted Random/Balanced Roulette, Random, Quality, Last Played, Alphabetical, Date Added). Handler `_rule_load_song` filtert Songs nach Typ, wählt per Sortierung EINEN Song (Zufallsmodi ziehen bei jedem Aufruf frisch → variieren; Recommendation deterministisch → immer der Beste), lädt ihn per `_on_song_selected` (cue, **kein Autoplay**) und selektiert ihn in der Liste. Score-Kontext (last_played_map, start_date) 1:1 aus der Songliste.
- **Bugfix bei der Integration:** `_on_song_selected` bekam ein `offer_copy`-Flag (Default True für manuelle Klicks); die Regel lädt mit `offer_copy=False`, damit bei Singing kein interaktiver Sync-Copy-Dialog den Live-Betrieb blockiert (vorher „hängte" der Load bis zum Wegklicken).
- Betroffene Dateien: `rule_definitions.py`, `rule_widget.py`, `main.py`, `translations.json` (2 Statusbar-Keys de/en/ja).

**Mit ausgeliefert in v0.133 (separate Wünsche, kein Teil von BL-181):**
- Neuer Trigger `manual` („Virtual Stream Deck (manual only)"): feuert nie automatisch, Rule läuft nur über das Stream Deck / manuellen Aufruf.
- Virtual Stream Deck: Fallback-Anfangsbuchstabe (ohne Icon) wieder groß und dynamisch mitwachsend — Fix via `font-size` im Stylesheet statt `setFont` (Qt ignoriert setFont bei gesetztem Widget-Stylesheet).

**Aufwand (war veranschlagt):** Mittel

---

_Ausgelagert am 2026-08-21 (nach Build v0.135)._

### BL-182: Sequenz-Navigation — Zufalls-Modus (Würfel-Button) springt zu beliebiger passender Sequenz
**Status:** ERLEDIGT (Kern v0.134; optionale Rule-Aktion v0.135; gebaut/getestet 2026-08-21)
**Quelle:** David (2026-08-20)
**Beschreibung:** Bei aktivem Random-Button (Würfel-Icon) ruft „Weiter" statt der nächsten Sequenz eine zufällig gewählte andere auf, die weiterhin den eingestellten Filteroptionen entspricht.

**Umgesetzte Variante (v0.134) — Ziehen ohne Zurücklegen, stille Erneuerung:**
- Würfel-Toggle (`🎲`, checkable) in der SequenzView-Navigationszeile links vom „▶"-Button, blauer Rahmen im aktiven Zustand.
- „Weiter" wählt per `random.choice` einen anderen Index aus der aktuell gefilterten `self._seq_ids`; `self._seen_ids` (In-Memory-Set) merkt Gezeigtes und überspringt es; Pool erschöpft → still erneuern (wichtig für Dynamic Lyrics BL-173).
- Greift auf allen „Weiter"-Wegen (`_on_next`, Pfeil rechts, `advance()`); „Zurück" bleibt sequenziell. Zustand nur pro Session, Uniform-Zufall. i18n: `seq_nav_random_tooltip`.

**Optionale Rule-Aktion nachgeliefert (v0.135):** `sequenceview_random` („Random Sequence", Gruppe Sequence View) löst den Zufallssprung unabhängig vom Würfel-Toggle aus (per Regel / Virtual Stream Deck / Fernbedienung) und nutzt dieselbe „ohne Zurücklegen"-Logik. Neue `SequenceViewWidget.sync_pool()` spiegelt vor dem Zug die aktuell gefilterten Sequenz-IDs frisch, damit die Aktion die eingestellten Filter garantiert einhält — auch wenn das Detail-Dock beim Filterwechsel nicht sichtbar war. Dateien: `rule_definitions.py`, `main.py`.
**Verwandt:** BL-089, BL-091, BL-108, BL-113/BL-170, BL-132, BL-173.
**Aufwand (war veranschlagt):** Klein bis Mittel

### BL-178: Sessions als Unter-Element der Lokation (Wochentag/Zeit + Auto-Erkennung + geteilte Historie)
**Status:** ERLEDIGT — Paket 1 + Paket 2 in v0.135 (2026-08-21, gebaut). Der ursprünglich mitgedachte laufende Session-Wechsel-Hinweis wurde als eigener Punkt **BL-183** ausgegliedert (aktives Backlog).
**Quelle:** David (2026-07-27)

**Architektur-Entscheidung (2026-08-21):** Ansatz umgedreht — eine „Session" ist KEINE eigene Unter-Entität mit Override-Logik, sondern eine **ganz normale eigene Lokation** (Notizen, Programm, Tempo, Tips, Pause, Termine bleiben sauber an der eigenen Lokation). Geteilt wird **nur die Song-Historie**, gerichtet auf eine „Senke" umgeleitet. Vermeidet Sonderlogik im Audio-nahen Apply-Pfad.

**Paket 1 (v0.135):** Mehrere Termin-Slots pro Lokation (Liste von Tripeln Wochentag/Start/Ende — verschiedene Zeiten je Tag) + Start-Auto-Erkennung (Vorschlag+Bestätigung, Toleranz 60 Min vor Start). JSON-Spalte `schedules` (Alt-Spalten `weekdays`/`time_from`/`time_to` nur noch Lese-Fallback), `Location.schedule_list`, `find_locations_for_datetime()`, dynamische Termin-Liste im `_LocationSettingsDialog`, `_auto_detect_location_on_startup()`. QTimeEdit-Skin-Styling in allen Themes ergänzt; Dialog-Größe per `adjustSize()`.

**Paket 2 (v0.135):** Shared History. Spalte `shared_history_with`, Auflösung `_effective_history_id` an `log_play` + 4 Lese-Methoden (`get_last_played_map`, `get_planner_candidates` → gilt auch für den Evening Planner, `get_setlist`, `get_setlist_dates`). `set_shared_history` (transitiv auf Senke, Alt-Historie per Rückfrage migriert + `rebuild_stats_cache`), `create_sub_location` (übernimmt Einstellungen inkl. Termine, teilt Historie), `get_history_group`, `delete_location` löst verwaiste Senken-Verweise auf. UI: „Historie teilen mit …" + „Trennen", „Neue Unter-Lokation", Gruppen-Liste im Settings-Dialog (Senke fett+unterstrichen, Klick = verlustfreier Wechsel), Listen-Kennzeichnung „→ Zielname".
**Aufwand (war veranschlagt):** Groß

---

### BL-185: Zusätzliche JumpPoints mit sprechender Caption (aufgezeichnete Stücke)
**Status:** ERLEDIGT (v0.142 — gebaut/gezippt 2026-09-01)
**Quelle:** David (2026-08-23)
**Umsetzung (2026-09-01, mit David):**
- Speicherort: `song_properties` (Extended Data), Keys `marker_<idx>_time`/`marker_<idx>_caption`; idx = stabile ID (max+1). DB-CRUD in `song_db.py`: `get_markers`/`add_marker`/`update_marker`/`delete_marker`. Anzeige nach Zeit sortiert. Zeit = Original-Sekunden (tempo-/WSOLA-unabhängig).
- Setzen: Button „Set Marker" im `LoopWidget` (Zeile 2:1:1 Find Loop | Beat Snap | Set Marker), Caption-Abfrage vorbefüllt mit Zeitstempel. Callback → MainWindow `_add_custom_marker`.
- Springen: Marker-Button-Zeile in `SongDataWidget` zwischen „Loop Offset" und „Lyrics file" (analog Varianten), Klick → `_jump_to_time` (Crossfade-Seek).
- Verwalten: Rechtsklick-Kontextmenü an den Song-Data-Buttons UND Reiter „Marker" im `SongPropertiesDialog`.
- Teil 2: andockbares `jump_markers_widget.py` (`JumpMarkersWidget`) — Start · Loop-Start · Loop-Ende · Ende (Loop-Punkte nur wenn Loop gesetzt; „Ende" später entfernt → nur Start fix) + Custom-Marken, gleichmäßig verteilt mit dynamischem Umbruch (geteiltes `button_grid.py`). Klick → Sprung. Refresh gedrosselt (jeder 5. Tick) nur bei sichtbarem Dock.
- i18n de/en/ja; Docks vor `_restore_layout()` erzeugt.

---

### BL-199 — Programm-Call-Übersichts-Widget (Calls abhaken, verblassend nach Themefarbe)
**Status:** ERLEDIGT (v0.142 — gebaut/gezippt 2026-09-01) — als Widget „To Call"
**Quelle:** David (2026-08-28)
**Umsetzung (2026-09-01, mit David):**
- Andockbares Widget `to_call_widget.py` (`ToCallWidget`): Calls als anklickbare Kacheln, Ziel-Seitenverhältnis 2:1 (`button_grid.compute_cells(target_ratio=2.0)`), Auto-Fit-Schriftgröße pro Kachel (mit 4px-Cache). Ungenutzt = kontrastreich (`button_text`/`button_bg`); erledigt = gedimmt (`text_dim`/`muted_bg`), wandert ans Ende und sammelt sich unten in halber Höhe (Zwei-Zonen-Layout), offene rücken auf. Status nur zur Laufzeit.
- Kopfzeile „Füllen" → `ToCallFillDialog`: Programm-Dropdown (Default = erstes Session-Programm), Call-Checkliste (alle vorausgewählt), „Alle an/aus", Buttons „Füllen" und „Add to Notes".
- DB: `get_calls_for_program(program_label)` — Label-Match auf `call_programs.program`, Trenner gefiltert.
- Geteilte Call-Logik `call_selection.py`: `resolve_calls()` + `build_shortcode_params()` mit Sweet-Spot (>½ → `program`+`except`, sonst `calls`; alles → nur `program`).
- Notiz-Shortcode `[to_call …]` (Namen-basiert, inkl. Exclusion), Dispatch in `_shortcode_dispatch` → füllt Widget + zeigt Dock. Abhaken einer Notiz löst ihn aus.
- Geteilter Layout-Code `button_grid.py` (auch Jump-Markers-Widget); Perf-Marken; i18n de/en/ja; Dock vor `_restore_layout()`.
**Verwandt:** BL-151 (Pattern-Call-Checkliste), BL-198 (zuletzt geteachte Figur).

---

### BL-201 — main.py aufteilen (modularer Umbau für Git + Wartbarkeit)

**Status:** ERLEDIGT (2026-09-08 von David als fertig erklärt; Branch `refactor/main-split`)
**Quelle:** David + Session 2026-09-05 (Startup-Performance-Untersuchung → Architektur-Analyse)
**Aufwand:** Groß, aber strikt inkrementell (ein Cluster pro Commit, jeweils testbar)
**Ziel:** Die ~29.300-Zeilen-Datei `src/main.py` in modulare Unterdateien aufteilen — **primär für Git-Kollaboration und Wartbarkeit, NICHT für Performance.**

---

#### ✅ Umsetzungs-Stand (Stand 2026-09-07, Branch `refactor/main-split`)

**Fortschritt: `main.py` 29.309 → 24.301 Zeilen (−17 %) nach 3 extrahierten Clustern.**

| # | Cluster | Neues Modul | Commit | main.py-Δ | App-Smoke-Test |
|---|---|---|---|---:|---|
| 1 | Perf-/Startup-Logging | `src/perf.py` (300 Z.) | `0b55d17` | −233 | ✅ bestätigt (App lief, Songs, Perf-Log geschrieben) |
| 2 | UI-Helfer | `src/ui_helpers.py` (645 Z.) | `3c2f4ac` | −516 | ✅ bestätigt (Icons in allen Dialogen) |
| 3 | LyricsWidget (Pilot) | `src/lyrics_widget.py` (4.219 Z.) | `46687e1` | −4.257 | ✅ bestätigt (Text, Farb-Overlay, Zoom, Wrap-Buttons) |

**Was in den Modulen liegt:**
- **`perf.py`** — kompletter Performance-/Sentinel-Zustand. Der geteilte mutierbare Zustand ist **sauber gekapselt** (statt modulübergreifender Global-Schreibzugriffe): `main()` → `perf.configure(enabled, device_index, version)`, Stall-Detektor → `perf.record_stall(gap_ms)`, Lesen über `perf.is_enabled()` / `perf.get_last_perf()`. `diagnose_center` liest Sentinel-Stats jetzt aus `perf` statt `main` (Entkopplung wie in Abschnitt 5 gefordert). Startup-Instrumentierung (`_T_MODULE_TOP_*`) bleibt bewusst in `main.py`.
- **`ui_helpers.py`** — reine Helfer (`fmt_time`/`fmt_precise`/`parse_time_offset`, `_clear_layout`, `calc_loop_count`/`calc_loop_cut`/`calc_auto_loop` + `LOOP_CUT_TOLERANCE_S`, `show_loop_count_dialog`), Transport-/Icon-SVGs + `_make_icon`, `_make_dock`, `_PlayBarrier` und (in Stufe 3 nachgezogen) `_WrapButtonBar`.
- **`lyrics_widget.py`** — `LyricsWidget`, `_LyricSectionOverlay`, die `LYRIC_SECTION_*`-Konstanten, `lyric_section_lines`/`lyric_plain_text`.

**Methode (tokensparend, pro Cluster gleich):** verstreute Regionen per AST-Zeilenranges ausschneiden → Imports per Free-Variablen-Analyse + `pyflakes` ermitteln (pyflakes im Wegwerf-venv, da es in Davids Python fehlt) → extrahierte Namen nach `main.py` zurück-importieren, **alle Aufrufstellen bleiben unverändert**. Verifikation je Stufe: `py_compile` + `pyflakes` (0 undefined names) + isolierter Funktions-/Import-Test + Davids App-Smoke-Test. **Kein Modul importiert `main` → keine Zirkel** (verifiziert).

**Nebenbei abgesichert (Commit `8d11a28`):** Nachweis, dass die Dev-App wirklich `C:\Git\callers-caddy\src` lädt (Skript-Verzeichnis gewinnt über CWD `2_Test`). Veraltete Modul-Duplikate in `2_Test` (`main.py`, `song_db.py`, `rule_*.py` u. a.) nach `2_Test\_alt\` ausgeräumt. `main()` druckt beim Start `[Main] … — Code aus: <dir>` als dauerhafte Herkunftsanzeige.

**Nächste Cluster (Pareto-Reihenfolge, Abschnitt 7/8):** `sequences_widget.py` (~3.865 Z.) → `potential_widget.py` → `song_data_widget.py` → `player_widget.py` → `reports_bulk_tools.py` → `playlist_widget.py` → `loopfinder_break_photo.py` → `dialogs_genre_location_program.py`. `P29MainWindow` bleibt als Orchestrator in `main.py`.

---

**Bezug / Abhängigkeit (GitHub-Umstieg, 2026-09-07):** Dieser Split ist eine **Voraussetzung für die Kollaborationsphase** des GitHub-Umstiegs (siehe `GIT-Umstieg-Checkliste.md` im `Projekte`-Ordner). Für die reine **Absturzsicherung** (Repo anlegen + hochladen) ist er NICHT nötig, wohl aber für konfliktarmes **paralleles Arbeiten mit Thomas** (`FireWalkerHH`) — eine 29k-Zeilen-Datei erzeugt sonst Dauer-Merge-Konflikte. **Empfehlung:** den Split idealerweise BEREITS im Git durchführen (ein Cluster = ein Commit, jederzeit rücksetzbar — genau der Stufenplan aus Abschnitt 8). D. h. Reihenfolge nicht zwingend „erst splitten, dann Git", sondern „Git aufsetzen → Split als erste Arbeit im Repo → dann Thomas einladen".

---

#### 0. Kontext / Auslöser

Ausgangspunkt war Davids Eindruck, der App-Start dauere „unglaublich lange", inkl. Verdacht auf blinde Zeit *vor* dem sichtbaren Fenster und beim Doppelklick. Daraus wurde ein Startup-Performance-Test; daraus die Frage, ob die große `main.py` das Laden bremst; daraus dieser Umbau-Plan. Diese BL bündelt **alles** aus der Session: Messung, bereits umgesetzten Doppelklick-Fix, Architektur-Analyse und Pareto-Datengerüst.

---

#### 1. Startup-Performance — Messergebnis (Dev-Modus, David i9-11900, v0.148)

Neue, dauerhafte Instrumentierung macht die bisher **blinde Zeit vor `main()`** sichtbar (nur aktiv bei `debug/performance_logging=true`).

| Phase | warm (Ø 3 Läufe) | Anteil | vorher gemessen? |
|---|---|---|---|
| Bootloader + Python-Init (Prozessstart → Modul-Top) | ~580 ms | 15 % | ❌ war blind |
| **Import-Phase (Modul-Top → main)** | **~2040 ms** | **53 %** | ❌ war blind |
| QApplication + Lock | ~30 ms | 1 % | ✅ |
| Skin + Sprache | ~53 ms | 1 % | ✅ |
| MainWindow.\_\_init\_\_ | ~1170 ms | 30 % | ✅ (Docks+Tutorials ~840 ms, Layout ~250 ms) |
| window.show() | ~40 ms | 1 % | ✅ |
| **GESAMT ab Prozessstart bis sichtbar** | **~3900 ms** | | ❌ war blind |

- Das alte „GESAMT bis show" (1286 ms) zeigte nur **ein Drittel** der echten Wartezeit.
- **Kaltstart** (kalter OS-Cache / erste `.pyc`-Kompilierung): Import-Phase **9021 ms**, Gesamt ~11–12 s. Das ist der „ewig"-Fall, den David v. a. auf dem langsameren Laptop sieht.
- **Import-Kosten pro Modul (warm):** PySide6.QtCore 144 ms · numpy 181 ms · audio_engine/PortAudio 227 ms · song_db 32 ms · **`bpm_detector` 1343 ms** ⚠ · Rest <15 ms. → `bpm_detector` ist **zwei Drittel** der Import-Phase (zieht vermutlich librosa/scipy o. ä. beim Import).

**Instrumentierung** (in `main.py`, bereits im Working Tree): frühester Messpunkt ganz oben vor den schweren Imports (`_T_MODULE_TOP_*`); Prozess-Erstellungszeit via WinAPI `GetProcessTimes` (`_process_create_epoch`, mit korrekten `argtypes` — sonst 64-Bit-Pointer-Kappung → schlägt fehl); Log-Zeilen „Bootloader + Python-Init", „Import-Phase", „GESAMT ab Prozessstart bis SICHTBAR".

Archivierte Logs: `docs/perf_logs/2026-09-05_v148_david-i9_startup-instrumented.txt` (warm) und `…_startup-cold.txt` (kalt), im INDEX eingetragen.

**⭐ EXE-Baseline (echte .exe, David i9-11900 Desktop, v0.148)** — `docs/perf_logs/2026-09-05_v148_david-i9_exe-baseline.txt`:

| Phase | EXE | Dev-warm |
|---|---:|---:|
| Bootloader + Python-Init | 177 ms | ~580 ms |
| **Import-Phase** | **973 ms** | ~2040 ms |
| MainWindow.\_\_init\_\_ | 1005 ms | ~1170 ms |
| **GESAMT bis sichtbar** | **2268 ms** | ~3900 ms |

Die EXE ist über die ganze Kette schneller als der Dev-Modus (Dev-Zahlen überzeichnen das Problem für Endnutzer). Import-Phase bleibt mit **973 ms = 43 %** der größte Block und liegt komplett vor dem Fenster → `bpm_detector`-Lazy-Load (Abschnitt 9) ist der Top-Hebel. In MainWindow zwei EXE-Ausreißer: `addDockWidget(Player) 212 ms` (einmaliger Native-Handle-Aufwand, kaum wegoptimierbar) und `SeqFilter count_query 183 ms` (kalter DB-Cache; zweiter Lauf 3 ms → Index-Check / Sequenzen-Dock verzögert aufbauen). Doppelklick-Fix bestätigt: `QApplication + Lock 13 ms`. **Diese 2268 ms sind die Referenz, gegen die jede Optimierung gemessen wird.**

---

#### 2. Bereits umgesetzt heute (im Working Tree, NOCH NICHT gebaut/changelogt)

**a) Doppelklick-Fix — ERLEDIGT.** Der Single-Instance-Lock (`QLockFile`) saß tief in `main()` (nach QApplication + Audio-Selbsttest + allen Imports). Ein ungeduldiger zweiter Doppelklick zahlte dadurch den fast vollständigen Start, bevor er „läuft bereits" merkte — und stahl der ersten Instanz CPU/Disk in deren kritischster Phase.
- **Gelöst:** Lock wandert an den **Modul-Anfang** (`_acquire_single_instance_lock` / `_LOCK_FILE`), direkt nach den PySide6-Imports und **vor** die schweren lokalen Imports. Meldung per nativer WinAPI-`MessageBoxW` (die 2. Instanz fährt kein QtWidgets/QApplication mehr hoch).
- **Robuste Absturz-/Orphan-Erkennung bleibt 1:1 erhalten** (`setStaleLockTime(0)` + `removeStaleLockFile`, prüft ob Besitzer-Prozess noch lebt).
- Verifiziert: `QLockFile` + `QStandardPaths.TempLocation` funktionieren ohne `QApplication`.
- **Messung:** verschwendete Zeit der 2. Instanz **2824 ms → 1044 ms** (–63 %); die 2. Instanz lädt `bpm_detector`/audio/numpy jetzt gar nicht mehr. Rest-Sekunde ist reiner Interpreter-Start (unvermeidbar). Kein Regressions bei Instanz 1 (startet unverändert bis sichtbar durch).
- **Doppelklick-Messwert** wird in `logs/perf/second_instance.log` protokolliert.
- **TODO vor Release:** CHANGELOG-Eintrag + Build (Build-Regel: erst nach Davids OK). Version noch nicht gebumpt.

**b) Startup-Instrumentierung — ERLEDIGT** (siehe Abschnitt 1). Dauerhaft, hinter dem Perf-Flag.

---

#### 3. Kernbefund zur Dateigröße (Antwort: bremst die große main.py den Start?)

**Nein — nicht zur Laufzeit.**

| Kosten der Dateigröße | Wann | Betrag |
|---|---|---|
| `.pyc` laden/unmarshal | jeder Start, **auch EXE** | **~4 ms** |
| `.py → Bytecode` kompilieren | **nur kalt / Dev** (erste Ausführung) | ~887 ms |

- Die 1,3-MB-Datei kostet pro Start **~4 ms** — vernachlässigbar. Die Startzeit steckt in den **Library-Imports** (`bpm_detector`), nicht in der Dateigröße.
- **Ein Split beschleunigt den Programmstart also nicht.** Die 887 ms Kompilierzeit fallen nur beim allerersten Lauf an (Teil der „9 s kalt"); die gebaute EXE liefert vorkompilierte `.pyc` mit → entfällt für Endnutzer.
- **Aber:** In der Dev-Iteration cached Python `.pyc` **pro Modul**. Heute → jede Änderung an main.py = 887 ms Neukompilierung der ganzen Datei. Nach Split → nur das geänderte Modul kompiliert neu. Realer Dev-Vorteil.

---

#### 4. Warum trotzdem sinnvoll — Chancen

1. **Git-Kollaboration (Hauptargument).** Eine 29k-Zeilen-Datei = *jeder* Branch fasst sie an → Dauer-Merge-Konflikte, faktisch ein Dauer-Lock. Nach dem Split arbeiten parallele Features an getrennten Dateien und kollidieren kaum. Genau Davids Zukunftsszenario.
2. **Schnellere Dev-Iteration** (siehe Abschnitt 3, `.pyc`-Cache pro Modul).
3. **Übersichtlichkeit & gezieltere (KI-)Arbeit** in kleineren Dateien.
4. **Weg ist erprobt:** ~10 Widgets sind bereits ausgelagert (`notes_widget.py`, `stats_widget.py`, `evening_planner_widget.py`, `to_call_widget.py`, `jump_markers_widget.py`, `rule_widget.py`, `settings_dialog.py` …). Muster steht.

---

#### 5. Kopplungs-Analyse (Machbarkeit)

Sehr günstige Ausgangslage — lose gekoppelt:

- **Keine Widget↔Widget-Kopplung:** keine `isinstance`-Checks auf Widget-Typen, keine gegenseitige Instanziierung. Jedes große Widget wird **genau 1×** instanziiert (in `P29MainWindow`).
- **Kommunikation** über **49 Qt-Signale** + Dependency-Injection. Konstruktoren nehmen externe Abhängigkeiten (`engine`, `db`, `paths`, `skin_mgr`) — **keine** Geschwister-Widgets.
- **Kaum Rückgriff aufs Hauptfenster** (`self.window.<attr>` = 0, `self.parent()` 2×). `P29MainWindow` ist Kompositionswurzel.
- **Blaupause der bereits ausgelagerten Module:** sie injizieren `perf_log`/`perf_start` per Konstruktor (`perf_start=None, perf_log=None` → `self._perf_log = perf_log or (lambda *a,**k: None)`) und importieren `main` **nicht**.
- **Eine echte Rück-Kopplung:** `diagnose_center.py` macht 3× `import main as _m` (lazy, in Funktionen) und liest Laufzeit-Status (Stall-Sentinel / Perf). → Beim Split muss dieser Status in ein Blatt-Modul (`perf.py`), damit `diagnose_center` sauber von dort importiert.

---

#### 6. Risiken & Mitigationen

1. **Zirkuläre Importe** (klassischer Fallstrick). → Blatt-Module (`perf.py`, `ui_helpers.py`) **zuerst**; Helfer injizieren; **kein** `import main` in ausgelagerten Modulen. `diagnose_center`-Rückgriff mit umziehen.
2. **Big-Bang-Gefahr** (27k Zeilen auf einmal). → strikt inkrementell, **ein Cluster pro Commit, nach jedem testen**. Startup-Instrumentierung ist der Regressions-Wächter (Zahlen müssen gleich bleiben).
3. **Timing-Konflikt mit laufender Feature-Arbeit** (z. B. Programm-Umbau 2026). Der Split ist ein Riesen-Diff → auf eigenem Branch, wenn kein großer Feature-Branch offen ist.
4. **Subtile Regressionen** (Signal-Verdrahtung, `self.window()`-Aufrufe). → beherrschbar durch Cluster-weises Testen + Smoke-Test nach jeder Stufe.
5. **Paket-Zuordnung einzelner Kleinklassen** (v. a. `reports_bulk_tools.py`: welcher `_Bulk*Worker` zu Reports vs. Potential gehört) ist ein erster Schnitt — beim echten Verschieben je Modul eine Abhängigkeitsprüfung.

---

#### 7. Pareto-Datengerüst — auslagerbare Pakete (Zeilen exakt per AST, v0.148)

| # | Paket | Zeilen | % Datei | kumulativ |
|---|---|---:|---:|---:|
| 1 | `lyrics_widget.py` (LyricsWidget, _LyricSectionOverlay, lyric_section_lines, lyric_plain_text) | 4.137 | 14,1 % | 14,1 % |
| 2 | `sequences_widget.py` (SequenceView/Sequences + Editor/Import/Mapping-Dialoge) | 3.865 | 13,2 % | 27,3 % |
| 3 | `potential_widget.py` (PotentialWidget) | 3.101 | 10,6 % | **37,9 %** |
| 4 | `song_data_widget.py` (SongData/FilterBar/ListWidget + Reco-Helfer, SongPropertiesDialog) | 1.976 | 6,7 % | 44,6 % |
| 5 | `player_widget.py` (PlayerWidget, LoopWidget, Overlays, BPM/BeatSnap/SingingBody-Worker) | 1.906 | 6,5 % | **51,1 %** |
| 6 | `reports_bulk_tools.py` (ReportsWidget + alle _Bulk*/Ceder/Krabbelkiste/Beautify/Meta/Csv-Worker) | 1.742 | 5,9 % | 57,1 % |
| 7 | `playlist_widget.py` (Playlist/PoolTable/ManagerWidget, CustomFilterDialog) | 1.638 | 5,6 % | 62,7 % |
| 8 | `loopfinder_break_photo.py` (LoopFinder, Break, Photo) | 1.526 | 5,2 % | 67,9 % |
| 9 | `dialogs_genre_location_program.py` (Location/Genre/DanceProgram-Dialoge) | 1.317 | 4,5 % | 72,4 % |
| 10 | `ui_helpers.py` *(Blatt)* (fmt_time, _make_icon, SVG, calc_loop_*, _make_dock, _clear_layout, _PlayBarrier …) | 507 | 1,7 % | 74,1 % |
| 11 | `perf.py` *(Blatt)* (perf_log/start/split, _perf_*, get_stall_sentinel_stats, _process_create_epoch) | 199 | 0,7 % | 74,8 % |
| 12 | `feedback_dialog.py` (FeedbackDialog) | 177 | 0,6 % | 75,4 % |
| — | **bleibt in main.py** (P29MainWindow 6.325 + main() + Startup/Lock) | ~6.635 | 22,6 % | |

**Pareto-Lesart:** Die **3 größten Pakete (Lyrics + Sequences + Potential) = 11.103 Zeilen = 37,9 %** in nur 3 Extraktionen — riesig *und* eigenständig, also maximale Git-Entlastung pro Handgriff. Top 5 ≈ 51 %. Alles Auslagerbare = 75,4 % → main.py schrumpft auf **~7.200 Zeilen** (nur Orchestrator + Startup). Klassen-Zeilen exakt; Paket-*Zuordnung* ist erster Schnitt.

---

#### 8. Empfohlener Stufenplan (jede Stufe = eigener Commit, testbar)

1. **Blatt-Module zuerst** (rein additiv, kein Verhalten ändert sich): `perf.py` (Perf-Status + `get_stall_sentinel_stats`, damit `diagnose_center` von dort statt von `main` importiert) und `ui_helpers.py` (fmt_time, _make_icon, SVG-Templates, calc_loop_*, _make_dock, Konstanten).
2. **Pilot-Cluster:** `lyrics_widget.py` (~4.137 Z., größter isolierter Brocken) — beweist das Muster an einem realen Brocken.
3. Dann Cluster für Cluster nach Pareto: Sequences, Potential, Song-Daten, Player, Reports/Bulk, Playlist, LoopFinder/Break/Photo, Dialoge.
4. **`P29MainWindow` bleibt in main.py** — Orchestrator; das aufzuspalten ist unverhältnismäßig riskant und nicht Teil dieser BL.

**Guardrails:** eigener Branch, kein paralleler großer Feature-Branch; nach jeder Stufe Smoke-Test + Startup-Perf-Log gegen die Baseline (Abschnitt 1) prüfen; `_fallback/`-Backup vor jeder Stufe.

---

#### 9. Verwandte offene Hebel (separat, NICHT Teil des Splits)

- ~~**`bpm_detector` Lazy-Load** — der eigentliche Start-Hebel.~~ ✅ **ERLEDIGT 2026-09-07** (Commit `8cb0262`). Neue Messreihe NACH dem main.py-Split (8 warme Läufe, frischer Prozess je Lauf): `bpm_detector`→**scipy** war weiterhin die größte Bremse (~1,0 s), jetzt ausgelöst über den Modul-Import in `songdata_widget` (BpmWorker). `detect_bpm` wird nur in `BpmWorker.run()` gebraucht → Import dorthin verschoben (lazy). Alle anderen bpm/loop/singing-Nutzer importierten schon lazy. **Gegenmessung: Import-Phase 1824 ms → 597 ms (−1227 ms, −67 %); scipy beim Start nicht mehr geladen (verifiziert).** scipy lädt jetzt beim ersten BPM-/Beat-Snap-Vorgang. Größter Rest jetzt: audio_engine (PortAudio) 322 ms, PySide6 124 ms.
- ✅ **ERLEDIGT 2026-09-07** (Commit `b622609`) — **Sequenzen-Cover persistent cachen (B) + Startup-Load lazy (A).** Voller kritischer Pfad neu gemessen (echter App-Start, Perf-Log): nach dem bpm-Lazy-Load war der kalte `SeqFilter.count_query` (Band-Tanzbarkeits-Join `_cover_ids` über 97k `sequence_calls`) mit **275 ms** die größte verbliebene Einzelbremse, jedes Mal. **B:** `_cover_ids`-Ergebnis persistiert in neuer Tabelle `_band_cover`, gestempelt mit `_band_cache_ver.v` (bestehende Trigger auf sequences/sequence_calls/call_text_mappings/call_programs) → Lookup statt Join (**275 → 5 ms**), überlebt Neustarts, invalidiert nur bei echter Datenänderung. **A:** `set_program_bands(defer_load=True)` + `_init_sequences()` per `QTimer.singleShot(0, …)` nach `window.show()` → Cover-Compute nie mehr auf dem Erscheinungs-Pfad. **Gegenmessung: GESAMT bis SICHTBAR 1954 → ~1575 ms (−~380 ms); SequencesWidget-Bau 344 → 62 ms.** Nächste Rest-Hebel (schwerer): `addDockWidget(Player)` ~210 ms (Qt-Native-Handle, kaum vermeidbar), `Layout restore` ~215 ms, Import-Phase ~600 ms (PySide6 + PortAudio).
- **EXE-Realmessung** — Build nötig (Davids Freigabe), um Bootloader + UPX-Dekompression echt zu messen (Dev-Modus zeigt das nur teilweise).
- **CHANGELOG + Build** für den bereits erledigten Doppelklick-Fix + Instrumentierung (Abschnitt 2).

**Verwandt:** BL-123 (Codepflege / tote Klassen), BL-130/131 (async Laden), CLAUDE.md („Bekannte Qt-Fallen", Perf-Regeln), `docs/perf_logs/INDEX.md`.

