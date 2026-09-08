"""
Guided-Tutorial-Engine fuer Callers Caddy (P35).
=================================================
Tooltip-basiertes Tutorial-System mit Overlay, Highlight und Pfeil.

Architektur:
  - TutorialEngine: Zentrale Steuerung (Status, Ablauf, Trigger)
  - TutorialOverlay: Top-Level-Fenster mit Highlight und Tooltip
  - _TooltipBox: Innere Box mit Titel, Text, Buttons

Verwendung:
  engine = TutorialEngine(main_window, settings, skin_mgr)
  engine.register_widget("player", player_widget)
  engine.check_and_start()
"""

from dataclasses import dataclass
from PySide6.QtWidgets import (
    QWidget, QLabel, QPushButton, QHBoxLayout, QVBoxLayout,
    QDockWidget, QApplication,
)
from PySide6.QtCore import Qt, QRect, QPoint, QTimer
from PySide6.QtGui import QPainter, QColor, QPen, QKeySequence, QShortcut
from i18n import _t


# ---------------------------------------------------------------------------
# Datenstrukturen
# ---------------------------------------------------------------------------

@dataclass
class TutorialStep:
    """Ein einzelner Schritt in einem Tutorial."""
    element_path: str       # z.B. "player.btn_play" oder "a+b" fuer Multi-Highlight
    title_key: str          # i18n-Key fuer Titel
    text_key: str           # i18n-Key fuer Beschreibung
    anchor: str = "auto"    # "top", "bottom", "left", "right", "auto"
    action: str = ""        # Optionale Aktion VOR dem Schritt


@dataclass
class TutorialDef:
    """Definition eines Tutorials fuer ein Widget."""
    widget_id: str          # Stabile ID, z.B. "player"
    dock_name: str          # QDockWidget objectName, z.B. "dock_player"
    priority: int           # Hoeher = wird zuerst angeboten
    steps: list             # list[TutorialStep]
    auto_show: bool = True  # Dock automatisch einblenden?
    offer_text_key: str = "tutorial.offer_text"  # Individueller Offer-Text


# ---------------------------------------------------------------------------
# Tooltip-Box (innere Box im Overlay)
# ---------------------------------------------------------------------------

class _TooltipBox(QWidget):
    """Tooltip-Inhalt: Titel, Text, Schritt-Anzeige, Buttons.

    Zeichnet den Hintergrund selbst via paintEvent, weil das Parent-Overlay
    WA_TranslucentBackground hat und QSS-background dadurch nicht greift.
    """

    def __init__(self, parent, step, skin_mgr, on_next, on_skip, on_back,
                 step_num, total_steps, is_offer=False):
        super().__init__(parent)
        self.setFixedWidth(340)

        # Farben fuer paintEvent merken
        self._bg_color = QColor(skin_mgr.color("tutorial_box_bg", "#ffffff"))
        self._border_color = QColor(skin_mgr.color("tutorial_highlight", "#4a9eff"))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(8)

        # Farben aus Skin — dedizierte Tutorial-Box-Farben
        fg = skin_mgr.color("tutorial_box_text", "#f0f0f0")
        fg_dim = skin_mgr.color("text_dim", "#999999")
        accent = skin_mgr.color("tutorial_highlight", "#4a9eff")

        # Titel
        title = QLabel(_t(step.title_key))
        title.setStyleSheet(
            f"font-weight: bold; font-size: 14px; color: {fg}; "
            "border: none; background: transparent;"
        )
        layout.addWidget(title)

        # Text
        text = QLabel(_t(step.text_key))
        text.setWordWrap(True)
        text.setStyleSheet(
            f"color: {fg}; border: none; background: transparent;"
        )
        layout.addWidget(text)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)

        # Schritt-Anzeige (nicht beim Offer)
        if not is_offer:
            step_label = QLabel(f"{step_num} / {total_steps}")
            step_label.setStyleSheet(
                f"color: {fg_dim}; font-size: 11px; border: none; "
                "background: transparent;"
            )
            btn_row.addWidget(step_label)

        btn_row.addStretch()

        # Zurueck (nicht beim ersten Schritt, nicht beim Offer)
        if not is_offer and step_num > 1:
            btn_back = self._make_button(_t("tutorial.btn_back"), fg, "transparent")
            btn_back.clicked.connect(on_back)
            btn_row.addWidget(btn_back)

        if is_offer:
            # Offer: "Tour starten" + "Nicht jetzt"
            btn_yes = self._make_button(_t("tutorial.offer_yes"), "#ffffff", accent)
            btn_yes.clicked.connect(on_next)
            btn_row.addWidget(btn_yes)

            btn_no = self._make_button(_t("tutorial.offer_no"), fg, "transparent")
            btn_no.clicked.connect(on_skip)
            btn_row.addWidget(btn_no)
        else:
            # Normal: Next/Finish + Skip
            if step_num < total_steps:
                btn_next = self._make_button(_t("tutorial.btn_next"), "#ffffff", accent)
                btn_next.clicked.connect(on_next)
                btn_row.addWidget(btn_next)
            else:
                btn_finish = self._make_button(_t("tutorial.btn_finish"), "#ffffff", accent)
                btn_finish.clicked.connect(on_next)
                btn_row.addWidget(btn_finish)

            btn_skip = self._make_button(_t("tutorial.btn_skip"), fg_dim, "transparent")
            btn_skip.clicked.connect(on_skip)
            btn_row.addWidget(btn_skip)

        layout.addLayout(btn_row)

    def paintEvent(self, event):
        """Zeichnet opaken Hintergrund + Rahmen manuell."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = self.rect().adjusted(1, 1, -1, -1)
        # Vollflächiger Hintergrund
        painter.setBrush(self._bg_color)
        painter.setPen(QPen(self._border_color, 3))
        painter.drawRoundedRect(rect, 8, 8)
        painter.end()

    def _make_button(self, text, fg_color, bg_color):
        """Erstellt einen gestylten Button."""
        btn = QPushButton(text)
        border = "1px solid " + fg_color if bg_color == "transparent" else "none"
        btn.setStyleSheet(
            f"QPushButton {{ color: {fg_color}; background: {bg_color}; "
            f"border: {border}; border-radius: 4px; "
            f"padding: 4px 12px; font-size: 12px; }}"
            f"QPushButton:hover {{ opacity: 0.8; }}"
        )
        btn.setCursor(Qt.PointingHandCursor)
        return btn

    def sizeHint(self):
        return super().sizeHint()


# ---------------------------------------------------------------------------
# Highlight-Rahmen (eigenstaendiges Top-Level-Fenster)
# ---------------------------------------------------------------------------

class _HighlightFrame(QWidget):
    """Rahmen um ein oder mehrere Ziel-Elemente.

    Wird als Tool-Fenster des Parents platziert —
    liegt UEBER Docks, bleibt aber beim Parent-Fenster.
    """

    _PADDING = 6

    def __init__(self, targets, skin_mgr, owner=None):
        """targets: Liste von QWidget-Instanzen zum Highlighten.
        owner: Parent-Window (MainWindow/Dialog) — Tool bleibt bei diesem Fenster.
        """
        super().__init__(owner)
        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.Tool  # Bleibt bei Owner, kein Taskbar-Eintrag
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)

        self._targets = targets
        self._color = QColor(skin_mgr.color("tutorial_highlight", "#4a9eff"))
        self._reposition()
        self.show()

    def _reposition(self):
        """Berechnet Position und Groesse aus den globalen Target-Rects."""
        if not self._targets:
            return
        # Bounding-Box aller Targets in globalen Koordinaten
        rects = []
        for t in self._targets:
            if t and t.isVisible():
                global_pos = t.mapToGlobal(QPoint(0, 0))
                rects.append(QRect(global_pos, t.size()))
        if not rects:
            return
        united = rects[0]
        for r in rects[1:]:
            united = united.united(r)

        p = self._PADDING
        self.setGeometry(
            united.x() - p, united.y() - p,
            united.width() + 2 * p, united.height() + 2 * p,
        )

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        pen = QPen(self._color, 3)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(self.rect().adjusted(2, 2, -2, -2), 4, 4)
        painter.end()


# ---------------------------------------------------------------------------
# Overlay (Tooltip + Pfeil als Top-Level-Fenster)
# ---------------------------------------------------------------------------

class TutorialOverlay(QWidget):
    """Transparentes Overlay ueber dem Parent (faengt Klicks ab).

    Highlight-Rahmen und Tooltip-Box sind separate Top-Level-Fenster
    mit WindowStaysOnTopHint — liegen damit IMMER ueber allen Docks.
    """

    _MARGIN = 14      # Abstand Tooltip ↔ Ziel

    def __init__(self, parent, targets, step, skin_mgr,
                 on_next, on_skip, on_back,
                 step_num, total_steps, is_offer=False):
        """parent: QWidget (MainWindow oder QDialog).
        targets: Liste von QWidget-Instanzen (Highlight-Ziele).
        """
        super().__init__(parent)
        self._targets = targets if isinstance(targets, list) else [targets]
        self._step = step
        self._skin_mgr = skin_mgr
        self._on_next = on_next
        self._on_skip = on_skip

        # Komplett transparent — faengt nur Klicks ab
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setGeometry(parent.rect())

        # Owner-Window fuer Tool-Fenster (MainWindow oder QDialog)
        owner = parent.window()

        # Highlight-Rahmen als Tool-Fenster (bleibt bei Owner)
        self._highlight = _HighlightFrame(self._targets, skin_mgr, owner=owner)

        # Tooltip-Box als Tool-Fenster (bleibt bei Owner)
        self._tooltip = _TooltipPopup(
            step, skin_mgr,
            on_next, on_skip, on_back,
            step_num, total_steps, is_offer,
            owner=owner,
        )
        self._position_tooltip()

        # Keyboard-Shortcuts
        self._sc_next = QShortcut(QKeySequence(Qt.Key_Return), self)
        self._sc_next.activated.connect(on_next)
        self._sc_skip = QShortcut(QKeySequence(Qt.Key_Escape), self)
        self._sc_skip.activated.connect(on_skip)

        self.raise_()
        self.show()

    def _combined_global_rect(self) -> QRect:
        """Bounding-Box aller Targets in globalen Bildschirm-Koordinaten."""
        rects = []
        for t in self._targets:
            if t and t.isVisible():
                global_pos = t.mapToGlobal(QPoint(0, 0))
                rects.append(QRect(global_pos, t.size()))
        if not rects:
            return QRect(0, 0, 0, 0)
        united = rects[0]
        for r in rects[1:]:
            united = united.united(r)
        return united

    def _combined_parent_rect(self) -> QRect:
        """Bounding-Box aller Targets in Parent-Koordinaten."""
        rects = []
        parent = self.parentWidget()
        for t in self._targets:
            if t and t.isVisible():
                pos = t.mapTo(parent, QPoint(0, 0))
                rects.append(QRect(pos, t.size()))
        if not rects:
            return QRect(0, 0, 0, 0)
        united = rects[0]
        for r in rects[1:]:
            united = united.united(r)
        return united

    def _position_tooltip(self):
        """Positioniert Tooltip (globales Fenster) relativ zum Ziel."""
        target_global = self._combined_global_rect()
        self._tooltip.adjustSize()
        tooltip_size = self._tooltip.size()
        margin = self._MARGIN

        # Bildschirm-Rect fuer Rand-Clipping
        screen = QApplication.primaryScreen().availableGeometry()

        anchor = self._step.anchor
        if anchor == "auto":
            if target_global.bottom() + margin + tooltip_size.height() <= screen.bottom():
                anchor = "bottom"
            elif target_global.top() - margin - tooltip_size.height() >= screen.top():
                anchor = "top"
            elif target_global.right() + margin + tooltip_size.width() <= screen.right():
                anchor = "right"
            else:
                anchor = "left"

        if anchor == "bottom":
            x = target_global.center().x() - tooltip_size.width() // 2
            y = target_global.bottom() + margin
        elif anchor == "top":
            x = target_global.center().x() - tooltip_size.width() // 2
            y = target_global.top() - margin - tooltip_size.height()
        elif anchor == "right":
            x = target_global.right() + margin
            y = target_global.center().y() - tooltip_size.height() // 2
        else:  # left
            x = target_global.left() - margin - tooltip_size.width()
            y = target_global.center().y() - tooltip_size.height() // 2

        # Bildschirm-Rand-Clipping
        x = max(screen.x() + 8, min(x, screen.right() - tooltip_size.width() - 8))
        y = max(screen.y() + 8, min(y, screen.bottom() - tooltip_size.height() - 8))

        self._tooltip.move(int(x), int(y))
        self._tooltip.show()

    def paintEvent(self, event):
        """Nichts zeichnen — Overlay ist nur Klick-Faenger."""
        pass

    def resizeEvent(self, event):
        """Bei Fenster-Resize: Overlay + Positionen neu berechnen."""
        self.setGeometry(self.parentWidget().rect())
        self._position_tooltip()
        if self._highlight:
            self._highlight._reposition()

    def mousePressEvent(self, event):
        """Klick ausserhalb des Tooltips = Skip."""
        self._on_skip()

    def close(self):
        """Schliesst Overlay, Highlight-Rahmen und Tooltip-Popup."""
        if self._highlight:
            self._highlight.close()
            self._highlight = None
        if self._tooltip:
            self._tooltip.close()
            self._tooltip = None
        super().close()


class _TooltipPopup(QWidget):
    """Tooltip als Tool-Fenster — liegt ueber Docks, bleibt beim Parent."""

    def __init__(self, step, skin_mgr, on_next, on_skip, on_back,
                 step_num, total_steps, is_offer=False, owner=None):
        super().__init__(owner)
        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.Tool  # Bleibt bei Owner, kein Taskbar-Eintrag
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setFixedWidth(340)

        # Innere Box mit Inhalt
        self._box = _TooltipBox(
            self, step, skin_mgr,
            on_next, on_skip, on_back,
            step_num, total_steps, is_offer,
        )
        # Box fuellt das gesamte Popup
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._box)


# ---------------------------------------------------------------------------
# Tutorial-Engine (zentrale Steuerung)
# ---------------------------------------------------------------------------

class TutorialEngine:
    """Verwaltet Tutorial-Ablauf, Status und Overlay.

    Lebenszyklus:
      1. Registrierung der Widgets via register_widget()
      2. check_and_start() nach App-Start
      3. Offer → Start → Schritt fuer Schritt → Finish/Skip
      4. Automatisch naechstes Tutorial anbieten
    """

    def __init__(self, main_window, settings, skin_mgr):
        self._main = main_window
        self._settings = settings
        self._skin_mgr = skin_mgr
        self._overlay = None
        self._active_tutorial = None
        self._current_step = 0
        self._is_offer = False        # True wenn Offer-Overlay aktiv
        self._paused_for_session = False  # True = kein Tutorial mehr bis Neustart
        self._widget_map = {}         # widget_id → QWidget
        self._tutorials = []          # Wird von aussen gesetzt

    def set_tutorials(self, tutorials):
        """Setzt die Tutorial-Definitionen (aus tutorial_definitions.py)."""
        self._tutorials = tutorials

    # --- Registrierung ---
    def register_widget(self, widget_id, widget):
        """Registriert ein Widget fuer Element-Lookup."""
        self._widget_map[widget_id] = widget

    # --- Status ---
    def get_status(self, widget_id):
        """Liest Tutorial-Status aus INI."""
        return str(self._settings.value(
            f"Tutorials/{widget_id}", "not_started"
        ))

    def _set_status(self, widget_id, status):
        """Schreibt Tutorial-Status in INI."""
        self._settings.setValue(f"Tutorials/{widget_id}", status)

    def reset_all(self):
        """Setzt alle Tutorial-Status zurueck (inkl. Dialog-Tutorials)."""
        self._paused_for_session = False
        for tut in self._tutorials:
            self._settings.setValue(
                f"Tutorials/{tut.widget_id}", "not_started"
            )
        # Dialog-Tutorials und Sonder-Tutorials
        self._settings.setValue("Tutorials/location_dialog", "not_started")
        self._settings.setValue("Tutorials/beat_snap", "not_started")

    def complete_all(self):
        """Markiert alle Tutorials als abgeschlossen."""
        # Laufendes Tutorial beenden
        if self._active_tutorial:
            self._close_overlay()
            self._active_tutorial = None
        self._paused_for_session = False
        for tut in self._tutorials:
            self._settings.setValue(
                f"Tutorials/{tut.widget_id}", "completed"
            )
        # Dialog-Tutorials und Sonder-Tutorials
        self._settings.setValue("Tutorials/location_dialog", "completed")
        self._settings.setValue("Tutorials/beat_snap", "completed")

    def reset_one(self, widget_id):
        """Setzt ein einzelnes Tutorial zurueck."""
        self._paused_for_session = False
        self._settings.setValue(f"Tutorials/{widget_id}", "not_started")

    def start_specific(self, widget_id):
        """Startet ein bestimmtes Tutorial direkt (Menu-Auswahl hat Vorrang)."""
        # Laufendes Tutorial beenden
        if self._active_tutorial:
            self._close_overlay()
            self._active_tutorial = None
        self._paused_for_session = False
        self._settings.setValue(f"Tutorials/{widget_id}", "not_started")
        tut = next((t for t in self._tutorials if t.widget_id == widget_id), None)
        if tut:
            self._start_tutorial(tut)

    # --- Trigger ---
    def check_and_start(self):
        """Prueft ob ein Tutorial gestartet werden soll."""
        if self._active_tutorial:
            return
        if self._paused_for_session:
            return
        pending = [
            t for t in self._tutorials
            if self.get_status(t.widget_id) == "not_started"
        ]
        if not pending:
            self._restore_floating_docks()
            return
        pending.sort(key=lambda t: t.priority, reverse=True)
        self._offer_tutorial(pending[0])

    def _minimize_floating_docks(self, except_dock_name=""):
        """Versteckt alle losen (floating) Docks temporaer.

        Verhindert, dass ein loses Widget das Tutorial-Ziel verdeckt.
        Merkt sich die versteckten Docks fuer spaetere Wiederherstellung.
        """
        if not hasattr(self, '_hidden_docks'):
            self._hidden_docks = []
        for dock in self._main.findChildren(QDockWidget):
            if dock.objectName() == except_dock_name:
                continue
            if dock.isFloating() and dock.isVisible():
                dock.hide()
                self._hidden_docks.append(dock.objectName())

    def _restore_floating_docks(self):
        """Stellt temporaer versteckte Docks wieder her."""
        if not hasattr(self, '_hidden_docks'):
            return
        for name in self._hidden_docks:
            dock = self._main.findChild(QDockWidget, name)
            if dock is not None:
                dock.show()
        self._hidden_docks = []

    def _ensure_dock_visible(self, dock_name):
        """Blendet ein Dock-Widget ein und bringt es in den Vordergrund."""
        # Zuerst alle losen Docks in den Hintergrund
        self._minimize_floating_docks(except_dock_name=dock_name)
        dock = self._main.findChild(QDockWidget, dock_name)
        if dock is not None:
            dock.show()
            dock.raise_()

    # --- Tutorial-Ablauf ---
    def _offer_tutorial(self, tut):
        """Zeigt Angebot: 'Tour durch [Widget] starten?'"""
        if tut.auto_show:
            self._ensure_dock_visible(tut.dock_name)

        self._active_tutorial = tut
        self._current_step = 0
        self._is_offer = True

        targets = self._resolve_targets(tut.steps[0].element_path)
        if not targets:
            target_widget = self._widget_map.get(tut.widget_id)
            targets = [target_widget] if target_widget else []
        if not targets:
            self._finish_tutorial("skipped")
            return

        offer_step = TutorialStep(
            element_path=tut.steps[0].element_path,
            title_key="tutorial.offer_title",
            text_key=tut.offer_text_key,
            anchor="bottom",
        )
        self._close_overlay()
        self._overlay = TutorialOverlay(
            self._main, targets, offer_step, self._skin_mgr,
            on_next=self._on_offer_accept,
            on_skip=self._on_offer_decline,
            on_back=lambda: None,
            step_num=0,
            total_steps=len(tut.steps),
            is_offer=True,
        )

    def _on_offer_accept(self):
        """User akzeptiert die Tour."""
        self._is_offer = False
        self._current_step = 0
        self._show_step()

    def _on_offer_decline(self):
        """User lehnt ab — keine Tutorials mehr fuer heute."""
        self._finish_tutorial("not_started")
        self._paused_for_session = True

    def _start_tutorial(self, tut):
        """Startet ein Tutorial direkt (ohne Offer, z.B. bei manuellem Reset)."""
        if tut.auto_show:
            self._ensure_dock_visible(tut.dock_name)
        self._active_tutorial = tut
        self._current_step = 0
        self._is_offer = False
        self._show_step()

    def _show_step(self):
        """Zeigt den aktuellen Schritt."""
        if self._active_tutorial is None:
            return
        step = self._active_tutorial.steps[self._current_step]

        # Lose Docks aus dem Weg raeumen (ausser dem aktuellen)
        self._minimize_floating_docks(
            except_dock_name=self._active_tutorial.dock_name
        )

        if step.action:
            self._execute_action(step.action)

        targets = self._resolve_targets(step.element_path)
        if not targets or not any(t.isVisible() for t in targets):
            self._next_step()
            return

        self._close_overlay()
        self._overlay = TutorialOverlay(
            self._main, targets, step, self._skin_mgr,
            on_next=self._next_step,
            on_skip=self._skip_tutorial,
            on_back=self._prev_step,
            step_num=self._current_step + 1,
            total_steps=len(self._active_tutorial.steps),
        )

    def _next_step(self):
        """Naechster Schritt oder Tutorial beenden."""
        self._current_step += 1
        if self._current_step >= len(self._active_tutorial.steps):
            self._finish_tutorial("completed")
        else:
            self._show_step()

    def _prev_step(self):
        """Vorheriger Schritt."""
        if self._current_step > 0:
            self._current_step -= 1
            self._show_step()

    def _skip_tutorial(self):
        """Tutorial ueberspringen — keine Tutorials mehr fuer heute."""
        self._finish_tutorial("skipped")
        self._paused_for_session = True

    def _finish_tutorial(self, status):
        """Tutorial beenden und naechstes pruefen."""
        finished_id = None
        if self._active_tutorial:
            finished_id = self._active_tutorial.widget_id
            self._set_status(self._active_tutorial.widget_id, status)
        self._close_overlay()
        self._active_tutorial = None
        self._current_step = 0
        self._is_offer = False

        # Bei completed: Pause aufheben, naechstes Tutorial anbieten
        if status == "completed":
            self._paused_for_session = False

        # Spezialfall: Nach Player-Tutorial → LocationDialog oeffnen
        if finished_id == "player" and status == "completed":
            if self.get_status("location_dialog") == "not_started":
                QTimer.singleShot(300, self._open_location_with_tutorial)
                return

        # Spezialfall: Nach Loop-Tutorial → BeatSnap-Dialog oeffnen
        if finished_id == "loop" and status == "completed":
            if self.get_status("beat_snap") == "not_started":
                QTimer.singleShot(300, self._open_beat_snap_with_tutorial)
                return

        # Naechstes Tutorial nach kurzem Delay (nur wenn nicht pausiert)
        if not self._paused_for_session:
            QTimer.singleShot(500, self.check_and_start)
        else:
            # Keine weiteren Tutorials — versteckte Docks wiederherstellen
            self._restore_floating_docks()

    def _open_location_with_tutorial(self):
        """Oeffnet den LocationDialog und startet dort das Tutorial."""
        if hasattr(self._main, '_on_location_button_clicked'):
            self._main._on_location_button_clicked()

    def _open_beat_snap_with_tutorial(self):
        """Oeffnet den BeatSnap-Dialog fuer das Tutorial."""
        loop_widget = getattr(self._main, 'loop_widget', None)
        if loop_widget and hasattr(loop_widget, '_on_beat_snap'):
            # Temporaer btn_snap aktivieren falls noetig (Tutorial-Modus)
            was_enabled = loop_widget.btn_snap.isEnabled()
            if not was_enabled:
                loop_widget.btn_snap.setEnabled(True)
            loop_widget._on_beat_snap()
            if not was_enabled:
                loop_widget.btn_snap.setEnabled(False)

    def _close_overlay(self):
        """Schliesst das aktuelle Overlay."""
        if self._overlay:
            self._overlay.close()
            self._overlay.deleteLater()
            self._overlay = None

    # --- Schritt-Aktionen ---
    def _execute_action(self, action):
        """Fuehrt eine optionale Aktion vor einem Schritt aus."""
        if action.startswith("show_dock:"):
            dock_name = action.split(":", 1)[1]
            self._ensure_dock_visible(dock_name)

    # --- Element-Aufloesung ---
    def _resolve_targets(self, element_path):
        """Loest Element-Pfad auf. Unterstuetzt '+' fuer Multi-Highlight.

        Beispiel: "song_data.spin_bpm+song_data.btn_auto_bpm"
        Gibt Liste von QWidget-Instanzen zurueck.
        """
        paths = element_path.split("+")
        targets = []
        for path in paths:
            path = path.strip()
            if path == "_menu_bar":
                targets.append(self._main.menuBar())
                continue
            # Dock-Titelleisten: _dock_XXX_title → Titelbar-Widget des Docks
            if path.startswith("_dock_") and path.endswith("_title"):
                dock_name = "dock_" + path[6:-6]  # _dock_player_title → dock_player
                dock = self._main.findChild(QDockWidget, dock_name)
                if dock:
                    # QDockWidget hat kein offizielles titleBar-Widget,
                    # aber wir koennen das Dock selbst als Target nehmen
                    # und auf die oberen 30px beschraenken (Titelleiste)
                    targets.append(dock)
                continue
            widget = self._resolve_single(path)
            if widget:
                targets.append(widget)
        return targets

    def _resolve_single(self, element_path):
        """Loest einen einzelnen 'widget_id.attr.sub_attr' Pfad auf."""
        parts = element_path.split(".")
        widget_id = parts[0]
        widget = self._widget_map.get(widget_id)
        if widget is None:
            return None
        obj = widget
        for attr in parts[1:]:
            obj = getattr(obj, attr, None)
            if obj is None:
                return None
        if isinstance(obj, QWidget):
            return obj
        return None

    # --- Skin-Wechsel ---
    def refresh_overlay(self):
        """Overlay mit neuen Skin-Farben neu zeichnen."""
        if self._overlay and self._active_tutorial:
            if self._is_offer:
                self._offer_tutorial(self._active_tutorial)
            else:
                self._show_step()

    # --- Dialog-Tutorials ---
    def show_dialog_tutorial(self, dialog, tutorial_id, steps):
        """Zeigt ein Tutorial innerhalb eines QDialogs."""
        status = self.get_status(tutorial_id)
        if status != "not_started":
            return
        if self._paused_for_session:
            return

        self._dialog_tutorial = _DialogTutorial(
            dialog, tutorial_id, steps,
            self._skin_mgr, self._settings, self,
        )
        self._dialog_tutorial.start()


class _DialogTutorial:
    """Leichtgewichtiges Tutorial fuer QDialogs (nicht Dock-basiert)."""

    def __init__(self, dialog, tutorial_id, steps, skin_mgr, settings, engine):
        self._dialog = dialog
        self._tutorial_id = tutorial_id
        self._steps = steps
        self._skin_mgr = skin_mgr
        self._settings = settings
        self._engine = engine  # Referenz fuer Chaining
        self._current = 0
        self._overlay = None

    def start(self):
        self._show_step()

    def _show_step(self):
        if self._current >= len(self._steps):
            self._finish("completed")
            return

        step = self._steps[self._current]
        targets = self._resolve_targets(step.element_path)
        if not targets or not any(t.isVisible() for t in targets):
            self._current += 1
            self._show_step()
            return

        self._close()
        self._overlay = TutorialOverlay(
            self._dialog, targets, step, self._skin_mgr,
            on_next=self._next,
            on_skip=self._skip,
            on_back=self._prev,
            step_num=self._current + 1,
            total_steps=len(self._steps),
        )

    def _next(self):
        self._current += 1
        self._show_step()

    def _prev(self):
        if self._current > 0:
            self._current -= 1
            self._show_step()

    def _skip(self):
        self._finish("skipped")
        self._engine._paused_for_session = True

    def _finish(self, status):
        self._settings.setValue(f"Tutorials/{self._tutorial_id}", status)
        self._close()
        # Dialog schliessen damit er nicht im Weg ist
        if self._dialog and self._dialog.isVisible():
            self._dialog.reject()
        # Chaining: Nach Dialog-Tutorial naechstes Dock-Tutorial starten
        if status == "completed":
            self._engine._paused_for_session = False
            QTimer.singleShot(500, self._engine.check_and_start)

    def _close(self):
        if self._overlay:
            self._overlay.close()
            self._overlay.deleteLater()
            self._overlay = None

    def _resolve_targets(self, element_path):
        """Loest Attribut-Pfad relativ zum Dialog auf. Unterstuetzt '+'."""
        paths = element_path.split("+")
        targets = []
        for path in paths:
            path = path.strip()
            parts = path.split(".")
            obj = self._dialog
            for attr in parts:
                obj = getattr(obj, attr, None)
                if obj is None:
                    break
            if isinstance(obj, QWidget):
                targets.append(obj)
        return targets
