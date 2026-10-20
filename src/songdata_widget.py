"""Song-Daten-, Filter- und Listen-UI (BL-201, Stufe 7, aus main.py).

SongDataWidget (Metadaten-Editor), SongFilterBar, SongListWidget,
SongPropertiesDialog + Helfer-Dialoge sowie BpmWorker/FeedbackDialog.
Zirkelfrei: keine Rueckbezuege auf main.py.
"""

import os
import re
import random
from datetime import date, datetime

from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QPushButton, QLabel, QFileDialog,
    QFrame, QCheckBox, QLineEdit, QSpinBox, QDoubleSpinBox, QAbstractSpinBox,
    QFormLayout, QListWidget, QListWidgetItem, QTableWidget, QTableWidgetItem,
    QHeaderView, QComboBox, QMessageBox, QDialog, QDialogButtonBox,
    QInputDialog, QMenu, QAbstractItemView, QRadioButton, QButtonGroup,
    QTextEdit, QSizePolicy, QScrollArea, QTabWidget,
)
from PySide6.QtCore import Qt, QThread, Signal, QEvent
from PySide6.QtGui import QColor

from song_db import SongDatabase, Song, SONG_PROPERTY_KEYS
import song_types
from path_manager import PathManager
from i18n import _t
import song_data_io
import lyrics_files
from dialogs_lyrics_conflict import ask_lyrics_conflict
from perf import perf_start, perf_split, perf_log
from stats_widget import add_song_rating_actions
from ui_helpers import (
    fmt_time, fmt_precise, _make_icon, _clear_layout, parse_time_offset,
    _SVG_PENCIL, _SVG_CLOCK, _SVG_REMOVE_X, _WrapButtonBar, _UNRATED_QUALITY,
    _reco_days_since, _reco_score, _weighted_random_order, _style_date_cell,
)


class BpmWorker(QThread):
    """Worker-Thread fuer BPM-Erkennung (blockiert UI nicht)."""
    # TIC-0029: eigenes Signal NICHT 'finished' nennen — das wuerde das eingebaute
    # QThread.finished ueberschatten (das echte Thread-Ende signalisiert). 'done'
    # meldet "fachlich fertig", QThread.finished bleibt fuer sicheres Cleanup frei.
    done = Signal(float)       # Erkannte BPM
    error = Signal(str)        # Fehlermeldung

    def __init__(self, filepath: str):
        super().__init__()
        self._filepath = filepath

    def run(self):
        try:
            # Lazy-Import: bpm_detector zieht scipy (~1s Ladezeit). Nur laden,
            # wenn wirklich eine BPM-Messung startet — nicht beim App-Start.
            from bpm_detector import detect_bpm
            bpm = detect_bpm(self._filepath)
            self.done.emit(bpm)
        except Exception as e:
            self.error.emit(str(e))


class FeedbackDialog(QDialog):
    """Feedback-Dialog nach Songende: Quality und ERR bewerten (BL-119)."""

    # ERR-Reihenfolge: links = schwächste Reaktion, rechts = stärkste
    _ERR_ORDER = [0, 4, 3, 2, 1]
    # Gleiche Farben wie Evening Planner (_ERR_COL)
    _ERR_COLORS = {
        0: QColor("#808080"),
        1: QColor("#d9441c"),
        2: QColor("#c8901a"),
        3: QColor("#2e8b3e"),
        4: QColor("#2a5bbf"),
    }

    @staticmethod
    def _quality_color(val: int) -> QColor:
        """Gradient: 0=fast weiss, 10=Waldgruen (H=120, Saettigung steigt linear)."""
        t = val / 10.0
        sat = int(t * 205)       # 0 (weiss) → 205 (sattes Gruen)
        vsv = int(245 - t * 90)  # 245 (hell) → 155 (dunkel)
        return QColor.fromHsv(120, sat, vsv)

    @staticmethod
    def _btn_style(color: QColor, selected: bool) -> str:
        """Button-Style mit adaptiver Textfarbe (hell/dunkel je nach Hintergrund)."""
        if selected:
            bg = color.lighter(125)
            border = color.darker(140).name()
            extra = f"border: 3px solid {border}; font-weight: bold;"
        else:
            bg = color.darker(115)
            extra = "border: 1px solid rgba(0,0,0,60);"
        # Lesbarkeit: dunkler Text auf hellem Hintergrund, weiss auf dunklem
        lum = 0.299 * bg.red() + 0.587 * bg.green() + 0.114 * bg.blue()
        text = "white" if lum < 155 else "#222222"
        return (f"QPushButton {{ background-color: {bg.name()}; color: {text}; "
                f"border-radius: 4px; {extra} }}")

    def __init__(self, song, parent=None, location_id=None):
        super().__init__(parent)
        self.setWindowTitle(_t("feedback_dialog_title"))
        self.setModal(True)
        self.setMinimumWidth(480)
        self._song = song
        self._quality = song.quality
        self._err = song.err
        self._location_id = location_id
        # Listen von (QPushButton, QColor) bzw. (QPushButton, err_val, QColor)
        self._quality_btns = []
        self._err_btns = []
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        title_lbl = QLabel(f"<b>{self._song.title or self._song.filename}</b>")
        title_lbl.setAlignment(Qt.AlignCenter)
        layout.addWidget(title_lbl)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setFrameShadow(QFrame.Sunken)
        layout.addWidget(sep)

        # --- Quality ---
        q_lbl = QLabel(_t("feedback_quality_question"))
        q_lbl.setWordWrap(True)
        layout.addWidget(q_lbl)

        q_row = QHBoxLayout()
        q_row.setSpacing(3)
        for v in range(11):  # 0..10
            col = self._quality_color(v)
            btn = QPushButton(str(v))
            btn.setFixedHeight(30)
            btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            btn.setStyleSheet(self._btn_style(col, v == self._quality))
            btn.clicked.connect(lambda _c, val=v: self._set_quality(val))
            self._quality_btns.append((btn, col))
            q_row.addWidget(btn, 1)
        layout.addLayout(q_row)

        layout.addSpacing(6)

        # --- ERR ---
        e_lbl = QLabel(_t("feedback_err_question"))
        e_lbl.setWordWrap(True)
        layout.addWidget(e_lbl)

        e_row = QHBoxLayout()
        e_row.setSpacing(3)
        for v in self._ERR_ORDER:
            col = self._ERR_COLORS[v]
            btn = QPushButton(str(v))
            btn.setFixedHeight(30)
            btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            btn.setStyleSheet(self._btn_style(col, v == self._err))
            btn.setToolTip(_t(f"err_{v}"))
            btn.clicked.connect(lambda _c, val=v: self._set_err(val))
            self._err_btns.append((btn, v, col))
            e_row.addWidget(btn, 1)
        layout.addLayout(e_row)

        layout.addSpacing(4)

        # --- Notizen für die Zukunft ---
        sep2 = QFrame()
        sep2.setFrameShape(QFrame.HLine)
        sep2.setFrameShadow(QFrame.Sunken)
        layout.addWidget(sep2)

        note_lbl = QLabel(_t("feedback_note_label"))
        note_lbl.setWordWrap(True)
        layout.addWidget(note_lbl)

        self._note_edit = QTextEdit()
        self._note_edit.setFixedHeight(70)
        if self._location_id is None:
            self._note_edit.setEnabled(False)
            self._note_edit.setPlaceholderText(_t("feedback_note_placeholder_no_location"))
        else:
            self._note_edit.setPlaceholderText(_t("feedback_note_placeholder"))
        layout.addWidget(self._note_edit)

        layout.addSpacing(4)

        # Session-Suppression: bei Haken wird das Feedback-Fenster fuer den
        # Rest der Sitzung unterdrueckt (unabhaengig von Accept/Cancel).
        # Der INI-Standard bleibt unveraendert und greift beim naechsten Start.
        self._chk_suppress_session = QCheckBox(_t("feedback_suppress_session"))
        layout.addWidget(self._chk_suppress_session)

        layout.addSpacing(4)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_accept = QPushButton(_t("feedback_btn_accept"))
        btn_accept.setDefault(True)
        btn_cancel = QPushButton(_t("btn_cancel"))
        btn_accept.clicked.connect(self.accept)
        btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(btn_accept)
        btn_row.addWidget(btn_cancel)
        layout.addLayout(btn_row)

    def _set_quality(self, val):
        self._quality = val
        for i, (btn, col) in enumerate(self._quality_btns):
            btn.setStyleSheet(self._btn_style(col, i == val))

    def _set_err(self, val):
        self._err = val
        for btn, err_val, col in self._err_btns:
            btn.setStyleSheet(self._btn_style(col, err_val == val))

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape:
            self.reject()
            return
        super().keyPressEvent(e)

    @property
    def quality(self):
        return self._quality

    @property
    def err(self):
        return self._err

    @property
    def note_text(self) -> str:
        return self._note_edit.toPlainText().strip()

    @property
    def suppress_session(self) -> bool:
        return self._chk_suppress_session.isChecked()


class _AddVariantDialog(QDialog):
    """Mini-Dialog zum Hinzufuegen einer Music- oder Lyric-Variante."""

    def __init__(self, kind: str, paths, parent=None):
        super().__init__(parent)
        self._kind = kind
        self._paths = paths
        title = _t("dlg_add_variant_title_music") if kind == "music" else _t("dlg_add_variant_title_lyric")
        self.setWindowTitle(title)
        self.setMinimumWidth(380)
        self.name = ""
        self.filename = ""
        self._build_ui()

    def _build_ui(self):
        outer = QVBoxLayout(self)
        form = QFormLayout()

        self.edit_name = QLineEdit()
        self.edit_name.setPlaceholderText(_t("placeholder_variant_name"))
        form.addRow(_t("dlg_variant_name"), self.edit_name)

        file_widget = QWidget()
        file_row = QHBoxLayout(file_widget)
        file_row.setContentsMargins(0, 0, 0, 0)
        self.edit_file = QLineEdit()
        self.edit_file.setReadOnly(True)
        self.edit_file.textChanged.connect(self._update_ok)
        file_row.addWidget(self.edit_file)
        btn_browse = QPushButton("...")
        btn_browse.setObjectName("fileBtn")
        btn_browse.setFixedWidth(30)
        btn_browse.clicked.connect(self._browse)
        file_row.addWidget(btn_browse)
        form.addRow(_t("dlg_variant_file"), file_widget)

        outer.addLayout(form)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self.btn_ok = QPushButton(_t("btn_ok"))
        self.btn_ok.setDefault(True)
        self.btn_ok.setEnabled(False)
        btn_cancel = QPushButton(_t("btn_cancel"))
        self.btn_ok.clicked.connect(self._accept)
        btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(self.btn_ok)
        btn_row.addWidget(btn_cancel)
        outer.addLayout(btn_row)

    def _update_ok(self):
        self.btn_ok.setEnabled(bool(self.edit_file.text().strip()))

    def _browse(self):
        if self._kind == "music":
            start_dir = self._paths.music_dir if self._paths else os.path.expanduser("~")
            filepath, _ = QFileDialog.getOpenFileName(
                self, _t("dialog_select_audio"), start_dir, _t("filter_audio_files")
            )
            if filepath:
                fname = self._paths.to_relative_filename(filepath) \
                    if self._paths else os.path.basename(filepath)
                self.edit_file.setText(fname)
        else:
            start_dir = self._paths.lyrics_dir if self._paths else os.path.expanduser("~")
            filepath, _ = QFileDialog.getOpenFileName(
                self, _t("dialog_select_lyrics"), start_dir, _t("filter_lyrics_files")
            )
            if filepath:
                fname = self._paths.to_relative_lyric_filename(filepath) \
                    if self._paths else os.path.basename(filepath)
                self.edit_file.setText(fname)

    def _accept(self):
        self.name = self.edit_name.text().strip()
        self.filename = self.edit_file.text().strip()
        self.accept()


class _GenreEditDialog(QDialog):
    """Dialog zum Bearbeiten der Genres eines einzelnen Songs (Checkbox-Liste)."""

    def __init__(self, db, song_id: int, parent=None):
        super().__init__(parent)
        self.db = db
        self.song_id = song_id
        self.setWindowTitle(_t("genre_edit_title"))
        self.setMinimumWidth(320)
        self.setMinimumHeight(420)

        layout = QVBoxLayout(self)

        lbl = QLabel(_t("genre_edit_hint"))
        lbl.setWordWrap(True)
        layout.addWidget(lbl)

        self._list = QListWidget()
        self._list.setSelectionMode(QAbstractItemView.NoSelection)
        all_genres = db.get_all_genres()
        current_ids = {gid for gid, _ in db.get_genres_for_song(song_id)}
        for gid, gname in all_genres:
            item = QListWidgetItem(gname)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if gid in current_ids else Qt.Unchecked)
            item.setData(Qt.UserRole, gid)
            self._list.addItem(item)
        layout.addWidget(self._list)

        # Neues Genre on-the-fly anlegen
        new_row = QHBoxLayout()
        new_row.addWidget(QLabel(_t("genre_add_new")))
        self._edit_new = QLineEdit()
        self._edit_new.setPlaceholderText(_t("genre_add_placeholder"))
        self._edit_new.returnPressed.connect(self._add_new_genre)
        new_row.addWidget(self._edit_new, 1)
        btn_plus = QPushButton("+")
        btn_plus.setFixedWidth(28)
        btn_plus.clicked.connect(self._add_new_genre)
        new_row.addWidget(btn_plus)
        layout.addLayout(new_row)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def _add_new_genre(self):
        name = self._edit_new.text().strip()
        if not name:
            return
        # Bereits in Liste? Dann nur aktivieren
        for i in range(self._list.count()):
            item = self._list.item(i)
            if item.text().lower() == name.lower():
                item.setCheckState(Qt.Checked)
                self._edit_new.clear()
                return
        # Neu anlegen
        gid = self.db.insert_genre(name)
        item = QListWidgetItem(name)
        item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
        item.setCheckState(Qt.Checked)
        item.setData(Qt.UserRole, gid)
        self._list.addItem(item)
        self._edit_new.clear()

    def selected_genre_ids(self) -> list:
        result = []
        for i in range(self._list.count()):
            item = self._list.item(i)
            if item.checkState() == Qt.Checked:
                result.append(item.data(Qt.UserRole))
        return result


class CustomFilterDialog(QDialog):
    """Dialog fuer Custom-Playlist-Filter (bis zu 4 Playlisten als Whitelist).

    Zeigt 4 feste Slots; jeder kann mit einer Playlist-Datei belegt werden.
    Die Vorschau-Tabelle zeigt die Schnittmenge aller geladenen Slots.
    """

    MAX_SLOTS = 4

    def __init__(self, db, playlist_dir, initial_slots, permanent_state=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(_t("custom_filter_dlg_title"))
        self.setMinimumSize(480, 540)
        self._db = db
        self._playlist_dir = str(playlist_dir) if playlist_dir else ""
        # _slots: liste von {'name': str, 'song_ids': frozenset, 'filepath': str} oder None
        self._slots = [None] * self.MAX_SLOTS
        for i, s in enumerate(initial_slots):
            if i < self.MAX_SLOTS:
                self._slots[i] = s
        self._slot_filepath: list = [None] * self.MAX_SLOTS
        if initial_slots:
            for i, s in enumerate(initial_slots):
                if i < self.MAX_SLOTS and s is not None:
                    self._slot_filepath[i] = s.get("filepath")
        self._initial_permanent = list(permanent_state) if permanent_state else [False] * self.MAX_SLOTS
        self._build_ui()
        self._update_slot_ui()
        self._refresh_preview()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(6)

        lbl_hint = QLabel(_t("custom_filter_dlg_hint"))
        lbl_hint.setWordWrap(True)
        lbl_hint.setStyleSheet("font-size: 11px; color: gray;")
        layout.addWidget(lbl_hint)

        # Slot-Reihen
        slots_frame = QFrame()
        slots_frame.setFrameShape(QFrame.StyledPanel)
        slots_layout = QVBoxLayout(slots_frame)
        slots_layout.setSpacing(4)
        self._slot_name_labels = []
        self._slot_btn_remove = []
        self._slot_btn_permanent = []
        for i in range(self.MAX_SLOTS):
            row = QHBoxLayout()
            lbl_num = QLabel(f"{i + 1}.")
            lbl_num.setFixedWidth(18)
            row.addWidget(lbl_num)

            lbl_name = QLabel(_t("custom_slot_empty"))
            lbl_name.setMinimumWidth(180)
            lbl_name.setCursor(Qt.PointingHandCursor)
            lbl_name.installEventFilter(self)
            self._slot_name_labels.append(lbl_name)
            row.addWidget(lbl_name, 1)

            btn_load = QPushButton(_t("btn_load"))
            btn_load.clicked.connect(lambda _checked, idx=i: self._load_slot(idx))
            row.addWidget(btn_load)

            btn_remove = QPushButton(_t("btn_remove_playlist"))
            btn_remove.setEnabled(False)
            btn_remove.clicked.connect(lambda _checked, idx=i: self._remove_slot(idx))
            self._slot_btn_remove.append(btn_remove)
            row.addWidget(btn_remove)

            btn_perm = QPushButton(_t("btn_permanent"))
            btn_perm.setCheckable(True)
            btn_perm.setChecked(self._initial_permanent[i])
            btn_perm.setEnabled(False)
            btn_perm.setToolTip(_t("tooltip_permanent"))
            self._slot_btn_permanent.append(btn_perm)
            row.addWidget(btn_perm)

            slots_layout.addLayout(row)

        layout.addWidget(slots_frame)

        # Vorschau-Label
        self._lbl_preview = QLabel(_t("custom_filter_preview_loading"))
        self._lbl_preview.setStyleSheet("font-size: 11px; font-weight: bold;")
        layout.addWidget(self._lbl_preview)

        # Vorschau-Tabelle
        self._preview_table = QTableWidget()
        self._preview_table.setColumnCount(1)
        self._preview_table.setHorizontalHeaderLabels([_t("header_title")])
        self._preview_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self._preview_table.setSelectionBehavior(QTableWidget.SelectRows)
        self._preview_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._preview_table.verticalHeader().setVisible(False)
        layout.addWidget(self._preview_table, 1)

        # Buttons
        bb = QDialogButtonBox()
        btn_ok = bb.addButton(_t("btn_apply"), QDialogButtonBox.AcceptRole)
        btn_ok.clicked.connect(self.accept)
        btn_cancel = bb.addButton(_t("btn_cancel"), QDialogButtonBox.RejectRole)
        btn_cancel.clicked.connect(self.reject)
        layout.addWidget(bb)

    def eventFilter(self, obj, event):
        if event.type() == QEvent.MouseButtonDblClick:
            if obj in self._slot_name_labels:
                idx = self._slot_name_labels.index(obj)
                if self._slots[idx] is not None:
                    self._rename_slot(idx)
                    return True
        return super().eventFilter(obj, event)

    def _rename_slot(self, idx):
        current = self._slots[idx]["name"]
        new_name, ok = QInputDialog.getText(
            self, _t("custom_rename_title"), _t("custom_rename_label"),
            text=current)
        if ok and new_name.strip():
            self._slots[idx]["name"] = new_name.strip()
            self._update_slot_ui()

    def _update_slot_ui(self):
        for i in range(self.MAX_SLOTS):
            slot = self._slots[i]
            if slot:
                count = len(slot["song_ids"])
                self._slot_name_labels[i].setText(f"{slot['name']}  ({count})")
                self._slot_btn_remove[i].setEnabled(True)
                self._slot_btn_permanent[i].setEnabled(True)
            else:
                self._slot_name_labels[i].setText(_t("custom_slot_empty"))
                self._slot_btn_remove[i].setEnabled(False)
                self._slot_btn_permanent[i].setEnabled(False)
                self._slot_btn_permanent[i].setChecked(False)

    def _load_slot(self, idx):
        filepath, _ = QFileDialog.getOpenFileName(
            self, _t("dialog_load_playlist"), self._playlist_dir,
            _t("filter_playlist_files"))
        if not filepath:
            return
        try:
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    lines = f.readlines()
            except UnicodeDecodeError:
                with open(filepath, "r", encoding="cp1252") as f:
                    lines = f.readlines()
        except Exception as e:
            QMessageBox.warning(self, _t("error"), _t("load_failed", error=e))
            return

        song_ids = set()
        not_found = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            parts = line.split(" ", 2)
            if len(parts) < 2:
                continue
            mode = parts[0].upper()
            if mode not in ("P", "S"):
                mode = "P"
            # LOOPCOUNT-Token "N" oder "N:CUT" (BL-164) ueberspringen; nur Filename noetig
            if len(parts) == 3 and re.fullmatch(r"\d+(:\d+)?", parts[1]):
                filename = parts[2]
            elif len(parts) == 3:
                filename = parts[1] + " " + parts[2]
            else:
                filename = parts[1]
            song = self._db.get_by_title(filename) or self._db.get_by_filename(filename)
            if song:
                song_ids.add(song.id)
            else:
                not_found.append(filename)

        name = os.path.splitext(os.path.basename(filepath))[0]
        self._slot_filepath[idx] = filepath
        self._slots[idx] = {"name": name, "song_ids": frozenset(song_ids), "filepath": filepath}
        self._update_slot_ui()
        self._refresh_preview()
        if not_found:
            QMessageBox.information(
                self, _t("warning"),
                _t("songs_not_found", count=len(not_found),
                   names="\n".join(not_found[:10])))

    def _remove_slot(self, idx):
        self._slots[idx] = None
        self._slot_filepath[idx] = None
        self._update_slot_ui()
        self._refresh_preview()

    def _refresh_preview(self):
        """Zeigt Schnittmenge aller geladenen Slots in der Vorschau-Tabelle."""
        loaded = [s for s in self._slots if s is not None]
        if not loaded:
            self._lbl_preview.setText(_t("custom_filter_preview_empty"))
            self._preview_table.setRowCount(0)
            return

        ids = loaded[0]["song_ids"]
        for slot in loaded[1:]:
            ids = ids & slot["song_ids"]

        songs = []
        for sid in ids:
            song = self._db.get_by_id(sid)
            if song:
                songs.append(song)
        songs.sort(key=lambda s: (s.title or s.filename or "").lower())

        n_loaded = len(loaded)
        label = _t("custom_filter_preview_one") if n_loaded == 1 else _t("custom_filter_preview_multi", n=n_loaded)
        self._lbl_preview.setText(f"{label}  ({len(songs)})")

        self._preview_table.setUpdatesEnabled(False)
        self._preview_table.setRowCount(0)
        self._preview_table.setRowCount(len(songs))
        for row_idx, song in enumerate(songs):
            item = QTableWidgetItem(song.title or song.filename or "")
            self._preview_table.setItem(row_idx, 0, item)
        self._preview_table.setUpdatesEnabled(True)

    def get_slots(self) -> list:
        """Gibt die aktuellen Slots zurück (MAX_SLOTS Einträge, je dict oder None)."""
        return list(self._slots)

    def get_permanent_state(self) -> list:
        """Gibt die Permanent-Zustände zurück (MAX_SLOTS bools)."""
        return [btn.isChecked() for btn in self._slot_btn_permanent]


class SongPropertiesDialog(QDialog):
    """Generischer Key/Value-Editor fuer song_properties + Varianten-Verwaltung."""

    def __init__(self, db: SongDatabase, song_id: int, lang: str = "de", paths=None, parent=None, skin_mgr=None):
        super().__init__(parent)
        self.db = db
        self.song_id = song_id
        self.lang = lang
        self.paths = paths
        self.skin_mgr = skin_mgr
        self.setWindowTitle(_t("extended_data_title"))
        self.setMinimumWidth(480)
        self.setMinimumHeight(320)
        self._build_ui()
        self._load()

    def _build_ui(self):
        outer = QVBoxLayout(self)

        self.tabs = QTabWidget()
        outer.addWidget(self.tabs)

        # --- Tab 1: Allgemeine Eigenschaften ---
        tab_props = QWidget()
        props_layout = QVBoxLayout(tab_props)
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels([_t("prop_col_key"), _t("prop_col_value")])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.DoubleClicked | QTableWidget.EditKeyPressed)
        props_layout.addWidget(self.table)
        self.tabs.addTab(tab_props, _t("variant_tab_properties"))

        # --- Tab 2: Varianten ---
        tab_variants = QWidget()
        var_outer = QVBoxLayout(tab_variants)

        # Musik-Varianten
        music_hdr = QHBoxLayout()
        lbl_music = QLabel(f"<b>{_t('section_music_variants')}</b>")
        music_hdr.addWidget(lbl_music)
        music_hdr.addStretch()
        self.btn_add_music = QPushButton(_t("btn_add_music_variant"))
        self.btn_add_music.clicked.connect(lambda: self._add_variant("music"))
        music_hdr.addWidget(self.btn_add_music)
        var_outer.addLayout(music_hdr)

        self.music_variants_layout = QVBoxLayout()
        self.music_variants_layout.setSpacing(2)
        var_outer.addLayout(self.music_variants_layout)

        var_outer.addSpacing(12)

        # Lyric-Varianten
        lyric_hdr = QHBoxLayout()
        lbl_lyric = QLabel(f"<b>{_t('section_lyric_variants')}</b>")
        lyric_hdr.addWidget(lbl_lyric)
        lyric_hdr.addStretch()
        self.btn_add_lyric = QPushButton(_t("btn_add_lyric_variant"))
        self.btn_add_lyric.clicked.connect(lambda: self._add_variant("lyric"))
        lyric_hdr.addWidget(self.btn_add_lyric)
        var_outer.addLayout(lyric_hdr)

        self.lyric_variants_layout = QVBoxLayout()
        self.lyric_variants_layout.setSpacing(2)
        var_outer.addLayout(self.lyric_variants_layout)
        var_outer.addStretch()

        self.tabs.addTab(tab_variants, _t("variant_tab_variants"))

        # --- Tab 3: Custom-Jump-Marker (BL-185) ---
        tab_markers = QWidget()
        mk_outer = QVBoxLayout(tab_markers)
        mk_hint = QLabel(_t("marker_dialog_hint"))
        mk_hint.setWordWrap(True)
        mk_hint.setStyleSheet("color: gray; font-size: 11px;")
        mk_outer.addWidget(mk_hint)
        self.markers_layout = QVBoxLayout()
        self.markers_layout.setSpacing(2)
        mk_outer.addLayout(self.markers_layout)
        mk_outer.addStretch()
        self.tabs.addTab(tab_markers, _t("variant_tab_markers"))

        # OK / Abbrechen
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_ok = QPushButton(_t("btn_ok"))
        btn_ok.setDefault(True)
        btn_cancel = QPushButton(_t("btn_cancel"))
        btn_ok.clicked.connect(self._save_and_accept)
        btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(btn_ok)
        btn_row.addWidget(btn_cancel)
        outer.addLayout(btn_row)

    def _load(self):
        existing = self.db.get_properties(self.song_id)
        rows = []
        for key, (label_de, label_en) in SONG_PROPERTY_KEYS.items():
            display = label_de if self.lang == "de" else label_en
            rows.append((display, key, existing.get(key, "")))
        # Unbekannte Keys anzeigen (aber KEINE Varianten- oder Sync-Keys)
        for key, value in existing.items():
            if (key not in SONG_PROPERTY_KEYS and not self._is_variant_key(key)
                    and not key.startswith("lyric_sync_")
                    and not key.startswith("marker_")):
                rows.append((key, key, value))

        self.table.setRowCount(len(rows))
        for row_idx, (display, key, value) in enumerate(rows):
            key_item = QTableWidgetItem(display)
            key_item.setFlags(key_item.flags() & ~Qt.ItemIsEditable)
            key_item.setData(Qt.UserRole, key)
            self.table.setItem(row_idx, 0, key_item)
            self.table.setItem(row_idx, 1, QTableWidgetItem(value))

        self._reload_variants()
        self._reload_markers()

    @staticmethod
    def _is_variant_key(key: str) -> bool:
        import re
        return bool(re.match(r'^(music|lyric)_\d+_(name|file)$', key))

    def _reload_variants(self):
        _clear_layout(self.music_variants_layout)
        _clear_layout(self.lyric_variants_layout)
        for idx, name, filename in self.db.get_variants(self.song_id, "music"):
            self._add_variant_row(self.music_variants_layout, "music", idx, name, filename)
        for idx, name, filename in self.db.get_variants(self.song_id, "lyric"):
            self._add_variant_row(self.lyric_variants_layout, "lyric", idx, name, filename)

    def _add_variant_row(self, parent_layout, kind, idx, name, filename):
        row_widget = QWidget()
        row_layout = QHBoxLayout(row_widget)
        row_layout.setContentsMargins(4, 2, 4, 2)
        lbl_name = QLabel(f"<b>{name}</b>" if name else f"<i>{filename}</i>")
        lbl_file = QLabel(filename)
        lbl_file.setStyleSheet("color: gray; font-size: 11px;")
        lbl_file.setToolTip(filename)
        lbl_file.setMaximumWidth(240)
        row_layout.addWidget(lbl_name)
        row_layout.addWidget(lbl_file, 1)
        btn_del = QPushButton("✕")
        btn_del.setFixedWidth(26)
        btn_del.setFixedHeight(22)
        btn_del.setToolTip(_t("tooltip_delete_variant"))
        btn_del.clicked.connect(lambda checked=False, k=kind, i=idx: self._delete_variant(k, i))
        row_layout.addWidget(btn_del)
        parent_layout.addWidget(row_widget)

    def _add_variant(self, kind: str):
        dlg = _AddVariantDialog(kind, self.paths, self)
        if dlg.exec() != QDialog.Accepted or not dlg.filename:
            return
        self.db.add_variant(self.song_id, kind, dlg.name, dlg.filename)
        self._reload_variants()
        self.tabs.setCurrentIndex(1)

    def _delete_variant(self, kind: str, idx: int):
        self.db.delete_variant(self.song_id, kind, idx)
        self._reload_variants()

    # ---- Custom-Jump-Marker (BL-185) ----

    def _reload_markers(self):
        _clear_layout(self.markers_layout)
        markers = self.db.get_markers(self.song_id)
        if not markers:
            lbl = QLabel(_t("marker_none_yet"))
            lbl.setStyleSheet("color: gray; font-style: italic;")
            self.markers_layout.addWidget(lbl)
            return
        for idx, t, caption in markers:
            self._add_marker_row(idx, t, caption)

    def _add_marker_row(self, idx, time_seconds, caption):
        row_widget = QWidget()
        row_layout = QHBoxLayout(row_widget)
        row_layout.setContentsMargins(4, 2, 4, 2)
        lbl_cap = QLabel(f"<b>{caption}</b>" if caption else f"<i>{fmt_time(time_seconds)}</i>")
        lbl_time = QLabel(fmt_precise(time_seconds))
        lbl_time.setStyleSheet("color: gray; font-size: 11px; font-family: monospace;")
        row_layout.addWidget(lbl_cap, 1)
        row_layout.addWidget(lbl_time)
        # Icon-Farbe wie bei den Stream-Deck-Icons (Skin-Key 'icon_color')
        _ic = self.skin_mgr.color("icon_color", "#f0f0f0") if self.skin_mgr else "#f0f0f0"
        btn_edit = QPushButton()
        btn_edit.setIcon(_make_icon(_SVG_PENCIL, _ic))
        btn_edit.setFixedWidth(26)
        btn_edit.setFixedHeight(22)
        btn_edit.setToolTip(_t("marker_ctx_edit"))
        btn_edit.clicked.connect(
            lambda checked=False, i=idx, cap=caption: self._edit_marker_caption(i, cap))
        row_layout.addWidget(btn_edit)
        btn_time = QPushButton()
        btn_time.setIcon(_make_icon(_SVG_CLOCK, _ic))
        btn_time.setFixedWidth(26)
        btn_time.setFixedHeight(22)
        btn_time.setToolTip(_t("marker_ctx_edit_time"))
        btn_time.clicked.connect(
            lambda checked=False, i=idx, tt=time_seconds: self._edit_marker_time(i, tt))
        row_layout.addWidget(btn_time)
        btn_del = QPushButton()
        btn_del.setIcon(_make_icon(_SVG_REMOVE_X, _ic))
        btn_del.setFixedWidth(26)
        btn_del.setFixedHeight(22)
        btn_del.setToolTip(_t("marker_ctx_delete"))
        btn_del.clicked.connect(
            lambda checked=False, i=idx: self._delete_marker_dlg(i))
        row_layout.addWidget(btn_del)
        self.markers_layout.addWidget(row_widget)

    def _edit_marker_caption(self, idx, caption):
        new_cap, ok = QInputDialog.getText(
            self, _t("marker_edit_title"), _t("marker_edit_prompt"), text=caption)
        if ok:
            self.db.update_marker(self.song_id, idx, caption=new_cap.strip())
            self._reload_markers()

    def _edit_marker_time(self, idx, time_seconds):
        new_time, ok = QInputDialog.getText(
            self, _t("marker_edit_time_title"), _t("marker_edit_time_prompt"),
            text=fmt_precise(time_seconds))
        if ok:
            parsed = parse_time_offset(new_time)
            if parsed is not None and parsed >= 0:
                self.db.update_marker(self.song_id, idx, time_seconds=parsed)
                self._reload_markers()

    def _delete_marker_dlg(self, idx):
        self.db.delete_marker(self.song_id, idx)
        self._reload_markers()

    def _save_and_accept(self):
        for row in range(self.table.rowCount()):
            key = self.table.item(row, 0).data(Qt.UserRole)
            value = self.table.item(row, 1).text() if self.table.item(row, 1) else ""
            self.db.set_property(self.song_id, key, value)
        self.accept()


class SongDataWidget(QWidget):
    """Song-Daten-Modul: Editierbare Felder fuer den aktuellen Song."""

    def __init__(self, db: SongDatabase, paths: PathManager = None, parent=None):
        super().__init__(parent)
        self.db = db
        self.paths = paths
        self.skin_mgr = None          # von MainWindow gesetzt (fuer Icon-Tinting, BL-185)
        self._current_song: Song = None
        self._loading = False
        self._bpm_worker: BpmWorker = None
        self._lang = "de"
        self.on_song_saved = None
        self.on_file_changed = None   # callback(filepath) — nach Datei-Wechsel
        self.on_song_deleted = None   # callback(song_id) — nach Loeschen
        self.on_music_variant = None  # callback(filepath) — Musik-Variante gewaehlt
        self.on_lyric_variant = None  # callback(filename) — Lyric-Variante gewaehlt
        self.on_marker_jump = None    # callback(time_seconds) — Sprung zu Custom-Marker (BL-185)
        self.on_markers_changed = None  # callback() — Marker geaendert (Jump-Widget refresh, BL-185)
        self.get_location_id = None   # callable() → int|None — aktuelle Lokation
        self.on_add_note = None       # callback(text) — Notiz zur Lokation hinzufuegen
        self._active_music_variant = None  # aktiv gewaehlter Musik-Varianten-Filename
        self._active_lyric_variant = None  # aktiv gewaehlter Lyric-Varianten-Filename
        self._build_ui()

    def _build_ui(self):
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)

        # ScrollArea fuer den gesamten Inhalt
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll_content = QWidget()
        layout = QVBoxLayout(scroll_content)
        layout.setContentsMargins(8, 8, 8, 8)
        scroll.setWidget(scroll_content)
        outer_layout.addWidget(scroll)

        self.label_header = QLabel(_t("no_song_loaded"))
        self.label_header.setStyleSheet("font-size: 14px; font-weight: bold;")
        self.label_header.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.label_header)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight)

        file_row = QHBoxLayout()
        self.edit_filename = QLineEdit()
        self.edit_filename.setReadOnly(True)
        file_row.addWidget(self.edit_filename)
        self.btn_browse_file = QPushButton("...")
        self.btn_browse_file.setObjectName("fileBtn")
        self.btn_browse_file.setFixedWidth(30)
        self.btn_browse_file.setToolTip(_t("tooltip_browse_audio"))
        self.btn_browse_file.clicked.connect(self._browse_audio_file)
        file_row.addWidget(self.btn_browse_file)
        form.addRow(_t("form_filename"), file_row)

        # Musik-Varianten Auswahl (nur sichtbar wenn Varianten vorhanden)
        self.music_variants_widget = QWidget()
        self._music_variants_box = QHBoxLayout(self.music_variants_widget)
        self._music_variants_box.setContentsMargins(0, 0, 0, 0)
        self._music_variants_box.setSpacing(4)
        self._music_btn_group = None
        self.music_variants_widget.setVisible(False)
        form.addRow("", self.music_variants_widget)

        self.edit_title = QLineEdit()
        self.edit_title.setPlaceholderText(_t("placeholder_title"))
        self.edit_title.editingFinished.connect(self._auto_save)
        form.addRow(_t("form_title"), self.edit_title)

        self.edit_artist = QLineEdit()
        self.edit_artist.setPlaceholderText(_t("placeholder_artist"))
        self.edit_artist.editingFinished.connect(self._auto_save)
        form.addRow(_t("form_artist"), self.edit_artist)

        self.edit_label = QLineEdit()
        self.edit_label.setPlaceholderText(_t("placeholder_label"))
        self.edit_label.editingFinished.connect(self._auto_save)
        form.addRow(_t("form_label"), self.edit_label)

        genre_row = QHBoxLayout()
        self.label_genre = QLabel("\u2014")
        self.label_genre.setStyleSheet("color: #999;")
        self.label_genre.setWordWrap(True)
        genre_row.addWidget(self.label_genre, 1)
        self.btn_edit_genre = QPushButton(_t("btn_edit_genres"))
        self.btn_edit_genre.setObjectName("fileBtn")
        self.btn_edit_genre.setFixedWidth(28)
        self.btn_edit_genre.setToolTip(_t("genre_edit_title"))
        self.btn_edit_genre.setEnabled(False)
        self.btn_edit_genre.clicked.connect(self._edit_genres)
        genre_row.addWidget(self.btn_edit_genre)
        form.addRow(_t("form_genre"), genre_row)

        self.spin_quality = QSpinBox()
        self.spin_quality.setRange(0, 10)
        self.spin_quality.setValue(0)
        self.spin_quality.setToolTip(_t("tooltip_quality"))
        self.spin_quality.valueChanged.connect(self._auto_save)
        form.addRow(_t("form_quality"), self.spin_quality)

        self.combo_err = QComboBox()
        self.combo_err.addItem(_t("err_0"), 0)
        self.combo_err.addItem(_t("err_1"), 1)
        self.combo_err.addItem(_t("err_2"), 2)
        self.combo_err.addItem(_t("err_3"), 3)
        self.combo_err.addItem(_t("err_4"), 4)
        self.combo_err.setToolTip(_t("tooltip_err"))
        self.combo_err.currentIndexChanged.connect(self._auto_save)
        form.addRow(_t("form_err"), self.combo_err)

        bpm_row = QHBoxLayout()
        self.spin_bpm = QDoubleSpinBox()
        self.spin_bpm.setRange(0.0, 300.0)
        self.spin_bpm.setDecimals(1)
        self.spin_bpm.setSingleStep(0.5)
        self.spin_bpm.setValue(0.0)
        self.spin_bpm.setToolTip(_t("tooltip_bpm"))
        self.spin_bpm.valueChanged.connect(self._auto_save)
        bpm_row.addWidget(self.spin_bpm)
        self.btn_auto_bpm = QPushButton(_t("btn_auto_bpm"))
        self.btn_auto_bpm.setMinimumWidth(60)
        self.btn_auto_bpm.setToolTip(_t("tooltip_auto_bpm"))
        self.btn_auto_bpm.clicked.connect(self._on_auto_bpm)
        self.btn_auto_bpm.setEnabled(False)
        bpm_row.addWidget(self.btn_auto_bpm)
        form.addRow(_t("form_bpm"), bpm_row)

        self.spin_tempo = QDoubleSpinBox()
        self.spin_tempo.setRange(0.50, 1.50)
        self.spin_tempo.setDecimals(2)
        self.spin_tempo.setSingleStep(0.01)
        self.spin_tempo.setValue(1.00)
        self.spin_tempo.setToolTip(_t("tooltip_std_tempo"))
        self.spin_tempo.valueChanged.connect(self._auto_save)
        form.addRow(_t("form_std_tempo"), self.spin_tempo)

        self.spin_pitch = QDoubleSpinBox()
        self.spin_pitch.setRange(-6.0, 6.0)
        self.spin_pitch.setDecimals(1)
        self.spin_pitch.setSingleStep(0.2)
        self.spin_pitch.setValue(0.0)
        self.spin_pitch.setToolTip(_t("tooltip_pitch_semitones"))
        self.spin_pitch.valueChanged.connect(self._auto_save)
        form.addRow(_t("form_pitch"), self.spin_pitch)

        self.spin_volume = QDoubleSpinBox()
        self.spin_volume.setRange(0.0, 1.0)
        self.spin_volume.setDecimals(2)
        self.spin_volume.setSingleStep(0.05)
        self.spin_volume.setValue(1.0)
        self.spin_volume.setToolTip(_t("tooltip_volume"))
        self.spin_volume.valueChanged.connect(self._on_volume_changed)
        form.addRow(_t("form_volume"), self.spin_volume)

        self.spin_loop_in = QDoubleSpinBox()
        self.spin_loop_in.setRange(0.0, 9999.0)
        self.spin_loop_in.setDecimals(2)
        self.spin_loop_in.setSingleStep(0.01)
        self.spin_loop_in.setValue(0.0)
        self.spin_loop_in.setSuffix(" s")
        self.spin_loop_in.valueChanged.connect(self._auto_save)
        form.addRow(_t("form_loop_in"), self.spin_loop_in)

        self.spin_loop_out = QDoubleSpinBox()
        self.spin_loop_out.setRange(0.0, 9999.0)
        self.spin_loop_out.setDecimals(2)
        self.spin_loop_out.setSingleStep(0.01)
        self.spin_loop_out.setValue(0.0)
        self.spin_loop_out.setSuffix(" s")
        self.spin_loop_out.setToolTip(_t("tooltip_loop_out"))
        self.spin_loop_out.valueChanged.connect(self._auto_save)
        form.addRow(_t("form_loop_out"), self.spin_loop_out)

        self.spin_loop_offset = QDoubleSpinBox()
        self.spin_loop_offset.setRange(-3000.0, 3000.0)
        self.spin_loop_offset.setDecimals(1)
        self.spin_loop_offset.setSingleStep(0.5)
        self.spin_loop_offset.setValue(0.0)
        self.spin_loop_offset.setSuffix(" ms")
        self.spin_loop_offset.setToolTip(
            "Loop-Offset: Automatisch gemessen oder manuell einstellbar.\n"
            "Positiv = spaeter springen, Negativ = frueher."
        )
        self.spin_loop_offset.valueChanged.connect(self._on_offset_changed)
        form.addRow("Loop Offset", self.spin_loop_offset)

        # BL-185: Custom-Jump-Marker — je ein Button pro Marker (Klick = Sprung),
        # analog zu den Music-/Lyric-Varianten. Nur sichtbar, wenn Marker existieren.
        self.marker_widget = QWidget()
        self._marker_box = QHBoxLayout(self.marker_widget)
        self._marker_box.setContentsMargins(0, 0, 0, 0)
        self._marker_box.setSpacing(4)
        self.marker_widget.setVisible(False)
        # Label separat merken, damit in QFormLayout auch die Beschriftung
        # mit ausgeblendet wird, wenn keine Marker existieren.
        self._marker_row_label = QLabel(_t("form_markers"))
        self._marker_row_label.setVisible(False)
        form.addRow(self._marker_row_label, self.marker_widget)

        lyrics_row = QHBoxLayout()
        self.edit_lyrics = QLineEdit()
        self.edit_lyrics.setPlaceholderText(_t("placeholder_lyrics_file"))
        self.edit_lyrics.editingFinished.connect(self._auto_save)
        lyrics_row.addWidget(self.edit_lyrics)
        self.btn_browse_lyrics = QPushButton("...")
        self.btn_browse_lyrics.setObjectName("fileBtn")
        self.btn_browse_lyrics.setFixedWidth(30)
        self.btn_browse_lyrics.setToolTip(_t("tooltip_browse_lyrics"))
        self.btn_browse_lyrics.clicked.connect(self._browse_lyrics)
        lyrics_row.addWidget(self.btn_browse_lyrics)
        form.addRow(_t("form_lyrics_file"), lyrics_row)

        # Lyric-Varianten Auswahl (nur sichtbar wenn Varianten vorhanden)
        self.lyric_variants_widget = QWidget()
        self._lyric_variants_box = QHBoxLayout(self.lyric_variants_widget)
        self._lyric_variants_box.setContentsMargins(0, 0, 0, 0)
        self._lyric_variants_box.setSpacing(4)
        self._lyric_btn_group = None
        self.lyric_variants_widget.setVisible(False)
        form.addRow("", self.lyric_variants_widget)

        # Patter / Singing Call / Other. "Other" ist kein eigener Schalter,
        # sondern "weder Patter noch Singing" (intern#170, song_types).
        type_layout = QHBoxLayout()
        self.chk_pattern = QCheckBox(_t("chk_pattern"))
        self.chk_pattern.setToolTip(_t("tooltip_pattern"))
        self.chk_pattern.toggled.connect(self._on_type_toggled)
        type_layout.addWidget(self.chk_pattern)
        self.chk_singing = QCheckBox(_t("chk_singing"))
        self.chk_singing.setToolTip(_t("tooltip_singing"))
        self.chk_singing.toggled.connect(self._on_type_toggled)
        type_layout.addWidget(self.chk_singing)
        self.chk_other = QCheckBox(_t("chk_other"))
        self.chk_other.setToolTip(_t("tooltip_other"))
        self.chk_other.toggled.connect(self._on_other_toggled)
        type_layout.addWidget(self.chk_other)
        type_layout.addStretch()
        form.addRow(_t("form_type"), type_layout)

        self.label_date_added = QLabel("\u2014")
        self.label_date_added.setStyleSheet("color: #aaa;")
        form.addRow(_t("form_date_added"), self.label_date_added)

        layout.addLayout(form)

        self.label_db_info = QLabel("")
        self.label_db_info.setAlignment(Qt.AlignCenter)
        self.label_db_info.setStyleSheet("font-size: 11px; color: gray;")
        layout.addWidget(self.label_db_info)

        # Aktions-Buttons: Erweiterte Daten | Feedback | Song loeschen
        action_row = QHBoxLayout()
        action_row.setSpacing(4)

        self.btn_extended_data = QPushButton(_t("btn_extended_data"))
        self.btn_extended_data.setEnabled(False)
        self.btn_extended_data.clicked.connect(self._on_extended_data)
        action_row.addWidget(self.btn_extended_data)

        self.btn_feedback = QPushButton(_t("btn_feedback"))
        self.btn_feedback.setEnabled(False)
        self.btn_feedback.clicked.connect(self._on_feedback)
        action_row.addWidget(self.btn_feedback)

        self.btn_delete_song = QPushButton(_t("btn_delete_song"))
        self.btn_delete_song.setToolTip(_t("tooltip_delete_song"))
        self.btn_delete_song.setEnabled(False)
        self.btn_delete_song.clicked.connect(self._on_delete_song)
        action_row.addWidget(self.btn_delete_song)

        layout.addLayout(action_row)
        layout.addStretch()

        # Mausrad-Schutz: SpinBoxes/Combos sollen nicht versehentlich durch
        # Scrollen geaendert werden — gleiches Pattern wie im Settings-Dialog.
        for child in self.findChildren(QAbstractSpinBox):
            child.installEventFilter(self)
        for child in self.findChildren(QComboBox):
            child.installEventFilter(self)

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Wheel and isinstance(
                obj, (QAbstractSpinBox, QComboBox)):
            event.ignore()
            return True
        return super().eventFilter(obj, event)

    @property
    def shown_song(self):
        """Der im Dock angezeigte Song (kann vom geladenen Song abweichen)."""
        return self._current_song

    def replace_shown_song(self, fresh: Song):
        """Frisch aus der DB geholter Song mit gleicher ID: Objekt ersetzen und
        die von aussen geaenderten Bewertungsfelder neu zeigen."""
        self._current_song = fresh
        self.spin_quality.blockSignals(True)
        self.spin_quality.setValue(fresh.quality or 0)
        self.spin_quality.blockSignals(False)
        self.combo_err.blockSignals(True)
        idx = self.combo_err.findData(fresh.err or 0)
        if idx >= 0:
            self.combo_err.setCurrentIndex(idx)
        self.combo_err.blockSignals(False)

    def load_song(self, song: Song):
        if self._current_song is None or self._current_song.id != song.id:
            # Neuer Song — Varianten-Auswahl zuruecksetzen
            self._active_music_variant = None
            self._active_lyric_variant = None
        self._current_song = song
        self._populate_fields(song)
        self.label_header.setText(_t("song_header", id=song.id, title=song.title))
        self.label_db_info.setText(_t("db_info_line", id=song.id, filename=song.filename))
        # Auto-BPM nur wenn Datei existiert
        has_file = bool(song.filename and self.paths and
                        self.paths.find_song_file(song.filename))
        self.btn_auto_bpm.setEnabled(has_file)
        self.btn_delete_song.setEnabled(True)
        self.btn_edit_genre.setEnabled(True)
        self.btn_extended_data.setEnabled(True)
        self.btn_feedback.setEnabled(True)
        # Rote Markierung wenn Datei fehlt
        if has_file:
            self.label_db_info.setStyleSheet("font-size: 11px; color: gray;")
        else:
            self.label_db_info.setStyleSheet(
                "font-size: 11px; color: white; background-color: #ef4444; "
                "padding: 2px 4px; border-radius: 3px;")
        self._refresh_variants(song)
        self._refresh_markers(song)

    def clear_song(self):
        """Zeigt wieder "kein Song geladen" (z. B. nach dem Loeschen, intern#212)."""
        self._current_song = None
        self._active_music_variant = None
        self._active_lyric_variant = None
        empty = Song()
        self._populate_fields(empty)
        self.label_header.setText(_t("no_song_loaded"))
        self.label_db_info.setText("")
        self.label_db_info.setStyleSheet("font-size: 11px; color: gray;")
        for btn in (self.btn_auto_bpm, self.btn_delete_song, self.btn_edit_genre,
                    self.btn_extended_data, self.btn_feedback):
            btn.setEnabled(False)
        self._refresh_variants(empty)
        self._refresh_markers(empty)

    def _on_delete_song(self):
        """Aktuellen Song loeschen mit Sicherheitsabfrage."""
        if not self._current_song:
            return
        song = self._current_song
        msg = QMessageBox(self)
        msg.setWindowTitle(_t("dialog_delete_song"))
        msg.setText(_t("confirm_delete_song", title=song.title, id=song.id))
        msg.setInformativeText(_t("confirm_delete_song_info"))
        msg.setIcon(QMessageBox.Warning)
        msg.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        msg.setDefaultButton(QMessageBox.No)
        if msg.exec() != QMessageBox.Yes:
            return
        try:
            self.db.delete(song.id)
            self._current_song = None
            self.btn_delete_song.setEnabled(False)
            # Signal an MainWindow: Song wurde geloescht
            if self.on_song_deleted:
                self.on_song_deleted(song.id)
        except Exception as e:
            QMessageBox.warning(self, _t("error"), str(e))

    def set_lang(self, lang: str):
        self._lang = lang

    def _on_extended_data(self):
        if not self._current_song:
            return
        dlg = SongPropertiesDialog(self.db, self._current_song.id, self._lang, self.paths, self, skin_mgr=self.skin_mgr)
        dlg.exec()
        # Varianten-Buttons aktualisieren (Nutzer koennte Varianten hinzugefuegt/geloescht haben)
        self._refresh_variants(self._current_song)
        # Marker koennten im Dialog bearbeitet/geloescht worden sein (BL-185)
        self._refresh_markers(self._current_song)
        self._notify_markers_changed()

    def _refresh_variants(self, song: Song):
        """Varianten-Button-Zeilen aktualisieren (nach Song-Laden oder Dialog-Schluss)."""
        self._refresh_variant_buttons(
            self.music_variants_widget,
            self._music_variants_box,
            song,
            self.db.get_variants(song.id, "music"),
            song.filename,
            is_music=True,
        )
        self._refresh_variant_buttons(
            self.lyric_variants_widget,
            self._lyric_variants_box,
            song,
            self.db.get_variants(song.id, "lyric"),
            song.lyrics_file,
            is_music=False,
        )

    def _refresh_variant_buttons(self, container, box, song, variants, standard_filename, is_music):
        from PySide6.QtWidgets import QButtonGroup
        _clear_layout(box)
        if not variants:
            container.setVisible(False)
            return
        active = self._active_music_variant if is_music else self._active_lyric_variant
        btn_group = QButtonGroup(container)
        btn_group.setExclusive(True)
        std_btn = QPushButton(_t("variant_standard"))
        std_btn.setCheckable(True)
        std_btn.setChecked(active is None)
        if is_music:
            std_btn.clicked.connect(
                lambda checked=False: self._select_music_variant(None)
            )
        else:
            std_btn.clicked.connect(
                lambda checked=False: self._select_lyric_variant(None)
            )
        btn_group.addButton(std_btn)
        box.addWidget(std_btn)
        for _idx, name, filename in variants:
            label = name if name else filename
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setChecked(active == filename)
            btn.setToolTip(filename)
            if is_music:
                btn.clicked.connect(
                    lambda checked=False, f=filename: self._select_music_variant(f)
                )
            else:
                btn.clicked.connect(
                    lambda checked=False, f=filename: self._select_lyric_variant(f)
                )
            btn_group.addButton(btn)
            box.addWidget(btn)
        box.addStretch()
        container.setVisible(True)

    # ---- Custom-Jump-Marker (BL-185) ----

    def _refresh_markers(self, song: Song):
        """Marker-Button-Zeile aktualisieren. Ein Button je Marker, Klick = Sprung."""
        _clear_layout(self._marker_box)
        markers = self.db.get_markers(song.id) if (song and song.id) else []
        if not markers:
            self.marker_widget.setVisible(False)
            self._marker_row_label.setVisible(False)
            return
        self._marker_row_label.setVisible(True)
        for idx, t, caption in markers:
            label = caption if caption else fmt_time(t)
            btn = QPushButton(label)
            btn.setToolTip(f"{fmt_precise(t)}" + (f" — {caption}" if caption else ""))
            btn.clicked.connect(
                lambda checked=False, tt=t: self._jump_to_marker(tt))
            btn.setContextMenuPolicy(Qt.CustomContextMenu)
            btn.customContextMenuRequested.connect(
                lambda pos, b=btn, i=idx, tt=t, cap=caption:
                    self._marker_context_menu(b, pos, i, tt, cap))
            self._marker_box.addWidget(btn)
        self._marker_box.addStretch()
        self.marker_widget.setVisible(True)

    def _jump_to_marker(self, time_seconds: float):
        """Klick auf einen Marker-Button → Sprung ans Hauptfenster delegieren."""
        if self.on_marker_jump:
            self.on_marker_jump(time_seconds)

    def _marker_context_menu(self, btn, pos, idx: int, time_seconds: float,
                             caption: str):
        """Rechtsklick auf einen Marker-Button: Beschriftung/Zeit bearbeiten, loeschen."""
        if not self._current_song:
            return
        menu = QMenu(self)
        act_edit = menu.addAction(_t("marker_ctx_edit"))
        act_time = menu.addAction(_t("marker_ctx_edit_time"))
        menu.addSeparator()
        act_del = menu.addAction(_t("marker_ctx_delete"))
        chosen = menu.exec(btn.mapToGlobal(pos))
        if chosen == act_edit:
            new_cap, ok = QInputDialog.getText(
                self, _t("marker_edit_title"), _t("marker_edit_prompt"),
                text=caption)
            if ok:
                self.db.update_marker(self._current_song.id, idx,
                                      caption=new_cap.strip())
                self._refresh_markers(self._current_song)
                self._notify_markers_changed()
        elif chosen == act_time:
            new_time, ok = QInputDialog.getText(
                self, _t("marker_edit_time_title"), _t("marker_edit_time_prompt"),
                text=fmt_precise(time_seconds))
            if ok:
                parsed = parse_time_offset(new_time)
                if parsed is not None and parsed >= 0:
                    self.db.update_marker(self._current_song.id, idx,
                                          time_seconds=parsed)
                    self._refresh_markers(self._current_song)
                    self._notify_markers_changed()
        elif chosen == act_del:
            self.db.delete_marker(self._current_song.id, idx)
            self._refresh_markers(self._current_song)
            self._notify_markers_changed()

    def _notify_markers_changed(self):
        """Meldet Marker-Aenderungen ans Hauptfenster (Jump-Widget refreshen)."""
        if self.on_markers_changed:
            self.on_markers_changed()

    def _select_music_variant(self, filename):
        if filename is None:
            # Standard gewaehlt
            self._active_music_variant = None
            filename = self._current_song.filename
        else:
            # Variante gewaehlt — immer merken, auch wenn Dateiname = Standard-Dateiname
            self._active_music_variant = filename
        if not filename or not self.paths:
            return
        filepath = self.paths.find_song_file(filename)
        if filepath and self.on_music_variant:
            self.on_music_variant(filepath)

    def _select_lyric_variant(self, filename):
        if filename is None:
            # Standard gewaehlt
            self._active_lyric_variant = None
            filename = self._current_song.lyrics_file or ""
        else:
            # Variante gewaehlt — immer merken
            self._active_lyric_variant = filename
        if self.on_lyric_variant:
            self.on_lyric_variant(filename)

    def _on_feedback(self):
        """Feedback-Dialog manuell oeffnen und Ergebnis direkt in die Felder uebernehmen."""
        if not self._current_song:
            return
        loc_id = self.get_location_id() if callable(self.get_location_id) else None
        dlg = FeedbackDialog(self._current_song, self, location_id=loc_id)
        result = dlg.exec()
        # Session-Suppression wirkt unabhaengig von Accept/Cancel
        if dlg.suppress_session:
            win = self.window()
            if win is not None:
                win._feedback_suppressed_session = True
        if result == QDialog.Accepted:
            self._loading = True
            self.spin_quality.setValue(dlg.quality)
            idx = self.combo_err.findData(dlg.err)
            if idx >= 0:
                self.combo_err.setCurrentIndex(idx)
            self._loading = False
            self._auto_save()
            if dlg.note_text and loc_id is not None and callable(self.on_add_note):
                self.on_add_note(dlg.note_text)

    def _populate_fields(self, song: Song):
        self._loading = True
        self.edit_filename.setText(song.filename)
        self.edit_title.setText(song.title)
        self.edit_artist.setText(song.artist)
        self.edit_label.setText(song.label)
        # Genre-Tags anzeigen
        genres = self.db.get_genres_for_song(song.id) if song.id else []
        genre_text = ", ".join(name for _, name in genres) if genres else "\u2014"
        self.label_genre.setText(genre_text)
        self.spin_quality.setValue(song.quality)
        err_idx = self.combo_err.findData(song.err)
        self.combo_err.setCurrentIndex(err_idx if err_idx >= 0 else 0)
        self.spin_bpm.setValue(song.base_bpm)
        self.spin_tempo.setValue(song.standard_tempo)
        self.spin_pitch.setValue(song.pitch)
        self.spin_volume.setValue(song.volume)
        self.spin_loop_in.setValue(song.loop_in)
        self.spin_loop_out.setValue(song.loop_out)
        self.spin_loop_offset.setValue(song.loop_offset_ms)
        self.edit_lyrics.setText(song.lyrics_file)
        self.chk_pattern.setChecked(bool(song.is_pattern))
        self.chk_singing.setChecked(bool(song.is_singing))
        # Auch ohne toggled-Signal (gleiche Stellung wie beim Song davor)
        self._sync_other_checkbox()
        self.label_date_added.setText(song.date_added if song.date_added else "\u2014")
        self._loading = False

    def _collect_fields(self) -> Song:
        if not self._current_song:
            return None
        song = Song(
            id=self._current_song.id,
            filename=self._current_song.filename,
            title=self.edit_title.text().strip(),
            artist=self.edit_artist.text().strip(),
            label=self.edit_label.text().strip(),
            quality=self.spin_quality.value(),
            err=self.combo_err.currentData(),
            base_bpm=self.spin_bpm.value(),
            standard_tempo=self.spin_tempo.value(),
            pitch=self.spin_pitch.value(),
            volume=self.spin_volume.value(),
            loop_in=self.spin_loop_in.value(),
            loop_out=self.spin_loop_out.value(),
            loop_offset_ms=self.spin_loop_offset.value(),
            lyrics_file=self.edit_lyrics.text().strip(),
            is_pattern=1 if self.chk_pattern.isChecked() else 0,
            is_singing=1 if self.chk_singing.isChecked() else 0,
        )
        return song

    def _on_offset_changed(self, value):
        """Offset-SpinBox geaendert: Engine + AutoSave aktualisieren."""
        if self._loading:
            return
        # Engine sofort aktualisieren (Live-Aenderung)
        main_win = self.window()
        if hasattr(main_win, 'engine'):
            main_win.engine.set_loop_offset_ms(value)
        self._auto_save()

    def _on_volume_changed(self, value):
        """Volume-SpinBox geaendert: Engine sofort (smooth), DB leichtgewichtig."""
        if self._loading:
            return
        main_win = self.window()
        if hasattr(main_win, 'engine'):
            main_win.engine.set_volume(value)
        # DB: nur Volume-Spalte updaten, NICHT _auto_save (loest Lyrics-Reload aus)
        if not hasattr(self, '_volume_save_timer'):
            from PySide6.QtCore import QTimer
            self._volume_save_timer = QTimer(self)
            self._volume_save_timer.setSingleShot(True)
            self._volume_save_timer.timeout.connect(self._save_volume_only)
        self._volume_save_timer.start(500)

    def _save_volume_only(self):
        """Speichert nur den Volume-Wert in die DB (ohne on_song_saved-Chain)."""
        # TIC-0026: Guard — _volume_save_timer (500ms) kann nach db.close() feuern
        if not self._current_song or not self.db.is_open():
            return
        vol = self.spin_volume.value()
        self._current_song.volume = vol
        self.db.save_playback_settings(self._current_song.id, volume=vol)

    def refresh_loop_values(self, loop_in: float, loop_out: float):
        """Setzt die Loop-In/Out-Felder neu (z.B. nach Loop-Finder-Apply).

        Ohne erneutes Auto-Save: die Werte sind bereits in der DB. _loading
        unterdrueckt den valueChanged->_auto_save-Trigger.
        """
        prev = self._loading
        self._loading = True
        try:
            self.spin_loop_in.setValue(loop_in)
            self.spin_loop_out.setValue(loop_out)
            if self._current_song is not None:
                self._current_song.loop_in = loop_in
                self._current_song.loop_out = loop_out
        finally:
            self._loading = prev

    def _sync_other_checkbox(self):
        """'Other' folgt den beiden Schaltern: an, wenn beide aus sind."""
        self.chk_other.blockSignals(True)
        self.chk_other.setChecked(song_types.is_other(
            self.chk_pattern.isChecked(), self.chk_singing.isChecked()))
        self.chk_other.blockSignals(False)

    def _on_type_toggled(self, _checked=False):
        self._sync_other_checkbox()
        self._auto_save()

    def _on_other_toggled(self, checked: bool):
        """'Other' angekreuzt: Patter und Singing gehen aus. Abwaehlen geht
        nur, indem Patter oder Singing angekreuzt wird — sonst bliebe ein Song
        ohne Typ, und genau das ist Other."""
        if not checked:
            self._sync_other_checkbox()
            return
        for chk in (self.chk_pattern, self.chk_singing):
            chk.blockSignals(True)
            chk.setChecked(False)
            chk.blockSignals(False)
        self._auto_save()

    def _auto_save(self, *args):
        # TIC-0026: Guard — DB kann durch closeEvent schon geschlossen sein
        # (beim Schliessen feuern Felder noch editingFinished/valueChanged)
        if self._loading or not self._current_song or not self.db.is_open():
            return
        song = self._collect_fields()
        if song:
            self.db.update(song)
            self._current_song = song
            self.label_header.setText(_t("song_header", id=song.id, title=song.title))
            self.label_db_info.setText(
                _t("db_info_autosaved", id=song.id)
            )
            if self.on_song_saved:
                self.on_song_saved()

    def _browse_audio_file(self):
        """Oeffnet einen File-Dialog im Musik-Verzeichnis fuer Audio-Dateien."""
        if not self._current_song or not self.paths:
            return
        # _loading VOR dem Dialog: Fokus-Verlust → editingFinished blockieren
        self._loading = True
        start_dir = self.paths.music_dir
        filepath, _ = QFileDialog.getOpenFileName(
            self, _t("dialog_select_audio"), start_dir,
            _t("filter_audio_files")
        )
        if not filepath:
            self._loading = False
            return
        filepath = os.path.normpath(filepath)
        # Relativer Pfad gegen alle Musik-Slots (BL-147, kanonisch '/')
        new_filename = self.paths.to_relative_filename(filepath)
        # UNIQUE-Check: Ist die Datei schon einem anderen Song zugeordnet?
        existing = self.db.get_by_filename(new_filename)
        if existing and existing.id != self._current_song.id:
            from PySide6.QtWidgets import QMessageBox
            reply = QMessageBox.question(
                self, _t("file_copy_title"),
                _t("file_already_assigned",
                   filename=new_filename, id=existing.id,
                   title=existing.title),
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No
            )
            if reply != QMessageBox.Yes:
                self._loading = False
                return
            # Kopie erstellen mit Suffix
            import shutil
            base, ext = os.path.splitext(filepath)
            copy_nr = 1
            while True:
                copy_path = f"{base}_copy{copy_nr}{ext}"
                if not os.path.exists(copy_path):
                    break
                copy_nr += 1
            shutil.copy2(filepath, copy_path)
            filepath = copy_path
            new_filename = self.paths.to_relative_filename(filepath)
            print(f"[P32] Kopie erstellt: {new_filename}")
        # Filename in DB aendern
        self.db.update_filename(self._current_song.id, new_filename)
        self._current_song.filename = new_filename
        self.edit_filename.setText(new_filename)
        print(f"[P32] Datei gewaehlt: {os.path.basename(filepath)}"
              f" (aus {filepath})")
        self._loading = False
        # Song mit neuer Datei im Player laden
        if self.on_file_changed:
            self.on_file_changed(filepath)

    def _browse_lyrics(self):
        """Oeffnet einen File-Dialog im Lyrics-Verzeichnis."""
        start_dir = self.paths.lyrics_dir if self.paths else os.path.expanduser("~")
        filepath, _ = QFileDialog.getOpenFileName(
            self, _t("dialog_select_lyrics"), start_dir,
            _t("filter_lyrics_files")
        )
        if filepath:
            rel = self._lyrics_name_for(filepath)
            if rel is None:
                return
            self.edit_lyrics.setText(rel)
            self._auto_save()

    def _lyrics_name_for(self, filepath: str):
        """Name, unter dem die gewaehlte Datei beim Song gespeichert wird:
        relativ zum Lyrics-Ordner (BL-147, kanonisch '/'). Eine Datei von
        ausserhalb wird in den Lyrics-Ordner kopiert; liegt dort schon eine
        gleichnamige mit anderem Inhalt, entscheidet der Caller (intern#167).
        None = Caller hat abgebrochen oder das Kopieren ist fehlgeschlagen."""
        if not self.paths:
            return os.path.basename(filepath)
        lyrics_dir = self.paths.lyrics_dir
        if lyrics_files.is_inside(filepath, lyrics_dir):
            return self.paths.to_relative_lyric_filename(filepath)
        try:
            conflict = lyrics_files.find_conflict(filepath, lyrics_dir)
            if conflict is None:
                return lyrics_files.adopt(filepath, lyrics_dir)
            decision = ask_lyrics_conflict(self, conflict)
            if decision is None:
                return None
            return lyrics_files.resolve(conflict, decision)
        except OSError as e:
            QMessageBox.warning(self, _t("lyrics_conflict_title"),
                                _t("lyrics_copy_failed", error=str(e)))
            return None

    def _on_auto_bpm(self):
        """Startet BPM-Erkennung im Hintergrund-Thread."""
        if not self._current_song or not self.paths:
            return
        filepath = self.paths.find_song_file(self._current_song.filename)
        if not filepath:
            return
        self.btn_auto_bpm.setEnabled(False)
        self.btn_auto_bpm.setText("...")
        self._bpm_worker = BpmWorker(filepath)
        self._bpm_worker.done.connect(self._on_bpm_result)
        self._bpm_worker.error.connect(self._on_bpm_error)
        # TIC-0029: Referenz erst beim echten Thread-Ende freigeben.
        self._bpm_worker.finished.connect(self._release_bpm_worker)
        self._bpm_worker.start()

    def _release_bpm_worker(self):
        """Gibt den BPM-Worker erst nach echtem Thread-Ende frei (TIC-0029).

        Verhindert, dass der GC das QThread-Objekt zerstoert, waehrend run()
        noch laeuft (Crash 'QThread: Destroyed while thread is still running').
        """
        w = self._bpm_worker
        self._bpm_worker = None
        if w is not None:
            w.deleteLater()

    def _on_bpm_result(self, bpm: float):
        """Callback: BPM erfolgreich erkannt."""
        self.spin_bpm.setValue(bpm)
        self.btn_auto_bpm.setText(_t("btn_auto_bpm"))
        self.btn_auto_bpm.setEnabled(True)

    def _on_bpm_error(self, msg: str):
        """Callback: BPM-Erkennung fehlgeschlagen."""
        self.btn_auto_bpm.setText(_t("btn_auto_bpm"))
        self.btn_auto_bpm.setEnabled(True)
        print(f"[BPM] {_t('bpm_error')}: {msg}")

    def _edit_genres(self):
        """Oeffnet den Genre-Bearbeitungs-Dialog fuer den aktuellen Song."""
        if not self._current_song or not self._current_song.id:
            return
        dlg = _GenreEditDialog(self.db, self._current_song.id, parent=self)
        if dlg.exec() == QDialog.Accepted:
            selected = dlg.selected_genre_ids()
            self.db.set_genres_for_song(self._current_song.id, selected)
            # Anzeige aktualisieren
            genres = self.db.get_genres_for_song(self._current_song.id)
            genre_text = ", ".join(name for _, name in genres) if genres else "\u2014"
            self.label_genre.setText(genre_text)
            # Songlist und Planner informieren
            if self.on_song_saved:
                self.on_song_saved()

    def update_tempo(self, tempo_factor):
        self._loading = True
        self.spin_tempo.setValue(tempo_factor)
        self._loading = False

    def update_pitch(self, pitch_semitones):
        self._loading = True
        self.spin_pitch.setValue(pitch_semitones)
        self._loading = False


# Typ-Filter der Filterleiste: Radio-Button-ID -> Song-Typ (0 = Alle)
_TYPE_BY_FILTER_ID = {v: k for k, v in song_types.FILTER_ID.items()}


class SongFilterBar(QWidget):
    """Gemeinsamer Filter- und Sortier-Header fuer SongListWidget und PlaylistManagerWidget.

    Konfigurierbar ueber Konstruktor-Parameter:
      show_genre           -- Genre-ComboBox anzeigen
      show_recommendation  -- "Empfehlung"-Sortieroption
      show_custom_filter   -- Custom-Playlist-Filter-Button + Checkbox-Zeile (BL-097)
      db                   -- SongDatabase-Referenz (benoetigt fuer Custom-Filter-Dialog)
      pl_dir               -- Playlist-Verzeichnis (benoetigt fuer Custom-Filter-Dialog)
      settings             -- QSettings fuer Persistenz permanenter Custom-Filter (optional)

    Signale:
      sig_changed  -- wird emittiert wenn sich irgendein Filter/Sortierung aendert
    """

    sig_changed = Signal()

    SORT_ALPHA           = 0
    SORT_QUALITY         = 1
    SORT_LAST_PLAYED     = 2
    SORT_RECOMMENDATION  = 3
    SORT_DATE_ADDED      = 4
    SORT_RANDOM          = 5   # BL-170: reiner Zufall (Gleichverteilung)
    SORT_WEIGHTED_RANDOM = 6   # BL-170: gewichteter Zufall (Roulette-Wheel)

    def __init__(self, show_genre=False, show_recommendation=False,
                 show_custom_filter=False, db=None, pl_dir="", settings=None,
                 parent=None):
        super().__init__(parent)
        self._show_genre          = show_genre
        self._show_recommendation = show_recommendation
        self._show_custom_filter  = show_custom_filter
        self._db                  = db
        self._pl_dir              = pl_dir
        self._settings            = settings
        # Custom-Filter-State (BL-097)
        self._custom_slots:     list = [None, None, None, None]
        self._permanent_state:  list = [False, False, False, False]
        self._permanent_loaded: bool = False
        # BL-113: Stabiler Zufalls-Tiebreaker fuer Gleichstands-Gruppen (einmal pro Session)
        self._sort_random: dict = {}  # {song_id: float}
        self._sort_draw: dict   = {}  # BL-170: {song_id: float} Ziehung fuer Zufallssortierung
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # --- Zeile 1: Typ-Filter (RadioButtons) + optionaler Custom-Filter-Button ---
        filter_row = QHBoxLayout()
        filter_label = QLabel(_t("label_filter"))
        filter_label.setStyleSheet("font-weight: bold; font-size: 11px;")
        filter_row.addWidget(filter_label)
        self._filter_group = QButtonGroup(self)
        self._rb_all     = QRadioButton(_t("rb_all"))
        self._rb_pattern = QRadioButton(_t("rb_pattern"))
        self._rb_singing = QRadioButton(_t("rb_singing"))
        self._rb_other   = QRadioButton(_t("rb_other"))
        self._rb_all.setChecked(True)
        self._filter_group.addButton(self._rb_all,     0)
        self._filter_group.addButton(self._rb_pattern, 1)
        self._filter_group.addButton(self._rb_singing, 2)
        self._filter_group.addButton(self._rb_other,   3)
        filter_row.addWidget(self._rb_all)
        filter_row.addWidget(self._rb_pattern)
        filter_row.addWidget(self._rb_singing)
        filter_row.addWidget(self._rb_other)
        filter_row.addStretch()
        if self._show_custom_filter:
            self._btn_custom = QPushButton(_t("btn_custom_filter"))
            self._btn_custom.setToolTip(_t("tooltip_custom_filter"))
            self._btn_custom.clicked.connect(self._open_custom_filter_dialog)
            filter_row.addWidget(self._btn_custom)
        # idToggled feuert zweimal (checked + unchecked) — nur auf checked reagieren
        self._filter_group.idToggled.connect(
            lambda _bid, checked: self.sig_changed.emit() if checked else None)
        layout.addLayout(filter_row)

        # --- Custom-Filter-Checkbox-Zeile (BL-097, initial versteckt) ---
        if self._show_custom_filter:
            self._custom_row_widget = QWidget()
            custom_row = QHBoxLayout(self._custom_row_widget)
            custom_row.setContentsMargins(0, 2, 0, 2)
            custom_row.setSpacing(6)
            lbl_custom = QLabel(_t("custom_filter_row_label"))
            lbl_custom.setStyleSheet("font-size: 11px;")
            custom_row.addWidget(lbl_custom)
            self._custom_checkboxes: list = []
            for _i in range(CustomFilterDialog.MAX_SLOTS):
                chk = QCheckBox()
                chk.setChecked(True)
                chk.setVisible(False)
                chk.toggled.connect(lambda _: self.sig_changed.emit())
                self._custom_checkboxes.append(chk)
                custom_row.addWidget(chk)
            custom_row.addStretch()
            self._custom_row_widget.setVisible(False)
            layout.addWidget(self._custom_row_widget)

        # --- Zeile 2: Genre (optional) + Sortierung ---
        row2 = QHBoxLayout()
        row2.setSpacing(8)
        if self._show_genre:
            row2.addWidget(QLabel(_t("label_genre")))
            self._combo_genre = QComboBox()
            self._combo_genre.addItem(_t("all_genres"), 0)
            self._combo_genre.currentIndexChanged.connect(
                lambda _: self.sig_changed.emit())
            row2.addWidget(self._combo_genre, 1)
        else:
            self._combo_genre = None

        row2.addWidget(QLabel(_t("label_sort")))
        self._combo_sort = QComboBox()
        # Der Sortiermodus haengt an den SORT_*-Konstanten als userData, NICHT am
        # Index: "Empfehlung" ist optional, dadurch verschieben sich sonst alle
        # nachfolgenden Eintraege je nach show_recommendation.
        sort_items = [(_t("sort_alphabetical"),   self.SORT_ALPHA),
                      (_t("sort_quality"),        self.SORT_QUALITY),
                      (_t("sort_last_played"),    self.SORT_LAST_PLAYED)]
        if self._show_recommendation:
            sort_items.append((_t("sort_recommendation"), self.SORT_RECOMMENDATION))
        sort_items.append((_t("sort_date_added"), self.SORT_DATE_ADDED))
        # BL-170: Zufallssortierungen. Der gewichtete Zufall nutzt denselben
        # Score wie die Empfehlung, deshalb haengt er wie diese an
        # show_recommendation.
        sort_items.append((_t("sort_random"), self.SORT_RANDOM))
        if self._show_recommendation:
            sort_items.append((_t("sort_weighted_random"),
                               self.SORT_WEIGHTED_RANDOM))
        for text, mode in sort_items:
            self._combo_sort.addItem(text, mode)
        # Lieblings-Sortierung aus der INI vorauswaehlen (sort/default_mode).
        # Vor dem connect(), damit beim Aufbau kein sig_changed feuert. Modi, die
        # es in dieser Instanz nicht gibt (z.B. Empfehlung ohne
        # show_recommendation), fallen still auf den ersten Eintrag zurueck.
        if self._settings is not None:
            try:
                _def_mode = int(self._settings.value("sort/default_mode",
                                                     self.SORT_ALPHA))
            except (TypeError, ValueError):
                _def_mode = self.SORT_ALPHA
            _idx = self._combo_sort.findData(_def_mode)
            if _idx >= 0:
                self._combo_sort.setCurrentIndex(_idx)
        self._combo_sort.currentIndexChanged.connect(self._on_sort_changed)
        row2.addWidget(self._combo_sort, 1)

        # BL-113: Zufalls-Tiebreaker Toggle — geteilter INI-Eintrag
        # sort/random_tiebreaker (auch vom Evening Planner genutzt)
        self._chk_random_tb = QCheckBox(_t("chk_random_tiebreaker"))
        tb_checked = True
        if self._settings is not None:
            tb_checked = str(self._settings.value(
                "sort/random_tiebreaker", "true")).lower() == "true"
        self._chk_random_tb.setChecked(tb_checked)
        self._chk_random_tb.setToolTip(_t("tooltip_random_tiebreaker"))
        self._chk_random_tb.toggled.connect(self._on_random_tb_toggled)
        row2.addWidget(self._chk_random_tb)

        layout.addLayout(row2)

        # Checkbox ist bewusst IMMER schaltbar (Nutzerwunsch) — keine Ausgrauung
        # je Sort-Modus. Ob der Tiebreaker tatsaechlich greift, entscheidet die
        # Sort-Logik (use_tb), nicht der Enabled-Zustand.

        # --- Zeile 3: Suchfeld ---
        search_row = QHBoxLayout()
        search_row.setSpacing(8)
        search_label = QLabel(_t("label_search"))
        search_label.setStyleSheet("font-weight: bold; font-size: 11px;")
        search_row.addWidget(search_label)
        self.edit_search = QLineEdit()
        self.edit_search.setPlaceholderText(_t("search_placeholder"))
        self.edit_search.setClearButtonEnabled(True)
        self.edit_search.textChanged.connect(lambda _: self.sig_changed.emit())
        search_row.addWidget(self.edit_search, 1)
        layout.addLayout(search_row)

    # ---- Oeffentliche Properties ----

    @property
    def type_filter(self) -> int:
        """0 = Alle, 1 = Patter, 2 = Singing, 3 = Other."""
        return self._filter_group.checkedId()

    def set_type_filter(self, filter_id: int):
        """Setzt den Typ-Filter programmatisch (0 = Alle, 1 = Patter,
        2 = Singing, 3 = Other). Wirkt wie ein Klick auf den Radio-Button und loest
        ueber idToggled das sig_changed-Signal aus (Liste baut neu auf).
        No-op, wenn der gewuenschte Filter bereits aktiv ist — vermeidet
        einen ueberfluessigen Listen-Refresh."""
        btn = self._filter_group.button(filter_id)
        if btn is not None and not btn.isChecked():
            btn.setChecked(True)

    @property
    def sort_mode(self) -> int:
        mode = self._combo_sort.currentData()
        return self.SORT_ALPHA if mode is None else mode

    @property
    def search_text(self) -> str:
        return self.edit_search.text()

    @property
    def genre_id(self) -> int:
        if self._combo_genre is None:
            return 0
        return self._combo_genre.currentData() or 0

    def _on_sort_changed(self):
        """Sort-ComboBox geaendert: bei Umschalten auf eine Zufallssortierung neu
        mischen + Signal. Die Shuffle-Checkbox bleibt bewusst immer schaltbar;
        ob der Tiebreaker greift, entscheidet die Sort-Logik (use_tb)."""
        sm = self.sort_mode
        # BL-170: Beim Umschalten AUF eine Zufallssortierung neu mischen. Der
        # Tiebreaker-Cache bleibt unberuehrt — das sind zwei getrennte Dinge.
        if sm in (self.SORT_RANDOM, self.SORT_WEIGHTED_RANDOM):
            self._sort_draw.clear()
        self.sig_changed.emit()

    def reshuffle_random(self) -> bool:
        """Zieht die Zufallszahlen der Zufallssortierungen neu.

        No-op, wenn gerade keine der beiden Zufallssortierungen aktiv ist —
        bei einer deterministischen Sortierung gaebe es sonst nichts zu
        mischen. Gibt zurueck, ob tatsaechlich neu gemischt wurde.

        Gedacht fuer Aufrufer, die bewusst ein frisches Ergebnis wollen
        (Auto-Fill), im Gegensatz zum Cache-Verhalten von _draw(), das
        Tastendruck-Flackern verhindert.
        """
        if self.sort_mode not in (self.SORT_RANDOM, self.SORT_WEIGHTED_RANDOM):
            return False
        self._sort_draw.clear()
        return True

    def _on_random_tb_toggled(self, checked: bool):
        """Tiebreaker-Toggle: in geteiltem INI-Eintrag persistieren + Signal."""
        if self._settings is not None:
            self._settings.setValue("sort/random_tiebreaker", bool(checked))
        self.sig_changed.emit()

    # ---- Genre-Liste befuellen ----

    def set_genres(self, genres: list, current_id: int = 0):
        """Aktualisiert die Genre-ComboBox (no-op wenn show_genre=False)."""
        if self._combo_genre is None:
            return
        self._combo_genre.blockSignals(True)
        self._combo_genre.clear()
        self._combo_genre.addItem(_t("all_genres"), 0)
        restore_idx = 0
        for gid, gname in genres:
            self._combo_genre.addItem(gname, gid)
            if gid == current_id:
                restore_idx = self._combo_genre.count() - 1
        self._combo_genre.setCurrentIndex(restore_idx)
        self._combo_genre.blockSignals(False)

    # ---- BL-097: Custom-Playlist-Filter ----

    def _open_custom_filter_dialog(self):
        dlg = CustomFilterDialog(
            self._db, self._pl_dir, self._custom_slots,
            permanent_state=self._permanent_state, parent=self)
        if dlg.exec():
            self._custom_slots    = dlg.get_slots()
            self._permanent_state = dlg.get_permanent_state()
            self._save_permanent_filters()
            self._update_custom_row()
            self.sig_changed.emit()

    def _update_custom_row(self):
        if not self._show_custom_filter:
            return
        for i in range(CustomFilterDialog.MAX_SLOTS):
            slot = self._custom_slots[i]
            chk  = self._custom_checkboxes[i]
            if slot:
                chk.setText(slot["name"])
                chk.setChecked(True)
                chk.setVisible(True)
            else:
                chk.setVisible(False)
        has_any = any(s is not None for s in self._custom_slots)
        self._custom_row_widget.setVisible(has_any)

    def _get_active_custom_ids(self):
        """Gibt set der Song-IDs zurueck die alle aktiven Slots gemeinsam haben; None = kein Filter."""
        if not self._show_custom_filter:
            return None
        active = [
            self._custom_slots[i]
            for i, chk in enumerate(self._custom_checkboxes)
            if chk.isVisible() and chk.isChecked() and self._custom_slots[i] is not None
        ]
        if not active:
            return None
        ids = active[0]["song_ids"]
        for slot in active[1:]:
            ids = ids & slot["song_ids"]
        return ids

    def _save_permanent_filters(self):
        if not self._settings:
            return
        for i in range(CustomFilterDialog.MAX_SLOTS):
            key = f"custom-filter/slot_{i}"
            if self._permanent_state[i] and self._custom_slots[i] is not None:
                self._settings.setValue(key, self._custom_slots[i].get("filepath", ""))
            else:
                self._settings.setValue(key, "")
        self._settings.sync()

    def load_permanent_filters(self):
        """Liest permanente Custom-Filter aus INI und laedt sie als Slots.

        Wird beim ersten Oeffnen des Planners aufgerufen.
        No-op wenn show_custom_filter=False oder bereits geladen.
        """
        if not self._show_custom_filter or self._permanent_loaded or not self._settings:
            return
        self._permanent_loaded = True
        changed = False
        for i in range(CustomFilterDialog.MAX_SLOTS):
            fp = self._settings.value(f"custom-filter/slot_{i}", "")
            if not fp or not os.path.isfile(fp):
                continue
            try:
                try:
                    with open(fp, "r", encoding="utf-8") as f:
                        lines = f.readlines()
                except UnicodeDecodeError:
                    with open(fp, "r", encoding="cp1252") as f:
                        lines = f.readlines()
            except Exception:
                continue
            song_ids = set()
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                parts = line.split(" ", 2)
                if len(parts) < 2:
                    continue
                mode = parts[0].upper()
                if mode not in ("P", "S"):
                    mode = "P"
                filename = parts[2] if (len(parts) == 3 and parts[1].isdigit()) else \
                           (parts[1] + " " + parts[2]) if len(parts) == 3 else parts[1]
                song = self._db.get_by_title(filename) or self._db.get_by_filename(filename)
                if song:
                    song_ids.add(song.id)
            name = os.path.splitext(os.path.basename(fp))[0]
            self._custom_slots[i]    = {"name": name, "song_ids": frozenset(song_ids), "filepath": fp}
            self._permanent_state[i] = True
            changed = True
        if changed:
            self._update_custom_row()
            self.sig_changed.emit()

    # ---- Filter + Sortierung anwenden ----

    def filter_and_sort(self, songs: list, last_played_map: dict = None,
                        genre_song_ids: dict = None, start_date=None,
                        added_fallback=None) -> list:
        """Wendet alle aktiven Filter (inkl. Custom) und Sortierung auf songs an.

        added_fallback -- Datum, das Songs ohne date_added beim Sortieren nach
        Einfuegedatum erben (Erstaufnahme der Bibliothek). Bewusst getrennt von
        start_date: die Songliste braucht das Erbe-Datum, ihr "Tage seit zuletzt
        gespielt"-Fallback soll sich dadurch aber nicht mit aendern.
        """
        if last_played_map is None: last_played_map = {}
        if genre_song_ids  is None: genre_song_ids  = {}

        # Typ-Filter
        ft = self.type_filter
        if ft in _TYPE_BY_FILTER_ID:
            type_key = _TYPE_BY_FILTER_ID[ft]
            songs = [s for s in songs
                     if song_types.matches(s.is_pattern, s.is_singing, type_key)]

        # Genre-Filter
        gid = self.genre_id
        if gid:
            allowed = genre_song_ids.get(gid, set())
            songs = [s for s in songs if s.id in allowed]

        # Suchfeld-Filter
        search = self.search_text.strip().lower()
        if search:
            songs = [s for s in songs
                     if search in (s.title    or "").lower()
                     or search in (s.label    or "").lower()
                     or search in (s.filename or "").lower()]

        # Custom-Playlist-Filter (BL-097)
        custom_ids = self._get_active_custom_ids()
        if custom_ids is not None:
            songs = [s for s in songs if s.id in custom_ids]

        # Sortierung
        today = date.today()
        sd    = start_date or today
        af    = added_fallback or start_date or today

        def _days_since(song_id):
            return _reco_days_since(song_id, last_played_map, sd)

        # BL-113: Stabiler Zufalls-Tiebreaker — einmal pro Session zuweisen, dann cachen.
        # Die Checkbox ist immer schaltbar; der Tiebreaker greift aber nur bei
        # score-basierten Sortierungen mit moeglichen Gleichstaenden. In anderen
        # Modi (alphabetisch, Zufall) ist der Haken bewusst folgenlos.
        _tb_relevant = self.sort_mode in (self.SORT_QUALITY,
                                          self.SORT_RECOMMENDATION,
                                          self.SORT_DATE_ADDED)
        use_tb = self._chk_random_tb.isChecked() and _tb_relevant

        def _tb(song_id):
            if song_id not in self._sort_random:
                self._sort_random[song_id] = random.random()
            return self._sort_random[song_id] if use_tb else 0

        def _draw(song_id):
            """BL-170: gecachte Zufallszahl aus (0,1) fuer die Zufallssortierungen.

            Gecacht, damit Tippen im Suchfeld oder ein Genre-Wechsel die
            Reihenfolge nicht bei jedem Tastendruck neu wuerfelt. Neu gemischt
            wird beim Programmstart und beim Umschalten auf eine der beiden
            Zufallssortierungen (siehe _on_sort_changed).
            """
            u = self._sort_draw.get(song_id)
            if u is None:
                # random() kann 0.0 liefern — log(0) waere ein Fehler.
                u = random.random() or 1e-12
                self._sort_draw[song_id] = u
            return u

        def _added_ord(song):
            """Einfuegedatum als Ordinalzahl. Ohne Datum: Erstaufnahme-Datum aus
            der INI (playlist/start_date) — der migrierte Altbestand hat kein
            date_added, war aber zur Erstaufnahme bereits in der Bibliothek."""
            try:
                return date.fromisoformat(song.date_added[:10]).toordinal()
            except (ValueError, TypeError):
                return af.toordinal()

        sm = self.sort_mode
        if sm == self.SORT_ALPHA:
            songs = sorted(songs, key=lambda s: (s.title or s.filename).lower())
        elif sm == self.SORT_QUALITY:
            songs = sorted(songs, key=lambda s: (-s.quality, _tb(s.id)))
        elif sm == self.SORT_LAST_PLAYED:
            songs = sorted(songs, key=lambda s: -_days_since(s.id))
        elif sm == self.SORT_RECOMMENDATION:
            songs = sorted(songs, key=lambda s: (-(s.quality * _days_since(s.id)), _tb(s.id)))
        elif sm == self.SORT_DATE_ADDED:
            # Neueste Zugaenge zuerst.
            songs = sorted(songs, key=lambda s: (-_added_ord(s), _tb(s.id)))
        elif sm == self.SORT_RANDOM:
            # Reiner Zufall: jeder Song gleich wahrscheinlich.
            _t0 = perf_start()
            songs = sorted(songs, key=lambda s: _draw(s.id))
            perf_log(f"SongFilterBar.sort_random ({len(songs)} songs)", _t0)
        elif sm == self.SORT_WEIGHTED_RANDOM:
            # Gewichteter Zufall (Roulette-Wheel). Gewicht = Empfehlungs-Score
            # + 1, damit ein Score von 0 nicht Wahrscheinlichkeit 0 bedeutet.
            #
            # quality 0 heisst "noch nicht bewertet", nicht "schlecht". Mit dem
            # echten Wert 0 waere das Gewicht immer 1 und solche Songs kaemen
            # nie dran — sie koennten damit auch nie bewertet werden. Deshalb
            # zaehlt eine fehlende Bewertung HIER (und nur hier, nicht in der
            # Empfehlungs-Sortierung) als neutrale 5.
            #
            # Ein heute gespielter Song behaelt dagegen bewusst Gewicht 1: der
            # soll am selben Abend nicht nochmal drankommen.
            _t0 = perf_start()

            def _weight(s):
                q = s.quality if s.quality > 0 else _UNRATED_QUALITY
                # max(): ein in der Zukunft liegendes "zuletzt gespielt"
                # ergaebe negative Tage und damit ein negatives Gewicht.
                return max(1, q * _days_since(s.id) + 1)

            songs = _weighted_random_order(songs, _weight, _draw)
            perf_log(f"SongFilterBar.sort_weighted_random ({len(songs)} songs)", _t0)

        return songs


class SongListWidget(QWidget):
    """Songliste: Zeigt alle Songs mit 'Zuletzt gespielt' Spalte."""

    def __init__(self, db: SongDatabase, pl_dir: str = "", settings=None, parent=None):
        super().__init__(parent)
        self.db = db
        self._pl_dir = pl_dir
        self._settings = settings
        self.on_song_selected = None
        self.on_song_activated = None         # callback(song_id) — Doppelklick: laden + abspielen
        self.on_add_to_playlist = None        # callback(song_id)
        self.on_song_delete_requested = None  # callback(song_id)
        self.on_add_to_notes = None           # callback(song_title)
        self.on_song_rating_changed = None    # callback(song_id) — Quality/ERR ueber Kontextmenue geaendert
        self._all_songs = []
        self._filtered = []         # BL-206: aktuell gefilterte Liste (fuer Export)
        self._last_played_map = {}  # {song_id: "2026-03-08 20:30:00"}
        self._genre_song_ids = {}   # {genre_id: set(song_ids)} — gecacht, wird bei refresh() aktualisiert
        self._row_by_id = {}        # {song_id: row_index} — nach jedem _apply_filter aktuell
        self._playing_id = None     # song_id des aktuell spielenden Songs (Now-Playing-Highlight)
        self._date_format = "de"    # "de" oder "us"
        self._start_date = date.today()  # Erstaufnahme der Bibliothek (INI), s. set_start_date
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        self.label_count = QLabel(_t("songs_count", count=0))
        self.label_count.setStyleSheet("font-size: 13px; font-weight: bold;")
        layout.addWidget(self.label_count)

        # Gemeinsamer Filter-/Sortier-Header (BL-101 + BL-121)
        self._filter_bar = SongFilterBar(
            show_genre=True, show_recommendation=True,
            show_custom_filter=True, db=self.db,
            pl_dir=self._pl_dir, settings=self._settings, parent=self)
        self._filter_bar.sig_changed.connect(self._on_filter_changed)
        layout.addWidget(self._filter_bar)

        # QTableWidget statt QListWidget fuer 2 Spalten (Titel + Gespielt)
        self.table = QTableWidget()
        self.table.setColumnCount(2)
        self.table.setHorizontalHeaderLabels([_t("header_title"), _t("header_played")])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.cellClicked.connect(self._on_cell_clicked)
        self.table.cellDoubleClicked.connect(self._on_cell_double_clicked)
        self.table.installEventFilter(self)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._on_context_menu)
        layout.addWidget(self.table)

        _sl_btn_bar = _WrapButtonBar()
        btn_refresh = QPushButton(_t("btn_refresh_list"))
        btn_refresh.clicked.connect(self.refresh)
        _sl_btn_bar.add(btn_refresh)
        self._btn_to_notes = QPushButton(_t("btn_to_notes"))
        self._btn_to_notes.setToolTip(_t("btn_to_notes_tooltip_song"))
        self._btn_to_notes.clicked.connect(self._on_to_notes_clicked)
        _sl_btn_bar.add(self._btn_to_notes)
        self._btn_to_playlist = QPushButton(_t("btn_to_playlist"))
        self._btn_to_playlist.setToolTip(_t("tooltip_to_playlist_song"))
        self._btn_to_playlist.clicked.connect(self._on_to_playlist_clicked)
        _sl_btn_bar.add(self._btn_to_playlist)
        # BL-206: Export der DB-Daten der aktuell gefilterten Liste (JSON).
        self._btn_export = QPushButton(_t("sdio_export_btn"))
        self._btn_export.setToolTip(_t("sdio_export_btn_tip"))
        self._btn_export.clicked.connect(self._on_export_clicked)
        _sl_btn_bar.add(self._btn_export)
        layout.addWidget(_sl_btn_bar)

    def set_date_format(self, fmt: str):
        """Setzt das Datumsformat: 'de' fuer DD.MM.YY, 'us' fuer MM/DD/YY."""
        self._date_format = fmt

    def set_start_date(self, d: date):
        """Erstaufnahme-Datum der Bibliothek (INI playlist/start_date).

        Nur fuer die Sortierung/Anzeige nach Einfuegedatum: Songs aus der
        Migration haben kein date_added und erben dieses Datum.
        """
        self._start_date = d

    def _col1_role(self) -> str:
        """Was zeigt die zweite Tabellenspalte je nach Sortierung an?

        'added' beim Sortieren nach Einfuegedatum, 'score' bei der Empfehlung,
        sonst 'played' (Zuletzt-gespielt-Datum wie bisher). Kopf und Zellinhalt
        wandern so mit der Sortierung mit.
        """
        sm = self._filter_bar.sort_mode
        if sm == SongFilterBar.SORT_DATE_ADDED:
            return "added"
        if sm == SongFilterBar.SORT_RECOMMENDATION:
            return "score"
        return "played"

    def _col1_header(self) -> str:
        return {"added": _t("header_added"),
                "score": _t("header_score")}.get(self._col1_role(), _t("header_played"))

    def _added_cell(self, song):
        """(Anzeigetext, geerbt?) fuer die Spalte 'Hinzugefuegt'."""
        if song.date_added:
            return self._format_date(song.date_added), False
        return self._format_date(self._start_date.isoformat()), True

    def set_last_played_map(self, last_played_map: dict):
        """Aktualisiert die Zuletzt-Gespielt-Daten — schreibt nur geänderte Zeilen."""
        old_map = self._last_played_map
        self._last_played_map = last_played_map

        # Alle song_ids mit geändertem Wert (neu, entfernt oder geändert)
        changed = {sid for sid in set(old_map) | set(last_played_map)
                   if old_map.get(sid) != last_played_map.get(sid)}
        if not changed:
            return
        # Zeigt Spalte 1 gerade Einfuegedatum oder Score, gehoert sie nicht der
        # Last-Played-Anzeige — Map ist oben aktualisiert (fuer den naechsten
        # Moduswechsel), die Zellen bleiben unberuehrt.
        if self._col1_role() != "played":
            return

        for song_id in changed:
            row = self._row_by_id.get(song_id)
            if row is None:
                continue
            lp = last_played_map.get(song_id, "")
            date_display = self._format_date(lp) if lp else ""
            item_date = self.table.item(row, 1)
            if item_date:
                item_date.setText(date_display)
            else:
                item_date = QTableWidgetItem(date_display)
                item_date.setTextAlignment(Qt.AlignCenter)
                self.table.setItem(row, 1, item_date)

    def _format_date(self, iso_str: str) -> str:
        """Formatiert einen ISO-Datetime-String ins Kurzformat."""
        try:
            dt = datetime.fromisoformat(iso_str)
            if self._date_format == "us":
                return dt.strftime("%m/%d/%y")
            else:
                return dt.strftime("%d.%m.%y")
        except (ValueError, TypeError):
            return ""

    def refresh(self):
        _t0 = perf_start()
        self._all_songs = self.db.get_all()
        _t1 = perf_split("SongList.db.get_all", _t0)
        self._genre_song_ids = self.db.get_genre_song_ids()
        genres = self.db.get_all_genres()
        self._filter_bar.set_genres(genres, current_id=self._filter_bar.genre_id)
        self._apply_filter()
        perf_split(f"SongList._apply_filter ({len(self._all_songs)} songs)", _t1)

    def update_last_played(self, song_id: int, date_str: str):
        """Aktualisiert nur die Last-Played-Spalte fuer eine bestimmte Song-ID.

        Deutlich schneller als refresh() da kein DB-Fetch und kein Table-Rebuild.
        """
        self._last_played_map[song_id] = date_str
        if self._col1_role() != "played":
            return   # Spalte zeigt Einfuegedatum oder Score — nicht ueberschreiben
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item and item.data(Qt.UserRole) == song_id:
                date_display = self._format_date(date_str) if date_str else ""
                item_date = self.table.item(row, 1)
                if item_date:
                    item_date.setText(date_display)
                else:
                    item_date = QTableWidgetItem(date_display)
                    item_date.setTextAlignment(Qt.AlignCenter)
                    self.table.setItem(row, 1, item_date)
                break

    def _apply_filter(self):
        filtered = self._filter_bar.filter_and_sort(
            self._all_songs, self._last_played_map, self._genre_song_ids,
            start_date=self._start_date, added_fallback=self._start_date)
        # BL-206: aktuell gefilterte Liste fuer den Export merken.
        self._filtered = filtered

        # Die zweite Spalte wandert mit der Sortierung mit: Einfuegedatum bei
        # "Hinzugefuegt", der Empfehlungs-Score bei "Empfehlung", sonst das
        # Zuletzt-gespielt-Datum wie bisher.
        role = self._col1_role()
        self.table.setHorizontalHeaderLabels([_t("header_title"), self._col1_header()])

        self.table.setUpdatesEnabled(False)
        self.table.setRowCount(0)
        self.table.setRowCount(len(filtered))

        for row_idx, song in enumerate(filtered):
            display = song.title or song.filename
            # Typ-Kuerzel: P=Patter, S=Singing, PS=beides, O=Other
            display += f"  ({song_types.type_tag(song.is_pattern, song.is_singing)})"
            if song.label:
                display += f"  [{song.label}]"
            if song.quality > 0:
                display += f"  Q:{song.quality}"

            inherited = False
            tooltip = ""
            if role == "added":
                cell_text, inherited = self._added_cell(song)
            elif role == "score":
                cell_text = str(_reco_score(song, self._last_played_map, self._start_date))
                tooltip = _t("tooltip_score_col")
            else:
                last_played_str = self._last_played_map.get(song.id, "")
                cell_text = self._format_date(last_played_str) if last_played_str else ""

            item_title = QTableWidgetItem(display)
            item_title.setData(Qt.UserRole, song.id)
            item_title.setData(Qt.UserRole + 1, song.title or song.filename)
            self.table.setItem(row_idx, 0, item_title)

            item_date = QTableWidgetItem(cell_text)
            item_date.setTextAlignment(Qt.AlignCenter)
            _style_date_cell(item_date, inherited)
            if tooltip:
                item_date.setToolTip(tooltip)
            self.table.setItem(row_idx, 1, item_date)

        self._row_by_id = {
            self.table.item(r, 0).data(Qt.UserRole): r
            for r in range(self.table.rowCount())
            if self.table.item(r, 0)
        }
        # Nach dem Neuaufbau die native Selektion wieder auf den aktuellen Song
        # setzen — das IST das Highlight (Qt-Standard), kein eigenes Overlay.
        if self._playing_id is not None:
            row = self._row_by_id.get(self._playing_id)
            if row is not None:
                self.table.selectRow(row)
        self.table.setUpdatesEnabled(True)
        self.label_count.setText(_t("songs_count", count=len(self._all_songs)))

    def eventFilter(self, obj, event):
        if obj is self.table and event.type() == event.Type.KeyPress:
            if event.key() in (Qt.Key_Return, Qt.Key_Enter):
                row = self.table.currentRow()
                if row >= 0:
                    self._on_cell_clicked(row, 0)
                return True
            if event.key() == Qt.Key_Delete:
                row = self.table.currentRow()
                if row >= 0:
                    item = self.table.item(row, 0)
                    if item and self.on_song_delete_requested:
                        self.on_song_delete_requested(item.data(Qt.UserRole))
                return True
        return super().eventFilter(obj, event)

    def _on_filter_changed(self):
        self._apply_filter()

    def _on_cell_clicked(self, row, column):
        item = self.table.item(row, 0)
        if item:
            song_id = item.data(Qt.UserRole)
            if self.on_song_selected:
                self.on_song_selected(song_id)

    def _on_cell_double_clicked(self, row, column):
        """Doppelklick: Song laden UND direkt abspielen. Der Einfachklick
        (cellClicked) hat den Song bereits selektiert/geladen; hier folgt der
        Play-Start ueber den MainWindow-Callback."""
        item = self.table.item(row, 0)
        if item and self.on_song_activated:
            self.on_song_activated(item.data(Qt.UserRole))

    def set_playing_song(self, song_id):
        """Hebt den aktuell laufenden/gewaehlten Song hervor — ueber Qts native
        Zeilen-Selektion (Qt-Standard). Genau EINE Zeile ist markiert, sie
        wandert atomar. Bewusst KEIN zweites Highlight-System (setBackground)
        mehr darueber: das erzeugte frueher zwei Farben und ein Abschieds-Blau
        beim Wechsel, weil Overlay und Selektion nicht gleichzeitig umschalteten.
        Bei manuellem Klick selektiert Qt die Zeile selbst; hier folgt die
        Selektion zusaetzlich einem programmatisch gestarteten Song (Auto-Advance,
        Rule)."""
        self._playing_id = song_id
        row = self._row_by_id.get(song_id)
        if row is not None:
            self.table.selectRow(row)

    def _on_to_notes_clicked(self):
        title_item = self.table.item(self.table.currentRow(), 0)
        if title_item and self.on_add_to_notes:
            self.on_add_to_notes(title_item.data(Qt.UserRole + 1) or title_item.text())

    def _on_to_playlist_clicked(self):
        title_item = self.table.item(self.table.currentRow(), 0)
        if title_item and self.on_add_to_playlist:
            self.on_add_to_playlist(title_item.data(Qt.UserRole))

    def _on_export_clicked(self):
        """BL-206: DB-Daten der aktuell gefilterten Liste als JSON exportieren."""
        song_data_io.export_songs_interactive(self, self.db, self._filtered)

    def _on_context_menu(self, pos):
        item = self.table.itemAt(pos)
        if not item:
            return
        row = self.table.row(item)
        title_item = self.table.item(row, 0)
        if not title_item:
            return
        song_id = title_item.data(Qt.UserRole)
        clean_title = title_item.data(Qt.UserRole + 1) or title_item.text()
        menu = QMenu(self)
        act_notes = menu.addAction(_t("ctx_add_to_notes"))
        act_notes.triggered.connect(
            lambda: self.on_add_to_notes(clean_title) if self.on_add_to_notes else None)
        act_pl = menu.addAction(_t("ctx_add_to_playlist"))
        act_pl.triggered.connect(
            lambda: self.on_add_to_playlist(song_id) if self.on_add_to_playlist else None)
        def _after_rating():
            self.refresh()
            if self.on_song_rating_changed:
                self.on_song_rating_changed(song_id)
        add_song_rating_actions(menu, self.db, song_id, refresh_callback=_after_rating)
        menu.exec(self.table.viewport().mapToGlobal(pos))
