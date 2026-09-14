# Beat Snap Audition — Erkenntnisse und Versuchsprotokoll

## Kontext

Beat Snap Audition simuliert den Loop-Sprung zur Vorhör-Kontrolle:
- Phase 1: Spielt 5 Sekunden vor Loop-Out, Cursor wandert in oberer Waveform
- Phase 2: Seek zum Loop-In, Cursor wandert in unterer Waveform
- Der Loop-Sprung wird per `engine.seek()` simuliert (Engine-Loop-Punkte bleiben unangetastet)

Zwei Testrechner:
- **Build-PC**: Schneller Desktop (Intel Core, viel RAM)
- **Laptop**: Intel N150, schwacher Prozessor, typisch fuer Caller

## Audio-Engine Grundlagen (wichtig fuer alle Versuche)

- `_feed_pos`: Position wo der WSOLA als naechstes Daten liest (NICHT die Wiedergabe-Position)
- `_estimate_playback_pos()`: `_feed_pos - buffered_samples` — eine SCHAETZUNG, kein exakter Wert
- `get_position_seconds()`: Nutzt `_estimate_playback_pos()`, daher ebenfalls eine Schaetzung
- Nach `seek()` wird `flush()` aufgerufen → WSOLA-Buffer leer → Warmup noetig (50ms Stille)
- Waehrend Warmup meldet `get_position_seconds()` eine Position die noch nicht hoerbar ist
- `_feed_pos` eilt der tatsaechlichen Wiedergabe immer voraus (Feed-Ahead fuer WSOLA)

## Versuch 1: Akkumulierter Timer (Original, vor P31)

```
_audition_start_ms += 16   # 60 Hz Timer
elapsed = _audition_start_ms
cursor_pos = aud_start + (elapsed / 1000.0) * tempo
# Phase-Wechsel bei elapsed >= phase1_duration_ms
```

**Build-PC**: Funktioniert gut — Cursor und Audio synchron, sauberer Sprung
**Laptop**:
- Cursor hinkt hinterher (Timer-Ticks kommen unregelmaessig)
- Audio springt BEVOR Cursor den Strich erreicht → 2 sichtbare Spruenge
- Akustisch unsauber (Artefakte beim Seek ohne Warmup)

**Ursachen**:
- Timer-Drift: `+= 16` akkumuliert, aber echte Zeit zwischen Ticks variiert auf schwachem Prozessor
- Kein Seek-Warmup: `seek()` ohne Warmup → WSOLA-Einschwing-Artefakte

## Versuch 2: Seek-Warmup + 30 Hz Timer

Aenderungen:
- `seek()` in audio_engine.py: 50ms Warmup nach flush() waehrend Wiedergabe
- Timer von 16ms/60Hz auf 33ms/30Hz reduziert (CPU-Entlastung)
- Timer-Akkumulation angepasst: `+= 33`

**Build-PC**: Gut — Artefakte weg dank Warmup
**Laptop**:
- Artefakte weg (Warmup wirkt)
- Cursor hinkt NOCH MEHR hinterher (33ms Ticks driften staerker als 16ms)
- Immer noch 2 sichtbare Spruenge (Audio vor Cursor)

**Erkenntnis**: Warmup loest Audio-Artefakte, aber Timer-Drift wird durch groesseres Intervall schlimmer

## Versuch 3: QElapsedTimer (Echtzeit-Messung)

Aenderungen:
- `_audition_start_ms += 33` ersetzt durch `QElapsedTimer.elapsed()` (echte Millisekunden)
- Phase-Wechsel bei `elapsed >= phase1_duration_ms` (Echtzeit)
- `elapsed_timer.restart()` bei Phase-Wechsel

**Build-PC**: SCHLECHTER als vorher!
- Cursor springt ca. einen Takt VOR dem Strich
- 2 sichtbare Spruenge (Cursor-Sprung + Audio-Sprung)
**Laptop**: Ebenfalls schlecht

**Ursache**: Echtzeit ≠ Audio-Zeit!
- Bei Tempo < 1.0: Audio laeuft langsamer als Echtzeit → Cursor zu schnell
- Bei Tempo > 1.0: Audio laeuft schneller als Echtzeit → Cursor zu langsam
- Die Formel `(elapsed_ms / 1000.0) * tempo` multipliziert Echtzeit mit Tempo,
  aber das ist doppelt-gemoppelt: Die Echtzeit IST bereits tempo-beeinflusst
  (der Audio-Stream gibt tempo-angepasste Samples aus)

**Erkenntnis**: QElapsedTimer misst Wanduhr-Zeit, nicht Audio-Stream-Zeit.
Der akkumulierte Timer war naeher dran, weil er in "UI-Ticks" zaehlt
und die Tempo-Umrechnung konsistent anwendet.

## Versuch 4: Engine-Position als Source of Truth

Aenderungen:
- Cursor-Position = `engine.get_position_seconds()` (kein Timer, keine Berechnung)
- Phase-Wechsel wenn `pos >= aud_out - 0.05`

**Build-PC**: SCHLECHT
- Cursor springt weit vor der Linie (geschaetzte Position eilt voraus)
- Akustisch unsauberer Uebergang
**Laptop**: Ebenfalls schlecht

**Ursachen**:
1. `get_position_seconds()` basiert auf `_estimate_playback_pos()` = `_feed_pos - buffered`
2. `_feed_pos` eilt voraus (Feed-Ahead fuer WSOLA, mehrere tausend Samples)
3. Die Buffer-Schaetzung (`stretcher.input_available()`) ist ungenau
4. Ergebnis: Gemeldete Position ist systematisch VORAUS gegenueber der tatsaechlichen Wiedergabe
5. Phase-Wechsel-Trigger `pos >= aud_out - 0.05` feuert zu frueh
6. Nach Seek: Warmup-Phase (50ms Stille) — waehrenddessen meldet die Position schon den neuen Bereich, aber es ist noch nichts zu hoeren

**Erkenntnis**: `engine.get_position_seconds()` ist fuer grobe Slider-Darstellung OK,
aber NICHT praezise genug fuer frame-genaue Cursor-Synchronisation im Beat Snap.

## Versuch 5: Sample-Counter im Audio-Callback (Hybrid)

Aenderungen in audio_engine.py:
- Neues Feld `_playback_sample`: Zaehlt tatsaechlich ausgegebene Samples im Callback
- `_callback()`: `self._playback_sample += frames` nach `outdata[:] = stretched`
- `seek()`: `self._playback_sample = target` (auf Seek-Position setzen)
- `load()`: `self._playback_sample = 0`
- `stop()`: `self._playback_sample = self._feed_pos`
- Neue Methode `get_playback_position_seconds()`: `_playback_sample / sample_rate`

Aenderungen in beat_snap_dialog.py:
- Cursor-Position = `engine.get_playback_position_seconds()` (Sample-Counter)
- Phase-Wechsel wenn `pos >= aud_out` (kein Offset noetig, Counter ist exakt)

Warum das funktionieren sollte:
- Counter zaehlt NUR was tatsaechlich an die Soundkarte geht
- Kein Feed-Ahead-Offset (wie bei `_feed_pos`)
- Kein Buffer-Schaetzen (wie bei `_estimate_playback_pos`)
- Kein Timer-Drift (wie bei akkumuliertem Timer)
- Kein Echtzeit-vs-Audio-Zeit-Problem (wie bei QElapsedTimer)
- Warmup-Frames (Stille) werden NICHT gezaehlt (Callback returnt vorher)
- Thread-sicher: int-Zuweisung in Python ist atomar, lesen aus UI-Thread ist OK

**Build-PC**: Springt ca. einen Takt zu frueh, doppelter Sprung
**Laptop**: Gleich schlecht

**Ursache gefunden (erst nach Versuch 5 erkannt)**:
Der Sample-Counter selbst ist korrekt, aber das EIGENTLICHE Problem war
die ganze Zeit ein anderes: Die Engine hat einen eigenen Loop in
`_feed_stretcher()` (Zeile 251-254), der bei `_feed_pos >= _loop_out`
automatisch zurueckspringt. Dieser Feed-Loop passiert im FEED-AHEAD
(~0.5s vor der tatsaechlichen Wiedergabe), also BEVOR das Audio den
Loop-Punkt erreicht. Das erzeugt den "zu fruehen" ersten Sprung.
Der Beat-Snap-Dialog erkennt spaeter die Position und macht seinen
eigenen Seek → zweiter Sprung.

## Versuch 6: Engine-Loop deaktivieren + Sample-Counter ✅ LOESUNG

Aenderung: `_loop_active = False` waehrend Audition, Wiederherstellung in `_stop_audition()`.

Damit spielt die Engine linear (ohne eigenen Loop-Sprung). Der Beat-Snap-Dialog
steuert den einzigen Loop-Sprung allein per `seek()`, getriggert durch den
Playback-Sample-Counter.

Implementierung in beat_snap_dialog.py:
```python
def _on_audition(self):
    self._stop_audition()
    # Engine-Loop waehrend Audition DEAKTIVIEREN
    self._saved_loop_active = self._engine._loop_active
    self._engine._loop_active = False
    # ... seek + play ...

def _stop_audition(self):
    # Engine-Loop ZUERST wiederherstellen (vor stop())
    if hasattr(self, '_saved_loop_active'):
        self._engine._loop_active = self._saved_loop_active
    if self._engine.is_playing():
        self._engine.stop()

def _update_cursor(self):
    pos = self._engine.get_playback_position_seconds()
    if self._audition_phase == 1:
        if pos >= self._aud_out and not self._jump_done:
            self._engine.seek(self._aud_in)
            self._jump_done = True
            self._audition_phase = 2
            # Cursor-Wechsel zwischen Waveforms
```

**Build-PC**: FUNKTIONIERT — Ein sauberer Sprung, Cursor synchron, kein Doppel-Sprung ✅
**Laptop (EXE)**: FUNKTIONIERT — Gleich gut wie auf dem Build-PC, keine Drift-Probleme ✅
**User-Feedback**: "Das war es wohl. Jetzt klingt alles gut und sieht gut aus." (2026-03-16)

**Warum das funktioniert**:
1. `_loop_active = False` verhindert den Engine-internen Feed-Loop in `_feed_stretcher()`
2. Die Engine spielt linear weiter ueber den Loop-Punkt hinaus (kein vorzeitiger Ruecksprung)
3. NUR der Beat-Snap-Dialog steuert den Sprung per `seek()`, getriggert durch `_playback_sample`
4. `_playback_sample` zaehlt tatsaechlich ausgegebene Samples (kein Feed-Ahead, kein Schaetzen)
5. Kein Timer-Drift-Problem (Counter ist an Audio-Output gebunden, nicht an UI-Timer)
6. Kein Echtzeit-vs-Audio-Zeit-Problem (Counter zaehlt Audio-Samples, nicht Wanduhr-Zeit)
7. Engine-Loop wird in `_stop_audition()` VOR `stop()` wiederhergestellt → normaler Betrieb

**Kernproblem war**: Die Engine hatte einen EIGENEN Loop (`_feed_stretcher()`, Zeile 251-254),
der im Feed-Ahead (~0.5s vor Wiedergabe) zuruecksprang. Das erzeugte den ersten "Geister-Sprung".
Der Beat-Snap-Dialog machte dann seinen eigenen Seek → zweiter Sprung. Erst das Deaktivieren
des Engine-Loops eliminierte die Ursache des Doppel-Sprungs.

## Zusammenfassung der Erkenntnisse

### Die Loesung (Versuch 6):
- **Engine-Loop deaktivieren** waehrend Audition (`_loop_active = False`)
- **Sample-Counter** `_playback_sample` als Positionsquelle (zaehlt Output-Samples im Callback)
- **Beat-Snap-Dialog** steuert den einzigen Seek allein
- Funktioniert auf schnellem UND langsamem Rechner gleichermassen

### Was funktioniert:
- **Engine-Loop deaktivieren + Sample-Counter** (Versuch 6) — DIE LOESUNG
- Seek-Warmup (50ms) gegen WSOLA-Artefakte nach flush()
- 30 Hz Timer-Rate reicht visuell aus
- Akkumulierter Timer (`+= interval`) NUR auf schnellem Rechner

### Was NICHT funktioniert:
- `engine.get_position_seconds()` als Cursor-Quelle (systematisch voraus wegen Feed-Ahead)
- `QElapsedTimer` als Zeitbasis (Echtzeit ≠ Audio-Zeit bei Tempo != 1.0)
- Jede Methode die den Phase-Wechsel an die geschaetzte Audio-Position koppelt
- Akkumulierter Timer auf schwachem Rechner (Drift durch unregelmaessige Ticks)
- Engine-Loop aktiv lassen waehrend Audition (Feed-Ahead-Loop erzeugt Doppel-Sprung)

### Wichtigste Erkenntnis:
Das Kernproblem war NICHT die Cursor-Synchronisation, sondern der Engine-interne
Feed-Loop in `_feed_stretcher()`. Dieser springt im Feed-Ahead (~0.5s vor Wiedergabe)
zurueck und erzeugt einen "Geister-Sprung" den der Beat-Snap-Dialog nicht kontrolliert.
Erst das Deaktivieren von `_loop_active` waehrend der Audition loeste das Problem.

### Rahmenbedingungen (fuer zukuenftige Arbeiten):
- `_feed_pos` eilt der Wiedergabe voraus (WSOLA Feed-Ahead)
- `_estimate_playback_pos()` ist eine ungenaue Schaetzung (OK fuer Slider, nicht fuer Beat Snap)
- `_playback_sample` zaehlt tatsaechliche Output-Samples (praezise, thread-sicher)
- Audio-Callback laeuft in separatem Thread (int-Zuweisung in Python ist atomar)
- Warmup-Frames (Stille nach Seek) werden vom Sample-Counter NICHT gezaehlt
- `_loop_active` steuert den Engine-internen Feed-Loop — bei externer Loop-Kontrolle deaktivieren

### Bekanntes offenes Thema:
- `_playback_sample += frames` beruecksichtigt NICHT den Tempo-Faktor
- Bei Tempo != 1.0 driftet der Counter (zaehlt Output-Frames, nicht Source-Frames)
- Korrekte Formel waere: `+= int(frames * user_tempo * today_tempo)`
- Aktuell kein Problem, weil Beat Snap den Cursor relativ zur Audio-Position steuert
- Relevant falls `_playback_sample` kuenftig fuer andere Zwecke genutzt wird

### BPM-Detection (Comb-Filter-basierte Tempoerkennung):
- Methode: Comb Filter Bank Tempo Estimation
- Onset-Strength-Envelope wird mit Kammfiltern verschiedener Perioden gefaltet
- Dominante Periodizitaet = Tempo (Aufloesung 0.1 BPM)
- Daraus wird ein Beat Grid abgeleitet (gleichmaessiges Raster: `n / BPM * 60` Sekunden)
- Sub-Harmonik-Korrektur: Integer-Vielfache pruefen, hoehere Tempi bevorzugen

### Loop-Crossfade (ab 0.32):
- Nahtloser Loop-Uebergang statt hartem Schnitt mit flush()/warmup
- Am Loop-Ende: Die letzten N Frames werden mit den ersten N Frames von Loop-In
  linear ueberblendet (N = Crossfade-Dauer in Samples)
- Konfigurierbar via INI `loop/crossfade_ms` (Default 46ms)
- Budget-basierter Mechanismus im Audio-Callback:
  1. Feed erreicht Loop-Out → Budget wird berechnet (verbleibende Input-Samples / Tempo)
  2. Callback zaehlt Budget herunter (thread-safe, nur int-Operationen)
  3. Bei Budget = 0 → Loop-Do-Seek Flag an UI-Thread
  4. UI-Thread fuehrt seek() aus (naechster Timer-Tick)
  5. Fallback: Falls UI-Timer den Seek verpasst, springt Feed selbst zurueck
- Eliminiert WSOLA-Einschwing-Artefakte komplett

### Loop-Offset-Messung (ab 0.32):
- Automatische Messung des optimalen Versatzes zwischen Loop-Ende und Loop-Anfang
- Methode: FFT-basierte Kreuzkorrelation (`scipy.signal.correlate`)
  1. Tiefpass-Filter <200Hz (Butterworth 4. Ordnung, `sosfiltfilt`)
  2. Referenz: 200ms Audio vor Loop-Out
  3. Kandidat: ±2 Sekunden Audio um Loop-In
  4. Korrelation berechnen, Peaks finden
  5. Kleinsten Offset mit Korrelation >= 0.1 waehlen
- Tiefpass fokussiert auf Bass/Bassdrum — dort ist das rhythmische Muster staerker
- Hoehere Korrelationswerte (0.3-0.9 statt 0.15) durch Bass-Fokussierung
- Offset wird pro Song in DB gespeichert (`loop_offset_ms`)
- Auto-Apply bei Beat Snap und Loop-Test, manuell korrigierbar via SpinBox (±3000ms)
