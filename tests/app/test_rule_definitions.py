"""Tests fuer rule_definitions: Registrierung der Standard-Aktionen.

GUI-frei — prueft nur das Action-Registry-Schema, nicht die main.py-Anbindung.
"""
import tempfile

from rule_engine import RuleEngine
from rule_definitions import register_v1_definitions


def _registry():
    eng = RuleEngine(tempfile.gettempdir())
    register_v1_definitions(eng)
    return eng.registry


def test_dock_open_hat_open_position_param():
    # #66: dock_open bekommt den Schalter centered/last, Default centered.
    a = _registry().actions.get("dock_open")
    assert a is not None
    schema = a.params_schema
    assert "dock_name" in schema
    op = schema.get("open_position")
    assert op is not None, "open_position-Param fehlt"
    assert op["type"] == "choice"
    assert op["choices"] == ["centered", "last"]
    assert op["default"] == "centered"
