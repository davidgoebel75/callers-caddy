# F6.8 Playlist

## Laufzeit-Playlist (PlaylistWidget — Tab neben Songliste)
- Registerkarte im Songbereich (getabbt mit Songliste)
- Zeigt aktuelle Playlist: # | P/S | Titel
- Gespielte Songs ausgegraut, aktueller Song hervorgehoben
- Reorder-Buttons (▲/▼) zum Umsortieren
- Laden/Speichern als .txt-Dateien
- Einfach-Klick → Song vorgeladen (kein Auto-Play)
- Doppelklick → Song aus Playlist entfernen

## Playlist-Manager (PlaylistManagerWidget — eigenes Dock)
- Zwei-Panel-Layout: Song-Pool (links) + Playlist-Spiegel (rechts)
- Dazwischen: Transfer-Buttons (▶/◀) + Confirm-Button (✔, grün)
- Änderungen werden sofort im PlaylistWidget reflektiert (shared data)

### Song-Pool (linke Seite)
- Alle Songs aus der DB
- **Filter** (RadioButtons): Alle | Pattern | Singing
- **Sortierung** (ComboBox): Alphabetisch | Qualität | Zuletzt gespielt | Empfehlung
- Empfehlung = Songqualität × Tage seit letztem Abspielen im aktuellen Kontext (Lokation)
- Doppelklick oder ▶ → Song zur Playlist hinzufügen

### Playlist-Spiegel (rechte Seite)
- Spiegelt PlaylistWidget-Daten
- Drag & Drop: Zwischen Pool und Playlist + Reorder innerhalb Playlist
- Reorder-Buttons (▲/▼), Laden/Speichern
- Doppelklick oder ◀ → Song aus Playlist entfernen

### Confirm-Button
- Grüner Haken (✔) zwischen den Listen
- Schliesst Manager-Dock (Playlist bleibt erhalten)
- Wiederverwendbarer QSS-Style: `QPushButton[confirm="true"]`

## Auto-Advance
- Song-Ende (natürlich) → nächster unbearbeiteter Playlist-Song wird vorgeladen
- Stop-Button → gleicher Auto-Advance (Caller ist fertig mit Song)
- Fade-Out → linearer Volume-Ramp, dann Auto-Advance
- Nächster Song wird vorbereitet, startet erst bei Play

## Fade-Out
- Linearer Volume-Ramp im Audio-Callback (sample-genau)
- Dauer konfigurierbar: INI `[playlist] fade_out_time=3` (Default 3 Sekunden)
- Während Fade: Status "Fade Out...", Pause/Fade-Buttons deaktiviert
- Am Ende: gleicher Trigger wie natürliches Song-Ende

## Dateiformat (.txt)
- Eine Zeile pro Song: `P dateiname.mp3` oder `S dateiname.mp3`
- P = Pattern, S = Singing Call
- Gespeichert im `playlist_dir` (Default: `../playlists`)
- Beim Laden: Dateiname-Lookup in DB, nicht gefundene Songs → Warnung

## Technische Details
- Custom QTableWidget-Subklassen: `_PoolTable` (DragOnly), `_PlaylistTable` (DragDrop)
- MIME-Data: `pool:<song_id>` bzw. `playlist:<row_index>`
- Timer-basierte Song-Ende-Erkennung (nicht Signal aus Audio-Thread)
- WSOLA `can_process()` statt `input_available() <= 0` für Song-Ende

---

# F6.10 Kontexte

## Lokationen (ehemals "Clubs")
- Generalisiert: Club + Special unter einem Begriff "Lokation"
- Dauerhafte Kontexte (z.B. "SquareBreakers")

## Specials / Veranstaltungen
- Kontexte mit eigenem Termincharakter

## Session-Start
- Caller wählt aktuelle Lokation über Button im Player
- Lokation beeinflusst: Historie, Empfehlungen, Notizen, GEMA-Export
- Kein Lokation gewählt → Warn-Button (rot)

---

# F6.11 Abspielhistorie
- Pro Abspielvorgang: Song + Zeitpunkt + Lokation
- Lokationsbezogen: wann lief Song zuletzt in Lokation X?
- Veranstaltungsbezogen: Musikfolgeliste eines Specials
- Drei-Schichten-Architektur: play_history (Rohdaten), song_location_stats (Aggregate), On-the-Fly (UI)
