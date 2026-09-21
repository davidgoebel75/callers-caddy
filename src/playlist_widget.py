"""Playlist-UI fuer Callers Caddy (BL-201, Stufe 8, aus main.py).

PlaylistWidget (aktuelle Abspielliste) und PlaylistManagerWidget (Zauberstab-
Autofill/Planner) samt Tabellen-Helfern und PlaylistEntry.
Zirkelfrei: keine Rueckbezuege auf main.py.
"""

import re
from dataclasses import dataclass
from datetime import date, datetime

from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QPushButton, QLabel, QFileDialog,
    QSpinBox, QFormLayout, QTableWidget, QTableWidgetItem, QHeaderView,
    QComboBox, QMessageBox, QDialog, QMenu, QAbstractItemView, QSplitter,
)
from PySide6.QtCore import Qt, QMimeData, QSize
from PySide6.QtGui import QBrush, QPalette

from song_db import SongDatabase, Song
from path_manager import PathManager
from i18n import _t
from perf import perf_start, perf_log
from stats_widget import add_song_rating_actions
from songdata_widget import SongFilterBar
from ui_helpers import (
    _make_icon, _reco_score, _style_date_cell, _WrapButtonBar,
    _SVG_AUTOFILL, calc_auto_loop, show_loop_count_dialog,
)


@dataclass
class PlaylistEntry:
    """Ein Eintrag in der Playlist (nur im Speicher, nicht in DB)."""
    song: Song
    mode: str       # 'P' = Pattern, 'S' = Singing
    played: bool = False
    loop_count: int = 0   # 0 = Endlos (Standard), N = nach N Loops weiter
    # BL-164: Feinjustierung der Patter-Laenge. Anzahl Beats (ganze Phrasen),
    # die bei EINEM Loop-Durchlauf abgeschnitten werden, um naeher an die
    # gewuenschte Patter-Laenge zu kommen. 0 = kein Cut. Bewusst am Entry und
    # nicht am Song: die Ziel-Laenge variiert pro Lokation/Abend.
    loop_cut_beats: int = 0
    # BL-164: Zuletzt im Loop-Count-Dialog gewaehlte Wunschzeit (Minuten), damit
    # der Dialog beim Wiederoeffnen die vorige Wahl zeigt statt der Default-Zeit.
    # 0.0 = noch nie manuell gesetzt → Programm-Default verwenden.
    loop_target_min: float = 0.0


class _PoolTable(QTableWidget):
    """Song-Pool-Tabelle mit Drag-Support (sendet song_id als MIME)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.on_enter_pressed = None  # callback(row)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            row = self.currentRow()
            if row >= 0 and self.on_enter_pressed:
                self.on_enter_pressed(row)
            return
        super().keyPressEvent(event)

    def mimeData(self, items):
        md = QMimeData()
        row = self.currentRow()
        if row >= 0:
            item = self.item(row, 0)
            if item:
                song_id = item.data(Qt.UserRole)
                if song_id is not None:
                    md.setText(f"pool:{song_id}")
        return md


class _PlaylistTable(QTableWidget):
    """Playlist-Tabelle mit Drop-Support und internem Reorder per D&D."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.on_drop_song_id = None       # callback(song_id, target_row)
        self.on_reorder = None            # callback(from_row, to_row)
        self.on_enter_pressed = None      # callback(row)
        self.on_delete_pressed = None     # callback(row)
        self.on_col_double_click = None   # callback(row, col) — umgeht DragDrop-Signal-Timing

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            row = self.currentRow()
            if row >= 0 and self.on_enter_pressed:
                self.on_enter_pressed(row)
            return
        if event.key() in (Qt.Key_Delete, Qt.Key_Backspace):
            row = self.currentRow()
            if row >= 0 and self.on_delete_pressed:
                self.on_delete_pressed(row)
            return
        super().keyPressEvent(event)

    def dragEnterEvent(self, event):
        if event.mimeData().hasText():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if event.mimeData().hasText():
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event):
        text = event.mimeData().text() if event.mimeData().hasText() else ""
        target_row = self.indexAt(event.position().toPoint()).row()
        if target_row < 0:
            target_row = self.rowCount()

        if text.startswith("pool:"):
            try:
                song_id = int(text.split(":", 1)[1])
                if self.on_drop_song_id:
                    self.on_drop_song_id(song_id, target_row)
                event.acceptProposedAction()
            except (ValueError, IndexError):
                event.ignore()
        elif text.startswith("playlist:"):
            try:
                from_row = int(text.split(":", 1)[1])
                if from_row != target_row and self.on_reorder:
                    self.on_reorder(from_row, target_row)
                event.acceptProposedAction()
            except (ValueError, IndexError):
                event.ignore()
        else:
            event.ignore()

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton and self.on_col_double_click:
            index = self.indexAt(event.position().toPoint())
            if index.isValid():
                self.on_col_double_click(index.row(), index.column())
                event.accept()
                return
        super().mouseDoubleClickEvent(event)

    def mimeData(self, items):
        md = QMimeData()
        row = self.currentRow()
        if row >= 0:
            md.setText(f"playlist:{row}")
        return md


class PlaylistWidget(QWidget):
    """Schlanke Playlist-Ansicht: Liste der ausgewaehlten Songs.

    Zeigt die aktuelle Playlist mit Reihenfolge-Buttons, Laden/Speichern.
    Getabbt mit der Songliste — zur Laufzeit wechselt der Caller zwischen
    Songliste und Playlist.

    Besitzt das Datenmodell (_playlist, _current_index).
    Der PlaylistManagerWidget referenziert dieses Widget fuer Aenderungen.
    """

    def __init__(self, db: SongDatabase, paths: PathManager, parent=None):
        super().__init__(parent)
        self.db = db
        self.paths = paths
        self._playlist: list[PlaylistEntry] = []
        self._current_index: int = -1
        self._playing_id = None          # song_id des aktuell spielenden Songs (Now-Playing-Highlight)
        self._duration_cache: dict = {}  # {filename: seconds}

        # Callback: Song aus Playlist angeklickt -> vorladen
        self.on_playlist_song_selected = None
        # Callback: Playlist wurde geaendert -> Manager soll refreshen
        self.on_playlist_changed = None
        # Callback: Song aus Playlist in Notizen einfuegen (einzeln, Kontextmenue)
        self.on_add_to_notes = None  # callback(song_title)
        # Callback: mehrere Songs als Batch in Notizen einfuegen (+Notiz-Button)
        self.on_add_entries_to_notes = None  # callback(list[(title, mode)])
        # Callback: Quality/ERR via Kontextmenue geaendert
        self.on_song_rating_changed = None  # callback(song_id)

        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        self._label_count = QLabel(_t("playlist_count", count=0))
        self._label_count.setStyleSheet("font-size: 13px; font-weight: bold;")
        layout.addWidget(self._label_count)

        # Playlist Tabelle (mit D&D fuer Reorder)
        self._pl_table = _PlaylistTable()
        self._pl_table.setColumnCount(5)
        self._pl_table.setHorizontalHeaderLabels(["#", "P/S", _t("header_title"), "Loops", _t("header_duration")])
        self._pl_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self._pl_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self._pl_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self._pl_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self._pl_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self._pl_table.setSelectionBehavior(QTableWidget.SelectRows)
        # Mehrfachauswahl (Ctrl/Shift/Ziehen) — der +Notiz-Button uebertraegt
        # alle markierten Zeilen; ohne Markierung wird nach der ganzen Liste
        # gefragt (Issue #93).
        self._pl_table.setSelectionMode(QTableWidget.ExtendedSelection)
        self._pl_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._pl_table.verticalHeader().setVisible(False)
        self._pl_table.setDragEnabled(True)
        self._pl_table.setAcceptDrops(True)
        self._pl_table.setDropIndicatorShown(True)
        self._pl_table.setDragDropMode(QAbstractItemView.DragDrop)
        self._pl_table.on_reorder = self._on_dnd_reorder
        self._pl_table.on_col_double_click = self._on_pl_double_click
        self._pl_table.on_delete_pressed = self.remove_at
        self._pl_table.cellClicked.connect(self._on_pl_click)
        self._pl_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self._pl_table.customContextMenuRequested.connect(self._on_pl_context_menu)
        layout.addWidget(self._pl_table)

        # Buttons: Hoch/Runter/Loeschen + Laden/Speichern (bricht bei schmalen Docks um)
        _pl_btn_bar = _WrapButtonBar()
        self._btn_up = QPushButton("▲")
        self._btn_up.setFixedWidth(32)
        self._btn_up.setStyleSheet("font-size: 14px; padding: 0px;")
        self._btn_up.setToolTip(_t("tooltip_move_up"))
        self._btn_up.clicked.connect(self._on_move_up)
        _pl_btn_bar.add(self._btn_up)
        self._btn_down = QPushButton("▼")
        self._btn_down.setFixedWidth(32)
        self._btn_down.setStyleSheet("font-size: 14px; padding: 0px;")
        self._btn_down.setToolTip(_t("tooltip_move_down"))
        self._btn_down.clicked.connect(self._on_move_down)
        _pl_btn_bar.add(self._btn_down)
        self._btn_remove = QPushButton("✕")
        self._btn_remove.setFixedWidth(32)
        self._btn_remove.setStyleSheet("font-size: 14px; padding: 0px;")
        self._btn_remove.setToolTip(_t("tooltip_remove_from_playlist"))
        self._btn_remove.clicked.connect(self._on_remove_clicked)
        _pl_btn_bar.add(self._btn_remove)
        self._btn_pl_to_notes = QPushButton(_t("btn_to_notes"))
        self._btn_pl_to_notes.setToolTip(_t("btn_to_notes_tooltip_song"))
        self._btn_pl_to_notes.clicked.connect(self._on_to_notes_clicked)
        _pl_btn_bar.add(self._btn_pl_to_notes)
        self._btn_load = QPushButton(_t("btn_load"))
        self._btn_load.setToolTip(_t("tooltip_load_playlist"))
        self._btn_load.clicked.connect(self._on_load_playlist)
        _pl_btn_bar.add(self._btn_load)
        self._btn_save = QPushButton(_t("btn_save"))
        self._btn_save.setToolTip(_t("tooltip_save_playlist"))
        self._btn_save.clicked.connect(self._on_save_playlist)
        _pl_btn_bar.add(self._btn_save)
        # Summe rechtsbuendig in DERSELBEN Zeile wie die Buttons — spart die zweite
        # Zeile. Bei zu schmalem Dock bricht sie automatisch darunter um.
        self._label_total = QLabel("")
        self._label_total.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self._label_total.setStyleSheet("font-size: 12px; font-weight: bold;")
        _pl_btn_bar.add_trailing(self._label_total)
        self._pl_btn_bar = _pl_btn_bar
        layout.addWidget(_pl_btn_bar)

        # Entf-Taste: Shortcut auf Widget-Ebene, feuert bei jedem Kind-Fokus
        from PySide6.QtGui import QShortcut, QKeySequence
        del_sc = QShortcut(QKeySequence(Qt.Key_Delete), self)
        del_sc.setContext(Qt.WidgetWithChildrenShortcut)
        del_sc.activated.connect(self._on_remove_clicked)

    # ---- Dauer-Berechnung ----

    def _get_song_duration(self, song):
        """Song-Dauer aus Cache oder Datei lesen (inkl. Negative Cache)."""
        if song.filename in self._duration_cache:
            return self._duration_cache[song.filename]
        filepath = self.paths.find_song_file(song.filename)
        if filepath:
            try:
                import soundfile as sf
                info = sf.info(filepath)
                self._duration_cache[song.filename] = info.duration
                return info.duration
            except Exception:
                pass
        # Negative Cache: Datei nicht gefunden → 0.0 merken
        self._duration_cache[song.filename] = 0.0
        return 0.0

    def _calc_entry_duration(self, entry):
        """Berechnet die effektive Dauer eines Playlist-Eintrags (mit Loop-Count)."""
        dur = self._get_song_duration(entry.song)
        if dur <= 0:
            return 0.0
        if entry.loop_count <= 0:
            return dur  # Endlos: Gesamtdauer als Naehrung
        song = entry.song
        loop_in = song.loop_in
        loop_out = song.loop_out if song.loop_out > 0 else dur
        loop_dur = loop_out - loop_in
        if loop_dur <= 0:
            return dur
        pre_loop = loop_in
        post_loop = dur - loop_out
        result = pre_loop + entry.loop_count * loop_dur + post_loop
        # BL-164: Cut abziehen (nur bei loop_count>=2, konsistent mit der Engine)
        cut_beats = getattr(entry, 'loop_cut_beats', 0)
        bpm = song.base_bpm or 0.0
        if cut_beats > 0 and bpm > 0 and entry.loop_count >= 2:
            result -= cut_beats * 60.0 / bpm
        return result

    # ---- Playlist-Anzeige aktualisieren ----

    def refresh_display(self):
        """Aktualisiert die Tabelle aus den internen Daten."""
        _t0 = perf_start()
        self._pl_table.setUpdatesEnabled(False)
        self._pl_table.setRowCount(0)
        self._pl_table.setRowCount(len(self._playlist))
        total_secs = 0
        for idx, entry in enumerate(self._playlist):
            item_num = QTableWidgetItem(str(idx + 1))
            item_num.setTextAlignment(Qt.AlignCenter)
            self._pl_table.setItem(idx, 0, item_num)

            item_mode = QTableWidgetItem(entry.mode)
            item_mode.setTextAlignment(Qt.AlignCenter)
            self._pl_table.setItem(idx, 1, item_mode)

            display = entry.song.title or entry.song.filename
            item_title = QTableWidgetItem(display)
            self._pl_table.setItem(idx, 2, item_title)

            if entry.loop_count > 0:
                lc_text = str(entry.loop_count)
                if getattr(entry, 'loop_cut_beats', 0) > 0:
                    lc_text += " ✂"   # BL-164: Feinjustierung (Cut) aktiv
            elif entry.mode == 'S':
                lc_text = "1"
            else:
                lc_text = "∞"
            item_loops = QTableWidgetItem(lc_text)
            item_loops.setTextAlignment(Qt.AlignCenter)
            self._pl_table.setItem(idx, 3, item_loops)

            # Dauer-Spalte (inline mitsummieren)
            dur = self._calc_entry_duration(entry)
            total_secs += dur
            if dur > 0:
                mins, secs = divmod(int(dur), 60)
                item_dur = QTableWidgetItem(f"{mins}:{secs:02d}")
            else:
                item_dur = QTableWidgetItem("")
            item_dur.setTextAlignment(Qt.AlignCenter)
            self._pl_table.setItem(idx, 4, item_dur)

            # Gespielte Songs ausgrauen
            if entry.played:
                for col in range(5):
                    self._pl_table.item(idx, col).setForeground(Qt.gray)

            # Aktueller Song hervorheben (fett)
            if idx == self._current_index:
                font = item_title.font()
                font.setBold(True)
                for col in range(5):
                    self._pl_table.item(idx, col).setFont(font)

            # Aktuell SPIELENDER Song: Hintergrund-Highlight (folgt dem real
            # laufenden Song ueber die song_id — auch wenn er nicht per Klick
            # in der Playlist, sondern aus der Songliste gestartet wurde).
            if self._playing_id is not None and entry.song.id == self._playing_id:
                hl = self._pl_table.palette().color(QPalette.Highlight)
                hl.setAlpha(70)
                brush = QBrush(hl)
                for col in range(5):
                    self._pl_table.item(idx, col).setBackground(brush)

        self._pl_table.setUpdatesEnabled(True)
        self._label_count.setText(_t("playlist_count", count=len(self._playlist)))

        # Gesamtdauer anzeigen
        if total_secs > 0:
            t_mins, t_secs = divmod(int(total_secs), 60)
            t_hours, t_mins = divmod(t_mins, 60)
            if t_hours > 0:
                total_str = f"{t_hours}:{t_mins:02d}:{t_secs:02d}"
            else:
                total_str = f"{t_mins}:{t_secs:02d}"
            self._label_total.setText(_t("playlist_total", total=total_str))
        else:
            self._label_total.setText("")
        # Breite der Summe hat sich geaendert → Button-Leiste neu umbrechen, sonst
        # bleibt das rechtsbuendige Label auf seiner alten (leeren) Breite haengen.
        if hasattr(self, "_pl_btn_bar"):
            self._pl_btn_bar.relayout()
        perf_log(f"PlaylistWidget.refresh_display ({len(self._playlist)} entries)", _t0)

    # ---- Oeffentliche API (fuer Manager und MainWindow) ----

    def add_entry(self, entry: PlaylistEntry):
        """Fuegt einen Eintrag hinzu und aktualisiert die Anzeige."""
        self._playlist.append(entry)
        self.refresh_display()
        self._notify_changed()

    def add_entries_bulk(self, entries: list):
        """Fuegt mehrere Eintraege in einem Schritt hinzu (AR-002 Refresh-Storm-Fix).

        Im Gegensatz zu N× add_entry() ruft diese Methode refresh_display()
        und _notify_changed() nur EINMAL auf — egal wie viele Eintraege.
        Fuer den Playlist-Manager: _refresh_playlist_mirror() wird einmalig
        ueber den _notify_changed()-Callback ausgeloest.
        """
        if not entries:
            return
        self._playlist.extend(entries)
        self.refresh_display()
        self._notify_changed()

    def remove_at(self, index: int):
        """Entfernt einen Eintrag am Index und aktualisiert die Anzeige."""
        if index < 0 or index >= len(self._playlist):
            return
        if index < self._current_index:
            self._current_index -= 1
        elif index == self._current_index:
            self._current_index = -1
        self._playlist.pop(index)
        self.refresh_display()
        self._notify_changed()

    def get_playlist(self) -> list:
        return self._playlist

    def get_current_index(self) -> int:
        return self._current_index

    def set_playing_song(self, song_id):
        """Setzt den aktuell spielenden Song und aktualisiert das Highlight.

        Faerbt die betroffenen Zeilen direkt um (kein Tabellen-Neuaufbau),
        damit die Auswahl/der Fokus in der Playlist erhalten bleibt."""
        if song_id == self._playing_id:
            return
        self._playing_id = song_id
        self._apply_playing_highlight()

    def _apply_playing_highlight(self):
        """Setzt das Hintergrund-Highlight des spielenden Songs und raeumt alle
        anderen Zeilen ab (respektiert die Ausgrau-Farbe gespielter Eintraege)."""
        hl = self._pl_table.palette().color(QPalette.Highlight)
        hl.setAlpha(70)
        playing_brush = QBrush(hl)
        clear_brush = QBrush()
        for idx, entry in enumerate(self._playlist):
            is_playing = (self._playing_id is not None
                          and entry.song.id == self._playing_id)
            brush = playing_brush if is_playing else clear_brush
            for col in range(self._pl_table.columnCount()):
                it = self._pl_table.item(idx, col)
                if it is not None:
                    it.setBackground(brush)

    def _apply_current_highlight(self):
        """Setzt die Fett-Markierung des aktuellen Songs, ohne die Tabelle neu
        aufzubauen (analog _apply_playing_highlight). So bleiben Selektion und
        Fokus erhalten — kein setRowCount(0)/Item-Neuaufbau."""
        for idx in range(self._pl_table.rowCount()):
            it0 = self._pl_table.item(idx, 0)
            if it0 is None:
                continue
            font = it0.font()
            font.setBold(idx == self._current_index)
            for col in range(self._pl_table.columnCount()):
                it = self._pl_table.item(idx, col)
                if it is not None:
                    it.setFont(font)

    def get_current_entry(self):
        """Gibt den aktuell selektierten PlaylistEntry zurueck (oder None)."""
        if 0 <= self._current_index < len(self._playlist):
            return self._playlist[self._current_index]
        return None

    # Callback: Loop-Count-Edit angefragt -> MainWindow kuemmert sich
    on_loop_count_edit = None  # fn(row)

    def _on_pl_double_click(self, row, column):
        if column == 3:  # Loops-Spalte
            if self.on_loop_count_edit:
                self.on_loop_count_edit(row)
        # Andere Spalten: kein Double-Click-Verhalten in Playlist

    # ---- Klick -> Song vorladen ----

    def _on_pl_click(self, row, column):
        if row < 0 or row >= len(self._playlist):
            return
        entry = self._playlist[row]
        # Klick auf P/S-Spalte: Mode umschalten
        if column == 1:
            entry.mode = 'S' if entry.mode == 'P' else 'P'
            self.refresh_display()
            self._notify_changed()
            return
        self._current_index = row
        # Nur die Fett-Markierung inkrementell umsetzen — KEIN Tabellen-Neuaufbau,
        # damit die (Mehrfach-)Selektion und der Fokus erhalten bleiben. Ein voller
        # refresh_display() an dieser Stelle zerstoerte sonst die Auswahl und
        # lieferte currentRow() == -1 (Wurzel von Issue #93).
        self._apply_current_highlight()
        if self.on_playlist_song_selected:
            self.on_playlist_song_selected(entry)

    def _on_remove_clicked(self):
        row = self._pl_table.currentRow()
        if row < 0 or row >= len(self._playlist):
            return
        self.remove_at(row)

    def _on_to_notes_clicked(self):
        """+Notiz-Button: markierte Lieder in die Notizen uebernehmen. Ohne
        Markierung wird nachgefragt, ob die ganze Playlist uebernommen werden
        soll (Issue #93)."""
        if not self._playlist:
            return
        sm = self._pl_table.selectionModel()
        sel_rows = sorted({ix.row() for ix in sm.selectedRows()}) if sm else []
        sel_rows = [r for r in sel_rows if 0 <= r < len(self._playlist)]
        if not sel_rows:
            resp = QMessageBox.question(
                self,
                _t("pl_notes_export_title"),
                _t("pl_notes_all_question"),
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes,
            )
            if resp != QMessageBox.Yes:
                return
            sel_rows = list(range(len(self._playlist)))
        entries = [(self._playlist[r].song.title, self._playlist[r].mode)
                   for r in sel_rows]
        if self.on_add_entries_to_notes:
            self.on_add_entries_to_notes(entries)

    def _on_pl_context_menu(self, pos):
        item = self._pl_table.itemAt(pos)
        if not item:
            return
        row = self._pl_table.row(item)
        if row < 0 or row >= len(self._playlist):
            return
        song = self._playlist[row].song
        title = song.title
        menu = QMenu(self)
        act_remove = menu.addAction(_t("ctx_remove_from_playlist"))
        act_remove.triggered.connect(lambda: self.remove_at(row))
        menu.addSeparator()
        act_notes = menu.addAction(_t("ctx_add_to_notes"))
        act_notes.triggered.connect(
            lambda: self.on_add_to_notes(title) if self.on_add_to_notes else None)
        def _after_rating():
            self.refresh_display()
            if self.on_song_rating_changed:
                self.on_song_rating_changed(song.id)
        add_song_rating_actions(menu, self.db, song.id, refresh_callback=_after_rating)
        menu.exec(self._pl_table.viewport().mapToGlobal(pos))

    # ---- Reihenfolge ----

    def _on_move_up(self):
        row = self._pl_table.currentRow()
        if row <= 0 or row >= len(self._playlist):
            return
        self._playlist[row], self._playlist[row - 1] = (
            self._playlist[row - 1], self._playlist[row]
        )
        if self._current_index == row:
            self._current_index = row - 1
        elif self._current_index == row - 1:
            self._current_index = row
        self.refresh_display()
        self._pl_table.selectRow(row - 1)
        self._notify_changed()

    def _on_move_down(self):
        row = self._pl_table.currentRow()
        if row < 0 or row >= len(self._playlist) - 1:
            return
        self._playlist[row], self._playlist[row + 1] = (
            self._playlist[row + 1], self._playlist[row]
        )
        if self._current_index == row:
            self._current_index = row + 1
        elif self._current_index == row + 1:
            self._current_index = row
        self.refresh_display()
        self._pl_table.selectRow(row + 1)
        self._notify_changed()

    # ---- Drag & Drop Reorder ----

    def _on_dnd_reorder(self, from_row, to_row):
        """Wird aufgerufen wenn ein Playlist-Eintrag per D&D verschoben wird."""
        if from_row < 0 or from_row >= len(self._playlist):
            return
        if to_row < 0:
            to_row = 0
        if to_row >= len(self._playlist):
            to_row = len(self._playlist) - 1
        if from_row == to_row:
            return
        entry = self._playlist.pop(from_row)
        self._playlist.insert(to_row, entry)
        # Current-Index anpassen
        ci = self._current_index
        if ci == from_row:
            self._current_index = to_row
        elif from_row < ci <= to_row:
            self._current_index = ci - 1
        elif to_row <= ci < from_row:
            self._current_index = ci + 1
        self.refresh_display()
        self._pl_table.selectRow(to_row)
        self._notify_changed()

    # ---- Speichern / Laden ----

    def _on_save_playlist(self):
        if not self._playlist:
            QMessageBox.information(self, _t("dock_playlist"), _t("playlist_empty"))
            return
        pl_dir = self.paths.playlist_dir
        filepath, _ = QFileDialog.getSaveFileName(
            self, _t("dialog_save_playlist"), pl_dir,
            _t("filter_playlist_files")
        )
        if not filepath:
            return
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                for entry in self._playlist:
                    # BL-164: Cut nur anhaengen wenn gesetzt -> altes Format bleibt
                    # fuer Eintraege ohne Cut unveraendert (Rueckwaertskompatibilitaet)
                    cut = getattr(entry, 'loop_cut_beats', 0)
                    tok = f"{entry.loop_count}:{cut}" if cut > 0 else f"{entry.loop_count}"
                    f.write(f"{entry.mode} {tok} {entry.song.title}\n")
            print(f"[Playlist] Gespeichert: {filepath} ({len(self._playlist)} Songs)")
        except Exception as e:
            QMessageBox.warning(self, _t("error"), _t("save_failed", error=e))

    def _on_load_playlist(self):
        pl_dir = self.paths.playlist_dir
        filepath, _ = QFileDialog.getOpenFileName(
            self, _t("dialog_load_playlist"), pl_dir,
            _t("filter_playlist_files")
        )
        if not filepath:
            return
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                lines = f.readlines()
        except UnicodeDecodeError:
            with open(filepath, "r", encoding="cp1252") as f:
                lines = f.readlines()
        except Exception as e:
            QMessageBox.warning(self, _t("error"), _t("load_failed", error=e))
            return

        self._playlist.clear()
        self._current_index = -1
        not_found = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            parts = line.split(" ", 2)
            if len(parts) < 2:
                continue
            mode = parts[0].upper()
            if mode not in ('P', 'S'):
                mode = 'P'
            # Format: "MODE LOOPCOUNT FILENAME" oder "MODE FILENAME" (alt).
            # LOOPCOUNT ist "N" oder "N:CUT" (BL-164 Feinjustierung).
            loop_count = 0
            loop_cut = 0
            if len(parts) == 3 and re.fullmatch(r"\d+(:\d+)?", parts[1]):
                cnt = parts[1].split(":")
                loop_count = int(cnt[0])
                loop_cut = int(cnt[1]) if len(cnt) > 1 else 0
                filename = parts[2]
            elif len(parts) == 3:
                filename = parts[1] + " " + parts[2]
            else:
                filename = parts[1]
            # Suche: erst Titel (V1 + neu), dann Dateiname (V2-Uebergangsformat)
            song = self.db.get_by_title(filename) or self.db.get_by_filename(filename)
            if song:
                self._playlist.append(PlaylistEntry(
                    song=song, mode=mode, loop_count=loop_count,
                    loop_cut_beats=loop_cut))
            else:
                not_found.append(filename)

        self.refresh_display()
        self._notify_changed()
        if not_found:
            QMessageBox.warning(
                self, _t("warning"),
                _t("songs_not_found",
                   count=len(not_found),
                   names="\n".join(not_found[:10]))
            )
        print(f"[Playlist] Geladen: {filepath} ({len(self._playlist)} Songs, "
              f"{len(not_found)} nicht gefunden)")

    # ---- Auto-Advance (aufgerufen vom MainWindow) ----

    def get_next_unplayed_index(self) -> int:
        start = self._current_index + 1 if self._current_index >= 0 else 0
        for i in range(start, len(self._playlist)):
            if not self._playlist[i].played:
                return i
        return -1

    def mark_current_played(self):
        if 0 <= self._current_index < len(self._playlist):
            self._playlist[self._current_index].played = True
            self.refresh_display()
            self._notify_changed()

    def advance_to(self, index: int) -> PlaylistEntry:
        if 0 <= index < len(self._playlist):
            self._current_index = index
            self.refresh_display()
            self._notify_changed()
            return self._playlist[index]
        return None

    def has_active_playlist(self) -> bool:
        return len(self._playlist) > 0 and self._current_index >= 0

    def _notify_changed(self):
        if self.on_playlist_changed:
            self.on_playlist_changed()


class PlaylistManagerWidget(QWidget):
    """Zwei-Panel Playlisten-Manager: Song-Pool (links) + Playlist (rechts).

    Linke Seite: Alle Songs mit Filter (P/S/Alle) und Sortierung.
    Rechte Seite: Aktuelle Playlist mit Transfer-Buttons.
    Operiert auf dem Datenmodell des PlaylistWidget.
    """

    def __init__(self, db: SongDatabase, playlist_widget: PlaylistWidget, skin_mgr=None,
                 settings=None, parent=None):
        super().__init__(parent)
        self.db = db
        self._pw = playlist_widget  # Referenz auf das PlaylistWidget (besitzt die Daten)
        self._skin_mgr = skin_mgr
        self._settings = settings
        self._all_songs: list = []
        self._last_played_map: dict = {}
        self._genre_song_ids: dict = {}   # {genre_id: set(song_ids)}
        self._start_date: date = date.today()
        self._date_format = "de"
        self._needs_refresh = True  # Lazy: refresh erst beim Sichtbarwerden
        self._planned_tips: int = 0  # Vorgabe aus Lokation (0 = nicht gesetzt)
        # BL-085: liefert target_duration_min des aktiven Tanzprogramms (wird von P29MainWindow gesetzt)
        self.get_target_duration: callable = lambda: 7.0

        self._build_ui()
        self.update_skin()

    def update_skin(self, skin_mgr=None):
        """Icon-Farbe des Auto-Fill-Buttons aus dem aktuellen Skin setzen."""
        if skin_mgr:
            self._skin_mgr = skin_mgr
        sm = self._skin_mgr
        color = sm.color("button_text", "#ffffff") if sm else "#ffffff"
        self._btn_autofill.setIcon(_make_icon(_SVG_AUTOFILL, color))

    def _build_ui(self):
        outer = QHBoxLayout(self)
        outer.setContentsMargins(4, 4, 4, 4)

        splitter = QSplitter(Qt.Horizontal)
        self._splitter = splitter

        # ========== LINKE SEITE: Song-Pool ==========
        left_widget = QWidget()
        left = QVBoxLayout(left_widget)
        left.setContentsMargins(0, 0, 0, 0)

        # Gemeinsamer Filter-/Sortier-Header (BL-101 + BL-121)
        pl_dir = getattr(getattr(self._pw, "paths", None), "playlist_dir", "")
        self._filter_bar = SongFilterBar(
            show_genre=True, show_recommendation=True,
            show_custom_filter=True, db=self.db, pl_dir=pl_dir,
            settings=self._settings, parent=self)
        self._filter_bar.sig_changed.connect(self._refresh_pool)
        left.addWidget(self._filter_bar)

        # Song-Pool Tabelle (mit Drag-Support)
        self._pool_table = _PoolTable()
        self._pool_table.setColumnCount(3)
        self._pool_table.setHorizontalHeaderLabels([_t("header_title"), _t("header_played"), _t("header_q")])
        self._pool_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self._pool_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self._pool_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self._pool_table.setSelectionBehavior(QTableWidget.SelectRows)
        self._pool_table.setSelectionMode(QTableWidget.SingleSelection)
        self._pool_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._pool_table.verticalHeader().setVisible(False)
        self._pool_table.setDragEnabled(True)
        self._pool_table.setDragDropMode(QAbstractItemView.DragOnly)
        self._pool_table.cellDoubleClicked.connect(self._on_pool_double_click)
        self._pool_table.on_enter_pressed = self._on_pool_enter
        left.addWidget(self._pool_table)

        splitter.addWidget(left_widget)

        # ========== MITTE: Transfer-Buttons ==========
        mid_widget = QWidget()
        mid_widget.setFixedWidth(48)
        mid = QVBoxLayout(mid_widget)
        mid.setContentsMargins(0, 0, 0, 0)
        mid.addStretch()
        self._btn_add = QPushButton("▶")
        self._btn_add.setFixedSize(32, 32)
        self._btn_add.setStyleSheet("font-size: 16px; padding: 0px;")
        self._btn_add.setToolTip(_t("tooltip_add_to_playlist"))
        self._btn_add.clicked.connect(self._on_add_to_playlist)
        mid.addWidget(self._btn_add)
        self._btn_remove = QPushButton("◀")
        self._btn_remove.setFixedSize(32, 32)
        self._btn_remove.setStyleSheet("font-size: 16px; padding: 0px;")
        self._btn_remove.setToolTip(_t("tooltip_remove_from_playlist"))
        self._btn_remove.clicked.connect(self._on_remove_from_playlist)
        mid.addWidget(self._btn_remove)

        self._btn_autofill = QPushButton()
        self._btn_autofill.setFixedSize(32, 32)
        self._btn_autofill.setIconSize(QSize(18, 18))
        self._btn_autofill.setStyleSheet("padding: 0px;")
        self._btn_autofill.setToolTip(_t("tooltip_autofill"))
        self._btn_autofill.clicked.connect(self._on_auto_fill)
        mid.addWidget(self._btn_autofill)

        self._btn_clear = QPushButton("✖")
        self._btn_clear.setFixedSize(32, 32)
        self._btn_clear.setStyleSheet("font-size: 18px; font-weight: bold; padding: 0px; color: red;")
        self._btn_clear.setToolTip(_t("tooltip_clear_playlist"))
        self._btn_clear.clicked.connect(self._on_clear_playlist)
        mid.addWidget(self._btn_clear)

        self._btn_confirm = QPushButton("✔")
        self._btn_confirm.setFixedSize(32, 32)
        self._btn_confirm.setStyleSheet("font-size: 16px; padding: 0px;")
        self._btn_confirm.setProperty("confirm", True)
        self._btn_confirm.setToolTip(_t("tooltip_confirm_playlist"))
        self._btn_confirm.clicked.connect(self._on_confirm)
        mid.addWidget(self._btn_confirm)

        mid.addStretch()
        splitter.addWidget(mid_widget)

        # ========== RECHTE SEITE: Playlist-Spiegel (mit D&D) ==========
        right_widget = QWidget()
        right = QVBoxLayout(right_widget)
        right.setContentsMargins(0, 0, 0, 0)
        self._pl_table = _PlaylistTable()
        self._pl_table.setColumnCount(5)
        self._pl_table.setHorizontalHeaderLabels(["#", "P/S", _t("header_title"), "Loops", _t("header_duration")])
        self._pl_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self._pl_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self._pl_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self._pl_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self._pl_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self._pl_table.setSelectionBehavior(QTableWidget.SelectRows)
        self._pl_table.setSelectionMode(QTableWidget.SingleSelection)
        self._pl_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._pl_table.verticalHeader().setVisible(False)
        self._pl_table.setDragEnabled(True)
        self._pl_table.setAcceptDrops(True)
        self._pl_table.setDropIndicatorShown(True)
        self._pl_table.setDragDropMode(QAbstractItemView.DragDrop)
        self._pl_table.on_drop_song_id = self._on_drop_from_pool
        self._pl_table.on_reorder = self._on_dnd_reorder
        self._pl_table.on_col_double_click = self._on_pl_double_click
        self._pl_table.cellClicked.connect(self._on_pl_cell_click)
        self._pl_table.on_enter_pressed = self._on_pl_enter
        right.addWidget(self._pl_table)

        # Summen-Zeile
        self._label_pl_total = QLabel("")
        self._label_pl_total.setAlignment(Qt.AlignRight)
        self._label_pl_total.setStyleSheet("font-size: 12px; font-weight: bold; margin-top: 2px;")
        right.addWidget(self._label_pl_total)

        # Hoch/Runter + Laden/Speichern Buttons
        btn_row = QHBoxLayout()
        self._btn_up = QPushButton("▲")
        self._btn_up.setFixedSize(32, 32)
        self._btn_up.setStyleSheet("font-size: 16px; padding: 0px;")
        self._btn_up.setToolTip(_t("tooltip_move_up"))
        self._btn_up.clicked.connect(self._on_move_up)
        btn_row.addWidget(self._btn_up)
        self._btn_down = QPushButton("▼")
        self._btn_down.setFixedSize(32, 32)
        self._btn_down.setStyleSheet("font-size: 16px; padding: 0px;")
        self._btn_down.setToolTip(_t("tooltip_move_down"))
        self._btn_down.clicked.connect(self._on_move_down)
        btn_row.addWidget(self._btn_down)
        btn_row.addStretch()
        self._btn_load = QPushButton(_t("btn_load"))
        self._btn_load.setToolTip(_t("tooltip_load_playlist"))
        self._btn_load.clicked.connect(self._on_load_playlist)
        btn_row.addWidget(self._btn_load)
        self._btn_save = QPushButton(_t("btn_save"))
        self._btn_save.setToolTip(_t("tooltip_save_playlist"))
        self._btn_save.clicked.connect(self._on_save_playlist)
        btn_row.addWidget(self._btn_save)
        right.addLayout(btn_row)

        splitter.addWidget(right_widget)

        # Splitter-Proportionen: links 60%, mitte fix, rechts 40%
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 0)
        splitter.setStretchFactor(2, 2)
        outer.addWidget(splitter)

    # ---- Callbacks ----
    on_confirm = None  # Callback: Confirm-Button gedrueckt → Dock schliessen

    def _on_clear_playlist(self):
        """Gesamte Playlist loeschen — mit Rueckfrage."""
        if self._pl_table.rowCount() == 0:
            return
        reply = QMessageBox.question(
            self, _t("confirm_clear_playlist_title"),
            _t("confirm_clear_playlist_msg"),
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes:
            # Playlist im PlaylistWidget leeren (Single Source of Truth)
            self._pw._playlist.clear()
            self._pw._current_index = -1
            self._pw.refresh_display()
            self._pw._notify_changed()
            # Manager-Spiegel aktualisieren
            self._refresh_playlist_mirror()

    def _on_confirm(self):
        """Confirm-Button: Playlist uebernehmen und Manager-Dock schliessen."""
        if self.on_confirm:
            self.on_confirm()

    # ---- Daten setzen ----

    def set_start_date(self, d: date):
        self._start_date = d

    def set_date_format(self, fmt: str):
        self._date_format = fmt

    def set_last_played_map(self, lpm: dict):
        self._last_played_map = lpm
        if self.isVisible():
            self._refresh_pool()
        else:
            self._needs_refresh = True

    def refresh(self):
        """Laedt alle Songs aus DB und aktualisiert Pool + Playlist-Spiegel."""
        if not self.isVisible():
            self._needs_refresh = True
            return
        self._needs_refresh = False
        self._all_songs = self.db.get_all()
        self.refresh_genres()
        self._refresh_pool()
        self._refresh_playlist_mirror()

    def showEvent(self, event):
        super().showEvent(event)
        if self._needs_refresh:
            self.refresh()

    def refresh_genres(self):
        """Laedt Genres aus DB und aktualisiert Genre-Filter in der FilterBar."""
        self._genre_song_ids = self.db.get_genre_song_ids()
        genres = self.db.get_all_genres()
        current_id = self._filter_bar.genre_id
        self._filter_bar.set_genres(genres, current_id=current_id)


    def set_planned_tips(self, n: int):
        """Setzt die Tips-Voreinstellung aus der Lokation (0 = keine Vorgabe)."""
        self._planned_tips = n or 0

    def load_permanent_filters(self):
        """Weiterleitung an die FilterBar (BL-097: Permanente Custom-Filter laden)."""
        self._filter_bar.load_permanent_filters()

    # ---- Pool aktualisieren ----

    def _refresh_pool(self):
        # Filter + Sortierung via gemeinsame SongFilterBar (inkl. Custom-Filter BL-097)
        sorted_songs = self._filter_bar.filter_and_sort(
            self._all_songs, self._last_played_map,
            self._genre_song_ids, self._start_date)

        # Zweite Spalte wandert mit der Sortierung mit (wie in der Songliste):
        # Einfuegedatum / Empfehlungs-Score / Zuletzt-gespielt.
        sm = self._filter_bar.sort_mode
        role = ("added" if sm == SongFilterBar.SORT_DATE_ADDED
                else "score" if sm == SongFilterBar.SORT_RECOMMENDATION
                else "played")
        col1_head = {"added": _t("header_added"),
                     "score": _t("header_score")}.get(role, _t("header_played"))
        self._pool_table.setHorizontalHeaderLabels([
            _t("header_title"), col1_head, _t("header_q")])

        self._pool_table.setUpdatesEnabled(False)
        self._pool_table.setRowCount(0)
        self._pool_table.setRowCount(len(sorted_songs))
        for idx, song in enumerate(sorted_songs):
            display = song.title or song.filename
            type_tag = ""
            if song.is_pattern and song.is_singing:
                type_tag = "PS"
            elif song.is_pattern:
                type_tag = "P"
            elif song.is_singing:
                type_tag = "S"
            if type_tag:
                display += f"  ({type_tag})"
            if song.label:
                display += f"  [{song.label}]"

            inherited = False
            tooltip = ""
            if role == "added":
                if song.date_added:
                    cell_text = self._format_date(song.date_added)
                else:
                    cell_text = self._format_date(self._start_date.isoformat())
                    inherited = True
            elif role == "score":
                cell_text = str(_reco_score(song, self._last_played_map, self._start_date))
                tooltip = _t("tooltip_score_col")
            else:
                lp_str = self._last_played_map.get(song.id, "")
                cell_text = self._format_date(lp_str) if lp_str else ""

            item_title = QTableWidgetItem(display)
            item_title.setData(Qt.UserRole, song.id)
            self._pool_table.setItem(idx, 0, item_title)

            item_date = QTableWidgetItem(cell_text)
            item_date.setTextAlignment(Qt.AlignCenter)
            _style_date_cell(item_date, inherited)
            if tooltip:
                item_date.setToolTip(tooltip)
            self._pool_table.setItem(idx, 1, item_date)

            item_q = QTableWidgetItem(str(song.quality) if song.quality > 0 else "")
            item_q.setTextAlignment(Qt.AlignCenter)
            self._pool_table.setItem(idx, 2, item_q)
        self._pool_table.setUpdatesEnabled(True)

    def _format_date(self, iso_str: str) -> str:
        try:
            dt = datetime.fromisoformat(iso_str)
            if self._date_format == "us":
                return dt.strftime("%m/%d/%y")
            else:
                return dt.strftime("%d.%m.%y")
        except (ValueError, TypeError):
            return ""

    # ---- Playlist-Spiegel aktualisieren ----

    def _refresh_playlist_mirror(self):
        """Aktualisiert die rechte Playlist-Tabelle aus dem PlaylistWidget."""
        _t0 = perf_start()
        playlist = self._pw.get_playlist()
        current_idx = self._pw.get_current_index()

        self._pl_table.setUpdatesEnabled(False)
        self._pl_table.setRowCount(0)
        self._pl_table.setRowCount(len(playlist))
        total_secs = 0
        for idx, entry in enumerate(playlist):
            item_num = QTableWidgetItem(str(idx + 1))
            item_num.setTextAlignment(Qt.AlignCenter)
            self._pl_table.setItem(idx, 0, item_num)

            item_mode = QTableWidgetItem(entry.mode)
            item_mode.setTextAlignment(Qt.AlignCenter)
            self._pl_table.setItem(idx, 1, item_mode)

            display = entry.song.title or entry.song.filename
            item_title = QTableWidgetItem(display)
            self._pl_table.setItem(idx, 2, item_title)

            if entry.loop_count > 0:
                lc_text = str(entry.loop_count)
                if getattr(entry, 'loop_cut_beats', 0) > 0:
                    lc_text += " ✂"   # BL-164: Feinjustierung (Cut) aktiv
            elif entry.mode == 'S':
                lc_text = "1"
            else:
                lc_text = "∞"
            item_loops = QTableWidgetItem(lc_text)
            item_loops.setTextAlignment(Qt.AlignCenter)
            self._pl_table.setItem(idx, 3, item_loops)

            # Dauer-Spalte: bei Endlos-Loop (loop_count=0) Ziel-Patternlänge des Tanzprogramms nutzen
            if entry.loop_count <= 0 and entry.mode == 'P':
                dur = self.get_target_duration() * 60.0
            else:
                dur = self._pw._calc_entry_duration(entry)
            total_secs += dur
            if dur > 0:
                mins, secs = divmod(int(dur), 60)
                item_dur = QTableWidgetItem(f"{mins}:{secs:02d}")
            else:
                item_dur = QTableWidgetItem("")
            item_dur.setTextAlignment(Qt.AlignCenter)
            self._pl_table.setItem(idx, 4, item_dur)

            if entry.played:
                for col in range(5):
                    self._pl_table.item(idx, col).setForeground(Qt.gray)

            if idx == current_idx:
                font = item_title.font()
                font.setBold(True)
                for col in range(5):
                    self._pl_table.item(idx, col).setFont(font)
        self._pl_table.setUpdatesEnabled(True)
        if total_secs > 0:
            t_mins, t_secs = divmod(int(total_secs), 60)
            t_hours, t_mins = divmod(t_mins, 60)
            if t_hours > 0:
                total_str = f"{t_hours}:{t_mins:02d}:{t_secs:02d}"
            else:
                total_str = f"{t_mins}:{t_secs:02d}"
            self._label_pl_total.setText(_t("playlist_total", total=total_str))
        else:
            self._label_pl_total.setText("")
        perf_log(f"Planner._refresh_playlist_mirror ({len(playlist)} entries)", _t0)

    # ---- Mode-Erkennung ----

    def _determine_mode(self, song: Song) -> str:
        filter_id = self._filter_bar.type_filter
        if filter_id == 1:
            return 'P'
        elif filter_id == 2:
            return 'S'
        if song.is_pattern and not song.is_singing:
            return 'P'
        if song.is_singing and not song.is_pattern:
            return 'S'
        return 'P'

    def _make_entry(self, song, mode) -> "PlaylistEntry":
        """Zentrale Fabrik fuer NEU in den Planner kommende Songs (Button,
        Doppelklick, Drag&Drop, Auto-Fill) — wendet die Patter-Fuellung an.

        NICHT fuer das Laden gespeicherter Playlists verwenden: dort bleibt die
        gespeicherte Loop-Wahl erhalten.
        """
        entry = PlaylistEntry(song=song, mode=mode)
        self._apply_patter_fill(entry)
        return entry

    def _apply_patter_fill(self, entry) -> None:
        """BL-132+: Patter-Fill-Type 'target' → Patter auf die Programm-Ziellaenge
        optimieren. Default 'infinite' laesst den Patter endlos (loop_count=0).
        Singing-Calls (mode 'S') bleiben immer unberuehrt.
        """
        if entry.mode != 'P':
            return
        fill_type = "infinite"
        if self._settings is not None:
            fill_type = str(self._settings.value(
                "playlist/patter_fill_type", "infinite"))
        if fill_type != "target":
            return
        song = entry.song
        dur = self._pw._get_song_duration(song)
        if dur <= 0:
            return
        # Loop-Grenzen wie im Dialog/_calc_entry_duration robust bestimmen
        loop_in = song.loop_in or 0.0
        loop_out = song.loop_out if (song.loop_out or 0) > 0 else dur
        if loop_out - loop_in <= 0:
            return  # kein gueltiger Loop → bleibt endlos
        desired = self.get_target_duration() * 60.0
        loop_count, cut_beats = calc_auto_loop(
            loop_in, loop_out, dur,
            float(getattr(song, 'base_bpm', 0) or 0), desired)
        entry.loop_count = loop_count
        entry.loop_cut_beats = cut_beats
        entry.loop_target_min = self.get_target_duration()

    # ---- Transfer-Aktionen ----

    def _on_add_to_playlist(self):
        row = self._pool_table.currentRow()
        if row < 0:
            return
        song_id = self._pool_table.item(row, 0).data(Qt.UserRole)
        song = self.db.get_by_id(song_id)
        if song:
            mode = self._determine_mode(song)
            self._pw.add_entry(self._make_entry(song, mode))
            self._refresh_playlist_mirror()

    def _on_remove_from_playlist(self):
        row = self._pl_table.currentRow()
        if row < 0:
            return
        self._pw.remove_at(row)
        self._refresh_playlist_mirror()

    def _on_pool_double_click(self, row, column):
        self._add_pool_song(row)

    def _on_pool_enter(self, row):
        self._add_pool_song(row)

    def _add_pool_song(self, row):
        """Fuegt Song aus Pool-Zeile in die Playlist ein."""
        item = self._pool_table.item(row, 0)
        if not item:
            return
        song_id = item.data(Qt.UserRole)
        song = self.db.get_by_id(song_id)
        if song:
            mode = self._determine_mode(song)
            self._pw.add_entry(self._make_entry(song, mode))
            self._refresh_playlist_mirror()

    def _on_pl_cell_click(self, row, column):
        """Klick auf P/S-Spalte in der Planner-Playlist: Mode umschalten."""
        if column != 1:
            return
        playlist = self._pw.get_playlist()
        if row < 0 or row >= len(playlist):
            return
        entry = playlist[row]
        entry.mode = 'S' if entry.mode == 'P' else 'P'
        self._pw.refresh_display()
        self._refresh_playlist_mirror()

    def _on_pl_double_click(self, row, column):
        if column == 3:
            self._on_loop_count_edit(row)
        else:
            self._remove_pl_song(row)

    def _on_pl_enter(self, row):
        self._remove_pl_song(row)

    def _on_loop_count_edit(self, row):
        """Dialog: Loop-Anzahl per Zeitvorgabe oder manuell setzen."""
        playlist = self._pw.get_playlist()
        if row < 0 or row >= len(playlist):
            return
        entry = playlist[row]
        # TIC-0019: Loop-Daten frisch aus DB lesen (koennen per Rule seit dem Hinzufuegen geaendert worden sein)
        if entry.song.id is not None:
            fresh = self.db.get_by_id(entry.song.id)
            if fresh:
                entry.song = fresh
        result = show_loop_count_dialog(
            self, entry.song, self._pw.paths,
            default_minutes=self.get_target_duration(),
            current_count=entry.loop_count,
            current_cut=entry.loop_cut_beats,
            current_target_min=entry.loop_target_min,
        )
        if result is not None:
            entry.loop_count, entry.loop_cut_beats, entry.loop_target_min = result
            self._pw.refresh_display()
            self._refresh_playlist_mirror()

    def _remove_pl_song(self, row):
        """Entfernt Song an Position row aus der Playlist."""
        if row < 0:
            return
        self._pw.remove_at(row)
        self._refresh_playlist_mirror()

    # ---- Drag & Drop Callbacks ----

    def _on_drop_from_pool(self, song_id, target_row):
        """Song per D&D aus Pool in die Playlist gedroppt."""
        song = self.db.get_by_id(song_id)
        if song:
            mode = self._determine_mode(song)
            entry = self._make_entry(song, mode)
            playlist = self._pw.get_playlist()
            if target_row >= len(playlist):
                self._pw.add_entry(entry)
            else:
                playlist.insert(target_row, entry)
                self._pw.refresh_display()
                self._pw._notify_changed()
            self._refresh_playlist_mirror()

    def _on_dnd_reorder(self, from_row, to_row):
        """Playlist-Eintrag per D&D umsortiert."""
        playlist = self._pw.get_playlist()
        if from_row < 0 or from_row >= len(playlist):
            return
        if to_row < 0:
            to_row = 0
        if to_row >= len(playlist):
            to_row = len(playlist) - 1
        if from_row == to_row:
            return
        entry = playlist.pop(from_row)
        playlist.insert(to_row, entry)
        ci = self._pw.get_current_index()
        if ci == from_row:
            self._pw._current_index = to_row
        elif from_row < ci <= to_row:
            self._pw._current_index = ci - 1
        elif to_row <= ci < from_row:
            self._pw._current_index = ci + 1
        self._pw.refresh_display()
        self._pw._notify_changed()
        self._refresh_playlist_mirror()
        self._pl_table.selectRow(to_row)

    # ---- Reihenfolge (im Manager) ----

    def _on_move_up(self):
        row = self._pl_table.currentRow()
        playlist = self._pw.get_playlist()
        if row <= 0 or row >= len(playlist):
            return
        playlist[row], playlist[row - 1] = playlist[row - 1], playlist[row]
        ci = self._pw.get_current_index()
        if ci == row:
            self._pw._current_index = row - 1
        elif ci == row - 1:
            self._pw._current_index = row
        self._pw.refresh_display()
        self._refresh_playlist_mirror()
        self._pl_table.selectRow(row - 1)

    def _on_move_down(self):
        row = self._pl_table.currentRow()
        playlist = self._pw.get_playlist()
        if row < 0 or row >= len(playlist) - 1:
            return
        playlist[row], playlist[row + 1] = playlist[row + 1], playlist[row]
        ci = self._pw.get_current_index()
        if ci == row:
            self._pw._current_index = row + 1
        elif ci == row + 1:
            self._pw._current_index = row
        self._pw.refresh_display()
        self._refresh_playlist_mirror()
        self._pl_table.selectRow(row + 1)

    # ---- Laden/Speichern (delegiert an PlaylistWidget) ----

    def _on_save_playlist(self):
        self._pw._on_save_playlist()
        self._refresh_playlist_mirror()

    def _on_load_playlist(self):
        self._pw._on_load_playlist()
        self._refresh_playlist_mirror()

    def _on_auto_fill(self):
        """Auto-Fill: Playlist automatisch anhand von Tipps-Anzahl und Strategie befüllen."""
        dlg = QDialog(self)
        dlg.setWindowTitle(_t("autofill_title"))
        dlg.setMinimumWidth(320)
        layout = QVBoxLayout(dlg)

        form = QFormLayout()
        spin_tipps = QSpinBox()
        spin_tipps.setRange(1, 50)
        spin_tipps.setValue(self._planned_tips if self._planned_tips > 0 else 8)
        form.addRow(_t("autofill_tipps"), spin_tipps)

        combo_strategy = QComboBox()
        combo_strategy.addItem(_t("autofill_s1"), 1)
        combo_strategy.addItem(_t("autofill_s2"), 2)
        combo_strategy.addItem(_t("autofill_s3"), 3)
        combo_strategy.addItem(_t("autofill_s4"), 4)
        form.addRow(_t("autofill_strategy"), combo_strategy)
        layout.addLayout(form)

        btn_row = QHBoxLayout()
        btn_ok = QPushButton(_t("btn_ok"))
        btn_ok.setDefault(True)
        btn_cancel = QPushButton(_t("btn_cancel"))
        btn_ok.clicked.connect(dlg.accept)
        btn_cancel.clicked.connect(dlg.reject)
        btn_row.addStretch()
        btn_row.addWidget(btn_ok)
        btn_row.addWidget(btn_cancel)
        layout.addLayout(btn_row)

        if dlg.exec() != QDialog.Accepted:
            return

        n = spin_tipps.value()
        strategy = combo_strategy.currentData()

        # Bei Zufalls-Sortierung vor jedem Auto-Fill neu mischen: sonst liefert
        # der Ziehungs-Cache bei jedem Klick dieselbe Playlist.
        self._filter_bar.reshuffle_random()

        sorted_songs = self._filter_bar.filter_and_sort(
            self._all_songs, self._last_played_map,
            self._genre_song_ids, self._start_date)
        existing_ids = {e.song.id for e in self._pw.get_playlist()}

        def next_song(is_pattern=None, is_singing=None, used=None):
            for s in sorted_songs:
                if s.id in existing_ids:
                    continue
                if used is not None and s.id in used:
                    continue
                if is_pattern and not s.is_pattern:
                    continue
                if is_singing and not s.is_singing:
                    continue
                return s
            return None

        used = set()
        to_add = []  # Liste von (song, mode)

        def add_p(song):
            to_add.append((song, 'P')); used.add(song.id)

        def add_s(song):
            to_add.append((song, 'S')); used.add(song.id)

        if strategy == 1:
            for _ in range(n):
                p = next_song(is_pattern=True, used=used)
                if p: add_p(p)
                s = next_song(is_singing=True, used=used)
                if s: add_s(s)

        elif strategy == 2:
            p = next_song(is_pattern=True, used=used)
            if p: add_p(p)
            s = next_song(is_singing=True, used=used)
            if s: add_s(s)
            for _ in range(max(0, n - 2)):
                p = next_song(is_pattern=True, used=used)
                if p: add_p(p)
            p = next_song(is_pattern=True, used=used)
            if p: add_p(p)
            s = next_song(is_singing=True, used=used)
            if s: add_s(s)

        elif strategy == 3:
            for _ in range(n):
                p = next_song(is_pattern=True, used=used)
                if p: add_p(p)

        elif strategy == 4:
            for _ in range(n):
                s = next_song(is_singing=True, used=used)
                if s: add_s(s)

        # AR-002 Fix: Bulk-Add statt N× add_entry() — nur 1× refresh_display +
        # 1× _refresh_playlist_mirror (via _notify_changed im Bulk-Add).
        self._pw.add_entries_bulk(
            [self._make_entry(song, mode) for song, mode in to_add]
        )
        print(f"[Auto-Fill] Strategie {strategy}, {n} Tipps → {len(to_add)} Songs")
