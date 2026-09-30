"""Update-Pruefung im Hintergrund (intern#134).

Die Netzabfrage laeuft in einem Daemon-Thread statt in einem QThread. Ein
QThread, der beim Beenden noch im Netz-Timeout haengt, wurde mit dem
Hauptfenster zerstoert -> Qt Fatal "QThread: Destroyed while thread is still
running". Geprueft wird: das Ergebnis kommt im Main-Thread an, und ein
Beenden waehrend der Pruefung endet sauber.
"""
import os
import subprocess
import sys
import textwrap
import threading
import time

from PySide6.QtCore import QCoreApplication, QObject

import update_check

_SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")


def _wait_for(condition, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        QCoreApplication.processEvents()
        if condition():
            return True
        time.sleep(0.01)
    return False


class _Window(QObject):
    """Minimaler Ersatz fuer das Hauptfenster (nur Parent + _settings)."""
    _settings = None


def _checker(qapp, monkeypatch, result):
    """UpdateChecker, dessen _on_result mitschreibt (Args + Thread).

    _on_result wird auf der KLASSE ersetzt, bevor der Checker gebaut wird:
    __init__ verbindet so direkt den Mitschreiber, und der Test laeuft ueber
    die echte QueuedConnection aus update_check.py.
    """
    monkeypatch.setattr(update_check, "find_latest_update", result)
    calls = []
    orig = update_check.UpdateChecker._on_result

    def _record(self, *args):
        calls.append((args, threading.current_thread() is threading.main_thread()))
        orig(self, *args)

    monkeypatch.setattr(update_check.UpdateChecker, "_on_result", _record)
    return update_check.UpdateChecker(_Window(), "0.159"), calls


def test_result_arrives_in_main_thread(qapp, monkeypatch):
    checker, calls = _checker(qapp, monkeypatch, lambda v: None)
    checker.start()
    assert _wait_for(lambda: calls)
    assert calls == [(("", "", True), True)]
    assert not checker._running


def test_newer_version_is_reported(qapp, monkeypatch):
    checker, calls = _checker(qapp, monkeypatch,
                              lambda v: ("0.160", "https://example.invalid/u.zip"))
    shown = []
    monkeypatch.setattr(checker, "_show_update_dialog",
                        lambda ver, url: shown.append((ver, url)))
    checker.start()
    assert _wait_for(lambda: shown)
    assert shown == [("0.160", "https://example.invalid/u.zip")]


def test_error_reports_ok_false(qapp, monkeypatch):
    def _broken(v):
        raise OSError("offline")

    checker, calls = _checker(qapp, monkeypatch, _broken)
    failed = []
    monkeypatch.setattr(checker, "_show_check_failed", lambda: failed.append(1))
    checker.check_now()
    assert _wait_for(lambda: failed)
    assert calls[0][0] == ("", "", False)


def test_double_start_is_ignored(qapp, monkeypatch):
    release = threading.Event()
    queries = []

    def _slow(v):
        queries.append(1)
        release.wait(5)
        return None

    checker, calls = _checker(qapp, monkeypatch, _slow)
    checker.start()
    checker.start()
    checker.check_now()
    release.set()
    assert _wait_for(lambda: calls)
    QCoreApplication.processEvents()
    assert len(queries) == 1
    assert len(calls) == 1


def test_manual_click_during_startup_check_gets_feedback(qapp, monkeypatch):
    """Review #61: "Nach Updates suchen" waehrend die Start-Pruefung noch
    laeuft, startet keinen zweiten Thread, bekommt aber Rueckmeldung."""
    release = threading.Event()

    def _slow(v):
        release.wait(5)
        return None

    checker, calls = _checker(qapp, monkeypatch, _slow)
    up_to_date = []
    monkeypatch.setattr(checker, "_show_up_to_date", lambda: up_to_date.append(1))
    checker.start()
    checker.check_now()
    release.set()
    assert _wait_for(lambda: up_to_date)
    assert len(calls) == 1


def test_emit_after_checker_destroyed_is_swallowed(qapp, monkeypatch):
    """Endet die Pruefung erst, nachdem der Checker beim Beenden zerstoert
    wurde, darf der Hintergrund-Thread nicht mit RuntimeError abbrechen."""
    import shiboken6
    monkeypatch.setattr(update_check, "find_latest_update", lambda v: None)
    checker = update_check.UpdateChecker(_Window(), "0.159")
    shiboken6.delete(checker)
    errors = []
    monkeypatch.setattr(threading, "excepthook", lambda args: errors.append(args))
    t = threading.Thread(target=checker._run_check)
    t.start()
    t.join(5)
    assert not t.is_alive()
    assert errors == []


def test_quit_during_check_without_qt_fatal():
    """Regression intern#134: Fenster schliessen und App beenden, waehrend die
    Netzabfrage noch laeuft. Mit dem alten QThread brach Qt hier ab
    ("QThread: Destroyed while thread '' is still running", Exit-Code != 0)."""
    script = textwrap.dedent(f"""
        import sys, time
        sys.path.insert(0, {_SRC!r})
        from PySide6.QtCore import QTimer, qInstallMessageHandler
        from PySide6.QtWidgets import QApplication, QMainWindow
        qInstallMessageHandler(lambda typ, ctx, msg: print("QT-MSG:", msg, flush=True))
        import update_check
        update_check.find_latest_update = lambda v: time.sleep(5)
        app = QApplication([])
        win = QMainWindow()
        win._update_checker = update_check.UpdateChecker(win, "0.159")
        QTimer.singleShot(50, win._update_checker.start)
        QTimer.singleShot(300, win.close)
        QTimer.singleShot(350, app.quit)
        app.exec()
        del win
        print("ENDE", flush=True)
    """)
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
    run = subprocess.run([sys.executable, "-c", script], capture_output=True,
                          text=True, timeout=30, env=env)
    output = run.stdout + run.stderr
    assert "Destroyed while thread" not in output
    assert "ENDE" in run.stdout
    assert run.returncode == 0, output
