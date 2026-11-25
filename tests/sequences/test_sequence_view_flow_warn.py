"""Warn-Knopf vor "Taminations" im Sequenz-Detail (intern#247)."""
from sequences_widget import SequenceViewWidget


def test_warn_knopf_nur_mit_square_flow_und_warnung(keep, monkeypatch):
    w = keep(SequenceViewWidget(db=None))
    monkeypatch.setattr(w, "current_calls", lambda: ["A"])
    w.set_flow_info(["A"], {"warn": True, "warn_text": "Zeile 2: Call unbekannt"})
    assert w._btn_flow_warn.isHidden()                  # Square Flow aus
    w.set_taminations_enabled(True)
    assert not w._btn_flow_warn.isHidden()
    assert "⚠" not in w._lbl_header.text()              # Kopfzeile ohne Warnsymbol
    shown = []
    import sequences_widget as sw
    monkeypatch.setattr(sw.QMessageBox, "information",
                        lambda _p, _t, text: shown.append(text))
    w._btn_flow_warn.click()
    assert shown == ["Zeile 2: Call unbekannt"]
    w.set_flow_info(["A"], {"warn": False, "warn_text": ""})
    assert w._btn_flow_warn.isHidden()
    w.set_flow_info(["A"], {"warn": True, "warn_text": "x"})
    w.set_taminations_enabled(False)
    assert w._btn_flow_warn.isHidden()
