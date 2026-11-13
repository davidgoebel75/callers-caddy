"""Beenden waehrend eines Massenlaufs (intern#242): Abbruch zwischen zwei
Songs, Warten bis der Worker wirklich fertig ist."""
import threading
from types import SimpleNamespace

from PySide6.QtCore import QThread

from caddy.bulk.bulk_worker import stop_and_wait
from potential_widget import PotentialWidget


class SongWorker(QThread):
    """Bearbeitet "Songs", bis cancel() kommt; der laufende Song wird fertig."""

    def __init__(self):
        super().__init__()
        self._cancelled = False
        self.started_song = threading.Event()
        self.release = threading.Event()
        self.songs_done = 0

    def cancel(self):
        self._cancelled = True

    def run(self):
        while not self._cancelled:
            self.started_song.set()
            self.release.wait(5)
            self.songs_done += 1


class NoCancelWorker(QThread):
    """Wie der Loesch-Worker: kein cancel(), nur warten."""

    def run(self):
        self.msleep(50)


def test_stop_and_wait_cancels_and_returns_after_thread_end(keep):
    w = keep(SongWorker())
    w.start()
    assert w.started_song.wait(5)
    # Song laeuft noch, wenn stop_and_wait cancel() setzt
    threading.Timer(0.1, w.release.set).start()
    stop_and_wait([w])
    assert w.isFinished()
    assert w.songs_done == 1  # laufender Song fertig, kein weiterer
    assert w.signalsBlocked()  # kein finished-Slot nach db.close()


def test_stop_and_wait_waits_for_worker_without_cancel(keep):
    w = keep(NoCancelWorker())
    w.start()
    stop_and_wait([w])
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
