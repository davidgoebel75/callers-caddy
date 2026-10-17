"""Pausen-Uhr: Zustand und Uebergaenge, ohne Qt (intern#220).

reduce(state, action) -> (neuer Zustand, Ereignisse). Das Widget misst die Zeit,
schickt Aktionen und ruft fuer jedes Ereignis den passenden Callback.
"""
from dataclasses import dataclass, replace

QT_FREE = True

# Ereignisse, die reduce() meldet
STARTED = "started"     # frischer Start (nicht Fortsetzen)
FINISHED = "finished"   # echter Ablauf auf 0 (nicht Reset/Abbruch)


@dataclass(frozen=True)
class BreakState:
    total: float
    remaining: float
    running: bool = False
    finished: bool = False


@dataclass(frozen=True)
class Start:
    """Starten oder Fortsetzen."""


@dataclass(frozen=True)
class Pause:
    """Anhalten, Restzeit bleibt."""


@dataclass(frozen=True)
class Reset:
    """Zurueck auf volle Dauer. Abgebrochen, nicht abgelaufen: meldet nichts."""


@dataclass(frozen=True)
class SetDuration:
    """Neue Pausendauer. Ein laufender Countdown laeuft unveraendert weiter;
    None oder <= 0 aendert nichts."""
    seconds: float | None


@dataclass(frozen=True)
class Restart:
    """Frisch von vorn starten, auch wenn schon ein Countdown laeuft (Rule-Aktion,
    Wartemusik). Optional mit neuer Dauer."""
    seconds: float | None = None


@dataclass(frozen=True)
class Tick:
    """dt Sekunden sind vergangen."""
    dt: float


Action = Start | Pause | Reset | SetDuration | Restart | Tick


def reduce(state: BreakState, action: Action) -> tuple[BreakState, tuple[str, ...]]:
    match action:
        case Start():
            # Frisch = volle Restzeit oder abgelaufen; Fortsetzen nach Anhalten
            # meldet nichts. Anhalten im ersten Tick zaehlt bewusst als frisch.
            if state.finished or state.remaining <= 0:
                state = replace(state, remaining=state.total, finished=False)
            fresh = state.remaining >= state.total
            return replace(state, running=True), (STARTED,) if fresh else ()
        case Pause():
            return replace(state, running=False), ()
        case Reset():
            return BreakState(total=state.total, remaining=state.total), ()
        case SetDuration(seconds):
            if not seconds or seconds <= 0:
                return state, ()
            total = float(max(1, round(seconds)))
            if state.running:
                return replace(state, total=total), ()
            return BreakState(total=total, remaining=total), ()
        case Restart(seconds):
            state, _ = reduce(replace(state, running=False), SetDuration(seconds))
            return (BreakState(total=state.total, remaining=state.total,
                               running=True), (STARTED,))
        case Tick(dt):
            if not state.running:
                return state, ()
            remaining = state.remaining - dt
            if remaining > 0:
                return replace(state, remaining=remaining), ()
            return (replace(state, remaining=0.0, running=False, finished=True),
                    (FINISHED,))
    raise TypeError(f"Unbekannte Aktion: {action!r}")
