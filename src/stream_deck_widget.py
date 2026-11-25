"""
Stream-Deck-Widget fuer Callers Caddy (BL-168).

Gibt dem Rules-System ein sichtbares Gesicht: Rules mit button_number > 0
erscheinen als quadratische Buttons. Ein Klick fuehrt die Rule manuell aus
(Trigger uebersprungen, Conditions werden geprueft).

Layout: quadratische Kacheln, die die Widget-Flaeche moeglichst gut ausnutzen.
Die Spaltenzahl wird so gewaehlt, dass die Kacheln maximal gross werden; die
Zeilen werden gleichmaessig gefuellt (7 Buttons -> 4+3). Die Button-Matrix ist
im Widget zentriert, die Buttons sind innerhalb der Matrix linksbuendig.
"""

import math
import os

from PySide6.QtWidgets import QWidget, QToolButton, QLabel
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QIcon

from i18n import _t
from ui_helpers import tinted_icon


class StreamDeckWidget(QWidget):
    """Dock-Widget mit dynamisch angeordneten Rule-Buttons."""

    _MARGIN = 8      # Rand um die Matrix
    _GAP = 6         # Abstand zwischen Buttons
    _MIN_SIDE = 40   # Minimale Button-Kantenlaenge
    _MAX_SIDE = 160  # Maximale Button-Kantenlaenge

    _EDIT_SIZE = 18  # Kantenlaenge des Zahnrad-Edit-Buttons

    def __init__(self, rule_engine, skin_mgr=None, execute_callback=None,
                 edit_callback=None, parent=None):
        super().__init__(parent)
        self._engine = rule_engine
        self._skin_mgr = skin_mgr
        self._execute_callback = execute_callback
        self._edit_callback = edit_callback
        self._buttons: list[QToolButton] = []
        self.setMinimumSize(120, 120)

        # Hinweis bei leerem Deck
        self._empty_label = QLabel(_t("streamdeck.empty"), self)
        self._empty_label.setAlignment(Qt.AlignCenter)
        self._empty_label.setWordWrap(True)
        self._empty_label.setStyleSheet("color: #888888;")
        self._empty_label.hide()

        # Zahnrad-Edit-Button: randlos, hintergrundlos, NICHT Teil der Matrix.
        # Sitzt oben rechts am Rand und oeffnet direkt das Rules-Widget.
        self._edit_btn = QToolButton(self)
        self._edit_btn.setAutoRaise(True)
        self._edit_btn.setFocusPolicy(Qt.NoFocus)
        self._edit_btn.setCursor(Qt.PointingHandCursor)
        self._edit_btn.setToolTip(_t("streamdeck.edit_tooltip"))
        self._edit_btn.setStyleSheet(
            "QToolButton { border: none; background: transparent; padding: 0px; }")
        self._edit_btn.clicked.connect(self._on_edit_clicked)

        self.refresh()

    # --- Skin ---

    def apply_skin(self, skin_mgr):
        """Neue Skin-Referenz uebernehmen und Buttons mit neuen Icons neu bauen."""
        self._skin_mgr = skin_mgr
        self.refresh()

    def _button_stylesheet(self) -> str:
        """Theme-konforme Button-Optik — die (monochromen) Icons sitzen wie im
        Rest der App auf 'button_bg'. Ohne das waeren weisse Icons auf hellen
        System-Buttons (Win11) unsichtbar.
        """
        if not self._skin_mgr:
            return ""
        c = self._skin_mgr.color
        bg = c("button_bg", "#615f8b")
        hover = c("button_hover", "#7a78a5")
        pressed = c("button_pressed", "#4e4c73")
        text = c("button_text", "#f7f7f7")
        border = c("border", "#555555")
        return (
            "QToolButton#deckBtn {"
            f" background-color: {bg}; color: {text};"
            f" border: 1px solid {border}; border-radius: 8px;"
            " padding: 0px; margin: 0px;"
            " }"
            f"QToolButton#deckBtn:hover {{ background-color: {hover}; }}"
            f"QToolButton#deckBtn:pressed {{ background-color: {pressed}; }}"
        )

    def _tinted_icon(self, svg_name: str, color_key: str) -> QIcon:
        """Faerbt ein (monochromes) Cache-Icon auf eine Theme-Farbe um.

        Das Zahnrad liegt im Cache in icon_color (Win11: weiss) vor — auf dem
        Widget-Hintergrund waere das unsichtbar. Wir tinten es daher auf
        `color_key` (z.B. 'text_dim'), der mit widget_bg kontrastiert.
        """
        if not self._skin_mgr:
            return QIcon()
        return tinted_icon(self._skin_mgr, svg_name, color_key,
                           px=self._EDIT_SIZE * 2)

    def _on_edit_clicked(self):
        if self._edit_callback:
            self._edit_callback()

    # --- Aufbau ---

    def refresh(self):
        """Liest die Deck-Rules neu ein und baut die Buttons auf."""
        for btn in self._buttons:
            btn.deleteLater()
        self._buttons = []

        # Theme-Buttonfarben auf alle Deck-Buttons anwenden.
        # Nur die Matrix-Buttons stylen (QToolButton#deck), damit der randlose
        # Edit-Button unberuehrt bleibt.
        self.setStyleSheet(self._button_stylesheet())

        # Zahnrad-Edit-Button (getintet, damit auf hellem Win11-BG sichtbar)
        self._edit_btn.setIcon(self._tinted_icon("gear.svg", "text_dim"))
        self._edit_btn.setIconSize(QSize(self._EDIT_SIZE, self._EDIT_SIZE))
        self._edit_btn.setVisible(self._edit_callback is not None)

        rules = self._engine.get_stream_deck_rules() if self._engine else []

        for rule in rules:
            btn = QToolButton(self)
            btn.setObjectName("deckBtn")   # nur Matrix-Buttons per QSS stylen
            btn.setToolButtonStyle(Qt.ToolButtonIconOnly)
            btn.setAutoRaise(False)
            btn.setFocusPolicy(Qt.NoFocus)
            tooltip = rule.button_tooltip or rule.name
            btn.setToolTip(tooltip)
            self._apply_button_face(btn, rule)
            btn.clicked.connect(
                lambda checked=False, rid=rule.id: self._on_button_clicked(rid))
            btn.show()
            self._buttons.append(btn)

        self._empty_label.setVisible(not self._buttons)
        self._relayout()

    def _apply_button_face(self, btn: QToolButton, rule):
        """Setzt Icon oder Anfangsbuchstaben-Fallback auf den Button."""
        icon_path = ""
        if self._skin_mgr and rule.button_icon:
            candidate = os.path.join(self._skin_mgr.icon_dir, rule.button_icon)
            if os.path.isfile(candidate):
                icon_path = candidate

        if icon_path:
            btn.setIcon(QIcon(icon_path))
            btn.setText("")
            btn.setToolButtonStyle(Qt.ToolButtonIconOnly)
        else:
            # Fallback: Anfangsbuchstabe der Rule
            letter = (rule.name or "?").strip()[:1].upper() or "?"
            btn.setIcon(QIcon())
            btn.setText(letter)
            btn.setToolButtonStyle(Qt.ToolButtonTextOnly)

    def _on_button_clicked(self, rule_id: str):
        if self._execute_callback:
            self._execute_callback(rule_id)
        elif self._engine:
            self._engine.execute_rule_manual(rule_id)

    # --- Layout ---

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._relayout()

    def _relayout(self):
        """Positioniert die Buttons als moeglichst grosse quadratische Kacheln."""
        self._empty_label.setGeometry(self.rect())
        # Zahnrad oben rechts am Rand — immer, auch bei leerem Deck; ueber der
        # Matrix (raise_), damit ein Button es nicht verdeckt.
        es = self._EDIT_SIZE
        self._edit_btn.setGeometry(self.width() - es - 3, 3, es, es)
        self._edit_btn.raise_()
        n = len(self._buttons)
        if n == 0:
            return

        avail_w = max(1, self.width() - 2 * self._MARGIN)
        avail_h = max(1, self.height() - 2 * self._MARGIN)

        cols, side = self._best_grid(n, avail_w, avail_h)
        rows = math.ceil(n / cols)
        row_counts = self._distribute(n, rows)
        max_cols = max(row_counts) if row_counts else cols

        # Matrix-Bounding-Box zentrieren
        matrix_w = max_cols * side + (max_cols - 1) * self._GAP
        matrix_h = rows * side + (rows - 1) * self._GAP
        origin_x = (self.width() - matrix_w) // 2
        origin_y = (self.height() - matrix_h) // 2

        icon_px = max(16, int(side * 0.82))
        # Fallback-Buchstabe: deutlich groesser, damit er die Kachel aehnlich
        # fuellt wie ein Icon. Eine Glyphe rendert nur einen Teil ihrer
        # Pixelgroesse (Cap-Height + Bearing), 0.5 wirkte daher sehr klein.
        font_px = max(18, int(side * 0.66))

        idx = 0
        for r in range(rows):
            y = origin_y + r * (side + self._GAP)
            for c in range(row_counts[r]):
                x = origin_x + c * (side + self._GAP)  # linksbuendig in der Matrix
                btn = self._buttons[idx]
                btn.setGeometry(x, y, side, side)
                btn.setIconSize(QSize(icon_px, icon_px))
                if btn.toolButtonStyle() == Qt.ToolButtonTextOnly:
                    # WICHTIG: Font MUSS per Stylesheet gesetzt werden. Weil das
                    # Widget ein Stylesheet traegt (_button_stylesheet), ignoriert
                    # Qt ein per setFont() gesetztes Font komplett — der Buchstabe
                    # blieb sonst klein und skalierte nicht mit der Kachel. Die
                    # font-size ergaenzt nur; Hintergrund/Rand kommen weiter aus
                    # der Vorfahren-Regel QToolButton#deckBtn.
                    btn.setStyleSheet(
                        f"QToolButton {{ font-size: {font_px}px; font-weight: 700; }}")
                idx += 1

    def _best_grid(self, n: int, avail_w: int, avail_h: int) -> tuple[int, int]:
        """Waehlt Spaltenzahl mit maximaler Kantenlaenge; Tie -> gleichmaessiger.

        Returns (cols, side).
        """
        best_cols, best_side, best_waste = 1, -1.0, 10 ** 9
        for cols in range(1, n + 1):
            rows = math.ceil(n / cols)
            side_w = (avail_w - (cols - 1) * self._GAP) / cols
            side_h = (avail_h - (rows - 1) * self._GAP) / rows
            side = min(side_w, side_h)
            if side <= 0:
                continue
            waste = cols * rows - n  # leere Zellen = Ungleichmaessigkeit
            if side > best_side + 0.5 or (
                    abs(side - best_side) <= 0.5 and waste < best_waste):
                best_cols, best_side, best_waste = cols, side, waste
        side = int(max(self._MIN_SIDE, min(self._MAX_SIDE, best_side)))
        return best_cols, side

    @staticmethod
    def _distribute(n: int, rows: int) -> list[int]:
        """Verteilt n Buttons moeglichst gleichmaessig auf rows Zeilen.

        Vollere Zeilen zuerst (7,2 -> [4,3]).
        """
        if rows <= 0:
            return [n]
        base, rem = divmod(n, rows)
        return [base + 1 if i < rem else base for i in range(rows)]
