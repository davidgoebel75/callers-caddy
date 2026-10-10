"""Aufklappliste der Comboboxen auf schmalen Bildschirmen.

Auf einer schmalen Laptop-Aufloesung schrumpft das Layout die Comboboxen. Mit
dem Windows-Style ist die Aufklappliste dann nur so breit wie das Control, und
lange Eintraege sind abgeschnitten. P29MainWindow.eventFilter sieht das
Aufklappen (Mausklick, F4, Alt+Runter, ...) VOR der Combobox und macht die
Liste per widen_combo_popup() so breit wie ihren laengsten Eintrag.

Getestet wird mit echten Maus- und Tastatur-Ereignissen durch einen App-weiten
Filter mit derselben Bedingung wie im Hauptfenster — ohne das Hauptfenster
selbst hochzufahren.
"""
import pytest
from PySide6.QtCore import QObject, QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QComboBox, QStyleFactory

from sequences_widget import install_combo_click_to_open
from ui_helpers import opens_combo_popup, widen_combo_popup

# Breiter als die Combobox, aber schmaler als der Offscreen-Bildschirm (800 px)
LANG = "Langer Songtitel - Interpret (Remix)"

# Rand der Aufklappliste wie in allen Skins (skins/*/skin.qss)
SKIN_QSS = "QComboBox QAbstractItemView { border: 1px solid gray; }"


class _WieHauptfenster(QObject):
    """Dieselbe Bedingung wie in P29MainWindow.eventFilter."""

    def eventFilter(self, obj, event):
        if isinstance(obj, QComboBox) and opens_combo_popup(event):
            widen_combo_popup(obj)
        return False


@pytest.fixture(scope="session")
def windows_style(qapp):
    # Fusion (Standard unter offscreen) macht die Liste nicht editierbarer
    # Comboboxen schon von sich aus breit — der User sieht aber Windows.
    return QStyleFactory.create("windows11") or QStyleFactory.create("Windows")


@pytest.fixture(params=[False, True], ids=["fest", "editierbar"])
def combo(request, qapp, windows_style):
    filt = _WieHauptfenster()
    qapp.installEventFilter(filt)
    cb = QComboBox()
    cb.setStyle(windows_style)
    cb.setStyleSheet(SKIN_QSS)
    cb.setEditable(request.param)
    cb.addItems(["kurz", LANG])
    cb.resize(90, 24)
    cb.show()
    yield cb
    cb.hidePopup()
    qapp.removeEventFilter(filt)


def eintrag_passt_ganz(cb):
    view = cb.view()
    return view.viewport().width() >= view.sizeHintForColumn(0)


def klick_auf_pfeil(cb):
    # Rechts auf den Pfeil: bei editierbaren Comboboxen faengt die Mitte das
    # Eingabefeld ab
    QTest.mouseClick(cb, Qt.LeftButton, Qt.NoModifier,
                     QPoint(cb.width() - 8, cb.height() // 2))


AUFKLAPPEN = {
    "Mausklick": klick_auf_pfeil,
    "F4": lambda cb: QTest.keyClick(cb, Qt.Key_F4),
    "Alt+Runter": lambda cb: QTest.keyClick(cb, Qt.Key_Down, Qt.AltModifier),
    "Leertaste": lambda cb: QTest.keyClick(cb, Qt.Key_Space),
    "Select": lambda cb: QTest.keyClick(cb, Qt.Key_Select),
}


def test_ohne_verbreiterung_ist_der_eintrag_abgeschnitten(combo):
    # Gegenprobe: am Filter vorbei aufgeklappt zeigt sich das alte Problem
    combo.showPopup()
    assert not eintrag_passt_ganz(combo)


@pytest.mark.parametrize("aufklappen", AUFKLAPPEN.values(), ids=AUFKLAPPEN.keys())
def test_aufgeklappt_passt_der_laengste_eintrag_ganz_hinein(combo, aufklappen):
    aufklappen(combo)
    if not combo.view().isVisible():
        pytest.skip("Qt klappt editierbare Comboboxen mit dieser Taste nicht auf")
    assert eintrag_passt_ganz(combo)


def test_klick_mitten_ins_feld_der_sequenz_filter(combo):
    # Sequenz-Filter klappen editierbare Comboboxen per Klick ins Textfeld auf
    # (_ComboClickToOpen). Der Klick landet beim QLineEdit, nicht bei der
    # Combobox — am App-Filter vorbei.
    install_combo_click_to_open(combo)
    # QTest liefert an das angegebene Widget, nicht an das Kind unter der Maus
    QTest.mouseClick(combo.lineEdit() or combo, Qt.LeftButton)
    assert combo.view().isVisible()
    assert eintrag_passt_ganz(combo)


def test_kurze_liste_bleibt_so_breit_wie_die_combobox(combo):
    combo.clear()
    combo.addItems(["a", "b"])
    klick_auf_pfeil(combo)
    assert combo.view().window().width() == combo.width()


def test_riesen_eintrag_ragt_nicht_ueber_den_bildschirm(combo):
    combo.addItem("X" * 2000)
    klick_auf_pfeil(combo)
    assert combo.view().window().width() <= combo.screen().availableGeometry().width()
