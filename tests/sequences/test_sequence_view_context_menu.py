"""Sequenz-Detail: Rechtsklick auf einen Call-Text oeffnet das Call-Mapping
fuer genau diesen Call-Text (intern#177).
"""
import pytest
from PySide6.QtCore import QPoint
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import QMenu

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
    opened = []
    view.on_open_call_mapping = opened.append
    menu = view._build_text_menu(_pos_on(view, CALLS[1][1]))
    first = menu.actions()[0]
    assert first.text() == _t(MENU_TEXT)
    first.trigger()
    assert opened == [["Head Ladies Chain (Back Home)"]]


def test_eintrag_liegt_im_menue_selbst_nicht_in_einem_eingebetteten(view):
    """Ein eingebettetes zweites Menue verdeckte den Eintrag (intern#177)."""
    view.on_open_call_mapping = lambda texts: None
    menu = view._build_text_menu(_pos_on(view, CALLS[0][1]))
    assert not [c for c in menu.children() if isinstance(c, QMenu)]


# ---- nach dem Speichern im Call-Mapping: dieselbe Sequenz, neu gelesen ----

@pytest.fixture
def reloading(view):
    """Sequenz-Detail auf Sequenz 20 von [10, 20, 30]; _update_content ist
    durch einen Zaehler ersetzt (kein DB-Zugriff)."""
    view._seq_ids, view._current_idx = [10, 20, 30], 1
    reloads = []
    view._update_content = lambda: reloads.append(
        view._seq_ids[view._current_idx])
    return view, reloads


def test_nach_dem_neuladen_der_liste_wieder_dieselbe_sequenz(reloading):
    view, reloads = reloading
    state = view.shown_state()
    view._seq_ids, view._current_idx = [5, 10, 15, 20], 0   # Liste neu geladen
    view.restore_shown(state)
    assert reloads == [20]
    assert view._seq_ids == [5, 10, 15, 20]


def test_ausgeblendete_sequenz_bleibt_im_detail_stehen(reloading):
    view, reloads = reloading
    state = view.shown_state()
    view._seq_ids, view._current_idx = [10, 30], 0          # 20 faellt heraus
    view.restore_shown(state)
    assert reloads == [20]


def test_ohne_gezeigte_sequenz_passiert_nichts(view):
    assert view.shown_state() is None
    view.restore_shown(None)


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
