"""Bedingungen "Genre Is / Is Not" und Aktion "Set Loop Active" (intern#218)."""
import tempfile
import types

import pytest

from caddy.rules.song_conditions import genre_is, genre_is_not, loop_active_wanted


@pytest.mark.parametrize("genres, wahl, ist, ist_nicht", [
    (["Dont Loop this", "Rock"], "Dont Loop this", True, False),
    (["dont loop THIS"], "Dont Loop this", True, False),   # Gross/Klein egal
    (["Rock"], "Dont Loop this", False, True),
    ([], "Dont Loop this", False, True),                  # ohne Genre: Is Not wahr
    (["Rock"], "", False, False),                         # keine Wahl: nie
])
def test_genre_bedingungen(genres, wahl, ist, ist_nicht):
    p = {"genre_name": wahl}
    assert genre_is(genres, p) is ist
    assert genre_is_not(genres, p) is ist_nicht


@pytest.mark.parametrize("state, erwartet", [
    ("on", True), ("off", False), ("Off", False), (None, True)])
def test_loop_active_wunsch(state, erwartet):
    assert loop_active_wanted({"state": state}) is erwartet


def test_bausteine_registriert():
    from rule_definitions import register_v1_definitions
    from rule_engine import RuleEngine

    eng = RuleEngine(tempfile.gettempdir())
    register_v1_definitions(eng)
    reg = eng.registry
    for c in ("genre_is", "genre_is_not"):
        assert reg.conditions[c].params_schema["genre_name"]["type"] == "genre_choice"
    a = reg.actions["set_loop_active"]
    assert a.group == "Audio"
    assert a.params_schema["state"]["choices"] == ["on", "off"]


def test_set_loop_active_setzt_eindeutig(qapp):
    """Zweimal "off" bleibt aus, "on" schaltet ein - anders als Toggle."""
    import main
    from PySide6.QtWidgets import QCheckBox

    class _Win:
        """Nur die Registrierung aus main.py, ohne das ganze Hauptfenster."""
        def __getattr__(self, name):
            return None

    chk = QCheckBox()
    chk.setChecked(True)
    handlers = {}
    win = _Win()
    win.loop_widget = types.SimpleNamespace(chk_loop=chk)
    win.rule_engine = types.SimpleNamespace(
        register_action=lambda t, h: handlers.__setitem__(t, h))
    main.P29MainWindow._register_rule_actions(win)

    set_loop = handlers["set_loop_active"]
    set_loop({"state": "off"})
    set_loop({"state": "off"})
    assert chk.isChecked() is False
    set_loop({"state": "on"})
    assert chk.isChecked() is True


def test_genre_bedingung_im_regel_editor_ist_auswahl(qapp):
    from PySide6.QtWidgets import QComboBox, QHBoxLayout, QWidget
    from rule_definitions import register_v1_definitions
    from rule_engine import RuleEngine
    import rule_widget

    eng = RuleEngine(tempfile.gettempdir())
    register_v1_definitions(eng)
    editor = types.SimpleNamespace(
        _engine=eng,
        _genre_names_provider=lambda: [(1, "Rock"), (2, "Dont Loop this")],
        _on_editor_changed=lambda *a: None)
    holder = QWidget()
    lay = QHBoxLayout(holder)

    rule_widget.RulesWidget._add_cond_param_widgets(
        editor, lay, "genre_is", {"genre_name": "Dont Loop this"}, False)

    w = lay.itemAt(0).widget()
    assert isinstance(w, QComboBox)
    assert w.currentText() == "Dont Loop this"
