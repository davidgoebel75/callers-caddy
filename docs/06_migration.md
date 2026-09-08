# F6.21 Migration

## Quellsystem: Callers Caddy 1.0 (Access 97)

### Programmordner-Struktur
```
CallersCaddy/
├── caller.mdb              ← Access 97 Datenbank (Jet 3.5, 1.5 MB)
├── caller.ini              ← Konfiguration (Pfade, User, Pattern, Playlist)
├── Songs/ok/               ← 764 MP3-Dateien
├── Lyric/                  ← 411 Lyric-Dateien (.rtf, .doc, .htm)
├── notes/                  ← Notizen pro Gruppe (z.B. "FLHH Club.txt")
├── Playlists/              ← 27 Playlist-Dateien (Format: "P Songname")
├── Gimmick/                ← Gimmick-Dateien (.rtf)
├── Teaching/               ← Teaching-Dateien
├── backup/                 ← Backup (caller.exe, .mdb, .ini, .ini-Dateien)
├── ratings.ini             ← Rating-Skala Singing (0-9)
├── ratingp.ini             ← Rating-Skala Pattern (0-9)
├── tempo.ini               ← Tempo-Skala (0-9: "Schnarch" bis "Hot Hash")
├── genre.ini               ← Genre-Liste (NEW, Country, Gospel, Pop, ...)
├── Grouptypes.ini          ← Gruppentypen (Club, Class, Special, Demo)
├── english.ini             ← Sprachdatei (DE→EN Übersetzungen)
└── caller_*.mdb            ← MDBs anderer Caller (für Multi-User-Support)
```

### Datenbank-Schema (caller.mdb, Version 1.1)

#### Song (520 Einträge) — WICHTIGSTE TABELLE
| Spalte | Typ | Beschreibung | Migration |
|--------|-----|-------------|-----------|
| ID | Integer | Primary Key | → songs.id (oder neu) |
| Name | Text | Songtitel | → songs.title |
| Artist | Text | Interpret (oft NULL) | → songs.artist |
| Label | Text | Label + Nummer (z.B. "HH 648") | → songs.label |
| Genre | Text | Genre (aus genre.ini) | → songs.genre |
| Songtype | Text | "HD"=Hoedown, "SC"=Singing Call, ... | → songs.is_pattern/is_singing |
| URL_Music | Text | MP3-Dateiname (ohne Pfad) | → songs.filename |
| URL_Vocal | Text | Vocal-Track (selten benutzt) | ggf. ignorieren |
| URL_Lyric | Text | Lyric-Dateiname | → songs.lyric_file |
| Volume | Integer | Lautstärke (Default 100) | → songs.volume |
| Speed | Float | Tempo-Änderung (0.0 = neutral) | → songs.tempo |
| Pitch | Float | Pitch-Änderung (0.0 = neutral) | → songs.pitch |
| BPM | Float | Beats per Minute | → songs.bpm |
| Loop | Boolean | Loop aktiv? | → songs.loop_active |
| Loop_Start | Text(!) | Loop-In (Millisekunden als String) | → songs.loop_in (Samples!) |
| Loop_End | Text(!) | Loop-Out (Millisekunden als String) | → songs.loop_out (Samples!) |
| Laenge | Text(!) | Songlänge in ms | informativ |
| Rating_Singing | Text | Qualität Singing (0-9, manchmal "6 OK") | → songs.quality_singing |
| Rating_Pattern | Text | Qualität Pattern (0-9, manchmal "5 OK") | → songs.quality_pattern |
| Tempo | Text | Tempo-Bewertung (0-9, aus tempo.ini) | → songs.tempo_rating |

**Achtung**: Loop_Start, Loop_End, Laenge sind Strings (mit Leerzeichen!), nicht numerisch.
Speed/Pitch sind Floats (0.0 = neutral), nicht Prozentwerte.

#### gruppen (45 Einträge) → Lokationen
| Spalte | Typ | Beschreibung | Migration |
|--------|-----|-------------|-----------|
| id | Integer | Primary Key | → locations.id |
| name | Text | Gruppenname | → locations.name |
| plz | Text | PLZ | informativ (V2) |
| ort | Text | Stadt | informativ (V2) |
| strasse | Text | Straße | informativ (V2) |
| telefon | Text | Telefon | informativ (V2) |
| kontaktname | Text | Kontaktperson | informativ (V2) |
| kontaktplz/ort/strasse/telefon | Text | Kontaktdaten | informativ (V2) |
| tanzort | Text | Tanz-Location | informativ (V2) |

#### Historie (4830 Einträge) → play_history
| Spalte | Typ | Beschreibung | Migration |
|--------|-----|-------------|-----------|
| datum | DateTime | Zeitstempel | → play_history.played_at |
| gruppe | Text | Gruppenname (nicht ID!) | → play_history.location_id (Lookup) |
| titel | Text | Songtitel (nicht ID!) | → play_history.song_id (Lookup) |

**Achtung**: Historie referenziert Songs und Gruppen per NAME, nicht per ID!
Matching muss fuzzy sein (Tippfehler, Umlaute, gelöschte Songs möglich).

#### Sequenzen (885 Einträge) — Choreographie-Sequenzen
| Spalte | Typ | Beschreibung |
|--------|-----|-------------|
| ID | Integer | Primary Key |
| Feld1-Feld15 | Text | Einzelne Figuren der Sequenz |
| Level | Text | "MS", "Plus", etc. |
| Skill | Text | Schwierigkeitsgrad (meist NULL) |

#### Order (885) — Figur-Referenzen (parallel zu Sequenzen, gleiche IDs)
#### AlleFiguren (1026) — Figurenliste (Figur + Alias)
#### AuswahlFiguren (176) — Figuren für Dropdown/Filter
#### Figur (1019) — Figuren mit Order-Sortierung
#### Gimmicks (8) — Gimmick-Dateien (Name + URL)
#### Teaching (2) — Teaching-Dateien (kaum benutzt)
#### version (1) — DB-Version: "1.1"

### INI-Dateien

#### caller.ini
```ini
[SONGS]
ABSOLUTEPATH = 1
PATH1-4 = Pfade zu Song-Ordnern

[DATABASE]
DBFILE = Pfad zur MDB (auskommentiert = Default)

[USER]
NAME = "David Goebel"
LANGUAGE = DEUTSCH
ADVANCEDMODE = 1

[PATTERN]
TIME1/TIME2 = Pattern-Timing (Minuten)
TESTJUMP/DELTA = Loop-Test-Parameter

[PLAYLIST]
DEFAULT_SONGTYPE = 2
DEFAULT_SORTTYPE = 4
AUTONEXTSONG = 1
```

#### Skalen (ratings.ini, ratingp.ini, tempo.ini)
- 0-9 Skala mit optionalem Label
- Rating: 0="Besser Nicht" ... 5="OK" ... 9="Super"
- Tempo: 0="Schnarch" ... 5="OK" ... 9="Hot Hash"

#### genre.ini
Einfache Liste: NEW, Country, Gospel, Pop, Rock, Musical, Lovesong, Elvis, Weihnachten, ABBA, Lizenz

#### Grouptypes.ini
Club, Class, Special, Demo

### Playlists (Dateiformat)
- Format: `P Songname` oder `S Songname` (pro Zeile)
- Dateiname-Konvention: `{KÜRZEL}-{DATUM}.txt` (z.B. "SB-2024-06-28.txt")
- **Identisches Format wie in Callers Caddy 2.0!**

### Notes (pro Gruppe)
- Textdateien im `notes/`-Ordner
- Dateiname = Gruppenname (z.B. "FLHH Club.txt")
- Inhalt: Freitext (z.B. Teaching-Notes, Workshop-Themen)

### Lyrics
- 411 Dateien in verschiedenen Formaten: .rtf, .doc, .htm
- Zuordnung über Song.URL_Lyric in der DB

---

## Quellsystem: SquareView (SQLite)
- Import angestrebt, Umfang anhand verfügbarem Format zu definieren
- **Speicherformat: SQLite** — Migration SQLite → SQLite

---

## Migrationsstrategie

### Phase 1: Pflicht-Migration (Callers Caddy 1.0)
1. **Song-Tabelle** → songs (Titel, Dateiname, Tempo, Pitch, Volume, BPM, Loop, Ratings)
2. **gruppen** → locations (Name, Typ)
3. **Historie** → play_history (Datum, Lokation, Song — per Name-Matching)
4. **Playlists** → direkte Kopie (gleiches Dateiformat!)
5. **Notes** → direkte Kopie ins notes/-Verzeichnis
6. **Lyrics** → direkte Kopie ins lyric/-Verzeichnis
7. **MP3s** → Kopie/Verlinkung ins songs/-Verzeichnis

### Phase 2: Sequenzen (→ docs/13_sequenzen.md)
- Sequenzen/Order/Figuren → Sequenzen-Modul (Cached Live-Mapping)
- Gimmicks → eigenes Modul
- Gruppen-Kontaktdaten → erweiterte Lokationsverwaltung

### Konvertierungen (GEKLÄRT)
| Alt | Neu | Konvertierung |
|-----|-----|---------------|
| Speed 0.0 | tempo 1.0 | `1.0 + (speed / 100.0)` — Speed 0=100%, 5=105%, -3=97% |
| Pitch 0.0 | pitch 0.0 | Identisch (Halbtöne, negativer Wert = tiefer) |
| Loop_Start " 18120" | loop_in (Samples) | `int(ms_string.strip()) / 1000 * sample_rate` |
| Loop_End " 245406" | loop_out (Samples) | `int(ms_string.strip()) / 1000 * sample_rate` |
| Songtype | is_pattern/is_singing | Siehe Mapping unten |
| Rating "6 OK" | quality (int) | Erste Ziffer extrahieren |
| gruppe (Name) | location_id | Name-Matching gegen locations |
| titel (Name) | song_id | Name-Matching gegen songs |

#### Songtype-Mapping (Ist-Werte aus DB)
| Alter Wert | Anzahl | is_pattern | is_singing | Bedeutung |
|------------|--------|-----------|-----------|-----------|
| HD | 164x | True | False | Hoedown (= Pattern) |
| SD | 323x | False | True | Singing Call (SD war alter Name) |
| HDSD | 12x | True | True | Beides |
| SD,HD | 13x | True | True | Beides (alternatives Format) |
| X | 7x | False | False | Sonstige/Unbekannt |
| 2 | 1x | ? | ? | Vermutlich Datenfehler |

#### Speed-Verteilung (194 von 520 Songs haben Speed != 0)
- Bereich: -19 bis +75 (Ausreißer +75 ist vermutlich Fehler)
- Typisch: -10 bis +20 (entspricht 90% bis 120%)

### Technische Details
- **Access 97 (Jet 3.5)**: Aktueller ODBC-Treiber kann Jet 3.5 NICHT öffnen!
- **Lösung**: Python-Paket `access-parser` (Pure Python, liest Jet 3.5)
- **Encoding**: CP1252 (Windows Latin-1), Umlaute müssen konvertiert werden

---

## Migrations-App (Standalone)

### Konzept
Eigenständige PySide6-App, die **außerhalb** des Callers Caddy läuft.
Voraussetzung: Ein alter Callers Caddy 1.0 UND ein neuer Callers Caddy 2.0 sind installiert.

### UI-Layout
```
┌──────────────────────────────────────────────────┐
│  Callers Caddy Migration                         │
├──────────────────────────────────────────────────┤
│                                                  │
│  QUELLE (Callers Caddy 1.0)                      │
│  ┌──────────────────────────────────┐            │
│  │ Datenbank (.mdb): [___________] [📂]         │
│  │ Songs-Ordner:     [___________] [📂]         │
│  │ Lyrics-Ordner:    [___________] [📂]         │
│  │ Playlists-Ordner: [___________] [📂]         │
│  │ Notes-Ordner:     [___________] [📂]         │
│  └──────────────────────────────────┘            │
│                                                  │
│  ZIEL (Callers Caddy 2.0)                        │
│  ┌──────────────────────────────────┐            │
│  │ Programmordner:   [___________] [📂]         │
│  └──────────────────────────────────┘            │
│                                                  │
│  STATUS                                          │
│  ┌──────────────────────────────────┐            │
│  │ ✓ Datenbank gefunden (520 Songs) │            │
│  │ ✓ Songs-Ordner (764 MP3s)        │            │
│  │ ✓ Lyrics-Ordner (411 Dateien)    │            │
│  │ ✓ Playlists (27 Dateien)         │            │
│  │ ✓ Notes (9 Gruppen)              │            │
│  │ ✓ Zielordner bereit              │            │
│  └──────────────────────────────────┘            │
│                                                  │
│  [Vorschau]              [✔ Migrieren]           │
│  (grau bis alles OK)     (grün wenn bereit)      │
│                                                  │
│  Fortschritt: ████████████░░░ 75%                │
│  Songs: 390/520 | Historie: 4830/4830            │
└──────────────────────────────────────────────────┘
```

### Features
- **Auto-Detect**: Beim Wählen der MDB werden die Standard-Ordner (Songs/ok, Lyric, Playlists, notes) automatisch vorgeschlagen
- **Validierung**: Status-Bereich zeigt Häkchen/Warnungen für jeden Bereich
- **Vorschau**: Zeigt was migriert wird, bevor es losgeht
- **Migrieren-Button**: Grün (confirm-Style) nur wenn alle Pflichtfelder OK
- **Fortschrittsbalken**: Songs, Historie, Dateikopien
- **Log-Ausgabe**: Detailliertes Log mit Warnungen (fehlende MP3s, nicht-matchbare Historie-Einträge)

### Migrationsschritte (intern)
1. MDB lesen (access-parser)
2. Songs → SQLite (mit Speed/Pitch/Loop-Konvertierung)
3. Gruppen → Lokationen
4. Historie → play_history (Name-Matching mit Warnung bei Nicht-Treffer)
5. MP3-Dateien kopieren/verlinken
6. Lyrics kopieren
7. Playlists kopieren (gleiches Format)
8. Notes kopieren
9. Zusammenfassung + Log

### Tech-Stack
- Python + PySide6 (gleicher Stack wie Callers Caddy)
- access-parser (Pure Python, kein ODBC nötig)
- Eigenes Repo/Ordner: `tools/migration/`

## Ziel
- Für Anwender einfach: installieren → Ordner wählen → Migrieren klicken → fertig
- Eigenständiges Tool, kein Teil des Hauptprogramms
