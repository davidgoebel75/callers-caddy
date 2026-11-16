"""Beenden waehrend eines Massenlaufs (intern#242): Abbruch zwischen zwei
Songs, Warten bis der Worker wirklich fertig ist."""
import threading
from types import SimpleNamespace

from PySide6.QtCore import QThread, Signal

from caddy.bulk.bulk_worker import stop_for_shutdown
from potential_widget import PotentialWidget


class SongWorker(QThread):
    """Bearbeitet "Songs", bis cancel() kommt; der laufende Song wird fertig
    und sein Ergebnis geht wie beim Auto-Loop per loop_found an den
    Hauptthread."""
    loop_found = Signal(int)
    finished = Signal(int, int)

    def __init__(self):
        super().__init__()
        self._cancelled = False
        self.started_song = threading.Event()
        self.release = threading.Event()

    def cancel(self):
        self._cancelled = True

    def run(self):
        song = 0
        while not self._cancelled:
            self.started_song.set()
            self.release.wait(5)
            song += 1
            self.loop_found.emit(song)
        self.finished.emit(song, 0)


class NoCancelWorker(QThread):
    """Wie der Loesch-Worker: kein cancel(), nur warten."""

    def run(self):
        self.msleep(50)


def test_stop_cancels_saves_last_result_and_skips_ui_slots(keep):
    w = keep(SongWorker())
    saved, finished = [], []
    w.loop_found.connect(saved.append)
    w.finished.connect(lambda d, s: finished.append(d))
    w.start()
    assert w.started_song.wait(5)
    # Song laeuft noch, wenn stop_for_shutdown cancel() setzt
    timer = threading.Timer(0.1, w.release.set)
    timer.start()
    stop_for_shutdown(lambda: [w] if w.isRunning() else [])
    timer.join()
    assert w.isFinished()
    assert saved == [1]      # laufender Song fertig und gespeichert, kein weiterer
    assert finished == []    # kein UI-Slot / Folge-Lauf nach dem Beenden


def test_stop_waits_for_worker_without_cancel(keep):
    w = keep(NoCancelWorker())
    w.start()
    stop_for_shutdown(lambda: [w] if w.isRunning() else [])
    assert w.isFinished()


def test_running_workers_lists_only_running(keep):
    running = keep(SongWorker())
    running.release.set()
    done = keep(NoCancelWorker())
    done.start()
    done.wait()
    running.start()
    owner = SimpleNamespace(_bulk_worker=running, _timing_worker=done,
                            _bulk_delete_worker=None)
    try:
        assert PotentialWidget.running_workers(owner) == [running]
    finally:
        running.cancel()
        running.wait()


def test_stop_also_stops_worker_started_during_confirm(keep):
    """Review #172: Waehrend die Rueckfrage offen ist, kann ein Probelauf
    einen Folge-Lauf starten. stop_for_shutdown sieht so lange nach, bis
    nichts mehr laeuft."""
    first, late = keep(SongWorker()), keep(SongWorker())
    first.release.set()
    late.release.set()
    first.start()
    first.finished.connect(lambda d, s: None)
    all_workers = [first]

    def running():
        found = [w for w in all_workers if w.isRunning()]
        if late not in all_workers:      # Folge-Lauf startet nach dem 1. Blick
            late.start()
            all_workers.append(late)
        return found

    stop_for_shutdown(running)
    assert first.isFinished() and late.isFinished()
