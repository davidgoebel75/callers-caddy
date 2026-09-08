"""Zentraler Mausrad-Schutz fuer Eingabefelder.

Problem: Schwebt der Mauszeiger beim Scrollen durch ein Fenster zufaellig
ueber einer ComboBox / SpinBox / einem Slider, aendert das Mausrad deren Wert —
Einstellungen lassen sich so unbemerkt verstellen (z.B. im Rules-Fenster).

Loesung: ein prozessweiter Event-Filter, der Wheel-Events NUR am Feld selbst
schluckt. Zwei Verhaltensweisen bleiben bewusst erhalten:
  * Ist das ComboBox-Popup geoeffnet (aktiv angeklickt), scrollt die Liste
    normal — der Filter greift am Feld, nicht an der Popup-View.
  * Nur Felder, auf denen der Guard aktiv installiert wird, sind geschuetzt.
    KEIN globaler App-Filter — lange Auswahllisten (z.B. Figuren in den
    Sequenz-Widgets), bei denen Scrollen erwuenscht ist, bleiben unangetastet.

Verwendung:
    from wheel_guard import install_wheel_guard, guard_widget
    install_wheel_guard(self)     # alle Combo-/Spin-/Slider-Felder unter self
    guard_widget(mein_feld)       # ein einzelnes Feld

Beide Funktionen sind idempotent und koennen nach dynamischem Nachbau von
Feldern erneut aufgerufen werden.
"""
from PySide6.QtCore import QObject, QEvent
from PySide6.QtWidgets import QComboBox, QAbstractSpinBox, QSlider

# QAbstractSpinBox deckt QSpinBox, QDoubleSpinBox, QDateTimeEdit etc. ab.
_GUARDED_TYPES = (QComboBox, QAbstractSpinBox, QSlider)


class _WheelGuard(QObject):
    """Schluckt Wheel-Events auf geschuetzten Feldern (kein Weiterreichen)."""

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Wheel and isinstance(obj, _GUARDED_TYPES):
            event.ignore()
            return True
        return super().eventFilter(obj, event)


# Ein einziger, prozessweiter Filter. Parentlos -> Referenz halten gegen GC.
_GUARD = _WheelGuard()


def guard_widget(widget) -> None:
    """Schuetzt ein einzelnes Feld vor Mausrad-Wertaenderung (idempotent)."""
    widget.installEventFilter(_GUARD)


def install_wheel_guard(root) -> None:
    """Schuetzt alle Combo-/Spin-/Slider-Felder unterhalb von ``root``.

    Idempotent: derselbe Filter mehrfach installiert bleibt ein einziger
    Filter — nach dynamischem Feld-Aufbau einfach erneut aufrufen.
    """
    for cls in _GUARDED_TYPES:
        for child in root.findChildren(cls):
            child.installEventFilter(_GUARD)
