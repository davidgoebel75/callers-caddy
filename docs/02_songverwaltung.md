# F6.6 Songliste und Songverwaltung

## Songbereich
- Unter dem Player, Registerkarten: Songliste | Playlist
- Scrollbar, Substring-Suche (Name + andere Textfelder)
- Klick = laden (nicht starten)

## Song-Datenfelder
- Dateiname (technisch, unveränderlich)
- Titel (editierbar, beim Import = Dateiname)
- Label
- Qualität (numerische Skala, 0-9 oder 0-10, Migration entscheidet)
- Basis-BPM
- Standard-Tempo
- Pitch
- Lautstärke
- Loop-In, Loop-Out
- Lyrics-Dateiname
- is_pattern (Boolean, Default: 1 = ja)
- is_singing (Boolean, Default: 1 = ja)

## F6.7 Import-Workflow
- Bibliotheksordner + separater Importordner ("Neu")
- Neue Songs im Importordner werden erkannt → Bibliotheksordner
- Import erzeugt: Dateiname, Titel (= Dateiname)
- Loop-In = Anfang, Loop-Out = Ende
- is_pattern = 1, is_singing = 1 (beide angehakt)
- Auto-BPM wenn technisch möglich
- Nur Dateiname gespeichert, KEINE absoluten Pfade
- Alle Pfade relativ → Installation kopierbar

### Bulk-Import (geplant)
- Mehrere Songs gleichzeitig importieren (Ordner oder Mehrfachauswahl)
- VOR dem Import: Auswahl des Song-Typs (Pattern, Singing Call, beides)
- Gewaehlter Typ wird auf alle importierten Songs angewendet
- Einzelne Songs koennen danach im Song-Daten-Panel geaendert werden
