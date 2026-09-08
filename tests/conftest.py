"""Gemeinsame Testeinrichtung.

Legt src/ auf den sys.path — relativ zur eigenen Datei, damit die Tests aus
jedem Verzeichnis heraus laufen — und stellt die QApplication bereit, die
Qt-Widgets zum Leben brauchen.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "src"))

# Ohne Bildschirm rendern: so laufen die Tests auch ueber eine Remote-Sitzung
# und blitzen beim Laufen keine Fenster auf. setdefault, damit man die Variable
# beim Debuggen von aussen ueberschreiben und die Fenster sehen kann.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="session")
def qapp():
    """Eine QApplication fuer die ganze Sitzung — Qt vertraegt nur eine."""
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])
