# Tech-Stack Entscheidung

## Systemvoraussetzungen (Endnutzer)

- **Betriebssystem: Windows 10 oder 11 (64-bit).** Windows 7 und 8/8.1 werden **nicht** unterstuetzt.
  - Grund: **Qt 6 / PySide6** (fest gepinnt auf 6.12.0 in `installer/requirements.txt`, intern#241) hat Win 7/8 fallengelassen und zielt nur auf Win 10/11. **Python 3.12** (im Build gebuendelt) verlangt ebenfalls mind. Windows 8.1 — praktisch also auch kein Win 7.
  - Ein Start unter Windows 7 schlaegt mit fehlenden System-DLLs fehl. Das ist **erwartetes Verhalten, kein Bug** — es gibt keinen sinnvollen Workaround, ohne die Qt-/Python-Version zurueckzudrehen.
- **Architektur: x86-64.** Kein offizielles ARM-Build.
- **Kein Python noetig:** Die EXE buendelt Python + alle Abhaengigkeiten (PyInstaller).
- **Audio:** Ausgabe ueber Windows (WASAPI via PortAudio/sounddevice).

> "Windows 9" gibt es nicht — Microsoft ging von 8 direkt auf 10.

## Sprache: Python
- Schnelle Entwicklung, gutes Debugging
- Audio-kritische Teile laufen nativ in C (Rubber Band, PortAudio)
- GIL kein Problem: Audio-Callbacks laufen in C ausserhalb des GIL

## UI: PySide6 (Qt 6 Widgets)
- Native Desktop-Widgets, kein WebView
- QDockWidget fuer Docking/magnetisches Andocken
- QTableView mit Model fuer 10k+ Songs (virtuelles Scrolling)
- QTranslator fuer i18n (DE/EN)
- saveState()/restoreState() fuer Layout-Persistenz
- Lizenz: LGPLv3 (kompatibel mit Open Source UND Closed Source)

## Audio: eigener Time-Stretcher + sounddevice
- **Rubber Band** (C-Library) war geplant, wird aber nicht eingesetzt: Time-Stretching + Pitch-Shifting sind eigener Code (WSOLA, SoundTouch-Stil, `src/time_stretcher.py`, `src/pitch_shifter.py`)
- **sounddevice** (PortAudio-Wrapper): Low-Latency Audio-Ausgabe
  - Callbacks laufen in C → kein GIL-Problem
- **MP3-Decoding**: pydub/ffmpeg oder audioread/soundfile
- **Looping**: eigene Logik auf PCM-Buffer-Ebene

## Datenbank: SQLite
- Lokal, portabel, eine Datei
- Relativ pfadbar → Installation kopierbar
- Python: sqlite3 (built-in) oder SQLAlchemy
- 10k Songs: trivial

## Lizenz: Open Source (GPL-2.0-or-later)
- Lizenztext: `LICENSE` im Projektstamm (unveraenderter GPLv2-Text); "oder spaeter" steht im About-Dialog und hier
- Rubber Band (urspruenglicher Anlass fuer die GPL) wird nicht mehr ausgeliefert; Time-Stretching/Pitch-Shifting sind eigener Code
- PySide6 wird unter LGPL-3.0 genutzt, kompatibel
- Quellcode oeffentlich, kostenlose Nutzung
- **Fremdkomponenten:** `installer/licenses/THIRD_PARTY.txt` listet jede mitgelieferte Komponente mit Lizenzdatei; `build.py` legt `LICENSE` und `licenses/` neben die EXE. Neue Zeile in `installer/requirements.txt` → dort nachtragen (Test `tests/app/test_third_party_licenses.py` erinnert). Kommt eine Komponente ohne Python-Paket dazu, ebenfalls dort eintragen.

## Distribution
- PyInstaller oder cx_Freeze → standalone .exe / .app
- Portable Version: Ordner kopieren reicht
- Geschaetzte Groesse: ~50-80 MB

## Zusammenfassung
```
Python + PySide6 (Qt Widgets) + Rubber Band + sounddevice + SQLite
```

---

# Zweitbeste Alternative: C++ + Qt

## Warum zweitbeste?
- Technisch gleichwertig oder leicht ueberlegen (volle Kontrolle, kein GIL)
- Aber: deutlich langsamer in der Entwicklung (geschaetzt 3-4x)
- Hoehere Einstiegshuerde, mehr Boilerplate, komplexeres Debugging

## Stack
- **Sprache**: C++17
- **UI**: Qt 6 Widgets (QDockWidget, QTableView, QTranslator — identisch)
- **Audio**: Rubber Band (direkt C++ API) + PortAudio
- **DB**: SQLite (C API direkt oder Qt SQL Modul)
- **Build**: CMake + Qt Creator
- **Distribution**: kompakter (~20 MB), einfachere Einzeldatei

## Vorteile gegenueber Python
- Kein GIL (Audio-Thread voellig frei)
- Kleinere Distribution
- Maximale Performance-Kontrolle
- Ein Kompilat, keine Python-Runtime noetig

## Nachteile gegenueber Python
- 3-4x langsamere Entwicklung
- Speicherverwaltung manuell (oder Smart Pointers)
- Kompilierzeiten bei Aenderungen
- Komplexeres Debugging (Segfaults statt Exceptions)

## Wann umsteigen?
Falls sich in P1-P6 herausstellt, dass der Python-GIL trotz C-Callbacks
zu Audio-Problemen fuehrt, waere C++ + Qt der natuerliche Fallback.
Die UI bleibt identisch (Qt Widgets), nur die Sprache aendert sich.
