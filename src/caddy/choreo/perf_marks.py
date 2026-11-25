"""Perf-Marken fuer Square Flow (intern#247, intern#263).

Qt-frei und ohne Abhaengigkeit von `perf`: Hier entstehen nur die Zeilen; geschrieben
werden sie vom Worker bzw. Widget ueber `perf.perf_write`, und nur bei eingeschaltetem
Performance-Logging.

Bewusst grob, damit die Messung selbst nichts kostet:
- je Analyse-Auftrag eine Zeile (Quelle und Dauer),
- fuer die Animation eine Sammelzeile je Zeitfenster (Standard 5 s) statt einer Zeile je Bild.

Die Zeilen tragen das Praefix `[SquareFlow]` statt `[Perf]`: Der Haenger-Detektor merkt
sich nur `[Perf]`-Zeilen als "letzten Event im Hauptthread"; Zeilen aus dem
Hintergrund-Thread sollen ihn nicht in die Irre fuehren.
"""
import time

QT_FREE = True

PREFIX = "[SquareFlow]"

SOURCE_MEMORY = "Speicher"
SOURCE_DB = "DB-Cache"
SOURCE_ENGINE = "Engine"


def analyse_line(seq_id, n_calls, source, ms, engine_started=False, error=None):
    """Eine Zeile je Analyse-Auftrag, z. B.
    `[SquareFlow] Analyse seq=1234 (37 Calls): Engine 820 ms, mit Engine-Start`."""
    seq = "-" if seq_id is None else seq_id
    line = f"{PREFIX} Analyse seq={seq} ({n_calls} Calls): {source} {ms:.0f} ms"
    if engine_started:
        line += ", mit Engine-Start"
    if error:
        line += f", Fehler: {error}"
    return line


class AnimStats:
    """Sammelt Zeichen- und Schrittzeiten der Animation und liefert je Zeitfenster eine Zeile.

    paint(ms): ein gezeichnetes Bild; step(ms): ein Animationsschritt (Beat berechnen, Pose
    setzen). poll() gibt nach Ablauf des Fensters die Zeile zurueck (oder None) und beginnt
    ein neues Fenster. Ohne gezeichnete Bilder im Fenster entsteht keine Zeile.
    """

    def __init__(self, period=5.0, clock=time.perf_counter):
        self._period = period
        self._clock = clock
        self.restart()

    def restart(self):
        """Neues Fenster, z. B. wenn die Animation nach einer Pause wieder losgeht."""
        self._t0 = self._clock()
        self.frames = 0
        self._paint_sum = 0.0
        self.paint_max = 0.0
        self.steps = 0
        self.step_max = 0.0

    def paint(self, ms):
        self.frames += 1
        self._paint_sum += ms
        if ms > self.paint_max:
            self.paint_max = ms

    def step(self, ms):
        self.steps += 1
        if ms > self.step_max:
            self.step_max = ms

    def poll(self, force=False):
        """force=True: Fenster sofort abschliessen (Animation endet)."""
        elapsed = self._clock() - self._t0
        if elapsed < self._period and not force:
            return None
        line = None
        if self.frames:
            avg = self._paint_sum / self.frames
            line = (f"{PREFIX} Animation {elapsed:.0f}s: {self.frames} Frames, "
                    f"paint avg {avg:.1f} / max {self.paint_max:.0f} ms, "
                    f"Schritt max {self.step_max:.0f} ms")
        self.restart()
        return line
