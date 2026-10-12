"""Gemeinsame Testeinrichtung.

src/ legt pytest.ini auf den sys.path (pythonpath). Hier: Crash-Handler
umlenken und die QApplication bereitstellen, die Qt-Widgets zum Leben brauchen.
"""
import atexit
import contextlib
import glob
import os
import tempfile

import pytest

# `import main` richtet beim Laden den Crash-Handler mit os.getcwd() ein, also
# dem Repo-Stamm -> Ausnahmen in Qt-Slots landeten in logs/crashes/ im Repo
# (intern#159). setup() behaelt einen schon vorhandenen Logger, deshalb hier
# vorab einen anlegen, der in ein Temp-Verzeichnis schreibt. Muss vor dem
# Sammeln der Tests passieren (manche importieren main ganz oben). setup()
# installiert auch gleich die Hooks, sonst faengt _no_crash_log Ausnahmen nur,
# wenn vorher ein Test main importiert hat.
# Am Ende wieder weg, solange leer; mit Crash-Log bleibt er zum Nachsehen.
import crash_handler
_crash_dir = tempfile.mkdtemp(prefix="cc-crash-")
crash_handler.setup(_crash_dir)


@atexit.register
def _remove_empty_crash_dir():
    with contextlib.suppress(OSError):
        os.rmdir(_crash_dir)


def _crash_logs():
    return set(glob.glob(os.path.join(_crash_dir, "logs", "crashes", "*.log")))


@pytest.fixture(autouse=True)
def _no_crash_log():
    """Eine Ausnahme in einem Qt-Slot bricht den Test nicht ab, der
    Crash-Handler schreibt sie nur ins Log, und die Suite bliebe gruen
    (PR #119). Deshalb schlaegt der Test fehl, sobald waehrend seines Laufs
    ein neues Crash-Log entsteht."""
    before = _crash_logs()
    yield
    new = sorted(_crash_logs() - before)
    if new:
        with open(new[0], encoding="utf-8") as f:
            text = f.read()
        _, sep, exception = text.partition("--- Exception ---")
        pytest.fail(f"Neues Crash-Log {new[0]}\n{sep + exception if sep else text}",
                    pytrace=False)

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
