"""Sequenz-Detail: Programm und Beats aus / hinter / unter dem Call (intern#164)."""
import pytest
from PySide6.QtCore import QPoint, QSettings
from PySide6.QtGui import QTextCursor

from i18n import _t
from caddy.settings import ini_keys
from sequences_widget import LABEL_BELOW, LABEL_INLINE, LABEL_OFF, SequenceViewWidget

CALLS = [
    (1, "Heads Square Thru 4", "call_square_thru", 10.0011, "Square Thru", "Basic 1"),
    (2, "Unbekannter Call-Text", None, None, None, None),
    (3, "Swing Thru", "call_swing_thru", 20.0038, "Swing Thru", "Mainstream"),
]


@pytest.fixture
def settings(tmp_path):
    return QSettings(str(tmp_path / "t.ini"), QSettings.IniFormat)


@pytest.fixture
def view(qapp, keep, settings):
    w = keep(SequenceViewWidget(db=None, settings=settings))
    w.resize(600, 400)
    w._calls = list(CALLS)
    w._text_edit.setHtml(w._make_html(20))
    w.show()
    qapp.processEvents()
    return w


def _render(w, mode):
    w._label_mode = mode
    w._text_edit.setHtml(w._make_html(20))


def _pos_on(w, text):
    cursor = QTextCursor(w._text_edit.document())
    cursor.setPosition(w._text_edit.toPlainText().index(text) + 2)
    return w._text_edit.cursorRect(cursor).center()


def test_standard_ist_hinter_dem_call(view):
    assert view._label_mode == LABEL_INLINE
    lines = view._text_edit.toPlainText().split("\n")
    assert len(lines) == 3 and "Basic 1" in lines[0]


def test_ausblenden_laesst_nur_die_calls_und_das_fragezeichen(view):
    _render(view, LABEL_OFF)
    text = view._text_edit.toPlainText()
    assert "Basic 1" not in text and "Mainstream" not in text
    assert "?" in text.split("\n")[1]


def test_unter_dem_call_eigene_zeile(view):
    _render(view, LABEL_BELOW)
    lines = view._text_edit.toPlainText().split("\n")
    assert lines[0].strip() == "Heads Square Thru 4"
    assert "Basic 1" in lines[1]
    assert lines[2].startswith("Unbekannter Call-Text")   # ohne Etikett keine Leerzeile
    assert lines[3].strip() == "Swing Thru" and "Mainstream" in lines[4]
    assert view._line_calls == [0, 0, 1, 2, 2]


@pytest.mark.parametrize("text, call", [("Basic 1", 0), ("Swing Thru", 2),
                                        ("Mainstream", 2), ("Unbekannt", 1)])
def test_klick_auf_die_unterzeile_trifft_den_call(view, text, call):
    _render(view, LABEL_BELOW)
    assert view._call_text_at(_pos_on(view, text)) == CALLS[call][1]


def test_menue_schaltet_um_und_merkt_es(view, settings):
    view.on_open_call_mapping = lambda texts: None
    menu = view._build_text_menu(_pos_on(view, "Swing Thru"))
    acts = {a.text(): a for a in menu.actions()}
    assert menu.actions()[0].text() == _t("ctx_open_call_mapping_for_call_text")
    assert acts[_t("seq_labels_inline")].isChecked()
    acts[_t("seq_labels_below")].trigger()
    assert view._label_mode == LABEL_BELOW
    assert settings.value(ini_keys.SEQ_DETAIL_LABELS) == LABEL_BELOW


def test_gemerkte_einstellung_gilt_beim_start(keep, settings):
    settings.setValue(ini_keys.SEQ_DETAIL_LABELS, LABEL_OFF)
    w = keep(SequenceViewWidget(db=None, settings=settings))
    assert w._label_mode == LABEL_OFF
    settings.setValue(ini_keys.SEQ_DETAIL_LABELS, "quatsch")
    w2 = keep(SequenceViewWidget(db=None, settings=settings))
    assert w2._label_mode == LABEL_INLINE


def test_unterhalb_der_letzten_zeile_nichts(view):
    _render(view, LABEL_BELOW)
    doc_h = int(view._text_edit.document().size().height())
    assert view._call_text_at(QPoint(50, doc_h + 40)) is None
