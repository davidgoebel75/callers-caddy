---
status: proposed
---

# Fachpakete unter einem Dach-Paket in src/

Neue Module kommen in ein Fachpaket unter `src/caddy/`, nicht flach nach `src/`.
Die Fachpakete folgen den Ordnern in `tests/` (`playback`, `songs`, `lyrics` ...).
Bestehende Module ziehen nur um, wenn sie fuer eine Aufgabe ohnehin angefasst
werden: Ein Umzug in einem Rutsch wuerde jeden offenen Branch mit Konflikten
treffen, und Lazy-Imports in Funktionen sieht man im Diff nicht. Das Dach-Paket
verhindert Kollisionen mit den Datenordnern, die neben der INI entstehen
(`lyrics/`, `rules/`, `music/` ...), wenn man aus `src/` startet.

Innerhalb eines Fachpakets steht Zustandslogik ohne Qt in einem eigenen Modul
(z. B. als Reducer, erstes Beispiel: `caddy/playback/break_clock.py`), das Widget
ruft sie nur auf. Solche Module tragen `QT_FREE = True`; `tests/app/test_qt_free.py`
prueft per `ast`, dass sie nirgends PySide6 importieren.

## Considered Options

- **Fachpakete direkt in `src/`** (`src/lyrics/` ...): kollidiert mit den Datenordnern.
- **Alles auf einmal umziehen:** Konflikte mit allen offenen Branches.
- **Qt-freie Module per Liste im Test oder per Namenskonvention erkennen:** Die
  Liste vergisst man, die Konvention trifft Qt-Helfer wie `skin_manager`, die
  keine Widgets sind. Die Markierung im Modul selbst zeigt dem Leser auch gleich
  die Rolle.

Offen bis zur Abnahme: der Name des Dach-Pakets (`caddy`).
