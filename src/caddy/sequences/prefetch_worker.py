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
Sequenz-Detail, jeweils nur bei passender Datenversion.
"""
import threading

from PySide6.QtCore import QObject, Signal

from song_db import SongDatabase


class SequencePrefetchWorker(QObject):
    figures_ready = Signal(object)              # (Datenversion, Figuren)
    details_ready = Signal(int, int, object)    # (Auftrag, Datenversion, Details)

    def __init__(self, open_connection, parent=None):
        """open_connection: z. B. db.open_worker_connection; laeuft im Thread."""
        super().__init__(parent)
        self._open_connection = open_connection
        self._cond = threading.Condition()
        self._want_figures = False
        self._details_job = None                # (Auftrag, Sequenz-IDs)
        self._thread = None
        self._stop = False

    def request_figures(self):
        with self._cond:
            self._want_figures = True
            self._start()
            self._cond.notify()

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
            return ("figures", None)

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
                        token, ids = arg
                        ver = SongDatabase.sequence_data_version_on_connection(conn)
                        self.details_ready.emit(
                            token, ver, SongDatabase.sequence_details_on_connection(conn, ids))
                    else:
                        res = SongDatabase.build_sequence_figures_on_connection(conn)
                        if res is not None:
                            self.figures_ready.emit(res)
                except Exception as exc:          # Hintergrund: nie die App reissen
                    print(f"[SeqPrefetch] {kind} fehlgeschlagen: {type(exc).__name__}: {exc}")
        except Exception as exc:
            print(f"[SeqPrefetch] Verbindung fehlgeschlagen: {type(exc).__name__}: {exc}")
        finally:
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass
