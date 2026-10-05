"""Gemeinsame Testeinrichtung.

src/ legt pytest.ini auf den sys.path (pythonpath). Hier: Crash-Handler
umlenken und die QApplication bereitstellen, die Qt-Widgets zum Leben brauchen.
"""
import atexit
import contextlib
import os
import tempfile

import pytest

# `import main` richtet beim Laden den Crash-Handler mit os.getcwd() ein, also
# dem Repo-Stamm -> Ausnahmen in Qt-Slots landeten in logs/crashes/ im Repo
# (intern#159). setup() behaelt einen schon vorhandenen Logger, deshalb hier
# vorab einen anlegen, der in ein Temp-Verzeichnis schreibt. Muss vor dem
# Sammeln der Tests passieren (manche importieren main ganz oben).
# Am Ende wieder weg, solange leer; mit Crash-Log bleibt er zum Nachsehen.
import crash_handler
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


@pytest.fixture(autouse=True)
def _fresh_fuzzy_cache(monkeypatch):
    """Der Fuzzy-Cache des Call-Mapping-Dialogs haelt die ganze Sitzung
    (sequence_mapper.fuzzy_suggest_cache). Jeder Test beginnt leer, sonst
    haengt das Verhalten des Dialogs von der Testreihenfolge ab."""
    import sequence_mapper
    monkeypatch.setattr(sequence_mapper, "_fuzzy_cache", (None, {}))
