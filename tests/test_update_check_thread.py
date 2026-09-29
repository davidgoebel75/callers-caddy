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


def _warte_auf(bedingung, timeout=5.0):
    ende = time.monotonic() + timeout
    while time.monotonic() < ende:
        QCoreApplication.processEvents()
        if bedingung():
            return True
        time.sleep(0.01)
    return False


class _Fenster(QObject):
    """Minimaler Ersatz fuer das Hauptfenster (nur Parent + _settings)."""
    _settings = None


def _checker(qapp, monkeypatch, ergebnis):
    """UpdateChecker, dessen _on_result mitschreibt (Args + Thread)."""
    monkeypatch.setattr(update_check, "find_latest_update", ergebnis)
    checker = update_check.UpdateChecker(_Fenster(), "0.159")
    aufrufe = []
    orig = checker._on_result

    def _mitschreiben(*args):
        aufrufe.append((args, threading.current_thread() is threading.main_thread()))
        orig(*args)

    monkeypatch.setattr(checker, "_on_result", _mitschreiben)
    # Die Verbindung haengt an der gebundenen Methode aus __init__ -> neu verbinden
    checker._check_done.disconnect()
    checker._check_done.connect(_mitschreiben)
    return checker, aufrufe


def test_ergebnis_kommt_im_main_thread_an(qapp, monkeypatch):
    checker, aufrufe = _checker(qapp, monkeypatch, lambda v: None)
    checker.start()
    assert _warte_auf(lambda: aufrufe)
    assert aufrufe == [(("", "", True), True)]
    assert not checker._running


def test_neuere_version_wird_gemeldet(qapp, monkeypatch):
    checker, aufrufe = _checker(qapp, monkeypatch,
                                lambda v: ("0.160", "https://example.invalid/u.zip"))
    gezeigt = []
    monkeypatch.setattr(checker, "_show_update_dialog",
                        lambda ver, url: gezeigt.append((ver, url)))
    checker.start()
    assert _warte_auf(lambda: gezeigt)
    assert gezeigt == [("0.160", "https://example.invalid/u.zip")]


def test_fehler_meldet_ok_false(qapp, monkeypatch):
    def _kaputt(v):
        raise OSError("offline")

    checker, aufrufe = _checker(qapp, monkeypatch, _kaputt)
    fehlgeschlagen = []
    monkeypatch.setattr(checker, "_show_check_failed", lambda: fehlgeschlagen.append(1))
    checker.check_now()
    assert _warte_auf(lambda: fehlgeschlagen)
    assert aufrufe[0][0] == ("", "", False)


def test_doppelstart_wird_ignoriert(qapp, monkeypatch):
    freigabe = threading.Event()
    zaehler = []

    def _langsam(v):
        zaehler.append(1)
        freigabe.wait(5)
        return None

    checker, aufrufe = _checker(qapp, monkeypatch, _langsam)
    checker.start()
    checker.start()
    checker.check_now()
    freigabe.set()
    assert _warte_auf(lambda: aufrufe)
    QCoreApplication.processEvents()
    assert len(zaehler) == 1
    assert len(aufrufe) == 1


def test_beenden_waehrend_der_pruefung_ohne_qt_fatal():
    """Regression intern#134: Fenster schliessen und App beenden, waehrend die
    Netzabfrage noch laeuft. Mit dem alten QThread brach Qt hier ab
    ("QThread: Destroyed while thread '' is still running", Exit-Code != 0)."""
    skript = textwrap.dedent(f"""
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
    lauf = subprocess.run([sys.executable, "-c", skript], capture_output=True,
                          text=True, timeout=30, env=env)
    ausgabe = lauf.stdout + lauf.stderr
    assert "Destroyed while thread" not in ausgabe
    assert "ENDE" in lauf.stdout
    assert lauf.returncode == 0, ausgabe
