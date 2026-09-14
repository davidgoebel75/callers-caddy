"""Sequenzen-UI fuer Callers Caddy (BL-201, aus main.py ausgelagert).

Enthaelt Sequenz-Ansicht/-Verwaltung, Import- und Editor-Dialoge sowie den
Call-Mapping-Dialog. Zirkelfrei: keine Rueckbezuege auf main.py.
"""

import os
import re
import sys
import random

from PySide6.QtWidgets import (
    QApplication, QWidget, QHBoxLayout, QVBoxLayout,
    QPushButton, QLabel, QFileDialog, QGroupBox,
    QFrame, QCheckBox, QLineEdit, QFormLayout,
    QTableWidget, QTableWidgetItem, QHeaderView, QComboBox,
    QMessageBox, QDialog, QMenu, QAbstractItemView,
    QTextBrowser, QTextEdit, QPlainTextEdit, QListWidget, QListWidgetItem,
)
from PySide6.QtCore import Qt, QTimer, QSettings, QEvent, QObject
from PySide6.QtGui import (
    QIcon, QColor, QSyntaxHighlighter, QTextCharFormat,
    QFont, QFontMetrics, QKeySequence, QShortcut,
)

from song_db import calls_to_json
from i18n import _t
from ui_helpers import mark_toggle, widen_combo_popup
from zoom_wheel import install_ctrl_wheel_zoom
from perf import perf_start, perf_log, perf_split
from sequence_mapper import CallMatcher as _CallMatcher


class _ComboClickToOpen(QObject):
    """Event-Filter: Klick ins editierbare Combo oeffnet die Auswahlliste.

    Editierbare QComboBox oeffnen ihr Popup sonst NUR ueber den schmalen
    Dropdown-Pfeil (ein Klick ins Textfeld setzt nur den Cursor). Das wirkt wie
    ein kaputtes/leeres Feld. Damit oeffnet ein Klick irgendwo ins Feld die
    Liste — wie bei nicht-editierbaren Combos; Tippen zum Suchen bleibt moeglich.
    """

    def __init__(self, combo):
        super().__init__(combo)
        self._combo = combo

    def eventFilter(self, obj, event):
        if (event.type() == QEvent.MouseButtonPress
                and not self._combo.view().isVisible()):
            # Klick kommt beim QLineEdit an, nicht bei der Combobox — der
            # App-Filter im Hauptfenster verbreitert hier also nicht
            widen_combo_popup(self._combo)
            self._combo.showPopup()
            return True
        return super().eventFilter(obj, event)


def install_combo_click_to_open(combo):
    """Macht ein editierbares QComboBox per Klick ins Feld aufklappbar."""
    line_edit = combo.lineEdit()
    if line_edit is not None:
        combo._click_to_open = _ComboClickToOpen(combo)  # Referenz halten
        line_edit.installEventFilter(combo._click_to_open)


class SequenceViewWidget(QWidget):
    """Sequenz-Detail-Ansicht als QWidget für QDockWidget-Integration.

    Zeigt eine einzelne Sequenz mit Auto-Zoom und Vor/Zurück-Navigation.
    Wird von SequencesWidget über on_open_detail gesteuert.
    """

    def __init__(self, db, skin_mgr=None):
        super().__init__()
        self._db = db
        self._skin_mgr = skin_mgr
        self._seq_ids = []
        self._current_idx = 0
        self._calls = []
        # BL-182: Zufalls-Modus (Würfel). Wenn aktiv, springt „Weiter" (Button,
        # Pfeiltaste, Dynamic-Lyrics-advance) zu einer zufälligen anderen Sequenz
        # aus der aktuell gefilterten Liste — Ziehen ohne Zurücklegen. Das
        # Session-Gedächtnis merkt sich bereits gezeigte Sequenz-IDs; ist der
        # Pool erschöpft, wird er STILL (ohne Meldung) erneuert.
        self._random_mode = False
        self._seen_ids = set()
        self.on_add_to_notes = None   # callback(seq_id)
        self.on_edit_sequence = None  # callback(seq_id) → Editor oeffnen
        self.on_delete_sequence = None  # callback(seq_id) → Sequenz loeschen
        # BL-173: Callback, wenn sich die Sequenzliste aendert (fuer das Gating
        # des Dynamic-Lyrics-Buttons im Lyrics-Widget).
        self.on_sequences_changed = None
        # BL-173: Callback, wenn sich die AKTUELL gezeigte Sequenz aendert
        # (Auto-Blaettern durch Dynamic Lyrics oder Nutzer-Navigation). Das
        # Lyric-Widget spiegelt daraufhin die neue Sequenz.
        self.on_current_sequence_changed = None
        self.setMinimumWidth(200)
        self.setMinimumHeight(100)
        self._build_ui()

    def _text_color(self) -> str:
        if self._skin_mgr:
            return self._skin_mgr.color("text", "#f0f0f0")
        return "#f0f0f0"

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.setContentsMargins(8, 8, 8, 8)

        # BL-189: Header-Zeile mit Sequenz-Typ und Schwierigkeit der aktuell
        # gezeigten Sequenz. Zeigt auf einen Blick, um was fuer eine Sequenz es
        # sich handelt — auch ohne aktiven Filter im Sequenzen-Widget.
        self._lbl_header = QLabel()
        self._lbl_header.setAlignment(Qt.AlignCenter)
        # Farbe per StyleSheet, Schriftgroesse per QFont (wird in
        # _recalc_header_font dynamisch an die Breite angepasst).
        self._lbl_header.setStyleSheet(f"color: {self._text_color()};")
        self._header_text = ""
        layout.addWidget(self._lbl_header)

        # QTextEdit: Qt handhabt Wrapping, Zeilenhoehe und Unterlaengen korrekt
        self._text_edit = QTextEdit()
        self._text_edit.setReadOnly(True)
        self._text_edit.setFrameShape(QFrame.NoFrame)
        self._text_edit.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._text_edit.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        layout.addWidget(self._text_edit, 1)

        nav_layout = QHBoxLayout()
        _NAV_H = 40  # Einheitliche Hoehe fuer alle Nav-Buttons

        self._btn_prev = QPushButton("◀")
        self._btn_prev.setFixedSize(44, _NAV_H)
        self._btn_prev.setStyleSheet("font-size: 16px; padding: 0px;")
        self._btn_prev.setToolTip(_t("seq_nav_prev_tooltip"))
        self._btn_prev.clicked.connect(self._on_prev)

        self._lbl_pos = QLabel()
        self._lbl_pos.setAlignment(Qt.AlignCenter)
        self._lbl_pos.setStyleSheet(f"font-size: 12px; color: {self._text_color()};")

        # BL-182: Würfel-Toggle. Ist er aktiv, springt „Weiter" zu einer
        # zufälligen passenden Sequenz statt zur nächsten in der Reihenfolge.
        self._btn_random = QPushButton("🎲")
        self._btn_random.setFixedSize(44, _NAV_H)
        mark_toggle(self._btn_random, active=True)
        # Nur Groesse/Font inline; die Aktiv-Faerbung (gruen) kommt themebar
        # ueber die QSS-Regel [activeState="true"]:checked (Skin-Token success),
        # damit alle Aktiv-Toggles dieselbe Farbe teilen (Gestaltprinzip).
        self._btn_random.setStyleSheet(
            "QPushButton { font-size: 16px; padding: 0px; }")
        self._btn_random.setToolTip(_t("seq_nav_random_tooltip"))
        self._btn_random.toggled.connect(self._on_random_toggled)

        self._btn_next = QPushButton("▶")
        self._btn_next.setFixedSize(44, _NAV_H)
        self._btn_next.setStyleSheet("font-size: 16px; padding: 0px;")
        self._btn_next.setToolTip(_t("seq_nav_next_tooltip"))
        self._btn_next.clicked.connect(self._on_next)

        self._btn_to_notes = QPushButton(_t("btn_to_notes"))
        self._btn_to_notes.setFixedHeight(_NAV_H)
        self._btn_to_notes.setToolTip(_t("btn_to_notes_tooltip_seq"))
        self._btn_to_notes.clicked.connect(self._on_to_notes)

        self._btn_edit = QPushButton(_t("seq_edit_change_btn"))
        self._btn_edit.setFixedHeight(_NAV_H)
        self._btn_edit.setToolTip(_t("seq_editor_edit_tooltip"))
        self._btn_edit.clicked.connect(self._on_edit)

        self._btn_delete = QPushButton(_t("btn_delete_sequence"))
        self._btn_delete.setFixedHeight(_NAV_H)
        self._btn_delete.setToolTip(_t("btn_delete_sequence_tooltip"))
        self._btn_delete.clicked.connect(self._on_delete)

        nav_layout.addWidget(self._btn_prev)
        nav_layout.addStretch()
        nav_layout.addWidget(self._lbl_pos)
        nav_layout.addStretch()
        nav_layout.addWidget(self._btn_edit)
        nav_layout.addWidget(self._btn_to_notes)
        nav_layout.addWidget(self._btn_delete)
        nav_layout.addWidget(self._btn_random)
        nav_layout.addWidget(self._btn_next)
        layout.addLayout(nav_layout)

    def set_sequence(self, db, seq_ids: list, current_idx: int):
        """Setzt neue Sequenzliste und aktuellen Index."""
        _t0 = perf_start()
        self._db = db
        self._seq_ids = seq_ids
        self._current_idx = current_idx
        if seq_ids:
            # Buttons reaktivieren (koennten durch _show_empty deaktiviert sein)
            self._btn_delete.setEnabled(True)
            self._btn_edit.setEnabled(True)
            self._btn_to_notes.setEnabled(True)
        self._update_content()
        _pt = perf_split(f"SeqView.set_sequence: update_content (list={len(seq_ids)})", _t0)
        self._notify_sequences_changed()
        self._notify_current_sequence_changed()
        perf_log("SeqView.set_sequence: TOTAL", _t0)

    def current_calls(self) -> list:
        """BL-173: Call-Zeilen der AKTUELL gezeigten Sequenz (fuer Dynamic Lyrics).
        Nutzt den bereits geladenen Cache self._calls — kein DB-Zugriff."""
        return [c[1] for c in self._calls if c and len(c) > 1 and c[1]]

    def advance(self):
        """BL-173: Blaettert eine Sequenz weiter (wie der Weiter-Button). Wird von
        Dynamic Lyrics an jeder Figuren-Teil-Grenze aufgerufen.

        BL-182: Ist der Würfel-Modus aktiv, wird stattdessen zu einer zufälligen
        passenden Sequenz gesprungen (Ziehen ohne Zurücklegen, stille Pool-
        Erneuerung). Im normalen Modus passiert am Listenende nichts mehr.
        """
        if not self._seq_ids:
            return
        if self._random_mode:
            self._go_random()
            return
        if self._current_idx >= len(self._seq_ids) - 1:
            return
        self._current_idx += 1
        self._update_content()
        self._notify_current_sequence_changed()

    def _notify_sequences_changed(self):
        if callable(self.on_sequences_changed):
            try:
                self.on_sequences_changed()
            except Exception:
                pass

    def _notify_current_sequence_changed(self):
        """BL-173: Schnittstelle → Lyric-Widget: die gezeigte Sequenz hat sich
        geaendert (Auto-Blaettern oder Nutzer-Navigation)."""
        if callable(self.on_current_sequence_changed):
            try:
                self.on_current_sequence_changed()
            except Exception:
                pass

    def _make_html(self, font_size: int) -> str:
        """Rendert Calls als HTML mit gegebener Schriftgrösse.

        Nutzt <br> statt Block-Elemente, damit Qt kein extra Inter-Block-Spacing einfuegt.
        """
        badge_size = max(9, min(11, font_size // 4))
        # Optionaler Treffer-Highlight: nur gesetzt, wenn das Widget als
        # "Beispiel-Betrachter" (Call-Mapping -> Beispiel zeigen) genutzt wird.
        # Der normale Dock setzt das Attribut nie -> keine Verhaltensaenderung.
        hl = getattr(self, "_highlight_text", None)
        parts = []
        for i, (_pos, call_text, entity_id, _to, _canonical, program) in enumerate(self._calls):
            if entity_id and program:
                badge = (f'&nbsp;<span style="font-size:{badge_size}px;color:#aaa;'
                         f'border:1px solid #666;padding:1px 3px;'
                         f'border-radius:2px;">{program}</span>')
            elif entity_id is None:
                badge = '&nbsp;<span style="font-size:10px;color:#ff6666;font-style:italic;">?</span>'
            else:
                badge = ""
            sep = "<br>" if i < len(self._calls) - 1 else ""
            if hl and call_text == hl:
                label = (f'<span style="background-color:#ffd54a;color:#212529;">'
                         f'{call_text}</span>')
            else:
                label = call_text
            parts.append(f'<b>{label}</b>{badge}{sep}')
        text_color = self._text_color()
        return (f'<span style="font-size:{font_size}px;color:{text_color};">'
                + "".join(parts) + '</span>')

    def _recalc_font_size(self):
        """Passt Schriftgrösse so an, dass alle Calls die verfügbare Höhe füllen.

        Ueberlauf wird NIE toleriert: nach einer proportionalen Startschaetzung
        wird die Schrift sicher verkleinert, bis das gesamte Dokument in die
        verfuegbare Hoehe passt. Sonst schnitt die frueher genutzte 8-%-Toleranz
        bei grosser Schrift die letzte Zeile halb ab.
        """
        n = len(self._calls)
        if n == 0:
            return
        available = self._text_edit.height()
        self._text_edit.document().setDocumentMargin(2)
        if available < 20:
            self._text_edit.setHtml(self._make_html(14))
            return

        # Sicherheitsabstand, damit die Unterlaengen der letzten Zeile Platz haben.
        target = available - 6

        # 1) Startschaetzung aus der Zeilenzahl.
        font_size = max(10, min(72, int(available / (n * 1.2))))
        self._text_edit.setHtml(self._make_html(font_size))

        # 2) Eine proportionale Korrektur Richtung Ziel (fuellt auch Freiraum aus).
        doc_h = self._text_edit.document().size().height()
        if doc_h > 0:
            font_size = max(10, min(72, int(font_size * target / doc_h)))
            self._text_edit.setHtml(self._make_html(font_size))

        # 3) Sicher verkleinern, bis wirklich nichts mehr ueberlaeuft. Die
        #    Startschaetzung liegt meist schon nah dran, daher wenige Schritte.
        guard = 0
        while (font_size > 10 and guard < 12
               and self._text_edit.document().size().height() > target):
            font_size -= 1
            self._text_edit.setHtml(self._make_html(font_size))
            guard += 1

    def _update_header(self, seq_id: int):
        """BL-189: Fuellt die Header-Zeile mit Typ und Schwierigkeit der Sequenz.

        Leere Werte werden weggelassen; ist gar nichts gesetzt, bleibt die Zeile
        leer (nimmt dann kaum Platz weg)."""
        raw = self._db.get_sequence_raw(seq_id) or {}
        seq_type = (raw.get("seq_type") or "").strip()
        difficulty = (raw.get("difficulty") or "").strip()
        parts = []
        if seq_type:
            parts.append(f"{_t('header_type')}: {seq_type}")
        if difficulty:
            parts.append(f"{_t('header_difficulty')}: {difficulty}")
        self._header_text = "   ·   ".join(parts)
        self._lbl_header.setText(self._header_text)
        self._recalc_header_font()

    def _recalc_header_font(self):
        """BL-189: Passt die Schriftgroesse der Header-Zeile so an, dass der Text
        die verfuegbare Breite des Widgets gut ausfuellt und damit gut lesbar ist.

        Sucht per QFontMetrics die groesste Schrift (in Grenzen), bei der der Text
        noch in die Breite passt, und wendet sie ueber das StyleSheet an. Wichtig:
        das Widget hat ein StyleSheet (Farbe), daher wird `setFont()` von Qt
        ignoriert — die Groesse MUSS per `font-size` im StyleSheet gesetzt werden.
        Leerer Header → nichts zu tun."""
        if not self._header_text:
            self._lbl_header.setStyleSheet(f"color: {self._text_color()};")
            return
        avail = self._lbl_header.width() - 8  # kleiner Sicherheitsrand
        if avail < 20:
            return
        font = QFont(self._lbl_header.font())
        best = 11
        # 11..40 px sind ein sinnvoller Rahmen fuer eine einzeilige Info-Zeile.
        for size in range(11, 41):
            font.setPixelSize(size)
            if QFontMetrics(font).horizontalAdvance(self._header_text) <= avail:
                best = size
            else:
                break
        self._lbl_header.setStyleSheet(
            f"color: {self._text_color()}; font-size: {best}px;")

    def _update_content(self):
        if not self._seq_ids:
            self._text_edit.clear()
            self._lbl_header.setText("")
            self._lbl_pos.setText("")
            self._btn_prev.setEnabled(False)
            self._btn_next.setEnabled(False)
            return
        seq_id = self._seq_ids[self._current_idx]
        self._update_header(seq_id)
        self._lbl_pos.setText(f"{self._current_idx + 1} / {len(self._seq_ids)}")
        self._btn_prev.setEnabled(self._current_idx > 0)
        # BL-182: Im Würfel-Modus bleibt „Weiter" immer aktiv (solange mehr als
        # eine Sequenz vorhanden ist) — auch am nominellen Listenende, weil dann
        # zufällig gesprungen wird.
        if self._random_mode:
            self._btn_next.setEnabled(len(self._seq_ids) > 1)
        else:
            self._btn_next.setEnabled(self._current_idx < len(self._seq_ids) - 1)
        self._calls = self._db.get_sequence_calls(seq_id)
        self._recalc_font_size()
        # Nochmal nach erstem Layout-Pass, damit height()/width() korrekt ist
        QTimer.singleShot(0, self._recalc_font_size)
        QTimer.singleShot(0, self._recalc_header_font)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._recalc_header_font()
        self._recalc_font_size()

    def _on_prev(self):
        if self._current_idx > 0:
            self._current_idx -= 1
            self._update_content()
            self._notify_current_sequence_changed()

    def _on_next(self):
        # BL-182: Würfel-Modus → zufälliger Sprung statt index+1.
        if self._random_mode:
            self._go_random()
            return
        if self._current_idx < len(self._seq_ids) - 1:
            self._current_idx += 1
            self._update_content()
            self._notify_current_sequence_changed()

    def _on_random_toggled(self, checked: bool):
        """BL-182: Würfel-Modus an/aus. Beim Einschalten wird das Session-
        Gedächtnis zurückgesetzt und die aktuell gezeigte Sequenz als bereits
        gesehen vorgemerkt, damit sie nicht sofort erneut gezogen wird."""
        self._random_mode = checked
        if checked:
            self._seen_ids = set()
            if self._seq_ids and 0 <= self._current_idx < len(self._seq_ids):
                self._seen_ids.add(self._seq_ids[self._current_idx])
        # Next-Button-Zustand an den neuen Modus anpassen.
        if self._seq_ids:
            self._update_content()

    def _go_random(self):
        """BL-182: Springt zu einer zufälligen anderen Sequenz aus der aktuell
        gefilterten Liste. Ziehen ohne Zurücklegen: in dieser Session bereits
        gezeigte Sequenzen werden übersprungen. Ist der Pool erschöpft, wird er
        STILL erneuert (keine Meldung) — wichtig für den Live-Betrieb und für
        Dynamic Lyrics im Singing Call, wo ein Dialog stören würde."""
        n = len(self._seq_ids)
        if n == 0:
            return
        if n == 1:
            # Nur eine Sequenz: nichts zu würfeln, aber Spiegelung anstoßen.
            self._current_idx = 0
            self._seen_ids = {self._seq_ids[0]}
            self._update_content()
            self._notify_current_sequence_changed()
            return
        pool = [i for i in range(n)
                if self._seq_ids[i] not in self._seen_ids and i != self._current_idx]
        if not pool:
            # Pool erschöpft → still erneuern; aktuelle Sequenz weiter ausschließen.
            self._seen_ids = set()
            pool = [i for i in range(n) if i != self._current_idx]
        self._current_idx = random.choice(pool)
        self._seen_ids.add(self._seq_ids[self._current_idx])
        self._update_content()
        self._notify_current_sequence_changed()

    def random_start(self):
        """BL-182: Waehlt eine zufaellige START-Sequenz, wenn der Zufallsmodus an ist
        — fuer den Dynamic-Lyrics-Start, damit auch die ERSTE Sequenz gemischt ist
        (statt immer der deterministischen Nr. 1). Respektiert und FUEHRT das
        Session-Gedaechtnis (_seen_ids) fort: gezogen wird aus den noch nicht
        gesehenen Sequenzen; ist der Pool erschoepft, wird er still erneuert.
        No-Op, wenn Zufall aus ist oder die Liste leer ist."""
        n = len(self._seq_ids)
        if not self._random_mode or n == 0:
            return
        pool = [i for i in range(n) if self._seq_ids[i] not in self._seen_ids]
        if not pool:
            # Alles in dieser Session schon gehabt -> still erneuern.
            self._seen_ids = set()
            pool = list(range(n))
        self._current_idx = random.choice(pool)
        self._seen_ids.add(self._seq_ids[self._current_idx])
        self._update_content()
        self._notify_current_sequence_changed()

    def sync_pool(self, seq_ids: list):
        """BL-182: Aktualisiert die gefilterte Sequenzliste (den Zufalls-Pool)
        auf den uebergebenen Stand, OHNE die Anzeige zu resetten und OHNE das
        Session-Gedaechtnis (_seen_ids) zu verwerfen.

        Wird vor dem per-Regel ausgeloesten Zufallssprung gerufen, damit dieser
        sich garantiert an die aktuell eingestellten Filter haelt — auch wenn
        der Live-Sync (on_filter_changed_detail) bei verstecktem Dock nicht
        gegriffen hat. Ids, die nicht mehr im Filter sind, fallen aus _seen_ids
        heraus; die gerade gezeigte Sequenz behaelt (falls noch enthalten) ihren
        Index, damit sie beim naechsten Zug korrekt ausgeschlossen bleibt."""
        if seq_ids == self._seq_ids:
            return
        cur_id = (self._seq_ids[self._current_idx]
                  if 0 <= self._current_idx < len(self._seq_ids) else None)
        self._seq_ids = seq_ids
        self._seen_ids = {sid for sid in self._seen_ids if sid in seq_ids}
        if cur_id in seq_ids:
            self._current_idx = seq_ids.index(cur_id)
        else:
            self._current_idx = 0

    def _on_to_notes(self):
        if self._seq_ids and self.on_add_to_notes:
            self.on_add_to_notes(self._seq_ids[self._current_idx])

    def _on_edit(self):
        if self._seq_ids and self.on_edit_sequence:
            self.on_edit_sequence(self._seq_ids[self._current_idx])

    def _on_delete(self):
        """Loescht die aktuelle Sequenz nach Rueckfrage."""
        if not self._seq_ids or not self.on_delete_sequence:
            return
        seq_id = self._seq_ids[self._current_idx]
        reply = QMessageBox.question(
            self, _t("delete_sequence_title"),
            _t("confirm_delete_sequence_one"),
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return
        self.on_delete_sequence(seq_id)

    def remove_id_after_delete(self, seq_id: int):
        """Wird vom Hauptfenster aufgerufen, nachdem eine Sequenz geloescht
        wurde. Springt zur naechsten (oder vorherigen) Sequenz in der Liste.
        """
        if seq_id not in self._seq_ids:
            return
        idx = self._seq_ids.index(seq_id)
        self._seq_ids.pop(idx)
        if not self._seq_ids:
            self._current_idx = 0
            self._show_empty()
            return
        # Nach Loeschen: gleichen Index halten = naechste anzeigen.
        # Wenn am Ende, eins zurueck.
        if idx >= len(self._seq_ids):
            self._current_idx = len(self._seq_ids) - 1
        else:
            self._current_idx = idx
        self._update_content()

    def _show_empty(self):
        """Leert die Anzeige nach Loeschen der letzten Sequenz."""
        self._calls = []
        self._text_edit.setPlainText("")
        self._lbl_pos.setText("0 / 0")
        self._btn_prev.setEnabled(False)
        self._btn_next.setEnabled(False)
        self._btn_delete.setEnabled(False)
        self._btn_edit.setEnabled(False)
        self._btn_to_notes.setEnabled(False)
        self._notify_sequences_changed()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Left:
            self._on_prev()
        elif event.key() == Qt.Key_Right:
            self._on_next()
        else:
            super().keyPressEvent(event)


class SequencesWidget(QWidget):
    """Sequenzen-Fenster: Anzeige und Filterung von Singing-Call-Sequenzen.

    Features:
      - Contains-Filter (Autocomplete: welcher Call ist enthalten)
      - Limit-Filter (Programm-Level: nur Sequenzen bis zu diesem Level)
      - Lazy Loading (50er-Bloecke)
      - Zoom [-/+] mit Prozentanzeige (wie LyricsWidget)
      - Remapping-Button (Zahnrad)
      - Klick auf Zeile: SequenceViewWidget im Dock aktualisieren
    """

    _PAGE_SIZE = 50   # Lazy Loading: Bloecke a 50 Zeilen

    def __init__(self, db, skin_mgr=None, settings=None):
        super().__init__()
        self.db = db
        self._skin_mgr = skin_mgr
        self._settings = settings  # QSettings fuer Voreinstellungen (optional)
        self._zoom_pct = 100       # Zoom-Prozent
        self._total_count = 0      # Gesamtanzahl (gefiltert)
        self._loaded_count = 0     # Bisher geladene Zeilen
        self._program_bands = None # MS50: Band-Menge der aktuellen Lokation (Mengen-Filter)
        self.on_open_detail = None           # callback(seq_ids, current_idx) → setzt SequenceViewWidget
        self.on_filter_changed_detail = None  # callback() → Filter geaendert, Dock zuruecksetzen
        self.on_add_to_notes = None           # callback(seq_id)
        self.on_add_filter_to_notes = None    # callback() → aktive Filter als Shortcode
        self.on_sequences_deleted = None      # callback(seq_ids) → SequenceView informieren
        self._loading = False      # Schutz gegen Endlos-Nachladen
        # BL-190: Teaching-Order-Grenze des aktuell gewaehlten Tanzprogramms.
        # Steuert nur die Sortierung der Contains-Vorschlaege (Programm-Calls
        # zuerst), kein harter Filter. None = keine Programm-Sortierung.
        self._program_sort_to = None

        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)

        # --- Toolbar: Zoom [-][+] + Prozent + Zahnrad ---
        toolbar = QHBoxLayout()
        toolbar.setSpacing(4)

        skin_dir = ""
        if self._skin_mgr and self._skin_mgr.icon_dir:
            skin_dir = self._skin_mgr.icon_dir.replace("\\", "/")

        self._btn_zoom_out = QPushButton()
        self._btn_zoom_out.setFixedSize(28, 28)
        self._btn_zoom_out.setToolTip(_t("tooltip_zoom_out"))
        if skin_dir:
            self._btn_zoom_out.setIcon(QIcon(f"{skin_dir}/zoom-out.svg"))
        else:
            self._btn_zoom_out.setText("\u2212")
        self._btn_zoom_out.clicked.connect(self._on_zoom_out)
        toolbar.addWidget(self._btn_zoom_out)

        self._label_zoom = QLabel("100%")
        self._label_zoom.setAlignment(Qt.AlignCenter)
        self._label_zoom.setFixedWidth(44)
        self._label_zoom.setStyleSheet("font-size: 11px;")
        toolbar.addWidget(self._label_zoom)

        self._btn_zoom_in = QPushButton()
        self._btn_zoom_in.setFixedSize(28, 28)
        self._btn_zoom_in.setToolTip(_t("tooltip_zoom_in"))
        if skin_dir:
            self._btn_zoom_in.setIcon(QIcon(f"{skin_dir}/zoom-in.svg"))
        else:
            self._btn_zoom_in.setText("+")
        self._btn_zoom_in.clicked.connect(self._on_zoom_in)
        toolbar.addWidget(self._btn_zoom_in)

        toolbar.addStretch()

        self._btn_seq_to_notes = QPushButton(_t("btn_to_notes"))
        self._btn_seq_to_notes.setToolTip(_t("btn_to_notes_tooltip_seq"))
        self._btn_seq_to_notes.clicked.connect(self._on_seq_to_notes)
        toolbar.addWidget(self._btn_seq_to_notes)

        self._btn_filter_to_notes = QPushButton(_t("btn_filter_to_notes"))
        self._btn_filter_to_notes.setToolTip(_t("btn_filter_to_notes_tooltip"))
        self._btn_filter_to_notes.clicked.connect(self._on_filter_to_notes)
        toolbar.addWidget(self._btn_filter_to_notes)

        self._btn_gear = QPushButton()
        self._btn_gear.setFixedSize(28, 28)
        self._btn_gear.setToolTip(_t("tooltip_remapping"))
        if skin_dir:
            self._btn_gear.setIcon(QIcon(f"{skin_dir}/gear.svg"))
        else:
            self._btn_gear.setText("\u2699")
        self._btn_gear.clicked.connect(self._on_remapping)
        toolbar.addWidget(self._btn_gear)

        layout.addLayout(toolbar)

        # --- Filter: Enthaelt + Limit ---
        filter_layout = QHBoxLayout()
        filter_layout.setSpacing(8)

        filter_layout.addWidget(QLabel(_t("label_contains")))
        self._combo_contains = QComboBox()
        self._combo_contains.setEditable(True)
        self._combo_contains.setInsertPolicy(QComboBox.NoInsert)
        self._combo_contains.setToolTip(_t("tooltip_contains"))
        self._combo_contains.currentIndexChanged.connect(self._on_filter_changed)
        # Editierbar (Tippen zum Suchen in ~580 Calls), aber ein Klick IRGENDWO
        # ins Feld oeffnet die Liste — wie bei den nicht-editierbaren Filtern.
        install_combo_click_to_open(self._combo_contains)
        # BL-190: Substring-Suche (nicht nur Wortanfang) + Clear-Button (x).
        self._setup_search_combo(self._combo_contains)
        filter_layout.addWidget(self._combo_contains, 1)

        filter_layout.addWidget(QLabel(_t("label_limit")))
        self._combo_limit = QComboBox()
        self._combo_limit.setToolTip(_t("tooltip_limit"))
        # BL-190: Limit ebenfalls als Suchfeld mit Substring-Vorschlaegen.
        self._combo_limit.setEditable(True)
        self._combo_limit.setInsertPolicy(QComboBox.NoInsert)
        self._combo_limit.currentIndexChanged.connect(self._on_filter_changed)
        install_combo_click_to_open(self._combo_limit)
        self._setup_search_combo(self._combo_limit)
        filter_layout.addWidget(self._combo_limit, 1)

        # "Nur"-Checkbox: hoechster Call muss im Programm des Limits liegen
        self._check_only_program = QCheckBox(_t("check_only_program"))
        self._check_only_program.setToolTip(_t("tooltip_only_program"))
        # Voreinstellung aus der INI (sequences/only_program_default) — vor dem
        # connect(), damit der Aufbau kein _on_filter_changed ausloest.
        if self._settings is not None:
            self._check_only_program.setChecked(
                str(self._settings.value(
                    "sequences/only_program_default", "false")).lower() == "true")
        self._check_only_program.toggled.connect(self._on_filter_changed)
        filter_layout.addWidget(self._check_only_program)

        layout.addLayout(filter_layout)

        # --- Filter-Zeile 2: Type + Difficulty ---
        filter_layout2 = QHBoxLayout()
        filter_layout2.setSpacing(8)

        filter_layout2.addWidget(QLabel(_t("label_type")))
        self._combo_type = QComboBox()
        self._combo_type.setToolTip(_t("tooltip_type"))
        self._combo_type.currentIndexChanged.connect(self._on_filter_changed)
        filter_layout2.addWidget(self._combo_type, 1)

        filter_layout2.addWidget(QLabel(_t("label_difficulty")))
        self._combo_difficulty = QComboBox()
        self._combo_difficulty.setToolTip(_t("tooltip_difficulty"))
        self._combo_difficulty.currentIndexChanged.connect(self._on_filter_changed)
        filter_layout2.addWidget(self._combo_difficulty, 1)

        # BL-191: Tag-Filter — Suchfeld mit Substring-Vorschlaegen + x zum Leeren
        # (gleiche Bedienung wie der Enthält-Filter). Match selbst ist exakt.
        filter_layout2.addWidget(QLabel(_t("label_tags")))
        self._combo_tags = QComboBox()
        self._combo_tags.setEditable(True)
        self._combo_tags.setInsertPolicy(QComboBox.NoInsert)
        self._combo_tags.setToolTip(_t("tooltip_tags"))
        self._combo_tags.currentIndexChanged.connect(self._on_filter_changed)
        install_combo_click_to_open(self._combo_tags)
        self._setup_search_combo(self._combo_tags)
        filter_layout2.addWidget(self._combo_tags, 1)

        layout.addLayout(filter_layout2)

        # --- Tabelle ---
        self._table = QTableWidget()
        self._table.setColumnCount(4)
        self._table.setHorizontalHeaderLabels([
            _t("header_sequence"), _t("header_level"),
            _t("header_type"), _t("header_difficulty")
        ])
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        # BL-166: STRG + Mausrad zoomt wie die +/- Buttons
        install_ctrl_wheel_zoom(self._table, self._on_zoom_in, self._on_zoom_out)
        self._table.setColumnHidden(1, True)   # Level: nur im Filter-Dropdown sichtbar
        self._table.setColumnHidden(2, True)   # Type: nur im Filter-Dropdown sichtbar
        self._table.setColumnHidden(3, True)   # Difficulty: nur im Filter-Dropdown sichtbar
        self._table.verticalHeader().setVisible(False)
        self._table.verticalScrollBar().valueChanged.connect(self._on_scroll)
        self._table.cellClicked.connect(self._on_cell_clicked)
        self._table.setContextMenuPolicy(Qt.CustomContextMenu)
        self._table.customContextMenuRequested.connect(self._on_context_menu)
        layout.addWidget(self._table)

        # --- Aktions-Leiste unter der Tabelle ---
        action_row = QHBoxLayout()
        action_row.setSpacing(6)
        action_row.addStretch()
        self._btn_delete_seq = QPushButton(_t("btn_delete_sequence"))
        self._btn_delete_seq.setToolTip(_t("btn_delete_sequence_tooltip"))
        self._btn_delete_seq.clicked.connect(self._on_delete_selected)
        self._btn_delete_seq.setEnabled(False)
        action_row.addWidget(self._btn_delete_seq)
        layout.addLayout(action_row)

        # Button-Status an Selektion koppeln
        self._table.itemSelectionChanged.connect(self._update_delete_button)

        # --- Statuszeile ---
        self._label_status = QLabel(_t("no_sequences_loaded"))
        self._label_status.setStyleSheet("font-size: 11px; color: #999;")
        layout.addWidget(self._label_status)

        # Default-Eintraege fuer Dropdowns
        self._populate_dropdowns()

    # ---- Zoom ----

    def set_zoom(self, pct: int):
        """Setzt Zoom-Level ohne Schreiben in INI (fuer Restore beim Start)."""
        self._zoom_pct = max(50, min(200, pct))
        self._apply_zoom()

    def _on_zoom_out(self):
        self._zoom_pct = max(50, self._zoom_pct - 10)
        self._apply_zoom()

    def _on_zoom_in(self):
        self._zoom_pct = min(200, self._zoom_pct + 10)
        self._apply_zoom()

    def _apply_zoom(self):
        self._label_zoom.setText(f"{self._zoom_pct}%")
        font_size = max(8, int(12 * self._zoom_pct / 100))
        self._table.setStyleSheet(f"QTableWidget {{ font-size: {font_size}px; }}")

    # ---- Filter ----

    def _get_contains_filter(self):
        """Gibt die entity_id des Contains-Filters zurueck (oder None)."""
        idx = self._combo_contains.currentIndex()
        if idx <= 0:
            return None
        return self._combo_contains.itemData(idx, Qt.UserRole)

    def _get_limit_filter(self):
        """Gibt die max_teaching_order des Limit-Filters zurueck (oder None)."""
        idx = self._combo_limit.currentIndex()
        if idx <= 0:
            return None
        return self._combo_limit.itemData(idx, Qt.UserRole)

    def _get_min_to_filter(self):
        """Gibt die Untergrenze fuer den "Nur"-Filter zurueck (oder None).

        Aktiv nur wenn die Checkbox gesetzt UND ein Limit gewaehlt ist.
        Untergrenze = Programm-Start des Limit-Calls (Ganzzahlteil der
        Teaching Order, z.B. 50.0 bei einem A1-Limit) — d.h. der hoechste
        Call der Sequenz muss im Programm des Limits liegen.
        """
        if not self._check_only_program.isChecked():
            return None
        limit = self._get_limit_filter()
        if limit is None:
            return None
        return float(int(limit))

    def _get_bands_below(self):
        """MS50: Bei aktivem "Nur"-Filter die Baender UNTER dem obersten der
        gewaehlten Programme. Der Filter zeigt dann nur Sequenzen, die das oberste
        Band wirklich brauchen (nicht mit den tieferen tanzbar).

        Rueckgabe None, wenn "Nur" aus ist oder nur ein Band gewaehlt ist
        (dann gibt es nichts "darunter").
        """
        bands = self._program_bands
        if not bands or not self._check_only_program.isChecked():
            return None
        if len(bands) < 2:
            return None
        top = max(bands)
        below = set(bands) - {top}
        return below or None

    def _get_type_filter(self):
        """Gibt den Type-Filter-Text zurueck (oder None)."""
        idx = self._combo_type.currentIndex()
        if idx <= 0:
            return None
        return self._combo_type.currentText()

    def _get_difficulty_filter(self):
        """Gibt den Difficulty-Filter-Text zurueck (oder None)."""
        idx = self._combo_difficulty.currentIndex()
        if idx <= 0:
            return None
        return self._combo_difficulty.currentText()

    def _get_tags_filter(self):
        """BL-191: Gibt den gewaehlten Tag-Filter zurueck (oder None = alle).

        Das Combo ist editierbar (Suchfeld), daher wird der Text ausgewertet:
        leer oder der "Alle"-Platzhalter (Index 0) = kein Filter.
        """
        text = self._combo_tags.currentText().strip()
        if not text or text == _t("tags_all"):
            return None
        return text

    def get_contains_filter_text(self) -> str:
        """Gibt den Anzeigetext des aktuellen Contains-Filters zurueck (leer = kein Filter)."""
        idx = self._combo_contains.currentIndex()
        if idx <= 0:
            return ""
        return self._combo_contains.itemText(idx)

    def get_limit_filter_text(self) -> str:
        """Gibt den Anzeigetext des aktuellen Limit-Filters zurueck (leer = kein Filter)."""
        idx = self._combo_limit.currentIndex()
        if idx <= 0:
            return ""
        return self._combo_limit.itemText(idx)

    def set_contains_filter(self, text: str):
        """Setzt den Contains-Filter auf einen Eintrag mit passendem Text (oder leer)."""
        for i in range(self._combo_contains.count()):
            if self._combo_contains.itemText(i) == text:
                self._combo_contains.setCurrentIndex(i)
                return
        # Nicht gefunden: direkt als Text setzen (editierbar)
        self._combo_contains.setCurrentText(text)

    def set_limit_filter(self, text: str):
        """Setzt den Limit-Filter auf einen Eintrag mit passendem Text."""
        for i in range(self._combo_limit.count()):
            if self._combo_limit.itemText(i) == text:
                self._combo_limit.setCurrentIndex(i)
                return

    def set_type_filter(self, text: str) -> bool:
        """BL-181 A: Setzt den Type-Filter auf den Eintrag mit passendem Text.

        Rueckgabe True, wenn der Typ gefunden und gesetzt wurde. Ein leerer Text
        schaltet auf "Alle" (Index 0). Ist der Typ nicht vorhanden, bleibt der
        Filter unveraendert und es wird False zurueckgegeben (der Aufrufer kann
        das protokollieren).
        """
        if not text:
            self._combo_type.setCurrentIndex(0)
            return True
        for i in range(self._combo_type.count()):
            if self._combo_type.itemText(i) == text:
                self._combo_type.setCurrentIndex(i)
                return True
        return False

    def set_limit_filter_by_to(self, to_value):
        """BL-132: Setzt den Limit-Filter anhand des Teaching-Order-Werts (UserRole).

        Wird aufgerufen wenn ein Tanzprogramm mit konfiguriertem Sequenz-Limit gewaehlt wird.
        Hat das Programm KEIN Sequenz-Limit (to_value None), bleibt der aktuell
        gewaehlte Limit-Filter unangetastet — ein manuell gesetztes Limit darf beim
        Programmwechsel nicht auf "Alle" zurueckgeworfen werden (sonst wirkt das
        Sync destruktiv fuer Nutzer ohne gepflegte sequence_limit_to-Werte).
        """
        if to_value is None:
            return
        for i in range(self._combo_limit.count()):
            if self._combo_limit.itemData(i, Qt.UserRole) == to_value:
                self._combo_limit.setCurrentIndex(i)
                return

    # --- BL-193..197: deterministische Filter-Setter fuer Rule-Aktionen ---
    # Jeder Setter blockt die Signale, setzt den Wert (per Text-Match, sonst
    # Freitext bzw. "Alle") und loest genau EIN _on_filter_changed() aus.

    def _rule_set_combo(self, combo, text: str, editable: bool):
        combo.blockSignals(True)
        if not text:
            combo.setCurrentIndex(0)
        else:
            hit = False
            for i in range(combo.count()):
                if combo.itemText(i) == text:
                    combo.setCurrentIndex(i)
                    hit = True
                    break
            if not hit:
                if editable:
                    combo.setCurrentText(text)
                else:
                    combo.setCurrentIndex(0)
        combo.blockSignals(False)
        self._on_filter_changed()

    def rule_set_contains(self, text: str):
        """BL-193: Contains-Filter setzen (leer = kein Filter)."""
        self._rule_set_combo(self._combo_contains, text, editable=True)

    def rule_set_limit(self, text: str):
        """BL-194: Limit-Filter setzen (leer = kein Filter)."""
        self._rule_set_combo(self._combo_limit, text, editable=True)

    def rule_set_difficulty(self, text: str):
        """BL-196: Difficulty-Filter setzen (leer = kein Filter)."""
        self._rule_set_combo(self._combo_difficulty, text, editable=False)

    def rule_set_tags(self, text: str):
        """BL-197: Tag-Filter setzen (leer = kein Filter)."""
        self._rule_set_combo(self._combo_tags, text, editable=True)

    def rule_set_only(self, enabled: bool):
        """BL-195: "Nur"-Filter (hoechster Call im Programm) umschalten."""
        self._check_only_program.blockSignals(True)
        self._check_only_program.setChecked(bool(enabled))
        self._check_only_program.blockSignals(False)
        self._on_filter_changed()

    def set_program_bands(self, bands, defer_load=False):
        """MS50: Setzt die Programm-Band-Menge der aktuellen Lokation (Mengen-Filter).

        bands = Menge von Band-Ganzzahlen (z.B. {10,20,30}) oder None/leer (kein
        Programm-Filter -> alle Sequenzen). Loest normal ein Neuladen aus.

        defer_load=True: nur Baender + Contains/Limit-Listen setzen, das (ggf.
        teure) Tabellen-Laden NICHT sofort ausloesen. Der Aufrufer laedt spaeter
        selbst (z.B. per load_sequences() nach window.show()) -> haelt den
        Startup-Cover-Compute vom kritischen Pfad fern (BL-201/Perf).
        """
        new = set(int(b) for b in bands) if bands else None
        if new == self._program_bands and not defer_load:
            return
        _t0 = perf_start()
        self._program_bands = new
        # MS50: Contains- und Limit-Liste an die neuen Baender knuepfen
        self._rebuild_contains_items()
        self._rebuild_limit_items()
        if not defer_load:
            self._on_filter_changed()
        perf_log(f"SeqFilter.set_program_bands({sorted(new) if new else None}): TOTAL", _t0)

    def _on_filter_changed(self, _idx=None):
        """Filter geaendert: Tabelle neu laden und SequenceView zuruecksetzen."""
        _t0 = perf_start()
        self._loaded_count = 0
        self._load_sequences(reset=True)
        _pt = perf_split("SeqFilter._on_filter_changed: load_sequences", _t0)
        if self.on_filter_changed_detail:
            self.on_filter_changed_detail()
            perf_split("SeqFilter._on_filter_changed: detail_callback", _pt)

    def reset_filters(self):
        """Setzt alle Filter auf 'Alle'/keiner und laedt neu (z.B. nach Neuanlage).

        Damit ist eine frisch erstellte Sequenz garantiert sichtbar, auch wenn
        zuvor ein Typ-/Level-Filter aktiv war.
        """
        for combo in (self._combo_contains, self._combo_limit,
                      self._combo_type, self._combo_difficulty,
                      self._combo_tags):
            combo.blockSignals(True)
            combo.setCurrentIndex(0)
            combo.blockSignals(False)
        self._check_only_program.blockSignals(True)
        self._check_only_program.setChecked(False)
        self._check_only_program.blockSignals(False)
        self._on_filter_changed()

    def select_sequence(self, seq_id: int):
        """Markiert eine Sequenz in der Tabelle (falls geladen) und oeffnet sie
        im SequenzView. Laedt bei Bedarf weitere Bloecke nach, bis sie sichtbar
        ist oder das Ende erreicht wird."""
        seq_ids = self.get_filtered_seq_ids()
        if seq_id not in seq_ids:
            return
        target_idx = seq_ids.index(seq_id)

        # Solange nachladen, bis die Zielzeile geladen ist
        while (self._loaded_count <= target_idx
               and self._loaded_count < self._total_count):
            self._load_sequences(reset=False)

        for r in range(self._table.rowCount()):
            it = self._table.item(r, 0)
            if it and it.data(Qt.UserRole) == seq_id:
                self._table.selectRow(r)
                self._table.scrollToItem(it)
                break

        if self.on_open_detail:
            self.on_open_detail(seq_ids, target_idx)

    def _current_filter_args(self) -> dict:
        """MS50: Zentrale Ableitung ALLER Filter-Parameter fuer die Sequenz-Abfragen
        (Tabelle, Zaehler, Detail-IDs) — eine Quelle, damit die Pfade nicht
        auseinanderlaufen. Im Baender-Modus begrenzt der Limit-Filter die effektive
        Band-Menge (_effective_bands) und "Only" laeuft ueber bands_below; ohne
        Programmwahl gilt der Legacy-max_to/min_to-Pfad."""
        args = dict(
            entity_id_filter=self._get_contains_filter(),
            type_filter=self._get_type_filter(),
            difficulty_filter=self._get_difficulty_filter(),
            tags_filter=self._get_tags_filter(),
        )
        if self._program_bands:
            # Limit wirkt als FEINE Teaching-Order-Obergrenze (cover_max_to) INNERHALB
            # der gewaehlten Baender — nicht als Band-Reduktion. So schliesst "Limit =
            # Spin Chain Thru" die spaeter gelehrten Figuren desselben Bandes (Recycle)
            # korrekt aus.
            args.update(
                max_to_filter=None,
                min_to_filter=None,
                bands_filter=self._program_bands,
                bands_below_filter=self._get_bands_below(),
                cover_max_to=self._get_limit_filter(),
            )
        else:
            args.update(
                max_to_filter=self._get_limit_filter(),
                min_to_filter=self._get_min_to_filter(),
                bands_filter=None,
                bands_below_filter=None,
                cover_max_to=None,
            )
        return args

    # ---- Daten laden ----

    def load_sequences(self):
        """Laedt Sequenzen in die Tabelle (initialer Aufruf)."""
        self._loaded_count = 0
        self._load_sequences(reset=True)

    def _load_sequences(self, reset=False):
        """Laedt den naechsten Block Sequenzen (Lazy Loading)."""
        if self._loading:
            return
        self._loading = True
        _t0 = perf_start()

        args = self._current_filter_args()
        _pt = perf_split("SeqFilter._load: prep_filters", _t0)

        self._total_count = self.db.get_filtered_count(**args)
        _pt = perf_split(
            f"SeqFilter._load: count_query -> {self._total_count} "
            f"(bands={sorted(args['bands_filter']) if args['bands_filter'] else None}, "
            f"only={args['bands_below_filter'] is not None})", _pt)

        if reset:
            self._loaded_count = 0

        rows = self.db.get_filtered_sequences(
            limit=self._PAGE_SIZE, offset=self._loaded_count, **args)
        _pt = perf_split(f"SeqFilter._load: page_query -> {len(rows)} rows "
                        f"(offset={self._loaded_count})", _pt)

        if reset:
            self._table.setUpdatesEnabled(False)
            self._table.setRowCount(0)
            self._table.setRowCount(len(rows))
            self._fill_rows(0, rows)
            self._table.setUpdatesEnabled(True)
        else:
            old_count = self._table.rowCount()
            self._table.setUpdatesEnabled(False)
            self._table.setRowCount(old_count + len(rows))
            self._fill_rows(old_count, rows)
            self._table.setUpdatesEnabled(True)

        _pt = perf_split("SeqFilter._load: fill_table", _pt)
        self._loaded_count += len(rows)
        self._update_status()
        perf_log("SeqFilter._load: TOTAL", _t0)
        self._loading = False

    def _fill_rows(self, start_idx: int, rows: list):
        """Fuellt Tabellenzeilen ab start_idx."""
        from sequence_mapper import get_program_label
        for i, row in enumerate(rows):
            table_idx = start_idx + i
            seq_id = row[0]
            fields = row[1:16]   # field_1 bis field_15
            max_to = row[17]     # max_teaching_order
            seq_type = row[18] if len(row) > 18 else ""    # type
            difficulty = row[19] if len(row) > 19 else ""  # difficulty

            # Sequenz-Spalte (col 0): Calls als Kette \u2014 seq_id als UserRole
            call_texts = [f for f in fields if f]
            seq_text = " \u2192 ".join(call_texts)
            item_seq = QTableWidgetItem(seq_text)
            item_seq.setData(Qt.UserRole, seq_id)
            self._table.setItem(table_idx, 0, item_seq)

            # Level-Spalte
            if max_to is not None:
                level = get_program_label(max_to)
            else:
                level = row[16] or "?"  # level_original als Fallback
            self._table.setItem(table_idx, 1, QTableWidgetItem(level))

            # Type-Spalte
            self._table.setItem(table_idx, 2, QTableWidgetItem(seq_type or ""))

            # Difficulty-Spalte
            self._table.setItem(table_idx, 3, QTableWidgetItem(difficulty or ""))

    def _update_status(self):
        """Aktualisiert die Statuszeile."""
        total_db = self.db.get_sequence_count()
        if self._total_count == total_db:
            self._label_status.setText(
                _t("sequences_count", count=self._total_count)
            )
        else:
            self._label_status.setText(
                _t("sequences_filtered", filtered=self._total_count, total=total_db)
            )

    # ---- Lazy Loading ----

    def _on_scroll(self, value):
        """Beim Scrollen ans Ende: naechsten Block nachladen."""
        if self._loading:
            return
        scrollbar = self._table.verticalScrollBar()
        if value >= scrollbar.maximum() - 5:
            if self._loaded_count < self._total_count:
                self._load_sequences(reset=False)

    # ---- Detail-Dock ----

    def _on_cell_clicked(self, row, _col):
        """Klick auf Zeile: SequenceViewWidget im Dock aktualisieren (BL-089).

        Shift-/Strg-Klick wird ignoriert — dann ist der Klick fuer die
        Mehrfach-Auswahl (Loeschen etc.) und soll das Detail-Fenster nicht
        umstellen.
        """
        mods = QApplication.keyboardModifiers()
        if mods & (Qt.ShiftModifier | Qt.ControlModifier):
            return
        item = self._table.item(row, 0)
        if not item:
            return
        seq_id = item.data(Qt.UserRole)
        if seq_id is None:
            return

        seq_ids = self.db.get_filtered_sequence_ids(**self._current_filter_args())
        if not seq_ids:
            return

        try:
            current_idx = seq_ids.index(seq_id)
        except ValueError:
            current_idx = 0

        if self.on_open_detail:
            self.on_open_detail(seq_ids, current_idx)

    def _on_context_menu(self, pos):
        item = self._table.itemAt(pos)
        if not item:
            return
        row = self._table.row(item)
        id_item = self._table.item(row, 0)
        if not id_item:
            return
        seq_id = id_item.data(Qt.UserRole)
        if seq_id is None:
            return
        selected_ids = self._get_selected_seq_ids()
        # Wenn die Rechtsklick-Zeile nicht in der Selektion ist, nur sie nehmen
        if seq_id not in selected_ids:
            selected_ids = [seq_id]
        menu = QMenu(self)
        act = menu.addAction(_t("ctx_add_to_notes"))
        act.triggered.connect(
            lambda: self.on_add_to_notes(seq_id) if self.on_add_to_notes else None)
        menu.addSeparator()
        del_label = (_t("ctx_delete_sequence")
                     if len(selected_ids) == 1
                     else _t("ctx_delete_sequences_many", count=len(selected_ids)))
        del_act = menu.addAction(del_label)
        del_act.triggered.connect(
            lambda: self._delete_sequences_with_confirm(selected_ids))
        menu.exec(self._table.viewport().mapToGlobal(pos))

    # ---- Loeschen ----

    def _get_selected_seq_ids(self) -> list:
        """Liefert die Sequenz-IDs aller selektierten Zeilen (Multi-Select-fähig)."""
        ids = []
        for row in {idx.row() for idx in self._table.selectionModel().selectedRows()}:
            id_item = self._table.item(row, 0)
            if id_item is None:
                continue
            seq_id = id_item.data(Qt.UserRole)
            if seq_id is not None:
                ids.append(seq_id)
        return ids

    def _update_delete_button(self):
        n = len(self._get_selected_seq_ids())
        self._btn_delete_seq.setEnabled(n > 0)

    def _on_delete_selected(self):
        ids = self._get_selected_seq_ids()
        if not ids:
            return
        self._delete_sequences_with_confirm(ids)

    def _delete_sequences_with_confirm(self, seq_ids: list):
        """Loescht Sequenzen nach Rueckfrage. Aktualisiert Tabelle + SequenceView."""
        if not seq_ids:
            return
        if len(seq_ids) == 1:
            msg = _t("confirm_delete_sequence_one")
        else:
            msg = _t("confirm_delete_sequence_many", count=len(seq_ids))
        reply = QMessageBox.question(
            self, _t("delete_sequence_title"), msg,
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return
        deleted = self.db.delete_sequences(seq_ids)
        print(f"[Sequenzen] {deleted} geloescht: {seq_ids}")
        # Tabelle + Dropdowns neu laden
        self._populate_dropdowns()
        self.load_sequences()
        # Detail-View informieren (falls Callback gesetzt)
        if getattr(self, "on_sequences_deleted", None):
            self.on_sequences_deleted(seq_ids)

    def _on_seq_to_notes(self):
        seq_ids = self.get_filtered_seq_ids()
        if not seq_ids:
            return
        idx = self.get_current_seq_idx()
        if self.on_add_to_notes:
            self.on_add_to_notes(seq_ids[idx])

    def _on_filter_to_notes(self):
        if self.on_add_filter_to_notes:
            self.on_add_filter_to_notes()

    def get_filtered_seq_ids(self) -> list:
        """Gibt die aktuell gefilterten Sequenz-IDs zurück (für Rule-Aktionen).
        Nutzt dieselbe zentrale Filter-Ableitung wie Tabelle/Zaehler."""
        _t0 = perf_start()
        res = self.db.get_filtered_sequence_ids(**self._current_filter_args())
        perf_log(f"SeqFilter.get_filtered_seq_ids: ids_query -> {len(res)}", _t0)
        return res

    def get_current_seq_idx(self) -> int:
        """Gibt den Index der aktuell markierten Tabellenzeile in den gefilterten IDs zurück."""
        seq_ids = self.get_filtered_seq_ids()
        row = self._table.currentRow()
        if row >= 0 and seq_ids:
            item = self._table.item(row, 0)
            if item:
                sel_id = item.data(Qt.UserRole)
                try:
                    return seq_ids.index(sel_id)
                except ValueError:
                    pass
        return 0

    # ---- Remapping ----

    def _on_remapping(self):
        """Remapping: max_teaching_order fuer alle Sequenzen neu berechnen."""
        if self.db.get_sequence_count() == 0:
            QMessageBox.warning(
                self, _t("remapping_title"),
                _t("remapping_no_sequences")
            )
            return

        reply = QMessageBox.question(
            self, _t("remapping_title"),
            _t("remapping_confirm"),
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return

        self._do_remapping()
        stats = self.db.get_mapping_stats()
        QMessageBox.information(
            self, _t("remapping_done_title"),
            _t("remapping_done_msg",
               total=stats['total_unique_texts'],
               mapped=stats['mapped'],
               unmapped=stats['unmapped'],
               auto=stats['auto'],
               manual=stats['manual'])
        )

    def _do_remapping(self):
        """Baut fehlende Auto-Mappings neu und berechnet max_teaching_order neu."""
        self.db.backfill_auto_mappings()
        self.db.recompute_sequence_max_to()
        self._populate_dropdowns()
        self.load_sequences()
        print("[Sequenzen] Remapping: Auto-Mappings ergaenzt + max_teaching_order neu berechnet")

    # ---- Dropdowns ----

    def _setup_search_combo(self, combo):
        """BL-190: Editierbare Combo als Suchfeld — Substring-Vervollstaendigung
        (nicht nur Wortanfang) und ein Clear-Button (x) im Feld.

        Der Clear-Button leert nur den Text; damit der Filter wirklich entfaellt,
        setzen wir bei leerem Text auf Index 0 (= "Alle"/"kein Limit") zurueck.
        """
        cpl = combo.completer()
        if cpl is not None:
            from PySide6.QtWidgets import QCompleter
            # PopupCompletion statt des Combo-Defaults InlineCompletion: Inline +
            # MatchContains ist kaputt — die Inline-Vervollstaendigung nimmt an, der
            # Treffer BEGINNE mit dem Getippten, bei "Thru" ist der Treffer aber
            # "Pass Thru". Das erzeugte im Feld Murks wie "Thru thru". Popup zeigt die
            # Substring-Treffer sauber als Liste; Enter uebernimmt den markierten Call.
            cpl.setCompletionMode(QCompleter.PopupCompletion)
            cpl.setFilterMode(Qt.MatchContains)
            cpl.setCaseSensitivity(Qt.CaseInsensitive)
        le = combo.lineEdit()
        if le is not None:
            le.setClearButtonEnabled(True)
            le.textChanged.connect(lambda text, c=combo: self._on_search_combo_cleared(c, text))

    def _on_search_combo_cleared(self, combo, text):
        """Wird der Text (per x-Button oder Loeschen) geleert, den Filter auf
        Index 0 zuruecksetzen — sonst bliebe die alte Auswahl aktiv."""
        if text == "" and combo.currentIndex() != 0:
            combo.setCurrentIndex(0)   # loest _on_filter_changed aus (Neuladen)

    def _calls_for_current_bands(self, include_separators: bool):
        """MS50: Figuren-Liste passend zu den aktuell gewaehlten Programm-Baendern
        (_program_bands). Nur Zeilen, deren Band gewaehlt ist; eine Figur erscheint
        genau EINMAL, im NIEDRIGSTEN gewaehlten Band. Ohne Programmwahl -> alle
        Figuren (bisheriges Verhalten). Rueckgabe [(name, entity_id, to), ...] nach
        Teaching-Order sortiert."""
        from sequence_mapper import get_all_calls_sorted
        all_calls = get_all_calls_sorted(self.db)
        bands = self._program_bands
        if not bands:
            rows = list(all_calls)
        else:
            best = {}   # entity_id -> (name, eid, to) im niedrigsten gewaehlten Band
            for name, eid, to in all_calls:
                if to is None or int(to) not in bands:
                    continue
                if eid not in best or to < best[eid][2]:
                    best[eid] = (name, eid, to)
            rows = sorted(best.values(), key=lambda r: r[2])
        if not include_separators:
            rows = [r for r in rows if not r[0].startswith("--")]
        return rows

    def _rebuild_contains_items(self):
        """BL-190 + MS50: Fuellt das Contains-Dropdown mit den Figuren der gewaehlten
        Programme (Band-gefiltert, siehe _calls_for_current_bands) und ordnet Calls
        bis zur Programm-Grenze zuerst. Auswahl bleibt ueber die entity_id erhalten.
        """
        _t0 = perf_start()
        calls = self._calls_for_current_bands(include_separators=False)
        prev_eid = self._get_contains_filter()   # aktuell gewaehlte entity_id (oder None)
        _pt = perf_split(f"SeqFilter._rebuild_contains: get_calls -> {len(calls)}", _t0)

        limit_to = self._program_sort_to
        if limit_to is not None:
            # stabile Sortierung: Gruppe 0 = im/unter dem Programm, Gruppe 1 = darueber.
            # Innerhalb der Gruppen bleibt die Teaching-Order-Reihenfolge erhalten.
            calls = sorted(calls, key=lambda c: 0 if (c[2] is not None and c[2] <= limit_to) else 1)

        self._combo_contains.blockSignals(True)
        self._combo_contains.clear()
        self._combo_contains.addItem(_t("contains_all"))
        restore_idx = 0
        for name, entity_id, to in calls:
            self._combo_contains.addItem(name, entity_id)
            if prev_eid is not None and entity_id == prev_eid:
                restore_idx = self._combo_contains.count() - 1
        self._combo_contains.setCurrentIndex(restore_idx)
        self._combo_contains.blockSignals(False)
        perf_split(f"SeqFilter._rebuild_contains: fill_combo ({len(calls)} items)", _pt)
        perf_log("SeqFilter._rebuild_contains: TOTAL", _t0)

    def _rebuild_limit_items(self):
        """MS50: Fuellt das Limit-Dropdown mit den Figuren der gewaehlten Programme
        (Band-gefiltert, inkl. Programm-Trenner). Die bisherige Auswahl bleibt ueber
        ihre Teaching-Order erhalten, falls sie noch in der Liste ist."""
        prev_to = None
        idx = self._combo_limit.currentIndex()
        if idx > 0:
            prev_to = self._combo_limit.itemData(idx, Qt.UserRole)
        calls = self._calls_for_current_bands(include_separators=True)
        self._combo_limit.blockSignals(True)
        self._combo_limit.clear()
        self._combo_limit.addItem(_t("limit_none"))
        restore_idx = 0
        for name, entity_id, to in calls:
            self._combo_limit.addItem(name, to)
            if prev_to is not None and to == prev_to:
                restore_idx = self._combo_limit.count() - 1
        self._combo_limit.setCurrentIndex(restore_idx)
        self._combo_limit.blockSignals(False)

    def set_program_sort_to(self, to_value):
        """BL-190: Setzt die Teaching-Order-Grenze des aktuellen Tanzprogramms
        (aus dance_programs.sequence_limit_to) und ordnet die Contains-Vorschlaege
        neu. Reine Sortier-Aenderung — kein Neuladen der Tabelle noetig."""
        if to_value == self._program_sort_to:
            return
        self._program_sort_to = to_value
        self._rebuild_contains_items()

    def _populate_dropdowns(self):
        """Baut die Filter-Dropdowns auf (nach Import/Remapping)."""
        # Contains + Limit sind an die gewaehlten Programm-Baender geknuepft
        # (_calls_for_current_bands). Bei Programmwechsel werden sie ueber
        # set_program_bands neu gebaut.
        self._rebuild_contains_items()
        self._rebuild_limit_items()

        # --- Type-Dropdown ---
        _DEFAULT_TYPE = "Singer (Corner progression)"
        self._combo_type.blockSignals(True)
        self._combo_type.clear()
        self._combo_type.addItem(_t("type_all"))
        default_type_idx = 0
        for t in self.db.get_sequence_type_values():
            self._combo_type.addItem(t)
            if t == _DEFAULT_TYPE:
                default_type_idx = self._combo_type.count() - 1
        self._combo_type.setCurrentIndex(default_type_idx)
        self._combo_type.blockSignals(False)

        # --- Difficulty-Dropdown ---
        self._combo_difficulty.blockSignals(True)
        self._combo_difficulty.clear()
        self._combo_difficulty.addItem(_t("difficulty_all"))
        for d in self.db.get_sequence_difficulty_values():
            self._combo_difficulty.addItem(d)
        self._combo_difficulty.blockSignals(False)

        # --- Tags-Dropdown (BL-191) ---
        self._combo_tags.blockSignals(True)
        prev_tag = self._get_tags_filter()
        self._combo_tags.clear()
        self._combo_tags.addItem(_t("tags_all"))
        for tg in self.db.get_sequence_tags_values():
            self._combo_tags.addItem(tg)
        # Vorherige Auswahl beibehalten (z.B. nach Editor-Speichern), sonst "Alle".
        restore_idx = 0
        if prev_tag:
            for i in range(1, self._combo_tags.count()):
                if self._combo_tags.itemText(i) == prev_tag:
                    restore_idx = i
                    break
        self._combo_tags.setCurrentIndex(restore_idx)
        self._combo_tags.blockSignals(False)

    # ---- Import ----

    def import_from_mdb(self, mdb_path: str):
        """Importiert Sequenzen aus einer Access-MDB (nur Rohdaten).

        Das Mapping (Call-Texte → Entity-IDs) muss separat ueber
        tools/map_sequence_calls.py erfolgen.

        Args:
            mdb_path: Pfad zur caller.mdb
        """
        # mdb_reader liegt in src/migration/ (Sub-Paket neben main.py)
        migration_dir = os.path.join(os.path.dirname(__file__), "migration")
        if migration_dir not in sys.path:
            sys.path.insert(0, migration_dir)

        from mdb_reader import MdbReader

        # 1) MDB lesen
        reader = MdbReader(mdb_path)
        sequences = reader.read_sequences()
        print(f"[Import] {len(sequences)} Sequenzen gelesen")

        # 2) In Bulk-Format bringen und schnell einspielen (Warte-Cursor)
        seqs = []
        for seq in sequences:
            calls = []
            for i in range(1, 16):
                val = seq.get(f"Feld{i}", None)
                if val and isinstance(val, str) and val.strip() and val.strip() != "-":
                    calls.append(val.strip())
            level = seq.get("Level", "") or ""
            if isinstance(level, str):
                level = level.strip()
            seqs.append({"calls": calls, "level": level})

        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            self.db.bulk_import_sequences(seqs, source="",
                                          dedup_against_existing=True)
            # 3) Dropdowns + Tabelle
            self._populate_dropdowns()
            self.load_sequences()
        finally:
            QApplication.restoreOverrideCursor()

        print(f"[Import] {len(sequences)} Sequenzen importiert")
        QMessageBox.information(
            self, _t("import_done_title"),
            _t("import_done_msg", count=len(sequences))
        )

    def import_from_json(self, json_paths: list):
        """Importiert Sequenzen aus einer oder mehreren JSON-Dateien (Ceder-Format).

        Erwartet pro Eintrag:
          { "calls": [...], "level": "...", "seq_type": "...", "difficulty": "..." }

        Sequenzen werden einfach angehaengt (kein Loeschen bestehender Daten).
        Dubletten-Bereinigung ist ein separater Schritt.
        """
        import json as _json

        all_seqs = []
        seen_ids: set = set()  # Deduplizierung ueber alle gewaehlten Dateien

        for path in json_paths:
            try:
                with open(path, encoding="utf-8") as f:
                    data = _json.load(f)
                if not isinstance(data, list):
                    print(f"[Import JSON] {path}: kein Array — uebersprungen")
                    continue
                for seq in data:
                    ceder_id = seq.get("id", "")
                    if ceder_id and ceder_id in seen_ids:
                        continue
                    if ceder_id:
                        seen_ids.add(ceder_id)
                    all_seqs.append(seq)
            except Exception as e:
                print(f"[Import JSON] Fehler beim Lesen von {path}: {e}")

        if not all_seqs:
            QMessageBox.warning(self, _t("import_json_title"),
                                _t("import_json_empty"))
            return

        # Bulk-Import (eine Transaktion, Index/Cache einmal) + Dedup gegen Bestand,
        # damit ein erneuter Import nicht dupliziert. Loest das Pro-Zeile-Commit-
        # Perf-Problem (10k Sequenzen: Sekunden statt ~40 s). Warte-Cursor, weil
        # Index+Cache-Neubau auf langsamen Rechnern ein paar Sekunden dauern kann.
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            inserted, skipped = self.db.bulk_import_sequences(
                all_seqs, source="", dedup_against_existing=True)
            # Dropdowns + Tabelle aktualisieren
            self._populate_dropdowns()
            self.load_sequences()
        finally:
            QApplication.restoreOverrideCursor()

        print(f"[Import JSON] {inserted} Sequenzen eingefuegt, {skipped} uebersprungen")
        QMessageBox.information(
            self, _t("import_json_title"),
            _t("import_json_done", inserted=inserted, skipped=skipped)
        )

    def import_from_csds(self, csds_paths: list):
        """Importiert Sequenzen aus einer oder mehreren CSDS-Dateien (Vic Ceder Export).

        Format:
          @
          #PROOFREAD#
          #EASY#
          #REC=6734#
          #SEQTYPE=10#
          #AUTHOR=...#
          Call 1,
          Call 2,
          ...
          @

        Sequenzen werden angehaengt (kein Loeschen bestehender Daten).
        """
        import re as _re

        # Mapping SEQTYPE-Nummer → lesbarer Name (kanonische Ceder-Konvention:
        # "Singer (...)" und Pfeil "➔" als Trenner — muss zu song_db.
        # canonicalize_seq_type passen, sonst entstehen doppelte Filter-Kategorien).
        _SEQTYPE_NAMES = {
            "5":   "Static Set ➔ Resolve",
            "10":  "Singer (Corner progression)",
            "20":  "Singer (R-H Lady progression)",
            "30":  "Singing break",
            "40":  "Stir the bucket",
            "80":  "Static Set ➔ Zero Line",
            "90":  "Static Set ➔ Zero Box",
            "95":  "Zero Line ➔ Resolve",
            "100": "Zero Line ➔ Zero Line",
            "110": "Zero Line ➔ Zero Box",
            "115": "Zero Box ➔ Resolve",
            "120": "Zero Box ➔ Zero Line",
            "130": "Zero Box ➔ Zero Box",
        }
        _DIFFICULTY_MAP = {
            "EASY":   "Easy",
            "MEDIUM": "Medium",
            "HARD":   "Hard",
        }

        def _clean_call(raw: str) -> str:
            """Bereinigt eine Call-Zeile: XML-Tags entfernen, Trailing-Komma abschneiden."""
            # <C ALT="...">text</C> → text
            cleaned = _re.sub(r'<C[^>]*>(.*?)</C>', r'\1', raw)
            return cleaned.rstrip(',').strip()

        def _parse_csds_content(text: str) -> list:
            seqs = []
            for block in text.split('@'):
                lines = block.splitlines()
                difficulty = ""
                rec_id = ""
                seq_type = ""
                calls = []
                for line in lines:
                    s = line.strip()
                    if not s:
                        continue
                    if s.startswith('#') and s.endswith('#'):
                        inner = s[1:-1]
                        if inner in _DIFFICULTY_MAP:
                            difficulty = _DIFFICULTY_MAP[inner]
                        elif inner.startswith('REC='):
                            rec_id = inner[4:]
                        elif inner.startswith('SEQTYPE='):
                            seq_type = _SEQTYPE_NAMES.get(inner[8:], inner[8:])
                        # PROOFREAD, AUTHOR etc. ignorieren
                    else:
                        call = _clean_call(s)
                        if call:
                            calls.append(call)
                if calls:
                    seqs.append({
                        "id": rec_id,
                        "calls": calls,
                        "seq_type": seq_type,
                        "difficulty": difficulty,
                        "level": "",
                    })
            return seqs

        all_seqs = []
        seen_ids: set = set()

        for path in csds_paths:
            try:
                with open(path, encoding="utf-8", errors="replace") as f:
                    content = f.read()
                for seq in _parse_csds_content(content):
                    rec_id = seq.get("id", "")
                    if rec_id and rec_id in seen_ids:
                        continue
                    if rec_id:
                        seen_ids.add(rec_id)
                    all_seqs.append(seq)
            except Exception as e:
                print(f"[Import CSDS] Fehler beim Lesen von {path}: {e}")

        if not all_seqs:
            QMessageBox.warning(self, _t("import_csds_title"),
                                _t("import_csds_empty"))
            return

        # Bulk-Import + Dedup + Warte-Cursor (wie JSON-Import).
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            inserted, skipped = self.db.bulk_import_sequences(
                all_seqs, source="", dedup_against_existing=True)
            self._populate_dropdowns()
            self.load_sequences()
        finally:
            QApplication.restoreOverrideCursor()

        print(f"[Import CSDS] {inserted} Sequenzen eingefuegt, {skipped} uebersprungen")
        QMessageBox.information(
            self, _t("import_csds_title"),
            _t("import_csds_done", inserted=inserted, skipped=skipped)
        )

    def import_from_freetext(self, sequences, seq_type: str, difficulty: str):
        """Importiert Sequenzen aus einem geparsten Freitext (BL-098).

        Args:
            sequences: list[list[str]] — bereits geparsterCall-Listen
                (siehe FreetextSequenceImportDialog._parse_text).
            seq_type: Sequenz-Typ (Pflichtfeld, vom Nutzer im Dialog gewaehlt).
            difficulty: Schwierigkeitsgrad (optional, '' = leer).
        """
        if not sequences:
            return 0, 0

        # In Bulk-Format bringen (Typ/Schwierigkeit gelten fuer alle) und
        # ueber den schnellen Bulk-Import + Dedup + Warte-Cursor einspielen.
        seqs = [{"calls": c, "seq_type": seq_type, "difficulty": difficulty}
                for c in sequences if c]
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            inserted, skipped = self.db.bulk_import_sequences(
                seqs, source="", dedup_against_existing=True)
            self._populate_dropdowns()
            self.load_sequences()
        finally:
            QApplication.restoreOverrideCursor()

        print(f"[Import Freitext] {inserted} Sequenzen eingefuegt, "
              f"{skipped} uebersprungen")
        QMessageBox.information(
            self, _t("freetext_import_title"),
            _t("freetext_import_done", inserted=inserted, skipped=skipped)
        )
        return inserted, skipped


class _MappingHighlighter(QSyntaxHighlighter):
    """Faerbt jede Zeile (Block) gruen, deren Call-Text bereits gemappt ist.

    Die Mapping-Pruefung kommt ueber den Callback is_mapped(text) -> bool,
    den der Editor mit einem Cache versorgt.
    """

    def __init__(self, document, is_mapped):
        super().__init__(document)
        self._is_mapped = is_mapped
        self._fmt = QTextCharFormat()
        self._fmt.setBackground(QColor(46, 94, 46))   # dezentes Gruen
        self._fmt.setForeground(QColor(220, 255, 220))

    def highlightBlock(self, text: str):
        if text.strip() and self._is_mapped(text):
            self.setFormat(0, len(text), self._fmt)


class _CallListEdit(QPlainTextEdit):
    """Mehrzeiliges Call-Eingabefeld mit Doppelklick-Hook pro Zeile.

    Bei Doppelklick wird on_line_double_click(line_text) aufgerufen.
    Gibt der Callback True zurueck (z.B. weil ein Zuordnungs-Dialog geoeffnet
    wurde), entfaellt das normale Wort-Markieren.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.on_line_double_click = None

    def mouseDoubleClickEvent(self, event):
        cursor = self.cursorForPosition(event.position().toPoint())
        line = cursor.block().text().strip()
        if line and self.on_line_double_click:
            if self.on_line_double_click(line):
                return
        super().mouseDoubleClickEvent(event)


class SequenceEditorDialog(QDialog):
    """Editor zum Erstellen und Bearbeiten von Sequenzen (BL-015).

    Aufbau:
      - Kopfbereich: Typ + Schwierigkeit (editierbare Dropdowns, mit
        vorhandenen Werten vorbefuellt)
      - Eingabe-Liste: ein Call pro Zeile (QPlainTextEdit). Diese Zeilen-
        Konvention ist die Basis fuer das spaetere Call-Mapping.
      - Buttons: + Neu, Speichern, Auf Duplikate pruefen, Schliessen

    Limit: max. 15 Calls pro Sequenz (DB-Schema field_1..field_15).
    Beim Speichern werden ueberzaehlige Zeilen abgewiesen.

    Per-Zeile-Mapping (BL-015 Ausbau): Jede Zeile, deren Call-Text bereits ein
    Mapping hat (oder exakt passt), wird gruen markiert. Doppelklick auf eine
    Zeile oeffnet den CallFiguresPickerDialog mit ihrer Figuren-Menge
    (BL-210.5). Typ ist Pflichtfeld.

    Args:
        db: SongDB
        parent: Eltern-Widget
        seq_id: Falls gesetzt, wird diese bestehende Sequenz geladen (Bearbeiten).
        on_saved: Callback on_saved(seq_id, was_new) nach erfolgreichem Speichern.
    """

    MAX_CALLS = 15

    def __init__(self, db, parent=None, seq_id: int = None, on_saved=None):
        super().__init__(parent)
        self.db = db
        self._seq_id = seq_id              # None = Neuanlage
        self._on_saved = on_saved
        self._map_cache = {}               # call_text -> bool (gemappt?)
        self._matcher = None               # CallMatcher (lazy)
        self.setWindowTitle(_t("seq_editor_title"))
        self.setMinimumSize(440, 480)
        self.setModal(True)
        self._build_ui()
        if seq_id is not None:
            self._load_sequence(seq_id)
        self._update_title()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # --- Kopfbereich: Typ + Schwierigkeit ---
        head = QGroupBox(_t("seq_editor_head_group"))
        form = QFormLayout(head)

        self._combo_type = QComboBox()
        self._combo_type.setEditable(True)
        install_combo_click_to_open(self._combo_type)
        self._combo_type.setInsertPolicy(QComboBox.NoInsert)
        self._combo_type.addItem("")
        for t in self.db.get_sequence_type_values():
            self._combo_type.addItem(t)
        self._combo_type.setCurrentText("")
        form.addRow(_t("label_type"), self._combo_type)

        self._combo_difficulty = QComboBox()
        self._combo_difficulty.setEditable(True)
        install_combo_click_to_open(self._combo_difficulty)
        self._combo_difficulty.setInsertPolicy(QComboBox.NoInsert)
        self._combo_difficulty.addItem("")
        for d in self.db.get_sequence_difficulty_values():
            self._combo_difficulty.addItem(d)
        self._combo_difficulty.setCurrentText("")
        form.addRow(_t("label_difficulty"), self._combo_difficulty)

        # BL-191: frei vergebbarer Tag/Kategorie (Freitext mit Auto-Vervollstaendigung
        # ueber bereits genutzte Tags — verhindert leicht abweichende Schreibvarianten).
        self._combo_tags = QComboBox()
        self._combo_tags.setEditable(True)
        install_combo_click_to_open(self._combo_tags)
        self._combo_tags.setInsertPolicy(QComboBox.NoInsert)
        self._combo_tags.setToolTip(_t("seq_editor_tags_tooltip"))
        self._combo_tags.addItem("")
        for tg in self.db.get_sequence_tags_values():
            self._combo_tags.addItem(tg)
        self._combo_tags.setCurrentText("")
        form.addRow(_t("label_tags"), self._combo_tags)

        layout.addWidget(head)

        # --- Eingabe-Liste: ein Call pro Zeile ---
        hint = QLabel(_t("seq_editor_lines_hint"))
        hint.setWordWrap(True)
        hint.setStyleSheet("font-size: 11px; color: #888;")
        layout.addWidget(hint)

        self._edit_calls = _CallListEdit()
        self._edit_calls.setPlaceholderText(_t("seq_editor_placeholder"))
        self._edit_calls.on_line_double_click = self._handle_line_dblclick
        self._edit_calls.textChanged.connect(self._on_text_changed)
        layout.addWidget(self._edit_calls, 1)

        # Highlighter: gemappte Zeilen gruen
        self._highlighter = _MappingHighlighter(
            self._edit_calls.document(), self._is_mapped
        )
        # Debounce-Timer fuer das Neu-Hervorheben beim Tippen
        self._rehl_timer = QTimer(self)
        self._rehl_timer.setSingleShot(True)
        self._rehl_timer.setInterval(300)
        self._rehl_timer.timeout.connect(self._highlighter.rehighlight)

        self._lbl_count = QLabel()
        self._lbl_count.setStyleSheet("font-size: 11px; color: #999;")
        layout.addWidget(self._lbl_count)

        # --- Buttons ---
        # BL-191: autoDefault abschalten — sonst feuert ein Enter in einem der
        # editierbaren Combos (Typ/Difficulty/Tags) den ersten auto-default-Button
        # (+ Neu) und loest faelschlich den Verwerfen-Dialog aus.
        btn_row = QHBoxLayout()
        self._btn_new = QPushButton(_t("seq_editor_btn_new"))
        self._btn_new.setToolTip(_t("seq_editor_btn_new_tooltip"))
        self._btn_new.setAutoDefault(False)
        self._btn_new.setDefault(False)
        self._btn_new.clicked.connect(self._on_new)
        btn_row.addWidget(self._btn_new)

        self._btn_save = QPushButton(_t("seq_editor_btn_save"))
        self._btn_save.setStyleSheet("font-weight: bold;")
        self._btn_save.setAutoDefault(False)
        self._btn_save.setDefault(False)
        self._btn_save.clicked.connect(self._on_save)
        btn_row.addWidget(self._btn_save)

        self._btn_dup = QPushButton(_t("seq_editor_btn_dup"))
        self._btn_dup.setToolTip(_t("seq_editor_btn_dup_tooltip"))
        self._btn_dup.setAutoDefault(False)
        self._btn_dup.setDefault(False)
        self._btn_dup.clicked.connect(self._on_check_duplicate)
        btn_row.addWidget(self._btn_dup)

        btn_row.addStretch()

        btn_close = QPushButton(_t("btn_close"))
        btn_close.setAutoDefault(False)
        btn_close.setDefault(False)
        btn_close.clicked.connect(self.reject)
        btn_row.addWidget(btn_close)

        layout.addLayout(btn_row)
        self._update_line_count()

    # ---- Laden / Status ----

    def _load_sequence(self, seq_id: int):
        """Laedt eine bestehende Sequenz in die Felder (Bearbeiten-Modus)."""
        data = self.db.get_sequence_raw(seq_id)
        if not data:
            return
        self._combo_type.setCurrentText(data["seq_type"])
        self._combo_difficulty.setCurrentText(data["difficulty"])
        self._combo_tags.setCurrentText(data.get("tags", ""))
        calls = [f.strip() for f in data["fields"]
                 if f and f.strip() and f.strip() != "-"]
        self._edit_calls.setPlainText("\n".join(calls))
        self._update_line_count()

    def _update_title(self):
        if self._seq_id is None:
            self.setWindowTitle(_t("seq_editor_title"))
        else:
            self.setWindowTitle(_t("seq_editor_title_edit", id=self._seq_id))

    def _get_calls(self) -> list:
        """Liest die nicht-leeren Zeilen als Call-Liste."""
        text = self._edit_calls.toPlainText()
        return [ln.strip() for ln in text.splitlines() if ln.strip()]

    def _update_line_count(self):
        # Kein 15-Limit mehr — nur noch die Anzahl anzeigen (calls_json speichert
        # beliebig viele Calls; field_1..15 sind der Rueckwaerts-Mirror).
        n = len(self._get_calls())
        self._lbl_count.setText(_t("seq_editor_count_simple", count=n))
        self._lbl_count.setStyleSheet("font-size: 11px; color: #999;")

    # ---- Mapping-Markierung ----

    def _on_text_changed(self):
        """Bei Texteingabe: Zaehler aktualisieren + Neu-Hervorheben anstossen."""
        self._update_line_count()
        self._rehl_timer.start()

    def _matcher_obj(self):
        """Lazy CallMatcher ueber alle Teaching-Order-Calls."""
        if self._matcher is None:
            from sequence_mapper import CallMatcher
            self._matcher = CallMatcher(self.db.get_teaching_order_calls())
        return self._matcher

    def _exact_entity(self, text: str):
        """Gibt die entity_id zurueck, wenn der Text EXAKT (Score 1.0) zu einem
        bekannten Call passt — sonst None. Basis fuer Auto-Mapping."""
        score, eid = self._matcher_obj().suggest(text)
        if eid is not None and score >= 0.999:
            return eid
        return None

    def _is_mapped(self, text: str) -> bool:
        """Prueft (gecacht), ob ein Call-Text gemappt ODER ein exakter Treffer ist.

        Gruen also auch fuer Calls, die zwar noch keine Mapping-Zeile haben, aber
        exakt zu einem bekannten Call passen — diese werden beim Speichern als
        'auto'-Mapping persistiert.
        """
        key = text.strip()
        if not key:
            return False
        if key not in self._map_cache:
            mapped = self.db.get_entity_for_call_text(key) is not None
            if not mapped:
                mapped = self._exact_entity(key) is not None
            self._map_cache[key] = mapped
        return self._map_cache[key]

    def _persist_auto_mappings(self, calls: list):
        """Legt fuer exakte Treffer ohne Mapping-Zeile ein 'auto'-Mapping an.

        Wird beim Speichern aufgerufen, damit `recompute_sequence_max_to()`
        das Level berechnen kann. Unsichere/fuzzy Treffer bleiben unberuehrt.
        """
        for c in calls:
            key = c.strip()
            if not key:
                continue
            if self.db.get_entity_for_call_text(key) is not None:
                continue
            eid = self._exact_entity(key)
            if eid is not None:
                self.db.set_call_text_mapping(key, eid, mapped_by="auto")

    def _handle_line_dblclick(self, line: str) -> bool:
        """Doppelklick auf eine Zeile: Figuren-Picker oeffnen (BL-210.5).

        Immer, auch bei vorhandener Zuordnung: sonst kaeme man an eine fertige
        (womoeglich unvollstaendige) Menge nicht mehr heran. Vorbelegt mit der
        aktuellen Menge, ohne Zuordnung mit dem Matcher-Vorschlag. OK schreibt
        die Menge (mapped_by='manual'), Abbrechen schreibt nichts.

        Returns True, wenn der Doppelklick behandelt wurde (normales
        Wort-Markieren unterdruecken); False bei leerer Zeile.
        """
        key = line.strip()
        if not key:
            return False
        if self.db.get_teaching_order_count() == 0:
            QMessageBox.warning(self, _t("seq_map_picker_title"),
                                _t("call_mapping_no_to_calls"))
            return True
        current = self.db.get_call_text_figures(key)
        selected = current
        if not current:
            # Ohne Zuordnung den Matcher-Vorschlag vorab anhaken
            _score, suggested = self._matcher_obj().suggest(key)
            selected = [suggested] if suggested is not None else []
        entities = [(f"{cname}  [{prog}]" if prog else cname, eid)
                    for eid, cname, _to, prog in self.db.get_teaching_order_calls()
                    if not cname.startswith("--")]
        dlg = CallFiguresPickerDialog(entities, selected=selected, parent=self)
        dlg.setWindowTitle(_t("seq_map_picker_text", text=key))
        if dlg.exec() != QDialog.Accepted:
            return True
        ids = dlg.selected_entity_ids()
        if set(ids) != set(current):
            # Nur bei geaenderter Menge schreiben: sonst wuerde aus 'auto' ein
            # 'manual' und der Cover-Cache verworfen. Leere Auswahl entfernt
            # eine bestehende Zuordnung (wie im Call-Mapping).
            self.db.set_call_text_figures(key, ids, mapped_by="manual")
        # Cache verwerfen und neu hervorheben -> Zeile faerbt neu
        self._map_cache.pop(key, None)
        self._highlighter.rehighlight()
        return True

    # ---- Aktionen ----

    def _on_new(self):
        """Formular fuer eine neue Sequenz leeren."""
        if self._get_calls():
            reply = QMessageBox.question(
                self, _t("seq_editor_title"),
                _t("seq_editor_new_confirm"),
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No
            )
            if reply != QMessageBox.Yes:
                return
        self._seq_id = None
        self._combo_type.setCurrentText("")
        self._combo_difficulty.setCurrentText("")
        self._edit_calls.clear()
        self._edit_calls.setFocus()
        self._update_title()
        self._update_line_count()

    def _on_check_duplicate(self):
        """Prueft, ob die aktuelle Eingabe bereits als Sequenz existiert."""
        calls = self._get_calls()
        if not calls:
            QMessageBox.information(self, _t("seq_editor_btn_dup"),
                                    _t("seq_editor_empty"))
            return
        dup_id = self.db.find_sequence_by_fields(calls, exclude_id=self._seq_id)
        if dup_id is None:
            QMessageBox.information(self, _t("seq_editor_btn_dup"),
                                    _t("seq_editor_dup_none"))
        else:
            QMessageBox.warning(self, _t("seq_editor_btn_dup"),
                                _t("seq_editor_dup_found", id=dup_id))

    def _on_save(self):
        """Speichert die Sequenz (Neuanlage oder Update)."""
        calls = self._get_calls()
        if not calls:
            QMessageBox.warning(self, _t("seq_editor_title"),
                                _t("seq_editor_empty"))
            return
        # Kein 15-Call-Limit mehr: calls_json speichert die volle Liste
        # (field_1..15 bleiben als Mirror). Siehe docs/seq_calls_json_umbau.md.

        seq_type = self._combo_type.currentText().strip()
        difficulty = self._combo_difficulty.currentText().strip()
        tags = self._combo_tags.currentText().strip()

        # Typ ist Pflichtfeld
        if not seq_type:
            QMessageBox.warning(self, _t("seq_editor_title"),
                                _t("seq_editor_type_required"))
            self._combo_type.setFocus()
            return

        # Exakte Treffer als 'auto'-Mapping sichern, damit das Level berechnet wird
        self._persist_auto_mappings(calls)

        was_new = self._seq_id is None
        if was_new:
            new_id = self.db.insert_sequence(calls, level_original="",
                                             seq_type=seq_type,
                                             difficulty=difficulty, tags=tags)
        else:
            new_id = self._seq_id
            self.db.update_sequence(self._seq_id, calls, level_original="",
                                    seq_type=seq_type, difficulty=difficulty,
                                    tags=tags)

        if self._on_saved:
            self._on_saved(new_id, was_new)

        QMessageBox.information(self, _t("seq_editor_title"),
                                _t("seq_editor_saved"))
        # Nach Neuanlage gleich fuer den naechsten Datensatz leeren
        if was_new:
            self._combo_type.setCurrentText(seq_type)
            self._combo_difficulty.setCurrentText(difficulty)
            self._combo_tags.setCurrentText(tags)
            self._edit_calls.clear()
            self._edit_calls.setFocus()
            self._update_line_count()


class FreetextSequenceImportDialog(QDialog):
    """Importiert Sequenzen aus einer Freitext-Datei (BL-098).

    Unterstuetzt drei Formate (auto-erkannt):
      1. Eine Zeile pro Sequenz, Calls durch Komma getrennt.
      2. Ein Call pro Zeile, Sequenzen durch Leerzeile(n) getrennt.
      3. Wie 2., zusaetzlich Trennzeichen am Ende der Zeile (`,` oder `;`).

    Algorithmus:
      - Datei in Bloecke splitten. Trenner ist:
          * eine oder mehrere Leerzeilen, ODER
          * eine Ceder-Header-Zeile (enthaelt `ID=<digits>` — z.B.
            "Mainstream -- Singer (Corner progression)   Easy   ID=6734   Print").
        Header-Zeilen werden verworfen.
      - Pro Block: Zeilen trimmen, trailing `,;` strippen.
      - Block mit genau 1 Zeile + Komma → per `,` splitten (Format 1).
      - Sonst → jede Zeile = ein Call (Format 2/3).
      - Max. 15 Calls pro Sequenz (Rest wird abgeschnitten, in Vorschau angezeigt).
    """

    MAX_CALLS = 15
    PREVIEW_BLOCKS = 3
    # Ceder-Header-Erkennung: Zeilen mit ID=<Zahl> sind Sequenz-Trennzeilen.
    _CEDER_HEADER_RE = re.compile(r'\bID\s*=\s*\d+\b', re.IGNORECASE)

    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self._parsed = []  # list[list[str]]
        self._truncated_count = 0
        self.setWindowTitle(_t("freetext_import_title"))
        self.setModal(True)
        self.resize(700, 600)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # --- Datei-Auswahl ---
        file_row = QHBoxLayout()
        file_row.addWidget(QLabel(_t("freetext_import_file")))
        self._edit_path = QLineEdit()
        self._edit_path.setReadOnly(True)
        file_row.addWidget(self._edit_path, 1)
        btn_browse = QPushButton("...")
        btn_browse.setObjectName("fileBtn")
        btn_browse.setFixedWidth(36)
        btn_browse.clicked.connect(self._on_browse)
        file_row.addWidget(btn_browse)
        layout.addLayout(file_row)

        # --- Typ + Schwierigkeit ---
        meta_form = QFormLayout()
        meta_form.setLabelAlignment(Qt.AlignRight)

        self._combo_type = QComboBox()
        self._combo_type.setEditable(True)
        install_combo_click_to_open(self._combo_type)
        self._combo_type.setInsertPolicy(QComboBox.NoInsert)
        self._combo_type.addItem("")
        for t in self.db.get_sequence_type_values():
            self._combo_type.addItem(t)
        self._combo_type.setCurrentText("")
        self._combo_type.currentTextChanged.connect(self._update_button_state)
        meta_form.addRow(_t("label_type") + " *", self._combo_type)

        self._combo_difficulty = QComboBox()
        self._combo_difficulty.setEditable(True)
        install_combo_click_to_open(self._combo_difficulty)
        self._combo_difficulty.setInsertPolicy(QComboBox.NoInsert)
        self._combo_difficulty.addItem("")
        for d in self.db.get_sequence_difficulty_values():
            self._combo_difficulty.addItem(d)
        self._combo_difficulty.setCurrentText("")
        meta_form.addRow(_t("label_difficulty"), self._combo_difficulty)

        layout.addLayout(meta_form)

        # --- Vorschau ---
        layout.addWidget(QLabel(_t("freetext_import_preview")))
        self._preview = QTextBrowser()
        self._preview.setStyleSheet(
            "QTextBrowser { background-color: white; color: black; }"
        )
        layout.addWidget(self._preview, 1)

        self._status_label = QLabel("")
        self._status_label.setStyleSheet("color: #555; font-size: 11px;")
        layout.addWidget(self._status_label)

        # --- Buttons ---
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self._btn_import = QPushButton(_t("btn_import"))
        self._btn_import.setEnabled(False)
        self._btn_import.clicked.connect(self.accept)
        btn_row.addWidget(self._btn_import)
        btn_cancel = QPushButton(_t("btn_cancel"))
        btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(btn_cancel)
        layout.addLayout(btn_row)

    # ---- Datei-Auswahl + Parsing ----

    def _on_browse(self):
        settings = QSettings()
        last_dir = str(settings.value("sequences/freetext_import_dir", ""))
        if not last_dir or not os.path.isdir(last_dir):
            last_dir = os.path.expanduser("~")
        path, _ignored = QFileDialog.getOpenFileName(
            self, _t("dialog_freetext_select"), last_dir,
            _t("filter_freetext")
        )
        if not path:
            return
        settings.setValue("sequences/freetext_import_dir",
                          os.path.dirname(path))
        self._edit_path.setText(path)
        self._load_and_parse(path)

    def _load_and_parse(self, path: str):
        try:
            try:
                with open(path, encoding="utf-8") as f:
                    text = f.read()
            except UnicodeDecodeError:
                with open(path, encoding="cp1252") as f:
                    text = f.read()
        except Exception as e:
            QMessageBox.warning(self, _t("freetext_import_title"),
                                _t("freetext_import_read_error", error=str(e)))
            self._parsed = []
            self._update_preview()
            self._update_button_state()
            return

        self._parsed, self._truncated_count = self._parse_text(text)
        self._update_preview()
        self._update_button_state()

    @classmethod
    def _parse_text(cls, text: str):
        """Parst Freitext in eine Liste von Sequenzen.

        Returns:
            (sequences, truncated_count) — sequences ist list[list[str]],
            truncated_count = wie viele Sequenzen auf 15 Calls gekuerzt wurden.
        """
        # Zeilenenden normalisieren, BEVOR gesplittet wird. Manche Quellen
        # (z. B. SqView-Exporte) schreiben pro Zeile ein doppeltes CR: '\r\r\n'.
        # splitlines() zerlegt das lone '\r' in eine zusaetzliche Phantom-
        # Leerzeile — dann wuerde jeder Call als eigene Sequenz erkannt.
        # '\r+\n' → '\n' (deckt '\r\n' und '\r\r\n…' ab), danach lone CR (alt-Mac).
        text = re.sub(r'\r+\n', '\n', text)
        text = text.replace('\r', '\n')
        # Zeilenweise verarbeiten — Leerzeile bleibt erhalten als Trenner
        raw_lines = text.split('\n')
        sequences = []
        truncated = 0
        block_lines = []

        def _flush_block():
            nonlocal truncated
            if not block_lines:
                return
            # Block-Inhalt: Zeilen trimmen + trailing , ; entfernen
            cleaned = []
            for ln in block_lines:
                s = ln.strip().rstrip(',;').strip()
                if s:
                    cleaned.append(s)
            if not cleaned:
                return
            # Format-Erkennung: 1 Zeile + Komma → Komma-Split, sonst je Zeile = ein Call
            if len(cleaned) == 1 and ',' in cleaned[0]:
                calls = [c.strip() for c in cleaned[0].split(',')]
                calls = [c for c in calls if c]
            else:
                calls = cleaned
            if not calls:
                return
            # Kein 15-Limit mehr — volle Liste uebernehmen (calls_json speichert alles).
            sequences.append(calls)

        for ln in raw_lines:
            if ln.strip() == "" or cls._CEDER_HEADER_RE.search(ln):
                # Leerzeile ODER Ceder-Header → vorigen Block abschliessen,
                # Header-Zeile selbst nicht uebernehmen.
                _flush_block()
                block_lines = []
            else:
                block_lines.append(ln)
        _flush_block()

        return sequences, truncated

    def _update_preview(self):
        if not self._parsed:
            self._preview.setPlainText("")
            self._status_label.setText(_t("freetext_import_status_empty"))
            return

        # HTML-Vorschau: erste N Bloecke
        parts = []
        for i, calls in enumerate(self._parsed[:self.PREVIEW_BLOCKS], start=1):
            parts.append(f"<b>#{i}</b>")
            for c in calls:
                # einfache HTML-Escapes
                esc = (c.replace('&', '&amp;')
                        .replace('<', '&lt;').replace('>', '&gt;'))
                parts.append(f"&nbsp;&nbsp;{esc}")
            parts.append("")
        if len(self._parsed) > self.PREVIEW_BLOCKS:
            parts.append(f"<i>… +{len(self._parsed) - self.PREVIEW_BLOCKS}</i>")
        self._preview.setHtml("<br>".join(parts))

        status = _t("freetext_import_status",
                    count=len(self._parsed))
        if self._truncated_count > 0:
            status += "  " + _t("freetext_import_status_truncated",
                                count=self._truncated_count,
                                max=self.MAX_CALLS)
        self._status_label.setText(status)

    def _update_button_state(self, *_args):
        has_seqs = bool(self._parsed)
        has_type = bool(self._combo_type.currentText().strip())
        self._btn_import.setEnabled(has_seqs and has_type)

    # ---- Ergebnis fuer den Aufrufer ----

    def get_result(self):
        """Returns: (sequences, seq_type, difficulty)"""
        return (
            list(self._parsed),
            self._combo_type.currentText().strip(),
            self._combo_difficulty.currentText().strip(),
        )


class SequenceImportDialog(QDialog):
    """Universeller Sequenz-Import (BL-098).

    Erkennt automatisch das Format der ausgewaehlten Datei(en) und
    bietet eine einheitliche Oberflaeche mit Vorschau, Bulk-Override
    fuer Typ/Schwierigkeit und Duplikat-Erkennung.

    Unterstuetzte Formate:
      - MDB / ACCDB (alte CC1-Datenbank)
      - JSON (Ceder-Eigen-Schema, Array mit calls/level/seq_type/difficulty)
      - CSDS (Vic Ceder Choreo-DB Export, @-Bloecke + #KEY=VALUE#)
      - Freitext (Leerzeile / Ceder-Web-Header als Trenner)

    Quellen-Modus pro Meta-Feld:
      - "Bulk" (Standard): Alle importierten Sequenzen bekommen den im
        Dialog gewaehlten Wert.
      - "Aus Datei": Nur verfuegbar wenn das Format pro Sequenz Werte
        liefert (JSON, CSDS). Bulk-Wert wird als Fallback genutzt, wenn
        die Datei fuer eine Sequenz keinen Wert hat.
    """

    FMT_AUTO = "auto"
    FMT_MDB = "mdb"
    FMT_JSON = "json"
    FMT_CSDS = "csds"
    FMT_FREETEXT = "freetext"

    SRC_BULK = "bulk"
    SRC_FILE = "file"

    # Gross-/Kleinschreibung der Call-Texte beim Import
    CASE_ASIS  = "asis"    # 1. wie im Text (unveraendert)
    CASE_UPPER = "upper"   # 2. ALLES GROSSBUCHSTABEN
    CASE_TITLE = "title"   # 3. Erster Buchstabe je Wort gross, Rest klein

    MAX_CALLS = 15
    PREVIEW_BLOCKS = 3

    # CSDS-Konstanten (Kopie aus import_from_csds, damit Dialog autark ist).
    # Kanonische Ceder-Konvention: "Singer (...)" + Pfeil "➔" als Trenner —
    # muss zu song_db.canonicalize_seq_type und der Kopie in import_from_csds passen.
    _SEQTYPE_NAMES = {
        "5":   "Static Set ➔ Resolve",
        "10":  "Singer (Corner progression)",
        "20":  "Singer (R-H Lady progression)",
        "30":  "Singing break",
        "40":  "Stir the bucket",
        "80":  "Static Set ➔ Zero Line",
        "90":  "Static Set ➔ Zero Box",
        "95":  "Zero Line ➔ Resolve",
        "100": "Zero Line ➔ Zero Line",
        "110": "Zero Line ➔ Zero Box",
        "115": "Zero Box ➔ Resolve",
        "120": "Zero Box ➔ Zero Line",
        "130": "Zero Box ➔ Zero Box",
    }
    _DIFFICULTY_MAP = {"EASY": "Easy", "MEDIUM": "Medium", "HARD": "Hard"}
    _CEDER_HEADER_RE = re.compile(r'\bID\s*=\s*\d+\b', re.IGNORECASE)

    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self._paths = []
        self._detected_format = None  # FMT_* nach Datei-Auswahl
        self._parsed = []  # list[dict]: calls, seq_type, difficulty, level, source_id
        self._inserted_count = 0
        self._skipped_dupes = 0
        self.setWindowTitle(_t("seq_import_title"))
        self.setModal(True)
        self.resize(750, 700)
        self._build_ui()
        self._update_meta_widgets()
        self._update_preview()
        self._update_button_state()

    # ---- UI ----

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # --- Datei-Auswahl ---
        file_row = QHBoxLayout()
        file_row.addWidget(QLabel(_t("seq_import_file")))
        self._edit_path = QLineEdit()
        self._edit_path.setReadOnly(True)
        file_row.addWidget(self._edit_path, 1)
        btn_browse = QPushButton("...")
        btn_browse.setObjectName("fileBtn")
        btn_browse.setFixedWidth(36)
        btn_browse.clicked.connect(self._on_browse)
        file_row.addWidget(btn_browse)
        layout.addLayout(file_row)

        # --- Format-Erkennung + Override ---
        fmt_row = QHBoxLayout()
        fmt_row.addWidget(QLabel(_t("seq_import_format")))
        self._label_detected = QLabel("—")
        self._label_detected.setStyleSheet("font-weight: bold;")
        fmt_row.addWidget(self._label_detected, 1)

        fmt_row.addWidget(QLabel(_t("seq_import_override")))
        self._combo_format = QComboBox()
        self._combo_format.addItem(_t("seq_fmt_auto"), self.FMT_AUTO)
        self._combo_format.addItem(_t("seq_fmt_mdb"), self.FMT_MDB)
        self._combo_format.addItem(_t("seq_fmt_json"), self.FMT_JSON)
        self._combo_format.addItem(_t("seq_fmt_csds"), self.FMT_CSDS)
        self._combo_format.addItem(_t("seq_fmt_freetext"), self.FMT_FREETEXT)
        self._combo_format.currentIndexChanged.connect(self._on_format_changed)
        fmt_row.addWidget(self._combo_format)
        layout.addLayout(fmt_row)

        # --- Typ + Schwierigkeit mit Quellen-Schalter ---
        meta_form = QFormLayout()
        meta_form.setLabelAlignment(Qt.AlignRight)

        type_row = QHBoxLayout()
        self._combo_type_src = QComboBox()
        self._combo_type_src.addItem(_t("seq_import_src_bulk"), self.SRC_BULK)
        self._combo_type_src.addItem(_t("seq_import_src_file"), self.SRC_FILE)
        self._combo_type_src.currentIndexChanged.connect(self._update_preview)
        self._combo_type_src.currentIndexChanged.connect(self._update_button_state)
        self._combo_type_src.setFixedWidth(160)
        type_row.addWidget(self._combo_type_src)
        self._combo_type = QComboBox()
        self._combo_type.setEditable(True)
        install_combo_click_to_open(self._combo_type)
        self._combo_type.setInsertPolicy(QComboBox.NoInsert)
        self._combo_type.addItem("")
        for t in self.db.get_sequence_type_values():
            self._combo_type.addItem(t)
        self._combo_type.setCurrentText("")
        self._combo_type.currentTextChanged.connect(self._update_preview)
        self._combo_type.currentTextChanged.connect(self._update_button_state)
        type_row.addWidget(self._combo_type, 1)
        meta_form.addRow(_t("label_type") + " *", type_row)

        diff_row = QHBoxLayout()
        self._combo_diff_src = QComboBox()
        self._combo_diff_src.addItem(_t("seq_import_src_bulk"), self.SRC_BULK)
        self._combo_diff_src.addItem(_t("seq_import_src_file"), self.SRC_FILE)
        self._combo_diff_src.currentIndexChanged.connect(self._update_preview)
        self._combo_diff_src.setFixedWidth(160)
        diff_row.addWidget(self._combo_diff_src)
        self._combo_difficulty = QComboBox()
        self._combo_difficulty.setEditable(True)
        install_combo_click_to_open(self._combo_difficulty)
        self._combo_difficulty.setInsertPolicy(QComboBox.NoInsert)
        self._combo_difficulty.addItem("")
        for d in self.db.get_sequence_difficulty_values():
            self._combo_difficulty.addItem(d)
        self._combo_difficulty.setCurrentText("")
        self._combo_difficulty.currentTextChanged.connect(self._update_preview)
        diff_row.addWidget(self._combo_difficulty, 1)
        meta_form.addRow(_t("label_difficulty"), diff_row)

        # Gross-/Kleinschreibung der Call-Texte (Standard: wie im Text)
        self._combo_case = QComboBox()
        self._combo_case.addItem(_t("seq_import_case_asis"),  self.CASE_ASIS)
        self._combo_case.addItem(_t("seq_import_case_upper"), self.CASE_UPPER)
        self._combo_case.addItem(_t("seq_import_case_title"), self.CASE_TITLE)
        self._combo_case.setCurrentIndex(0)
        self._combo_case.currentIndexChanged.connect(self._update_preview)
        meta_form.addRow(_t("seq_import_case_label"), self._combo_case)

        layout.addLayout(meta_form)

        # --- Vorschau ---
        layout.addWidget(QLabel(_t("seq_import_preview")))
        self._preview = QTextBrowser()
        self._preview.setStyleSheet(
            "QTextBrowser { background-color: white; color: black; }"
        )
        layout.addWidget(self._preview, 1)

        # --- Optionen + Status ---
        self._chk_dedup = QCheckBox(_t("seq_import_dedup"))
        self._chk_dedup.setChecked(True)
        self._chk_dedup.stateChanged.connect(self._update_preview)
        layout.addWidget(self._chk_dedup)

        self._status_label = QLabel("")
        self._status_label.setStyleSheet("color: #555; font-size: 11px;")
        layout.addWidget(self._status_label)

        # --- Buttons ---
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self._btn_import = QPushButton(_t("btn_import"))
        self._btn_import.setEnabled(False)
        self._btn_import.clicked.connect(self._on_import)
        btn_row.addWidget(self._btn_import)
        btn_cancel = QPushButton(_t("btn_cancel"))
        btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(btn_cancel)
        layout.addLayout(btn_row)

    # ---- Datei-Auswahl ----

    def _on_browse(self):
        settings = QSettings()
        last_dir = str(settings.value("sequences/universal_import_dir", ""))
        if not last_dir or not os.path.isdir(last_dir):
            last_dir = os.path.expanduser("~")
        paths, _ignored = QFileDialog.getOpenFileNames(
            self, _t("seq_import_dialog_select"), last_dir,
            _t("seq_import_filter")
        )
        if not paths:
            return
        settings.setValue("sequences/universal_import_dir",
                          os.path.dirname(paths[0]))
        self._paths = paths
        # Anzeige: erste Datei + Anzahl
        if len(paths) == 1:
            self._edit_path.setText(paths[0])
        else:
            self._edit_path.setText(
                f"{paths[0]}  (+{len(paths) - 1})"
            )
        self._reparse()

    def _on_format_changed(self, *_args):
        if self._paths:
            self._reparse()

    def _reparse(self):
        """Erkennt Format (falls Auto) und parst alle gewaehlten Dateien."""
        override = self._combo_format.currentData()
        if override == self.FMT_AUTO:
            fmt = self._detect_format(self._paths[0]) if self._paths else None
        else:
            fmt = override
        self._detected_format = fmt

        # Label aktualisieren
        if fmt is None:
            self._label_detected.setText("—")
        else:
            self._label_detected.setText(self._format_label(fmt))

        # Parsen
        if not self._paths or fmt is None:
            self._parsed = []
        else:
            try:
                self._parsed = self._parse_paths(self._paths, fmt)
            except Exception as e:
                QMessageBox.warning(self, _t("seq_import_title"),
                                    _t("seq_import_parse_error", error=str(e)))
                self._parsed = []

        # MDB: nur erste Datei wird genutzt — Hinweis falls mehrere gewaehlt
        if fmt == self.FMT_MDB and len(self._paths) > 1:
            QMessageBox.information(self, _t("seq_import_title"),
                                    _t("seq_import_mdb_only_first"))

        self._update_meta_widgets()
        self._update_preview()
        self._update_button_state()

    def _format_label(self, fmt: str) -> str:
        return {
            self.FMT_MDB:      _t("seq_fmt_mdb"),
            self.FMT_JSON:     _t("seq_fmt_json"),
            self.FMT_CSDS:     _t("seq_fmt_csds"),
            self.FMT_FREETEXT: _t("seq_fmt_freetext"),
        }.get(fmt, "—")

    @classmethod
    def _detect_format(cls, path: str) -> str:
        """Erkennt das Format anhand Datei-Endung + Inhalts-Stichprobe."""
        ext = os.path.splitext(path)[1].lower()
        if ext in (".mdb", ".accdb"):
            return cls.FMT_MDB
        # Inhalts-Stichprobe (erste 4 KB reichen fuer alle Sniffs)
        try:
            try:
                with open(path, encoding="utf-8") as f:
                    head = f.read(4096)
            except UnicodeDecodeError:
                with open(path, encoding="cp1252") as f:
                    head = f.read(4096)
        except Exception:
            return cls.FMT_FREETEXT
        # CSDS: @-Block mit #REC=/#SEQTYPE=
        if "@" in head and ("#REC=" in head or "#SEQTYPE=" in head):
            return cls.FMT_CSDS
        # JSON: beginnt mit [ oder {
        stripped = head.lstrip()
        if ext == ".json" or stripped.startswith("[") or stripped.startswith("{"):
            try:
                import json as _json
                with open(path, encoding="utf-8") as f:
                    data = _json.load(f)
                if isinstance(data, (list, dict)):
                    return cls.FMT_JSON
            except Exception:
                pass
        return cls.FMT_FREETEXT

    # ---- Parser pro Format ----

    def _parse_paths(self, paths: list, fmt: str) -> list:
        """Parst die gewaehlten Dateien zu normalisierten Sequenz-Dicts.

        Returns:
            list[dict] mit keys: calls (list[str]), seq_type (str),
            difficulty (str), level (str), source_id (str).
        """
        if fmt == self.FMT_MDB:
            return self._parse_mdb(paths[0])
        if fmt == self.FMT_JSON:
            return self._parse_json(paths)
        if fmt == self.FMT_CSDS:
            return self._parse_csds(paths)
        return self._parse_freetext(paths)

    @staticmethod
    def _parse_mdb(path: str) -> list:
        # mdb_reader liegt in src/migration/ (Sub-Paket neben main.py)
        migration_dir = os.path.join(os.path.dirname(__file__), "migration")
        if migration_dir not in sys.path:
            sys.path.insert(0, migration_dir)
        from mdb_reader import MdbReader  # type: ignore
        reader = MdbReader(path)
        raw = reader.read_sequences()
        result = []
        for seq in raw:
            calls = []
            for i in range(1, 16):
                val = seq.get(f"Feld{i}", None)
                if isinstance(val, str) and val.strip() and val.strip() != "-":
                    calls.append(val.strip())
            if not calls:
                continue
            level = seq.get("Level", "") or ""
            if isinstance(level, str):
                level = level.strip()
            result.append({
                "calls": calls,   # kein 15-Limit mehr (calls_json)
                "seq_type": "",
                "difficulty": "",
                "level": level,
                "source_id": "",
            })
        return result

    @staticmethod
    def _parse_json(paths: list) -> list:
        import json as _json
        result = []
        seen_ids = set()
        for path in paths:
            try:
                with open(path, encoding="utf-8") as f:
                    data = _json.load(f)
            except Exception as e:
                print(f"[SeqImport JSON] {path}: {e}")
                continue
            if not isinstance(data, list):
                continue
            for seq in data:
                if not isinstance(seq, dict):
                    continue
                src_id = str(seq.get("id", "") or "")
                if src_id and src_id in seen_ids:
                    continue
                if src_id:
                    seen_ids.add(src_id)
                calls_raw = seq.get("calls", [])
                calls = [str(c).strip() for c in calls_raw
                         if isinstance(c, str) and c.strip()]
                if not calls:
                    continue
                result.append({
                    "calls": calls,   # kein 15-Limit mehr (calls_json)
                    "seq_type": str(seq.get("seq_type", "") or "").strip(),
                    "difficulty": str(seq.get("difficulty", "") or "").strip(),
                    "level": str(seq.get("level", "") or "").strip(),
                    "source_id": src_id,
                })
        return result

    @classmethod
    def _parse_csds(cls, paths: list) -> list:
        import re as _re
        def _clean_call(raw: str) -> str:
            cleaned = _re.sub(r'<C[^>]*>(.*?)</C>', r'\1', raw)
            return cleaned.rstrip(',').strip()

        result = []
        seen_ids = set()
        for path in paths:
            try:
                with open(path, encoding="utf-8", errors="replace") as f:
                    text = f.read()
            except Exception as e:
                print(f"[SeqImport CSDS] {path}: {e}")
                continue
            for block in text.split('@'):
                lines = block.splitlines()
                difficulty = ""
                rec_id = ""
                seq_type = ""
                calls = []
                for line in lines:
                    s = line.strip()
                    if not s:
                        continue
                    if s.startswith('#') and s.endswith('#'):
                        inner = s[1:-1]
                        if inner in cls._DIFFICULTY_MAP:
                            difficulty = cls._DIFFICULTY_MAP[inner]
                        elif inner.startswith('REC='):
                            rec_id = inner[4:]
                        elif inner.startswith('SEQTYPE='):
                            seq_type = cls._SEQTYPE_NAMES.get(
                                inner[8:], inner[8:])
                    else:
                        call = _clean_call(s)
                        if call:
                            calls.append(call)
                if not calls:
                    continue
                if rec_id and rec_id in seen_ids:
                    continue
                if rec_id:
                    seen_ids.add(rec_id)
                result.append({
                    "calls": calls,   # kein 15-Limit mehr (calls_json)
                    "seq_type": seq_type,
                    "difficulty": difficulty,
                    "level": "",
                    "source_id": rec_id,
                })
        return result

    @classmethod
    def _parse_freetext(cls, paths: list) -> list:
        result = []
        for path in paths:
            try:
                # newline="" verhindert die Universal-Newline-Uebersetzung
                # beim Lesen. Sonst wandelt Python '\r\r\n' (SqView-Export:
                # doppeltes CR pro Zeile) schon hier in '\n\n' um — eine
                # Phantom-Leerzeile pro Call, die _parse_text nicht mehr von
                # einem echten Sequenz-Trenner unterscheiden koennte. Mit
                # rohem '\r' normalisiert _parse_text '\r+\n' → '\n' korrekt.
                try:
                    with open(path, encoding="utf-8", newline="") as f:
                        text = f.read()
                except UnicodeDecodeError:
                    with open(path, encoding="cp1252", newline="") as f:
                        text = f.read()
            except Exception as e:
                print(f"[SeqImport Freitext] {path}: {e}")
                continue
            sequences, _truncated = FreetextSequenceImportDialog._parse_text(text)
            for calls in sequences:
                result.append({
                    "calls": calls,   # kein 15-Limit mehr (calls_json)
                    "seq_type": "",
                    "difficulty": "",
                    "level": "",
                    "source_id": "",
                })
        return result

    # ---- Meta-Aufloesung (Bulk vs. aus Datei) ----

    def _has_meta_in_file(self) -> tuple:
        """Returns (has_type, has_diff) — gibt es im Parser-Output Werte?"""
        if not self._parsed:
            return False, False
        has_type = any(s.get("seq_type") for s in self._parsed)
        has_diff = any(s.get("difficulty") for s in self._parsed)
        return has_type, has_diff

    def _update_meta_widgets(self):
        """Aktiviert/Deaktiviert die "Aus Datei"-Optionen je nach Format."""
        has_type, has_diff = self._has_meta_in_file()
        # Type-Quelle
        type_src_model = self._combo_type_src.model()
        type_src_model.item(1).setEnabled(has_type)
        if not has_type and self._combo_type_src.currentData() == self.SRC_FILE:
            self._combo_type_src.setCurrentIndex(0)
        # Difficulty-Quelle
        diff_src_model = self._combo_diff_src.model()
        diff_src_model.item(1).setEnabled(has_diff)
        if not has_diff and self._combo_diff_src.currentData() == self.SRC_FILE:
            self._combo_diff_src.setCurrentIndex(0)

    def _resolve_meta(self, seq: dict) -> tuple:
        """Wendet Quellen-Modus auf eine Sequenz an. Returns (seq_type, difficulty)."""
        bulk_type = self._combo_type.currentText().strip()
        bulk_diff = self._combo_difficulty.currentText().strip()
        if self._combo_type_src.currentData() == self.SRC_FILE:
            seq_type = seq.get("seq_type", "") or bulk_type
        else:
            seq_type = bulk_type
        if self._combo_diff_src.currentData() == self.SRC_FILE:
            difficulty = seq.get("difficulty", "") or bulk_diff
        else:
            difficulty = bulk_diff
        return seq_type, difficulty

    @staticmethod
    def _apply_case_one(text: str, mode: str) -> str:
        """Wendet den Gross-/Kleinschreibungs-Modus auf einen Call-Text an.

        CASE_TITLE macht jeden Buchstaben gross, dem KEIN alphanumerisches
        Zeichen vorausgeht — also am Wortanfang und auch nach Trennzeichen wie
        Leerzeichen, '-', '(', ')', '/', '&'. Nach einer Ziffer bleibt der
        Buchstabe klein, damit '1ST' zu '1st' wird (nicht '1St' wie .title()).
        Beispiele: 'WALK-GIRLS' -> 'Walk-Girls', '(LOOK AT HER)' -> '(Look At Her)'.
        """
        if mode == SequenceImportDialog.CASE_UPPER:
            return text.upper()
        if mode == SequenceImportDialog.CASE_TITLE:
            out = []
            prev_alnum = False
            for ch in text:
                if ch.isalpha():
                    out.append(ch.lower() if prev_alnum else ch.upper())
                else:
                    out.append(ch)
                prev_alnum = ch.isalnum()
            return "".join(out)
        return text  # CASE_ASIS

    def _cased_calls(self, seq: dict) -> list:
        """Call-Liste einer Sequenz mit angewandtem Gross-/Kleinschreibungs-Modus."""
        mode = self._combo_case.currentData()
        if mode == self.CASE_ASIS:
            return list(seq["calls"])
        return [self._apply_case_one(c, mode) for c in seq["calls"]]

    # ---- Vorschau + Status ----

    def _build_dupe_set(self) -> set:
        """Liest alle existierenden calls_json fuer O(1)-Dubletten-Check.

        Ueber die volle Callliste (calls_json) statt der 15 Mirror-Felder, damit
        >15-Call-Sequenzen nicht faelschlich als Dublette gelten (BL calls_json)."""
        try:
            rows = self.db._conn.execute(
                "SELECT calls_json FROM sequences"
            ).fetchall()
            return set(r[0] for r in rows if r[0])
        except Exception as e:
            print(f"[SeqImport] Dubletten-Cache fehlgeschlagen: {e}")
            return set()

    @staticmethod
    def _fields_tuple(calls: list):
        """Dubletten-Schluessel = kanonisches calls_json (volle Liste, kein 15-Cap)."""
        return calls_to_json(calls)

    def _count_duplicates(self) -> int:
        if not self._chk_dedup.isChecked() or not self._parsed:
            return 0
        existing = self._build_dupe_set()
        if not existing:
            return 0
        seen = set(existing)
        dupes = 0
        for seq in self._parsed:
            key = self._fields_tuple(self._cased_calls(seq))
            if key in seen:
                dupes += 1
            else:
                seen.add(key)
        return dupes

    def _update_preview(self, *_args):
        if not self._parsed:
            self._preview.setPlainText("")
            self._status_label.setText(_t("seq_import_status_empty"))
            return

        parts = []
        for i, seq in enumerate(self._parsed[:self.PREVIEW_BLOCKS], start=1):
            seq_type, difficulty = self._resolve_meta(seq)
            meta_bits = []
            if seq_type:
                meta_bits.append(seq_type)
            if difficulty:
                meta_bits.append(difficulty)
            if seq.get("level"):
                meta_bits.append(seq["level"])
            meta = " · ".join(meta_bits) if meta_bits else "—"
            parts.append(f"<b>#{i}</b>  <i>{meta}</i>")
            for c in self._cased_calls(seq):
                esc = (c.replace('&', '&amp;')
                        .replace('<', '&lt;').replace('>', '&gt;'))
                parts.append(f"&nbsp;&nbsp;{esc}")
            parts.append("")
        if len(self._parsed) > self.PREVIEW_BLOCKS:
            parts.append(f"<i>… +{len(self._parsed) - self.PREVIEW_BLOCKS}</i>")
        self._preview.setHtml("<br>".join(parts))

        # Status: erkannt / davon Duplikate
        total = len(self._parsed)
        dupes = self._count_duplicates()
        if dupes > 0:
            status = _t("seq_import_status_with_dupes",
                        total=total, new=total - dupes, dupes=dupes)
        else:
            status = _t("seq_import_status_total", total=total)
        self._status_label.setText(status)

    def _update_button_state(self, *_args):
        if not self._parsed:
            self._btn_import.setEnabled(False)
            return
        # Typ muss vorhanden sein — entweder per Bulk oder pro Sequenz
        if self._combo_type_src.currentData() == self.SRC_BULK:
            has_type = bool(self._combo_type.currentText().strip())
        else:
            # File-Mode: pro Sequenz oder Fallback Bulk
            fallback = self._combo_type.currentText().strip()
            has_type = all((s.get("seq_type") or fallback)
                           for s in self._parsed)
        self._btn_import.setEnabled(has_type)

    # ---- Import ----

    def _on_import(self):
        if not self._parsed:
            return
        # Meta pro Sequenz aufloesen, dann per Bulk-Import (schnell, eine
        # Transaktion, Index/Cache einmal) einspielen. Dedup gegen Bestand nur,
        # wenn die Checkbox gesetzt ist (calls_json-Schluessel).
        dedup = self._chk_dedup.isChecked()
        seqs = []
        for seq in self._parsed:
            calls = self._cased_calls(seq)
            if not calls:
                continue
            seq_type, difficulty = self._resolve_meta(seq)
            seqs.append({"calls": calls, "level": seq.get("level", ""),
                         "seq_type": seq_type, "difficulty": difficulty})

        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            inserted, skipped = self.db.bulk_import_sequences(
                seqs, source="", dedup_against_existing=dedup)
        finally:
            QApplication.restoreOverrideCursor()

        self._inserted_count = inserted
        self._skipped_dupes = skipped
        self.accept()

    def get_summary(self) -> tuple:
        """Returns (inserted, skipped_dupes) — fuer den Aufrufer."""
        return self._inserted_count, self._skipped_dupes


class CallFiguresPickerDialog(QDialog):
    """Mehrfach-Picker: Figuren-Menge eines Call-Texts per Haken-Liste (BL-210.4).

    Eigenstaendig (keine DB, keine Interna anderer Dialoge), damit ihn auch der
    Sequenz-Editor nutzen kann. Ein Haken plus OK ist der Einzelfall, kein
    Haken plus OK die leere Menge (= Zuordnung entfernen).

    Args:
        entities: [(label, entity_id), ...] — nur echte Figuren
        selected: vorab angehakte entity_ids; ids ohne Eintrag in entities
            erscheinen ganz oben als eigener Haken "[entity_id]"
        allow_split: zeigt "An Komma aufteilen" (nur Call-Mapping-Dialog)
    """

    def __init__(self, entities, selected=(), parent=None, allow_split=False):
        super().__init__(parent)
        self.setWindowTitle(_t("seq_map_picker_title"))
        self.setMinimumSize(440, 520)
        layout = QVBoxLayout(self)

        self._search = QLineEdit()
        self._search.setPlaceholderText(_t("call_mapping_search_target"))
        self._search.setClearButtonEnabled(True)
        self._search.textChanged.connect(self._apply_filter)
        layout.addWidget(self._search)

        entities = list(entities)
        chosen = set(selected or ())
        # Zugeordnete Figuren ausserhalb der Liste (z.B. ohne call_programs-
        # Zeile) als eigene Haken fuehren: sonst loeschte schon ein OK ohne
        # Aenderung sie stillschweigend. Abhaken bleibt moeglich.
        known = {eid for _label, eid in entities}
        unknown = [(f"[{eid}]", eid) for eid in dict.fromkeys(selected or ())
                   if eid not in known]
        first_checked = None
        self._list = QListWidget()
        self._list.setUpdatesEnabled(False)
        for label, eid in unknown + entities:
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, eid)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if eid in chosen else Qt.Unchecked)
            self._list.addItem(item)
            if first_checked is None and eid in chosen:
                first_checked = item
        self._list.setUpdatesEnabled(True)
        # Erst nach dem Befuellen verbinden: das Vorab-Anhaken loest nichts aus
        self._list.itemChanged.connect(self._on_item_changed)
        layout.addWidget(self._list, 1)
        if first_checked is not None:
            self._list.scrollToItem(first_checked, QAbstractItemView.PositionAtCenter)

        # Die Menge bleibt sichtbar, auch wenn der Suchfilter Haken ausblendet
        self._lbl_selected = QLabel()
        self._lbl_selected.setWordWrap(True)
        self._lbl_selected.setStyleSheet("font-size: 11px; color: #888;")
        layout.addWidget(self._lbl_selected)
        self._update_selected_label()
        self._search.setFocus()

        self._split = False
        btn_row = QHBoxLayout()
        if allow_split:
            # Davids Split-Weg: statt einer Menge den Call-Text beim Speichern
            # am Komma aufteilen (split_sequence_call_at_comma)
            btn_split = QPushButton(_t("call_mapping_split"))
            btn_split.setAutoDefault(False)
            btn_split.clicked.connect(self._on_split)
            btn_row.addWidget(btn_split)
        btn_row.addStretch()
        btn_ok = QPushButton(_t("btn_ok"))
        btn_ok.setDefault(True)
        btn_ok.clicked.connect(self.accept)
        btn_row.addWidget(btn_ok)
        btn_cancel = QPushButton(_t("btn_cancel"))
        btn_cancel.setAutoDefault(False)
        btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(btn_cancel)
        layout.addLayout(btn_row)

    def _items(self):
        return (self._list.item(i) for i in range(self._list.count()))

    def _on_split(self):
        self._split = True
        self.accept()

    def _on_item_changed(self, item):
        """Die Referenz fuehrt eine Figur je Programm (z.B. Plus und Plus (2026))
        -> alle Eintraege derselben entity_id gleich anhaken."""
        eid, state = item.data(Qt.UserRole), item.checkState()
        self._list.blockSignals(True)
        for it in self._items():
            if it.data(Qt.UserRole) == eid and it.checkState() != state:
                it.setCheckState(state)
        self._list.blockSignals(False)
        self._update_selected_label()

    def _update_selected_label(self):
        labels = {}
        for it in self._items():
            if it.checkState() == Qt.Checked:
                labels.setdefault(it.data(Qt.UserRole), it.text())
        self._lbl_selected.setText(
            _t("call_mapping_picker_selected", names=" | ".join(labels.values()))
            if labels else _t("call_mapping_none"))

    def _apply_filter(self, text):
        """Blendet Eintraege ohne Teiltreffer aus (case-insensitive). Haken
        ausgeblendeter Eintraege bleiben stehen und zaehlen weiter."""
        needle = text.strip().lower()
        self._list.setUpdatesEnabled(False)
        for it in self._items():
            it.setHidden(bool(needle) and needle not in it.text().lower())
        self._list.setUpdatesEnabled(True)

    def set_search_text(self, text: str):
        """Setzt das Suchfeld; filtert wie beim Tippen."""
        self._search.setText(text)

    def visible_entity_ids(self) -> list:
        """entity_ids der nach dem Suchfilter sichtbaren Eintraege."""
        return list(dict.fromkeys(
            it.data(Qt.UserRole) for it in self._items() if not it.isHidden()))

    def selected_entity_ids(self) -> list:
        """Angehakte entity_ids in Listen-Reihenfolge (jede Figur einmal)."""
        return list(dict.fromkeys(
            it.data(Qt.UserRole) for it in self._items()
            if it.checkState() == Qt.Checked))

    def split_requested(self) -> bool:
        """True, wenn "An Komma aufteilen" gewaehlt wurde (statt einer Menge)."""
        return self._split


class _NumericItem(QTableWidgetItem):
    """QTableWidgetItem mit numerischer Sortierung (fuer Anzahl-Spalte)."""

    def __lt__(self, other):
        try:
            return (self.data(Qt.DisplayRole) or 0) < (other.data(Qt.DisplayRole) or 0)
        except TypeError:
            return super().__lt__(other)


class CallMappingDialog(QDialog):
    """Dialog zum Verwalten des Call-Text-Mappings.

    Zeigt alle Call-Texte aus den Sequenzen mit Haeufigkeit und aktuellem Mapping.
    Filter-Toggle: Nicht gemappt / Gemappt / Alle.
    Tabelle ist nach allen Spalten sortierbar.
    Auto-Vorschlag: normalisierter Textvergleich (Prefixe/Suffixe abschneiden).
    """

    # Filter-Werte
    _F_UNMAPPED = "unmapped"
    _F_MAPPED   = "mapped"
    _F_ALL      = "all"

    # Rollenwert der Figur-Spalte fuer "An Komma aufteilen"
    _SPLIT = "__SPLIT_COMMA__"

    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self._all_data    = []   # [(call_text, count, eid, cname, prog, mapped_by), ...]
        self._entity_list = []   # [(label, entity_id), ...] — Figuren fuer den Picker
        self._eid_to_label = {}
        self._eid_min_to   = {}  # entity_id -> frueheste Teaching-Order (Rangfolge)
        self._figure_sets  = {}  # call_text -> [entity_id, ...], hoechste zuerst
        self._matcher      = None  # CallMatcher, wird in _prepare_data() gesetzt
        self._alive        = True   # False sobald der Dialog schliesst
        self._pending_texts = []    # noch zu berechnende Vorschlaege (chunked)
        self._pending_pos   = 0
        self.setWindowTitle(_t("call_mapping_title"))
        self.setMinimumSize(900, 600)
        self._build_ui()
        # Matcher-Aufbau + ~11k Zeilen laden dauern 1-3 s. Nicht synchron in
        # __init__, sonst haengt die App, bevor das Fenster ueberhaupt erscheint.
        # Stattdessen: Fenster sofort mit Ladehinweis zeigen, dann laden.
        self._loaded_once = False
        self._label_info.setText(_t("call_mapping_loading"))

    def showEvent(self, event):
        super().showEvent(event)
        # Beim ersten Anzeigen die schwere Arbeit anstossen — nach dem Paint,
        # damit Fenster + Ladehinweis zuerst sichtbar sind.
        if not self._loaded_once:
            self._loaded_once = True
            QTimer.singleShot(0, self._load_deferred)

    def _load_deferred(self):
        """Baut Matcher + Tabelle auf. Die teure Fuzzy-Vorschlags-Schleife (~2 s)
        laeuft NICHT hier, sondern danach im Hintergrund-Worker — das Fenster ist
        so sofort da; noch fehlende Vorschlaege faerben sich nach."""
        import time
        _t0 = time.perf_counter()
        # Zuerst das Fenstergeruest (Filter, Suchleiste, Buttons, leere Tabelle,
        # "Lädt…") malen lassen, BEVOR die ~600 ms Datenaufbau laufen. Sonst
        # bliebe das ganze Fenster bis dahin weiss. singleShot(0) kommt dem ersten
        # Paint zuvor -> hier explizit erzwingen.
        QApplication.processEvents()
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            self._prepare_data()
            _t1 = time.perf_counter()
            self._load_table()
            _t2 = time.perf_counter()
        finally:
            QApplication.restoreOverrideCursor()
        # Sichtbaren Bereich sofort einfaerben, damit er nicht auf die Vorschlaege
        # wartet, und ERZWINGEN, dass Qt die Tabelle jetzt malt — bevor die
        # (CPU-lastige) Vorschlagsberechnung laeuft. Ohne dieses processEvents
        # blieb das Fenster weiss, bis alles fertig war.
        self._color_visible_rows_now()
        QApplication.processEvents()
        _t3 = time.perf_counter()
        print(f"[Call-Mapping] Open: prepare {(_t1-_t0)*1000:.0f}ms, "
              f"load_table {(_t2-_t1)*1000:.0f}ms, sichtbar-faerben {(_t3-_t2)*1000:.0f}ms, "
              f"gesamt {(_t3-_t0)*1000:.0f}ms ({self._table.rowCount()} Zeilen)")
        self._start_progressive_suggestions()

    def _start_progressive_suggestions(self):
        """Berechnet fehlende Vorschlaege in kleinen Haeppchen auf dem Main-Thread
        (statt in einem Thread, der den GIL haelt und das Malen blockiert). Nach
        jedem Haeppchen kehrt die Kontrolle zur Event-Loop zurueck -> Qt malt und
        bleibt bedienbar; die Farben laufen sichtbar von oben durch. Beim zweiten
        Oeffnen (Cache warm) faellt das ganz weg -> instant."""
        self._pending_texts = list(dict.fromkeys(
            r[0] for r in self._all_data
            if r[2] is None and r[0] not in self._suggest_cache))
        self._pending_pos = 0
        if not self._pending_texts:
            return
        self._label_info.setText(_t("call_mapping_computing"))
        QTimer.singleShot(0, self._process_suggest_chunk)

    def _process_suggest_chunk(self):
        """Ein Haeppchen (~20 ms) berechnen, sichtbare Zeilen faerben, dann per
        singleShot das naechste — die Event-Loop malt dazwischen."""
        if not self._alive:
            return
        CHUNK = 100   # ~100 Texte * ~0,2 ms ~ 20 ms pro Tick
        texts = self._pending_texts
        end = min(self._pending_pos + CHUNK, len(texts))
        for i in range(self._pending_pos, end):
            t = texts[i]
            if t not in self._suggest_cache:
                self._suggest_cache[t] = self._matcher.suggest(t)
        self._pending_pos = end
        # Was der Nutzer gerade sieht, sofort einfaerben.
        self._color_visible_rows_now()
        if end < len(texts):
            QTimer.singleShot(0, self._process_suggest_chunk)
        else:
            # Fertig: alle Zeilen faerben (auch die nie sichtbaren, fuer Sortierung/
            # Figur-Spaltensuche) und die Info-Zeile auf die Zaehlung zuruecksetzen.
            self._apply_cached_suggestions()
            self._apply_column_filters()

    def closeEvent(self, event):
        # Laufende Chunk-Verarbeitung stoppen (die Ticks pruefen self._alive).
        self._alive = False
        super().closeEvent(event)

    # ------------------------------------------------------------------ UI --

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(6)

        # Filter-Zeile
        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel(_t("call_mapping_filter_label")))
        self._combo_filter = QComboBox()
        self._combo_filter.addItem(_t("call_mapping_f_unmapped"), self._F_UNMAPPED)
        self._combo_filter.addItem(_t("call_mapping_f_mapped"),   self._F_MAPPED)
        self._combo_filter.addItem(_t("call_mapping_f_all"),      self._F_ALL)
        self._combo_filter.currentIndexChanged.connect(self._load_table)
        filter_row.addWidget(self._combo_filter)
        filter_row.addStretch()
        self._label_info = QLabel()
        self._label_info.setStyleSheet("font-size: 11px; color: #888;")
        filter_row.addWidget(self._label_info)
        layout.addLayout(filter_row)

        hint = QLabel(_t("call_mapping_hint"))
        hint.setStyleSheet("font-size: 11px; color: #888;")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        # Tabelle
        self._table = QTableWidget()
        self._table.setColumnCount(4)
        self._table.setHorizontalHeaderLabels([
            _t("call_mapping_col_raw"),
            _t("call_mapping_col_count"),
            _t("call_mapping_col_target"),
            _t("call_mapping_col_source"),
        ])
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self._table.verticalHeader().setVisible(False)
        self._table.setSortingEnabled(True)
        # Keine Zelle direkt editierbar — einmal hier statt setFlags je Figur-Item
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        # Figur-Spalte: Doppelklick (oder F2) oeffnet den Mehrfach-Picker
        self._table.doubleClicked.connect(self._open_figures_picker)
        f2 = QShortcut(QKeySequence(Qt.Key_F2), self._table)
        f2.setContext(Qt.WidgetShortcut)
        f2.activated.connect(
            lambda: self._open_figures_picker(self._table.currentIndex()))

        # Rechtsklick auf die Call-Text-Spalte -> "Beispiel zeigen" (Sequenzen,
        # die diesen Text nutzen, in einem eigenen Betrachter durchblaettern).
        self._table.setContextMenuPolicy(Qt.CustomContextMenu)
        self._table.customContextMenuRequested.connect(self._on_table_context_menu)
        self._example_win = None   # lazy erzeugter Beispiel-Betrachter
        # Beim Scrollen die neu sichtbaren Zeilen sofort einfaerben (waehrend der
        # Worker noch rechnet). Nach dem Worker ein guenstiger No-Op.
        self._table.verticalScrollBar().valueChanged.connect(
            lambda *_: self._color_visible_rows_now())

        # --- Per-Spalten-Suchzeile (Filter je Textspalte) ---
        # Substring-Filter, case-insensitive; Breiten an die Spalten gekoppelt,
        # damit die Felder unter ihren Ueberschriften sitzen. Anzahl-Spalte ohne
        # Filter (numerisch). Zweck u.a.: Figuren nach Muster wie "& Spread" finden.
        self._col_filters = []
        search_bar = QHBoxLayout()
        search_bar.setSpacing(0)
        search_bar.setContentsMargins(self._table.frameWidth(), 0, 0, 0)
        _ph = {0: _t("call_mapping_search_raw"),
               2: _t("call_mapping_search_target"),
               3: _t("call_mapping_search_source")}
        for col in range(4):
            edit = QLineEdit()
            if col in _ph:
                edit.setPlaceholderText(_ph[col])
                edit.setClearButtonEnabled(True)
                edit.textChanged.connect(self._apply_column_filters)
            else:
                edit.setEnabled(False)   # Anzahl: kein Textfilter
            self._col_filters.append(edit)
            search_bar.addWidget(edit)
        layout.addLayout(search_bar)
        layout.addWidget(self._table)

        # Suchfeld-Breiten an die Spaltenbreiten koppeln
        self._table.horizontalHeader().sectionResized.connect(
            lambda *_: self._sync_filter_widths())
        QTimer.singleShot(0, self._sync_filter_widths)

        # Buttons
        btn_layout = QHBoxLayout()
        self._btn_confirm_sel = QPushButton(_t("call_mapping_confirm_selected"))
        self._btn_confirm_sel.clicked.connect(self._on_confirm_selected)
        btn_layout.addWidget(self._btn_confirm_sel)
        btn_layout.addStretch()
        self._btn_save = QPushButton(_t("call_mapping_save"))
        self._btn_save.setDefault(True)
        self._btn_save.clicked.connect(self._on_save)
        btn_layout.addWidget(self._btn_save)
        btn_cancel = QPushButton(_t("btn_cancel"))
        btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(btn_cancel)
        layout.addLayout(btn_layout)

    # ---------------------------------------------------------- Daten laden --

    def _prepare_data(self):
        """Laedt alle Daten einmalig aus der DB (kein Rendering)."""
        self.db.ensure_filler_words_entity()
        self._all_data = self.db.get_all_call_texts_with_mapping()
        # BL-210.4: alle Figuren-Mengen in EINER Abfrage, keine DB-Abfrage je Zeile
        self._figure_sets = self.db.get_all_call_text_figures()

        to_calls = self.db.get_teaching_order_calls()

        # Picker-Liste nur mit echten Figuren: "keine Zuordnung" = kein Haken,
        # "An Komma aufteilen" ist ein Knopf im Picker, Programm-Separatoren
        # ("-- Basic 1 --") sind keine Figuren.
        self._entity_list = []
        self._eid_to_label = {}
        self._eid_min_to = {}
        for eid, cname, to, prog in to_calls:
            label = f"{cname}  [{prog}]" if prog else cname
            self._eid_to_label[eid] = label
            self._eid_min_to.setdefault(eid, to)   # to_calls aufsteigend sortiert
            if not cname.startswith("--"):
                self._entity_list.append((label, eid))

        # CallMatcher: Drei-Stufen-Matching (exakt → Token-Overlap → SequenceMatcher)
        self._matcher = _CallMatcher(to_calls)
        # Suggest-Cache: der Fuzzy-Vorschlag je Call-Text ist teuer (~2 s ueber
        # alle ~10k ungemappten). Der Cache wird AM HAUPTFENSTER gehalten, damit
        # ein erneutes Oeffnen des Dialogs in derselben Sitzung instant ist. Er
        # wird verworfen, wenn sich die Kanonisch-Call-Liste aendert (Signatur).
        # Key = call_text -> (score, entity_id).
        sig = hash(tuple((c[0], c[1]) for c in to_calls))
        parent = self.parent()
        cache = getattr(parent, "_call_suggest_cache", None) if parent else None
        if (cache is None
                or getattr(parent, "_call_suggest_sig", None) != sig):
            cache = {}
            if parent is not None:
                parent._call_suggest_cache = cache
                parent._call_suggest_sig = sig
        self._suggest_cache = cache

    def _load_table(self):
        """Befuellt die Tabelle gemaess aktivem Filter — alle Zeilen auf einmal."""
        fval = self._combo_filter.currentData()
        if fval == self._F_UNMAPPED:
            rows = [r for r in self._all_data if r[2] is None]
        elif fval == self._F_MAPPED:
            rows = [r for r in self._all_data if r[2] is not None]
        else:
            rows = self._all_data

        self._label_info.setText(
            _t("call_mapping_info", count=len(rows))
        )

        self._table.setSortingEnabled(False)
        self._table.setUpdatesEnabled(False)
        self._table.setRowCount(0)
        self._table.setRowCount(len(rows))
        none_label = _t("call_mapping_none")   # einmal statt je Zeile

        for i, (call_text, count, entity_id, cname, prog, mapped_by) in enumerate(rows):

            # Col 0: Call-Text — Hintergrundfarbe je nach Match-Qualitaet
            item0 = QTableWidgetItem(call_text)
            item0.setData(Qt.UserRole, call_text)
            item0.setFlags(item0.flags() & ~Qt.ItemIsEditable)
            self._table.setItem(i, 0, item0)

            # Col 1: Anzahl (numerisch sortierbar)
            item1 = _NumericItem()
            item1.setData(Qt.DisplayRole, count)
            item1.setTextAlignment(Qt.AlignCenter)
            item1.setFlags(item1.flags() & ~Qt.ItemIsEditable)
            self._table.setItem(i, 1, item1)

            # Col 2: Figuren-Menge (Doppelklick oeffnet den Picker). Rollenwert
            # und Anzeige fuer den Normalfall (eine Figur) direkt, ohne Helfer-
            # Aufrufe je Zeile — ~13k Zeilen auf dem Main-Thread.
            if entity_id:
                # Bereits gemappt — gruen
                figures = self._figure_sets.get(call_text)
                if figures and len(figures) > 1:
                    stored = list(figures)
                    label = self._figures_text(figures)
                else:
                    stored = entity_id
                    label = self._eid_to_label.get(entity_id) or f"[{entity_id}]"
                item0.setBackground(QColor("#d4edda"))
            else:
                # Auto-Vorschlag via CallMatcher — aus dem Cache. Ist er noch nicht
                # berechnet (erster Aufbau, Worker laeuft noch), bleibt die Zeile
                # neutral-hellgrau und wird von _apply_cached_suggestions nachgefaerbt.
                cached = self._suggest_cache.get(call_text)
                if cached is not None:
                    score, suggested = cached
                    stored = suggested
                    label = self._eid_to_label.get(suggested, none_label)
                    item0.setBackground(self._bg_for_score(score))
                else:
                    stored = None
                    label = none_label
                    # Helles Grau (nicht Theme-Default): der erzwungene dunkle Text
                    # muss auch im Dark-Theme lesbar bleiben.
                    item0.setBackground(QColor("#e9ecef"))
            # Immer dunkle Schrift auf den hellen Pastell-Hintergruenden — sonst
            # ist der Call-Text im Dark-Theme (heller Standard-Text) unlesbar.
            # Gilt themeunabhaengig, weil die Hintergruende fix hell sind.
            item0.setForeground(QColor("#212529"))
            item2 = QTableWidgetItem(label)
            item2.setData(Qt.UserRole,     stored)   # aktuell (Picker aktualisiert)
            item2.setData(Qt.UserRole + 1, stored)   # original (fuer Change-Detection)
            self._table.setItem(i, 2, item2)

            # Col 3: Quelle
            source = mapped_by if mapped_by else "—"
            item3 = QTableWidgetItem(source)
            item3.setFlags(item3.flags() & ~Qt.ItemIsEditable)
            self._table.setItem(i, 3, item3)

        self._table.setUpdatesEnabled(True)
        self._table.setSortingEnabled(True)
        # Aktive Spalten-Suchfilter nach dem Neuladen erneut anwenden
        self._apply_column_filters()

    @staticmethod
    def _bg_for_score(score):
        """Zeilen-Hintergrund nach Vorschlags-Qualitaet (fix helle Farben)."""
        if score >= _CallMatcher.CONFIDENT:
            return QColor("#d4edda")   # gruen: sicherer Vorschlag
        if score >= _CallMatcher.UNCERTAIN:
            return QColor("#fff3cd")   # gelb: unsicherer Vorschlag
        return QColor("#f8d7da")       # rot: kein Vorschlag

    def _apply_row_suggestion(self, row):
        """Faerbt EINE Zeile anhand des Caches ein und setzt den Vorschlag.
        Zeilen, die beim Laden schon gemappt waren, bleiben unberuehrt."""
        item0 = self._table.item(row, 0)
        item2 = self._table.item(row, 2)
        if not item0 or not item2:
            return
        if self._figures(item2, Qt.UserRole + 1):
            return   # war beim Laden bereits gemappt
        cached = self._suggest_cache.get(item0.data(Qt.UserRole))
        if cached is None:
            return
        score, suggested = cached
        if not self._figures(item2, Qt.UserRole):
            # Nutzer hat noch nichts gewaehlt -> Vorschlag uebernehmen. Original
            # (UserRole+1) = Vorschlag: so gilt der Auto-Vorschlag wie bisher
            # NICHT als Aenderung beim "Speichern" (nur "Bestaetigen" schreibt ihn).
            figures = [suggested] if suggested else []
            item2.setData(Qt.UserRole + 1, self._stored(figures))
            self._show_figures(item2, figures)
            item0.setBackground(self._bg_for_score(score))
        else:
            # Nutzer hat schon selbst gewaehlt -> Auswahl behalten, gruen faerben.
            item0.setBackground(QColor("#d4edda"))

    def _apply_cached_suggestions(self):
        """Faerbt alle noch neutralen (Worker-)Zeilen anhand des Caches nach."""
        self._table.setUpdatesEnabled(False)
        for row in range(self._table.rowCount()):
            self._apply_row_suggestion(row)
        self._table.setUpdatesEnabled(True)

    def _color_visible_rows_now(self):
        """Faerbt die aktuell SICHTBAREN Zeilen sofort ein (synchron, ~40 Zeilen
        = wenige ms), damit der sichtbare Bereich beim Oeffnen nicht erst auf den
        Hintergrund-Worker warten muss. Der Rest wird vom Worker nachgezogen."""
        if getattr(self, "_matcher", None) is None:
            return   # noch nicht vorbereitet (frueher Scroll-Event)
        tbl = self._table
        n = tbl.rowCount()
        if n == 0:
            return
        h = tbl.viewport().height()
        top = tbl.rowAt(0)
        if top < 0:
            top = 0
        bottom = tbl.rowAt(max(0, h - 1))
        if bottom < 0:
            bottom = n - 1
        rows = range(max(0, top), min(n, bottom + 2))
        # Fehlende Vorschlaege dieser Zeilen berechnen (in den geteilten Cache) ...
        for row in rows:
            it0 = tbl.item(row, 0)
            it2 = tbl.item(row, 2)
            if it0 and it2 and not self._figures(it2, Qt.UserRole + 1):
                ct = it0.data(Qt.UserRole)
                if ct not in self._suggest_cache:
                    self._suggest_cache[ct] = self._matcher.suggest(ct)
        # ... und anwenden.
        tbl.setUpdatesEnabled(False)
        for row in rows:
            self._apply_row_suggestion(row)
        tbl.setUpdatesEnabled(True)

    def _sync_filter_widths(self):
        """Koppelt die Breite der Suchfelder an die jeweiligen Spaltenbreiten."""
        header = self._table.horizontalHeader()
        for col, edit in enumerate(self._col_filters):
            edit.setFixedWidth(max(0, header.sectionSize(col)))

    def _apply_column_filters(self):
        """Blendet Zeilen aus, die nicht ALLE aktiven Spalten-Suchbegriffe
        enthalten (Substring, case-insensitive)."""
        active = []
        for col, edit in enumerate(self._col_filters):
            if edit.isEnabled():
                txt = edit.text().strip().lower()
                if txt:
                    active.append((col, txt))
        visible = 0
        for row in range(self._table.rowCount()):
            show = True
            for col, txt in active:
                item = self._table.item(row, col)
                if txt not in (item.text().lower() if item else ""):
                    show = False
                    break
            self._table.setRowHidden(row, not show)
            if show:
                visible += 1
        # Info-Zeile: bei aktivem Suchfilter sichtbare Anzahl zeigen
        if active:
            self._label_info.setText(
                _t("call_mapping_info_filtered",
                   visible=visible, total=self._table.rowCount()))
        else:
            self._label_info.setText(
                _t("call_mapping_info", count=self._table.rowCount()))

    # ---------------------------------------------------- Figuren-Mengen --
    # Rollen der Figur-Spalte (Spalte 2):
    #   Qt.UserRole     aktuelle Menge (Picker schreibt)
    #   Qt.UserRole + 1 Menge beim Laden bzw. Auto-Vorschlag (Change-Detection)
    # Rollenwert: None fuer die leere Menge; ein String fuer genau eine Figur
    # (Normalfall, wie vor BL-210 — billiger als eine Liste je Zeile) und fuer
    # den Split-Marker _SPLIT; eine Liste [entity_id, ...] (hoechste zuerst)
    # erst ab zwei Figuren. Gelesen wird immer ueber _figures(): PySide6 gibt
    # Sequenzen als Liste zurueck, und eine leere Liste ist nicht None.

    @staticmethod
    def _stored(figures):
        """Menge -> Rollenwert."""
        if not figures:
            return None
        if len(figures) == 1:
            return figures[0]   # Einzel-Figur oder Split-Marker
        return list(figures)

    @staticmethod
    def _figures(item, role) -> tuple:
        """Rollenwert -> Menge als Tupel: () = keine Zuordnung, (_SPLIT,) = Split."""
        value = item.data(role)
        if not value:
            return ()
        if isinstance(value, str):
            return (value,)
        return tuple(value)

    def _figures_text(self, figures) -> str:
        """Anzeige: alle Figuren mit Trenner, ab zwei Figuren vorn "+n"."""
        if not figures:
            return _t("call_mapping_none")
        if len(figures) == 1:   # Normalfall ohne join (_load_table: ~13k Zeilen)
            eid = figures[0]
            if eid == self._SPLIT:
                return _t("call_mapping_split")
            return self._eid_to_label.get(eid) or f"[{eid}]"
        labels = " | ".join(self._eid_to_label.get(e) or f"[{e}]" for e in figures)
        return f"+{len(figures) - 1}  {labels}"

    def _rank_figures(self, entity_ids) -> list:
        """Hoechste Figur zuerst, wie die DB: frueheste Teaching-Order absteigend,
        Figur ohne Programm zuerst, Gleichstand entity_id aufsteigend."""
        def key(eid):
            to = self._eid_min_to.get(eid)
            return (0, 0.0, eid) if to is None else (1, -to, eid)
        return sorted(dict.fromkeys(entity_ids), key=key)

    def _show_figures(self, item2, figures):
        """Setzt aktuelle Menge und Anzeige einer Figur-Zelle. Die Anzeige
        zuletzt: bei aktiver Sortierung kann die Zeile danach wandern."""
        item2.setData(Qt.UserRole, self._stored(figures))
        item2.setData(Qt.DisplayRole, self._figures_text(figures))

    def _open_figures_picker(self, index):
        """Doppelklick/F2 auf die Figur-Spalte: Mehrfach-Picker (BL-210.4)."""
        if not index.isValid() or index.column() != 2:
            return
        item0 = self._table.item(index.row(), 0)
        item2 = self._table.item(index.row(), 2)
        if item0 is None or item2 is None:
            return
        current = self._figures(item2, Qt.UserRole)
        if current == (self._SPLIT,):
            current = ()
        dlg = CallFiguresPickerDialog(self._entity_list, selected=current,
                                      parent=self, allow_split=True)
        dlg.setWindowTitle(_t("seq_map_picker_text", text=item0.data(Qt.UserRole)))
        if dlg.exec() != QDialog.Accepted:
            return
        # Ueber das gemerkte Item schreiben, nicht ueber den Zeilenindex: waehrend
        # der Picker offen war, kann die Vorschlags-Einfaerbung umsortiert haben.
        if dlg.split_requested():
            self._show_figures(item2, [self._SPLIT])
        else:
            self._show_figures(item2, self._rank_figures(dlg.selected_entity_ids()))

    # ----------------------------------------------------- Beispiel zeigen --

    def _on_table_context_menu(self, pos):
        """Rechtsklick-Menue auf der Call-Text-Spalte: "Beispiel zeigen"."""
        index = self._table.indexAt(pos)
        if not index.isValid() or index.column() != 0:
            return
        item0 = self._table.item(index.row(), 0)
        if item0 is None:
            return
        call_text = item0.data(Qt.UserRole)
        if not call_text:
            return
        menu = QMenu(self)
        act = menu.addAction(_t("call_mapping_show_example"))
        chosen = menu.exec(self._table.viewport().mapToGlobal(pos))
        if chosen is act:
            self._show_call_examples(call_text)

    def _show_call_examples(self, call_text: str):
        """Oeffnet einen nicht-modalen Betrachter mit allen Sequenzen, die diesen
        Call-Text nutzen — zum Durchblaettern, der Treffer ist hervorgehoben.

        Bewusst ein EIGENES Fenster (eigene SequenceViewWidget-Instanz) statt des
        Docks im Hauptfenster: der Mapping-Dialog ist modal, der Dock waere
        gesperrt. Als Kind des modalen Dialogs bleibt dieses Fenster bedienbar.
        """
        seq_ids = self.db.get_sequence_ids_with_call_text(call_text)
        if not seq_ids:
            QMessageBox.information(
                self, _t("call_mapping_show_example"),
                _t("call_mapping_example_none", text=call_text))
            return

        win = self._example_win
        if win is None:
            win = QDialog(self)
            win.setModal(False)
            win.setMinimumSize(420, 480)
            vbox = QVBoxLayout(win)
            vbox.setContentsMargins(8, 8, 8, 8)
            lbl = QLabel()
            lbl.setWordWrap(True)
            lbl.setStyleSheet("font-weight: bold;")
            vbox.addWidget(lbl)
            skin_mgr = getattr(self.parent(), "skin_mgr", None)
            viewer = SequenceViewWidget(self.db, skin_mgr=skin_mgr)
            # Reiner Betrachter: Bearbeiten/Loeschen/Notizen ausblenden.
            for btn in ("_btn_edit", "_btn_delete", "_btn_to_notes"):
                b = getattr(viewer, btn, None)
                if b is not None:
                    b.hide()
            vbox.addWidget(viewer, 1)
            win._lbl = lbl
            win._viewer = viewer
            self._example_win = win

        win.setWindowTitle(_t("call_mapping_example_title", text=call_text))
        win._lbl.setText(_t("call_mapping_example_header",
                            text=call_text, count=len(seq_ids)))
        win._viewer._highlight_text = call_text
        win._viewer.set_sequence(self.db, seq_ids, 0)
        win.show()
        win.raise_()
        win.activateWindow()

    # ------------------------------------------------------------ Speichern --

    def _on_confirm_selected(self):
        """Bestaetigt die Auto-Vorschlaege fuer alle markierten Zeilen.

        Geeignet, wenn der Filter bereits korrekt vorschlaegt (gruene/gelbe Zeilen):
        Zeilen selektieren (Ctrl/Shift+Click), Button — die Vorschlaege werden
        direkt in die DB geschrieben und die Zeile als bestaetigt markiert.
        """
        import time
        _t_start = time.perf_counter()

        rows = sorted({idx.row() for idx in self._table.selectedIndexes()})
        # (raw_text, [entity_id, ...]) je bestaetigbarer Zeile einsammeln.
        pairs = []
        confirmed_texts = {}   # call_text -> Figuren-Menge (hoechste zuerst)
        confirmed_rows = []    # View-Zeilenindizes der bestaetigten Zeilen
        for row in rows:
            item0 = self._table.item(row, 0)
            item2 = self._table.item(row, 2)
            if not item0 or not item2:
                continue
            raw_text = item0.data(Qt.UserRole)
            current  = self._figures(item2, Qt.UserRole)
            # Nur Zeilen mit echter Ziel-Figur bestaetigen (im Normalfall der
            # Einzel-Vorschlag). Split-Marker und "keine Zuordnung" ueberspringen.
            if not current or current == (self._SPLIT,):
                continue
            pairs.append((raw_text, list(current)))
            confirmed_texts[raw_text] = list(current)
            confirmed_rows.append(row)
        _t_collect = time.perf_counter()

        confirmed = 0
        if pairs:
            # EIN Batch-Commit statt eines Commits je Zeile (frueher bis ~0,5 s).
            confirmed = self.db.set_call_text_figures_bulk(pairs, mapped_by="manual")
        _t_write = time.perf_counter()

        if confirmed > 0:
            # KEIN Voll-Requery + Voll-Reload mehr (frueher ~3 s: die suggest()-
            # Schleife lief ueber alle ~10k ungemappten Texte neu). Stattdessen
            # das In-Memory-Modell fuer die bestaetigten Texte aktualisieren ...
            new_all = []
            for r in self._all_data:
                figures = confirmed_texts.get(r[0])
                if figures is not None:
                    # (call_text, count, entity_id, cname, prog, mapped_by)
                    # entity_id = hoechste Figur (wie call_text_mappings).
                    # cname/prog werden in _load_table nicht gelesen (Label kommt
                    # aus _eid_to_label) -> None ist unschaedlich.
                    new_all.append((r[0], r[1], figures[0], None, None, "manual"))
                else:
                    new_all.append(r)
            self._all_data = new_all
            self._figure_sets.update(confirmed_texts)

            if self._combo_filter.currentData() == self._F_UNMAPPED:
                # Im "Nicht gemappt"-Filter fallen die bestaetigten Zeilen nur weg
                # -> gezielt entfernen statt die ganze (~10k Zeilen) Tabelle neu zu
                # bauen. Von hinten nach vorne, damit die Indizes stabil bleiben.
                self._table.setSortingEnabled(False)
                self._table.setUpdatesEnabled(False)
                for row in sorted(confirmed_rows, reverse=True):
                    self._table.removeRow(row)
                self._table.setUpdatesEnabled(True)
                self._table.setSortingEnabled(True)
                self._apply_column_filters()   # Info-Zeile + aktive Suchfilter
            else:
                # "Gemappt"/"Alle": bestaetigte Zeilen bleiben sichtbar (Status
                # aendert sich) -> voller, aber dank Suggest-Cache billiger Aufbau.
                self._load_table()
        _t_reload = time.perf_counter()

        print(f"[Call-Mapping] Confirm selected: {confirmed} Zeilen | "
              f"sammeln {(_t_collect-_t_start)*1000:.0f}ms, "
              f"schreiben {(_t_write-_t_collect)*1000:.0f}ms, "
              f"reload {(_t_reload-_t_write)*1000:.0f}ms, "
              f"gesamt {(_t_reload-_t_start)*1000:.0f}ms")

        if confirmed == 0:
            QMessageBox.information(
                self, _t("call_mapping_title"),
                _t("call_mapping_confirm_none_selected")
            )
        else:
            QMessageBox.information(
                self, _t("call_mapping_title"),
                _t("call_mapping_confirmed_n", count=confirmed)
            )

    def _on_save(self):
        """Speichert geaenderte Zuordnungen; fuehrt Splits durch; loescht entfernte."""
        saved = 0
        deleted = 0
        split_seqs = 0
        split_occ = 0

        for row in range(self._table.rowCount()):
            item0 = self._table.item(row, 0)
            item2 = self._table.item(row, 2)
            if not item0 or not item2:
                continue

            raw_text = item0.data(Qt.UserRole)
            current  = self._figures(item2, Qt.UserRole)
            original = self._figures(item2, Qt.UserRole + 1)

            if set(current) == set(original):
                continue  # unveraendert (Menge, Reihenfolge egal)

            if current == (self._SPLIT,):
                s, o = self.db.split_sequence_call_at_comma(raw_text)
                split_seqs += s
                split_occ  += o
            elif current:
                self.db.set_call_text_figures(raw_text, list(current), mapped_by="manual")
                saved += 1
            else:
                # Mapping entfernen (User hat auf "keine Zuordnung" geaendert)
                self.db.delete_call_text_mapping(raw_text)
                deleted += 1

        print(f"[Call-Mapping] {saved} gespeichert, {deleted} entfernt, "
              f"{split_occ} Splits in {split_seqs} Sequenzen")

        parts = []
        if saved:
            parts.append(_t("call_mapping_saved_n", count=saved))
        if deleted:
            parts.append(_t("call_mapping_deleted", count=deleted))
        if split_seqs:
            parts.append(_t("call_mapping_split_done", seqs=split_seqs, occ=split_occ))
        QMessageBox.information(
            self, _t("call_mapping_title"),
            "\n".join(parts) if parts else _t("call_mapping_nothing")
        )
        self.accept()
