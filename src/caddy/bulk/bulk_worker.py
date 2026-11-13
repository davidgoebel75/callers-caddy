"""Qt-Mantel der Massenlaeufe: Thread, Signale, Verbindung (intern#139).

Die Schleife selbst steht in bulk_run.py (ohne Qt). Hier nur, was QThread und
Signal braucht (daher kein QT_FREE).
"""
from PySide6.QtCore import QThread, Signal

from caddy.bulk.bulk_run import BulkCounts, run_bulk


def stop_and_wait(workers):
    """Bricht laufende Worker ab und wartet ohne Zeitlimit auf ihr Ende
    (intern#242). cancel() greift zwischen zwei Songs, der laufende Song wird
    noch fertig geschrieben. Worker ohne cancel() (Loeschen, Ceder) laufen zu
    Ende. Nur fuers Beenden: Signale werden blockiert, damit kein finished-Slot
    mehr gegen die gleich geschlossene DB laeuft."""
    for w in workers:
        w.blockSignals(True)
        if hasattr(w, 'cancel'):
            w.cancel()
    for w in workers:
        w.wait()


class BulkWorker(QThread):
    """Hintergrund-Worker fuer einen Massenlauf ueber eine Liste von Jobs.

    open_connection wird im Thread aufgerufen (SQLite-Verbindungen sind
    threadgebunden). Das Signal finished(done, skipped) ueberschreibt wie in den
    Bestands-Workern das eingebaute QThread.finished; es kommt als LETZTES,
    nach dem Schliessen der Verbindung, auch nach einem Fehler. Nach einem
    Fehler mitten im Lauf traegt es den Stand bis dahin (intern#239)."""
    progress = Signal(int, int, str)     # current, total, song_name
    finished = Signal(int, int)          # done, skipped
    error = Signal(str)

    def __init__(self, jobs, step, open_connection, *,
                 name_of=lambda job: "", label="Bulk", parent=None):
        super().__init__(parent)
        self._jobs = jobs
        self._step = step
        self._open_connection = open_connection
        self._name_of = name_of
        self._label = label
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    @property
    def cancelled(self) -> bool:
        return self._cancelled

    def run(self):
        counts = BulkCounts()
        conn = None
        try:
            conn = self._open_connection()
            run_bulk(self._jobs, self._step, conn=conn,
                     is_cancelled=lambda: self._cancelled,
                     on_progress=self.progress.emit,
                     name_of=self._name_of, label=self._label, counts=counts)
        except Exception as e:
            print(f"[{self._label}] Abbruch: {e}")
            self.error.emit(str(e))
        finally:
            if conn is not None:
                try:
                    conn.close()
                except Exception as e:
                    print(f"[{self._label}] close fehlgeschlagen: {e}")
        self.finished.emit(counts.done, counts.skipped)
