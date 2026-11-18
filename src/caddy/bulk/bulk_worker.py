"""Qt-Mantel der Massenlaeufe: Thread, Signale, Verbindung (intern#139).

Die Schleife selbst steht in bulk_run.py (ohne Qt). Hier nur, was QThread und
Signal braucht (daher kein QT_FREE).
"""
import warnings

from PySide6.QtCore import QCoreApplication, QThread, Signal

from caddy.bulk.bulk_run import BulkCounts, run_bulk

# Signale, die nur die Oberflaeche bedienen oder Folge-Laeufe starten. Beim
# Beenden getrennt; Ergebnis-Signale wie loop_found (Auto-Loop speichert im
# Hauptthread) bleiben verbunden.
_UI_SIGNALS = ('progress', 'finished', 'error', 'finished_ok', 'failed')


def stop_for_shutdown(running_workers):
    """Bricht laufende Worker beim Beenden ab und wartet ohne Zeitlimit auf ihr
    Ende (intern#242). running_workers() liefert die gerade laufenden Worker;
    es wird so lange nachgesehen, bis nichts mehr laeuft, denn waehrend der
    Rueckfrage kann ein Probelauf noch einen Folge-Lauf gestartet haben
    (Review PR #172). cancel() greift zwischen zwei Songs, der laufende Song
    wird noch fertig bearbeitet. Worker ohne cancel() (Loeschen, Ceder) laufen
    zu Ende. UI-Signale werden getrennt, damit kein Slot einen Folge-Lauf
    startet oder nach db.close() die DB anfasst; beim Warten laufen Events
    weiter, damit loop_found den letzten Loop noch speichert."""
    while workers := running_workers():
        _stop(workers)


def _stop(workers):
    for w in workers:
        for name in _UI_SIGNALS:
            sig = getattr(w, name, None)
            if sig is None:
                continue
            with warnings.catch_warnings():
                warnings.simplefilter('ignore')   # nichts verbunden
                try:
                    sig.disconnect()
                except (RuntimeError, TypeError, SystemError):
                    pass
        if hasattr(w, 'cancel'):
            w.cancel()
    for w in workers:
        while not w.wait(20):
            QCoreApplication.processEvents()
    QCoreApplication.processEvents()   # letztes loop_found nach Thread-Ende


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
