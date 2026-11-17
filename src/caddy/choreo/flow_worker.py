"""Hintergrund-Rechner fuer Square Flow (intern#247).

Ein Daemon-Thread nimmt Auftraege an (nur der neueste zaehlt), rechnet die Sequenz mit der
Engine durch und meldet das Ergebnis per Qt-Signal (queued in den UI-Thread). Der UI-Thread
wartet nie auf die Engine (Audio-Prioritaet, TIC-0025). Engine und Thread starten erst mit
dem ersten Auftrag.
"""
import threading
from collections import OrderedDict

from PySide6.QtCore import QObject, Signal

from caddy.choreo import analysis
from caddy.choreo.engine import TamEngine

_CACHE_SIZE = 64


class SquareFlowWorker(QObject):
    ready = Signal(int, object)          # (token, Ergebnis-dict oder {"error": ...})

    def __init__(self, db_path=None, engine=None, parent=None):
        super().__init__(parent)
        self._db_path = db_path
        self._engine = engine
        self._cond = threading.Condition()
        self._job = None
        self._thread = None
        self._stop = False
        self._app = None
        self._cache = OrderedDict()

    def engine(self):
        if self._engine is None:
            self._engine = TamEngine()
        return self._engine

    def available(self):
        return self.engine().available()

    def request(self, token, calls, seq_type):
        """Auftrag einreihen; ein noch wartender Auftrag wird ersetzt."""
        with self._cond:
            self._job = (token, tuple(calls), seq_type or "")
            if self._thread is None:
                self._thread = threading.Thread(target=self._loop, daemon=True,
                                                name="square-flow-worker")
                self._thread.start()
            self._cond.notify()

    def invalidate(self):
        """Call-Mapping oder Tabelle geaendert: Zwischenspeicher verwerfen."""
        with self._cond:
            self._cache.clear()
            self._app = None

    def shutdown(self):
        with self._cond:
            self._stop = True
            self._cond.notify()
        if self._engine is not None:
            self._engine.close()

    # --- Thread -------------------------------------------------------------

    def _load_app(self):
        if self._app is None:
            from song_db_sequences import read_choreo_call_names
            self._app = read_choreo_call_names(self._db_path) if self._db_path else {}
        return self._app

    def _loop(self):
        while True:
            with self._cond:
                while self._job is None and not self._stop:
                    self._cond.wait()
                if self._stop:
                    return
                token, calls, seq_type = self._job
                self._job = None
            key = (calls, seq_type)
            result = self._cache.get(key)
            if result is None:
                try:
                    eng = self.engine()
                    if not eng.available():
                        result = {"error": "engine_missing"}
                    else:
                        result = analysis.analyse_sequence(eng.run, calls, seq_type,
                                                           self._load_app())
                        self._cache[key] = result
                        while len(self._cache) > _CACHE_SIZE:
                            self._cache.popitem(last=False)
                except Exception as exc:          # Feature darf die App nie mitreissen
                    result = {"error": f"{type(exc).__name__}: {exc}"}
            else:
                self._cache.move_to_end(key)
            if not self._stop:
                self.ready.emit(token, result)
