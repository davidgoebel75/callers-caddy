"""Hintergrund-Rechner fuer Square Flow (intern#247).

Ein Daemon-Thread nimmt Auftraege an (nur der neueste zaehlt), rechnet die Sequenz mit der
Engine durch und meldet das Ergebnis per Qt-Signal (queued in den UI-Thread). Der UI-Thread
wartet nie auf die Engine (Audio-Prioritaet, TIC-0025). Engine und Thread starten erst mit
dem ersten Auftrag.

Zwischenspeicher in zwei Stufen:
- im Arbeitsspeicher: komplette Ergebnisse (mit Animation) der letzten Sequenzen;
- in der DB (sequence_choreo): Ergebnis und, seit intern#263, die Animation (zlib-gepackt).
  Ein Treffer wird sofort gemeldet, ohne die Engine zu starten. Nur bei einem alten Eintrag
  ohne Animation rechnet der Worker danach noch, wenn sie gebraucht wird (Dock sichtbar),
  und meldet ein zweites Mal.

Die Zuordnungen Call-Text -> Callname liest der Worker vor jedem Lauf frisch aus der DB
(eine Abfrage, im Hintergrund-Thread, nur fuer die Kartentexte der Sequenz, intern#263).
Sie gehen in den Schluessel beider Stufen ein:
Aendert sich das Call-Mapping irgendwo, passen alte Ergebnisse nicht mehr und werden neu
gerechnet, ohne dass jede Schreibstelle Bescheid geben muss (Review #192, Punkt 7).
"""
import hashlib
import threading
import time
from collections import OrderedDict

from PySide6.QtCore import QObject, Signal

import perf
from caddy.choreo import analysis, mapping, perf_marks
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
        self._engine_fp = None
        self._cache = OrderedDict()

    def engine(self):
        if self._engine is None:
            self._engine = TamEngine()
        return self._engine

    def available(self):
        return self.engine().available()

    def request(self, token, calls, seq_type, seq_id=None, need_animation=True):
        """Auftrag einreihen; ein noch wartender Auftrag wird ersetzt."""
        with self._cond:
            self._job = (token, tuple(calls), seq_type or "", seq_id, need_animation)
            if self._thread is None:
                self._thread = threading.Thread(target=self._loop, daemon=True,
                                                name="square-flow-worker")
                self._thread.start()
            self._cond.notify()

    def shutdown(self):
        with self._cond:
            self._stop = True
            self._cond.notify()
        if self._engine is not None:
            self._engine.close()

    # --- Thread -------------------------------------------------------------

    def _load_app(self, calls):
        """Aktuelle Zuordnungen Call-Text -> Callname (bei jedem Lauf neu gelesen), nur fuer
        die Kartentexte dieser Sequenz (intern#263). mapping.py schlaegt die Zeilen mit
        abgeschnittenem Leerraum nach, input_hash mit dem Text wie gegeben: beide Formen
        lesen, dazu die Platzhalter, die mapping selbst als Zeile einsetzt."""
        if not self._db_path:
            return {}
        from song_db_sequences import read_choreo_call_names
        texts = set(mapping.SYNTH_LINES)
        for c in calls:
            texts.add(c)
            texts.add(str(c).strip())
        return read_choreo_call_names(self._db_path, texts)

    def _engine_fingerprint(self):
        """Stand der Engine-Datei (ohne den Prozess zu starten)."""
        if self._engine_fp is None:
            path = self.engine().path
            h = hashlib.sha256()
            try:
                with open(path, "rb") as f:
                    for block in iter(lambda: f.read(1 << 20), b""):
                        h.update(block)
                self._engine_fp = h.hexdigest()[:16]
            except (OSError, TypeError):
                self._engine_fp = ""
        return self._engine_fp

    def _emit(self, token, result):
        if not self._stop:
            self.ready.emit(token, result)

    def _loop(self):
        while True:
            with self._cond:
                while self._job is None and not self._stop:
                    self._cond.wait()
                if self._stop:
                    return
                token, calls, seq_type, seq_id, need_anim = self._job
                self._job = None
            try:
                self._run_job(token, calls, seq_type, seq_id, need_anim)
            except Exception as exc:             # Feature darf die App nie mitreissen
                self._emit(token, {"error": f"{type(exc).__name__}: {exc}"})

    def _mark(self, t0, seq_id, n_calls, source, engine_started=False, error=None):
        """Perf-Marke je Auftrag (nur bei eingeschaltetem Performance-Logging)."""
        if perf.is_enabled():
            perf.perf_write(perf_marks.analyse_line(
                seq_id, n_calls, source, (time.perf_counter() - t0) * 1000,
                engine_started=engine_started, error=error))

    def _run_job(self, token, calls, seq_type, seq_id, need_anim):
        t0 = time.perf_counter()
        app = self._load_app(calls)
        ihash = analysis.input_hash(calls, seq_type, app)
        key = ihash                          # Zeilen, Typ und Call-Mapping
        result = self._cache.get(key)
        if result is not None:
            self._cache.move_to_end(key)
            self._emit(token, result)
            self._mark(t0, seq_id, len(calls), perf_marks.SOURCE_MEMORY)
            return
        eng = self.engine()
        if not eng.available():
            self._emit(token, {"error": "engine_missing"})
            self._mark(t0, seq_id, len(calls), perf_marks.SOURCE_ENGINE,
                       error="engine_missing")
            return
        efp = self._engine_fingerprint()
        db = self._db_path if (self._db_path and seq_id is not None) else None
        if db:
            from song_db_sequences import read_choreo_cache
            row = read_choreo_cache(db, seq_id)
            if row and row[0] == ihash and row[1] == efp:
                cached = analysis.from_cache(row[2], row[3])
                if cached is not None:
                    complete = analysis.cache_complete(cached, row[3])
                    if complete:                 # intern#263: Animation oder NO_ANIM -> fertig
                        self._remember(key, cached)
                    self._emit(token, cached)
                    self._mark(t0, seq_id, len(calls), perf_marks.SOURCE_DB)
                    if complete or not need_anim:
                        return
                    t0 = time.perf_counter()     # Engine-Lauf danach eigens messen
        starts = getattr(eng, "start_count", 0)
        result = analysis.analyse_sequence(eng.run, calls, seq_type, app)
        self._remember(key, result)
        self._emit(token, result)
        self._mark(t0, seq_id, len(calls), perf_marks.SOURCE_ENGINE,
                   engine_started=getattr(eng, "start_count", 0) != starts,
                   error=result.get("error") if isinstance(result, dict) else None)
        # Abbruch ohne Engine-Urteil (Timeout, ...) nicht in die DB: sonst lieferte die
        # naechste Sitzung bei verstecktem Dock den abgebrochenen Lauf (Review #196).
        # Der Speicher-Cache behaelt ihn fuer diese Sitzung.
        if db and not (isinstance(result, dict) and result.get("transient")):
            from song_db_sequences import write_choreo_cache
            write_choreo_cache(db, seq_id, ihash, efp, analysis.to_cache(result),
                               analysis.anim_to_blob(result))

    def _remember(self, key, result):
        self._cache[key] = result
        self._cache.move_to_end(key)
        while len(self._cache) > _CACHE_SIZE:
            self._cache.popitem(last=False)

