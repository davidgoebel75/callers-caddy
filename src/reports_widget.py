"""Reports-UI fuer Callers Caddy (BL-201, Stufe 11, aus main.py).

ReportsWidget: Setlist-Export und weitere Reports.
Zirkelfrei: keine Rueckbezuege auf main.py.
"""

import os

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QFormLayout, QPushButton, QFileDialog, QCheckBox,
    QTableWidget, QTableWidgetItem, QComboBox,
)

from i18n import _t


class ReportsWidget(QWidget):
    """Reports-Fenster: Setlist-Export und weitere Reports."""

    def __init__(self, db, paths=None, parent=None):
        super().__init__(parent)
        self.db = db
        self.paths = paths
        self._date_format = "de"
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)

        # Filter-Bereich
        filter_layout = QFormLayout()
        filter_layout.setSpacing(4)

        self._combo_location = QComboBox()
        self._combo_location.currentIndexChanged.connect(self._on_location_changed)
        filter_layout.addRow(_t("report_location"), self._combo_location)

        self._combo_date = QComboBox()
        self._combo_date.currentIndexChanged.connect(self._on_date_changed)
        filter_layout.addRow(_t("report_date"), self._combo_date)

        layout.addLayout(filter_layout)

        # Checkbox Uhrzeit
        self._chk_time = QCheckBox(_t("report_show_time"))
        self._chk_time.toggled.connect(self._refresh_table)
        layout.addWidget(self._chk_time)

        # Tabelle
        self._table = QTableWidget()
        self._table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectRows)
        self._table.setAlternatingRowColors(True)
        self._table.verticalHeader().setVisible(False)
        layout.addWidget(self._table, 1)

        # Export-Button
        self._btn_export = QPushButton(_t("report_export"))
        self._btn_export.setEnabled(False)
        self._btn_export.clicked.connect(self._on_export)
        layout.addWidget(self._btn_export)

        # Lazy Init: Erst beim ersten Sichtbarwerden befuellen
        self._refreshing = False
        self._initialized = False

    def showEvent(self, event):
        super().showEvent(event)
        if not self._initialized:
            self._initialized = True
            self._populate_filters()

    def set_date_format(self, fmt: str):
        self._date_format = fmt
        if self._initialized:
            self._refresh_table()

    def _format_date(self, iso_date: str) -> str:
        """ISO-Datum (2026-03-13) ins Anzeigeformat."""
        try:
            parts = iso_date.split("-")
            if self._date_format == "us":
                return f"{parts[1]}/{parts[2]}/{parts[0]}"
            return f"{parts[2]}.{parts[1]}.{parts[0]}"
        except (IndexError, AttributeError):
            return iso_date

    def _populate_filters(self):
        """Fuellt beide Combos initial."""
        self._refreshing = True

        self._combo_location.clear()
        self._combo_location.addItem(_t("report_all"), None)
        for loc_id, name in self.db.get_setlist_locations():
            self._combo_location.addItem(name, loc_id)

        self._combo_date.clear()
        self._combo_date.addItem(_t("report_all"), None)
        for d in self.db.get_setlist_dates():
            self._combo_date.addItem(self._format_date(d), d)

        self._refreshing = False
        self._refresh_table()

    def _on_location_changed(self):
        if self._refreshing:
            return
        self._refreshing = True
        loc_id = self._combo_location.currentData()

        # Datum-Combo aktualisieren
        current_date = self._combo_date.currentData()
        self._combo_date.clear()
        self._combo_date.addItem(_t("report_all"), None)
        for d in self.db.get_setlist_dates(loc_id):
            self._combo_date.addItem(self._format_date(d), d)

        # Vorherige Auswahl wiederherstellen wenn moeglich
        if current_date:
            idx = self._combo_date.findData(current_date)
            if idx >= 0:
                self._combo_date.setCurrentIndex(idx)

        self._refreshing = False
        self._refresh_table()

    def _on_date_changed(self):
        if self._refreshing:
            return
        self._refreshing = True
        date_str = self._combo_date.currentData()

        # Location-Combo aktualisieren
        current_loc = self._combo_location.currentData()
        self._combo_location.clear()
        self._combo_location.addItem(_t("report_all"), None)
        for loc_id, name in self.db.get_setlist_locations(date_str):
            self._combo_location.addItem(name, loc_id)

        # Vorherige Auswahl wiederherstellen wenn moeglich
        if current_loc:
            idx = self._combo_location.findData(current_loc)
            if idx >= 0:
                self._combo_location.setCurrentIndex(idx)

        self._refreshing = False
        self._refresh_table()

    def _refresh_table(self):
        """Tabelle befuellen basierend auf aktuellem Filter."""
        loc_id = self._combo_location.currentData()
        date_str = self._combo_date.currentData()
        show_time = self._chk_time.isChecked()

        # Spalten aufbauen
        cols = [_t("report_col_nr"), _t("report_col_title"), _t("report_col_label")]
        if show_time:
            cols.append(_t("report_col_time"))
        self._table.setColumnCount(len(cols))
        self._table.setHorizontalHeaderLabels(cols)

        if loc_id is None:
            self._table.setRowCount(0)
            self._btn_export.setEnabled(False)
            return

        rows = self.db.get_setlist(loc_id, date_str)  # date_str=None → alle Tage
        self._table.setUpdatesEnabled(False)
        self._table.setRowCount(0)
        self._table.setRowCount(len(rows))
        for i, (title, label, played_at) in enumerate(rows):
            self._table.setItem(i, 0, QTableWidgetItem(str(i + 1)))
            self._table.setItem(i, 1, QTableWidgetItem(title or ""))
            self._table.setItem(i, 2, QTableWidgetItem(label or ""))
            if show_time and played_at:
                time_str = played_at[11:16] if len(played_at) >= 16 else ""
                self._table.setItem(i, 3, QTableWidgetItem(time_str))
        self._table.setUpdatesEnabled(True)
        self._table.resizeColumnsToContents()

        self._btn_export.setEnabled(len(rows) > 0)

    def _on_export(self):
        """Exportiert die aktuelle Setlist als TXT."""
        loc_id = self._combo_location.currentData()
        loc_name = self._combo_location.currentText()
        date_str = self._combo_date.currentData()
        show_time = self._chk_time.isChecked()

        if loc_id is None:
            return

        # Wenn kein bestimmtes Datum → alle Tage dieser Location (chronologisch)
        if date_str:
            dates = [date_str]
        else:
            dates = list(reversed(self.db.get_setlist_dates(loc_id)))

        # Datei-Dialog
        default_name = f"Setlist_{loc_name}_{dates[0] if dates else 'export'}.txt"
        start_dir = self.paths.app_dir if self.paths else os.path.expanduser("~")
        filepath, _ = QFileDialog.getSaveFileName(
            self, _t("report_export"), os.path.join(start_dir, default_name),
            "Text (*.txt)"
        )
        if not filepath:
            return

        # Spaltenheader bauen
        hdr_nr = _t("report_col_nr")
        hdr_title = _t("report_col_title")
        hdr_label = _t("report_col_label")
        hdr_time = _t("report_col_time")
        header_line = f"{hdr_nr:<5s} {hdr_title:<40s} {hdr_label}"
        if show_time:
            header_line += f"  {hdr_time}"
        separator = "-" * len(header_line)

        lines = [f"Setlist — {loc_name}", ""]
        for d in dates:
            lines.append(self._format_date(d))
            lines.append("")
            lines.append(header_line)
            lines.append(separator)
            rows = self.db.get_setlist(loc_id, d)
            if not rows:
                lines.append(f"  ({_t('report_no_data')})")
            else:
                for i, (title, label, played_at) in enumerate(rows):
                    nr = f"{i + 1:3d}."
                    parts = [f"{nr:<5s}", f" {title or '':<40s}", label or ""]
                    if show_time and played_at:
                        time_str = played_at[11:16] if len(played_at) >= 16 else ""
                        parts.append(f"  {time_str}")
                    lines.append("".join(parts))
            lines.append("")

        with open(filepath, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        print(f"[Reports] Setlist exportiert: {filepath}")

    def refresh(self):
        """Extern aufrufen wenn sich History-Daten geaendert haben."""
        self._populate_filters()
