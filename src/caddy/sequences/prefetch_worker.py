"""Hintergrund-Lesen fuer das Sequenzfenster (intern#268).

Zwei Auftraege, beide ohne eigenes SQL: Der Worker ruft dieselben Funktionen der
DB-Schicht auf wie der Hauptthread, nur auf seiner eigenen Verbindung aus
SongDatabase.open_worker_connection (intern#146, #139).

- Figuren vorbauen: SongDatabase.build_sequence_figures_on_connection. Danach kostet
  ein Programmwechsel nur noch Mengenvergleiche (~2 ms) statt des Aufbaus im
  Hauptthread (am N150 gedrosselt bis 2,5 s).
- Sequenz-Detail einer Liste: SongDatabase.sequence_details_on_connection. Ein
  neuer Auftrag ersetzt einen noch wartenden (nur die zuletzt gesetzte Liste zaehlt).

Uebernommen wird im Hauptthread (Signal): adopt_sequence_figures bzw. das
Sequenz-Detail, jeweils nur bei passender Datenversion. Wann die Figuren neu
vorgebaut werden, entscheidet caddy.sequences.figures_task (Pull, intern#274).

Warum threading.Thread statt QThread (CODING_STANDARDS nennt fuer DB-Arbeit ueber
20 ms QThread, Review #204): Der Worker braucht keine eigene Qt-Ereignisschleife und
keine Qt-Objekte im Thread. Er wartet an einer threading.Condition auf Auftraege,
damit ein neuer Auftrag einen wartenden ersetzt und die Wartezeit abbricht
(_superseded). Ergebnisse gehen ueber Qt-Signale zurueck; weil der Sender in einem
fremden Thread laeuft, stellt Qt sie in die Warteschlange des Hauptthreads. Gleiches
Muster wie caddy.choreo.flow_worker (#196).
"""
import threading

from PySide6.QtCore import QObject, Signal

from song_db import SongDatabase


class SequencePrefetchWorker(QObject):
    figures_ready = Signal(object)              # (Datenversion, Figuren)
    details_ready = Signal(int, int, object)    # (Auftrag, Datenversion, Details)

    DETAILS_DELAY_S = 0.3     # erst nach dem Wechsel lesen
    DETAILS_BATCH = 50        # Sequenzen je Portion
    DETAILS_PAUSE_S = 0.02    # Pause zwischen den Portionen

    def __init__(self, open_connection, parent=None):
        """open_connection: z. B. db.open_worker_connection; laeuft im Thread."""
        super().__init__(parent)
        self._open_connection = open_connection
        self._cond = threading.Condition()
        self._want_figures = False
        self._figures_running = False
        self._details_job = None                # (Auftrag, Sequenz-IDs)
        self._thread = None
        self._stop = False

    def request_figures(self):
        with self._cond:
            self._want_figures = True
            self._start()
            self._cond.notify()

    def figures_pending(self) -> bool:
        """Wartet oder laeuft ein Figuren-Vorbau? (intern#274, fuer den Pull)"""
        with self._cond:
            return self._want_figures or self._figures_running

    def request_details(self, token, seq_ids):
        """Ein noch wartender Detail-Auftrag wird ersetzt."""
        with self._cond:
            self._details_job = (token, list(seq_ids))
            self._start()
            self._cond.notify()

    def shutdown(self, wait=1.0):
        with self._cond:
            self._stop = True
            self._cond.notify()
        if self._thread is not None:
            self._thread.join(wait)

    def _start(self):
        if self._thread is None:
            self._thread = threading.Thread(target=self._loop, daemon=True,
                                            name="sequence-prefetch")
            self._thread.start()

    def _next_job(self):
        with self._cond:
            while not self._stop and self._details_job is None and not self._want_figures:
                self._cond.wait()
            if self._stop:
                return None
            if self._details_job is not None:   # zuerst: haengt am Wechsel
                job, self._details_job = ("details", self._details_job), None
                return job
            self._want_figures = False
            self._figures_running = True
            return ("figures", None)

    def _superseded(self, wait=0.0) -> bool:
        """Bis zu wait Sekunden warten; True, wenn inzwischen ein neuerer
        Detail-Auftrag kam oder der Worker beendet wird."""
        with self._cond:
            if wait > 0 and not self._stop and self._details_job is None:
                self._cond.wait(wait)
            return self._stop or self._details_job is not None

    def _run_details(self, conn, token, ids):
        """Gemessen bei 40 % (intern#268): Liest der Worker die ganze Liste sofort,
        ringt er mitten im Wechsel mit dem Hauptthread um den GIL. Deshalb erst
        DETAILS_DELAY_S warten, bis der Wechsel durch ist, dann in Portionen mit
        Pause dazwischen. Ein neuerer Auftrag bricht ab; jede Portion kommt einzeln."""
        if self._superseded(self.DETAILS_DELAY_S):
            return
        ver = SongDatabase.sequence_data_version_on_connection(conn)
        for i in range(0, len(ids), self.DETAILS_BATCH):
            if i and self._superseded(self.DETAILS_PAUSE_S):
                return
            part = ids[i:i + self.DETAILS_BATCH]
            found = SongDatabase.sequence_details_on_connection(conn, part)
            if self._stop:                      # beim Beenden nichts mehr senden
                return
            self.details_ready.emit(token, ver, found)

    def _loop(self):
        conn = None
        try:
            conn = self._open_connection()
            while True:
                job = self._next_job()
                if job is None:
                    return
                kind, arg = job
                try:
                    if kind == "details":
                        self._run_details(conn, *arg)
                    else:
                        res = SongDatabase.build_sequence_figures_on_connection(conn)
                        # Review #204: nach shutdown() kein Signal mehr (die App
                        # schliesst dann schon DB und Engine)
                        if res is not None and not self._stop:
                            self.figures_ready.emit(res)
                except Exception as exc:          # Hintergrund: nie die App reissen
                    print(f"[SeqPrefetch] {kind} fehlgeschlagen: {type(exc).__name__}: {exc}")
                finally:
                    if kind == "figures":
                        with self._cond:
                            self._figures_running = False
        except Exception as exc:
            print(f"[SeqPrefetch] Verbindung fehlgeschlagen: {type(exc).__name__}: {exc}")
        finally:
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass
