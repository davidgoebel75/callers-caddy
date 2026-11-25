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

## Choreo-Ergebnis (sequence_choreo, intern#247)
- sequence_id: Sequenz (Primaerschluessel, kein Fremdschluessel)
- input_hash: Kartenzeilen, Typ, App-Callnamen dieser Zeilen, Mapping-Stand, Ergebnisform
- engine_ver: Pruefsumme der Engine-Datei (tam_cli)
- result_json: Urteil, Beats je Zeile, Summe, Abbruchzeile, Hinweise (ohne Animation)
- Abgeleiteter Zwischenspeicher fuer Square Flow: passt Hash oder Engine nicht mehr, wird
  neu gerechnet und ueberschrieben. Geschrieben aus dem Hintergrund-Thread ueber eine
  eigene kurze Verbindung. Darf jederzeit geleert werden.

## Beats je Call (call_timing, intern#164)
- Referenzdaten nach den CALLERLAB-Timing-Charts, eine Zeile je Call und Variante
- programm, call, variante: wie in der Chart; entity_ids: App-Calls als Text
  ('a|b' = einer davon, 'a+b' = beide zusammen)
- typ: fest, bereich, dynamisch, not_timed, call_plus, plus_call, max
- beats, beats_bis: Wert bzw. Bereich; anything_ab: ab welchem Teil "(Anything)" zaehlt
- standard: 1 = diese Variante gilt, wenn die Karte nichts anderes sagt;
  variante_regel: woran eine andere Variante erkannt wird
- quelle, bemerkung: Chart-Stand und Hinweis (ohne Namen)
- id = Reihenfolge der Quelldatei src/callerlab_timing.json
- Wird beim Start komplett ersetzt, wenn die Version der Datei nicht zur Marke
  callerlab_timing_version in app_meta passt. Nutzer pflegen hier nichts.

Details: siehe docs/13_sequenzen.md
