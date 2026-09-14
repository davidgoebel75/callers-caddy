# Fachliches Datenmodell

## Song
- Dateiname
- Titel (editierbar)
- Label
- Qualität (numerische Skala)
- Basis-BPM
- Standard-Tempo
- Pitch
- Lautstärke
- Loop-In
- Loop-Out
- Lyrics-Datei

## Kontext
- Typ: Club (dauerhaft, ohne Datum) oder Special (mit Termin)
- Name

## Session
- Gewählter Kontext
- Heutiges Tempo
- Aktuelle Playlist
- Aktueller Song

## Historieneintrag (play_history)
- Song-Referenz (song_id → songs.id)
- Kontext-Referenz (club_id → clubs.id, NULL = kein Club)
- Zeitpunkt (played_at, ISO 8601)
- Nur Appends, wird nie geaendert oder geloescht
- Index auf (club_id, song_id, played_at DESC) fuer schnelle Abfragen

## Song-Club-Cache (song_club_stats)
- song_id + club_id = Primary Key (eine Zeile pro Song+Club-Kombination)
- last_played (letztes Spieldatum im Club)
- play_count (Anzahl Abspielungen im Club)
- Wird bei jedem Abspielvorgang aktualisiert (INSERT OR REPLACE)
- "Tage seit letztem Play" wird NICHT gespeichert, sondern on-the-fly berechnet:
  julianday('now') - julianday(last_played)
- Kann jederzeit aus play_history neu aufgebaut werden (Sicherheitsnetz)
- Zweck: Performance — vermeidet teuren GROUP BY ueber gesamte Historie

## Note
- Kontextbezug
- Text
- Status (offen / erledigt)

## Foto
- Bezug zu Session oder Kontext

## Sequenz (sequences)
- field_1 bis field_15: Call-Texte (Original aus MDB-Import)
- level_original: Original-Programmstufe aus MDB
- max_teaching_order: Vorberechneter Cache (hoechste TO aller Calls)

## Sequenz-Calls (sequence_calls)
- sequence_id → sequences.id
- position: 1–15 (Feld-Position)
- call_text: Original-Text
- entity_id: Aufgeloeste Entity-ID (aus Burleson-Vocabulary)
- teaching_order: Zugewiesene Nummer (aus Teaching-Order-Dateien)
- Wird bei Remapping neu berechnet

Details: siehe docs/13_sequenzen.md
