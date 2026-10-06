"""Sequenz-Detail: Rechtsklick auf einen Call-Text oeffnet das Call-Mapping
fuer genau diesen Call-Text (intern#177).
"""
import pytest
from PySide6.QtCore import QPoint
from PySide6.QtGui import QTextCursor

from i18n import _t
from sequences_widget import SequenceViewWidget

CALLS = [
    (1, "Heads Square Thru 4", "call_square_thru", 10.0011, "Square Thru", "Basic 1"),
    (2, "Head Ladies Chain (Back Home)", "call_teacup_chain", 39.0005, "Teacup Chain", "Plus"),
    (3, "Unbekannter Call-Text", None, None, None, None),
]
MENU_TEXT = "ctx_open_call_mapping_for_call_text"


@pytest.fixture
def view(qapp):
    w = SequenceViewWidget(db=None)
    w.resize(600, 400)
    w._calls = list(CALLS)
    w._text_edit.setHtml(w._make_html(20))
    w.show()
    qapp.processEvents()
    yield w
    w.deleteLater()


def _pos_on(w, call_text) -> QPoint:
    """Punkt mitten im Text der Zeile mit diesem Call-Text."""
    cursor = QTextCursor(w._text_edit.document())
    cursor.setPosition(w._text_edit.toPlainText().index(call_text) + 3)
    return w._text_edit.cursorRect(cursor).center()


@pytest.mark.parametrize("call_text", [c[1] for c in CALLS])
def test_zeile_unter_der_maus_liefert_ihren_call_text(view, call_text):
    assert view._call_text_at(_pos_on(view, call_text)) == call_text


def test_unterhalb_der_letzten_zeile_kein_call_text(view):
    doc_h = int(view._text_edit.document().size().height())
    below = QPoint(50, doc_h + 40)
    assert view._call_text_at(below) is None


def test_eintrag_oeffnet_call_mapping_fuer_diesen_call_text(view):
    opened, refreshed = [], []
    view.on_open_call_mapping = opened.append
    view.refresh = lambda: refreshed.append(True)
    menu = view._build_text_menu(_pos_on(view, CALLS[1][1]))
    first = menu.actions()[0]
    assert first.text() == _t(MENU_TEXT)
    first.trigger()
    assert opened == [["Head Ladies Chain (Back Home)"]]
    assert refreshed == [True]          # Detail liest die Zuordnung neu


def test_auch_fuer_call_text_ohne_zuordnung(view):
    view.on_open_call_mapping = lambda texts: None
    menu = view._build_text_menu(_pos_on(view, CALLS[2][1]))
    assert menu.actions()[0].text() == _t(MENU_TEXT)


def test_ohne_callback_kein_eintrag_aber_standardmenue(view):
    """Beispiel-Betrachter im Call-Mapping: dort ist kein Callback gesetzt."""
    menu = view._build_text_menu(_pos_on(view, CALLS[0][1]))
    texts = [a.text() for a in menu.actions()]
    assert _t(MENU_TEXT) not in texts
    assert any(texts)                   # Kopieren usw. bleiben
