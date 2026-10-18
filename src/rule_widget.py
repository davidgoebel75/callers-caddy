"""
Rules-Widget fuer Callers Caddy — Regelverwaltung.

Zweispaltig: Links Regelliste (mit Suche + Drag&Drop), rechts Editor.
"""

import json
import os

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QPushButton, QLineEdit, QComboBox, QLabel, QCheckBox, QGroupBox,
    QScrollArea, QSplitter, QAbstractItemView, QHeaderView, QMessageBox,
    QSizePolicy, QSpinBox, QDoubleSpinBox, QFileDialog, QDialog,
    QFormLayout, QListWidget, QListWidgetItem,
)
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QColor, QIcon, QPixmap, QPainter

from i18n import _t
from rule_engine import Rule, ConditionDef, ActionDef
from wheel_guard import install_wheel_guard


# Menschenlesbare Labels fuer Action-/Condition-Parameter (englisch — wie alle
# Rules-Namen, i18n-Konvention). Fehlt ein Name hier, wird der param_name
# huebsch aufbereitet (snake_case -> "Snake Case"). Ein Schema kann per
# {"label": "..."} auch selbst ein Label vorgeben (hat Vorrang).
PARAM_LABELS = {
    "dock_name":    "Widget",
    "open_position": "Open position",
    "dock_left":    "Left widget",
    "dock_right":   "Right widget",
    "width_pct":    "Width %",
    "height_pct":   "Height %",
    "x_pct":        "X position %",
    "y_pct":        "Y position %",
    "split":        "Split",
    "layout_name":  "Layout",
    "genre_name":   "Genre",
    "seq_type":     "Sequence type",
    "type":         "Type",
    "sort":         "Sort",
    "minutes":      "Minutes",
    "delta":        "Delta",
    "volume":       "Volume",
    "level":        "Level",
    "message":      "Message",
    "path":         "File",
    "position":     "Position",
    "offset":       "Offset (mm:ss.cs)",
    "preset":       "Preset",
    "duration_ms":  "Duration (ms)",
    "call":         "Call",
    "difficulty":   "Difficulty",
    "tag":          "Tag",
    "state":        "State",
    "program_ids":  "Programs",
}


def _param_label(param_name: str, schema: dict) -> str:
    """Liefert das Anzeige-Label fuer einen Parameter."""
    if schema.get("label"):
        return schema["label"]
    if param_name in PARAM_LABELS:
        return PARAM_LABELS[param_name]
    return param_name.replace("_", " ").capitalize()


def _populate_action_combo(combo: QComboBox, actions: dict):
    """Befuellt ein QComboBox mit Aktionen, gruppiert durch nicht-waehlbare Header."""
    seen_groups = []
    ungrouped = []
    grouped = {}
    for a_str, a_info in actions.items():
        g = getattr(a_info, "group", "") or ""
        if g:
            grouped.setdefault(g, []).append((a_str, a_info))
            if g not in seen_groups:
                seen_groups.append(g)
        else:
            ungrouped.append((a_str, a_info))

    def _add_header(text):
        combo.addItem(f"── {text} ──", None)
        idx = combo.count() - 1
        item = combo.model().item(idx)
        item.setFlags(item.flags() & ~Qt.ItemIsEnabled & ~Qt.ItemIsSelectable)
        item.setData(QColor("#888888"), Qt.ForegroundRole)

    for group in seen_groups:
        _add_header(group)
        for a_str, a_info in grouped[group]:
            combo.addItem(f"  {a_info.display_name}", a_str)

    if ungrouped:
        if seen_groups:
            _add_header("Other")
        for a_str, a_info in ungrouped:
            combo.addItem(a_info.display_name, a_str)


# ===========================================================================
# Tasten-Trigger Dialog
# ===========================================================================

class KeyPressCaptureDialog(QDialog):
    """Dialog zum Erfassen einer Taste und Konvertierung zu Trigger-Name.

    WICHTIG: ESC, ENTER und SPACE werden als Tasten-Trigger erfasst,
    nicht als Dialog-Aktionen. Abbrechen nur per Maus-Klick.
    """

    # Mapping: Qt Key Code → (trigger_name, display_name)
    # Multimedia-Tasten: Qt empfängt sie nur wenn das OS sie nicht abfängt.
    # Auf manchen Laptops/Treibern werden sie systemweit verarbeitet und erreichen Qt nicht.
    _SPECIAL_KEY_MAP = {
        Qt.Key_Space:      ("key_space",      "Space"),
        Qt.Key_Return:     ("key_return",     "Return"),
        Qt.Key_Enter:      ("key_return",     "Return"),
        Qt.Key_Delete:     ("key_delete",     "Delete"),
        Qt.Key_Tab:        ("key_tab",        "Tab"),
        Qt.Key_Escape:     ("key_escape",     "Escape"),
        Qt.Key_Insert:     ("key_insert",     "Insert"),
        Qt.Key_Backspace:  ("key_backspace",  "Backspace"),
        Qt.Key_Home:       ("key_home",       "Home"),
        Qt.Key_End:        ("key_end",        "End"),
        Qt.Key_PageUp:     ("key_pageup",     "Page Up"),
        Qt.Key_PageDown:   ("key_pagedown",   "Page Down"),
        Qt.Key_Left:       ("key_left",       "← Links"),
        Qt.Key_Right:      ("key_right",      "→ Rechts"),
        Qt.Key_Up:         ("key_up",         "↑ Hoch"),
        Qt.Key_Down:       ("key_down",       "↓ Runter"),
        # Multimedia-Tasten (werden vom OS abgefangen, falls Treiber sie systemweit verwaltet)
        Qt.Key_VolumeUp:        ("key_volume_up",    "Lauter"),
        Qt.Key_VolumeDown:      ("key_volume_down",  "Leiser"),
        Qt.Key_VolumeMute:      ("key_volume_mute",  "Stumm"),
        Qt.Key_MediaPlay:       ("key_media_play",   "Media Play"),
        Qt.Key_MediaStop:       ("key_media_stop",   "Media Stop"),
        Qt.Key_MediaNext:       ("key_media_next",   "Media Nächster"),
        Qt.Key_MediaPrevious:   ("key_media_prev",   "Media Vorheriger"),
        Qt.Key_MonBrightnessUp:   ("key_brightness_up",   "Heller"),
        Qt.Key_MonBrightnessDown: ("key_brightness_down", "Dunkler"),
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(_t("rule.key_capture_title"))
        self.setMinimumSize(420, 180)
        self.setModal(True)
        self.captured_trigger: str | None = None
        self.captured_key_display: str | None = None
        self._build_ui()
        self.setFocusPolicy(Qt.StrongFocus)
        self.setFocus()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        info = QLabel(_t("rule.key_capture_info"))
        info.setWordWrap(True)
        layout.addWidget(info)

        self._label_captured = QLabel(_t("rule.key_capture_waiting"))
        self._label_captured.setAlignment(Qt.AlignCenter)
        self._label_captured.setWordWrap(True)
        self._label_captured.setStyleSheet("font-size: 14px; font-weight: bold;")
        self._label_captured.setMinimumHeight(50)
        layout.addWidget(self._label_captured)

        layout.addStretch()

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self._btn_ok = QPushButton("OK")
        self._btn_ok.setEnabled(False)
        self._btn_ok.setDefault(False)
        self._btn_ok.setAutoDefault(False)
        self._btn_ok.setFocusPolicy(Qt.NoFocus)
        self._btn_ok.clicked.connect(self.accept)
        btn_layout.addWidget(self._btn_ok)

        self._btn_cancel = QPushButton(_t("btn_cancel"))
        self._btn_cancel.setDefault(False)
        self._btn_cancel.setAutoDefault(False)
        self._btn_cancel.setFocusPolicy(Qt.NoFocus)
        self._btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(self._btn_cancel)

        layout.addLayout(btn_layout)

    def keyPressEvent(self, event):
        """Erfasst die gedrückte Taste — ALLE Keys, inkl. ESC/ENTER/SPACE."""
        if event.isAutoRepeat():
            return

        self.captured_trigger = self._key_to_trigger(event)
        self.captured_key_display = self._key_to_display(event)

        if self.captured_trigger:
            self._label_captured.setText(
                _t("rule.key_capture_result")
                .replace("{key}", self.captured_key_display)
                .replace("{trigger}", self.captured_trigger)
            )
            self._btn_ok.setEnabled(True)
        else:
            self._label_captured.setText(_t("rule.key_capture_unknown"))
            self.captured_trigger = None
            self._btn_ok.setEnabled(False)

        event.accept()  # Verhindert Qt-Default-Verhalten (ESC=reject, ENTER=click)

    def reject(self):
        """Nur per Maus-Klick auf Abbrechen — nicht per ESC."""
        self.captured_trigger = None
        super().reject()

    def _key_to_trigger(self, event) -> str | None:
        """Konvertiert QKeyEvent zu Trigger-Name."""
        key_code = event.key()

        # A-Z
        if 65 <= key_code <= 90:
            return f"key_{chr(key_code).lower()}"

        # 0-9
        if 48 <= key_code <= 57:
            return f"key_{chr(key_code)}"

        # F1-F24
        if Qt.Key_F1 <= key_code <= Qt.Key_F24:
            fn = key_code - Qt.Key_F1 + 1
            return f"key_f{fn}"

        # Alle anderen bekannten Tasten (inkl. Multimedia)
        entry = self._SPECIAL_KEY_MAP.get(key_code)
        return entry[0] if entry else None

    def _key_to_display(self, event) -> str:
        """Konvertiert QKeyEvent zu benutzerfreundlichem Display-Namen."""
        key_code = event.key()

        if 65 <= key_code <= 90:
            return chr(key_code)
        if 48 <= key_code <= 57:
            return chr(key_code)
        if Qt.Key_F1 <= key_code <= Qt.Key_F24:
            return f"F{key_code - Qt.Key_F1 + 1}"

        entry = self._SPECIAL_KEY_MAP.get(key_code)
        return entry[1] if entry else f"Key({key_code})"


class _ActionDragHandle(QLabel):
    """Drag-Handle (≡) zum Verschieben von Action-Zeilen per Maus."""

    def __init__(self, rules_widget, row_widget, parent=None):
        super().__init__("≡", parent)
        self._rw = rules_widget
        self._row = row_widget
        self._dragging = False
        self.setCursor(Qt.SizeVerCursor)
        self.setFixedWidth(18)
        self.setAlignment(Qt.AlignCenter)
        self.setToolTip("Drag to reorder")
        self.setStyleSheet("color: #888; font-size: 14px;")

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._dragging = True

    def mouseMoveEvent(self, event):
        if self._dragging:
            self._rw._on_action_drag(self._row,
                                     event.globalPosition().toPoint().y())

    def mouseReleaseEvent(self, event):
        self._dragging = False


class RulesWidget(QWidget):
    """Dock-Widget zur Verwaltung von Rules."""

    def __init__(self, rule_engine, dock_names_provider=None,
                 genre_names_provider=None, preset_names_provider=None,
                 layout_names_provider=None, seqtype_names_provider=None,
                 difficulty_names_provider=None, tags_names_provider=None,
                 call_names_provider=None, program_choices_provider=None,
                 skin_mgr=None,
                 parent=None):
        super().__init__(parent)
        self._engine = rule_engine
        self._dock_names_provider = dock_names_provider      # callable -> dict
        self._genre_names_provider = genre_names_provider    # callable -> [(id, name)]
        self._preset_names_provider = preset_names_provider  # callable -> [str]
        self._layout_names_provider = layout_names_provider  # callable -> [str]
        self._seqtype_names_provider = seqtype_names_provider  # callable -> [str]  (BL-181)
        # BL-192..197: Provider fuer die neuen Sequence-Filter-/Programm-Aktionen
        self._difficulty_names_provider = difficulty_names_provider  # -> [str]
        self._tags_names_provider = tags_names_provider             # -> [str]
        self._call_names_provider = call_names_provider             # -> [str]
        self._program_choices_provider = program_choices_provider   # -> [(id, label)]
        self._skin_mgr = skin_mgr                            # fuer Stream-Deck-Icons
        self._current_rule = None    # Aktuell selektierte Rule
        self._updating = False       # Guard gegen Endlosschleifen
        self._build_ui()
        self._refresh_list()

        # Callback: Engine benachrichtigt bei externen Aenderungen
        self._engine.on_rules_changed = self._refresh_list

    # Style fuer Mini-Buttons (×, +) damit sie in jedem Theme sichtbar sind
    _MINI_BTN_STYLE = (
        "QPushButton { font-size: 14px; font-weight: bold; "
        "padding: 0px 4px; min-width: 24px; max-width: 28px; }"
    )

    def _build_ui(self):
        self.setMinimumSize(700, 400)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        splitter = QSplitter(Qt.Horizontal)
        layout.addWidget(splitter)

        # --- Linke Seite: Regelliste ---
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)

        # Suchfeld
        self._search = QLineEdit()
        self._search.setPlaceholderText(_t("rule.search_placeholder"))
        self._search.textChanged.connect(self._apply_filter)
        left_layout.addWidget(self._search)

        # Tabelle
        self._table = QTableWidget()
        self._table.setColumnCount(4)
        self._table.setHorizontalHeaderLabels(["", "Name", "Trigger", "Source"])
        self._table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(
            3, QHeaderView.ResizeToContents)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.itemChanged.connect(self._on_table_item_changed)
        self._table.itemSelectionChanged.connect(self._on_selection_changed)

        # Kein Built-in DnD (zerstoert Zeilenstruktur) — Up/Down Buttons stattdessen
        self._table.setDragDropMode(QAbstractItemView.NoDragDrop)
        self._table.setDragEnabled(False)
        self._table.setAcceptDrops(False)

        left_layout.addWidget(self._table)

        # Buttons
        btn_row = QHBoxLayout()
        self._btn_add = QPushButton(_t("rule.btn_add"))
        self._btn_add.clicked.connect(self._on_add_rule)
        btn_row.addWidget(self._btn_add)

        self._btn_duplicate = QPushButton(
            _t("rule.btn_duplicate"))
        self._btn_duplicate.setEnabled(False)
        self._btn_duplicate.clicked.connect(self._on_duplicate_rule)
        btn_row.addWidget(self._btn_duplicate)

        self._btn_delete = QPushButton(
            _t("rule.btn_delete"))
        self._btn_delete.setEnabled(False)
        self._btn_delete.clicked.connect(self._on_delete_rule)
        btn_row.addWidget(self._btn_delete)

        btn_row.addStretch()

        # Export / Import
        self._btn_export = QPushButton(_t("rule.btn_export"))
        self._btn_export.clicked.connect(self._on_export_rules)
        btn_row.addWidget(self._btn_export)

        self._btn_import = QPushButton(_t("rule.btn_import"))
        self._btn_import.clicked.connect(self._on_import_rules)
        btn_row.addWidget(self._btn_import)

        btn_row.addStretch()

        # Up/Down fuer User-Rule-Reihenfolge
        self._btn_up = QPushButton("▲")
        self._btn_up.setFixedSize(32, 32)
        self._btn_up.setStyleSheet("font-size: 16px; padding: 0px;")
        self._btn_up.setToolTip("Move Up")
        self._btn_up.setEnabled(False)
        self._btn_up.clicked.connect(self._on_move_up)
        btn_row.addWidget(self._btn_up)

        self._btn_down = QPushButton("▼")
        self._btn_down.setFixedSize(32, 32)
        self._btn_down.setStyleSheet("font-size: 16px; padding: 0px;")
        self._btn_down.setToolTip("Move Down")
        self._btn_down.setEnabled(False)
        self._btn_down.clicked.connect(self._on_move_down)
        btn_row.addWidget(self._btn_down)
        left_layout.addLayout(btn_row)

        splitter.addWidget(left)

        # --- Rechte Seite: Editor ---
        right_scroll = QScrollArea()
        right_scroll.setWidgetResizable(True)
        right_scroll.setFrameShape(QScrollArea.NoFrame)
        right_scroll.viewport().setAutoFillBackground(False)
        right_scroll.setStyleSheet("QScrollArea { background: transparent; }"
                                   "QScrollArea > QWidget > QWidget { background: transparent; }")

        self._editor = QWidget()
        self._editor_layout = QVBoxLayout(self._editor)
        self._editor_layout.setContentsMargins(4, 4, 4, 4)

        # Name
        name_row = QHBoxLayout()
        name_row.addWidget(QLabel("Name:"))
        self._edit_name = QLineEdit()
        self._edit_name.textChanged.connect(self._on_editor_changed)
        name_row.addWidget(self._edit_name)
        self._editor_layout.addLayout(name_row)

        # Active
        self._chk_active = QCheckBox(
            _t("rule.col_active"))
        self._chk_active.stateChanged.connect(self._on_active_changed)
        self._editor_layout.addWidget(self._chk_active)

        # Once per Song
        self._chk_once = QCheckBox("Once per Song")
        self._chk_once.setToolTip(
            "Fire this rule only once per song (reset on new play)")
        self._chk_once.stateChanged.connect(self._on_editor_changed)
        self._editor_layout.addWidget(self._chk_once)

        # Trigger
        trigger_row = QHBoxLayout()
        trigger_row.addWidget(QLabel("Trigger:"))
        self._combo_trigger = QComboBox()
        self._combo_trigger.currentIndexChanged.connect(
            self._on_editor_changed)
        trigger_row.addWidget(self._combo_trigger)

        # Button: Neuen Tasten-Trigger erstellen
        self._btn_create_key_trigger = QPushButton(_t("rule.btn_create_key_trigger"))
        self._btn_create_key_trigger.setToolTip(_t("rule.btn_create_key_trigger_tooltip"))
        self._btn_create_key_trigger.setMaximumWidth(80)
        self._btn_create_key_trigger.clicked.connect(self._on_create_key_trigger)
        trigger_row.addWidget(self._btn_create_key_trigger)

        trigger_row.addStretch()
        self._editor_layout.addLayout(trigger_row)

        # Conditions
        self._cond_group = QGroupBox(
            _t("rule.label_conditions"))
        self._cond_layout = QVBoxLayout(self._cond_group)
        self._btn_add_cond_group = QPushButton(
            _t("rule.btn_add_or_group"))
        self._btn_add_cond_group.clicked.connect(self._on_add_or_group)
        self._cond_layout.addWidget(self._btn_add_cond_group)
        self._editor_layout.addWidget(self._cond_group)

        # Actions
        self._action_group = QGroupBox(
            _t("rule.label_actions"))
        self._action_layout = QVBoxLayout(self._action_group)
        self._btn_add_action = QPushButton(
            _t("rule.btn_add_action"))
        self._btn_add_action.clicked.connect(self._on_add_action)
        self._action_layout.addWidget(self._btn_add_action)
        self._editor_layout.addWidget(self._action_group)

        # Stream Deck (BL-168) — auch fuer System-Rules editierbar
        self._build_stream_deck_group()

        # Save Button
        self._btn_save = QPushButton(_t("rule.btn_save"))
        self._btn_save.setEnabled(False)
        self._btn_save.clicked.connect(self._on_save_rule)
        self._editor_layout.addWidget(self._btn_save)

        self._editor_layout.addStretch()
        right_scroll.setWidget(self._editor)
        splitter.addWidget(right_scroll)

        # Splitter-Verhaeltnis 40:60
        splitter.setSizes([400, 600])

        # Editor initial deaktiviert
        self._set_editor_enabled(False)

        # Trigger-ComboBox befuellen
        self._populate_trigger_combo()

    # --- Stream Deck (BL-168) ---

    def _build_stream_deck_group(self):
        """Sektion 'Stream Deck' im Editor: Buttonnummer, Icon (mit Vorschau),
        Tooltip. Bewusst auch fuer System-Rules editierbar (Presentation, nicht
        Logik) — persistiert sofort ueber die Engine.
        """
        self._deck_group = QGroupBox("Stream Deck")
        deck_layout = QVBoxLayout(self._deck_group)

        # Buttonnummer
        num_row = QHBoxLayout()
        num_row.addWidget(QLabel(_t("streamdeck.button_number") + ":"))
        self._spin_button_number = QSpinBox()
        self._spin_button_number.setRange(0, 999)
        self._spin_button_number.setToolTip(_t("streamdeck.button_number_tooltip"))
        self._spin_button_number.valueChanged.connect(self._on_deck_changed)
        num_row.addWidget(self._spin_button_number)
        num_row.addStretch()
        deck_layout.addLayout(num_row)

        # Icon-Auswahl + Vorschau
        icon_row = QHBoxLayout()
        icon_row.addWidget(QLabel(_t("streamdeck.button_icon") + ":"))
        self._combo_button_icon = QComboBox()
        self._combo_button_icon.setIconSize(QSize(20, 20))
        self._populate_icon_combo()
        self._combo_button_icon.currentIndexChanged.connect(self._on_deck_changed)
        self._combo_button_icon.currentIndexChanged.connect(self._update_icon_preview)
        icon_row.addWidget(self._combo_button_icon, 1)

        self._icon_preview = QLabel()
        self._icon_preview.setFixedSize(40, 40)
        self._icon_preview.setAlignment(Qt.AlignCenter)
        self._icon_preview.setToolTip(_t("streamdeck.icon_preview"))
        icon_row.addWidget(self._icon_preview)
        deck_layout.addLayout(icon_row)

        # Tooltip-Text
        tip_row = QHBoxLayout()
        tip_row.addWidget(QLabel(_t("streamdeck.button_tooltip") + ":"))
        self._edit_button_tooltip = QLineEdit()
        self._edit_button_tooltip.setPlaceholderText(
            _t("streamdeck.button_tooltip_placeholder"))
        # Sofort-Persistenz erst bei Fokusverlust/Enter (nicht pro Tastendruck)
        self._edit_button_tooltip.editingFinished.connect(self._on_deck_changed)
        tip_row.addWidget(self._edit_button_tooltip)
        deck_layout.addLayout(tip_row)

        self._editor_layout.addWidget(self._deck_group)

    def _deck_chip_pixmap(self, svg_name: str, px: int) -> QPixmap:
        """Rendert ein Icon so, wie es auf dem Deck-Button aussieht: auf einer
        button_bg-farbigen Kachel. So sind die (in Win11 weissen) Icons auch in
        der hellen Editor-Vorschau/Dropdown sichtbar (WYSIWYG).
        """
        pm = QPixmap(px, px)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        bg = QColor(self._skin_mgr.color("button_bg", "#615f8b")
                    ) if self._skin_mgr else QColor("#615f8b")
        p.setPen(Qt.NoPen)
        p.setBrush(bg)
        r = px * 0.2
        p.drawRoundedRect(0, 0, px, px, r, r)
        if svg_name and self._skin_mgr:
            path = os.path.join(self._skin_mgr.icon_dir, svg_name)
            if os.path.isfile(path):
                ip = int(px * 0.62)
                off = (px - ip) // 2
                p.drawPixmap(off, off, QIcon(path).pixmap(ip, ip))
        p.end()
        return pm

    def _populate_icon_combo(self):
        """Befuellt das Icon-Dropdown mit den verfuegbaren SVGs (mit Vorschau)."""
        self._combo_button_icon.clear()
        self._combo_button_icon.addItem(_t("streamdeck.no_icon"), "")
        if not self._skin_mgr:
            return
        for name in self._skin_mgr.image_names():
            self._combo_button_icon.addItem(
                QIcon(self._deck_chip_pixmap(name, 20)), name, name)

    def _update_icon_preview(self):
        """Zeigt das aktuell gewaehlte Icon gross in der Vorschau (als Deck-Kachel)."""
        name = self._combo_button_icon.currentData() or ""
        if name:
            self._icon_preview.setPixmap(self._deck_chip_pixmap(name, 36))
        else:
            self._icon_preview.clear()

    def _on_deck_changed(self, *args):
        """Reagiert auf Aenderungen der Stream-Deck-Felder.

        User-Rules: Die Deck-Felder sind normale Editor-Felder. Sie werden NICHT
        sofort persistiert — sonst wuerde das Betreten des Deck-Bereichs mitten
        im Bearbeiten die ganze Rule speichern und neu laden, was den Save-Button
        ausgraut (wirkt wie „kann nicht speichern"). Stattdessen nur als Aenderung
        markieren; _on_save_rule schreibt Deck-Parameter gemeinsam mit dem Rest.

        System-Rules haben keinen Save-Flow (Editor schreibgeschuetzt) und muessen
        daher weiterhin sofort persistiert werden, damit man sie aufs Deck pinnen
        kann.
        """
        if self._updating or not self._current_rule:
            return
        if self._current_rule.source == "user":
            self._on_editor_changed()
            return
        rid = self._current_rule.id
        number = self._spin_button_number.value()
        icon = self._combo_button_icon.currentData() or ""
        tooltip = self._edit_button_tooltip.text().strip()
        self._engine.set_stream_deck_params(rid, number, icon, tooltip)
        # Nach dem ausgeloesten Refresh die Rule wieder selektieren
        self._select_rule_by_id(rid)

    def _load_stream_deck_into_editor(self, rule):
        """Laedt die Stream-Deck-Felder einer Rule in den Editor."""
        self._spin_button_number.setValue(rule.button_number or 0)
        idx = self._combo_button_icon.findData(rule.button_icon or "")
        self._combo_button_icon.setCurrentIndex(idx if idx >= 0 else 0)
        self._edit_button_tooltip.setText(rule.button_tooltip or "")
        self._edit_button_tooltip.setPlaceholderText(
            rule.name or _t("streamdeck.button_tooltip_placeholder"))
        self._update_icon_preview()

    # --- Trigger-ComboBox ---

    def _populate_trigger_combo(self):
        self._combo_trigger.clear()
        for t_str, t_info in self._engine.registry.triggers.items():
            self._combo_trigger.addItem(t_info.display_name, t_str)

    def _on_create_key_trigger(self):
        """Handler für Button '+ Taste': Öffnet Dialog zum Erfassen einer Taste."""
        dlg = KeyPressCaptureDialog(self)
        if dlg.exec() != QDialog.Accepted:
            return  # User hat Abbrechen geklickt

        trigger_name = dlg.captured_trigger
        if not trigger_name:
            return

        # Prüfen, ob Trigger schon existiert
        if trigger_name in self._engine.registry.triggers:
            QMessageBox.information(
                self,
                _t("rule.key_trigger_exists_title"),
                _t("rule.key_trigger_exists").replace("{trigger}", trigger_name)
            )
            return

        # Neuen Trigger registrieren
        display_name = f"Key {dlg.captured_key_display}"
        self._engine.registry.add_trigger(trigger_name, display_name)

        # Trigger-Dropdown neu laden und neu erstellten Trigger auswählen
        self._populate_trigger_combo()
        idx = self._combo_trigger.findData(trigger_name)
        if idx >= 0:
            self._combo_trigger.setCurrentIndex(idx)

    # --- Liste ---

    def _refresh_list(self):
        """Aktualisiert die Regelliste."""
        self._updating = True
        rules = self._engine.get_merged_rules()
        self._table.setRowCount(0)
        self._table.setRowCount(len(rules))

        for idx, rule in enumerate(rules):
            # Active Checkbox
            chk = QTableWidgetItem()
            chk.setCheckState(Qt.Checked if rule.active else Qt.Unchecked)
            chk.setFlags(chk.flags() | Qt.ItemIsUserCheckable)
            self._table.setItem(idx, 0, chk)

            # Name
            name_item = QTableWidgetItem(rule.name)
            name_item.setData(Qt.UserRole, rule.id)
            if rule.source == "system":
                name_item.setForeground(QColor("#888888"))
            self._table.setItem(idx, 1, name_item)

            # Trigger
            trigger_info = self._engine.registry.triggers.get(rule.trigger)
            trigger_display = trigger_info.display_name if trigger_info else rule.trigger
            self._table.setItem(idx, 2, QTableWidgetItem(trigger_display))

            # Source
            source_text = "System" if rule.source == "system" else "User"
            self._table.setItem(idx, 3, QTableWidgetItem(source_text))

            # System-Rules: Nicht verschiebbar
            if rule.source == "system":
                for col in range(4):
                    item = self._table.item(idx, col)
                    if item:
                        flags = item.flags()
                        flags &= ~Qt.ItemIsDragEnabled
                        flags &= ~Qt.ItemIsDropEnabled
                        item.setFlags(flags)

        self._apply_filter()
        self._updating = False

    def _apply_filter(self):
        """Filtert die Tabelle nach dem Suchtext."""
        text = self._search.text().lower()
        for row in range(self._table.rowCount()):
            name_item = self._table.item(row, 1)
            trigger_item = self._table.item(row, 2)
            if not name_item:
                continue
            visible = True
            if text:
                name_match = text in (name_item.text() or "").lower()
                trigger_match = text in (trigger_item.text() or "").lower()
                visible = name_match or trigger_match
            self._table.setRowHidden(row, not visible)

    def _on_table_item_changed(self, item):
        """Checkbox in Spalte 0 der Tabelle geaendert — Active-Toggle."""
        if self._updating:
            return
        if item.column() != 0:
            return
        row = item.row()
        name_item = self._table.item(row, 1)
        if not name_item:
            return
        rule_id = name_item.data(Qt.UserRole)
        active = item.checkState() == Qt.Checked
        for rule in self._engine.get_merged_rules():
            if rule.id == rule_id:
                rule.active = active
                if rule.source == "system":
                    self._engine.toggle_system_rule(rule.id, active)
                else:
                    self._engine.save_user_rules()
                    # Stream Deck live aktualisieren (Button erscheint/verschwindet)
                    self._engine._notify_rules_changed()
                # Editor-Checkbox synchronisieren
                if self._current_rule and self._current_rule.id == rule_id:
                    self._updating = True
                    self._chk_active.setChecked(active)
                    self._updating = False
                break

    def _rule_for_row(self, row: int):
        """Liefert das Rule-Objekt fuer eine Tabellenzeile (oder None)."""
        name_item = self._table.item(row, 1)
        if not name_item:
            return None
        rule_id = name_item.data(Qt.UserRole)
        for rule in self._engine.get_merged_rules():
            if rule.id == rule_id:
                return rule
        return None

    def _selected_rules(self) -> list:
        """Liefert alle Rule-Objekte der aktuell selektierten Zeilen."""
        rules = []
        for index in self._table.selectionModel().selectedRows():
            rule = self._rule_for_row(index.row())
            if rule:
                rules.append(rule)
        return rules

    def _on_selection_changed(self):
        """Zeigt die selektierte Rule im Editor bzw. aktualisiert die Buttons."""
        if self._updating:
            return
        rows = self._table.selectionModel().selectedRows()
        if not rows:
            self._current_rule = None
            self._set_editor_enabled(False)
            self._btn_duplicate.setEnabled(False)
            self._btn_delete.setEnabled(False)
            self._btn_up.setEnabled(False)
            self._btn_down.setEnabled(False)
            return

        if len(rows) > 1:
            # Mehrfachauswahl: Editor macht keinen Sinn, nur Duplizieren/Loeschen
            self._current_rule = None
            self._set_editor_enabled(False)
            self._btn_duplicate.setEnabled(True)
            has_user = any(r.source == "user" for r in self._selected_rules())
            self._btn_delete.setEnabled(has_user)
            self._btn_up.setEnabled(False)
            self._btn_down.setEnabled(False)
            return

        row = rows[0].row()
        name_item = self._table.item(row, 1)
        if not name_item:
            return
        rule_id = name_item.data(Qt.UserRole)

        # Rule finden
        for rule in self._engine.get_merged_rules():
            if rule.id == rule_id:
                self._current_rule = rule
                self._load_rule_into_editor(rule)
                is_user = rule.source == "user"
                self._set_editor_enabled(True, readonly=not is_user)
                self._btn_duplicate.setEnabled(True)
                self._btn_delete.setEnabled(is_user)
                # Up/Down: nur fuer User-Rules, Grenzen beachten
                self._update_move_buttons(row, is_user)
                return

    def _on_active_changed(self, state):
        """Active-Checkbox im Editor geaendert."""
        if self._updating or not self._current_rule:
            return
        active = state == Qt.Checked.value if hasattr(Qt.Checked, 'value') else state == 2
        if self._current_rule.source == "system":
            self._engine.toggle_system_rule(self._current_rule.id, active)
            self._current_rule.active = active
            self._refresh_list()
        else:
            self._btn_save.setEnabled(True)

    # --- Editor ---

    def _set_editor_enabled(self, enabled, readonly=False):
        """Aktiviert/deaktiviert den Editor."""
        self._edit_name.setEnabled(enabled and not readonly)
        self._combo_trigger.setEnabled(enabled and not readonly)
        self._chk_active.setEnabled(enabled)  # Immer editierbar
        self._chk_once.setEnabled(enabled and not readonly)
        self._btn_add_cond_group.setEnabled(enabled and not readonly)
        self._btn_add_action.setEnabled(enabled and not readonly)
        self._btn_save.setEnabled(False)

        # Stream-Deck-Sektion: bewusst NICHT durch readonly gesperrt —
        # auch System-Rules duerfen aufs Deck gepinnt werden.
        self._deck_group.setEnabled(enabled)

        if not enabled:
            self._updating = True
            self._edit_name.clear()
            self._chk_active.setChecked(False)
            self._chk_once.setChecked(False)
            self._combo_trigger.setCurrentIndex(0)
            self._clear_conditions()
            self._clear_actions()
            self._spin_button_number.setValue(0)
            self._combo_button_icon.setCurrentIndex(0)
            self._edit_button_tooltip.clear()
            self._update_icon_preview()
            self._updating = False

    def _load_rule_into_editor(self, rule: Rule):
        """Laedt eine Rule in den Editor."""
        self._updating = True

        self._edit_name.setText(rule.name)
        self._chk_active.setChecked(rule.active)
        self._chk_once.setChecked(rule.once_per_song)

        # Trigger
        for i in range(self._combo_trigger.count()):
            if self._combo_trigger.itemData(i) == rule.trigger:
                self._combo_trigger.setCurrentIndex(i)
                break

        # Conditions
        self._clear_conditions()
        for group_idx, group in enumerate(rule.conditions):
            if group_idx > 0:
                self._add_or_separator()
            group_widget = self._create_condition_group(group,
                                                        readonly=rule.source == "system")
            # Vor dem "Add OR Group" Button einfuegen
            idx = self._cond_layout.count() - 1
            self._cond_layout.insertWidget(idx, group_widget)

        # Actions
        self._clear_actions()
        for action in rule.actions:
            action_widget = self._create_action_row(action,
                                                     readonly=rule.source == "system")
            idx = self._action_layout.count() - 1
            self._action_layout.insertWidget(idx, action_widget)

        # Stream Deck
        self._load_stream_deck_into_editor(rule)

        # Mausrad-Schutz auf alle Combo-/Spinbox-Felder (auch die eben dynamisch
        # erzeugten Trigger-/Condition-/Action-Felder)
        self._install_wheel_guard()

        self._updating = False

    def _install_wheel_guard(self):
        """Schuetzt alle Combo-/Spinbox-Felder im Rules-Editor vor
        versehentlicher Werteaenderung durchs Mausrad beim Hovern.

        Delegiert an die zentrale Utility (wheel_guard.py). Idempotent — muss
        nach jedem dynamischen (Neu-)Aufbau von Feldern erneut laufen, da neue
        Widgets sonst ungeschuetzt bleiben.
        """
        install_wheel_guard(self)

    def _on_editor_changed(self, *args):
        """Markiert dass Aenderungen vorliegen."""
        if not self._updating and self._current_rule:
            if self._current_rule.source == "user":
                self._btn_save.setEnabled(True)

    # --- Conditions UI ---

    def _clear_conditions(self):
        """Entfernt alle Condition-Widgets (nicht den Add-Button)."""
        while self._cond_layout.count() > 1:
            item = self._cond_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

    def _create_condition_group(self, conditions, readonly=False):
        """Erstellt eine AND-Gruppe als Widget."""
        group = QWidget()
        group.setProperty("condition_group", True)
        layout = QHBoxLayout(group)
        layout.setContentsMargins(2, 2, 2, 2)

        for i, cond in enumerate(conditions):
            if i > 0:
                layout.addWidget(QLabel("AND"))

            combo = QComboBox()
            combo.setEnabled(not readonly)
            combo.setProperty("cond_combo", True)
            for c_str, c_info in self._engine.registry.conditions.items():
                combo.addItem(c_info.display_name, c_str)
            # Aktuelle Bedingung setzen
            for idx in range(combo.count()):
                if combo.itemData(idx) == cond.type:
                    combo.setCurrentIndex(idx)
                    break
            layout.addWidget(combo)

            # Parameter-Widgets fuer diese Condition
            self._add_cond_param_widgets(layout, cond.type,
                                          cond.params, readonly)

            # Type-Aenderung: Params neu aufbauen
            combo.currentIndexChanged.connect(
                lambda idx, c=combo, g=group: self._on_cond_type_changed(g, c))
            combo.currentIndexChanged.connect(self._on_editor_changed)

        if not readonly:
            btn_add = QPushButton("+")
            btn_add.setFixedWidth(28)
            btn_add.setStyleSheet(self._MINI_BTN_STYLE)
            btn_add.setToolTip(_t("rule.btn_add_condition"))
            btn_add.clicked.connect(
                lambda checked, g=group: self._add_condition_to_group(g))
            layout.addWidget(btn_add)

            btn_remove = QPushButton("×")
            btn_remove.setFixedWidth(28)
            btn_remove.setStyleSheet(self._MINI_BTN_STYLE)
            btn_remove.setToolTip("Remove Group")
            btn_remove.clicked.connect(
                lambda checked, g=group: self._remove_condition_group(g))
            layout.addWidget(btn_remove)

        layout.addStretch()
        return group

    def _add_cond_param_widgets(self, layout, cond_type: str,
                                 params: dict, readonly: bool,
                                 insert_at: int = -1):
        """Fuegt Parameter-Eingaben fuer einen Condition-Typ hinzu."""
        cond_info = self._engine.registry.conditions.get(cond_type)
        if not cond_info or not cond_info.params_schema:
            return

        pos = insert_at if insert_at >= 0 else layout.count()

        for param_name, schema in cond_info.params_schema.items():
            param_type = schema.get("type", "text")
            value = params.get(param_name, schema.get("default", ""))

            if param_type == "float":
                w = QDoubleSpinBox()
                w.setEnabled(not readonly)
                w.setRange(schema.get("min", 0), schema.get("max", 999))
                w.setSingleStep(0.5)
                w.setDecimals(1)
                w.setValue(float(value) if value else schema.get("default", 5))
                w.setProperty("cond_param_name", param_name)
                w.valueChanged.connect(self._on_editor_changed)
            elif param_type == "int":
                w = QSpinBox()
                w.setEnabled(not readonly)
                w.setRange(schema.get("min", 0), schema.get("max", 999))
                w.setValue(int(value) if value else schema.get("default", 0))
                w.setProperty("cond_param_name", param_name)
                w.valueChanged.connect(self._on_editor_changed)
            elif param_type == "choice":
                # Rohwerte als Item-Text (englisch, keine i18n — Rules-Konvention)
                w = QComboBox()
                w.setEnabled(not readonly)
                for c in schema.get("choices", []):
                    w.addItem(c)
                cur = value if value else schema.get("default", "")
                if cur:
                    idx = w.findText(str(cur))
                    if idx >= 0:
                        w.setCurrentIndex(idx)
                w.setProperty("cond_param_name", param_name)
                w.currentIndexChanged.connect(self._on_editor_changed)
            elif param_type == "genre_choice":
                # intern#218: wie bei den Genre-Aktionen
                w = QComboBox()
                w.setEnabled(not readonly)
                if self._genre_names_provider:
                    for _, gname in self._genre_names_provider():
                        w.addItem(gname)
                if value:
                    idx = w.findText(str(value))
                    if idx >= 0:
                        w.setCurrentIndex(idx)
                    else:
                        # Genre geloescht/umbenannt: trotzdem anbieten, sonst
                        # ueberschreibt das naechste Speichern die Regel still.
                        w.addItem(str(value))
                        w.setCurrentText(str(value))
                w.setProperty("cond_param_name", param_name)
                w.currentIndexChanged.connect(self._on_editor_changed)
            elif param_type == "mmss":
                # BL-205: Zeit-Eingabe mm:ss (auch reine Sekunden), als String
                # gespeichert; der Evaluator parst zu Sekunden.
                w = QLineEdit()
                w.setEnabled(not readonly)
                w.setPlaceholderText("mm:ss")
                w.setFixedWidth(70)
                w.setText(str(value) if value else schema.get("default", ""))
                w.setProperty("cond_param_name", param_name)
                w.textChanged.connect(self._on_editor_changed)
            else:
                w = QLineEdit()
                w.setEnabled(not readonly)
                w.setText(str(value) if value else "")
                w.setProperty("cond_param_name", param_name)
                w.textChanged.connect(self._on_editor_changed)

            layout.insertWidget(pos, w)
            pos += 1

    def _on_cond_type_changed(self, group_widget, combo):
        """Baut Condition-Parameter-Widgets neu wenn Typ geaendert."""
        layout = group_widget.layout()
        # Finde die Position dieses Combos im Layout
        combo_pos = -1
        for i in range(layout.count()):
            item = layout.itemAt(i)
            if item and item.widget() is combo:
                combo_pos = i
                break
        if combo_pos < 0:
            return
        # Entferne alte Param-Widgets direkt nach dem Combo
        while combo_pos + 1 < layout.count():
            item = layout.itemAt(combo_pos + 1)
            if not item or not item.widget():
                break
            w = item.widget()
            if w.property("cond_param_name"):
                layout.takeAt(combo_pos + 1)
                w.deleteLater()
            else:
                break
        # Neue Params einfuegen
        cond_type = combo.currentData()
        if cond_type:
            self._add_cond_param_widgets(layout, cond_type, {},
                                          False, insert_at=combo_pos + 1)
        self._install_wheel_guard()

    def _add_or_separator(self):
        """Fuegt ein OR-Label zwischen Gruppen ein."""
        lbl = QLabel("— OR —")
        lbl.setAlignment(Qt.AlignCenter)
        lbl.setProperty("or_separator", True)
        idx = self._cond_layout.count() - 1
        self._cond_layout.insertWidget(idx, lbl)

    def _on_add_or_group(self):
        """Fuegt eine neue OR-Gruppe hinzu."""
        if self._cond_layout.count() > 1:
            self._add_or_separator()
        # Leere Gruppe mit erster Bedingung
        first_cond = list(self._engine.registry.conditions.keys())
        default_cond = ConditionDef(
            type=first_cond[0] if first_cond else "")
        group = self._create_condition_group([default_cond])
        idx = self._cond_layout.count() - 1
        self._cond_layout.insertWidget(idx, group)
        self._install_wheel_guard()
        self._on_editor_changed()

    def _add_condition_to_group(self, group_widget):
        """Fuegt eine AND-Bedingung zu einer bestehenden Gruppe hinzu."""
        layout = group_widget.layout()
        # Neues Combo vor dem +/× Button einfuegen
        combo = QComboBox()
        combo.setProperty("cond_combo", True)
        for c_str, c_info in self._engine.registry.conditions.items():
            combo.addItem(c_info.display_name, c_str)
        combo.currentIndexChanged.connect(
            lambda idx, c=combo, g=group_widget: self._on_cond_type_changed(g, c))
        combo.currentIndexChanged.connect(self._on_editor_changed)

        lbl = QLabel("AND")
        # Position: vor den letzten 3 Widgets (+, ×, stretch)
        insert_at = max(0, layout.count() - 3)
        layout.insertWidget(insert_at, lbl)
        layout.insertWidget(insert_at + 1, combo)
        self._install_wheel_guard()
        self._on_editor_changed()

    def _remove_condition_group(self, group_widget):
        """Entfernt eine OR-Gruppe."""
        idx = self._cond_layout.indexOf(group_widget)
        group_widget.deleteLater()
        # OR-Separator davor oder danach entfernen
        if idx > 0:
            prev = self._cond_layout.itemAt(idx - 1)
            if prev and prev.widget() and prev.widget().property("or_separator"):
                prev.widget().deleteLater()
        elif self._cond_layout.count() > 1:
            nxt = self._cond_layout.itemAt(0)
            if nxt and nxt.widget() and nxt.widget().property("or_separator"):
                nxt.widget().deleteLater()
        self._on_editor_changed()

    # --- Actions UI ---

    def _clear_actions(self):
        """Entfernt alle Action-Widgets (nicht den Add-Button)."""
        while self._action_layout.count() > 1:
            item = self._action_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

    def _create_action_row(self, action: ActionDef, readonly=False):
        """Erstellt eine Action-Zeile.

        Aufbau (BL-188): vertikal — Kopfzeile (Handle + Aktions-ComboBox + ×)
        und darunter eine eingerueckte Formularspalte mit Label + Eingabe pro
        Parameter. So bleibt das Rules-Fenster schmal, egal wie viele Parameter
        eine Aktion hat, und jeder Parameter ist benannt.
        """
        row = QWidget()
        row.setProperty("action_row", True)
        outer = QVBoxLayout(row)
        outer.setContentsMargins(2, 2, 2, 2)
        outer.setSpacing(2)

        # --- Kopfzeile: Handle + Aktions-ComboBox + × ---
        top = QWidget()
        top_l = QHBoxLayout(top)
        top_l.setContentsMargins(0, 0, 0, 0)

        if not readonly:
            handle = _ActionDragHandle(self, row)
            top_l.addWidget(handle)

        combo = QComboBox()
        combo.setEnabled(not readonly)
        _populate_action_combo(combo, self._engine.registry.actions)
        for idx in range(combo.count()):
            if combo.itemData(idx) == action.type:
                combo.setCurrentIndex(idx)
                break
        combo.setProperty("action_combo", True)
        combo.currentIndexChanged.connect(
            lambda i, r=row, c=combo: self._on_action_type_changed(r, c))
        combo.currentIndexChanged.connect(self._on_editor_changed)
        top_l.addWidget(combo)

        if not readonly:
            btn_remove = QPushButton("×")
            btn_remove.setFixedWidth(28)
            btn_remove.setStyleSheet(self._MINI_BTN_STYLE)
            btn_remove.clicked.connect(
                lambda checked, r=row: self._remove_action_row(r))
            top_l.addWidget(btn_remove)

        top_l.addStretch()
        outer.addWidget(top)

        # --- Parameter-Formular (eingerueckt unter der Aktion) ---
        params_box = QWidget()
        params_box.setProperty("params_box", True)
        form = QFormLayout(params_box)
        form.setContentsMargins(24, 0, 4, 0)
        form.setSpacing(3)
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        form.setFieldGrowthPolicy(QFormLayout.FieldsStayAtSizeHint)
        outer.addWidget(params_box)

        self._add_param_widgets(form, action.type, action.params, readonly)
        params_box.setVisible(form.rowCount() > 0)
        return row

    def _on_action_type_changed(self, row_widget, combo):
        """Baut das Parameter-Formular neu, wenn der Action-Typ geaendert wird."""
        # Gruppenheader haben data=None — nicht auswaehlbar, aber ignorieren
        if combo.currentData() is None:
            return
        # Param-Formular der Zeile finden
        params_box = None
        for child in row_widget.findChildren(QWidget):
            if child.property("params_box"):
                params_box = child
                break
        if params_box is None:
            return
        form = params_box.layout()
        # Alte Formularzeilen entfernen (loescht Labels + Editoren mit)
        while form.rowCount() > 0:
            form.removeRow(0)

        action_type = combo.currentData()
        if action_type:
            self._add_param_widgets(form, action_type, {}, False)
        params_box.setVisible(form.rowCount() > 0)
        self._install_wheel_guard()

    def _add_param_widgets(self, form, action_type: str, params: dict,
                            readonly: bool):
        """Fuegt pro Parameter eine Formularzeile (Label + Editor) in das
        uebergebene QFormLayout ein."""
        action_info = self._engine.registry.actions.get(action_type)
        if not action_info or not action_info.params_schema:
            return

        for param_name, schema in action_info.params_schema.items():
            param_type = schema.get("type", "text")
            value = params.get(param_name, schema.get("default", ""))

            if param_type == "dock_choice":
                w = QComboBox()
                w.setEnabled(not readonly)
                # Dock-Namen aus Provider
                if self._dock_names_provider:
                    for name in sorted(self._dock_names_provider().keys()):
                        w.addItem(name)
                if value:
                    idx = w.findText(str(value))
                    if idx >= 0:
                        w.setCurrentIndex(idx)
                w.setProperty("param_name", param_name)
                w.currentIndexChanged.connect(self._on_editor_changed)

            elif param_type == "layout_choice":
                w = QComboBox()
                w.setEnabled(not readonly)
                w.addItem("default")
                if self._layout_names_provider:
                    for lname in self._layout_names_provider():
                        if lname != "default":
                            w.addItem(lname)
                elif value and value != "default":
                    w.addItem(str(value))
                w.setCurrentText(str(value) if value else "default")
                w.setProperty("param_name", param_name)
                w.currentIndexChanged.connect(self._on_editor_changed)

            elif param_type == "genre_choice":
                w = QComboBox()
                w.setEnabled(not readonly)
                if self._genre_names_provider:
                    for _, gname in self._genre_names_provider():
                        w.addItem(gname)
                if value:
                    idx = w.findText(str(value))
                    if idx >= 0:
                        w.setCurrentIndex(idx)
                w.setProperty("param_name", param_name)
                w.currentIndexChanged.connect(self._on_editor_changed)

            elif param_type == "seqtype_choice":
                # BL-181: vorhandene Sequenz-Typwerte aus der DB (Freitext)
                w = QComboBox()
                w.setEnabled(not readonly)
                if self._seqtype_names_provider:
                    for tname in self._seqtype_names_provider():
                        w.addItem(tname)
                if value:
                    idx = w.findText(str(value))
                    if idx >= 0:
                        w.setCurrentIndex(idx)
                    else:
                        # Gespeicherter Typ existiert nicht mehr in der DB:
                        # trotzdem anbieten, damit die Rule erhalten bleibt.
                        w.addItem(str(value))
                        w.setCurrentText(str(value))
                w.setProperty("param_name", param_name)
                w.currentIndexChanged.connect(self._on_editor_changed)

            elif param_type in ("call_choice", "difficulty_choice", "tags_choice"):
                # BL-193/194/196/197: editierbares Dropdown aus dem passenden
                # Provider. Erster (leerer) Eintrag = "kein Filter".
                w = QComboBox()
                w.setEnabled(not readonly)
                w.setEditable(True)
                w.setInsertPolicy(QComboBox.NoInsert)
                w.addItem("")
                _provider = {
                    "call_choice":       self._call_names_provider,
                    "difficulty_choice": self._difficulty_names_provider,
                    "tags_choice":       self._tags_names_provider,
                }.get(param_type)
                if _provider:
                    try:
                        for _name in _provider():
                            w.addItem(str(_name))
                    except Exception:
                        pass
                w.setCurrentText(str(value) if value else "")
                w.setProperty("param_name", param_name)
                w.currentTextChanged.connect(self._on_editor_changed)

            elif param_type == "program_multichoice":
                # BL-192: Mehrfachauswahl der Tanzprogramme als Checkbox-Liste.
                # Gespeichert wird eine komma-separierte ID-Liste (String).
                w = QListWidget()
                w.setEnabled(not readonly)
                w.setUniformItemSizes(True)
                w.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
                w.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
                w.setSelectionMode(QAbstractItemView.NoSelection)
                _sel = {p.strip() for p in str(value or "").split(",") if p.strip()}
                if self._program_choices_provider:
                    try:
                        for _pid, _label in self._program_choices_provider():
                            _it = QListWidgetItem(str(_label))
                            _it.setFlags(_it.flags() | Qt.ItemIsUserCheckable)
                            _it.setCheckState(
                                Qt.Checked if str(_pid) in _sel else Qt.Unchecked)
                            _it.setData(Qt.UserRole, _pid)
                            w.addItem(_it)
                    except Exception:
                        pass
                # Theme-Farben (Fallback fuer skinlose Kontexte / Tests)
                _sm = self._skin_mgr
                _c = (lambda k, d: _sm.color(k, d) if _sm else d)
                _border = _c("border", "#555555")
                _bg = _c("widget_bg", "#363636")
                _txt = _c("text", "#f0f0f0")
                _hov = _c("muted_bg", "#424242")
                _acc = _c("button_bg", "#615f8b")
                w.setStyleSheet(
                    f"QListWidget {{ border: 1px solid {_border}; border-radius: 4px;"
                    f" background: {_bg}; color: {_txt}; padding: 2px; outline: 0; }}"
                    f"QListWidget::item {{ padding: 5px 6px; border-radius: 3px; }}"
                    f"QListWidget::item:hover {{ background: {_hov}; }}"
                    f"QListWidget::item:selected {{ background: {_acc}; color: {_txt}; }}"
                )
                # Hoehe an den Inhalt anpassen: alle Zeilen zeigen, ab 8 scrollen.
                _rows = max(1, w.count())
                _row_h = w.sizeHintForRow(0) if w.count() else 24
                _visible = min(_rows, 8)
                w.setFixedHeight(_visible * _row_h + 2 * w.frameWidth() + 6)
                w.setProperty("param_name", param_name)
                w.itemChanged.connect(self._on_editor_changed)

            elif param_type == "preset_choice":
                w = QComboBox()
                w.setEnabled(not readonly)
                if self._preset_names_provider:
                    for pname in self._preset_names_provider():
                        w.addItem(pname)
                if value:
                    idx = w.findText(str(value))
                    if idx >= 0:
                        w.setCurrentIndex(idx)
                w.setProperty("param_name", param_name)
                w.currentIndexChanged.connect(self._on_editor_changed)

            elif param_type == "float":
                w = QDoubleSpinBox()
                w.setEnabled(not readonly)
                w.setRange(schema.get("min", 0), schema.get("max", 999))
                w.setSingleStep(0.5)
                w.setDecimals(1)
                w.setValue(float(value) if value else schema.get("default", 0))
                w.setProperty("param_name", param_name)
                w.valueChanged.connect(self._on_editor_changed)

            elif param_type == "int":
                w = QSpinBox()
                w.setEnabled(not readonly)
                w.setRange(schema.get("min", -999999),
                           schema.get("max", 999999))
                w.setValue(int(value) if value else schema.get("default", 0))
                w.setProperty("param_name", param_name)
                w.valueChanged.connect(self._on_editor_changed)

            elif param_type == "choice":
                w = QComboBox()
                w.setEnabled(not readonly)
                for c in schema.get("choices", []):
                    w.addItem(c)
                if value:
                    idx = w.findText(str(value))
                    if idx >= 0:
                        w.setCurrentIndex(idx)
                w.setProperty("param_name", param_name)
                w.currentIndexChanged.connect(self._on_editor_changed)

            elif param_type == "file":
                # BL-137: Datei-Param mit Browse-Button. LineEdit traegt den
                # param_name (wird beim Auslesen erkannt), der Button daneben
                # oeffnet QFileDialog mit dem in der Schema angegebenen Filter.
                w = QLineEdit()
                w.setEnabled(not readonly)
                w.setText(str(value) if value else "")
                w.setProperty("param_name", param_name)
                w.textChanged.connect(self._on_editor_changed)
                # Browse-Button als zusaetzliches Widget einfuegen (ohne param_name,
                # damit der Extractor ihn ignoriert).
                browse = QPushButton("…")
                browse.setFixedWidth(28)
                browse.setEnabled(not readonly)
                file_filter = schema.get("file_filter", "Alle Dateien (*.*)")
                def _pick(checked=False, _w=w, _filter=file_filter, _name=param_name):
                    import os as _os
                    start_dir = _os.path.dirname(_w.text()) if _w.text() and _os.path.isfile(_w.text()) else ""
                    chosen, _ = QFileDialog.getOpenFileName(
                        self, f"Datei wählen — {_name}", start_dir, _filter,
                    )
                    if chosen:
                        _w.setText(chosen)
                browse.clicked.connect(_pick)
                # LineEdit + Browse-Button in einen Container (param_name bleibt
                # am LineEdit → Extractor findet ihn per findChildren)
                field = QWidget()
                fl = QHBoxLayout(field)
                fl.setContentsMargins(0, 0, 0, 0)
                fl.addWidget(w)
                fl.addWidget(browse)
                form.addRow(_param_label(param_name, schema), field)
                continue

            elif param_type == "time_offset":
                # Relative Verschiebung im Format mm:ss.cs mit optionalem
                # Vorzeichen (z.B. -0:20). Als String gespeichert, im Handler
                # zu Sekunden geparst; der Extractor liest QLineEdit -> text.
                w = QLineEdit()
                w.setEnabled(not readonly)
                w.setText(str(value) if value else "")
                w.setPlaceholderText("mm:ss.cs  (z.B. -0:20)")
                w.setToolTip("Relative Verschiebung: Minuten:Sekunden.Hundertstel, "
                             "Vorzeichen optional. -0:20 = 20 s zurück, 0:05 = 5 s vor.")
                w.setProperty("param_name", param_name)
                w.textChanged.connect(self._on_editor_changed)

            else:  # text
                w = QLineEdit()
                w.setEnabled(not readonly)
                w.setText(str(value) if value else "")
                w.setProperty("param_name", param_name)
                w.textChanged.connect(self._on_editor_changed)

            form.addRow(_param_label(param_name, schema), w)

    def _on_add_action(self):
        """Fuegt eine neue leere Action hinzu."""
        first_action = list(self._engine.registry.actions.keys())
        default = ActionDef(type=first_action[0] if first_action else "")
        row = self._create_action_row(default)
        idx = self._action_layout.count() - 1
        self._action_layout.insertWidget(idx, row)
        self._install_wheel_guard()
        self._on_editor_changed()

    def _remove_action_row(self, row_widget):
        row_widget.deleteLater()
        self._on_editor_changed()

    def _on_action_drag(self, source_row, global_y: int):
        """Verschiebt eine Action-Zeile live waehrend des Drag."""
        layout = self._action_layout
        n = layout.count() - 1  # -1 fuer den Add-Button am Ende

        # Quell-Index bestimmen
        src_idx = -1
        for i in range(n):
            item = layout.itemAt(i)
            if item and item.widget() is source_row:
                src_idx = i
                break
        if src_idx < 0:
            return

        # Ziel-Index anhand globaler Maus-Y bestimmen
        target_idx = n - 1  # Default: ans Ende
        for i in range(n):
            item = layout.itemAt(i)
            if not item:
                continue
            w = item.widget()
            if w is None:
                continue
            mid_y = w.mapToGlobal(w.rect().center()).y()
            if global_y < mid_y:
                target_idx = i
                break

        if target_idx == src_idx:
            return

        # Widget in neue Position verschieben
        layout.removeWidget(source_row)
        layout.insertWidget(target_idx, source_row)
        self._on_editor_changed()

    # --- Save ---

    def _capture_editor_into_rule(self, rule):
        """Uebernimmt alle Editor-Felder (Name/Trigger/Conditions/Actions) ins
        Rule-Objekt. Getrennt von _on_save_rule, damit auch _on_deck_changed die
        noch nicht per Save bestaetigten Eingaben sichern kann, bevor die Rule
        beim Deck-Persistieren neu geladen wird."""
        rule.name = self._edit_name.text().strip() or "Unnamed Rule"
        rule.active = self._chk_active.isChecked()
        rule.once_per_song = self._chk_once.isChecked()
        rule.trigger = self._combo_trigger.currentData() or ""
        rule.conditions = self._read_conditions_from_editor()
        rule.actions = self._read_actions_from_editor()

    def _on_save_rule(self):
        """Speichert die aktuelle Rule."""
        if not self._current_rule or self._current_rule.source != "user":
            return

        rule = self._current_rule
        self._capture_editor_into_rule(rule)
        self._engine.update_user_rule(rule)

        # Deck-Parameter gemeinsam mitspeichern (inkl. kompakter Neunummerierung).
        # update_user_rule hat die Rule mit Haupt-Feldern bereits in die Liste
        # synchronisiert; set_stream_deck_params ergaenzt die Deck-Felder und
        # schreibt erneut — so landet alles in EINEM Save-Klick auf Platte.
        self._engine.set_stream_deck_params(
            rule.id, self._spin_button_number.value(),
            self._combo_button_icon.currentData() or "",
            self._edit_button_tooltip.text().strip())

        self._btn_save.setEnabled(False)
        self._refresh_list()

    def _read_conditions_from_editor(self) -> list:
        """Liest Condition-Gruppen aus dem Editor."""
        groups = []
        current_group = []

        for i in range(self._cond_layout.count()):
            item = self._cond_layout.itemAt(i)
            if not item or not item.widget():
                continue
            w = item.widget()

            if w.property("or_separator"):
                if current_group:
                    groups.append(current_group)
                    current_group = []
                continue

            if w.property("condition_group"):
                # AND-Gruppe: Combos + zugehoerige Params auslesen
                and_conds = []
                layout = w.layout()
                current_ctype = None
                current_params = {}
                for j in range(layout.count()):
                    child_item = layout.itemAt(j)
                    if not child_item or not child_item.widget():
                        continue
                    child = child_item.widget()
                    if child.property("cond_combo"):
                        # Vorherige Condition abschliessen
                        if current_ctype:
                            and_conds.append(ConditionDef(
                                type=current_ctype, params=current_params))
                        current_ctype = child.currentData()
                        current_params = {}
                    elif child.property("cond_param_name"):
                        pname = child.property("cond_param_name")
                        if isinstance(child, QComboBox):
                            current_params[pname] = child.currentText()
                        elif isinstance(child, QDoubleSpinBox):
                            current_params[pname] = child.value()
                        elif isinstance(child, QSpinBox):
                            current_params[pname] = child.value()
                        elif isinstance(child, QLineEdit):
                            current_params[pname] = child.text()
                # Letzte Condition abschliessen
                if current_ctype:
                    and_conds.append(ConditionDef(
                        type=current_ctype, params=current_params))
                if and_conds:
                    current_group = and_conds

        if current_group:
            groups.append(current_group)
        return groups

    def _read_actions_from_editor(self) -> list:
        """Liest Actions aus dem Editor."""
        actions = []
        for i in range(self._action_layout.count()):
            item = self._action_layout.itemAt(i)
            if not item or not item.widget():
                continue
            w = item.widget()
            if not w.property("action_row"):
                continue

            action_type = ""
            params = {}

            # Aktions-ComboBox (Kopfzeile)
            for c in w.findChildren(QComboBox):
                if c.property("action_combo"):
                    action_type = c.currentData() or ""
                    break

            # Parameter-Editoren (im eingerueckten Formular verschachtelt)
            for child in w.findChildren(QWidget):
                pname = child.property("param_name")
                if not pname:
                    continue
                if isinstance(child, QListWidget):
                    # BL-192: komma-separierte ID-Liste der angehakten Programme
                    ids = []
                    for r in range(child.count()):
                        it = child.item(r)
                        if it.checkState() == Qt.Checked:
                            ids.append(str(it.data(Qt.UserRole)))
                    params[pname] = ",".join(ids)
                elif isinstance(child, QComboBox):
                    params[pname] = child.currentText()
                elif isinstance(child, QDoubleSpinBox):
                    params[pname] = child.value()
                elif isinstance(child, QSpinBox):
                    params[pname] = child.value()
                elif isinstance(child, QLineEdit):
                    params[pname] = child.text()

            if action_type:
                actions.append(ActionDef(type=action_type, params=params))
        return actions

    # --- Add / Duplicate / Delete ---

    def _on_add_rule(self):
        """Neue User-Rule erstellen."""
        rule = Rule(
            id="",
            name="New Rule",
            active=True,
            trigger="song_started",
            conditions=[],
            actions=[],
            source="user",
        )
        self._engine.add_user_rule(rule)
        self._refresh_list()
        # Letzte Zeile selektieren
        last = self._table.rowCount() - 1
        if last >= 0:
            self._table.selectRow(last)

    def _on_duplicate_rule(self):
        """Selektierte Rule(n) duplizieren als User-Rule(n)."""
        rules = self._selected_rules()
        if not rules:
            return
        import copy
        for rule in rules:
            new_rule = Rule(
                id="",
                name=f"{rule.name} (Copy)",
                active=True,
                trigger=rule.trigger,
                conditions=copy.deepcopy(rule.conditions),
                actions=copy.deepcopy(rule.actions),
                source="user",
            )
            self._engine.add_user_rule(new_rule)
        self._refresh_list()

    def _on_delete_rule(self):
        """Selektierte User-Rule(n) loeschen (System-Rules werden ignoriert)."""
        rules = [r for r in self._selected_rules() if r.source == "user"]
        if not rules:
            return
        if len(rules) == 1:
            message = _t("rule.confirm_delete")
        else:
            message = _t("rule.confirm_delete_multi").replace("{n}", str(len(rules)))
        reply = QMessageBox.question(
            self,
            _t("rule.confirm_delete_title"),
            message,
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            for rule in rules:
                self._engine.delete_user_rule(rule.id)
            self._current_rule = None
            self._set_editor_enabled(False)
            self._refresh_list()

    # --- Reorder (Up/Down) ---

    def _update_move_buttons(self, row: int, is_user: bool):
        """Aktiviert/deaktiviert Up/Down-Buttons je nach Position."""
        if not is_user:
            self._btn_up.setEnabled(False)
            self._btn_down.setEnabled(False)
            return
        # System-Rules zaehlen (stehen immer oben)
        sys_count = len(self._engine.get_system_rules())
        total = self._table.rowCount()
        self._btn_up.setEnabled(row > sys_count)
        self._btn_down.setEnabled(row < total - 1)

    def _on_move_up(self):
        """Verschiebt die selektierte User-Rule eine Position nach oben."""
        if not self._current_rule or self._current_rule.source != "user":
            return
        user_rules = self._engine.get_user_rules()
        ids = [r.id for r in user_rules]
        try:
            idx = ids.index(self._current_rule.id)
        except ValueError:
            return
        if idx <= 0:
            return
        ids[idx], ids[idx - 1] = ids[idx - 1], ids[idx]
        self._engine.reorder_user_rules(ids)
        self._refresh_list()
        self._select_rule_by_id(self._current_rule.id)

    def _on_move_down(self):
        """Verschiebt die selektierte User-Rule eine Position nach unten."""
        if not self._current_rule or self._current_rule.source != "user":
            return
        user_rules = self._engine.get_user_rules()
        ids = [r.id for r in user_rules]
        try:
            idx = ids.index(self._current_rule.id)
        except ValueError:
            return
        if idx >= len(ids) - 1:
            return
        ids[idx], ids[idx + 1] = ids[idx + 1], ids[idx]
        self._engine.reorder_user_rules(ids)
        self._refresh_list()
        self._select_rule_by_id(self._current_rule.id)

    def _select_rule_by_id(self, rule_id: str):
        """Selektiert eine Zeile anhand der Rule-ID."""
        for row in range(self._table.rowCount()):
            item = self._table.item(row, 1)
            if item and item.data(Qt.UserRole) == rule_id:
                self._table.selectRow(row)
                return

    # --- Export / Import ---

    def _on_export_rules(self):
        """Exportiert User-Rules als JSON-Datei.

        Ist in der Tabelle etwas markiert, werden nur die selektierten
        User-Rules exportiert. Ohne Selektion werden alle exportiert.
        """
        user_rules = self._engine.get_user_rules()
        if not user_rules:
            QMessageBox.information(
                self, _t("rule.export_title"),
                _t("rule.export_empty"))
            return

        selected_rows = self._table.selectionModel().selectedRows()
        if selected_rows:
            selected_ids = set()
            for index in selected_rows:
                name_item = self._table.item(index.row(), 1)
                if name_item:
                    selected_ids.add(name_item.data(Qt.UserRole))
            user_rules = [r for r in user_rules if r.id in selected_ids]
            if not user_rules:
                QMessageBox.information(
                    self, _t("rule.export_title"),
                    _t("rule.export_empty"))
                return

        path, _ = QFileDialog.getSaveFileName(
            self, _t("rule.export_title"), "my_rules.json",
            "JSON Files (*.json)")
        if not path:
            return
        data = {
            "version": 1,
            "source": "callers_caddy_user_rules",
            "rules": [r.to_dict() for r in user_rules],
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        QMessageBox.information(
            self, _t("rule.export_title"),
            _t("rule.export_success").replace("{n}", str(len(user_rules))))

    def _on_import_rules(self):
        """Importiert User-Rules aus einer JSON-Datei."""
        path, _ = QFileDialog.getOpenFileName(
            self, _t("rule.import_title"), "",
            "JSON Files (*.json)")
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            QMessageBox.warning(
                self, _t("rule.import_title"),
                _t("rule.import_error").replace("{e}", str(e)))
            return
        rules_data = data.get("rules", [])
        if not rules_data:
            QMessageBox.information(
                self, _t("rule.import_title"),
                _t("rule.import_empty"))
            return
        # Importierte Rules bekommen neue IDs um Konflikte zu vermeiden
        import time
        imported = 0
        for rd in rules_data:
            try:
                from rule_engine import Rule
                rule = Rule.from_dict(rd)
                rule.source = "user"
                rule.id = f"usr_{int(time.time() * 1000)}_{imported}"
                self._engine.add_user_rule(rule)
                imported += 1
            except Exception:
                continue
        self._refresh_list()
        QMessageBox.information(
            self, _t("rule.import_title"),
            _t("rule.import_success").replace("{n}", str(imported)))
