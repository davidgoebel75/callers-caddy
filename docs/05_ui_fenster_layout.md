# F6.17 Fenster, Module, Docking und Layout

## Grundprinzipien
- Module sind verschiebbar
- Magnetisches Andocken (Docking/Snapping)
- Nicht jedes Modul gleich skalierbar → eigene Layoutregeln pro Modul

## Resize-Regeln
| Modul | Breite | Höhe |
|-------|--------|------|
| Player | fest oder proportional | fest oder proportional |
| Songbereich | an Player gekoppelt | frei |
| Lyrics-Fenster | frei | frei |
| Foto-Fenster | frei | frei |
| Info-Fenster | frei | frei |

## Tabbed Docking (Registerkarten)
- Mehrere Module koennen im gleichen Bereich als Registerkarten gestapelt werden
- Anwendungsfall: Lyrics-Fenster und Sequenzen-Fenster im gleichen Dock-Bereich
  als Registerkarten → spart Platz, schneller Wechsel
- Qt: `AllowTabbedDocks` + `AllowNestedDocks` aktiviert (ab P19)
- Fenster von aussen andocken: Floating-Window zurueck in den Hauptbereich ziehen

## Layout-Persistenz
- Letzte Positionen, Grössen, Sichtbarkeiten speichern
- Beim Neustart wiederherstellen
- Mehrere Layouts → Backlog (spätere Version)

## F6.18 Fenstersteuerung über Player
- Buttons am unteren Rand des Players
- Ein-/Ausblenden: Songliste, Playlist, Lyrics, Notes, Foto, Einstellungen
- Sichtbarkeitszustand am Button erkennbar
- Beim Wiederöffnen: letzte Position + Grösse

## F6.19 Einstellungen
- Konfigurierbare Ordner: Songs, neue Songs, Lyrics
- Schwellwerte Pattern-Dauer-Warnung
- Layout-Speicherung
- Hotkeys → später
- **Skin-Faehigkeit** → sehr spaet: User koennen unterschiedliche Skins/Themes laden (z.B. via Qt Stylesheets)

## F6.20 Crash-Recovery
- Erkennung unreguläres Beenden
- Beim Neustart: Wiederherstellung anbieten
- Wiederherstellen: aktueller Song, Playlist, Kontext, heutiges Tempo
