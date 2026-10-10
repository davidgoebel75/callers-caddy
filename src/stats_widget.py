"""Stats-Widget (BL-019): Abspielstatistiken mit TOP / FLOP / Nie-gespielt + Histogramm."""

from __future__ import annotations

import math
from datetime import datetime, timedelta

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QListWidget, QListWidgetItem, QFrame, QSizePolicy, QGroupBox, QMenu,
    QAbstractItemView,
)
from PySide6.QtCore import Qt, QPoint, QRect
from PySide6.QtGui import QPainter, QColor, QPen, QFont
from PySide6.QtWidgets import QToolTip

from i18n import _t


def add_song_rating_actions(menu, db, song_id, refresh_callback=None):
    """Fuegt vier Bewertungs-Aktionen (Quality/ERR jeweils ±1) zu einem QMenu hinzu.

    Jede Aktion zeigt den aktuellen und den neuen Wert in der Form '[5>6]'.
    Am Wertebereichs-Rand (Quality 0..10, ERR 0..4) wird die jeweilige Aktion
    deaktiviert. Nach jeder Aenderung wird `refresh_callback()` gerufen, falls
    angegeben — typisch die `refresh()`-Methode der aufrufenden Liste.
    """
    song = db.get_by_id(song_id)
    if song is None:
        return
    menu.addSeparator()

    def _make(field, delta, lo, hi, key):
        cur = getattr(song, field) or 0
        new = max(lo, min(hi, cur + delta))
        act = menu.addAction(_t(key, old=cur, new=new))
        if new == cur:
            act.setEnabled(False)
            return
        def _apply():
            db.update_song_simple_field(song_id, field, new)
            if refresh_callback:
                refresh_callback()
        act.triggered.connect(_apply)

    _make("quality", +1, 0, 10, "ctx_quality_up")
    _make("quality", -1, 0, 10, "ctx_quality_down")
    _make("err",     +1, 0, 4,  "ctx_err_up")
    _make("err",     -1, 0, 4,  "ctx_err_down")


# ---- Zeitraum-Definitionen: (i18n-Key, Tage oder None=Alle) ----
_PERIODS = [
    ("stats_period_all", None),
    ("stats_period_5y",  5 * 365),
    ("stats_period_1y",  365),
    ("stats_period_3m",  90),
    ("stats_period_1m",  30),
]

# ---- Typ-Definitionen: (i18n-Key, SQL-Filterwert) ----
_TYPES = [
    ("stats_type_all",     None),
    ("stats_type_pattern", "pattern"),
    ("stats_type_singing", "singing"),
    ("stats_type_other",   "other"),
]

_TOOLTIP_SONGS = 5   # max. Songs im Balken-Tooltip


def _log_bin_edges_from_one(max_plays: int, n_bins: int = 9) -> list[int]:
    """Logarithmisch verteilte Bin-Grenzen für Play-Counts 1..max_plays.

    Ergibt n_bins Bins: [1, e1, e2, ..., max_plays+1].
    Bin 0 (count==0) wird separat vor dem Aufruf behandelt.
    """
    if max_plays < 1:
        return [1, 2]
    if max_plays < n_bins:
        return list(range(1, max_plays + 2))

    edges = [1]
    log_max = math.log(max_plays + 1)   # log(max+1), damit max selbst in letztes Bin fällt
    for i in range(1, n_bins):
        e = int(round(math.exp(log_max * i / n_bins)))
        edges.append(max(e, edges[-1] + 1))
    edges.append(max_plays + 1)
    return edges


def _heat_color(i: int, n: int) -> QColor:
    """Interpoliert Balkenfarbe von Blau (kalt, i=0) nach Orange-Rot (heiß, i=n-1)."""
    t = i / max(n - 1, 1)
    r = int(55  + t * (220 - 55))
    g = int(130 + t * (55  - 130))
    b = int(190 + t * (15  - 190))
    return QColor(r, g, b)


class _HistogramWidget(QWidget):
    """Balkendiagramm: Songs nach Play-Count in logarithmisch verteilten Bins.

    Jeder Balken zeigt beim Mouse-Over einen Tooltip mit bis zu 5 Beispiel-Songs.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        # Jeder Eintrag: (label, count, [display_str, ...])
        self._bins: list[tuple[str, int, list[str]]] = []
        self._max_bar = 1
        # Pixel-Rects der Balken — werden in paintEvent berechnet
        self._bar_rects: list[QRect] = []
        self.setMinimumHeight(170)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMouseTracking(True)

    def set_data(self, songs: list[tuple[int, str]]):
        """Befüllt das Histogramm.

        Args:
            songs: Liste von (play_count, "Anzeige-String") für alle Songs.
        """
        self._bins = []
        self._bar_rects = []
        self._max_bar = 1

        if not songs:
            self.update()
            return

        max_plays = max(c for c, _ in songs)

        # --- Bin 0: immer exakt count == 0 ---
        never = [t for c, t in songs if c == 0]
        self._bins.append(("0", len(never), never[:_TOOLTIP_SONGS]))

        if max_plays == 0:
            self._max_bar = len(never)
            self.update()
            return

        # --- Bins 1..9: logarithmisch für count >= 1 ---
        played = [(c, t) for c, t in songs if c > 0]
        edges = _log_bin_edges_from_one(max_plays, n_bins=9)
        n = len(edges) - 1
        buckets: list[list[str]] = [[] for _ in range(n)]

        for count, display in played:
            lo, hi = 0, n - 1
            while lo < hi:
                mid = (lo + hi + 1) // 2
                if edges[mid] <= count:
                    lo = mid
                else:
                    hi = mid - 1
            buckets[lo].append(display)

        for i in range(n):
            lo_val = edges[i]
            hi_val = edges[i + 1] - 1
            label = f"{lo_val}–{hi_val}" if lo_val != hi_val else str(lo_val)
            self._bins.append((label, len(buckets[i]), buckets[i][:_TOOLTIP_SONGS]))

        self._max_bar = max((b[1] for b in self._bins), default=1)
        self.update()

    # ------------------------------------------------------------------
    # Zeichnen
    # ------------------------------------------------------------------

    def _layout(self):
        """Gibt (ml, mb, mt, mr, chart_w, chart_h, bar_w, gap) zurück."""
        ml, mb, mt, mr = 44, 38, 12, 8
        chart_w = self.width() - ml - mr
        chart_h = self.height() - mt - mb
        n = max(len(self._bins), 1)
        gap = max(2, chart_w // (n * 8))
        bar_w = max(4, (chart_w - gap * (n + 1)) // n)
        return ml, mb, mt, mr, chart_w, chart_h, bar_w, gap

    def paintEvent(self, event):
        if not self._bins:
            p = QPainter(self)
            p.setPen(self.palette().color(self.foregroundRole()))
            p.drawText(self.rect(), Qt.AlignCenter, _t("stats_no_data"))
            p.end()
            return

        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        w, h = self.width(), self.height()
        ml, mb, mt, mr, chart_w, chart_h, bar_w, gap = self._layout()

        fg = self.palette().color(self.foregroundRole())
        ax_color  = QColor(fg.red(), fg.green(), fg.blue(), 120)
        val_color = QColor(fg.red(), fg.green(), fg.blue(), 200)
        n_bins    = len(self._bins)

        # Achsen
        p.setPen(QPen(ax_color, 1))
        p.drawLine(ml, mt, ml, mt + chart_h)
        p.drawLine(ml, mt + chart_h, w - mr, mt + chart_h)

        small_font = QFont()
        small_font.setPointSize(7)
        p.setFont(small_font)

        max_b = max(self._max_bar, 1)
        self._bar_rects = []

        for i, (label, count, _) in enumerate(self._bins):
            x = ml + gap + i * (bar_w + gap)
            bar_h = int(chart_h * count / max_b)
            y = mt + chart_h - bar_h

            # Balken — Farbgradient Blau→Orange/Rot
            p.setBrush(_heat_color(i, n_bins))
            p.setPen(Qt.NoPen)
            p.drawRect(x, y, bar_w, bar_h)
            self._bar_rects.append(QRect(x, y, bar_w, bar_h))

            # X-Label
            p.setPen(ax_color)
            p.drawText(
                x - gap, mt + chart_h + 4, bar_w + gap * 2, 20,
                Qt.AlignHCenter | Qt.AlignTop, label,
            )

            # Wert oben
            if count > 0:
                p.setPen(val_color)
                p.drawText(x, y - 14, bar_w, 14,
                           Qt.AlignHCenter | Qt.AlignBottom, str(count))

        # Y-Achse: Beschriftung
        p.setPen(ax_color)
        p.drawText(0, mt, ml - 3, 14, Qt.AlignRight | Qt.AlignTop, str(max_b))
        p.drawText(0, mt + chart_h - 7, ml - 3, 14, Qt.AlignRight | Qt.AlignTop, "0")

        # X-Achsen-Titel
        p.drawText(0, h - 14, w, 14,
                   Qt.AlignHCenter | Qt.AlignTop, _t("stats_histogram_xlabel"))
        p.end()

    # ------------------------------------------------------------------
    # Tooltip auf Balken
    # ------------------------------------------------------------------

    def mouseMoveEvent(self, event):
        pos = event.position().toPoint()
        for i, rect in enumerate(self._bar_rects):
            # Hitbox etwas nach oben erweitern (trifft auch leere Balken)
            ml, mb, mt, mr, _, chart_h, bar_w, gap = self._layout()
            hit = QRect(rect.x(), mt, bar_w, chart_h)
            if hit.contains(pos):
                label, count, sample = self._bins[i]
                lines = [f"{label}  →  {count} {_t('stats_songs_count')}"]
                if sample:
                    lines.append("─" * 28)
                    lines.extend(sample)
                    if count > _TOOLTIP_SONGS:
                        lines.append(f"… +{count - _TOOLTIP_SONGS} {_t('stats_more')}")
                QToolTip.showText(
                    self.mapToGlobal(pos), "\n".join(lines), self
                )
                return
        QToolTip.hideText()

    def leaveEvent(self, event):
        QToolTip.hideText()


class StatsWidget(QWidget):
    """Abspielstatistiken: TOP / FLOP / Nie gespielt + Histogramm."""

    on_navigate_song   = None   # fn(song_id)     — wird von main.py gesetzt
    on_add_to_playlist = None   # fn(song_id)     — Song zur Playlist hinzufügen
    on_add_to_notes    = None   # fn(song_title)  — [load_song]-Shortcode in Notizen
    on_song_rating_changed = None  # fn(song_id)  — Quality/ERR via Kontextmenue geaendert

    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self._location_ids: list[int | None] = []
        self._build_ui()
        self._populate_location_combo()
        self._refresh()

    # ------------------------------------------------------------------
    # UI-Aufbau
    # ------------------------------------------------------------------

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        # --- Filter-Zeile ---
        filter_row = QHBoxLayout()
        filter_row.setSpacing(8)

        filter_row.addWidget(QLabel(_t("stats_location_label") + ":"))
        self._loc_combo = QComboBox()
        self._loc_combo.setMinimumWidth(150)
        filter_row.addWidget(self._loc_combo)

        filter_row.addSpacing(12)

        filter_row.addWidget(QLabel(_t("stats_type_label") + ":"))
        self._type_combo = QComboBox()
        for key, _ in _TYPES:
            self._type_combo.addItem(_t(key))
        filter_row.addWidget(self._type_combo)

        filter_row.addSpacing(12)

        filter_row.addWidget(QLabel(_t("stats_period_label") + ":"))
        self._period_combo = QComboBox()
        for key, _ in _PERIODS:
            self._period_combo.addItem(_t(key))
        filter_row.addWidget(self._period_combo)

        filter_row.addStretch()
        root.addLayout(filter_row)

        root.addWidget(_make_hline())

        # --- 3 Spalten ---
        cols = QHBoxLayout()
        cols.setSpacing(8)
        self._top_list   = self._make_card(_t("stats_top"),   cols)
        self._flop_list  = self._make_card(_t("stats_flop"),  cols)
        self._never_list = self._make_card(_t("stats_never"), cols)
        root.addLayout(cols, stretch=1)

        root.addWidget(_make_hline())

        # --- Histogramm ---
        root.addWidget(QLabel(_t("stats_histogram_label")))
        self._histogram = _HistogramWidget()
        root.addWidget(self._histogram)

        # Signals
        self._loc_combo.currentIndexChanged.connect(self._refresh)
        self._type_combo.currentIndexChanged.connect(self._refresh)
        self._period_combo.currentIndexChanged.connect(self._refresh)

        for lst in (self._top_list, self._flop_list, self._never_list):
            lst.itemDoubleClicked.connect(self._on_double_click)
            lst.setContextMenuPolicy(Qt.CustomContextMenu)
            lst.customContextMenuRequested.connect(self._on_context_menu)

    def _make_card(self, title: str, layout: QHBoxLayout) -> QListWidget:
        box = QGroupBox(title)
        box.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        inner = QVBoxLayout(box)
        inner.setContentsMargins(4, 4, 4, 4)
        lst = QListWidget()
        lst.setAlternatingRowColors(True)
        lst.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        lst.setToolTip(_t("stats_dblclick_hint"))
        lst.setSelectionMode(QAbstractItemView.ExtendedSelection)
        inner.addWidget(lst)
        layout.addWidget(box)
        return lst

    # ------------------------------------------------------------------
    # Daten
    # ------------------------------------------------------------------

    def _populate_location_combo(self):
        self._loc_combo.blockSignals(True)
        self._loc_combo.clear()
        self._location_ids = [None]
        self._loc_combo.addItem(_t("stats_location_all"))
        for loc in self.db.get_all_locations():
            self._location_ids.append(loc.id)
            self._loc_combo.addItem(loc.name)
        self._loc_combo.blockSignals(False)

    def _current_filters(self) -> tuple:
        idx = self._loc_combo.currentIndex()
        location_id = self._location_ids[idx] if idx < len(self._location_ids) else None
        type_key    = _TYPES[self._type_combo.currentIndex()][1]
        period_days = _PERIODS[self._period_combo.currentIndex()][1]
        since = None
        if period_days is not None:
            since = (datetime.now() - timedelta(days=period_days)).strftime("%Y-%m-%d %H:%M:%S")
        return location_id, type_key, since

    def _refresh(self):
        location_id, type_key, since = self._current_filters()

        played = self.db.play_counts(location_id, since, type_key)

        # TOP (meistgespielt, absteigend — Query liefert schon DESC)
        self._fill_list(self._top_list,
            [(r[0], r[1], r[2], r[3]) for r in played], show_count=True)

        # FLOP (wenigst gespielt, aufsteigend)
        flop = sorted(played, key=lambda r: r[3])
        self._fill_list(self._flop_list,
            [(r[0], r[1], r[2], r[3]) for r in flop], show_count=True)

        # Nie gespielt + Histogramm: alle Songs mit ihrem Count (0 = nie gespielt)
        played_map = {r[0]: r[3] for r in played}
        all_songs = self.db.songs_by_type(type_key)
        self._fill_list(self._never_list,
            [(sid, title, label, 0) for sid, title, label in all_songs
             if sid not in played_map], show_count=False)

        histogram_data = []
        for sid, title, label in all_songs:
            display = f"{label} – {title}" if label else title
            histogram_data.append((played_map.get(sid, 0), display))
        self._histogram.set_data(histogram_data)

    def _fill_list(self, lst: QListWidget, rows: list, show_count: bool):
        lst.setUpdatesEnabled(False)
        lst.clear()
        for song_id, title, label, count in rows:
            clean_title = f"{label} – {title}" if label else title
            display = f"{clean_title}  ({_t('stats_plays', count=count)})" if show_count else clean_title
            item = QListWidgetItem(display)
            item.setData(Qt.UserRole,     song_id)
            item.setData(Qt.UserRole + 1, clean_title)
            lst.addItem(item)
        lst.setUpdatesEnabled(True)

    def _on_double_click(self, item: QListWidgetItem):
        song_id = item.data(Qt.UserRole)
        if song_id and self.on_navigate_song:
            self.on_navigate_song(song_id)

    def _on_context_menu(self, pos: QPoint):
        lst = self.sender()
        item = lst.itemAt(pos)
        if not item:
            return
        selected = lst.selectedItems() or [item]

        song_ids     = [it.data(Qt.UserRole) for it in selected]
        clean_titles = [it.data(Qt.UserRole + 1) or it.text() for it in selected]

        menu = QMenu(self)
        act_pl = menu.addAction(_t("ctx_add_to_playlist"))
        act_pl.triggered.connect(lambda: self._add_selection_to_playlist(song_ids))
        act_notes = menu.addAction(_t("ctx_add_to_notes"))
        act_notes.triggered.connect(lambda: self._add_selection_to_notes(clean_titles))

        if len(selected) == 1:
            song_id = song_ids[0]
            def _after_rating():
                self._refresh()
                if self.on_song_rating_changed:
                    self.on_song_rating_changed(song_id)
            add_song_rating_actions(menu, self.db, song_id, refresh_callback=_after_rating)
        else:
            # Bei Mehrfachauswahl ergibt +-1 auf Quality/ERR keinen Sinn
            # (keine einheitliche Basis) — Aktionen nur ausgegraut anzeigen.
            menu.addSeparator()
            for key in ("ctx_quality_up", "ctx_quality_down",
                        "ctx_err_up", "ctx_err_down"):
                act = menu.addAction(_t(f"{key}_multi"))
                act.setEnabled(False)

        menu.exec(lst.viewport().mapToGlobal(pos))

    def _add_selection_to_playlist(self, song_ids: list):
        if not self.on_add_to_playlist:
            return
        for song_id in song_ids:
            self.on_add_to_playlist(song_id)

    def _add_selection_to_notes(self, titles: list):
        if not self.on_add_to_notes:
            return
        for title in titles:
            self.on_add_to_notes(title)

    # ------------------------------------------------------------------
    # Öffentliche API
    # ------------------------------------------------------------------

    def apply_skin(self, _skin_mgr):
        pass

    def refresh_locations(self):
        current = self._loc_combo.currentIndex()
        self._populate_location_combo()
        self._loc_combo.setCurrentIndex(min(current, self._loc_combo.count() - 1))


# ------------------------------------------------------------------
# Hilfsfunktion
# ------------------------------------------------------------------

def _make_hline() -> QFrame:
    line = QFrame()
    line.setFrameShape(QFrame.HLine)
    line.setFrameShadow(QFrame.Sunken)
    return line
