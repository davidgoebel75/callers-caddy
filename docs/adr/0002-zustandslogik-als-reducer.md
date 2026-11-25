# Verzwickter Zustand wird ein Reducer

Haengen mehrere Zustandsfelder voneinander ab und werden sie an vielen Stellen
von Hand gesetzt, zieht die Logik in ein Modul ohne Qt:
`reduce(zustand, aktion) -> (neuer_zustand, ereignisse)`. Der Zustand ist eine
unveraenderliche Dataclass, Ereignisse kommen als Rueckgabewert, das Widget
gibt nur Aktionen weiter und ruft fuer die Ereignisse seine Callbacks. Die
Randfaelle sind so ohne Fenster und ohne private Felder testbar. Erstes
Beispiel: `caddy/breaks/break_clock.py` (intern#220).

**Einfach vor komplex:** Ein Reducer kommt nur, wo der Zustand wirklich
verzwickt ist. Einfache Werte bleiben einfache Werte, Logik ohne Zustand wird
eine reine Funktion. Im Zweifel bleibt es beim einfachen Wert.

**Performance:** Der Umbau darf die App nicht spuerbar langsamer machen,
besonders bei allem, was oft laeuft (Timer-Ticks, Wiedergabe, grosse Listen).
Bei Zweifeln vorher und nachher mit `tools/benchmark` messen. Die
Audio-Prioritaet (`CODING_STANDARDS.md`) gilt unveraendert.

## Considered Options

- **Zentraler Store fuer die ganze App (Redux-Stil):** Jede Aenderung liefe
  durch eine Stelle, auch die vielen unabhaengigen Werte. Jeder Baustein bekommt
  stattdessen seinen eigenen kleinen Reducer, erst wenn er ohnehin angefasst wird.
- **Framework fuer Zustandsautomaten:** Eine Dataclass und eine Funktion
  reichen; die Rolle von „subscribe" uebernehmen die Qt-Signale.
- **Zustand im Widget lassen:** Die Logik bleibt nur mit `qapp` und ueber
  private Felder testbar, Randfaelle (frischer Start oder Fortsetzen, Ablauf
  oder Abbruch) verteilen sich auf viele Methoden.
