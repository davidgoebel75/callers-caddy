"""Gemeinsame Testeinrichtung.

Legt src/ auf den sys.path — relativ zur eigenen Datei, damit die Tests aus
jedem Verzeichnis heraus laufen — und stellt die QApplication bereit, die
Qt-Widgets zum Leben brauchen.
"""
import atexit
import contextlib
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "src"))

# `import main` richtet beim Laden den Crash-Handler mit os.getcwd() ein, also
# dem Repo-Stamm -> Ausnahmen in Qt-Slots landeten in logs/crashes/ im Repo
# (intern#159). setup() behaelt einen schon vorhandenen Logger, deshalb hier
# vorab einen anlegen, der in ein Temp-Verzeichnis schreibt. Muss vor dem
# Sammeln der Tests passieren (manche importieren main ganz oben).
# Am Ende wieder weg, solange leer; mit Crash-Log bleibt er zum Nachsehen.
import crash_handler  # noqa: E402
_crash_dir = tempfile.mkdtemp(prefix="cc-crash-")
crash_handler._logger = crash_handler.CrashLogger(_crash_dir)


@atexit.register
def _remove_empty_crash_dir():
    with contextlib.suppress(OSError):
        os.rmdir(_crash_dir)

# Ohne Bildschirm rendern: so laufen die Tests auch ueber eine Remote-Sitzung
# und blitzen beim Laufen keine Fenster auf. setdefault, damit man die Variable
# beim Debuggen von aussen ueberschreiben und die Fenster sehen kann.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="session")
def qapp():
    """Eine QApplication fuer die ganze Sitzung — Qt vertraegt nur eine."""
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])
