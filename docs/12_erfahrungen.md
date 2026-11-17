# Erfahrungshandbuch — Prototypen-Entwicklung

## Audio-Pipeline

### WSOLA Time-Stretcher (eigene Implementierung)
- **Warum eigener WSOLA?** Rubber Band (pyrubberband) braucht CLI-Binary (nicht echtzeitfaehig), natives `rubberband` pip-Package braucht vorinstallierte C-Libraries. SoundTouch ebenfalls keine pip-Packages fuer Windows. Daher eigener Streaming-WSOLA.
- **v1 hatte Qualitaetsprobleme**: Scheppern/Rasseln selbst bei -1% Tempo. Ursache: fehlende Fensterung, zu kleines Fenster, ungenaue Korrelationssuche.
- **v2 Loesung**: Hann-Fenster mit 50% Overlap (COLA-Bedingung), groesseres Fenster (4096), Coarse-to-Fine Korrelationssuche (Schritt 8 grob, dann Schritt 1 fein). Ergebnis: sauberer Sound, 49x Echtzeit.
- **Fenstergroesse 8192**: Ab P5 auf 8192 erhoeht fuer bessere Qualitaet bei extremen Einstellungen. Kein merklicher Performance-Verlust.
- **Qualitaetsgrenzen**: WSOLA klingt gut im Bereich 70%-130% Stretching. Darunter/darueber zunehmend blechern/metallisch. Bei 60% Tempo + 5 Halbtoene (~45% Stretching) sind Artefakte unvermeidbar — algorithmische Grenze.
- **syn_hop = window_size // 2**: Immer automatisch berechnen, NICHT als Parameter uebergeben. v2 hatte Bug weil main.py noch den alten syn_hop-Parameter uebergab.

### Pitch-Shifting (Resampling + WSOLA)
- **Ansatz**: scipy.signal.resample aendert Pitch+Tempo, WSOLA kompensiert Tempo zurueck.
- **Kritischer Bug**: `tempo_compensation()` muss `1.0 / pitch_ratio` zurueckgeben (INVERS!). Erster Versuch gab `pitch_ratio` zurueck → Turntable-Effekt (Pitch aenderte Tempo mit).
- **Formel**: pitch_ratio = 2^(semitones/12). Hoeher = kuerzeres Signal. WSOLA muss strecken = langsamer = 1/ratio.

### Kombiniertes Tempo + Pitch
- **WSOLA-Tempo = user_tempo × (1/pitch_ratio)**. Multiplikation, nicht Addition.
- Beispiel: 110% Tempo + 1 Halbton → WSOLA = 1.1 × 0.9438 = 1.038

### Feed-Ahead Buffer und Latenz
- **Problem**: FEED_AHEAD_SECONDS = 2.0 fuehrte zu 1-2 Sekunden Verzoegerung bei Pitch/Tempo-Aenderung.
- **Loesung 1**: FEED_AHEAD_SECONDS auf 0.5 reduziert. Reicht fuer stabilen Audio-Callback.
- **Loesung 2**: Flush-and-Refeed-Mechanismus. Bei Aenderung: altes Audio verwerfen, feed_pos zurueckrechnen, mit neuen Einstellungen neu befuellen.
- **Flush ist thread-safe**: Muss unter Lock laufen, da Audio-Callback parallel retrieve() aufruft.
- **Rewind-Berechnung**: `rewind = unprocessed_samples × old_pitch_ratio + output_buffered`

### Seek (Position springen)
- Funktioniert via flush() + feed_pos setzen + refeed
- Position-Slider braucht `_seeking`-Flag um zu unterscheiden ob User zieht oder Timer aktualisiert. sliderPressed/sliderReleased Events nutzen.

### Loop-System
- Loop-Grenzen werden beim Einspeisen (feed) geprueft, nicht beim Abspielen
- Bei Loop-Punkt: feed_pos zurueck auf Loop-In, Stretcher flushen
- Loop-Test: 5s vor Loop-Out springen, Loop automatisch aktivieren
- Song-Ende-Erkennung nur wenn Loop NICHT aktiv

### Songdauer-Anzeige
- Effektive Dauer = Original-Dauer / (song_tempo × today_tempo)
- Pitch aendert die hoerbare Dauer nicht (wird ja durch WSOLA kompensiert)

## Audio-Infrastruktur

### sounddevice (PortAudio)
- Callback-basiert, laeuft in C-Thread ausserhalb Python GIL
- `latency='low'` fuer geringe Verzoegerung
- blocksize=1024 funktioniert gut (~ 23ms bei 44100 Hz)

### soundfile (libsndfile)
- MP3-Support ab libsndfile 1.1.0+ (in aktueller pip-Version enthalten)
- Daten als float32 laden: `sf.read(path, dtype='float32')`
- Mono -> Stereo reshape: `data.reshape(-1, 1)` wenn ndim==1

## UI (PySide6 / Qt)

### Allgemein
- QTimer mit 50ms Intervall fuer UI-Updates (20 FPS, genuegt fuer Zeitanzeige)
- Slider valueChanged feuert auch bei programmatischer Aenderung → blockSignals(True) nutzen
- FileDialog Startverzeichnis: `os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))` fuer Projektroot

## UI-Layout-Entscheidungen (aus P7-Test)

### Modul-Zuordnung der Controls
- **"Loop aktiv" Checkbox** → gehoert auf den **Player** (wird staendig gebraucht)
- **Loop-In/Out setzen + Loop-Test** → gehoert aufs **Loop-Fenster** (nur beim Import neuer Songs noetig, nicht dauerhaft sichtbar)
- **Song-Info** → Debugging/Test-Modul, kein Endanwender-Feature

### QDockWidget-Architektur
- Funktioniert sehr intuitiv: Andocken, Abkoppeln, Schliessen
- Geschlossene Module ueber "Ansicht"-Menu wieder einblendbar
- **Spaeter**: Icon-Buttons im Player statt Menu fuer Ein-/Ausblenden
- Alle Module teilen sich eine Audio-Engine (Observer-Pattern via Timer)
- `splitDockWidget()` fuer initiale Anordnung (z.B. vertikal untereinander)
- `_make_dock()` Hilfsfunktion fuer einheitliche Dock-Erstellung

### P10 Resize-Regeln — verschoben
- Wird erst getestet wenn die endgueltigen Module feststehen
- Dann pro Modul: min/max Groesse, festes vs. freies Resize definieren
- **Bekanntes Problem**: Song-Daten kann in die Songliste "reinragen" wenn Gesamtfenster zu klein. Muss durch minimumSize / minimumSizeHint pro DockWidget geloest werden

### QSpinBox statt QSlider fuer Tempo/Pitch
- QSpinBox (Integer) und QDoubleSpinBox (Float) sind extrem platzsparend
- Pfeile oben/unten, Wert in der Mitte — ideal fuer den Player
- Tempo: QSpinBox, 50-150, suffix " %", singleStep=1
- Pitch: QDoubleSpinBox, -6.0 bis 6.0, suffix " HT", singleStep=0.2
- Beide in einer Zeile nebeneinander → spart enorm Platz gegenueber zwei GroupBox+Slider

### Sync Player ↔ Song-Daten
- Wenn Player-SpinBox geaendert wird → Callback an MainWindow → Song-Daten SpinBox aktualisieren
- blockSignals(True) beim Setzen externer Werte, um Endlosschleifen zu vermeiden
- Richtung: Player → Song-Daten (einseitig fuer jetzt, Auto-Save kommt in P14)

### QSettings — Portabel statt Registry
- **NICHT** `QSettings("Org", "App")` verwenden → landet in Windows-Registry
- **Stattdessen** `QSettings("pfad/datei.ini", QSettings.IniFormat)` → lokale INI-Datei
- INI-Datei im App-Verzeichnis = portabel (kopierbar, plattformunabhaengig)
- `saveGeometry()` / `restoreGeometry()` fuer Fensterposition + Groesse
- `saveState()` / `restoreState()` fuer Dock-Layout (Position, Sichtbarkeit, floating)
- Wichtig: `setObjectName()` fuer jeden QDockWidget, sonst kann restoreState() sie nicht zuordnen

### Central Widget Trick
- Wenn alle Module QDockWidgets sind: Central Widget auf maximale Groesse 0x0 setzen
- So werden alle Bereiche gleichwertig und frei positionierbar

## Datenbank (SQLite)

### P13 Songmodell
- **SQLite built-in**: Python `sqlite3` Modul reicht voellig, kein ORM noetig fuer diese Groesse
- **WAL-Modus**: `PRAGMA journal_mode=WAL` fuer bessere Read-Concurrency (Audio-Thread + UI-Thread)
- **Dataclass als Song-Objekt**: `@dataclass` mit `Optional[int] id` = None fuer neue Songs, ID wird nach Insert gesetzt
- **get_or_create() Pattern**: Beim Laden einer MP3 wird der Dateiname gesucht. Existiert er → gespeicherte Settings laden. Sonst → neuer Eintrag mit Default-Werten (Titel = Dateiname ohne .mp3)
- **Nur Dateiname gespeichert, KEIN absoluter Pfad**: Portabilitaet — Installation kann kopiert werden
- **Loop-Out Default = 0.0**: Bedeutet "Songende". Beim Laden wird 0.0 auf die tatsaechliche Songlaenge gesetzt
- **Partial Update fuer Auto-Save**: `save_playback_settings()` erlaubt einzelne Felder zu aktualisieren (Keyword-Only), ohne den ganzen Song laden zu muessen
- **DB-Datei liegt neben der Anwendung**: `callers_caddy.db` im App-Verzeichnis (portabel, wie die INI-Datei)
- **AudioEngine erweitert**: `set_loop_in(seconds)` und `set_loop_out(seconds)` hinzugefuegt um Loop-Marker direkt per Sekundenwert zu setzen (nicht nur "at_current")

### Songfelder (Lastenheft)
Alle Pflichtfelder implementiert:
- filename (technisch, UNIQUE, unveraenderlich)
- title (editierbar, Default = Dateiname)
- label (Plattenlabel)
- quality (0-10 Skala)
- base_bpm, standard_tempo, pitch, volume
- loop_in, loop_out (in Sekunden)
- lyrics_file (Dateiname)

### Integration Song-DB mit AudioEngine
- Beim Laden einer MP3: `get_or_create()` → Song-Objekt
- Tempo/Pitch-SpinBox auf gespeicherte Werte setzen via `apply_song_settings()`
- Loop-Marker via `set_loop_in(seconds)` / `set_loop_out(seconds)` restaurieren
- Songliste (QListWidget): Einfach-Klick = Song laden (NICHT starten, gemaess Lastenheft)
- Substring-Suche ueber Titel, Label, Dateiname
- **DB-Datei**: `callers_caddy.db` (ab P19 umbenannt von songs.db — gemeinsame DB fuer alle Entitaeten)

### P14 Auto-Save (in P13 mit abgenommen)
- **Kein Speichern-Button noetig** — alles wird automatisch gespeichert
- Auto-Save-Trigger:
  - SpinBoxen: `valueChanged` → sofort gespeichert
  - Textfelder: `editingFinished` → bei Fokus-Verlust oder Enter
  - Song-Wechsel: `_save_current_song()` speichert Tempo/Pitch/Loop aus Engine
  - App-Schliessen: ebenso
- **`_loading`-Flag**: Verhindert Auto-Save waehrend `_populate_fields()`, da `setValue()` `valueChanged` feuert
- Auch fuer `update_tempo()`/`update_pitch()` (Sync vom Player) wird `_loading` gesetzt
- Duplikat-Schutz: `get_or_create()` + UNIQUE-Constraint auf filename → keine versehentlichen Duplikate

### P15 Portable Pfade
- **PathManager-Klasse**: Zentrale Stelle fuer alle Verzeichnis-Pfade, gibt nach aussen nur absolute Pfade
- **INI speichert nur relative Pfade**: `os.path.relpath(absolute, app_dir)` → portabel
- **Fallback bei anderem Laufwerk** (Windows C: vs D:): `os.path.relpath()` wirft `ValueError`, dann absolut speichern
- **Default-Ordnerstruktur**: `../music/`, `../neu/`, `../lyrics/` relativ zum App-Verzeichnis
- **`ensure_directories()`**: Erstellt fehlende Verzeichnisse beim Start automatisch
- **`find_song_file(filename)`**: Sucht erst im music_dir, dann app_dir, dann rekursiv im music_dir
- **FileDialog startet im music_dir**: Nicht mehr im Projektroot, sondern im konfigurierten Musik-Verzeichnis
- **Pfade-Menu**: Verzeichnisse koennen zur Laufzeit geaendert werden (Dialog → relativer Pfad in INI)
- **Abnahmetest**: Songs verschoben → Player findet sie nicht mehr → Pfad-Einstellung angepasst → Player findet sie wieder

### P16 Heutiges Tempo
- **Session-Faktor**: `_today_tempo` getrennt von `_user_tempo` (Song-Tempo). Bleibt beim Song-Wechsel erhalten, wird beim Laden NICHT zurueckgesetzt.
- **Formel**: `combined = song_tempo × today_tempo × pitch_compensation` (Multiplikation)
- **Effektive Dauer**: `original / (song_tempo × today_tempo)` — Pitch aendert Dauer nicht
- **Layout**: Labels zentriert UEBER den SpinBoxen statt daneben. 3 Spalten: Heutiges Tempo | Song-Tempo | Pitch. Spart horizontalen Platz.
- **Loop-Bug gefixed**: `_feed_stretcher()` While-Schleife hatte `_feed_pos < len(data)` als Bedingung → Loop-Back-Code wurde nie erreicht wenn loop_out == len(data). Fix: Zuerst `_feed_pos >= loop_out` pruefen, dann bei Loop zurueckspringen, sonst `break`.
- **Prototyp-Daten kopieren**: DB + INI aus dem vorherigen Prototyp mitkopieren, spart User das erneute Aufbauen von Testdaten

### P18 Pattern/Singing Modus
- **is_pattern / is_singing**: Getrennte Booleans statt enum → Song kann beides sein
- **Pattern → Loop**: Wenn `is_pattern`, wird Loop automatisch aktiviert beim Laden. Singing → Loop deaktiviert.
- **Filter**: Radiobuttons "Alle / Pattern / Singing" filtern die Songliste live

### P19 Club-Auswahl
- **Gemeinsame DB**: Alle Entitaeten (Songs, Clubs, spaeter Historie) in einer `callers_caddy.db`
  - Vorteil: Foreign Keys, JOINs, eine Verbindung, einfaches Backup
  - Nachteil: keiner bei dieser Groessenordnung
- **Club-Dialog**: QDialog mit QListWidget, Add/Rename/Delete, "Kein Club" Button
- **Roter Club-Button**: Warning-StyleSheet wenn kein Club ausgewaehlt (`background-color: #ef4444`)
- **Titelzeile**: `setWindowTitle(f"{BASE_TITLE}  @  {club.name}")` zeigt aktuellen Club
- **NEU-Button**: Aus Player verschoben ins Loop-Fenster, Callback-Delegation an MainWindow
- **Tabbed Docking**: `AllowTabbedDocks | AllowNestedDocks` aktiviert fuer spaetere Registerkarten (Lyrics/Sequenzen)
- **Docking-Limitation**: Floating-Fenster docken nur an wenn sie UEBER das Hauptfenster gezogen werden, kein magnetisches Snapping von aussen — Qt-Limitation, akzeptiert

### P20 Abspielhistorie
- **Club → Lokation**: Generalisierter Kontext (Club oder Special). Unterscheidung nur per Name (z.B. "Sommer-Special 2026"). Kein separates event_date-Feld.
- **Drei-Schichten-Architektur** (umgesetzt):
  1. `play_history` — unveraenderliches Protokoll (nur INSERTs): song_id, location_id, played_at
  2. `song_location_stats` — materialisierter Cache (song_id + location_id = PK, last_played, play_count)
  3. Berechnung "days_since" on-the-fly: `julianday('now') - julianday(last_played)` (fuer spaetere Empfehlungen)
- **Log-Zeitpunkt**: Bei Play-Start (nicht bei Resume aus Pause). `engine.paused` VOR `engine.play()` pruefen.
- **Cache-Update**: INSERT play_history + UPSERT song_location_stats (ON CONFLICT DO UPDATE)
- **Cache nur wenn Lokation gesetzt**: Plays ohne Lokation landen nur in play_history, nicht im Stats-Cache
- **Lokation-Wechsel**: Einfacher LEFT JOIN auf song_location_stats → O(Songs) statt O(Songs × History)
- **Cache-Rebuild**: `rebuild_stats_cache()` regeneriert aus play_history (Sicherheitsnetz)
- **IDs**: AUTOINCREMENT garantiert niemals Wiederverwendung — wichtig fuer Foreign Keys in Historie
- **Songliste**: QListWidget → QTableWidget mit 2 Spalten (Titel + Gespielt). HeaderView.Stretch fuer Titel, ResizeToContents fuer Datum.
- **Datumsformat**: INI-Setting `display/date_format` (de = DD.MM.YY, us = MM/DD/YY). Toggle im Ansicht-Menue.
- **Migration-Reihenfolge**: `_migrate()` MUSS vor `_create_tables()` laufen. Sonst erstellt `CREATE TABLE IF NOT EXISTS locations` eine leere Tabelle, bevor `ALTER TABLE clubs RENAME TO locations` die Daten uebertragen kann.
- **Migrations-Sonderfall**: Falls clubs UND locations beide existieren (abgebrochener erster Start), werden Daten manuell kopiert und clubs-Tabelle geloescht.
- **Neue Spalte = nur ins `_CREATE_*`** (seit intern#145, stehen in `song_db_schema.py`). Bestehende DBs bekommen sie beim Start automatisch: `_add_missing_columns()` fuehrt die `_CREATE_*` in einer In-Memory-DB aus und baut aus `PRAGMA table_info` das `ADD COLUMN`. Nicht nachruestbar sind PRIMARY KEY, UNIQUE, FOREIGN KEY, NOT NULL ohne Standardwert und eine Funktion als Standardwert; so eine Spalte braucht eine eigene Migration. `tests/db/test_schema.py` wird dann rot. Neue Tabelle: zusaetzlich in `_TABLE_SCHEMAS` eintragen (Test prueft das). `_DATA_FIXES` enthaelt nur noch Daten-Korrekturen und laeuft nach `_create_tables()`.
- **Update von beliebig alten Staenden**: Caller ueberspringen oft Versionen. `tests/db/schemas/` haelt reine Schema-Abbilder (ohne Daten) aller bekannten Altstaende; jeder Testlauf prueft den Update-Weg von jedem davon. Mit jedem Release kommt eins dazu: `python tests/db/test_schema.py 2.0.X`.
- **Fremdschluessel brauchen ihr Ziel**: Mit `PRAGMA foreign_keys=ON` scheitert ein INSERT in eine Tabelle, deren FK-Zieltabelle noch fehlt, auch wenn kein einziger Wert darauf zeigt. Darum legt `_migrate_location_programs()` vorher `dance_programs` an. Ohne das startete die App mit DBs von vor den Tanzprogrammen nicht (intern#145, T5 vom Maerz 2026).

## SVG-Icons in Qt QSS

### Arrow-SVGs (SpinBox, ComboBox) — KRITISCH
- **Format**: MUESSEN `width="8" height="5" viewBox="0 0 8 5"` mit gefuelltem `<polygon>` verwenden
- **Passend zur QSS-Angabe**: `width: 8px; height: 5px;` in den Sub-Controls
- **NICHT** 24x24 ViewBox mit `stroke`-Pfaden verwenden — Qt skaliert auf 8x5 herunter, Strokes werden unsichtbar duenn
- **Bewaehrtes Format**:
  - Up: `<polygon points="4,0 8,5 0,5" fill="#farbe"/>`
  - Down: `<polygon points="0,0 8,0 4,5" fill="#farbe"/>`
- **Mehrfach getestet**: Stroke-basierte SVGs erscheinen trotz korrekter Farbe (#000000) als unsichtbar in SpinBox-Pfeilen

### Dock-Icons (close, float)
- 24x24px, stroke-width 2.2-2.5 ist OK (werden nicht so stark skaliert)
- Auf `QDockWidget` Selector setzen: `titlebar-close-icon` und `titlebar-normal-icon`
- **NICHT** `image:` auf `::close-button`/`::float-button` Sub-Controls — erzeugt Ueberlappung

### Lupen/Gear-Icons
- 24x24 mit stroke ist OK (werden via `image:` in groesseren Bereichen angezeigt)

### Qt SVG-Caching
- Qt cached SVG-Icons die via QSS `image: url()` geladen werden
- Bei Aenderungen: Theme-Reload noetig (Skin-Wechsel oder App-Neustart), nicht nur Datei-Austausch
- `SkinManager.load()` + `QApplication.setStyleSheet()` erzwingt Neuauswertung

### Theme-spezifische Icon-Farben
- `title_icon` Variable in skin.json steuert Dock-Titlebar-Icons (z.B. dark: #f7f7f7, light: #ffffff, gold: #2a2518)
- Arrow-SVGs und Close/Float-SVGs haben jeweils eigene Dateien pro Theme-Ordner
- Bei neuem Theme: Alle SVGs im Theme-Ordner mit passenden Farben erstellen

### App-weite Keyboard-Shortcuts (EventFilter statt QShortcut)
- **Problem**: `QShortcut` mit `ApplicationShortcut`-Context wird von QTableWidget/QListWidget type-to-search verschluckt (einzelne Buchstaben wie L, P)
- **Loesung**: `QApplication.instance().installEventFilter(self)` auf MainWindow
- **eventFilter()** prueft: `event.type() == QEvent.KeyPress`, `event.modifiers() == Qt.NoModifier`, dann `event.text().lower()` auswerten
- **Guard 1**: `_is_text_input_focused()` → laesst Buchstaben in SpinBox/LineEdit/TextEdit durch
- **Guard 2**: `QApplication.activeModalWidget()` → blockiert Shortcuts bei offenen Dialogen
- **Floating Dock Fokus**: `dock.activateWindow()` VOR `widget.setFocus()` aufrufen, da floating QDockWidgets kein Keyboard-Input empfangen ohne vorherige Aktivierung
- **Startup-Fokus**: `song_list.table.setFocus()` nach Layout-Restore setzen, sonst blockiert fokussierter SpinBox die Shortcuts

## Windows Defender und PyInstaller-EXEs

### Erster Start nach Update: deutlich langsamer
- Windows Defender scannt beim **ersten Start** alle neuen/geaenderten Dateien im PyInstaller-Bundle
- Besonders betroffen: der erste `addDockWidget()`-Aufruf, weil Qt dort intern DLLs laedt — genau dann laufen Defender-Scans parallel
- **Messung**: Erster Start 4683ms fuer Player-addDockWidget, zweiter Start 735ms (gleicher PC, gleiche App)
- Ab dem zweiten Start ist alles normal — Defender hat gecacht

### Empfehlung fuer Kunden
- In der Installationsanleitung und im Changelog bei jedem Release hinweisen:
  > "Beim ersten Start nach einem Update kann die App einige Sekunden laenger brauchen — Windows Defender scannt die neuen Dateien. Ab dem zweiten Start ist alles normal."
- Wer die App taeglich nutzt: App-Ordner in Windows-Sicherheit → Virenschutz → Ausnahmen eintragen. Dann entfaellt der Scan komplett.

### Faustregel beim Performance-Messen
- Immer **zweiten Start** als Baseline nehmen — erster Start hat Defender-Overhead
- Beim Testen auf neuer Hardware/frischer Installation immer zweimal starten vor Messung

## Entwicklungsprozess

### Prototyp-Abnahme
- User testet, gibt explizit frei
- Fehler sofort fixen, User testet erneut
- Prototypen koennen mehrere Abnahmekriterien gleichzeitig erfuellen (P5 hat P6 mit abgedeckt)

### Refactoring-Vollstaendigkeitsregel (ab P0.85)

Bei jeder Extraktion von Logik in eine neue Klasse/Komponente **zwei Listen erstellen, bevor angefangen wird**:

1. **Aufbau-Liste**: Was entsteht neu? (neue Klasse, neue Methoden, neue Parameter)
2. **Abbau-Liste**: Welche Symbole/Methoden/Felder werden danach in den alten Klassen ueberfluessig?

**Zweiphasen-Vorgehen** (PFLICHT):
- **Phase 1 — Aufbau**: Neue Komponente implementieren, alte Klassen auf die neue umverdrahten. Alten Code noch NICHT loeschen — er ist das Sicherheitsnetz waehrend des Tests.
- **Warten**: User testet und bestaetigt, dass alles funktioniert.
- **Phase 2 — Abbau**: Erst nach Bestaetigung: grep auf die Abbau-Liste, alle Reste entfernen.

**Bei „Paritaet"-Anforderungen**: Explizit pruefen, ob alle Features des reichhaltigeren Widgets auch im aermeren ankommen — nicht nur die Huelle.

Hintergrund: In P0.85 wurde `SongFilterBar` als gemeinsame Komponente extrahiert. Die alte `PlaylistManagerWidget` hatte danach noch duplizierte State-Felder (`_custom_slots`, `_permanent_state`) und Methoden, weil nur der Aufbau, nicht der Abbau sauber durchgefuehrt wurde. `SongListWidget` bekam ausserdem nur `show_genre=False` statt voller Paritaet, obwohl der User explizit „vereinheitlichen" gefordert hatte.

### Haeufige Fehlerquellen
- Parameter-Mismatch zwischen Modulen (syn_hop v1→v2)
- Inverse Formeln (pitch_ratio vs 1/pitch_ratio)
- Threading: Audio-Callback + UI-Thread greifen auf gleiche Buffer zu
- Feed-Position vs. Hoerposition: nicht dasselbe wegen Pufferung
- While-Schleifen-Bedingung vs. innere Pruefung: Loop-Back-Code muss VOR der Abbruchbedingung pruefen (P16 Loop-Bug)
