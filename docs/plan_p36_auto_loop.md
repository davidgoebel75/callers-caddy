# P36 — Auto Loop Finder

## Ziel

Neues Widget "Loop Finder", das automatisch gute Loop-Kandidaten erkennt und dem User zur Auswahl anbietet. Kein neues pip-Package — alles mit scipy + numpy.

## Prinzip

Square-Dance-Musik ist repetitiv. Gute Loops beginnen meist im **ersten Viertel** (nach dem Intro) und enden im **letzten Viertel** (vor dem Outro). Der Algorithmus sucht Stellen, die **klanglich aehnlich** sind — dort kann ein Loop unauffaellig zurueckspringen.

## Architektur

**Eigenes Widget** (kein Eingriff in bestehenden Code):
- `loop_finder.py` — Analyse-Logik (reines Python, kein Qt)
- `loop_finder_widget.py` — Dock-Widget mit UI
- Bestehende Module werden nur gelesen, nicht veraendert

**Vorhandene Bausteine wiederverwenden:**
- `detect_beat_grid()` aus `bpm_detector.py` → Beat-Raster
- `_onset_strength()` aus `bpm_detector.py` → Transient-Erkennung
- `WaveformWidget` aus `beat_snap_dialog.py` → Waveform-Anzeige
- `scipy.signal.correlate()` Muster aus `audio_engine.py` → Aehnlichkeitsvergleich
- Audio-Laden: `soundfile.sf.read()` + Mono-Downmix (bewaehrtes Pattern)

## Analyse-Pipeline (loop_finder.py)

```
Song laden (mono, 22050 Hz)
    │
    ▼
Beat-Grid erzeugen (detect_beat_grid)
    │
    ▼
Downbeat-Schaetzung (Kick-Energie auf Beat 1 vs. 2/3/4)
    │
    ▼
Bar-Raster (Taktgrenzen, je 4 Beats)
    │
    ▼
Kandidaten sammeln:
  Loop-In:  Alle Taktgrenzen im 1. Viertel
  Loop-Out: Alle Taktgrenzen im letzten Viertel
    │
    ▼
Fuer jedes Paar (loop_in, loop_out) Score berechnen:
  - Chroma-Aehnlichkeit (Harmonie)
  - Onset-Muster-Aehnlichkeit (Rhythmus)
  - Energie-Aehnlichkeit (Lautstaerke/Klangfuelle)
  - Phasen-Kompatibilitaet (gleiche Position im Takt)
    │
    ▼
Top 5 Vorschlaege zurueckgeben, sortiert nach Score
```

### Schritt 1: Beat-Grid + Downbeat

```python
bpm, beat_times = detect_beat_grid(filepath)  # bestehende Funktion

# Downbeat-Schaetzung: 4 moegliche Phasen testen
# Fuer jede Phase: mittlere Kick-Energie auf Beat 1 messen
# Staerkste Phase = Downbeat-Offset
# → bar_times = beat_times[offset::4]  (jeder 4. Beat)
```

### Schritt 2: Chroma-Features (neu, ~30 Zeilen)

```python
# FFT → Frequenz-Bins → auf 12 Halbtoene mappen
# chroma[i] = Energie aller Frequenzen die zu Halbton i gehoeren
# Pro Bar: Mittelwert der Chroma-Vektoren → 12-dim Vektor
# Aehnlichkeit: Kosinus-Distanz zwischen zwei Chroma-Vektoren
```

**Kein librosa noetig** — Chroma ist nur eine Umrechnung von FFT-Bins auf 12 Tonklassen. Formel: `note = 12 * log2(freq / 440) % 12`

### Schritt 3: Onset-Muster-Vergleich

```python
# _onset_strength() liefert Onset-Envelope
# Pro Takt: 4 Onset-Werte (auf Beats) → Pattern-Vektor
# Aehnlichkeit: Korrelation zwischen Pattern am Loop-In und Loop-Out
```

### Schritt 4: Energie-Aehnlichkeit

```python
# RMS-Energie in Fenster um Loop-In vs. Loop-Out
# Aehnlich wie measure_loop_offset(), aber ohne Verschiebung
# Guter Loop: Energieniveau an beiden Stellen aehnlich
```

### Schritt 5: Scoring

```python
score = (0.35 * chroma_score      # Harmonie-Aehnlichkeit
       + 0.30 * onset_score       # Rhythmus-Aehnlichkeit
       + 0.20 * energy_score      # Lautstaerke-Aehnlichkeit
       + 0.15 * phase_score)      # Taktposition-Kompatibilitaet
```

Gewichtung anpassbar — erstmal mit diesen Werten starten, spaeter tunen.

## Widget-UI (loop_finder_widget.py)

```
┌─────────────────────────────────────────────────┐
│ Loop Finder                              [≡] [×] │
├─────────────────────────────────────────────────┤
│                                                   │
│  [🔍 Analysieren]           Status: Bereit        │
│                                                   │
│  ┌─── Vorschlaege ────────────────────────────┐  │
│  │  Nr │ Score │ Loop-In  │ Loop-Out │ Takte  │  │
│  │  1  │  92%  │  0:18.3  │  2:41.7  │  8+8   │  │
│  │  2  │  87%  │  0:22.1  │  2:37.9  │  8+8   │  │
│  │  3  │  81%  │  0:14.5  │  2:45.5  │ 16+16  │  │
│  │  4  │  74%  │  0:26.0  │  2:33.8  │  8+8   │  │
│  │  5  │  68%  │  0:18.3  │  2:45.5  │  8+16  │  │
│  └────────────────────────────────────────────┘  │
│                                                   │
│  [▶ Vorhoeren]  [✓ Uebernehmen]                  │
│                                                   │
│  ┌─── Waveform ──────────────────────────────┐   │
│  │  ~~~~Loop-In~~~~  ···  ~~~~Loop-Out~~~~    │   │
│  └────────────────────────────────────────────┘  │
│                                                   │
└─────────────────────────────────────────────────┘
```

### Elemente:
- **Analysieren-Button**: Startet Analyse in QThread (nicht blockierend)
- **Vorschlags-Tabelle**: Top 5, sortiert nach Score, Doppelklick = Vorhoeren
- **Vorhoeren-Button**: Spielt ~5s vor Loop-Out, springt zu Loop-In, spielt weiter
- **Uebernehmen-Button**: Schreibt gewaehlten Vorschlag in loop_in/loop_out der DB
- **Waveform**: Zeigt Ausschnitte um Loop-In und Loop-Out (WaveformWidget wiederverwenden)

### Verhalten:
- Widget reagiert auf Song-Wechsel (wie andere Widgets)
- Analyse nur auf Knopfdruck (nicht automatisch — kann 2-5s dauern)
- Nach Uebernahme: Loop-Widget aktualisiert sich automatisch (bestehender Mechanismus)
- QThread fuer Analyse (wie BPM-Detection)

## Dock-Integration (main.py)

- Neues Dock `dock_loop_finder`, getabbt mit Loop-Widget
- Menu-Eintrag unter "Ansicht" / "View"
- Default: versteckt (muss ueber Menu eingeblendet werden)
- Layout-Version erhoehen (wegen neuem Dock)

## Implementierungsreihenfolge

### Phase A: Analyse-Kern (loop_finder.py)
1. Beat-Grid laden + Downbeat-Schaetzung
2. Chroma-Berechnung (FFT → 12 Halbtoene)
3. Kandidaten-Sammlung (1. + letztes Viertel)
4. Scoring-Funktion
5. Unit-Test mit bekannten Songs

### Phase B: Widget (loop_finder_widget.py)
1. Grundgeruest: Dock-Widget mit Tabelle + Buttons
2. QThread-Analyse mit Progress
3. Vorschlags-Anzeige
4. Waveform-Vorschau (WaveformWidget einbetten)

### Phase C: Integration
1. Vorhoeren via Audio-Engine
2. Uebernehmen → DB schreiben → Loop-Widget aktualisieren
3. Dock in main.py einhaengen
4. Tutorial-Eintrag (optional, spaeter)

## Risiken und Absicherung

| Risiko | Absicherung |
|--------|-------------|
| Analyse veraendert bestehende Loops | Eigenes Widget, nur auf Knopfdruck, Uebernehmen explizit |
| Schlechte Vorschlaege bei untypischer Musik | User waehlt aus Top 5 + Vorhoeren, nichts wird automatisch gesetzt |
| Analyse zu langsam | QThread, 22050 Hz Resampling, nur 1.+letztes Viertel analysieren |
| Chroma-Berechnung ungenau ohne librosa | Einfache FFT→Halbton-Zuordnung reicht fuer Aehnlichkeitsvergleich |
| Neue Dependencies | Keine — alles scipy + numpy |

## Nicht in v0.36

- Kein automatisches Loop-Setzen beim Import
- Kein Batch-Modus (alle Songs auf einmal)
- Keine Feinkorrektur im Widget (dafuer gibt es Beat Snap)
- Kein Tutorial (erst wenn das Feature stabil ist)
