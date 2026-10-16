"""Standard-Buttons der Qt-Dialoge in der App-Sprache (intern#217).

Qt beschriftet Yes/No/Cancel usw. selbst; ohne geladene qtbase-Uebersetzung
bleiben sie englisch, auch wenn der Rest der Oberflaeche deutsch ist.
"""
import pytest
from PySide6.QtWidgets import QMessageBox

from qt_translation import install_qt_translation


@pytest.fixture
def lang(qapp):
    """Installiert die Qt-Uebersetzung und stellt am Ende Englisch wieder her,
    damit die Sitzungs-QApplication fuer andere Tests unveraendert bleibt."""
    yield install_qt_translation
    install_qt_translation("en")


def _button_texts():
    box = QMessageBox()
    box.setStandardButtons(QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel)
    texts = {box.buttonRole(b): b.text().replace("&", "") for b in box.buttons()}
    box.deleteLater()
    return texts


def test_german_buttons(lang):
    lang("de")
    assert _button_texts() == {
        QMessageBox.YesRole: "Ja",
        QMessageBox.NoRole: "Nein",
        QMessageBox.RejectRole: "Abbrechen",
    }


def test_switching_language_replaces_translation(lang):
    """Sprachwahl im Migrations-Tool: der zweite Aufruf ersetzt den ersten."""
    lang("de")
    lang("ja")
    # Qt-Konvention fuer Japanisch: Kuerzel in Klammern, "はい(&Y)"
    assert _button_texts()[QMessageBox.YesRole] == "はい(Y)"
    lang("en")
    assert _button_texts() == {
        QMessageBox.YesRole: "Yes",
        QMessageBox.NoRole: "No",
        QMessageBox.RejectRole: "Cancel",
    }
