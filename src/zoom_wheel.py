"""STRG + Mausrad zum Zoomen (BL-166).

Zentraler Event-Filter fuer alle Widgets, die bereits eine Zoom-Funktion
haben. Der Filter ruft ausschliesslich die *vorhandenen* Zoom-Callables des
Widgets auf — Schrittweite, Grenzen und Label-Aktualisierung bleiben damit
Sache des jeweiligen Widgets, es gibt keine zweite Zoom-Logik.

Verwendung:

    from zoom_wheel import install_ctrl_wheel_zoom

    install_ctrl_wheel_zoom(self._table, self._on_zoom_in, self._on_zoom_out)

Der Filter wird auf dem Zielwidget UND — falls es eine ScrollArea ist — auf
dessen Viewport installiert, weil QAbstractScrollArea Wheel-Events am
Viewport zustellt.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, QEvent, Qt
from PySide6.QtWidgets import QAbstractScrollArea

# Ein Maus-Rasterschritt in Achtel-Grad (Qt-Konvention)
_NOTCH = 120


class _CtrlWheelZoomFilter(QObject):
    """Faengt Wheel-Events mit gedrueckter STRG-Taste ab."""

    def __init__(self, parent, zoom_in, zoom_out):
        super().__init__(parent)
        self._zoom_in = zoom_in
        self._zoom_out = zoom_out
        self._accum = 0     # Restwinkel fuer stufenlose Raeder/Touchpads

    def eventFilter(self, obj, event):
        if event.type() != QEvent.Wheel:
            return False
        if not (event.modifiers() & Qt.ControlModifier):
            return False

        self._accum += event.angleDelta().y()
        while self._accum >= _NOTCH:
            self._accum -= _NOTCH
            self._zoom_in()
        while self._accum <= -_NOTCH:
            self._accum += _NOTCH
            self._zoom_out()

        # Event verbrauchen — sonst scrollt das Widget zusaetzlich, und
        # QTextEdit/QTextBrowser wuerde seinen eingebauten Ctrl+Wheel-Zoom
        # anwerfen und den Zoom des Widgets ueberschreiben.
        event.accept()
        return True


def install_ctrl_wheel_zoom(target, zoom_in, zoom_out):
    """Aktiviert STRG + Mausrad auf ``target``.

    Args:
        target: Widget, ueber dem gezoomt werden soll.
        zoom_in: Callable ohne Argumente — vorhandene Zoom-in-Funktion.
        zoom_out: Callable ohne Argumente — vorhandene Zoom-out-Funktion.

    Returns:
        Den installierten Filter (am ``target`` geparented, muss nicht
        selbst am Leben gehalten werden).
    """
    filt = _CtrlWheelZoomFilter(target, zoom_in, zoom_out)
    target.installEventFilter(filt)
    if isinstance(target, QAbstractScrollArea):
        target.viewport().installEventFilter(filt)
    return filt
