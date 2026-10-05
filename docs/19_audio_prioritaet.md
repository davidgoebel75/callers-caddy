# Audio-Prioritaet — Hintergrund und Diagnose (TIC-0025, v0.80)

Die Eiserne Regel steht in `CLAUDE.md`, die pruefbaren Architektur-Garantien und Pflicht-Pattern in `CODING_STANDARDS.md`. Hier Herleitung und Diagnose-Ablauf.

## Hintergrund

Python's GIL bedeutet: jede laengere Operation auf dem Main-Thread (UI-Timer, Event-Handler, Rule-Actions) blockiert den Audio-Callback, weil sounddevice's PortAudio-Callback ebenfalls den GIL braucht. Andere Audio-Programme (C/C++) haben dieses Problem nicht — bei uns muss die Architektur das aktiv kompensieren.

## Diagnose-Werkzeuge

- **Rules-Aktions-Timing** (ab v0.78): `src/rule_engine.py._execute_actions` misst jede Action und schreibt `[Xms]` in `rules/rules.log`. Alles ueber 5 ms ist verdaechtig, alles ueber 50 ms ist ein Bug.
- **Perf-Log** (`perf_log.txt`): Main-Thread-Operationen mit Timing. Suche nach Eintraegen > 50 ms.
- **der i5-6500 eines Users (2015)** ist unser Referenz-Worstcase. Aktionen die auf dem Desktop 30 ms kosten, kosten dort schnell 100+ ms.

## Wenn ein neuer Audio-Aussetzer-Bug auftritt

1. **Erst Rules-Log pruefen** (`rules/rules.log`): gibt es eine Action mit > 50 ms genau vor dem Aussetzer?
2. **Dann Perf-Log pruefen**: gibt es eine Main-Thread-Operation > 50 ms im Zeitfenster?
3. **Dann erst Audio-Engine anfassen** — die Engine selbst ist seit v0.80 robust. 99% aller Aussetzer-Ursachen liegen im Main-Thread, nicht in der Engine.
