# F6.1 Audio Player (Hauptfenster)

## Grundfunktionen
- MP3-Wiedergabe (V1 nur MP3)
- Play (F5), Pause (F6), Stop (F7), Fade Out (F8)
- Leertaste als Play/Pause-Toggle optional
- Song laden = kein Autoplay, Start nur über Play/Hotkey

## Transport-Buttons
- **Play**: Startet Wiedergabe / Resume nach Pause
- **Pause**: Pausiert Wiedergabe (Play setzt fort)
- **Stop**: Beendet Wiedergabe, triggert Auto-Advance (nächster Playlist-Song)
- **Fade Out**: Lineares Ausblenden über konfigurierbare Dauer (INI `fade_out_time`, Default 3s), dann Stop + Auto-Advance

## Button-States
| Zustand | Play | Pause | Stop | Fade Out |
|---------|------|-------|------|----------|
| Geladen | ✅ | ❌ | ❌ | ❌ |
| Wiedergabe | ❌ | ✅ | ✅ | ✅ |
| Pausiert | ✅ | ❌ | ✅ | ❌ |
| Fade Out... | ❌ | ❌ | ✅ | ❌ |
| Gestoppt | ✅ | ❌ | ❌ | ❌ |

## F6.2 Tempo, Pitch, Lautstärke, BPM
- Pro Song gespeichert: Standard-Tempo, Pitch, Lautstärke, Basis-BPM
- Änderungen sofort auto-gespeichert
- Tempo live während Wiedergabe änderbar
- **Pitch bleibt bei Tempoänderung konstant** (Time-Stretching!)
- Pitch separat änderbar, Schrittweite 0,2 Halbtöne
- Pitch-Änderung auch während Wiedergabe
- BPM per Tap Tempo (Leertaste)
- Auto-BPM-Erkennung beim Import (optional)
- Anzeige: Basis-BPM, Song-Tempo, heutiges Tempo, aktuelle BPM

## Berechnungslogik
effektive_BPM = Basis_BPM × Song_Tempo_Faktor × Heutiges_Tempo_Faktor
(Multiplikation, NICHT Addition der Prozentwerte)

## F6.3 Heutiges Tempo (Session-Faktor)
- Prozentfaktor für aktuelle Session
- Wirkt zusätzlich zum Song-Tempo auf ALLE Songs
- Während laufendem Song änderbar
- Kein dauerhafter Songwert, sondern Sessionwert
- Wird bei Crash-Recovery wiederhergestellt

## F6.4 Pattern vs. Singing Call
- Jeder Song kann beides sein (kontextabhängig, nicht fest verdrahtet)
- Pattern: rhythmisch, Loop standardmässig AN
- Singing Call: 7 gleich grosse Segmente, Loop standardmässig AUS
- Nutzungsart ergibt sich aus Playlist-Eintrag / aktueller Nutzung

## F6.5 Loop-System
- Import-Default: Loop-In = Anfang, Loop-Out = Ende
- Mindestens 2 Marker: Loop-In, Loop-Out
- Marker auf aktuelle Wiedergabeposition setzbar
- Feinjustierung in Sekunden und Hundertstelsekunden
- Direkte Eingabe als mm:ss.xx
- Testhörfunktion: ~5s vor Loop-Out, Rücksprung auf Loop-In
- Loop-Marken pro Song gespeichert, Auto-Save

### Loop-Crossfade (ab 0.32)
- Nahtloser Uebergang am Loop-Punkt durch Crossfade statt hartem Schnitt
- Crossfade-Dauer konfigurierbar: INI `loop/crossfade_ms` (Default 46ms)
- Funktionsweise: Am Loop-Ende werden die letzten Crossfade-Frames mit den
  ersten Frames von Loop-In ueberblendet (lineares Fade-Out/Fade-In)
- Kein flush()/warmup noetig — eliminiert WSOLA-Einschwing-Artefakte
- Budget-basierter Mechanismus: Audio-Callback zaehlt Output-Samples als
  Countdown, kein Zugriff auf Stretcher-Interna aus dem UI-Thread

### Loop-Offset (ab 0.32)
- Pro Song einstellbarer Offset fuer den Loop-Sprung (DB-Feld `loop_offset_ms`)
- Verschiebt den effektiven Loop-Out-Punkt: `effective_loop_out = loop_out + offset`
- Positiver Offset = Loop spielt laenger, negativer = Loop springt frueher
- **Auto-Messung**: FFT-basierte Kreuzkorrelation im Tiefpass-Bereich (<200Hz)
  - Vergleicht Audio an Loop-Out mit Audio an Loop-In
  - Suchbereich ±2 Sekunden, waehlt kleinsten Offset mit Korrelation >= 0.1
  - Wird bei Beat Snap und Loop-Test automatisch ausgefuehrt
- **Manuelle Korrektur**: SpinBox in Song-Daten (±3000ms, 0.5ms Schritte)
- Offset wird in DB gespeichert und beim Song-Laden wiederhergestellt

## Fade-Out Implementierung (technisch)
- Linearer Volume-Ramp im Audio-Callback (`_callback`), sample-genau
- `start_fade_out(duration_s)` berechnet `_fade_step = 1.0 / (duration * sample_rate)`
- Pro Sample: `_fade_volume -= _fade_step`, Audio multipliziert mit Volume
- Bei Volume ≤ 0: `playing = False` → gleicher Trigger wie natürliches Song-Ende
- Fade-State wird bei Play/Stop zurückgesetzt
- Status-Anzeige: "Status: Fade Out..." während des Fades

## Audio-Engine (technisch)
- Eigener Streaming-WSOLA Time-Stretcher (kein Rubber Band/SoundTouch)
- sounddevice (PortAudio) für Audio-Ausgabe
- Song-Ende-Erkennung: `can_process()` statt `input_available() <= 0`
  (WSOLA braucht `window_size + search_range` Samples Vorlauf)
- UI-Updates via Timer-Polling (50ms), NICHT via Signale aus Audio-Thread
