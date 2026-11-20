"""Modales Fenster: Name und Farbe eines Taenzers im Pilot Square (intern#249).

Geoeffnet per Doppelklick auf einen Taenzer in Square Flow. Haelt selbst keine Daten:
Ergebnis geht zurueck an den Pilot Square, die einzige Ablage. Kennt den Pilot Square
nicht (Palette und Skin-Farben kommen als Parameter), dadurch zirkelfrei.
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QGridLayout, QLabel, QLineEdit, QPushButton,
    QVBoxLayout)

from i18n import _t


class PilotDancerDialog(QDialog):
    """Name (eine Zeile) + Farbe aus der Standardpalette (None = ohne Farbe)."""

    def __init__(self, title: str, name: str, color: Optional[str],
                 palette: list, colors: Optional[dict] = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self._colors = colors or {}
        self._color = color
        self._buttons: list[tuple[Optional[str], QPushButton]] = []

        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(_t("square.dancer_name")))
        self._name = QLineEdit(name)
        self._name.selectAll()
        lay.addWidget(self._name)

        lay.addWidget(QLabel(_t("square.dancer_color")))
        grid = QGridLayout()
        grid.setSpacing(4)
        for i, c in enumerate(palette):
            btn = QPushButton("✕" if c is None else "")
            btn.setFixedSize(34, 28)
            btn.setFocusPolicy(Qt.NoFocus)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setToolTip(_t("square.color_none_short") if c is None else "")
            btn.clicked.connect(lambda _x=False, col=c: self._pick(col))
            self._buttons.append((c, btn))
            grid.addWidget(btn, i // 4, i % 4)
        lay.addLayout(grid)

        box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        box.button(QDialogButtonBox.Ok).setText(_t("btn_ok"))
        box.button(QDialogButtonBox.Cancel).setText(_t("btn_cancel"))
        box.accepted.connect(self.accept)
        box.rejected.connect(self.reject)
        lay.addWidget(box)
        self._restyle()

    def _pick(self, color: Optional[str]):
        self._color = color
        self._restyle()

    def _restyle(self):
        c = self._colors
        border = c.get("border", "#555555")
        mark = c.get("text", "#f0f0f0")
        for col, btn in self._buttons:
            bg = col or c.get("input_bg", "#404040")
            chosen = (col or None) == (self._color or None)
            width = 3 if chosen else 1
            btn.setStyleSheet(
                f"QPushButton {{ background: {bg}; color: {c.get('text_dim', '#888888')}; "
                f"border: {width}px solid {mark if chosen else border}; border-radius: 4px; }}")

    def result_name(self) -> str:
        return self._name.text().strip()

    def result_color(self) -> Optional[str]:
        return self._color
